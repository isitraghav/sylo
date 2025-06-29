import shutil
import zipfile
import time
import uuid

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

# Global upload progress tracking dictionary
upload_progress = {}

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

def upload_to_s3(file_path, s3_key):
    """Upload a file to S3 and return the URL"""
    try:
        s3_client = get_s3_resource()
        
        # Upload file to S3
        s3_client.upload_file(file_path, bucket_name, s3_key)
        
        # Generate the S3 URL
        s3_url = f"{s3_prefix}/{s3_key}"
        return s3_url
        
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        raise


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
    """Plant detail page with overview, site details, and report tabs"""
    try:
        plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
        if not plant:
            flash('Plant not found', 'error')
            return redirect(url_for('homepage'))
        
        # Get audits for this plant to check if anomalies map is available
        audits = list(audits_collection.find({'plant_id': str(plant['_id'])}).sort('_id', -1))
        
        plant = make_serializable(plant)
        
        return render_template('plant_detail_clean.html', plant=plant, audits=audits)
    except Exception as e:
        print(f"Error in plant_detail: {e}")
        flash('Error loading plant details', 'error')
        return redirect(url_for('homepage'))

@app.route('/plant/<plant_id>/overview')
@login_required
def plant_overview(plant_id):
    try:
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
        
        anomaly_data = {
            'high': progress_data['high'],
            'medium': progress_data['medium'],
            'low': progress_data['low'],
            'resolved': 10
        }
        
        plant = make_serializable(plant)
        
        return render_template('plant_overview.html', 
                             plant=plant, 
                             analytics=analytics,
                             progress_data=progress_data,
                             anomaly_data=anomaly_data)
    except Exception as e:
        print(f"Error in plant_overview: {e}")
        flash('Error loading overview page', 'error')
        return redirect(url_for('homepage'))


@app.route('/api/plants/update-photo', methods=['POST'])
@login_required
def update_plant_photo():
    try:
        plant_id = request.form.get('plant_id')
        plant_photo = request.files.get('plant_photo')
        
        if not plant_id or not plant_photo or not plant_photo.filename:
            return jsonify({'success': False, 'message': 'Plant ID and photo are required'})
        
        # Save the uploaded file
        filename = secure_filename(plant_photo.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"plant_{timestamp}_{filename}"
        upload_path = os.path.join(UPLOAD_FOLDER, 'plant_photos')
        os.makedirs(upload_path, exist_ok=True)
        file_path = os.path.join(upload_path, filename)
        plant_photo.save(file_path)
        plant_photo_url = f"/static/uploads/plant_photos/{filename}"
        
        # Update the plant document
        result = plants_collection.update_one(
            {'_id': ObjectId(plant_id)},
            {'$set': {'plant_photo': plant_photo_url}}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'Photo updated successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to update photo'})
    except Exception as e:
        print(f"Error updating plant photo: {e}")
        return jsonify({'success': False, 'message': 'Server error'})

