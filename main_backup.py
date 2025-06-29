import shutil
import zipfile

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_from_directory
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
import os
from datetime import datetime, timedelta
import json
import subprocess
import boto3
import io
from werkzeug.utils import secure_filename
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv,dotenv_values
import  gdown

import logging
from logging.handlers import RotatingFileHandler



load_dotenv()  # Load environment variables from .env file (if exists)

# Get configuration from environment variables with fallbacks
def get_config(key, default=None):
    """Get configuration from environment variables or .env file"""
    # First try environment variables (for production)
    value = os.environ.get(key)
    if value:
        return value
    
    # Then try .env file (for local development)
    try:
        sec_config = dotenv_values(".env")
        return sec_config.get(key, default)
    except:
        return default

app = Flask(__name__)
app.config['SECRET_KEY'] = 'vdvhvgh8764767363868'

# Configure MongoDB URI with fallback handling
mongo_uri = get_config('MONGO_CONNECTION')
if not mongo_uri:
    print("❌ ERROR: MONGO_CONNECTION not found in environment variables or .env file")
    print("🔧 Please set MONGO_CONNECTION in Render dashboard environment variables")
    # Use a default for testing (will fail gracefully)
    mongo_uri = "mongodb://localhost:27017/solar_plant_db"

app.config['MONGO_URI'] = mongo_uri
app.config['UPLOAD_FOLDER'] = 'uploads_data'
# Disable all reloading mechanisms
app.config['DEBUG'] = False
app.config['TESTING'] = False
# Maximum file upload size - Set to 50GB for large thermal imaging files
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 * 1024  # 50 GB
# Increase timeout settings for large file uploads
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year cache for static files

app.permanent_session_lifetime = timedelta(days=15)  # Expires in 30 minutes

handler = RotatingFileHandler('app.log', maxBytes=100000, backupCount=3)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

app.logger.addHandler(handler)

mongo = PyMongo(app)
bucket_name = get_config('bucket_name', 'sylo-energy')
s3_prefix = get_config('s3_prefix', 'https://sylo-energy.s3.ap-south-1.amazonaws.com')

# Import enhanced upload configuration
from upload_config import UploadConfig, StreamingUpload
# Import upload progress tracking
from upload_progress import UploadProgressTracker, StreamingUploadWithProgress, upload_status
import uuid

# Configure upload settings with enhanced support
ALLOWED_EXTENSIONS = UploadConfig.ALLOWED_EXTENSIONS

UPLOAD_FOLDER = 'uploads_data'
# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if file is allowed using enhanced configuration"""
    return UploadConfig.is_allowed_file(filename)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database collections
users_collection = mongo.db.users
plants_collection = mongo.db.plants
audits_collection = mongo.db.audits
data_uploads_collection = mongo.db.data_uploads
anomalies_collection = mongo.db.anomalies
analysis_collection = mongo.db.analysis
def get_s3_resource():
    s3 = boto3.client(
        's3',
        aws_access_key_id=get_config('aws_access_key_id'),
        aws_secret_access_key=get_config('aws_secret_access_key'),
        region_name=get_config('region_name', 'ap-south-1')  # example: Mumbai region
    )
    return s3


non_access_function= ['get_admin', 'user_status_update','register', 'add_audit', 'plants_api', 'upload_file', 'anomalies_api', 'upload', 'upload_images_parallel','get_geojson', 'assign_client']

