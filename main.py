import shutil
import zipfile

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_file
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

# PDF generation imports
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from PIL import Image as PILImage
    import requests
    PDF_ENABLED = True
except ImportError:
    PDF_ENABLED = False
    print("PDF generation libraries not found. PDF functionality will be disabled.")



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

app = Flask(__name__, static_url_path='/static')
app.config['SECRET_KEY'] = 'vdvhvgh8764767363868'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable caching for static files

# Add cache control headers to prevent browser caching
@app.after_request
def add_header(response):
    """
    Add headers to both force latest IE rendering engine or Chrome Frame,
    and also to prevent caching of dynamic and static content
    """
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

# Add a timestamp as a context variable to all templates for cache-busting
@app.context_processor
def inject_now():
    from datetime import datetime
    return {'now': datetime.now().timestamp()}

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

# Additional configuration for handling very large files
import signal
import socket

# Increase socket timeout for large file operations
socket.setdefaulttimeout(7200)  # 2 hours timeout for socket operations

# Configure threading for better performance with large files
import threading
threading.stack_size(32768)  # Increase stack size for threads

# Configure temporary directory for large file processing
import tempfile
tempfile.tempdir = app.config['UPLOAD_FOLDER']

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
anomaly_updates_collection = mongo.db.anomaly_updates
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
            doc[key] = value.date().isoformat()
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
    return render_template('homepage.html', plants=plants, check_mate=role)


@app.route('/api/plants', methods=['GET', 'POST'])
@login_required
def plants_api():
    if request.method == 'POST':
        # Handle form data instead of JSON for file upload support
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.form
            
            # Handle plant image upload
            plant_photo = None
            if 'plant_image' in request.files:
                file = request.files['plant_image']
                if file and file.filename != '':
                    # Generate unique filename
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"{timestamp}_{secure_filename(file.filename)}"
                    
                    # Save file
                    upload_path = os.path.join('uploads_data', filename)
                    file.save(upload_path)
                    plant_photo = f'/uploads_data/{filename}'
        else:
            # Handle JSON data (for compatibility)
            data = request.get_json()

        plant_data = {
            'name': data.get('name'),
            'client': data.get('client'),
            'latitude': float(data.get('latitude')) if data.get('latitude') else 0.0,
            'longitude': float(data.get('longitude')) if data.get('longitude') else 0.0,
            'address': data.get('address'),
            'pincode': data.get('pincode'),
            'state': data.get('state'),
            'country': data.get('country'),
            'ac_capacity': float(data.get('ac_capacity')) if data.get('ac_capacity') else 0.0,
            'dc_capacity': float(data.get('dc_capacity')) if data.get('dc_capacity') else 0.0,
            'land_area': float(data.get('land_area')) if data.get('land_area') else 0.0,
            'plant_type': data.get('plant_type'),
            'mounting_type': data.get('mounting_type'),
            'module_type': data.get('module_type'),
            'total_modules_inspected': int(data.get('total_modules_inspected')) if data.get('total_modules_inspected') else 0,
            'created_by': session['user_id'],
            'no_of_inverters': int(data.get('no_of_inverters')) if data.get('no_of_inverters') else 0,
            'no_of_blocks': int(data.get('no_of_blocks')) if data.get('no_of_blocks') else 0,
            'installation_date': data.get('installation_date'),
            'created_at': datetime.utcnow(),
        }
        
        # Add plant photo if uploaded
        if 'plant_photo' in locals():
            plant_data['plant_photo'] = plant_photo

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
            if 'created_at' in plant:
                plant['created_at'] = plant['created_at'].isoformat()

        return jsonify({'plants': plants})


@app.route('/api/plants/<plant_id>', methods=['GET', 'PUT'])
@login_required
def single_plant_api(plant_id):
    if request.method == 'GET':
        # Fetch single plant
        plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
        if not plant:
            return jsonify({'success': False, 'message': 'Plant not found'}), 404
        
        # Convert ObjectId to string and handle datetime
        plant['_id'] = str(plant['_id'])
        if 'created_at' in plant:
            plant['created_at'] = plant['created_at'].isoformat()
        
        return jsonify(plant)
    
    elif request.method == 'PUT':
        # Update plant details
        try:
            # Handle form data for multipart/form-data
            if request.content_type and 'multipart/form-data' in request.content_type:
                data = request.form
            else:
                # Handle JSON data
                data = request.get_json() or {}

            update_data = {}
            
            # Only update fields that are provided
            if data.get('name'):
                update_data['name'] = data.get('name')
            if data.get('client'):
                update_data['client'] = data.get('client')
            if data.get('state'):
                update_data['state'] = data.get('state')
            if data.get('country'):
                update_data['country'] = data.get('country')
            if data.get('ac_capacity'):
                update_data['ac_capacity'] = float(data.get('ac_capacity'))
            if data.get('dc_capacity'):
                update_data['dc_capacity'] = float(data.get('dc_capacity'))
            if data.get('module_type'):
                update_data['module_type'] = data.get('module_type')
            if data.get('mounting_type'):
                update_data['mounting_type'] = data.get('mounting_type')
            if data.get('land_area'):
                update_data['land_area'] = data.get('land_area')
            if data.get('total_modules_inspected'):
                update_data['total_modules_inspected'] = int(data.get('total_modules_inspected'))
            if data.get('no_of_inverters'):
                update_data['no_of_inverters'] = int(data.get('no_of_inverters'))
            if data.get('no_of_blocks'):
                update_data['no_of_blocks'] = int(data.get('no_of_blocks'))
            if data.get('inspection_date'):
                update_data['inspection_date'] = data.get('inspection_date')
            
            # Add update timestamp
            update_data['updated_at'] = datetime.utcnow()

            # Update the plant
            result = plants_collection.update_one(
                {'_id': ObjectId(plant_id)},
                {'$set': update_data}
            )

            if result.modified_count > 0:
                return jsonify({'success': True, 'message': 'Plant updated successfully'})
            else:
                return jsonify({'success': False, 'message': 'No changes made or plant not found'})

        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500


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
    try:

        if audits and len(audits) >0:
            for i in json.loads(audits[0]['anomalies'])['features']:
                analysis_data.append(i['properties'])

    except Exception as err:
        print("Error into get features for analysis_data",err)
    get_session_user = session.get('user_role')
    role = 1 if get_session_user == 'admin' else 0
    audits = [make_serializable(i) for i in audits]
    print("audit length", len(audits))
    return render_template('plant_detail_1.html', plant=plant, audits=audits,analysis_data=analysis_data,check_mate=role)


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

    # Add timestamp for cache busting
    from datetime import datetime
    now = datetime.now().timestamp()
    
    return render_template('audit_detail.html', 
                          audit=audit, 
                          plant=plant, 
                          anomalies=anomalies,
                          geojson=anomalies,
                          s3_url=s3_url,
                          thermal_ortho=thermal_ortho, 
                          visual_ortho=visual_ortho, 
                          block_filters=block_filters,
                          anomaly_filter=anomaly_filter,
                          s3_base_path=s3_base_path,
                          s3_tif_base_url=s3_tif_base_url,
                          anomaly_count=anomaly_count,
                          fault_colors=fault_colors,
                          now=now)


@app.route('/data')
@login_required
def data_page():
    # Get all plants for dropdown
    plants = list(plants_collection.find())
    # Get all audits for dropdown
    audits = list(audits_collection.find())

    return render_template('data_upload.html', plants=plants, audits=audits)


