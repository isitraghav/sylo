import os
import time
import hashlib
import threading
from flask import Flask, request, render_template, jsonify
from werkzeug.utils import secure_filename
import boto3
from botocore.config import Config

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = 'uploads_data'
TEMP_FOLDER = 'temp_uploads'
MAX_CONTENT_LENGTH = 5 * 1024 * 1024 * 1024  # 5GB max
CHUNK_SIZE = 16 * 1024 * 1024  # 16MB chunks - tested and working

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

# Global dict to track upload progress
upload_progress = {}
upload_locks = {}


@app.route('/audi_tif/new_upload', methods=['POST', 'GET'])
def upload_te():
    if request.method == 'GET':
        return render_template("test_upload.html")

    try:
        # Get form fields
        audit_type = request.form.get('audit_type')
        plant_id = request.form.get('plant_id')
        audit_id = request.form.get('audit_id')

        # Validate required fields
        if not all([audit_type, plant_id, audit_id]):
            return jsonify({'error': 'Missing required fields'}), 400

        # Get the uploaded file
        file = request.files.get('tif_file_name')
        if not file or file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        filename = secure_filename(file.filename)
        if not filename:
            return jsonify({'error': 'Invalid filename'}), 400

        # Create unique filename to avoid conflicts
        timestamp = str(int(time.time()))
        unique_filename = f"{audit_id}_{plant_id}_{timestamp}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

        print(f"Starting upload: {unique_filename}")
        print(f"Audit Type: {audit_type}, Plant ID: {plant_id}, Audit ID: {audit_id}")

        # FIXED: Process file immediately while stream is still open
        success = save_file_streaming_sync(file, file_path, unique_filename)

        if success:
            return jsonify({
                'message': 'File uploaded successfully',
                'filename': unique_filename,
                'path': file_path,
                'audit_type': audit_type,
                'plant_id': plant_id,
                'audit_id': audit_id
            }), 200
        else:
            return jsonify({'error': 'Upload failed'}), 500

    except Exception as err:
        print(f"Upload error: {err}")
        return jsonify({'error': f'Upload failed: {str(err)}'}), 500