def make_serializable(doc):
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            doc[key] = str(value)
        elif isinstance(value, datetime):
            doc[key] = value.strftime('%Y-%m-%d') if hasattr(value, 'strftime') else str(value)
    return doc
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or (f.__name__  in non_access_function and session.get('user_role') != 'admin'):
            return redirect(url_for('login'))

        return f(*args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('homepage'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            data = request.get_json()
            login_id = data.get('loginId')
            password = data.get('password')

            print(f"🔐 Login Attempt: {login_id}")
            
            user = users_collection.find_one({'email': login_id})
            if user and user['status'] == 0:
                print(f"❌ Login Failed - Account Disabled: {login_id}")
                return jsonify({'success': False, 'message': 'Invalid Access, Please Contact to site admin'})

            if user and user['password'] == password and user['status'] == 1:
                session['user_id'] = str(user['_id'])
                session['user_role'] = user['role']
                session['user_name'] = user.get('name', '')
                print(f"✅ Login Successful: {login_id} (Role: {user['role']})")
                return jsonify({'success': True, 'redirect': url_for('homepage')})
            else:
                print(f"❌ Login Failed - Invalid Credentials: {login_id}")
                return jsonify({'success': False, 'message': 'Invalid credentials'})
        except Exception as err:
            print(f"❌ Login Error: {str(err)}")
            return jsonify({'success': False, 'message': 'Invalid credentials'})

    print("🌐 Login Page Accessed")
    return render_template('login.html')


@app.route('/api/v1.0/register', methods=['POST'])
def register():
    data = request.get_json()
    login_id = data.get('loginId')
    password = data.get('password')
    fields= ['loginId', 'password']
    for field in fields:
        if data.get(field):
            pass
        else:
            return jsonify({'success': False, 'message': 'Registration failed'}), 400
    # Check if user already exists
    if users_collection.find_one({'email': login_id}) and login_id is not None:
        return jsonify({'success': False, 'message': 'User already exists'}), 400

    # Create new user
    # hashed_password = generate_password_hash(password)
    user_data = {
        'email': login_id,
        'password': str(password),
        'role': 'client',
        'status': 1,
        'created_at': datetime.utcnow()
    }

    result = users_collection.insert_one(user_data)

    if result.inserted_id:
        return jsonify({'success': True, 'message': 'User registered successfully'})
    else:
        return jsonify({'success': False, 'message': 'Registration failed'})


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/homepage')
@login_required
def homepage():
    # Get all plants for the user
    plants = [make_serializable(i) for i in list(plants_collection.find())]
    get_session_user = session.get('user_role')
    role= 1 if get_session_user == 'admin' else 0
    return render_template('homepage_1.html', plants=plants, check_mate=role)


@app.route('/api/plants', methods=['GET', 'POST'])
@login_required
def plants_api():
    if request.method == 'POST':
        if request.content_type and 'multipart/form-data' in request.content_type:
            # Handle form data with file upload
            data = request.form.to_dict()
            plant_photo = request.files.get('plant_photo')
            
            plant_photo_url = None
            if plant_photo and plant_photo.filename:
                # Save the uploaded file
                filename = secure_filename(plant_photo.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"plant_{timestamp}_{filename}"
                upload_path = os.path.join(UPLOAD_FOLDER, 'plant_photos')
                os.makedirs(upload_path, exist_ok=True)
                file_path = os.path.join(upload_path, filename)
                plant_photo.save(file_path)
                plant_photo_url = f"/static/uploads/plant_photos/{filename}"
        else:
            # Handle JSON data
            data = request.get_json()

        plant_data = {
            'name': data.get('name'),
            'client': data.get('client'),
            'latitude': float(data.get('latitude')),
            'longitude': float(data.get('longitude')),
            'address': data.get('address'),
            'pincode': data.get('pincode'),
            'state': data.get('state'),
            'country': data.get('country'),
            'ac_capacity': float(data.get('ac_capacity')),
            'dc_capacity': float(data.get('dc_capacity')),
            'land_area': float(data.get('land_area')),
            'plant_type': data.get('plant_type'),
            'mounting_type': data.get('mounting_type'),
            'module_type': data.get('module_type'),
            'total_modules_inspected': int(data.get('total_modules_inspected')),
            'created_by': session['user_id'],
            'no_of_inverters':data.get('no_of_inverters'),
            'no_of_blocks': data.get('no_of_blocks'),
            'inspection_date': datetime.strptime(data.get('inspection_date'), '%Y-%m-%d') if data.get('inspection_date') else None,
            'plant_photo': plant_photo_url,
            'created_at': datetime.utcnow(),
        }

        result = plants_collection.insert_one(plant_data)

        if result.inserted_id:
            return jsonify({'success': True, 'plant_id': str(result.inserted_id)})
        else:
            return jsonify({'success': False, 'message': 'Failed to create plant'})

    else:  # GET
        plants = list(plants_collection.find())
        # Convert ObjectId to string for JSON serialization
        for plant in plants:
            plant['_id'] = str(plant['_id'])
            plant['created_at'] = plant['created_at'].isoformat()

        return jsonify({'plants': plants})


@app.route('/plant/<plant_id>')
@login_required
def plant_detail(plant_id):
    plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
    if not plant:
        flash('Plant not found', 'error')
        return redirect(url_for('homepage'))

    # Get audits for this plant
    audits = list(audits_collection.find({'plant_id': str(plant['_id'])}).sort('_id', -1))
    analysis_data = []
    
    # Calculate analytics data and progress percentages
    analytics = {
        'power_loss': 0,
        'revenue_loss': 0,
    }
    
    # Progress percentages
    progress_data = {
        'pending': 25,     # Default values
        'resolved': 60,
        'not_found': 15,
        'high': 30,
        'medium': 45,
        'low': 25
    }
    
    try:
        if audits and len(audits) > 0:
            for audit in audits:
                try:
                    anomalies = json.loads(audit['anomalies'])['features']
                    for anomaly in anomalies:
                        analysis_data.append(anomaly['properties'])
                except:
                    continue
            
            # Calculate real percentages from analysis_data
            if analysis_data:
                total_anomalies = len(analysis_data)
                
                # Count by status (if available)
                pending_count = sum(1 for item in analysis_data if item.get('status', '').lower() == 'pending')
                resolved_count = sum(1 for item in analysis_data if item.get('status', '').lower() == 'resolved')
                not_found_count = total_anomalies - pending_count - resolved_count
                
                # Count by severity
                high_count = sum(1 for item in analysis_data if 'High' in item.get('Severity', ''))
                medium_count = sum(1 for item in analysis_data if 'Mid' in item.get('Severity', ''))
                low_count = sum(1 for item in analysis_data if 'Low' in item.get('Severity', ''))
                
                # Calculate percentages
                if total_anomalies > 0:
                    progress_data.update({
                        'pending': round((pending_count / total_anomalies) * 100),
                        'resolved': round((resolved_count / total_anomalies) * 100),
                        'not_found': round((not_found_count / total_anomalies) * 100),
                        'high': round((high_count / total_anomalies) * 100) if high_count else 20,
                        'medium': round((medium_count / total_anomalies) * 100) if medium_count else 30,
                        'low': round((low_count / total_anomalies) * 100) if low_count else 50
                    })
                
                # Calculate power loss and revenue loss
                analytics['power_loss'] = round(total_anomalies * 0.5, 1)  # 0.5 kW per anomaly
                analytics['revenue_loss'] = round(analytics['power_loss'] * 8760 * 3.5, 0)  # annual calculation
                
    except Exception as err:
        print("Error processing analysis_data:", err)
        
    get_session_user = session.get('user_role')
    role = 1 if get_session_user == 'admin' else 0
    audits = [make_serializable(i) for i in audits]
    
    print("audit length", len(audits))
    return render_template('plant_detail_1.html', 
                         plant=plant, 
                         audits=audits, 
                         analysis_data=analysis_data, 
                         analytics=analytics,
                         progress_data=progress_data,
                         check_mate=role)


@app.route('/plant/<plant_id>/overview')
@login_required
def plant_overview(plant_id):
    plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
    if not plant:
        flash('Plant not found', 'error')
        return redirect(url_for('homepage'))

    # Get audits for this plant
    audits = list(audits_collection.find({'plant_id': str(plant['_id'])}).sort('_id', -1))
    analysis_data = []
    
    # Calculate analytics data and progress percentages
    analytics = {
        'power_loss': 0,
        'revenue_loss': 0
    }
    
    progress_data = {
        'pending': 0,
        'resolved': 0,
        'not_found': 0,
        'high': 0,
        'medium': 0,
        'low': 0
    }
    
    try:
        if audits:
            for audit in audits:
                audit_id = str(audit['_id'])
                audit_analysis = list(analysis_collection.find({'audit_id': audit_id}))
                analysis_data.extend(audit_analysis)
            
            if analysis_data:
                total_count = len(analysis_data)
                
                # Status distribution
                pending_count = sum(1 for item in analysis_data if item.get('status') == 'Pending')
                resolved_count = sum(1 for item in analysis_data if item.get('status') == 'Resolved')
                not_found_count = sum(1 for item in analysis_data if item.get('status') == 'Not Found')
                
                # Severity distribution
                high_count = sum(1 for item in analysis_data if 'High' in item.get('severity', ''))
                medium_count = sum(1 for item in analysis_data if 'Medium' in item.get('severity', '') or 'Mid' in item.get('severity', ''))
                low_count = sum(1 for item in analysis_data if 'Low' in item.get('severity', ''))
                
                # Calculate percentages
                progress_data['pending'] = round((pending_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['resolved'] = round((resolved_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['not_found'] = round((not_found_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['high'] = round((high_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['medium'] = round((medium_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['low'] = round((low_count / total_count) * 100, 1) if total_count > 0 else 0
                
                # Calculate power and revenue loss
                total_anomalies = len(analysis_data)
                analytics['power_loss'] = round(total_anomalies * 0.5, 1)  # 0.5 kW per anomaly
                analytics['revenue_loss'] = round(analytics['power_loss'] * 8760 * 3.5, 0)  # annual calculation
                
    except Exception as err:
        print("Error processing analysis_data:", err)
        
    plant = make_serializable(plant)
    
    return render_template('plant_overview.html', 
                         plant=plant, 
                         analytics=analytics,
                         progress_data=progress_data)


# @app.route('/api/audits', methods=['POST'])
# @login_required
# def create_audit():
#     data = request.get_json()
#
#     audit_data = {
#         'name': data.get('name'),
#         'plant_id': data.get('plant_id'),
#         'start_date': datetime.strptime(data.get('start_date'), '%Y-%m-%d'),
#         'completion_date': datetime.strptime(data.get('completion_date'), '%Y-%m-%d'),
#         'project_code': data.get('project_code'),
#         'created_by': session['user_id'],
#         'created_at': datetime.utcnow(),
#         'status': 'active'
#
#     }
#     # Handle file uploads
#     uploaded_files = {}
#     print("--request.files",request.files)
#     # Handle GeoJSON file
#     if 'audit_geojson' in request.files:
#         geojson_file = request.files['audit_geojson']
#         if geojson_file and geojson_file.filename != '' and allowed_file(geojson_file.filename):
#             filename = secure_filename(geojson_file.filename)
#             filename = f"{audit_data['project_code']}_{filename}"
#             filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#             geojson_file.save(filepath)
#             uploaded_files['geojson_path'] = filepath
#         else:
#             return jsonify({'success': False, 'message': 'Invalid GeoJSON file'}), 400
#
#     # Check if the post request has the file part
#     # if 'file' not in request.files:
#     #     flash('No file part')
#     #     return redirect(request.url)
#     # file = request.files['file']
#     # If the user does not select a file, the browser submits an
#     # empty file without a filename.
#     # if file.filename == '':
#     #     flash('No selected file')
#     #     return redirect(request.url)
#     # if file and allowed_file(file.filename, data.get('file_type')):
#     #     filename = secure_filename(file.filename)
#     #     file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
#     #     return redirect(url_for('uploaded_file',
#     #                             filename=filename))
#
#     result = audits_collection.insert_one(audit_data)
#
#     if result.inserted_id:
#         return jsonify({'success': True, 'audit_id': str(result.inserted_id)})
#     else:
#         return jsonify({'success': False, 'message': 'Failed to create audit'})


@app.route('/api/audits', methods=['POST'])
def add_audit():
    try:
        # Get form data
        audit_data = {
            'name': request.form.get('name'),
            # 'project_code': request.form.get('project_code'),
            'plant_id': request.form.get('plant_id'),
            'created_by': session['user_id'],
            'created_at': datetime.utcnow(),
            'status': 'active',
            # 'audit_type':request.form.get('audit_type'),
            'start_date': datetime.strptime(request.form.get('start_date'), '%Y-%m-%d'),
            'completion_date': datetime.strptime(request.form.get('completion_date'), '%Y-%m-%d'),
            '_id':ObjectId()

        }

        # Validate required fields
        required_fields = ['name', 'start_date', 'completion_date', 'plant_id']
        for field in required_fields:
            if not audit_data[field]:
                print(f'{field} is required')
                return jsonify({'success': False, 'message': f'{field} is required'}), 400

        # Handle file uploads
        uploaded_files = {}
        file_path_all = f"/audit/{str(audit_data['plant_id'])}/{str(audit_data['_id'])}/"
        upload_path = os.path.join(
            app.config['UPLOAD_FOLDER'],
            str(audit_data['plant_id']),
            'audit',
            str(audit_data['_id'])
        )

        # Create the directory structure
        os.makedirs(upload_path, exist_ok=True)
        # Handle TIF file
        # if 'audit_tif' in request.files:
        #     tif_file = request.files['audit_tif']
        #     print("--geojson_file",tif_file, tif_file.filename)
        #
        #     if tif_file and tif_file.filename != '' and allowed_file(tif_file.filename):
        #         filename = secure_filename(tif_file.filename)
        #         # Add timestamp or unique ID to prevent filename conflicts
        #         filename = f"{audit_data['project_code']}_{filename}"
        #         filepath = os.path.join(upload_path,filename)
        #         audit_data['tif_file_name'] = filename
        #         tif_file.save(filepath)
        #         uploaded_files['tif_path'] = filepath
        #     else:
        #         return jsonify({'success': False, 'message': 'Invalid TIF file'}), 400

        # Handle GeoJSON file
        print("coming above geojson")
        geojson_file = request.files['audit_geojson']

        if 'audit_geojson' in request.files:
            # print("--geojson_file",geojson_file)

            if geojson_file and geojson_file.filename != '' and allowed_file(geojson_file.filename):
                filename = secure_filename(geojson_file.filename)
                filename = f"{filename}"
                filepath = os.path.join(upload_path, filename)
                geojson_file.save(filepath)
                uploaded_files['geojson_path'] = filepath
            else:
                print("invalid jeojso file")
                return jsonify({'success': False, 'message': 'Invalid GeoJSON file'}), 400

        # Combine form data with file paths
        complete_audit_data = {**audit_data, **uploaded_files}

        # Here you would typically save to your database
        # Example with MongoDB (if you're using it):
        # from pymongo import MongoClient
        # client = MongoClient('your_connection_string')
        # db = client.your_database
        # result = db.audits.insert_one(complete_audit_data)

        # For now, just print the data
        default_data = {}
        s3_path = f"audits/{str(audit_data['plant_id'])}/{str(audit_data['_id'])}/{geojson_file.filename}"
        audit_data['geojson_file_s3_path'] = s3_path
        print("coming above geojson",s3_path)

        anomalies_count = 0
        anomalies_corrected_count = 0
        with open(uploaded_files['geojson_path']) as f:

            geojson_data = json.load(f)
            geojson_str = json.dumps(geojson_data)
            geojson_bytes = io.BytesIO(geojson_str.encode('utf-8'))
            get_s3_resource().upload_fileobj(geojson_bytes, bucket_name, s3_path)
            print("data uploaded into s3 successfully")
            # print(geojson_data)
            import pandas as pd
            new_dict = geojson_data
            features = geojson_data['features']
            defect_data = []
            for i in features:
                if i['properties']['Anomaly'] is not None:
                    defect_data.append(i)
            new_dict['features'] = defect_data
            default_data = new_dict
            anomalies_count = len(defect_data)
        audit_data['anomalies'] = json.dumps(default_data)
        audit_data['anomalies_count'] =anomalies_count
        audit_data['anomalies_corrected_count'] = anomalies_corrected_count
        result = audits_collection.insert_one(audit_data)
        print("db insert result", result)

        return jsonify({
            'success': True,
            'message': 'Audit added successfully',
            'data': []
        }), 200

    except Exception as e:
        print(f"Error processing audit: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@app.route('/audit/<audit_id>')
@login_required
def audit_detail(audit_id):
    audit = audits_collection.find_one({'_id': ObjectId(audit_id)})
    if not audit:
        flash('Audit not found', 'error')
        return redirect(url_for('homepage'))
    # print("=----audit",audit['anomalies'])
    plant = plants_collection.find_one({'_id': ObjectId(audit['plant_id'])})

    # Get anomalies for this audit
    anomalies = json.loads(audit['anomalies'])['features'] if audit and audit.get('anomalies')  else []  #list(anomalies_collection.find({'audit_id': audit_id}))
    # print("---an", anomalies)
    #ortho_files = [i for i in audit['tif_files'] if i['status'] =='Completed'] if audit['tif_files'] else []
    tif_files = audit.get('tif_files')
    if isinstance(tif_files, list):
        ortho_files = [i for i in tif_files if i.get('status') == 'Completed']
    else:
        ortho_files = []
    s3_url = "http://127.0.0.1:5000/static/"
    thermal_ortho = [i for i in audit['tif_files'] if i['ortho_type'] =='thermal_ortho' and i['status'] =='Completed']
    visual_ortho = [i for i in audit['tif_files'] if i['ortho_type'] == 'visual_ortho' and i['status'] =='Completed']

    block_filters =[]
    anomaly_filter = []
    anomaly_count = {}
    # print("--anomalies",anomalies)
    if anomalies:
        for i in anomalies:
            block_value = i['properties']['Block']
            anomaly = i['properties']['Anomaly']
            if block_value not in block_filters and block_value is not None :
                block_filters.append(block_value)

            if anomaly not in anomaly_filter and block_value is not None:
                anomaly_filter.append(anomaly)
            if anomaly_count.get(anomaly):
                anomaly_count[anomaly] +=1
            else:
                anomaly_count[anomaly] = 1
    block_filters = sorted(block_filters, key=int)
    s3_base_path = f"{s3_prefix}/audits/{str(audit['plant_id'])}/{str(audit_id)}"
    s3_tif_base_url = s3_prefix
    fault_colors = {
            "Cell": "#FF0000",
            "Multi Cell": "#FFA500",
            "Bypass Diode": "#9C27B0",
            "Short Circuit": "#000000",
            "String Offline": "#FF1A94",
            "Module Power Mismatch": "#65E667",
            "Shading": "#E77148",
            "Plant Vegetation": "#2E7D32",
            "Other": "#00BFFF",
            "Junction Box": "#BFC494",
            "Physical Damage": "#C2185B",
            "Module Missing": "#FFFFFF",
            "Module Offline": "#FF1493",
        "Partial String Offline":"#ED0C7D"
        }
    fault_colors = {
        "Cell": "#FF0000",
        "Multi Cell": "#FFA500",
        "Bypass Diode": "#9C27B0",
        "Short Circuit": "#506E9A",
        "String Offline": "#FF1A94",
        "Module Power Mismatch": "#65E667",
        "Shading": "#E77148",
        "Vegetation": "#2E7D32",
        "Other": "#8C52FF",
        "Junction Box": "#BFC494",
        "Physical Damage": "#C2185B",
        "Module Missing": "#5CE1E6",
        "Module Offline": "#545454",
        "Partial String Offline": "#FF66C4"
    }
    audit = make_serializable(audit)

    return render_template('audit_detail.html', audit=audit, plant=plant, anomalies=anomalies,geojson= anomalies,s3_url=s3_url,thermal_ortho=thermal_ortho, visual_ortho=visual_ortho, block_filters=block_filters,anomaly_filter=anomaly_filter,s3_base_path=s3_base_path,s3_tif_base_url=s3_tif_base_url,anomaly_count=anomaly_count,fault_colors=fault_colors)


@app.route('/plant/<plant_id>/overview')
@login_required
def plant_overview(plant_id):
    plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
    if not plant:
        flash('Plant not found', 'error')
        return redirect(url_for('homepage'))

    # Get audits for this plant
    audits = list(audits_collection.find({'plant_id': str(plant['_id'])}).sort('_id', -1))
    analysis_data = []
    
    # Calculate analytics data and progress percentages
    analytics = {
        'power_loss': 0,
        'revenue_loss': 0
    }
    
    progress_data = {
        'pending': 0,
        'resolved': 0,
        'not_found': 0,
        'high': 0,
        'medium': 0,
        'low': 0
    }
    
    try:
        if audits:
            for audit in audits:
                audit_id = str(audit['_id'])
                audit_analysis = list(analysis_collection.find({'audit_id': audit_id}))
                analysis_data.extend(audit_analysis)
            
            if analysis_data:
                total_count = len(analysis_data)
                
                # Status distribution
                pending_count = sum(1 for item in analysis_data if item.get('status') == 'Pending')
                resolved_count = sum(1 for item in analysis_data if item.get('status') == 'Resolved')
                not_found_count = sum(1 for item in analysis_data if item.get('status') == 'Not Found')
                
                # Severity distribution
                high_count = sum(1 for item in analysis_data if 'High' in item.get('severity', ''))
                medium_count = sum(1 for item in analysis_data if 'Medium' in item.get('severity', '') or 'Mid' in item.get('severity', ''))
                low_count = sum(1 for item in analysis_data if 'Low' in item.get('severity', ''))
                
                # Calculate percentages
                progress_data['pending'] = round((pending_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['resolved'] = round((resolved_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['not_found'] = round((not_found_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['high'] = round((high_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['medium'] = round((medium_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['low'] = round((low_count / total_count) * 100, 1) if total_count > 0 else 0
                
                # Calculate power and revenue loss
                total_anomalies = len(analysis_data)
                analytics['power_loss'] = round(total_anomalies * 0.5, 1)  # 0.5 kW per anomaly
                analytics['revenue_loss'] = round(analytics['power_loss'] * 8760 * 3.5, 0)  # annual calculation
                
    except Exception as err:
        print("Error processing analysis_data:", err)
        
    plant = make_serializable(plant)
    
    return render_template('plant_overview.html', 
                         plant=plant, 
                         analytics=analytics,
                         progress_data=progress_data)

# @app.route('/api/audits', methods=['POST'])
# @login_required
# def create_audit():
#     data = request.get_json()
#
#     audit_data = {
#         'name': data.get('name'),
#         'plant_id': data.get('plant_id'),
#         'start_date': datetime.strptime(data.get('start_date'), '%Y-%m-%d'),
#         'completion_date': datetime.strptime(data.get('completion_date'), '%Y-%m-%d'),
#         'project_code': data.get('project_code'),
#         'created_by': session['user_id'],
#         'created_at': datetime.utcnow(),
#         'status': 'active'
#
#     }
#     # Handle file uploads
#     uploaded_files = {}
#     print("--request.files",request.files)
#     # Handle GeoJSON file
#     if 'audit_geojson' in request.files:
#         geojson_file = request.files['audit_geojson']
#         if geojson_file and geojson_file.filename != '' and allowed_file(geojson_file.filename):
#             filename = secure_filename(geojson_file.filename)
#             filename = f"{audit_data['project_code']}_{filename}"
#             filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#             geojson_file.save(filepath)
#             uploaded_files['geojson_path'] = filepath
#         else:
#             return jsonify({'success': False, 'message': 'Invalid GeoJSON file'}), 400
#
#     # Check if the post request has the file part
#     # if 'file' not in request.files:
#     #     flash('No file part')
#     #     return redirect(request.url)
#     # file = request.files['file']
#     # If the user does not select a file, the browser submits an
#     # empty file without a filename.
#     # if file.filename == '':
#     #     flash('No selected file')
#     #     return redirect(request.url)
#     # if file and allowed_file(file.filename, data.get('file_type')):
#     #     filename = secure_filename(file.filename)
#     #     file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
#     #     return redirect(url_for('uploaded_file',
#     #                             filename=filename))
#
#     result = audits_collection.insert_one(audit_data)
#
#     if result.inserted_id:
#         return jsonify({'success': True, 'audit_id': str(result.inserted_id)})
#     else:
#         return jsonify({'success': False, 'message': 'Failed to create audit'})


@app.route('/api/audits', methods=['POST'])
def add_audit():
    try:
        # Get form data
        audit_data = {
            'name': request.form.get('name'),
            # 'project_code': request.form.get('project_code'),
            'plant_id': request.form.get('plant_id'),
            'created_by': session['user_id'],
            'created_at': datetime.utcnow(),
            'status': 'active',
            # 'audit_type':request.form.get('audit_type'),
            'start_date': datetime.strptime(request.form.get('start_date'), '%Y-%m-%d'),
            'completion_date': datetime.strptime(request.form.get('completion_date'), '%Y-%m-%d'),
            '_id':ObjectId()

        }

        # Validate required fields
        required_fields = ['name', 'start_date', 'completion_date', 'plant_id']
        for field in required_fields:
            if not audit_data[field]:
                print(f'{field} is required')
                return jsonify({'success': False, 'message': f'{field} is required'}), 400

        # Handle file uploads
        uploaded_files = {}
        file_path_all = f"/audit/{str(audit_data['plant_id'])}/{str(audit_data['_id'])}/"
        upload_path = os.path.join(
            app.config['UPLOAD_FOLDER'],
            str(audit_data['plant_id']),
            'audit',
            str(audit_data['_id'])
        )

        # Create the directory structure
        os.makedirs(upload_path, exist_ok=True)
        # Handle TIF file
        # if 'audit_tif' in request.files:
        #     tif_file = request.files['audit_tif']
        #     print("--geojson_file",tif_file, tif_file.filename)
        #
        #     if tif_file and tif_file.filename != '' and allowed_file(tif_file.filename):
        #         filename = secure_filename(tif_file.filename)
        #         # Add timestamp or unique ID to prevent filename conflicts
        #         filename = f"{audit_data['project_code']}_{filename}"
        #         filepath = os.path.join(upload_path,filename)
        #         audit_data['tif_file_name'] = filename
        #         tif_file.save(filepath)
        #         uploaded_files['tif_path'] = filepath
        #     else:
        #         return jsonify({'success': False, 'message': 'Invalid TIF file'}), 400

        # Handle GeoJSON file
        print("coming above geojson")
        geojson_file = request.files['audit_geojson']

        if 'audit_geojson' in request.files:
            # print("--geojson_file",geojson_file)

            if geojson_file and geojson_file.filename != '' and allowed_file(geojson_file.filename):
                filename = secure_filename(geojson_file.filename)
                filename = f"{filename}"
                filepath = os.path.join(upload_path, filename)
                geojson_file.save(filepath)
                uploaded_files['geojson_path'] = filepath
            else:
                print("invalid jeojso file")
                return jsonify({'success': False, 'message': 'Invalid GeoJSON file'}), 400

        # Combine form data with file paths
        complete_audit_data = {**audit_data, **uploaded_files}

        # Here you would typically save to your database
        # Example with MongoDB (if you're using it):
        # from pymongo import MongoClient
        # client = MongoClient('your_connection_string')
        # db = client.your_database
        # result = db.audits.insert_one(complete_audit_data)

        # For now, just print the data
        default_data = {}
        s3_path = f"audits/{str(audit_data['plant_id'])}/{str(audit_data['_id'])}/{geojson_file.filename}"
        audit_data['geojson_file_s3_path'] = s3_path
        print("coming above geojson",s3_path)

        anomalies_count = 0
        anomalies_corrected_count = 0
        with open(uploaded_files['geojson_path']) as f:

            geojson_data = json.load(f)
            geojson_str = json.dumps(geojson_data)
            geojson_bytes = io.BytesIO(geojson_str.encode('utf-8'))
            get_s3_resource().upload_fileobj(geojson_bytes, bucket_name, s3_path)
            print("data uploaded into s3 successfully")
            # print(geojson_data)
            import pandas as pd
            new_dict = geojson_data
            features = geojson_data['features']
            defect_data = []
            for i in features:
                if i['properties']['Anomaly'] is not None:
                    defect_data.append(i)
            new_dict['features'] = defect_data
            default_data = new_dict
            anomalies_count = len(defect_data)
        audit_data['anomalies'] = json.dumps(default_data)
        audit_data['anomalies_count'] =anomalies_count
        audit_data['anomalies_corrected_count'] = anomalies_corrected_count
        result = audits_collection.insert_one(audit_data)
        print("db insert result", result)

        return jsonify({
            'success': True,
            'message': 'Audit added successfully',
            'data': []
        }), 200

    except Exception as e:
        print(f"Error processing audit: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@app.route('/audit/<audit_id>')
@login_required
def audit_detail(audit_id):
    audit = audits_collection.find_one({'_id': ObjectId(audit_id)})
    if not audit:
        flash('Audit not found', 'error')
        return redirect(url_for('homepage'))
    # print("=----audit",audit['anomalies'])
    plant = plants_collection.find_one({'_id': ObjectId(audit['plant_id'])})

    # Get anomalies for this audit
    anomalies = json.loads(audit['anomalies'])['features'] if audit and audit.get('anomalies')  else []  #list(anomalies_collection.find({'audit_id': audit_id}))
    # print("---an", anomalies)
    #ortho_files = [i for i in audit['tif_files'] if i['status'] =='Completed'] if audit['tif_files'] else []
    tif_files = audit.get('tif_files')
    if isinstance(tif_files, list):
        ortho_files = [i for i in tif_files if i.get('status') == 'Completed']
    else:
        ortho_files = []
    s3_url = "http://127.0.0.1:5000/static/"
    thermal_ortho = [i for i in audit['tif_files'] if i['ortho_type'] =='thermal_ortho' and i['status'] =='Completed']
    visual_ortho = [i for i in audit['tif_files'] if i['ortho_type'] == 'visual_ortho' and i['status'] =='Completed']

    block_filters =[]
    anomaly_filter = []
    anomaly_count = {}
    # print("--anomalies",anomalies)
    if anomalies:
        for i in anomalies:
            block_value = i['properties']['Block']
            anomaly = i['properties']['Anomaly']
            if block_value not in block_filters and block_value is not None :
                block_filters.append(block_value)

            if anomaly not in anomaly_filter and block_value is not None:
                anomaly_filter.append(anomaly)
            if anomaly_count.get(anomaly):
                anomaly_count[anomaly] +=1
            else:
                anomaly_count[anomaly] = 1
    block_filters = sorted(block_filters, key=int)
    s3_base_path = f"{s3_prefix}/audits/{str(audit['plant_id'])}/{str(audit_id)}"
    s3_tif_base_url = s3_prefix
    fault_colors = {
            "Cell": "#FF0000",
            "Multi Cell": "#FFA500",
            "Bypass Diode": "#9C27B0",
            "Short Circuit": "#000000",
            "String Offline": "#FF1A94",
            "Module Power Mismatch": "#65E667",
            "Shading": "#E77148",
            "Plant Vegetation": "#2E7D32",
            "Other": "#00BFFF",
            "Junction Box": "#BFC494",
            "Physical Damage": "#C2185B",
            "Module Missing": "#FFFFFF",
            "Module Offline": "#FF1493",
        "Partial String Offline":"#ED0C7D"
        }
    fault_colors = {
        "Cell": "#FF0000",
        "Multi Cell": "#FFA500",
        "Bypass Diode": "#9C27B0",
        "Short Circuit": "#506E9A",
        "String Offline": "#FF1A94",
        "Module Power Mismatch": "#65E667",
        "Shading": "#E77148",
        "Vegetation": "#2E7D32",
        "Other": "#8C52FF",
        "Junction Box": "#BFC494",
        "Physical Damage": "#C2185B",
        "Module Missing": "#5CE1E6",
        "Module Offline": "#545454",
        "Partial String Offline": "#FF66C4"
    }
    audit = make_serializable(audit)

    return render_template('audit_detail.html', audit=audit, plant=plant, anomalies=anomalies,geojson= anomalies,s3_url=s3_url,thermal_ortho=thermal_ortho, visual_ortho=visual_ortho, block_filters=block_filters,anomaly_filter=anomaly_filter,s3_base_path=s3_base_path,s3_tif_base_url=s3_tif_base_url,anomaly_count=anomaly_count,fault_colors=fault_colors)


@app.route('/plant/<plant_id>/overview')
@login_required
def plant_overview(plant_id):
    plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
    if not plant:
        flash('Plant not found', 'error')
        return redirect(url_for('homepage'))

    # Get audits for this plant
    audits = list(audits_collection.find({'plant_id': str(plant['_id'])}).sort('_id', -1))
    analysis_data = []
    
    # Calculate analytics data and progress percentages
    analytics = {
        'power_loss': 0,
        'revenue_loss': 0
    }
    
    progress_data = {
        'pending': 0,
        'resolved': 0,
        'not_found': 0,
        'high': 0,
        'medium': 0,
        'low': 0
    }
    
    try:
        if audits:
            for audit in audits:
                audit_id = str(audit['_id'])
                audit_analysis = list(analysis_collection.find({'audit_id': audit_id}))
                analysis_data.extend(audit_analysis)
            
            if analysis_data:
                total_count = len(analysis_data)
                
                # Status distribution
                pending_count = sum(1 for item in analysis_data if item.get('status') == 'Pending')
                resolved_count = sum(1 for item in analysis_data if item.get('status') == 'Resolved')
                not_found_count = sum(1 for item in analysis_data if item.get('status') == 'Not Found')
                
                # Severity distribution
                high_count = sum(1 for item in analysis_data if 'High' in item.get('severity', ''))
                medium_count = sum(1 for item in analysis_data if 'Medium' in item.get('severity', '') or 'Mid' in item.get('severity', ''))
                low_count = sum(1 for item in analysis_data if 'Low' in item.get('severity', ''))
                
                # Calculate percentages
                progress_data['pending'] = round((pending_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['resolved'] = round((resolved_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['not_found'] = round((not_found_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['high'] = round((high_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['medium'] = round((medium_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['low'] = round((low_count / total_count) * 100, 1) if total_count > 0 else 0
                
                # Calculate power and revenue loss
                total_anomalies = len(analysis_data)
                analytics['power_loss'] = round(total_anomalies * 0.5, 1)  # 0.5 kW per anomaly
                analytics['revenue_loss'] = round(analytics['power_loss'] * 8760 * 3.5, 0)  # annual calculation
                
    except Exception as err:
        print("Error processing analysis_data:", err)
        
    plant = make_serializable(plant)
    
    return render_template('plant_overview.html', 
                         plant=plant, 
                         analytics=analytics,
                         progress_data=progress_data)

# @app.route('/api/audits', methods=['POST'])
# @login_required
# def create_audit():
#     data = request.get_json()
#
#     audit_data = {
#         'name': data.get('name'),
#         'plant_id': data.get('plant_id'),
#         'start_date': datetime.strptime(data.get('start_date'), '%Y-%m-%d'),
#         'completion_date': datetime.strptime(data.get('completion_date'), '%Y-%m-%d'),
#         'project_code': data.get('project_code'),
#         'created_by': session['user_id'],
#         'created_at': datetime.utcnow(),
#         'status': 'active'
#
#     }
#     # Handle file uploads
#     uploaded_files = {}
#     print("--request.files",request.files)
#     # Handle GeoJSON file
#     if 'audit_geojson' in request.files:
#         geojson_file = request.files['audit_geojson']
#         if geojson_file and geojson_file.filename != '' and allowed_file(geojson_file.filename):
#             filename = secure_filename(geojson_file.filename)
#             filename = f"{audit_data['project_code']}_{filename}"
#             filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#             geojson_file.save(filepath)
#             uploaded_files['geojson_path'] = filepath
#         else:
#             return jsonify({'success': False, 'message': 'Invalid GeoJSON file'}), 400
#
#     # Check if the post request has the file part
#     # if 'file' not in request.files:
#     #     flash('No file part')
#     #     return redirect(request.url)
#     # file = request.files['file']
#     # If the user does not select a file, the browser submits an
#     # empty file without a filename.
#     # if file.filename == '':
#     #     flash('No selected file')
#     #     return redirect(request.url)
#     # if file and allowed_file(file.filename, data.get('file_type')):
#     #     filename = secure_filename(file.filename)
#     #     file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
#     #     return redirect(url_for('uploaded_file',
#     #                             filename=filename))
#
#     result = audits_collection.insert_one(audit_data)
#
#     if result.inserted_id:
#         return jsonify({'success': True, 'audit_id': str(result.inserted_id)})
#     else:
#         return jsonify({'success': False, 'message': 'Failed to create audit'})


@app.route('/api/audits', methods=['POST'])
def add_audit():
    try:
        # Get form data
        audit_data = {
            'name': request.form.get('name'),
            # 'project_code': request.form.get('project_code'),
            'plant_id': request.form.get('plant_id'),
            'created_by': session['user_id'],
            'created_at': datetime.utcnow(),
            'status': 'active',
            # 'audit_type':request.form.get('audit_type'),
            'start_date': datetime.strptime(request.form.get('start_date'), '%Y-%m-%d'),
            'completion_date': datetime.strptime(request.form.get('completion_date'), '%Y-%m-%d'),
            '_id':ObjectId()

        }

        # Validate required fields
        required_fields = ['name', 'start_date', 'completion_date', 'plant_id']
        for field in required_fields:
            if not audit_data[field]:
                print(f'{field} is required')
                return jsonify({'success': False, 'message': f'{field} is required'}), 400

        # Handle file uploads
        uploaded_files = {}
        file_path_all = f"/audit/{str(audit_data['plant_id'])}/{str(audit_data['_id'])}/"
        upload_path = os.path.join(
            app.config['UPLOAD_FOLDER'],
            str(audit_data['plant_id']),
            'audit',
            str(audit_data['_id'])
        )

        # Create the directory structure
        os.makedirs(upload_path, exist_ok=True)
        # Handle TIF file
        # if 'audit_tif' in request.files:
        #     tif_file = request.files['audit_tif']
        #     print("--geojson_file",tif_file, tif_file.filename)
        #
        #     if tif_file and tif_file.filename != '' and allowed_file(tif_file.filename):
        #         filename = secure_filename(tif_file.filename)
        #         # Add timestamp or unique ID to prevent filename conflicts
        #         filename = f"{audit_data['project_code']}_{filename}"
        #         filepath = os.path.join(upload_path,filename)
        #         audit_data['tif_file_name'] = filename
        #         tif_file.save(filepath)
        #         uploaded_files['tif_path'] = filepath
        #     else:
        #         return jsonify({'success': False, 'message': 'Invalid TIF file'}), 400

        # Handle GeoJSON file
        print("coming above geojson")
        geojson_file = request.files['audit_geojson']

        if 'audit_geojson' in request.files:
            # print("--geojson_file",geojson_file)

            if geojson_file and geojson_file.filename != '' and allowed_file(geojson_file.filename):
                filename = secure_filename(geojson_file.filename)
                filename = f"{filename}"
                filepath = os.path.join(upload_path, filename)
                geojson_file.save(filepath)
                uploaded_files['geojson_path'] = filepath
            else:
                print("invalid jeojso file")
                return jsonify({'success': False, 'message': 'Invalid GeoJSON file'}), 400

        # Combine form data with file paths
        complete_audit_data = {**audit_data, **uploaded_files}

        # Here you would typically save to your database
        # Example with MongoDB (if you're using it):
        # from pymongo import MongoClient
        # client = MongoClient('your_connection_string')
        # db = client.your_database
        # result = db.audits.insert_one(complete_audit_data)

        # For now, just print the data
        default_data = {}
        s3_path = f"audits/{str(audit_data['plant_id'])}/{str(audit_data['_id'])}/{geojson_file.filename}"
        audit_data['geojson_file_s3_path'] = s3_path
        print("coming above geojson",s3_path)

        anomalies_count = 0
        anomalies_corrected_count = 0
        with open(uploaded_files['geojson_path']) as f:

            geojson_data = json.load(f)
            geojson_str = json.dumps(geojson_data)
            geojson_bytes = io.BytesIO(geojson_str.encode('utf-8'))
            get_s3_resource().upload_fileobj(geojson_bytes, bucket_name, s3_path)
            print("data uploaded into s3 successfully")
            # print(geojson_data)
            import pandas as pd
            new_dict = geojson_data
            features = geojson_data['features']
            defect_data = []
            for i in features:
                if i['properties']['Anomaly'] is not None:
                    defect_data.append(i)
            new_dict['features'] = defect_data
            default_data = new_dict
            anomalies_count = len(defect_data)
        audit_data['anomalies'] = json.dumps(default_data)
        audit_data['anomalies_count'] =anomalies_count
        audit_data['anomalies_corrected_count'] = anomalies_corrected_count
        result = audits_collection.insert_one(audit_data)
        print("db insert result", result)

        return jsonify({
            'success': True,
            'message': 'Audit added successfully',
            'data': []
        }), 200

    except Exception as e:
        print(f"Error processing audit: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@app.route('/audit/<audit_id>')
@login_required
def audit_detail(audit_id):
    audit = audits_collection.find_one({'_id': ObjectId(audit_id)})
    if not audit:
        flash('Audit not found', 'error')
        return redirect(url_for('homepage'))
    # print("=----audit",audit['anomalies'])
    plant = plants_collection.find_one({'_id': ObjectId(audit['plant_id'])})

    # Get anomalies for this audit
    anomalies = json.loads(audit['anomalies'])['features'] if audit and audit.get('anomalies')  else []  #list(anomalies_collection.find({'audit_id': audit_id}))
    # print("---an", anomalies)
    #ortho_files = [i for i in audit['tif_files'] if i['status'] =='Completed'] if audit['tif_files'] else []
    tif_files = audit.get('tif_files')
    if isinstance(tif_files, list):
        ortho_files = [i for i in tif_files if i.get('status') == 'Completed']
    else:
        ortho_files = []
    s3_url = "http://127.0.0.1:5000/static/"
    thermal_ortho = [i for i in audit['tif_files'] if i['ortho_type'] =='thermal_ortho' and i['status'] =='Completed']
    visual_ortho = [i for i in audit['tif_files'] if i['ortho_type'] == 'visual_ortho' and i['status'] =='Completed']

    block_filters =[]
    anomaly_filter = []
    anomaly_count = {}
    # print("--anomalies",anomalies)
    if anomalies:
        for i in anomalies:
            block_value = i['properties']['Block']
            anomaly = i['properties']['Anomaly']
            if block_value not in block_filters and block_value is not None :
                block_filters.append(block_value)

            if anomaly not in anomaly_filter and block_value is not None:
                anomaly_filter.append(anomaly)
            if anomaly_count.get(anomaly):
                anomaly_count[anomaly] +=1
            else:
                anomaly_count[anomaly] = 1
    block_filters = sorted(block_filters, key=int)
    s3_base_path = f"{s3_prefix}/audits/{str(audit['plant_id'])}/{str(audit_id)}"
    s3_tif_base_url = s3_prefix
    fault_colors = {
            "Cell": "#FF0000",
            "Multi Cell": "#FFA500",
            "Bypass Diode": "#9C27B0",
            "Short Circuit": "#000000",
            "String Offline": "#FF1A94",
            "Module Power Mismatch": "#65E667",
            "Shading": "#E77148",
            "Plant Vegetation": "#2E7D32",
            "Other": "#00BFFF",
            "Junction Box": "#BFC494",
            "Physical Damage": "#C2185B",
            "Module Missing": "#FFFFFF",
            "Module Offline": "#FF1493",
        "Partial String Offline":"#ED0C7D"
        }
    fault_colors = {
        "Cell": "#FF0000",
        "Multi Cell": "#FFA500",
        "Bypass Diode": "#9C27B0",
        "Short Circuit": "#506E9A",
        "String Offline": "#FF1A94",
        "Module Power Mismatch": "#65E667",
        "Shading": "#E77148",
        "Vegetation": "#2E7D32",
        "Other": "#8C52FF",
        "Junction Box": "#BFC494",
        "Physical Damage": "#C2185B",
        "Module Missing": "#5CE1E6",
        "Module Offline": "#545454",
        "Partial String Offline": "#FF66C4"
    }
    audit = make_serializable(audit)

    return render_template('audit_detail.html', audit=audit, plant=plant, anomalies=anomalies,geojson= anomalies,s3_url=s3_url,thermal_ortho=thermal_ortho, visual_ortho=visual_ortho, block_filters=block_filters,anomaly_filter=anomaly_filter,s3_base_path=s3_base_path,s3_tif_base_url=s3_tif_base_url,anomaly_count=anomaly_count,fault_colors=fault_colors)


@app.route('/plant/<plant_id>/overview')
@login_required
def plant_overview(plant_id):
    plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
    if not plant:
        flash('Plant not found', 'error')
        return redirect(url_for('homepage'))

    # Get audits for this plant
    audits = list(audits_collection.find({'plant_id': str(plant['_id'])}).sort('_id', -1))
    analysis_data = []
    
    # Calculate analytics data and progress percentages
    analytics = {
        'power_loss': 0,
        'revenue_loss': 0
    }
    
    progress_data = {
        'pending': 0,
        'resolved': 0,
        'not_found': 0,
        'high': 0,
        'medium': 0,
        'low': 0
    }
    
    try:
        if audits:
            for audit in audits:
                audit_id = str(audit['_id'])
                audit_analysis = list(analysis_collection.find({'audit_id': audit_id}))
                analysis_data.extend(audit_analysis)
            
            if analysis_data:
                total_count = len(analysis_data)
                
                # Status distribution
                pending_count = sum(1 for item in analysis_data if item.get('status') == 'Pending')
                resolved_count = sum(1 for item in analysis_data if item.get('status') == 'Resolved')
                not_found_count = sum(1 for item in analysis_data if item.get('status') == 'Not Found')
                
                # Severity distribution
                high_count = sum(1 for item in analysis_data if 'High' in item.get('severity', ''))
                medium_count = sum(1 for item in analysis_data if 'Medium' in item.get('severity', '') or 'Mid' in item.get('severity', ''))
                low_count = sum(1 for item in analysis_data if 'Low' in item.get('severity', ''))
                
                # Calculate percentages
                progress_data['pending'] = round((pending_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['resolved'] = round((resolved_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['not_found'] = round((not_found_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['high'] = round((high_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['medium'] = round((medium_count / total_count) * 100, 1) if total_count > 0 else 0
                progress_data['low'] = round((low_count / total_count) * 100, 1) if total_count > 0 else 0
                
                # Calculate power and revenue loss
                total_anomalies = len(analysis_data)
                analytics['power_loss'] = round(total_anomalies * 0.5, 1)  # 0.5 kW per anomaly
                analytics['revenue_loss'] = round(analytics['power_loss'] * 8760 * 3.5, 0)  # annual calculation
                
    except Exception as err:
        print("Error processing analysis_data:", err)
        
    plant = make_serializable(plant)
    
    return render_template('plant_overview.html', 
                         plant=plant, 
                         analytics=analytics,
                         progress_data=progress_data)

# @app.route('/api/audits', methods=['POST'])
# @login_required
# def create_audit():
#     data = request.get_json()
#
#     audit_data = {
#         'name': data.get('name'),
#         'plant_id': data.get('plant_id'),
#         'start_date': datetime.strptime(data.get('start_date'), '%Y-%m-%d'),
#         'completion_date': datetime.strptime(data.get('completion_date'), '%Y-%m-%d'),
#         'project_code': data.get('project_code'),
#         'created_by': session['user_id'],
#         'created_at': datetime.utcnow(),
#         'status': 'active'
#
#     }
#     # Handle file uploads
#     uploaded_files = {}
#     print("--request.files",request.files)
#     # Handle GeoJSON file
#     if 'audit_geojson' in request.files:
#         geojson_file = request.files['audit_geojson']
#         if geojson_file and geojson_file.filename != '' and allowed_file(geojson_file.filename):
#             filename = secure_filename(geojson_file.filename)
#             filename = f"{audit_data['project_code']}_{filename}"
#             filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#             geojson_file.save(filepath)
#             uploaded_files['geojson_path'] = filepath
#         else:
#             return jsonify({'success': False, 'message': 'Invalid GeoJSON file'}), 400
#
#     # Check if the post request has the file part
#     # if 'file' not in request.files:
#     #     flash('No file part')
#     #     return redirect(request.url)
#     # file = request.files['file']
#     # If the user does not select a file, the browser submits an
#     # empty file without a filename.
#     # if file.filename == '':
#     #     flash('No selected file')
#     #     return redirect(request.url)
#     # if file and allowed_file(file.filename, data.get('file_type')):
#     #     filename = secure_filename(file.filename)
#     #     file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
#     #     return redirect(url_for('uploaded_file',
#     #                             filename=filename))
#
#     result = audits_collection.insert_one(audit_data)
#
#     if result.inserted_id:
#         return jsonify({'success': True, 'audit_id': str(result.inserted_id)})
#     else:
#         return jsonify({'success': False, 'message': 'Failed to create audit'})


@app.route('/api/audits', methods=['POST'])
def add_audit():
    try:
        # Get form data
        audit_data = {
            'name': request.form.get('name'),
            # 'project_code': request.form.get('project_code'),
            'plant_id': request.form.get('plant_id'),
            'created_by': session['user_id'],
            'created_at': datetime.utcnow(),
            'status': 'active',
            # 'audit_type':request.form.get('audit_type'),
            'start_date': datetime.strptime(request.form.get('start_date'), '%Y-%m-%d'),
            'completion_date': datetime.strptime(request.form.get('completion_date'), '%Y-%m-%d'),
            '_id':ObjectId()

        }

        # Validate required fields
        required_fields = ['name', 'start_date', 'completion_date', 'plant_id']
        for field in required_fields:
            if not audit_data[field]:
                print(f'{field} is required')
                return jsonify({'success': False, 'message': f'{field} is required'}), 400

        # Handle file uploads
        uploaded_files = {}
        file_path_all = f"/audit/{str(audit_data['plant_id'])}/{str(audit_data['_id'])}/"
        upload_path = os.path.join(
            app.config['UPLOAD_FOLDER'],
            str(audit_data['plant_id']),
            'audit',
            str(audit_data['_id'])
        )

        # Create the directory structure
        os.makedirs(upload_path, exist_ok=True)
        # Handle TIF file
        # if 'audit_tif' in request.files:
        #     tif_file = request.files['audit_tif']
        #     print("--geojson_file",tif_file, tif_file.filename)
        #
        #     if tif_file and tif_file.filename != '' and allowed_file(tif_file.filename):
        #         filename = secure_filename(tif_file.filename)
        #         # Add timestamp or unique ID to prevent filename conflicts
        #         filename = f"{audit_data['project_code']}_{filename}"
        #         filepath = os.path.join(upload_path,filename)
        #         audit_data['tif_file_name'] = filename
        #         tif_file.save(filepath)
        #         uploaded_files['tif_path'] = filepath
        #     else:
        #         return jsonify({'success': False, 'message': 'Invalid TIF file'}), 400

        # Handle GeoJSON file
        print("coming above geojson")
        geojson_file = request.files['audit_geojson']

        if 'audit_geojson' in request.files:
            # print("--geojson_file",geojson_file)

            if geojson_file and geojson_file.filename != '' and allowed_file(geojson_file.filename):
                filename = secure_filename(geojson_file.filename)
                filename = f"{filename}"
                filepath = os.path.join(upload_path, filename)
                geojson_file.save(filepath)
                uploaded_files['geojson_path'] = filepath
            else:
                print("invalid jeojso file")
                return jsonify({'success': False, 'message': 'Invalid GeoJSON file'}), 400

        # Combine form data with file paths
        complete_audit_data = {**audit_data, **uploaded_files}

        # Here you would typically save to your database
        # Example with MongoDB (if you're using it):
        # from pymongo import MongoClient
        # client = MongoClient('your_connection_string')
        # db = client.your_database
        # result = db.audits.insert_one(complete_audit_data)

        # For now, just print the data
        default_data = {}
        s3_path = f"audits/{str(audit_data['plant_id'])}/{str(audit_data['_id'])}/{geojson_file.filename}"
        audit_data['geojson_file_s3_path'] = s3_path
        print("coming above geojson",s3_path)

        anomalies_count = 0
        anomalies_corrected_count = 0
        with open(uploaded_files['geojson_path']) as f:

            geojson_data = json.load(f)
            geojson_str = json.dumps(geojson_data)
            geojson_bytes = io.BytesIO(geojson_str.encode('utf-8'))
            get_s3_resource().upload_fileobj(geojson_bytes, bucket_name, s3_path)
            print("data uploaded into s3 successfully")
            # print(geojson_data)
            import pandas as pd
            new_dict = geojson_data
            features = geojson_data['features']
            defect_data = []
            for i in features:
                if i['properties']['Anomaly'] is not None:
                    defect_data.append(i)
            new_dict['features'] = defect_data
            default_data = new_dict
            anomalies_count = len(defect_data)
        audit_data['anomalies'] = json.dumps(default_data)
        audit_data['anomalies_count'] =anomalies_count
        audit_data['anomalies_corrected_count'] = anomalies_corrected_count
        result = audits_collection.insert_one(audit_data)
        print("db insert result", result)

        return jsonify({
            'success': True,
            'message': 'Audit added successfully',
            'data': []
        }), 200

    except Exception as e:
        print(f"Error processing audit: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@app.route('/audit/<audit_id>')
@login_required
def audit_detail(audit_id):
    audit = audits_collection.find_one({'_id': ObjectId(audit_id)})
    if not audit:
        flash('Audit not found', 'error')
        return redirect(url_for('homepage'))
    # print("=----audit",audit['anomalies'])
    plant = plants_collection.find_one({'_id': ObjectId(audit['plant_id'])})

    # Get anomalies for this audit
    anomalies = json.loads(audit['anomalies'])['features'] if audit and audit.get('anomalies')  else []  #list(anomalies_collection.find({'audit_id': audit_id}))
    # print("---an", anomalies)
    #ortho_files = [i for i in audit['tif_files'] if i['status'] =='Completed'] if audit['tif_files'] else []
    tif_files = audit.get('tif_files')
    if isinstance(tif_files, list):
        ortho_files = [i for i in tif_files if i.get('status') == 'Completed']
    else:
        ortho_files = []
    s3_url = "http://127.0.0.1:5000/static/"
    thermal_ortho = [i for i in audit['tif_files'] if i['ortho_type'] =='thermal_ortho' and i['status'] =='Completed']
    visual_ortho = [i for i in audit['tif_files'] if i['ortho_type'] == 'visual_ortho' and i['status'] =='Completed']

    block_filters =[]
    anomaly_filter = []
    anomaly_count = {}
    # print("--anomalies",anomalies)
    if anomalies:
        for i in anomalies:
            block_value = i['properties']['Block']
            anomaly = i['properties']['Anomaly']
            if block_value not in block_filters and block_value is not None :
                block_filters.append(block_value)

            if anomaly not in anomaly_filter and block_value is not None:
                anomaly_filter.append(anomaly)
            if anomaly_count.get(anomaly):
                anomaly_count[anomaly] +=1
            else:
                anomaly_count[anomaly] = 1
    block_filters = sorted(block_filters, key=int)
    s3_base_path = f"{s3_prefix}/audits/{str(audit['plant_id'])}/{str(audit_id)}"
    s3_tif_base_url = s3_prefix
    fault_colors = {
            "Cell": "#FF0000",
            "Multi Cell": "#FFA500",
            "Bypass Diode": "#9C27B0",
            "Short Circuit": "#000000",
            "String Offline": "#FF1A94",
            "Module Power Mismatch": "#65E667",
            "Shading": "#E77148",
            "Plant Vegetation": "#2E7D32",
            "Other": "#00BFFF",
            "Junction Box": "#BFC494",
            "Physical Damage": "#C2185B",
            "Module Missing": "#FFFFFF",
            "Module Offline": "#FF1493",
        "Partial String Offline":"#ED0C7D"
        }
    fault_colors = {
        "Cell": "#FF0000",
        "Multi Cell": "#FFA500",
        "Bypass Diode": "#9C27B0",
        "Short Circuit": "#506E9A",
        "String Offline": "#FF1A94",
        "Module Power Mismatch": "#65E667",
        "Shading": "#E77148",
        "Vegetation": "#2E7D32",
        "Other": "#8C52FF",
        "Junction Box": "#BFC494",
        "Physical Damage": "#C2185B",
        "Module Missing": "#5CE1E6",
        "Module Offline": "#545454",
        "Partial String Offline": "#FF66C4"
    }
    audit = make_serializable(audit)

    return render_template('audit_detail.html', audit=audit, plant=plant, anomalies=anomalies,geojson= anomalies,s3_url=s3_url,thermal_ortho=thermal_ortho, visual_ortho=visual_ortho, block_filters=block_filters,anomaly_filter=anomaly_filter,s3_base_path=s3_base_path,s3_tif_base_url=s3_tif_base_url,anomaly_count=anomaly_count,fault_colors=fault_colors)


@app.route('/plant/<plant_id>/overview')
@login_required
def plant_overview(plant_id):
    plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
    if not plant:
        flash('Plant not found', 'error')
        return redirect(url_for('homepage'))

    # Get audits for this plant
    audits = list(audits_collection.find({'plant_id': str(plant['_id'])}).sort('_id', -1))
    analysis_data = []
    
    # Calculate analytics data and progress percentages
    analytics = {
        'power_loss': 0,
        'revenue_loss': 0
    }
    
    progress_data = {
        'pending': 0,
        'resolved': 0,
        'not_found': 0,
        'high': 0,
        'medium': 0,
        'low': 0
    }
    
    try:
        if audits:
            for audit in audits:
                audit_id = str(audit['_id'])
                audit_analysis = list(analysis_collection.find({'audit_id': audit_id}))
                analysis_data.extend(audit_analysis)
            
            if analysis_data:
                total_count = len(analysis_data)
                
                # Status distribution
                pending_count = sum(1 for item in analysis_data if item.get('status') == 'Pending')
                resolved_count = sum(1 for item in analysis_data if item.get('status') == 'Resolved')
                not_found_count = sum(1 for item in analysis_data if item.get('status') == '