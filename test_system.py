"""
Test script to demonstrate upload progress and failure handling
"""
import requests
import time
import json

def test_login_page():
    """Test the login page and show terminal output"""
    print("🌐 Testing SYLO Energy Login Page...")
    
    try:
        response = requests.get('http://127.0.0.1:3333/login')
        print(f"✅ Login page loaded successfully (Status: {response.status_code})")
        
        # Check if the page contains our updated content
        if 'SYLO ENERGY' in response.text and 'login_back.jpeg' in response.text:
            print("✅ Updated design with logo and background image loaded")
        else:
            print("⚠️  Updated design may not be fully loaded")
            
    except Exception as e:
        print(f"❌ Error accessing login page: {e}")

def test_login_attempt():
    """Test login attempt to show terminal status logging"""
    print("\n🔐 Testing login attempt...")
    
    try:
        # Test a failed login attempt
        login_data = {
            'loginId': 'test@sylo.com',
            'password': 'wrongpassword'
        }
        response = requests.post('http://127.0.0.1:3333/login', 
                               json=login_data,
                               headers={'Content-Type': 'application/json'})
        print(f"Login attempt status: {response.status_code}")
        result = response.json()
        print(f"Response: {result}")
        
    except Exception as e:
        print(f"❌ Error during login attempt: {e}")

def test_upload_progress():
    """Test upload progress tracking"""
    print("\n📊 Testing upload progress tracking...")
    
    try:
        # Get all upload status
        response = requests.get('http://127.0.0.1:3333/api/upload/status')
        print(f"Upload status endpoint: {response.status_code}")
        result = response.json()
        print(f"Active uploads: {result.get('total_active', 0)}")
        
    except Exception as e:
        print(f"❌ Error checking upload status: {e}")

def test_upload_progress_page():
    """Test the upload progress test page"""
    print("\n🚀 Testing upload progress test page...")
    
    try:
        response = requests.get('http://127.0.0.1:3333/upload-progress-test')
        print(f"Upload progress test page: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Upload progress test page loaded successfully")
        
    except Exception as e:
        print(f"❌ Error accessing upload progress page: {e}")

if __name__ == "__main__":
    print("🔧 SYLO Energy System Test Suite")
    print("=" * 50)
    
    test_login_page()
    test_login_attempt()
    test_upload_progress()
    test_upload_progress_page()
    
    print("\n" + "=" * 50)
    print("✅ Test suite completed!")
    print("\nTo see terminal status output:")
    print("1. Check the Flask server terminal for login attempts")
    print("2. Try uploading a file at: http://127.0.0.1:3333/upload-progress-test")
    print("3. Monitor upload progress with real-time status updates")