@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    upload_id = str(uuid.uuid4())
    
    try:
        file_type = request.form.get('file_type')
        plant_id = request.form.get('plant_id')
        audit_id = request.form.get('audit_id')
        project_code = request.form.get('project_code')

        if 'file' not in request.files:
            print(f"❌ Upload Failed [{upload_id}]: No file selected")
            return jsonify({'success': False, 'message': 'No file selected', 'upload_id': upload_id})

        file = request.files['file']

        if file.filename == '':
            print(f"❌ Upload Failed [{upload_id}]: No file selected")
            return jsonify({'success': False, 'message': 'No file selected', 'upload_id': upload_id})

        if not file or not allowed_file(file.filename):
            print(f"❌ Upload Failed [{upload_id}]: Invalid file type - {file.filename}")
            return jsonify({'success': False, 'message': 'Invalid file type', 'upload_id': upload_id})

        # Get file size
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
        
        print(f"🚀 Starting Upload [{upload_id}]: {file.filename} ({file_size} bytes)")
        
        # Create progress tracker
        tracker = UploadProgressTracker(upload_id, file.filename, file_size)
        tracker.set_stage('preparing', 'Preparing file upload')

        filename = secure_filename(file.filename)
        # Create unique filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
        filename = timestamp + filename

        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Use streaming upload with progress tracking
        streaming_upload = StreamingUploadWithProgress(file, file_path, tracker)
        result = streaming_upload.save_with_progress()
        
        if result['success']:
            tracker.set_stage('saving_metadata', 'Saving file metadata to database')
            
            # Save file info to database
            upload_data = {
                'filename': filename,
                'original_filename': file.filename,
                'file_type': file_type,
                'file_path': file_path,
                'plant_id': plant_id,
                'audit_id': audit_id,
                'project_code': project_code,
                'uploaded_by': session['user_id'],
                'uploaded_at': datetime.utcnow(),
                'upload_id': upload_id,
                'file_size': file_size
            }

            db_result = data_uploads_collection.insert_one(upload_data)

            if db_result.inserted_id:
                tracker.complete(file_path)
                print(f"✅ Upload Successful [{upload_id}]: {filename}")
                return jsonify({
                    'success': True, 
                    'message': 'File uploaded successfully',
                    'upload_id': upload_id,
                    'filename': filename,
                    'file_size': file_size
                })
            else:
                tracker.fail('Failed to save file metadata to database')
                print(f"❌ Database Error [{upload_id}]: Failed to save file info")
                return jsonify({'success': False, 'message': 'Failed to save file info', 'upload_id': upload_id})
        else:
            print(f"❌ Upload Failed [{upload_id}]: File save failed")
            return jsonify({'success': False, 'message': 'Failed to save file', 'upload_id': upload_id})

    except Exception as e:
        print(f"❌ Upload Exception [{upload_id}]: {str(e)}")
        if upload_id in upload_status:
            upload_status[upload_id].fail(str(e))
        return jsonify({'success': False, 'message': f'Upload failed: {str(e)}', 'upload_id': upload_id})


@app.route('/api/anomalies', methods=['GET', 'POST'])
@login_required
def anomalies_api():
    if request.method == 'POST':
        data = request.get_json()

        anomaly_data = {
            'audit_id': data.get('audit_id'),
            'plant_id': data.get('plant_id'),
            'type': data.get('type'),
            'severity': data.get('severity'),
            'latitude': float(data.get('latitude')),
            'longitude': float(data.get('longitude')),
            'block': data.get('block'),
            'module_info': data.get('module_info'),
            'image_path': data.get('image_path'),
            'status': 'pending',  # default status
            'detected_at': datetime.utcnow(),
            'created_by': session['user_id']
        }

        result = anomalies_collection.insert_one(anomaly_data)

        if result.inserted_id:
            return jsonify({'success': True, 'anomaly_id': str(result.inserted_id)})
        else:
            return jsonify({'success': False, 'message': 'Failed to create anomaly'})

    else:  # GET
        audit_id = request.args.get('audit_id')
        plant_id = request.args.get('plant_id')

        query = {}
        if audit_id:
            query['audit_id'] = audit_id
        if plant_id:
            query['plant_id'] = plant_id

        anomalies = list(anomalies_collection.find(query))

        # Convert ObjectId to string for JSON serialization
        for anomaly in anomalies:
            anomaly['_id'] = str(anomaly['_id'])
            anomaly['detected_at'] = anomaly['detected_at'].isoformat()

        return jsonify({'anomalies': anomalies})


@app.route('/api/anomalies/<audit_id>/status', methods=['PUT'])
@login_required
def update_anomaly_status(audit_id):
    data = request.get_json()
    new_status = data.get('status')
    anomaly_id = data.get('anomaly_id')
    if new_status not in ['pending', 'resolved', 'anomaly_id']:
        print("-----")
        return jsonify({'success': False, 'message': 'Invalid status'})
    audit = audits_collection.find_one({"_id":ObjectId(audit_id)}, {"anomalies":1})
    anomalies = json.loads(audit['anomalies']) if audit and audit.get('anomalies') else []
    print("-----")
    anomalies_corrected_count =  {"anomalies_corrected_count": -1} if  new_status  =='pending' else  {"anomalies_corrected_count": 1}
    if anomalies and anomalies['features']:
        new_dict = anomalies
        features = anomalies['features']
        defect_data = []
        for i in features:
            if i['properties']['Image name'] == anomaly_id:
                up_data_new = i
                up_data_new['resolve_status']= new_status
                defect_data.append(up_data_new)
            else:
                defect_data.append(i)

        new_dict['features'] = defect_data
        default_data = new_dict
        audit_data = {}
        audit_data['anomalies'] = json.dumps(default_data)
        result = audits_collection.update_one({'_id': ObjectId(audit_id)},{"$set":audit_data,
                                                                           "$inc":anomalies_corrected_count
                                                                           })
    if audit:
        return jsonify({'success': True, 'message': 'Status updated successfully'})
    else:
        return jsonify({'success': False, 'message': 'Failed to update status'})


