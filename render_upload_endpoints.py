"""
Render-optimized chunked upload endpoints
Handles large file uploads within Render's 10-minute timeout limit
"""
import os
import json
import uuid
from datetime import datetime
from flask import request, jsonify
from main import app, data_uploads_collection, get_s3_resource
import boto3

# In-memory storage for upload sessions (use Redis in production)
upload_sessions = {}

@app.route('/api/upload/init', methods=['POST'])
def init_chunked_upload():
    """Initialize a chunked upload session"""
    try:
        data = request.json
        
        # Generate unique upload ID
        upload_id = str(uuid.uuid4())
        
        # Create upload session
        session = {
            'upload_id': upload_id,
            'filename': data['filename'],
            'file_size': data['fileSize'],
            'total_chunks': data['totalChunks'],
            'uploaded_chunks': [],
            'audit_type': data['audit_type'],
            'plant_id': data['plant_id'],
            'audit_id': data['audit_id'],
            'created_at': datetime.utcnow(),
            'status': 'initialized'
        }
        
        upload_sessions[upload_id] = session
        
        # Create temporary directory for chunks
        chunk_dir = os.path.join('temp_chunks', upload_id)
        os.makedirs(chunk_dir, exist_ok=True)
        session['chunk_dir'] = chunk_dir
        
        return jsonify({
            'success': True,
            'uploadId': upload_id,
            'message': 'Upload session initialized'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to initialize upload: {str(e)}'
        }), 500

@app.route('/api/upload/chunk', methods=['POST'])
def upload_chunk():
    """Upload a single chunk"""
    try:
        upload_id = request.form.get('uploadId')
        chunk_index = int(request.form.get('chunkIndex'))
        
        if upload_id not in upload_sessions:
            return jsonify({
                'success': False,
                'error': 'Upload session not found'
            }), 404
        
        session = upload_sessions[upload_id]
        chunk_file = request.files['chunk']
        
        # Save chunk to temporary file
        chunk_path = os.path.join(session['chunk_dir'], f'chunk_{chunk_index:06d}')
        chunk_file.save(chunk_path)
        
        # Track uploaded chunk
        session['uploaded_chunks'].append(chunk_index)
        session['status'] = 'uploading'
        
        return jsonify({
            'success': True,
            'chunkIndex': chunk_index,
            'uploadedChunks': len(session['uploaded_chunks']),
            'totalChunks': session['total_chunks']
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Chunk upload failed: {str(e)}'
        }), 500

@app.route('/api/upload/finalize', methods=['POST'])
def finalize_upload():
    """Combine chunks and finalize upload"""
    try:
        data = request.json
        upload_id = data['uploadId']
        
        if upload_id not in upload_sessions:
            return jsonify({
                'success': False,
                'error': 'Upload session not found'
            }), 404
        
        session = upload_sessions[upload_id]
        
        # Verify all chunks are uploaded
        if len(session['uploaded_chunks']) != session['total_chunks']:
            return jsonify({
                'success': False,
                'error': f'Missing chunks: {session["total_chunks"] - len(session["uploaded_chunks"])}'
            }), 400
        
        # Combine chunks into final file
        final_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S_')}{session['filename']}"
        final_path = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
        
        os.makedirs(os.path.dirname(final_path), exist_ok=True)
        
        with open(final_path, 'wb') as final_file:
            for i in range(session['total_chunks']):
                chunk_path = os.path.join(session['chunk_dir'], f'chunk_{i:06d}')
                if os.path.exists(chunk_path):
                    with open(chunk_path, 'rb') as chunk_file:
                        final_file.write(chunk_file.read())
                    os.remove(chunk_path)  # Clean up chunk
        
        # Upload to S3 (optional, for backup)
        try:
            s3_client = get_s3_resource()
            s3_key = f"uploads/{session['plant_id']}/{session['audit_id']}/{final_filename}"
            s3_client.upload_file(final_path, os.environ.get('bucket_name'), s3_key)
            s3_url = f"https://{os.environ.get('bucket_name')}.s3.{os.environ.get('region_name')}.amazonaws.com/{s3_key}"
        except Exception as s3_error:
            print(f"S3 upload failed: {s3_error}")
            s3_url = None
        
        # Save to database
        upload_data = {
            'filename': final_filename,
            'original_filename': session['filename'],
            'file_path': final_path,
            'file_size': session['file_size'],
            'audit_type': session['audit_type'],
            'plant_id': session['plant_id'],
            'audit_id': session['audit_id'],
            's3_url': s3_url,
            'uploaded_at': datetime.utcnow(),
            'upload_method': 'chunked_render'
        }
        
        result = data_uploads_collection.insert_one(upload_data)
        
        # Clean up
        os.rmdir(session['chunk_dir'])
        del upload_sessions[upload_id]
        
        return jsonify({
            'success': True,
            'filename': final_filename,
            'file_size': session['file_size'],
            'database_id': str(result.inserted_id),
            's3_url': s3_url,
            'message': 'Upload completed successfully'
        })
        
    except Exception as e:
        # Clean up on error
        if upload_id in upload_sessions:
            session = upload_sessions[upload_id]
            if 'chunk_dir' in session and os.path.exists(session['chunk_dir']):
                import shutil
                shutil.rmtree(session['chunk_dir'])
            del upload_sessions[upload_id]
        
        return jsonify({
            'success': False,
            'error': f'Upload finalization failed: {str(e)}'
        }), 500

@app.route('/api/upload/status/<upload_id>', methods=['GET'])
def get_upload_status(upload_id):
    """Get upload progress status"""
    if upload_id not in upload_sessions:
        return jsonify({
            'success': False,
            'error': 'Upload session not found'
        }), 404
    
    session = upload_sessions[upload_id]
    progress = len(session['uploaded_chunks']) / session['total_chunks'] * 100
    
    return jsonify({
        'success': True,
        'uploadId': upload_id,
        'progress': progress,
        'uploadedChunks': len(session['uploaded_chunks']),
        'totalChunks': session['total_chunks'],
        'status': session['status'],
        'filename': session['filename'],
        'file_size': session['file_size']
    })

@app.route('/render-upload')
def render_upload_page():
    """Serve the Render-optimized upload page"""
    return render_template('render_upload.html')

print("✅ Render-optimized chunked upload endpoints added")