@app.route('/static/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(UPLOAD_FOLDER, filename)

# Import required modules for Google Drive upload
import re
import urllib.parse
from upload_progress import UploadProgressTracker, upload_status

# Global upload tracking
upload_sessions = {}

def extract_file_id_from_folder_url(folder_url):
    """Extract folder ID from Google Drive folder URL"""
    # Handle both folder and file URLs
    patterns = [
        r'/folders/([a-zA-Z0-9-_]+)',
        r'/file/d/([a-zA-Z0-9-_]+)',
        r'id=([a-zA-Z0-9-_]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, folder_url)
        if match:
            return match.group(1)
    
    return None

@app.route('/google_drive_upload')
@login_required
def google_drive_upload():
    """Render Google Drive upload page"""
    return render_template('google_drive_upload.html')

@app.route('/audi_tif/upload', methods=['POST'])
@login_required 
def handle_google_drive_upload():
    """Handle Google Drive upload request with enhanced progress tracking"""
    try:
        # Get form data
        audit_type = request.form.get('audit_type')
        plant_id = request.form.get('plant_id')
        audit_id = request.form.get('audit_id')
        tif_file_name = request.form.get('tif_file_name')
        g_url = request.form.get('g_url')
        upload_id = request.form.get('upload_id')
        
        # Validate required fields
        if not all([audit_type, plant_id, audit_id, tif_file_name, g_url]):
            return jsonify({
                'success': False,
                'error': 'All fields are required'
            }), 400
        
        # Generate upload ID if not provided
        if not upload_id:
            upload_id = str(uuid.uuid4())
        
        # Create enhanced progress tracker
        tracker = UploadProgressTracker(upload_id, tif_file_name, 0)  # Size unknown initially
        tracker.set_stage('initializing', 'Validating Google Drive link')
        
        # Validate Google Drive URL
        if 'drive.google.com' not in g_url:
            tracker.set_status('failed', 'Invalid Google Drive URL')
            return jsonify({
                'success': False,
                'error': 'Invalid Google Drive URL'
            }), 400
        
        # Store upload session with enhanced data
        upload_sessions = getattr(app, 'upload_sessions', {})
        upload_sessions[upload_id] = {
            'upload_id': upload_id,
            'audit_type': audit_type,
            'plant_id': plant_id,
            'audit_id': audit_id,
            'tif_file_name': tif_file_name,
            'g_url': g_url,
            'start_time': datetime.utcnow(),
            'status': 'started'
        }
        app.upload_sessions = upload_sessions
        
        # Start background process with enhanced tracking
        import threading
        thread = threading.Thread(
            target=process_google_drive_upload_enhanced,
            args=(upload_id, audit_type, plant_id, audit_id, tif_file_name, g_url, tracker)
        )
        thread.start()
        
        return jsonify({
            'success': True,
            'upload_id': upload_id,
            'message': 'Google Drive upload started successfully'
        })
        
    except Exception as e:
        print(f"Error in Google Drive upload: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def process_google_drive_upload_enhanced(upload_id, audit_type, plant_id, audit_id, tif_file_name, g_url, tracker):
    """Enhanced Google Drive upload process with detailed progress tracking"""
    try:
        # Stage 1: Initialize download
        tracker.set_stage('downloading', 'Preparing Google Drive download')
        tracker.set_progress(5)
        
        # Extract file ID from Google Drive URL
        import re
        file_id_match = re.search(r'/file/d/([a-zA-Z0-9-_]+)', g_url)
        if not file_id_match:
            raise Exception('Could not extract file ID from Google Drive URL')
        
        file_id = file_id_match.group(1)
        
        # Stage 2: Create temporary directory
        tracker.set_stage('downloading', 'Creating temporary workspace')
        tracker.set_progress(10)
        
        temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'temp', upload_id)
        os.makedirs(temp_dir, exist_ok=True)
        temp_file_path = os.path.join(temp_dir, tif_file_name)
        
        # Stage 3: Download from Google Drive with progress
        tracker.set_stage('downloading', 'Downloading from Google Drive')
        tracker.set_progress(15)
        
        download_url = f"https://drive.google.com/uc?id={file_id}"
        
        # Enhanced download with gdown
        try:
            import gdown
            
            # Use gdown for reliable download with progress
            def progress_callback(current, total):
                if total > 0:
                    progress = 15 + (current / total) * 60  # 15% to 75%
                    tracker.set_progress(progress)
                    tracker.set_stage('downloading', f'Downloaded {current/1024/1024:.1f}MB / {total/1024/1024:.1f}MB')
            
            # Update tracker total size if we can get it
            try:
                # Try to get file info first
                file_info = gdown.get_file_info(file_id)
                if file_info and 'size' in file_info:
                    tracker.total_size = int(file_info['size'])
            except:
                pass
            
            # Download file
            gdown.download(download_url, temp_file_path, quiet=False)
            
        except Exception as e:
            print(f"gdown failed, trying alternative method: {e}")
            # Fallback to requests
            import requests
            response = requests.get(download_url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            if total_size > 0:
                tracker.total_size = total_size
            
            downloaded = 0
            with open(temp_file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = 15 + (downloaded / total_size) * 60
                            tracker.set_progress(progress)
                            tracker.set_stage('downloading', f'Downloaded {downloaded/1024/1024:.1f}MB / {total_size/1024/1024:.1f}MB')
        
        # Stage 4: Verify file
        tracker.set_stage('processing', 'Verifying downloaded file')
        tracker.set_progress(75)
        
        if not os.path.exists(temp_file_path):
            raise Exception('File download failed - file not found')
        
        file_size = os.path.getsize(temp_file_path)
        if file_size == 0:
            raise Exception('Downloaded file is empty')
        
        tracker.file_size = file_size
        
        # Stage 5: Upload to S3
        tracker.set_stage('uploading', 'Uploading to cloud storage')
        tracker.set_progress(80)
        
        try:
            s3_key = f"thermal_audits/{plant_id}/{audit_id}/{tif_file_name}"
            s3_url = upload_to_s3(temp_file_path, s3_key)
            
            tracker.set_progress(90)
            tracker.set_stage('finalizing', 'Saving audit record')
            
            # Stage 6: Save to database
            audit_data = {
                'audit_id': audit_id,
                'plant_id': plant_id,
                'audit_type': audit_type,
                'tif_file_name': tif_file_name,
                'google_drive_url': g_url,
                's3_url': s3_url,
                's3_key': s3_key,
                'file_size': file_size,
                'upload_date': datetime.utcnow(),
                'upload_method': 'google_drive_enhanced',
                'status': 'completed',
                'upload_id': upload_id
            }
            
            audits_collection.insert_one(audit_data)
            
            # Stage 7: Complete
            tracker.set_progress(100)
            tracker.set_status('completed', f'Upload completed successfully. File uploaded to cloud storage.')
            tracker.final_path = s3_url
            
        except Exception as s3_error:
            print(f"S3 upload failed: {s3_error}")
            # Save without S3 URL
            audit_data = {
                'audit_id': audit_id,
                'plant_id': plant_id,
                'audit_type': audit_type,
                'tif_file_name': tif_file_name,
                'google_drive_url': g_url,
                'local_path': temp_file_path,
                'file_size': file_size,
                'upload_date': datetime.utcnow(),
                'upload_method': 'google_drive_local',
                'status': 'completed',
                'upload_id': upload_id,
                'note': 'Stored locally due to cloud upload failure'
            }
            
            audits_collection.insert_one(audit_data)
            tracker.set_status('completed', 'Upload completed (stored locally)')
        
    except Exception as e:
        print(f"Error in enhanced Google Drive upload process: {e}")
        tracker.set_status('failed', f'Upload failed: {str(e)}')
        
    finally:
        # Cleanup temp files (optional - keep for debugging)
        try:
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                # Don't delete immediately - keep for potential retry
                pass
        except:
            pass

@app.route('/audit/upload', methods=['POST'])
def audit_upload():
    """Handle Google Drive folder upload for audits"""
    try:
        data = request.get_json()
        g_url = data.get('g_url')
        plant_id = data.get('plant_id')
        tif_file_name = data.get('tif_file_name', f'audit_{int(time.time())}.tif')
        
        if not g_url:
            return jsonify({'success': False, 'error': 'Google Drive URL is required'}), 400
            
        # Generate unique upload ID
        upload_id = str(uuid.uuid4())
        
        # Store upload info for tracking
        upload_progress[upload_id] = {
            'plant_id': plant_id,
            'tif_file_name': tif_file_name,
            'g_url': g_url,
            'status': 'initialized',
            'created_at': datetime.utcnow()
        }
        
        # Start background upload process
        import threading
        thread = threading.Thread(target=process_audit_google_drive_upload, args=(upload_id,))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'upload_id': upload_id,
            'message': 'Google Drive upload started'
        })
        
    except Exception as e:
        print(f"Error in Google Drive upload: {e}")
        return jsonify({
            'success': False,
            'error': f'Upload failed: {str(e)}'
        }), 500

def process_audit_google_drive_upload(upload_id):
    """Background process to handle Google Drive download and AWS upload"""
    try:
        session = upload_sessions.get(upload_id)
        if not session:
            return
        
        tracker = upload_status.get(upload_id)
        if not tracker:
            return
        
        # Extract folder/file ID from URL
        folder_id = extract_file_id_from_folder_url(session['g_url'])
        if not folder_id:
            tracker.set_status('failed', 'Invalid Google Drive URL')
            return
        
        # Update progress
        tracker.set_stage('downloading', 'Downloading from Google Drive')
        
        # Import gdown for downloading
        import gdown
        import tempfile
        
        # Create temp directory
        temp_dir = tempfile.mkdtemp()
        temp_file_path = os.path.join(temp_dir, session['tif_file_name'])
        
        try:
            # Try downloading as a file first
            file_url = f'https://drive.google.com/uc?id={folder_id}'
            
            tracker.set_stage('downloading', 'Downloading file from Google Drive')
            
            # Download the file
            gdown.download(file_url, temp_file_path, quiet=False, fuzzy=True)
            
            # Check if file was downloaded
            if not os.path.exists(temp_file_path):
                raise Exception("File download failed")
            
            file_size = os.path.getsize(temp_file_path)
            tracker.total_size = file_size
            
            # Update progress
            tracker.set_stage('uploading', 'Uploading to AWS S3')
            
            # Upload to S3
            s3_client = get_s3_resource()
            bucket_name = get_config('bucket_name', 'sylo-energy')
            
            # Generate S3 key
            s3_key = f"{session['audit_type']}/{session['plant_id']}/{session['audit_id']}/{session['tif_file_name']}"
            
            # Upload with progress callback
            def upload_callback(bytes_transferred):
                tracker.update_progress(bytes_transferred, 'uploading')
            
            s3_client.upload_file(
                temp_file_path,
                bucket_name,
                s3_key,
                Callback=upload_callback
            )
            
            # Final S3 URL
            s3_url = f"{get_config('s3_prefix')}/{s3_key}"
            
            # Save audit record to database
            audit_data = {
                'audit_type': session['audit_type'],
                'plant_id': session['plant_id'],
                'audit_id': session['audit_id'],
                'file_name': session['tif_file_name'],
                'google_drive_url': session['g_url'],
                's3_url': s3_url,
                's3_key': s3_key,
                'file_size': file_size,
                'upload_date': datetime.utcnow(),
                'upload_method': 'google_drive'
            }
            
            audits_collection.insert_one(audit_data)
            
            # Update progress as completed
            tracker.set_status('completed', f'Upload completed successfully. File uploaded to S3: {s3_url}')
            tracker.final_path = s3_url
            
        except Exception as e:
            print(f"Error in Google Drive upload process: {e}")
            tracker.set_status('failed', f'Upload failed: {str(e)}')
        
        finally:
            # Cleanup temp files
            try:
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
                os.rmdir(temp_dir)
            except:
                pass
                
    except Exception as e:
        print(f"Critical error in process_audit_google_drive_upload: {e}")
        if upload_id in upload_status:
            upload_status[upload_id].set_status('failed', f'Critical error: {str(e)}')

@app.route('/upload_progress/<upload_id>')
@login_required
def get_upload_progress(upload_id):
    """Get upload progress for a specific upload ID"""
    try:
        tracker = upload_status.get(upload_id)
        if not tracker:
            return jsonify({'status': 'not_found'})
        
        return jsonify(tracker.get_progress_info())
        
    except Exception as e:
        print(f"Error getting upload progress: {e}")
        return jsonify({'status': 'error', 'error': str(e)})

@app.route('/upload')
@login_required
def upload_page():
    """Render upload page options"""
    return render_template('data_upload.html')

@app.route('/check/<plant_id>')
@login_required
def anomalies_map(plant_id):
    """Display anomalies map for a specific plant"""
    try:
        plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
        if not plant:
            flash('Plant not found', 'error')
            return redirect(url_for('homepage'))
        
        # Get all audits for this plant
        audits = list(audits_collection.find({'plant_id': plant_id}).sort('upload_date', -1))
        
        # Format audit data for the template
        formatted_audits = []
        for audit in audits:
            formatted_audits.append({
                '_id': str(audit['_id']),
                'audit_type': audit.get('audit_type', 'thermal'),
                'tif_file_name': audit.get('tif_file_name', 'Unknown'),
                'upload_date': audit.get('upload_date', datetime.utcnow()).strftime('%Y-%m-%d %H:%M'),
                'status': audit.get('status', 'completed'),
                's3_url': audit.get('s3_url', ''),
                'file_size': audit.get('file_size', 0)
            })
        
        return render_template('anomalies_map.html', 
                             plant=plant, 
                             audits=formatted_audits)
        
    except Exception as e:
        print(f"Error loading anomalies map: {e}")
        flash('Error loading anomalies map', 'error')
        return redirect(url_for('homepage'))

@app.route('/audit/<audit_id>/details')
@login_required
def audit_details(audit_id):
    """Display detailed view of an audit with thermal map"""
    try:
        audit = audits_collection.find_one({'_id': ObjectId(audit_id)})
        if not audit:
            flash('Audit not found', 'error')
            return redirect(url_for('homepage'))
        
        plant = plants_collection.find_one({'_id': ObjectId(audit['plant_id'])})
        
        return render_template('audit_detail_map.html', 
                             audit=audit, 
                             plant=plant)
        
    except Exception as e:
        print(f"Error loading audit details: {e}")
        flash('Error loading audit details', 'error')
        return redirect(url_for('homepage'))

@app.route('/api/upload-progress/<upload_id>')
@login_required
def api_upload_progress(upload_id):
    """API endpoint for real-time upload progress"""
    try:
        tracker = upload_status.get(upload_id)
        if not tracker:
            return jsonify({'status': 'not_found', 'progress': 0})
        
        progress_info = tracker.get_progress_info()
        return jsonify(progress_info)
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e), 'progress': 0})