def save_file_streaming_sync(file_obj, file_path, unique_filename):
    """Save file using streaming - SYNCHRONOUS version that works"""
    try:
        # Initialize progress tracking
        upload_progress[unique_filename] = {
            'bytes_written': 0,
            'status': 'uploading',
            'start_time': time.time()
        }
        upload_locks[unique_filename] = threading.Lock()

        bytes_written = 0
        hash_md5 = hashlib.md5()

        # Create temporary file first
        temp_path = os.path.join(TEMP_FOLDER, f"temp_{unique_filename}")

        # CRITICAL FIX: Process the file stream IMMEDIATELY, not in a thread
        with open(temp_path, 'wb') as f:
            while True:
                # Read directly from file_obj.stream while it's still open
                chunk = file_obj.stream.read(CHUNK_SIZE)
                if not chunk:
                    break

                # Write chunk
                f.write(chunk)
                bytes_written += len(chunk)
                hash_md5.update(chunk)

                # Update progress (thread-safe)
                with upload_locks[unique_filename]:
                    upload_progress[unique_filename]['bytes_written'] = bytes_written

                # Log progress every 500MB
                if bytes_written % (500 * 1024 * 1024) == 0:
                    print(f"Progress {unique_filename}: {bytes_written / (1024 * 1024):.1f} MB")

        # Move from temp to final location atomically
        os.rename(temp_path, file_path)

        # Update final progress
        with upload_locks[unique_filename]:
            upload_progress[unique_filename].update({
                'status': 'completed',
                'bytes_written': bytes_written,
                'md5_hash': hash_md5.hexdigest(),
                'end_time': time.time()
            })

        file_size_mb = bytes_written / (1024 * 1024)
        elapsed_time = upload_progress[unique_filename]['end_time'] - upload_progress[unique_filename]['start_time']

        print(f"Upload completed: {unique_filename}")
        print(f"Size: {file_size_mb:.1f} MB, Time: {elapsed_time:.1f}s")
        print(f"Speed: {file_size_mb / elapsed_time:.1f} MB/s")

        return True

    except Exception as e:
        print(f"Streaming save error: {e}")

        # Update progress with error
        if unique_filename in upload_progress:
            with upload_locks.get(unique_filename, threading.Lock()):
                upload_progress[unique_filename]['status'] = 'failed'
                upload_progress[unique_filename]['error'] = str(e)

        # Clean up temp file
        temp_path = os.path.join(TEMP_FOLDER, f"temp_{unique_filename}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

        return False

    finally:
        # Clean up progress tracking after some time
        def cleanup_progress():
            time.sleep(300)  # Wait 5 minutes
            if unique_filename in upload_progress:
                del upload_progress[unique_filename]
            if unique_filename in upload_locks:
                del upload_locks[unique_filename]

        cleanup_thread = threading.Thread(target=cleanup_progress)
        cleanup_thread.daemon = True
        cleanup_thread.start()


@app.route('/audi_tif/async_upload', methods=['POST'])
def async_upload():
    """Asynchronous upload - FIXED VERSION"""
    try:
        audit_type = request.form.get('audit_type')
        plant_id = request.form.get('plant_id')
        audit_id = request.form.get('audit_id')
        file = request.files.get('tif_file_name')

        if not all([audit_type, plant_id, audit_id, file]):
            return jsonify({'error': 'Missing required fields or file'}), 400

        filename = secure_filename(file.filename)
        timestamp = str(int(time.time()))
        unique_filename = f"{audit_id}_{plant_id}_{timestamp}_{filename}"

        # CRITICAL FIX: Save to temp file first BEFORE starting thread
        temp_path = os.path.join(TEMP_FOLDER, f"async_temp_{unique_filename}")

        # Save the entire file to temp location while stream is open
        file.save(temp_path)

        final_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

        # Now start background processing from the saved temp file
        def background_process():
            process_saved_file(temp_path, final_path, unique_filename)

        upload_thread = threading.Thread(target=background_process)
        upload_thread.daemon = True
        upload_thread.start()

        return jsonify({
            'message': 'Upload started',
            'upload_id': unique_filename,
            'progress_url': f'/upload_progress/{unique_filename}'
        }), 202

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def process_saved_file(temp_path, final_path, unique_filename):
    """Process a file that's already saved to disk"""
    try:
        # Initialize progress tracking
        upload_progress[unique_filename] = {
            'bytes_written': 0,
            'status': 'processing',
            'start_time': time.time()
        }
        upload_locks[unique_filename] = threading.Lock()

        # Get file size
        file_size = os.path.getsize(temp_path)
        bytes_processed = 0
        hash_md5 = hashlib.md5()

        # Process file in chunks for progress tracking
        with open(temp_path, 'rb') as src, open(final_path, 'wb') as dst:
            while True:
                chunk = src.read(CHUNK_SIZE)
                if not chunk:
                    break

                dst.write(chunk)
                bytes_processed += len(chunk)
                hash_md5.update(chunk)

                # Update progress
                with upload_locks[unique_filename]:
                    upload_progress[unique_filename]['bytes_written'] = bytes_processed

                # Log progress
                if bytes_processed % (500 * 1024 * 1024) == 0:
                    print(f"Processing {unique_filename}: {bytes_processed / (1024 * 1024):.1f} MB")

        # Remove temp file
        os.remove(temp_path)

        # Update final progress
        with upload_locks[unique_filename]:
            upload_progress[unique_filename].update({
                'status': 'completed',
                'bytes_written': bytes_processed,
                'md5_hash': hash_md5.hexdigest(),
                'end_time': time.time()
            })

        file_size_mb = bytes_processed / (1024 * 1024)
        elapsed_time = upload_progress[unique_filename]['end_time'] - upload_progress[unique_filename]['start_time']

        print(f"Processing completed: {unique_filename}")
        print(f"Size: {file_size_mb:.1f} MB, Time: {elapsed_time:.1f}s")

    except Exception as e:
        print(f"Processing error: {e}")

        # Clean up temp file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

        # Update progress with error
        if unique_filename in upload_progress:
            with upload_locks.get(unique_filename, threading.Lock()):
                upload_progress[unique_filename]['status'] = 'failed'
                upload_progress[unique_filename]['error'] = str(e)


@app.route('/upload_progress/<filename>')
def get_upload_progress(filename):
    """Get real-time upload progress"""
    progress = upload_progress.get(filename, {'status': 'not_found'})

    if 'start_time' in progress and progress['status'] in ['uploading', 'processing']:
        elapsed = time.time() - progress['start_time']
        bytes_written = progress['bytes_written']

        if elapsed > 0 and bytes_written > 0:
            speed_mbps = (bytes_written / (1024 * 1024)) / elapsed
            progress['speed_mbps'] = round(speed_mbps, 2)
            progress['elapsed_time'] = round(elapsed, 1)

    return jsonify(progress)


# Alternative method using werkzeug's save method
@app.route('/audi_tif/simple_upload', methods=['POST'])
def simple_upload():
    """Simple upload using werkzeug's built-in save method"""
    try:
        audit_type = request.form.get('audit_type')
        plant_id = request.form.get('plant_id')
        audit_id = request.form.get('audit_id')
        file = request.files.get('tif_file_name')

        if not all([audit_type, plant_id, audit_id, file]):
            return jsonify({'error': 'Missing required fields or file'}), 400

        filename = secure_filename(file.filename)
        timestamp = str(int(time.time()))
        unique_filename = f"{audit_id}_{plant_id}_{timestamp}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

        print(f"Starting simple upload: {unique_filename}")

        # Use werkzeug's built-in save method - this is the most reliable
        start_time = time.time()
        file.save(file_path)
        end_time = time.time()

        # Get file size
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)
        elapsed_time = end_time - start_time

        print(f"Simple upload completed: {unique_filename}")
        print(f"Size: {file_size_mb:.1f} MB, Time: {elapsed_time:.1f}s")
        print(f"Speed: {file_size_mb / elapsed_time:.1f} MB/s")

        return jsonify({
            'message': 'File uploaded successfully',
            'filename': unique_filename,
            'path': file_path,
            'size_mb': round(file_size_mb, 1),
            'upload_time': round(elapsed_time, 1),
            'speed_mbps': round(file_size_mb / elapsed_time, 1)
        }), 200

    except Exception as e:
        print(f"Simple upload error: {e}")
        return jsonify({'error': str(e)}), 500


# Health check endpoint
@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'active_uploads': len(upload_progress),
        'upload_folder': app.config['UPLOAD_FOLDER']
    })


if __name__ == '__main__':
    app.run(debug=True, threaded=True,port=1211, host='0.0.0.0')