@app.route('/api/dashboard/stats')
@login_required
def dashboard_stats():
    # Get overall statistics
    total_plants = plants_collection.count_documents({})
    total_audits = audits_collection.count_documents({})

    # Anomaly statistics
    total_anomalies = anomalies_collection.count_documents({})
    resolved_anomalies = anomalies_collection.count_documents({'status': 'resolved'})
    pending_anomalies = anomalies_collection.count_documents({'status': 'pending'})

    # Anomaly types distribution
    anomaly_types = list(anomalies_collection.aggregate([
        {'$group': {'_id': '$type', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ]))

    stats = {
        'total_plants': total_plants,
        'total_audits': total_audits,
        'total_anomalies': total_anomalies,
        'resolved_anomalies': resolved_anomalies,
        'pending_anomalies': pending_anomalies,
        'anomaly_types': anomaly_types
    }

    return jsonify(stats)


# Optional: Route to handle file downloads/viewing
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# @app.route('/audi_tif/upload', methods=['POST'])
# def upload():
#     print("coming here")
#     file = request.files.get('tif_file_name')
#     print("---file", file)
#     try:
#         print("request.form:", request.form)
#     except Exception as e:
#         print("error accessing request.form:", e)
#     print("request", request.form)
#     file = request.files['tif_file_name']
#     fields= ['audit_type', 'plant_id',  'audit_id']
#     inputs = {}
#     data = request.form
#     for i in fields:
#         if data.get(i):
#             inputs[i] = data.get(i)
#         else:
#             print("comng here")
#             return jsonify({"status": False, "error": "Invalid params"}), 400
#
#
#
#     file_path = f"audits/{inputs['plant_id']}/{inputs['audit_id']}/{inputs['audit_type']}/{file.filename}"
#     file_path = file_path
#     new_task = {
#         "tif_path": file_path,
#         "status": "In Progress",
#         "ortho_type": inputs['audit_type'],
#         "created_at": datetime.utcnow()
#     }
#
#     existing = audits_collection.find_one({
#         "_id": ObjectId(inputs['audit_id']),
#         "tif_files.tif_path": file_path
#     })
#
#     if existing:
#         audits_collection.update_one(
#             {
#                 "_id": ObjectId(inputs['audit_id']),
#                 "tif_files.tif_path": file_path
#             },
#             {
#                 "$set": {
#                     "tif_files.$.status": 'In Progress',
#                     "created_at": datetime.utcnow()
#                 }
#             }
#         )
#     else:
#         audits_collection.update_one(
#             {"_id": ObjectId(inputs['audit_id'])},
#             {"$push": {"tif_files": new_task}}
#         )
#
#     # Save original TIF
#     upload_path = os.path.join(
#         app.config['UPLOAD_FOLDER'],
#         str(inputs['plant_id']),
#         'audit',
#         str(inputs['audit_id'])
#     )
#     input_path = os.path.join(upload_path, file.filename)
#     os.makedirs(upload_path, exist_ok=True)
#     file.save(input_path)
#     output_cog_path = os.path.join(upload_path, f"COG_{file.filename}")
#
#     # Convert to COG
#     try:
#         subprocess.check_call([
#             "gdal_translate", "-of", "COG",
#             "-co", "COMPRESS=DEFLATE",
#             "-co", "BLOCKSIZE=512",
#             # "-co", "OVERVIEWS=AUTO",
#             "-co", "BIGTIFF=YES",
#             input_path,
#             output_cog_path
#         ])
#     except subprocess.CalledProcessError as e:
#         print("fnfkjnfkj", e)
#         return jsonify({'error': 'GDAL conversion failed', 'details': str(e)}), 500
#
#
#
#
#
#
#
#     try:
#
#         with open(output_cog_path, "rb") as f:
#             get_s3_resource().upload_fileobj(f, bucket_name, file_path)
#
#         # os.rmdir(upload_path)
#         try:
#             shutil.rmtree(upload_path)
#         except OSError as e:
#             print("Error: %s - %s." % (e.filename, e.strerror))
#
#         audits_collection.update_one(
#             {
#                 "_id": ObjectId(inputs['audit_id']),
#                 "tif_files.tif_path": file_path  # Match the element inside the array
#             },
#             {
#                 "$set": {
#                     "tif_files.$.status": "Completed"  # $ points to the matched array element
#                 }
#             }
#         )
#     except Exception as  err:
#         print("Eerr", err)
#         audits_collection.update_one(
#             {
#                 "_id": ObjectId(inputs['audit_id']),
#                 "tif_files.tif_path": file_path  # Match the element inside the array
#             },
#             {
#                 "$set": {
#                     "tif_files.$.status": "failed"  # $ points to the matched array element
#                 }
#             }
#         )
#
#
#     return "OK"



def copy_to_s3(local_file_path, s3_bucket_path, aws_access_key, aws_secret_key):
    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = aws_access_key
    env["AWS_SECRET_ACCESS_KEY"] = aws_secret_key
    env["AWS_DEFAULT_REGION"] = 'ap-south-1'

    try:
        command = ["aws", "s3", "cp", local_file_path, s3_bucket_path]
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1,
                              text=True) as process:
            for line in process.stdout:
                print(line, end='')  # shows real-time CLI progress bar

        return True
    except subprocess.CalledProcessError as e:
        print("Upload failed:", e)
        return False


@app.route('/audi_tif/upload', methods=['POST'])
def upload():
    upload_id = str(uuid.uuid4())
    
    try:
        print(f"🚀 Starting TIF Upload [{upload_id}]")
        print("request", request.form)
        
        fields= ['audit_type', 'plant_id',  'audit_id','g_url', 'tif_file_name']
        inputs = {}

        data = request.form
        for i in fields:
            if data.get(i):
                inputs[i] = data.get(i)
            else:
                print(f"❌ TIF Upload Failed [{upload_id}]: Missing field {i}")
                return jsonify({"status": False, "error": "Invalid params", "upload_id": upload_id}), 400

        tracker = UploadProgressTracker(upload_id, inputs['tif_file_name'], 0)  # Size unknown initially
        tracker.set_stage('validating', 'Checking Google Drive folder')

        try:
            print(f"🔍 Validating Google Drive URL: {inputs['g_url']}")
            
            # Try to access the folder
            files = gdown.download_folder(inputs['g_url'], skip_download=True, use_cookies=False)
            
            if not files:
                error_msg = f"""No files found in Google Drive folder. 
                
TROUBLESHOOTING:
1. Ensure the folder URL is correct
2. Set folder permission to 'Anyone with the link'
3. Check that the folder contains the TIF file: {inputs['tif_file_name']}

Folder URL: {inputs['g_url']}"""
                tracker.fail(error_msg)
                print(f"❌ TIF Upload Failed [{upload_id}]: {error_msg}")
                return jsonify({
                    "status": False, 
                    "error": "No files found in Google Drive folder", 
                    "upload_id": upload_id,
                    "troubleshooting": "Check folder permissions and URL"
                }), 400
            
        except Exception as folder_err:
            error_msg = f"""Cannot access Google Drive folder: {str(folder_err)}

COMMON SOLUTIONS:
1. Change folder permission to 'Anyone with the link'
2. Use folder URL instead of file URL
3. Ensure stable internet connection

URL provided: {inputs['g_url']}"""
            tracker.fail(error_msg)
            print(f"❌ TIF Upload Failed [{upload_id}]: {error_msg}")
            return jsonify({
                "status": False, 
                "error": "Cannot access Google Drive folder - check permissions", 
                "upload_id": upload_id,
                "details": str(folder_err)
            }), 400

        file_exist = False
        file_name = None
        file_id = None

        print(f"📂 Found {len(files)} file(s) in Google Drive folder")
        for file in files:
            file_id_value = file[0]
            file_name_found = file[1]
            print(f"📁 Found file: {file_name_found} vs {inputs['tif_file_name']}")
            if file_name_found == inputs['tif_file_name']:
                print("file ---", file, file_id_value)
                file_exist = True
                file_name = inputs['tif_file_name']
                file_id = file_id_value
                break

        if not file_exist:
            # List available files for user reference
            available_files = [file[1] for file in files]
            error_msg = f"""TIF file '{inputs['tif_file_name']}' not found in Google Drive folder.

Available files in folder:
{chr(10).join(f"- {f}" for f in available_files[:10])}
{f"... and {len(available_files)-10} more files" if len(available_files) > 10 else ""}

Please check:
1. File name is exactly correct (case-sensitive)
2. File exists in the specified folder
3. File has proper extension (.tif or .tiff)"""
            
            tracker.fail(error_msg)
            print(f"❌ TIF Upload Failed [{upload_id}]: {error_msg}")
            return jsonify({
                "status": False, 
                "message": f"File '{inputs['tif_file_name']}' not found", 
                "upload_id": upload_id,
                "available_files": available_files[:10],
                "total_files": len(available_files)
            }), 400

        tracker.set_stage('preparing_database', 'Setting up database records')

        file_path = f"audits/{inputs['plant_id']}/{inputs['audit_id']}/{inputs['audit_type']}/{file_name}"
        file_path = file_path
        new_task = {
            "tif_path": file_path,
            "status": "In Progress",
            "ortho_type": inputs['audit_type'],
            "created_at": datetime.utcnow(),
            "upload_id": upload_id
        }

        query = {
            "_id": ObjectId(inputs['audit_id']),
            "tif_files.tif_path": file_path
        }
        set_failed_status ={"$set": {"tif_files.$.status": "failed"  }}

        existing = audits_collection.find_one(query)

        if existing:
            audits_collection.update_one(query,
                {
                    "$set": {
                        "tif_files.$.status": 'In Progress',
                        "created_at": datetime.utcnow()
                    }
                }
            )
        else:
            audits_collection.update_one(
                {"_id": ObjectId(inputs['audit_id'])},
                {"$push": {"tif_files": new_task}}
            )

        tracker.set_stage('downloading', 'Downloading TIF file from Google Drive')

        # Save original TIF
        upload_path = os.path.join(
            app.config['UPLOAD_FOLDER'],
            str(inputs['plant_id']),
            'audit',
            str(inputs['audit_id'])
        )
        input_path = os.path.join(upload_path, file_name)
        os.makedirs(upload_path, exist_ok=True)

        try:
            url = f'https://drive.google.com/uc?id={file_id}'
            tracker.set_stage('downloading', f'Downloading from Google Drive: {file_name}')
            print(f"📥 Downloading from Google Drive: {url}")
            
            # Try multiple download methods for better compatibility
            download_success = False
            download_methods = [
                # Method 1: Standard gdown with fuzzy matching
                lambda: gdown.download(url, input_path, quiet=False, fuzzy=True, use_cookies=False),
                # Method 2: gdown with different parameters
                lambda: gdown.download(url, input_path, quiet=False, fuzzy=False, use_cookies=True),
                # Method 3: Direct file ID download
                lambda: gdown.download(f'https://drive.google.com/file/d/{file_id}/view', input_path, quiet=False, fuzzy=True),
                # Method 4: Alternative URL format
                lambda: gdown.download(f'https://drive.google.com/open?id={file_id}', input_path, quiet=False, fuzzy=True)
            ]
            
            for i, method in enumerate(download_methods, 1):
                try:
                    print(f"🔄 Trying download method {i}/4...")
                    tracker.set_stage('downloading', f'Attempting download method {i}/4')
                    
                    method()
                    
                    # Verify download success
                    if os.path.exists(input_path) and os.path.getsize(input_path) > 0:
                        actual_size = os.path.getsize(input_path)
                        tracker.total_size = actual_size
                        tracker.update_progress(actual_size, 'download_complete')
                        print(f"✅ Download Complete (Method {i}): {file_name} ({actual_size} bytes)")
                        download_success = True
                        break
                    else:
                        print(f"⚠️ Method {i} failed: File not found or empty")
                        continue
                        
                except Exception as method_err:
                    print(f"⚠️ Method {i} failed: {str(method_err)}")
                    continue
            
            if not download_success:
                # Provide detailed error message with instructions
                error_msg = f"""Failed to download file from Google Drive after trying all methods.

TROUBLESHOOTING STEPS:
1. Ensure the Google Drive file has 'Anyone with the link' permission
2. Right-click the file → Share → Change to 'Anyone with the link' → Copy link
3. Use a folder URL instead of direct file URL (recommended)
4. Check if the file exists and is accessible

File ID: {file_id}
Attempted URL: {url}

For better results, use a Google Drive folder URL containing the TIF file."""
                
                raise Exception(error_msg)
                
        except Exception as err:
            error_msg = f"Error downloading file from Google Drive: {str(err)}"
            tracker.fail(error_msg)
            print(f"❌ Download Failed [{upload_id}]: {error_msg}")
            app.logger.error(error_msg)
            audits_collection.update_one(query, set_failed_status)
            
            # Provide user-friendly error response
            return jsonify({
                "status": False, 
                "message": "Google Drive download failed - please check file permissions", 
                "error": "Make sure the file has 'Anyone with the link' permission and try again",
                "upload_id": upload_id,
                "troubleshooting": {
                    "step1": "Right-click the file in Google Drive",
                    "step2": "Click 'Share'", 
                    "step3": "Change permission to 'Anyone with the link'",
                    "step4": "Copy the sharing link and try again"
                }
            })

        tracker.set_stage('converting', 'Converting TIF to COG format for optimization')
        output_cog_path = os.path.join(upload_path, f"COG_{file_name}")
        
        print(f"🔄 Starting GDAL conversion: {input_path} -> {output_cog_path}")
        app.logger.info(f"GDAL conversion: {input_path} -> {output_cog_path}")
        
        # Convert to COG
        try:
            conversion_cmd = [
                "gdal_translate", "-of", "COG",
                "-co", "COMPRESS=DEFLATE",
                "-co", "BLOCKSIZE=512",
                "-co", "BIGTIFF=YES",
                input_path,
                output_cog_path
            ]
            print(f"🔧 GDAL Command: {' '.join(conversion_cmd)}")
            
            subprocess.check_call(conversion_cmd)
            
            # Verify COG creation
            if os.path.exists(output_cog_path):
                cog_size = os.path.getsize(output_cog_path)
                print(f"✅ COG Conversion Complete: {output_cog_path} ({cog_size} bytes)")
                tracker.set_stage('conversion_complete', f'COG conversion completed ({cog_size} bytes)')
            else:
                raise Exception("COG file was not created")
                
        except subprocess.CalledProcessError as e:
            error_msg = f"GDAL conversion failed: {str(e)}"
            tracker.fail(error_msg)
            print(f"❌ Conversion Failed [{upload_id}]: {error_msg}")
            app.logger.error(error_msg)
            audits_collection.update_one(query, set_failed_status)
            return jsonify({'error': 'GDAL conversion failed', 'details': str(e), 'upload_id': upload_id}), 500

        try:
            tracker.set_stage('uploading_s3', 'Uploading to AWS S3 cloud storage')
            s3_path = f"s3://{bucket_name}/{file_path}"
            print(f"☁️ Starting S3 upload: {output_cog_path} -> {s3_path}")
            print(f"🔑 AWS Config: Key={get_config('aws_access_key_id')[:10]}..., Region={get_config('region_name', 'ap-south-1')}")

            s3_upload_status = copy_to_s3(
                output_cog_path,
                s3_path,
                get_config('aws_access_key_id'),
                get_config('aws_secret_access_key')
            )
            
            if s3_upload_status == False:
                error_msg = "S3 upload failed - please check AWS credentials and permissions"
                tracker.fail(error_msg)
                print(f"❌ S3 Upload Failed [{upload_id}]: {error_msg}")
                audits_collection.update_one(query, set_failed_status)
                return jsonify({"status": False, "message": "S3 upload failed", "upload_id": upload_id})
            
            print(f"✅ S3 Upload Successful: {s3_path}")
            tracker.set_stage('s3_upload_complete', f'File uploaded to S3: {s3_path}')

            tracker.set_stage('cleaning_up', 'Cleaning up temporary files')
            print(f"🧹 Cleaning up temporary files: {upload_path}")
            
            try:
                shutil.rmtree(upload_path)
                print(f"✅ Cleanup Complete: {upload_path}")
            except OSError as e:
                print(f"⚠️ Cleanup Warning: {e.filename} - {e.strerror}")

            # Mark as completed in database
            audits_collection.update_one(query, {
                "$set": {
                    "tif_files.$.status": "Completed",
                    "tif_files.$.s3_path": s3_path,
                    "tif_files.$.completed_at": datetime.utcnow()
                }
            })
            
            tracker.complete(s3_path)
            print(f"🎉 TIF Upload Complete [{upload_id}]: {file_name} -> {s3_path}")
            
        except Exception as err:
            error_msg = f"S3 upload error: {str(err)}"
            tracker.fail(error_msg)
            print(f"❌ S3 Upload Error [{upload_id}]: {error_msg}")
            audits_collection.update_one(query, set_failed_status)
            return jsonify({"status": False, "message": "Upload processing failed", "upload_id": upload_id})

        return jsonify({"status": True, "message":"File uploaded completed", "upload_id": upload_id})
    
    except Exception as e:
        error_msg = f"TIF upload failed: {str(e)}"
        print(f"❌ TIF Upload Exception [{upload_id}]: {error_msg}")
        if upload_id in upload_status:
            upload_status[upload_id].fail(error_msg)
        return jsonify({"status": False, "message": error_msg, "upload_id": upload_id})

def upload_single_file(file_name, file_bytes):
    try:
        get_s3_resource().upload_fileobj(
            io.BytesIO(file_bytes),
            bucket_name,
            f'{file_name }',
            ExtraArgs={'ContentType': 'image/jpeg'}  # optionally detect mime type
        )
        return file_name
    except Exception as e:
        return f"Failed: {file_name} ({str(e)})"


# @app.route("/api/anomalies/<anomoly_id>/status", methods=['PUT'])
# def update_anomalies_status(anomoly_id):
#     print(request.form,anomoly_id)
#     return {}

@app.route('/audit/upload-images-from-zip-parallel', methods=['POST'])
def upload_images_parallel():
    file = request.files['zip_file']
    fields = ['plant_id', 'audit_id']
    print("coming request")
    inputs = {}
    data = request.form
    for i in fields:
        if data.get(i):
            inputs[i] = data.get(i)
        else:
            print("invalid params", i)
            return jsonify({"status": False, "error": "Invalid params"}), 400


    # return {"data":1}
    if 'zip_file' not in request.files:
        print("No zip file provided")

        return jsonify({'error': 'No zip file provided'}), 400

    zip_file = request.files['zip_file']
    if zip_file.filename == '':
        print("Errrointo file name empty file name")
        return jsonify({'error': 'Empty filename'}), 400

    zip_path = f"audits/{str(inputs['plant_id'])}/{str(inputs['audit_id'])}/zip_images/"
    uploaded_files = []
    audits_collection.update_one(
        {
            "_id": ObjectId(inputs['audit_id']),
        },
        {
            "$set": {"zip_upload_status":"In Progress", "zip_path":zip_path }
        }
    )
    print("updaing files s3")
    try:
        with zipfile.ZipFile(zip_file) as z:
            images = [
                (name, z.read(name)) for name in z.namelist()
                if name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'))
            ]
        with ThreadPoolExecutor(max_workers=50) as executor:  # adjust number of threads as needed
            futures = [executor.submit(upload_single_file, f"audits/{str(inputs['plant_id'])}/{str(inputs['audit_id'])}/zip_images/{name}", data) for name, data in images]
            for future in as_completed(futures):
                uploaded_files.append(future.result())

        audits_collection.update_one( { "_id": ObjectId(inputs['audit_id'])},
            {
                "$set": {"zip_upload_status": "Completed"}
            }
        )
        return jsonify({'message': 'Upload complete', 'files': uploaded_files})

    except Exception as err:
        print("Error into zip upload", err)
        audits_collection.update_one(
            {
                "_id": ObjectId(inputs['audit_id']),
            },
            {
                "$set": {"zip_upload_status": "Failed"}
            }
        )
        return jsonify({'error': 'Invalid zip file'}), 400

@app.route('/api/get_geojson/<audit_id>', methods=['POST'])
def get_geojson(audit_id):
    try:
        filter_options = dict(request.form)
        print("request data", filter_options, len(filter_options))
        audit = audits_collection.find_one({"_id":ObjectId(audit_id)}, {"anomalies":1})
        anomalies = json.loads(audit['anomalies'])['features'] if audit and audit.get('anomalies') else []

        if len(filter_options) >0:

            if filter_options.get('block') is not None and len(filter_options.get('block') ) >0:
                anomalies =[i for i in anomalies if i.get('properties', {}).get('Block') == filter_options['block'] ]

            if filter_options.get('an') is not None and len(filter_options.get('an')) >0:
                anomalies =[i for i in anomalies if i.get('properties', {}).get('Anomaly') == filter_options['an'] ]


        return jsonify(anomalies)
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500




def up_data():


    with open('/Users/dharmendrabajiya/Downloads/layout.geojson') as f:

        geojson_data = json.load(f)

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
        audit_data = {}
        audit_data['anomalies'] = json.dumps(default_data)
        result = audits_collection.update_one({'_id':ObjectId('6846edcd862975f9b5c47ae0')},
        {"$set": audit_data})
# up_data()

@app.route("/test_sample")
def get_one():
    return render_template("check.html")


def serialize_client(client):
    return {
        '_id': str(client['_id']),  # Convert ObjectId to string
        'login_id': client['email'],
        'role': client['role'],
        'status':client['status'],
        'created_at': client['created_at'].strftime('%Y-%m-%d %H:%M:%S')  # Format datetime
    }
@app.route("/api/v1.0/main", methods=['GET'])
@login_required
def get_admin():
    client_list = list(users_collection.find({"role":"client"}, {"password": 0}))
    client_list = [serialize_client(client) for client in client_list]
    return render_template('admin.html',client_list=client_list)


# @app.route("/assign-plant", methods=['GET','POST'])
# @login_required
# def assign_client():
#     print(request)
#     if request.method == 'POST':
#         print("form coming", request.json)
#         js_data = request.json
#         selected_plants = js_data['selectedPlants'][0]
#         client_list = list(users_collection.find_one({"_id":ObjectId(js_data['clientId'])}, {"password": 0}))
#         print(client_list)
#         return {"s":1}
#     else:
#         args = request.args
#         fields = ['client_id']
#         for field in fields:
#             if args.get(field):
#                 pass
#             else:
#                 return redirect('/api/v1.0/main')
#         client_id = args.get('client_id')
#         client_list = list(users_collection.find({"_id":ObjectId(client_id)}, {"password": 0}))
#         print(client_list)
#         plant_list = list(plants_collection.find({}, {"_id": 1, "name":1}))
#         return render_template('assign_client_plant.html',client_list=client_list,plant_list=plant_list)

@app.route("/api/v1.0/user_status_update", methods=['POST'])
@login_required
def user_status_update():
    data = request.get_json()
    if session.get('user_role') != 'admin':
        return jsonify({'success': False, 'message': 'Invalid Access'}), 400

    clientId = data.get('clientId')
    password = data.get('password')
    status = data.get('status')
    if clientId is None :
            return jsonify({'success': False, 'message': 'Invalid User'}), 400

    get_user = users_collection.find_one({'_id': ObjectId(clientId)})
    if get_user is None:
        return jsonify({'success': False, 'message': 'Invalid user'}), 400

    if str(get_user['_id']) != str(clientId) or get_user.get('role') == 'admin':
        return jsonify({'success': False, 'message': 'Invalid User updating'}), 400


    if clientId is not None and password is not None and len(password) > 5:
        users_collection.update_one({"_id":ObjectId(clientId)}, {"$set":{"password": str(password),"updated_at": datetime.utcnow()}})
        return jsonify({'success': False, 'message': 'User password updated successfully'}), 200

    if clientId is not None and (status==0 or status ==1) and password is None:
        users_collection.update_one({"_id":ObjectId(clientId)}, {"$set":{"status": int(status), "updated_at": datetime.utcnow()} })
        return jsonify({'success': False, 'message': 'User status updated successfully'}), 200


    return jsonify({'success': False, 'message': 'Something Went Wrong'}), 400


# @app.route('/audi_tif/check_data', methods=['POST'])
# def upload():

@app.route('/audi_tif/new_upload', methods=['POST','GET'])
def upload_te():
    if request.method =='GET':
        return render_template("test_upload.html")
    try:
        # Get form fields
        audit_type = request.form.get('audit_type')
        plant_id = request.form.get('plant_id')
        audit_id = request.form.get('audit_id')

        # Get the uploaded file
        file = request.files.get('tif_file_name')
        print("----tif_file",file)
        if not file:
            return "No file part", 400

        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # Save the file manually in chunks
        # file = request.files['big_file']
        # filename = file.filename
        # file_path = os.path.join(file_path, filename)
        CHUNK_SIZE = 400 * 1024 * 1024  # 400 MB

        with open(file_path, 'wb') as f:
            while True:
                chunk = file.stream.read(CHUNK_SIZE)  # 16MB chunks
                if not chunk:
                    break
                f.write(chunk)

        print("Saved file to:", file_path)
        print("Audit Type:", audit_type)
        print("Plant ID:", plant_id)
        print("Audit ID:", audit_id)
        print("----file uploaded successfully")

        return f"File uploaded successfully: {file}", 200

    except Exception as err:
        print("---err", err)
        return render_template("test_upload.html")


# Health check endpoint for monitoring and deployment
@app.route('/health')
def health_check():
    """Health check endpoint for load balancers and monitoring"""
    try:
        # Test database connection
        mongo.db.command('ping')
        return {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'connected',
            'upload_capacity': '50GB',
            'version': '1.0.0'
        }, 200
    except Exception as e:
        return {
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }, 503

# Import and register Render-optimized upload endpoints
try:
    from render_upload_endpoints import register_render_endpoints
    register_render_endpoints(app, data_uploads_collection, get_s3_resource)
    print("✅ Render-optimized upload endpoints loaded successfully")
except ImportError as e:
    print(f"⚠️ Render upload endpoints not loaded: {e}")
except Exception as e:
    print(f"⚠️ Error loading render endpoints: {e}")

# Add upload progress tracking endpoints
@app.route('/api/upload/progress/<upload_id>', methods=['GET'])
def get_upload_progress(upload_id):
    """Get upload progress status"""
    try:
        if upload_id in upload_status:
            tracker = upload_status[upload_id]
            return jsonify({
                'success': True,
                'status': tracker.get_status()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Upload ID not found'
            }), 404
    except Exception as e:
        print(f"❌ Error getting upload progress: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/upload/status', methods=['GET'])
def get_all_upload_status():
    """Get status of all active uploads"""
    try:
        active_uploads = {}
        for upload_id, tracker in upload_status.items():
            active_uploads[upload_id] = tracker.get_status()
        
        return jsonify({
            'success': True,
            'active_uploads': active_uploads,
            'total_active': len(active_uploads)
        })
    except Exception as e:
        print(f"❌ Error getting upload status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Upload progress test page
@app.route('/upload-progress-test')
def upload_progress_test():
    """Test page for upload progress tracking"""
    return render_template('upload_with_progress.html')

# Google Drive upload page
@app.route('/google-drive-upload')
def google_drive_upload():
    """Google Drive upload page with real-time progress"""
    return render_template('google_drive_upload.html')

# Upload progress endpoint (simple version for compatibility)
@app.route('/upload_progress/<upload_id>', methods=['GET'])
def upload_progress(upload_id):
    """Get upload progress status (simple endpoint for compatibility)"""
    try:
        if upload_id in upload_status:
            tracker = upload_status[upload_id]
            status_data = tracker.get_status()
            return jsonify(status_data)
        else:
            return jsonify({
                'status': 'not_found',
                'error': 'Upload ID not found'
            }), 404
    except Exception as e:
        print(f"❌ Error getting upload progress: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/plant/<plant_id>/overview')
@login_required
def plant_overview(plant_id):
    """Plant overview page with analytics and charts"""
    print(f"🏭 Plant overview requested for plant: {plant_id}")
    
    plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
    if not plant:
        print(f"❌ Plant not found: {plant_id}")
        flash('Plant not found', 'error')
        return redirect(url_for('homepage'))
    
    print(f"✅ Plant found: {plant.get('name', 'Unknown')} (ID: {plant_id})")
    
    # Make plant serializable
    plant = make_serializable(plant)
    
    # Get the latest audit for this plant to fetch real data
    audits = list(audits_collection.find({'plant_id': str(plant_id)}).sort('_id', -1).limit(1))
    print(f"📄 Found {len(audits)} audits for plant {plant_id}")
    
    # Initialize default data
    anomaly_data = {
        'labels': [],
        'counts': [],
        'colors': []
    }
    
    bar_chart_data = {
        'labels': [],
        'datasets': []
    }
    
    analytics = {
        'power_loss': '0',
        'revenue_loss': '0'
    }
    
    progress_data = {
        'pending': 0,
        'resolved': 0,
        'not_found': 0,
        'high': 0,
        'medium': 0,
        'low': 0
    }
    
    # If audit data exists, process it
    if audits and audits[0].get('anomalies'):
        try:
            audit_id = str(audits[0]['_id'])
            print(f"🏭 Processing plant {plant_id} overview with audit {audit_id}")
            
            anomalies = json.loads(audits[0]['anomalies'])['features']
            print(f"📊 Found {len(anomalies)} anomalies to process for overview charts")
            
            # Process anomalies for charts
            anomaly_counts = {}
            blocks_data = {}
            
            # Define color mapping for anomaly types
            color_map = {
                'Bypass Diode': '#9C27B0',
                'Multi Cell Hotspot': '#FFA500', 
                'Cell Hotspot': '#FF0000',
                'Partial String Offline': '#FF66C4',
                'Vegetation': '#2E7D32',
                'Physical Damage': '#C2185B',
                'Module Power Mismatch': '#65E667',
                'Shading': '#E77148',
                'Short Circuit': '#506E9A',
                'String Offline': '#FF1A94',
                'Module Offline': '#545454',
                'Junction Box': '#BFC494',
                'Module Missing': '#5CE1E6',
                'Other': '#8C52FF',
                'Cell': '#FF0000',
                'Multi Cell': '#FFA500'
            }
            
            for anomaly in anomalies:
                properties = anomaly['properties']
                
                # Debug: Print available properties to understand data structure
                print(f"🔍 Available properties: {list(properties.keys())}")
                
                # Use the correct property name based on your existing code
                anomaly_type = properties.get('Anomaly', 'Unknown')  # Changed from 'Anomaly_type' to 'Anomaly'
                block_value = properties.get('Block', 'Unknown')
                
                print(f"   Anomaly type: {anomaly_type}, Block: {block_value}")
                
                # Count anomaly types
                if anomaly_type in anomaly_counts:
                    anomaly_counts[anomaly_type] += 1
                else:
                    anomaly_counts[anomaly_type] = 1
                
                # Group by blocks for bar chart
                if block_value != 'Unknown':
                    if block_value not in blocks_data:
                        blocks_data[block_value] = {}
                    
                    if anomaly_type in blocks_data[block_value]:
                        blocks_data[block_value][anomaly_type] += 1
                    else:
                        blocks_data[block_value][anomaly_type] = 1
            
            print(f"📈 Anomaly type distribution for overview:")
            for anomaly_type, count in anomaly_counts.items():
                print(f"   {anomaly_type}: {count}")
            
            print(f"🏗️ Block distribution for overview:")
            for block, type_data in blocks_data.items():
                total_in_block = sum(type_data.values())
                print(f"   Block {block}: {total_in_block} anomalies")
            
            # Prepare pie chart data
            anomaly_data['labels'] = list(anomaly_counts.keys())
            anomaly_data['counts'] = list(anomaly_counts.values())
            anomaly_data['colors'] = [color_map.get(label, '#888888') for label in anomaly_data['labels']]
            
            # Prepare bar chart data
            if blocks_data:
                sorted_blocks = sorted(blocks_data.keys())
                bar_chart_data['labels'] = sorted_blocks
                
                # Create datasets for each anomaly type
                datasets = []
                for anomaly_type in anomaly_counts.keys():
                    dataset_data = []
                    for block in sorted_blocks:
                        count = blocks_data[block].get(anomaly_type, 0)
                        dataset_data.append(count)
                    
                    datasets.append({
                        'label': anomaly_type,
                        'data': dataset_data,
                        'backgroundColor': color_map.get(anomaly_type, '#888888')
                    })
                
                bar_chart_data['datasets'] = datasets
                print(f"📊 Created {len(datasets)} datasets for {len(sorted_blocks)} blocks")
            
            # Calculate some basic analytics
            total_anomalies = sum(anomaly_counts.values())
            # Estimate power loss (placeholder calculation)
            analytics['power_loss'] = str(total_anomalies * 2)  # 2kW per anomaly estimate
            analytics['revenue_loss'] = str(total_anomalies * 1500)  # Rs 1500 per anomaly estimate
            
            print(f"💰 Calculated analytics:")
            print(f"   Power loss estimate: {analytics['power_loss']} kW")
            print(f"   Revenue loss estimate: Rs {analytics['revenue_loss']}")
            
        except Exception as e:
            print(f"❌ Error processing anomaly data for plant {plant_id}: {e}")
    else:
        print(f"⚠️ No audit data found for plant {plant_id} - using empty data")
    
    print(f"🎯 Rendering plant overview template with:")
    print(f"   Analytics: {analytics}")
    print(f"   Anomaly data labels: {len(anomaly_data['labels'])} types")
    print(f"   Bar chart labels: {len(bar_chart_data['labels'])} blocks")
    
    return render_template('plant_overview.html', 
                         plant=plant, 
                         analytics=analytics,
                         progress_data=progress_data,
                         anomaly_data=anomaly_data,
                         bar_chart_data=bar_chart_data)

@app.route('/plant/<plant_id>/site-details')
@login_required
def plant_site_details(plant_id):
    """Plant site details page with location and technical specifications"""
    plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
    if not plant:
        flash('Plant not found', 'error')
        return redirect(url_for('homepage'))
    
    # Make plant serializable
    plant = make_serializable(plant)
    
    # Check user role for admin/client access
    get_session_user = session.get('user_role')
    role = 1 if get_session_user == 'admin' else 0
    
    return render_template('plant_site_details.html', plant=plant, check_mate=role)

@app.route('/api/plants/<plant_id>/image', methods=['POST'])
@login_required
def update_plant_image_by_id(plant_id):
    """Update plant image by plant ID"""
    try:
        plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
        if not plant:
            return jsonify({'success': False, 'message': 'Plant not found'})
        
        if 'image' not in request.files:
            return jsonify({'success': False, 'message': 'No image file provided'})
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No image file selected'})
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Add timestamp to filename to make it unique
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            
            # Save file to uploads directory
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Update plant record with new image path
            photo_url = f"/uploads/{filename}"
            result = plants_collection.update_one(
                {'_id': ObjectId(plant_id)},
                {'$set': {'image': photo_url, 'updated_at': datetime.utcnow()}}
            )
            
            if result.modified_count > 0:
                return jsonify({'success': True, 'message': 'Image updated successfully', 'image_url': photo_url})
            else:
                return jsonify({'success': False, 'message': 'Failed to update image'})
        else:
            return jsonify({'success': False, 'message': 'Invalid file type'})
            
    except Exception as e:
        app.logger.error(f"Error updating plant image: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@app.route('/api/plants/<plant_id>/additional-image', methods=['POST'])
@login_required
def update_plant_additional_image_by_id(plant_id):
    """Update plant additional image by plant ID"""
    try:
        plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
        if not plant:
            return jsonify({'success': False, 'message': 'Plant not found'})
        
        if 'additional_image' not in request.files:
            return jsonify({'success': False, 'message': 'No additional image file provided'})
        
        file = request.files['additional_image']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No additional image file selected'})
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Add timestamp to filename to make it unique
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"additional_{timestamp}_{filename}"
            
            # Save file to uploads directory
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Update plant record with new additional image path
            photo_url = f"/uploads/{filename}"
            result = plants_collection.update_one(
                {'_id': ObjectId(plant_id)},
                {'$set': {'additional_image': photo_url, 'updated_at': datetime.utcnow()}}
            )
            
            if result.modified_count > 0:
                return jsonify({'success': True, 'message': 'Additional image updated successfully', 'image_url': photo_url})
            else:
                return jsonify({'success': False, 'message': 'Failed to update additional image'})
        else:
            return jsonify({'success': False, 'message': 'Invalid file type'})
            
    except Exception as e:
        app.logger.error(f"Error updating plant additional image: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@app.route('/api/plants/update-image', methods=['POST'])
@login_required
def update_plant_image():
    """Update plant image"""
    try:
        plant_id = request.form.get('plant_id')
        if not plant_id:
            return jsonify({'success': False, 'message': 'Plant ID is required'})
        
        plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
        if not plant:
            return jsonify({'success': False, 'message': 'Plant not found'})
        
        if 'plant_photo' not in request.files:
            return jsonify({'success': False, 'message': 'No image file provided'})
        
        file = request.files['plant_photo']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No image file selected'})
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Add timestamp to filename to make it unique
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            
            # Save file to uploads directory
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Update plant record with new image path
            photo_url = f"/uploads/{filename}"
            result = plants_collection.update_one(
                {'_id': ObjectId(plant_id)},
                {'$set': {'plant_photo': photo_url, 'updated_at': datetime.utcnow()}}
            )
            
            if result.modified_count > 0:
                return jsonify({'success': True, 'message': 'Image updated successfully'})
            else:
                return jsonify({'success': False, 'message': 'Failed to update image'})
        else:
            return jsonify({'success': False, 'message': 'Invalid file type'})
            
    except Exception as e:
        app.logger.error(f"Error updating plant image: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while updating the image'})


@app.route('/api/plant/<plant_id>/severity-data', methods=['GET', 'POST'])
@login_required
def plant_severity_data(plant_id):
    """API endpoint for managing severity data uploaded by admin"""
    plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
    if not plant:
        return jsonify({'success': False, 'message': 'Plant not found'}), 404
    
    # Handle severity data upload (POST)
    if request.method == 'POST':
        # Check if user is admin
        if session.get('user_role') != 'admin':
            return jsonify({'success': False, 'message': 'Only administrators can upload severity data'}), 403
        
        try:
            # Get severity data from request
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': 'No data provided'}), 400
            
            # Validate severity data structure
            if 'high' not in data or 'medium' not in data or 'low' not in data:
                return jsonify({'success': False, 'message': 'Invalid severity data format'}), 400
            
            # Store severity data in the plants collection
            plants_collection.update_one(
                {'_id': ObjectId(plant_id)},
                {'$set': {'severity_data': data}}
            )
            
            return jsonify({'success': True, 'message': 'Severity data uploaded successfully'})
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error uploading severity data: {str(e)}'}), 500
    
    # Handle severity data retrieval (GET)
    else:
        # Try to get severity data from the plant document
        severity_data = plant.get('severity_data')
        if severity_data:
            return jsonify({'success': True, 'severityData': severity_data})
        else:
            return jsonify({'success': False, 'message': 'No severity data found for this plant'}), 404


@app.route('/api/audit/<audit_id>/anomalies/by-block', methods=['GET'])
@login_required
def audit_anomalies_by_block(audit_id):
    """Get anomalies grouped by block for a specific audit"""
    try:
        print(f"🔍 Fetching anomalies by block for audit: {audit_id}")
        audit = audits_collection.find_one({'_id': ObjectId(audit_id)})
        if not audit or not audit.get('anomalies'):
            print(f"❌ No anomalies data found for audit: {audit_id}")
            return jsonify({'success': False, 'message': 'No anomalies data found'}), 404

        anomalies = json.loads(audit['anomalies'])['features']
        print(f"📊 Found {len(anomalies)} total anomalies in audit {audit_id}")
        
        # Group anomalies by block
        blocks_data = {}
        for anomaly in anomalies:
            block_value = anomaly['properties'].get('Block')
            if block_value:
                if block_value not in blocks_data:
                    blocks_data[block_value] = []
                blocks_data[block_value].append(anomaly)
        
        print(f"🏗️ Grouped anomalies into {len(blocks_data)} blocks:")
        for block, anomaly_list in blocks_data.items():
            print(f"   Block {block}: {len(anomaly_list)} anomalies")
        
        return jsonify({
            'success': True,
            'blocks': blocks_data
        })
    except Exception as e:
        print(f"❌ Error in audit_anomalies_by_block for audit {audit_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Error fetching anomalies by block: {str(e)}'}), 500


@app.route('/api/plant/<plant_id>/anomalies/by-block', methods=['GET'])
@login_required
def plant_anomalies_by_block(plant_id):
    """Get anomalies grouped by block for the latest audit of a plant"""
    try:
        print(f"🌱 Fetching anomalies by block for plant: {plant_id}")
        # Get the latest audit for this plant
        audits = list(audits_collection.find({'plant_id': str(plant_id)}).sort('_id', -1).limit(1))
        
        if not audits or not audits[0].get('anomalies'):
            print(f"❌ No anomalies data found for plant: {plant_id}")
            return jsonify({'success': False, 'message': 'No anomalies data found for this plant'}), 404
        
        latest_audit = audits[0]
        audit_id = str(latest_audit['_id'])
        print(f"📄 Using latest audit: {audit_id}")
        
        anomalies = json.loads(latest_audit['anomalies'])['features']
        print(f"📊 Found {len(anomalies)} total anomalies in latest audit")
        
        # Group anomalies by block and count by type
        blocks_data = {}
        anomaly_type_counts = {}
        
        for anomaly in anomalies:
            properties = anomaly['properties']
            block_value = properties.get('Block')
            anomaly_type = properties.get('Anomaly', 'Unknown')  # Changed from 'Anomaly_type' to 'Anomaly'
            
            print(f"   Processing anomaly - Type: {anomaly_type}, Block: {block_value}")
            
            if block_value:
                if block_value not in blocks_data:
                    blocks_data[block_value] = {}
                
                if anomaly_type not in blocks_data[block_value]:
                    blocks_data[block_value][anomaly_type] = 0
                blocks_data[block_value][anomaly_type] += 1
                
                # Overall count
                if anomaly_type not in anomaly_type_counts:
                    anomaly_type_counts[anomaly_type] = 0
                anomaly_type_counts[anomaly_type] += 1
        
        print(f"🏗️ Grouped anomalies into {len(blocks_data)} blocks:")
        for block, type_counts in blocks_data.items():
            total_in_block = sum(type_counts.values())
            print(f"   Block {block}: {total_in_block} anomalies")
            for anomaly_type, count in type_counts.items():
                print(f"     - {anomaly_type}: {count}")
        
        print(f"📈 Overall anomaly type distribution:")
        for anomaly_type, count in anomaly_type_counts.items():
            print(f"   {anomaly_type}: {count}")
        
        return jsonify({
            'success': True,
            'blocks': blocks_data,
            'anomaly_type_counts': anomaly_type_counts,
            'audit_id': str(latest_audit['_id'])
        })
    except Exception as e:
        print(f"❌ Error in plant_anomalies_by_block for plant {plant_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Error fetching plant anomalies by block: {str(e)}'}), 500


@app.route('/api/update_anomaly_details', methods=['POST'])
@login_required
def update_anomaly_details():
    """Update anomaly details with verification information"""
    try:
        # Get form data
        audit_id = request.form.get('audit_id')
        anomaly_id = request.form.get('anomaly_id')
        issue_type = request.form.get('issueType')
        status = request.form.get('status')
        voc_module = request.form.get('vocModule')
        module_serial = request.form.get('moduleSerial')
        verified_at = request.form.get('verifiedAt')
        verified_by = request.form.get('verifiedBy')
        action = request.form.get('action')
        remarks = request.form.get('remarks')
        
        # Handle file upload
        attachment = request.files.get('attachment')
        attachment_path = None
        
        if attachment and attachment.filename:
            filename = secure_filename(attachment.filename)
            # Create uploads directory if it doesn't exist
            upload_dir = os.path.join('uploads_data', 'anomaly_updates')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            attachment_path = os.path.join(upload_dir, f"{timestamp}_{filename}")
            attachment.save(attachment_path)
        
        # Create update record
        update_data = {
            'audit_id': audit_id,
            'anomaly_id': anomaly_id,
            'issue_type': issue_type,
            'status': status,
            'voc_module': voc_module,
            'module_serial': module_serial,
            'verified_at': verified_at,
            'verified_by': verified_by,
            'action': action,
            'remarks': remarks,
            'attachment_path': attachment_path,
            'created_at': datetime.now(),
            'updated_at': datetime.now(),
            'created_by': session['user_id']
        }
        
        # Check if update already exists and update it, otherwise create new
        existing_update = anomaly_updates_collection.find_one({
            'audit_id': audit_id,
            'anomaly_id': anomaly_id
        })
        
        if existing_update:
            # Update existing record
            update_data['updated_at'] = datetime.now()
            result = anomaly_updates_collection.update_one(
                {'audit_id': audit_id, 'anomaly_id': anomaly_id},
                {'$set': update_data}
            )
            app.logger.info(f"Updated anomaly details for audit {audit_id}, anomaly {anomaly_id}")
        else:
            # Create new record
            result = anomaly_updates_collection.insert_one(update_data)
            app.logger.info(f"Created new anomaly update for audit {audit_id}, anomaly {anomaly_id}")
        
        return jsonify({
            'success': True,
            'message': 'Anomaly details updated successfully',
            'data': update_data
        })
        
    except Exception as e:
        app.logger.error(f"Error updating anomaly details: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error updating anomaly details: {str(e)}'
        }), 500


@app.route('/api/generate_anomaly_pdf', methods=['POST'])
@login_required
def generate_anomaly_pdf():
    """Generate comprehensive PDF report for anomaly"""
    if not PDF_ENABLED:
        return jsonify({
            'success': False,
            'message': 'PDF generation is not available. Required libraries not installed.'
        }), 500
    
    try:
        data = request.get_json()
        image_path = data.get('image_path')
        image_name = data.get('image_name')
        properties = data.get('properties')
        audit_id = data.get('audit_id')
        
        # Create PDF buffer
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1*inch)
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            textColor=colors.HexColor('#2e7d32')
        )
        
        normal_style = styles['Normal']
        
        # Build PDF content
        story = []
        
        # Title
        story.append(Paragraph("Thermal Anomaly Report", title_style))
        story.append(Spacer(1, 20))
        
        # Anomaly Information
        story.append(Paragraph("Anomaly Information", heading_style))
        
        # Basic details table
        basic_data = [
            ['Anomaly ID:', properties.get('ID', 'N/A')],
            ['Anomaly Type:', properties.get('Anomaly', 'N/A')],
            ['Severity:', properties.get('Severity', 'N/A')],
            ['Date:', properties.get('Date', 'N/A')],
            ['Time:', properties.get('Time', 'N/A')],
        ]
        
        basic_table = Table(basic_data, colWidths=[2*inch, 3*inch])
        basic_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(basic_table)
        story.append(Spacer(1, 20))
        
        # Technical Details
        story.append(Paragraph("Technical Details", heading_style))
        
        tech_data = [
            ['ΔT (T2 - T1):', properties.get('Hotspot', 'N/A')],
            ['Irradiance:', properties.get('Irradian', 'N/A')],
            ['Module Make:', properties.get('make', 'N/A')],
            ['Module Watt:', properties.get('Wat', 'N/A')],
            ['Barcode Serial:', properties.get('barcode', 'N/A')],
        ]
        
        tech_table = Table(tech_data, colWidths=[2*inch, 3*inch])
        tech_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(tech_table)
        story.append(Spacer(1, 20))
        
        # Location Details
        story.append(Paragraph("Location Details", heading_style))
        
        location_data = [
            ['Latitude:', properties.get('Latitude', 'N/A')],
            ['Longitude:', properties.get('Longitude', 'N/A')],
            ['Block:', properties.get('Block', 'N/A')],
            ['String:', properties.get('String', 'N/A')],
            ['Module:', properties.get('panel', 'N/A')],
        ]
        
        location_table = Table(location_data, colWidths=[2*inch, 3*inch])
        location_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(location_table)
        story.append(Spacer(1, 30))
        
        # Thermal Image
        story.append(Paragraph("Thermal Image", heading_style))
        
        # Try to add the image
        try:
            if image_path.startswith('http'):
                # Download image from URL
                response = requests.get(image_path)
                if response.status_code == 200:
                    img_buffer = io.BytesIO(response.content)
                    img = Image(img_buffer, width=4*inch, height=3*inch)
                    story.append(img)
                else:
                    story.append(Paragraph(f"Error loading image from URL: {image_path}", normal_style))
            else:
                # Local file path
                if os.path.exists(image_path):
                    img = Image(image_path, width=4*inch, height=3*inch)
                    story.append(img)
                else:
                    story.append(Paragraph(f"Image not found: {image_path}", normal_style))
        except Exception as img_error:
            story.append(Paragraph(f"Error loading image: {str(img_error)}", normal_style))
        
        story.append(Spacer(1, 20))
        
        # Get update details if available
        update_details = anomaly_updates_collection.find_one({
            'audit_id': audit_id,
            'anomaly_id': image_name
        })
        
        if update_details:
            story.append(Paragraph("Update Details", heading_style))
            
            update_data = [
                ['Issue Type:', update_details.get('issue_type', 'N/A')],
                ['Status:', update_details.get('status', 'N/A')],
                ['Voc of Module:', update_details.get('voc_module', 'N/A')],
                ['Module Serial:', update_details.get('module_serial', 'N/A')],
                ['Verified At:', update_details.get('verified_at', 'N/A')],
                ['Verified By:', update_details.get('verified_by', 'N/A')],
                ['Action Taken:', update_details.get('action', 'N/A')],
            ]
            
            if update_details.get('remarks'):
                update_data.append(['Remarks:', update_details.get('remarks', 'N/A')])
            
            update_table = Table(update_data, colWidths=[2*inch, 3*inch])
            update_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            story.append(update_table)
        
        # Footer
        story.append(Spacer(1, 30))
        footer_text = f"Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        story.append(Paragraph(footer_text, normal_style))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'anomaly_report_{image_name}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        app.logger.error(f"Error generating PDF: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error generating PDF: {str(e)}'
        }), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')