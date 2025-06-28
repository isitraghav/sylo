#!/usr/bin/env python3
"""
Status check script for Solar Plant Management System
"""
import sys
import os
from dotenv import load_dotenv, dotenv_values

def check_environment():
    """Check if environment variables are properly configured"""
    print("🔍 Checking Environment Configuration...")
    
    if not os.path.exists('.env'):
        print("❌ .env file not found")
        return False
    
    config = dotenv_values(".env")
    required_keys = [
        'MONGO_CONNECTION', 'bucket_name', 's3_prefix', 
        'aws_access_key_id', 'aws_secret_access_key', 'region_name'
    ]
    
    missing_keys = [key for key in required_keys if key not in config or not config[key]]
    
    if missing_keys:
        print(f"❌ Missing environment variables: {', '.join(missing_keys)}")
        return False
    
    print("✅ Environment variables configured")
    return True

def check_dependencies():
    """Check if required packages are installed"""
    print("🔍 Checking Dependencies...")
    
    required_packages = [
        'flask', 'flask_pymongo', 'boto3', 'pymongo', 
        'dotenv', 'waitress', 'pandas', 'numpy'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing packages: {', '.join(missing_packages)}")
        return False
    
    print("✅ All dependencies installed")
    return True

def check_directories():
    """Check if required directories exist"""
    print("🔍 Checking Directories...")
    
    required_dirs = ['uploads_data', 'templates', 'static']
    missing_dirs = [d for d in required_dirs if not os.path.exists(d)]
    
    if missing_dirs:
        print(f"❌ Missing directories: {', '.join(missing_dirs)}")
        return False
    
    print("✅ All required directories exist")
    return True

def check_main_app():
    """Check if main application can be imported"""
    print("🔍 Checking Main Application...")
    
    try:
        import main
        from upload_config import UploadConfig
        max_size_gb = UploadConfig.get_file_size_gb(UploadConfig.MAX_FILE_SIZE)
        supported_types = len(UploadConfig.ALLOWED_EXTENSIONS)
        print(f"✅ Main application imports successfully")
        print(f"✅ Upload capacity: {max_size_gb:.1f} GB maximum")
        print(f"✅ Supported file types: {supported_types} formats")
        return True
    except Exception as e:
        print(f"❌ Error importing main application: {e}")
        return False

def main():
    """Run all status checks"""
    print("🚀 Solar Plant Management System - Status Check")
    print("=" * 50)
    
    checks = [
        check_environment,
        check_dependencies,
        check_directories,
        check_main_app
    ]
    
    all_passed = True
    for check in checks:
        if not check():
            all_passed = False
        print()
    
    if all_passed:
        print("🎉 All checks passed! The application is ready to run.")
        print("📋 To start the server, run:")
        print("   python server.py")
        print("🌐 Application will be available at: http://localhost:1211")
    else:
        print("⚠️  Some checks failed. Please resolve the issues above.")
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
