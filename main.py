"""
  Developer: Dharmendra Bajiya
  Email: bajiya2024@gmail.com
  Contact: +91-9785540104
  Date: June 2025
  Description: Sylo complete
"""
import shutil
import zipfile

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
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
    return render_template('homepage_1.html', plants=plants, check_mate=role)


@app.route('/api/plants', methods=['GET', 'POST'])
@login_required
def plants_api():
    if request.method == 'POST':
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

        # Create progress tracker for Google Drive download
        tracker = UploadProgressTracker(upload_id, inputs['tif_file_name'], 0)  # Size unknown initially
        tracker.set_stage('validating', 'Checking Google Drive folder')

        files = gdown.download_folder(inputs['g_url'], skip_download=True, use_cookies=False)
        file_exist = False
        file_name = None
        file_id = None

        for file in files:
            file_id_value = file[0]
            file_name = file[1]
            print(f"📁 Found file: {file_name} vs {inputs['tif_file_name']}")
            if file_name == inputs['tif_file_name']:
                print("file ---", file,file_id_value)
                file_exist=True
                file_name = inputs['tif_file_name']
                file_id = file_id_value
                break

        if not file_exist:
            error_msg = f"TIF file '{inputs['tif_file_name']}' not found in Google Drive"
            tracker.fail(error_msg)
            print(f"❌ TIF Upload Failed [{upload_id}]: {error_msg}")
            return jsonify({"status": False, "message":"Invalid File Name", "upload_id": upload_id}), 400

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
            tracker.set_stage('downloading', f'Downloading from: {url}')
            gdown.download(url, input_path, quiet=False,fuzzy=True, use_cookies=False)
            
            # Get actual file size after download
            if os.path.exists(input_path):
                actual_size = os.path.getsize(input_path)
                tracker.total_size = actual_size
                tracker.update_progress(actual_size, 'download_complete')
                
        except Exception as err:
            error_msg = f"Error downloading file from Google Drive: {str(err)}"
            tracker.fail(error_msg)
            print(f"❌ Download Failed [{upload_id}]: {error_msg}")
            app.logger.error(error_msg)
            audits_collection.update_one(query, set_failed_status)
            return jsonify({"status": False, "message":"Failed to download file", "upload_id": upload_id})

        tracker.set_stage('converting', 'Converting TIF to COG format')
        output_cog_path = os.path.join(upload_path, f"COG_{file_name}")

        app.logger.info("output_cog_path", output_cog_path)
        # Convert to COG
        try:
            subprocess.check_call([
                "gdal_translate", "-of", "COG",
                "-co", "COMPRESS=DEFLATE",
                "-co", "BLOCKSIZE=512",
                # "-co", "OVERVIEWS=AUTO",
                "-co", "BIGTIFF=YES",
                input_path,
                output_cog_path
            ])
            tracker.set_stage('conversion_complete', 'COG conversion completed')
        except subprocess.CalledProcessError as e:
            error_msg = f"GDAL conversion failed: {str(e)}"
            tracker.fail(error_msg)
            print(f"❌ Conversion Failed [{upload_id}]: {error_msg}")
            app.logger.error(error_msg)
            audits_collection.update_one(query, set_failed_status)
            return jsonify({'error': 'GDAL conversion failed', 'details': str(e), 'upload_id': upload_id}), 500

        try:
            tracker.set_stage('uploading_s3', 'Uploading to AWS S3')
            print("---output_cog_path","output_cog_path",output_cog_path, f"s3://{bucket_name}/{file_path}",get_config('aws_access_key_id'),get_config('aws_secret_access_key'))

            s3_upload_status = copy_to_s3(output_cog_path,
        f"s3://{bucket_name}/{file_path}",get_config('aws_access_key_id'),get_config('aws_secret_access_key'))
            if s3_upload_status == False:
                error_msg = "S3 upload failed"
                tracker.fail(error_msg)
                print(f"❌ S3 Upload Failed [{upload_id}]: {error_msg}")
                audits_collection.update_one(query,set_failed_status )
                return jsonify({"status": False, "message": "S3 upload failed", "upload_id": upload_id})

            tracker.set_stage('cleaning_up', 'Cleaning up temporary files')
            try:
                shutil.rmtree(upload_path)
            except OSError as e:
                print("Error: %s - %s." % (e.filename, e.strerror))

            # Mark as completed
            audits_collection.update_one(query,
                {
                    "$set": {
                        "tif_files.$.status": "Completed"  # $ points to the matched array element
                    }
                }
            )
            
            tracker.complete(f"s3://{bucket_name}/{file_path}")
            print(f"✅ TIF Upload Successful [{upload_id}]: {file_name}")
            
        except Exception as err:
            error_msg = f"S3 upload error: {str(err)}"
            tracker.fail(error_msg)
            print(f"❌ S3 Upload Error [{upload_id}]: {error_msg}")
            audits_collection.update_one(query,set_failed_status)
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

if __name__ == '__main__':
    app.run(port=3333)
    # app.run(debug=False, port=1212, host='0.0.0.0',use_reloader=False,
    #     use_debugger=False,
    #     use_evalex=False,
    #     threaded=True)