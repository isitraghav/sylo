"""
Upload Progress Tracking Module
Provides real-time upload status and progress monitoring
"""
import os
import time
import threading
from datetime import datetime
from flask import jsonify

# Global upload status tracking
upload_status = {}

class UploadProgressTracker:
    """Track upload progress with detailed status information"""
    
    def __init__(self, upload_id, filename, total_size):
        self.upload_id = upload_id
        self.filename = filename
        self.total_size = total_size
        self.bytes_uploaded = 0
        self.start_time = time.time()
        self.status = 'initializing'
        self.error = None
        self.stage = 'preparing'
        self.progress_percentage = 0
        self.upload_speed = 0
        self.eta = 0
        
        # Initialize in global tracker
        upload_status[upload_id] = self
    
    def update_progress(self, bytes_uploaded, stage='uploading'):
        """Update upload progress"""
        self.bytes_uploaded = bytes_uploaded
        self.stage = stage
        self.progress_percentage = (bytes_uploaded / self.total_size) * 100 if self.total_size > 0 else 0
        
        # Calculate upload speed and ETA
        elapsed_time = time.time() - self.start_time
        if elapsed_time > 0:
            self.upload_speed = bytes_uploaded / elapsed_time  # bytes per second
            remaining_bytes = self.total_size - bytes_uploaded
            if self.upload_speed > 0:
                self.eta = remaining_bytes / self.upload_speed
        
        self.status = 'uploading'
        
        # Log progress
        print(f"📊 Upload Progress - {self.filename}: {self.progress_percentage:.1f}% "
              f"({self.bytes_uploaded}/{self.total_size} bytes) - {stage}")
    
    def set_stage(self, stage, message=None):
        """Update the current stage of upload"""
        self.stage = stage
        if message:
            print(f"🔄 Upload Stage - {self.filename}: {stage} - {message}")
    
    def complete(self, final_path=None):
        """Mark upload as completed"""
        self.status = 'completed'
        self.stage = 'completed'
        self.progress_percentage = 100
        self.final_path = final_path
        print(f"✅ Upload Completed - {self.filename}: {final_path}")
    
    def fail(self, error_message):
        """Mark upload as failed"""
        self.status = 'failed'
        self.stage = 'failed'
        self.error = error_message
        print(f"❌ Upload Failed - {self.filename}: {error_message}")
    
    def get_status(self):
        """Get current upload status"""
        elapsed_time = time.time() - self.start_time
        
        return {
            'upload_id': self.upload_id,
            'filename': self.filename,
            'status': self.status,
            'stage': self.stage,
            'progress_percentage': round(self.progress_percentage, 1),
            'bytes_uploaded': self.bytes_uploaded,
            'total_size': self.total_size,
            'upload_speed_mbps': round(self.upload_speed / (1024 * 1024), 2) if self.upload_speed > 0 else 0,
            'elapsed_time': round(elapsed_time, 1),
            'eta_seconds': round(self.eta, 1) if hasattr(self, 'eta') else 0,
            'error': self.error
        }

class StreamingUploadWithProgress:
    """Enhanced streaming upload with progress tracking"""
    
    def __init__(self, file_obj, upload_path, tracker, chunk_size=8*1024*1024):
        self.file_obj = file_obj
        self.upload_path = upload_path
        self.tracker = tracker
        self.chunk_size = chunk_size
    
    def save_with_progress(self):
        """Save file with real-time progress updates"""
        try:
            self.tracker.set_stage('creating_file', 'Creating upload directory')
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.upload_path), exist_ok=True)
            
            self.tracker.set_stage('writing_file', 'Starting file write')
            
            bytes_written = 0
            with open(self.upload_path, 'wb') as f:
                while True:
                    chunk = self.file_obj.read(self.chunk_size)
                    if not chunk:
                        break
                    
                    f.write(chunk)
                    bytes_written += len(chunk)
                    
                    # Update progress
                    self.tracker.update_progress(bytes_written, 'writing_file')
                    
                    # Add small delay to prevent overwhelming the progress tracker
                    time.sleep(0.01)
            
            self.tracker.set_stage('verifying', 'Verifying file integrity')
            
            # Verify file size
            actual_size = os.path.getsize(self.upload_path)
            if actual_size != self.tracker.total_size:
                raise ValueError(f"File size mismatch: expected {self.tracker.total_size}, got {actual_size}")
            
            self.tracker.complete(self.upload_path)
            
            return {
                'success': True,
                'file_path': self.upload_path,
                'bytes_written': bytes_written,
                'upload_time': time.time() - self.tracker.start_time
            }
            
        except Exception as e:
            self.tracker.fail(str(e))
            # Clean up partial file
            if os.path.exists(self.upload_path):
                os.remove(self.upload_path)
            raise e

def cleanup_old_status(max_age_hours=24):
    """Clean up old upload status entries"""
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    to_remove = []
    for upload_id, tracker in upload_status.items():
        if current_time - tracker.start_time > max_age_seconds:
            to_remove.append(upload_id)
    
    for upload_id in to_remove:
        del upload_status[upload_id]
        print(f"🧹 Cleaned up old upload status: {upload_id}")

# Background cleanup task
def start_cleanup_task():
    """Start background task to clean up old upload status"""
    def cleanup_worker():
        while True:
            time.sleep(3600)  # Clean every hour
            cleanup_old_status()
    
    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()
    print("🧹 Started upload status cleanup task")

# Start cleanup task when module is imported
start_cleanup_task()

print("✅ Upload progress tracking module loaded")
