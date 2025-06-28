"""
File Upload Configuration Module
Optimized for handling large thermal imaging and geospatial files
"""
import os
from werkzeug.datastructures import FileStorage
from flask import current_app
import time

class UploadConfig:
    """Configuration class for optimized file uploads"""
    
    # Maximum file sizes (in bytes)
    MAX_FILE_SIZE = 50 * 1024 * 1024 * 1024  # 50 GB
    MAX_CHUNK_SIZE = 8 * 1024 * 1024         # 8 MB chunks
    
    # Timeout settings (in seconds)
    UPLOAD_TIMEOUT = 3600                     # 1 hour
    CHUNK_TIMEOUT = 300                       # 5 minutes per chunk
    
    # Supported file extensions
    ALLOWED_EXTENSIONS = {
        'tif', 'tiff',           # Thermal imaging
        'geojson', 'json',       # Geospatial data
        'zip', 'rar',           # Archives
        'csv', 'xlsx',          # Data files
        'png', 'jpg', 'jpeg',   # Images
        'kml', 'kmz',           # Google Earth files
        'shp', 'dbf', 'shx',    # Shapefiles
        'gpx', 'gps'            # GPS data
    }
    
    @staticmethod
    def is_allowed_file(filename):
        """Check if file extension is allowed"""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in UploadConfig.ALLOWED_EXTENSIONS
    
    @staticmethod
    def get_file_size_mb(file_size_bytes):
        """Convert bytes to MB"""
        return file_size_bytes / (1024 * 1024)
    
    @staticmethod
    def get_file_size_gb(file_size_bytes):
        """Convert bytes to GB"""
        return file_size_bytes / (1024 * 1024 * 1024)
    
    @staticmethod
    def validate_file_size(file_size_bytes):
        """Validate if file size is within limits"""
        return file_size_bytes <= UploadConfig.MAX_FILE_SIZE
    
    @staticmethod
    def get_upload_path(filename, subfolder=''):
        """Get safe upload path"""
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads_data')
        if subfolder:
            upload_folder = os.path.join(upload_folder, subfolder)
        os.makedirs(upload_folder, exist_ok=True)
        return os.path.join(upload_folder, filename)

class StreamingUpload:
    """Handle streaming uploads for large files"""
    
    def __init__(self, file_obj, upload_path, chunk_size=None):
        self.file_obj = file_obj
        self.upload_path = upload_path
        self.chunk_size = chunk_size or UploadConfig.MAX_CHUNK_SIZE
        self.total_bytes = 0
        self.start_time = time.time()
    
    def save_streaming(self):
        """Save file using streaming to handle large files efficiently"""
        try:
            with open(self.upload_path, 'wb') as f:
                while True:
                    chunk = self.file_obj.read(self.chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    self.total_bytes += len(chunk)
                    
                    # Check timeout
                    if time.time() - self.start_time > UploadConfig.UPLOAD_TIMEOUT:
                        raise TimeoutError("Upload timeout exceeded")
                    
                    # Validate file size during upload
                    if self.total_bytes > UploadConfig.MAX_FILE_SIZE:
                        raise ValueError("File size exceeds maximum limit")
            
            return {
                'success': True,
                'file_size': self.total_bytes,
                'file_size_mb': UploadConfig.get_file_size_mb(self.total_bytes),
                'file_size_gb': UploadConfig.get_file_size_gb(self.total_bytes),
                'upload_time': time.time() - self.start_time
            }
            
        except Exception as e:
            # Clean up partial file on error
            if os.path.exists(self.upload_path):
                os.remove(self.upload_path)
            raise e

# Web server configuration recommendations
WEB_SERVER_CONFIG = {
    'nginx': {
        'client_max_body_size': '50G',
        'client_body_timeout': '3600s',
        'client_header_timeout': '60s',
        'proxy_read_timeout': '3600s',
        'proxy_send_timeout': '3600s',
        'proxy_request_buffering': 'off'
    },
    'apache': {
        'LimitRequestBody': '53687091200',  # 50GB
        'TimeOut': '3600',
        'KeepAliveTimeout': '300'
    },
    'iis': {
        'maxAllowedContentLength': '53687091200',  # 50GB
        'requestTimeout': '01:00:00',  # 1 hour
        'maxRequestLength': '52428800'  # 50GB in KB
    }
}

# Operating system limits
OS_LIMITS = {
    'windows': {
        'max_file_size': '256TB',  # NTFS limit
        'practical_limit': '50GB',  # Recommended for web uploads
        'reason': 'Windows/NTFS supports very large files, limited by available RAM and disk space'
    },
    'linux': {
        'max_file_size': '8EB',   # ext4 limit
        'practical_limit': '50GB',
        'reason': 'Linux filesystems support huge files, limited by system resources'
    },
    'network': {
        'tcp_timeout': '2 hours default',
        'http_timeout': 'Configurable per server',
        'practical_upload_time': '1-6 hours for 50GB depending on network speed'
    }
}