@app.route('/api/audit/<audit_id>/report')
@login_required
def generate_audit_report(audit_id):
    """Generate PDF report for an audit"""
    try:
        audit = audits_collection.find_one({'_id': ObjectId(audit_id)})
        if not audit:
            return jsonify({'error': 'Audit not found'}), 404
        
        plant = plants_collection.find_one({'_id': ObjectId(audit['plant_id'])})
        
        # Here you would generate an actual PDF report
        # For now, return a JSON response
        return jsonify({
            'success': True,
            'message': 'Report generation started',
            'download_url': f'/api/audit/{audit_id}/download-report'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/audit/<audit_id>/export')
@login_required
def export_audit_data(audit_id):
    """Export audit data as JSON/CSV"""
    try:
        audit = audits_collection.find_one({'_id': ObjectId(audit_id)})
        if not audit:
            return jsonify({'error': 'Audit not found'}), 404
        
        # Prepare export data
        export_data = {
            'audit_id': str(audit['_id']),
            'plant_id': audit['plant_id'],
            'audit_type': audit['audit_type'],
            'file_name': audit['tif_file_name'],
            'upload_date': audit['upload_date'].isoformat() if audit.get('upload_date') else None,
            'file_size': audit.get('file_size', 0),
            'status': audit.get('status', 'completed'),
            's3_url': audit.get('s3_url', ''),
            'upload_method': audit.get('upload_method', 'unknown')
        }
        
        return jsonify(export_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload/status/<upload_id>')
@login_required
def real_time_upload_status(upload_id):
    """Real-time upload status for SSE (Server-Sent Events)"""
    def generate():
        while True:
            tracker = upload_status.get(upload_id)
            if not tracker:
                yield f"data: {json.dumps({'status': 'not_found'})}\n\n"
                break
            
            progress_info = tracker.get_progress_info()
            yield f"data: {json.dumps(progress_info)}\n\n"
            
            if progress_info['status'] in ['completed', 'failed']:
                break
            
            import time
            time.sleep(1)
    
    from flask import Response
    return Response(generate(), mimetype='text/plain')

if __name__ == '__main__':
    app.run(port=3333)

