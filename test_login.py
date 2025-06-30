#!/usr/bin/env python3
"""
Test script to verify login and homepage access
"""
import requests
import json

base_url = "http://localhost:5000"

# Start a session
session = requests.Session()

# Test login
login_data = {
    "loginId": "admin@test.com",
    "password": "admin123"
}

print("🔐 Testing login...")
login_response = session.post(f"{base_url}/login", json=login_data)
print(f"Login Status: {login_response.status_code}")
print(f"Login Response: {login_response.text}")

if login_response.status_code == 200:
    login_result = login_response.json()
    if login_result.get('success'):
        print("✅ Login successful!")
        
        # Test homepage access
        print("\n🏠 Testing homepage access...")
        homepage_response = session.get(f"{base_url}/homepage")
        print(f"Homepage Status: {homepage_response.status_code}")
        
        if homepage_response.status_code == 200:
            print("✅ Homepage accessible!")
            print(f"Response length: {len(homepage_response.text)} characters")
            # Check if it contains expected content
            if "plant-card" in homepage_response.text:
                print("✅ Homepage contains plant card elements")
            else:
                print("⚠️ Homepage doesn't contain expected plant card elements")
        else:
            print(f"❌ Homepage not accessible: {homepage_response.status_code}")
            print(f"Response: {homepage_response.text[:500]}...")
    else:
        print(f"❌ Login failed: {login_result.get('message', 'Unknown error')}")
else:
    print(f"❌ Login request failed: {login_response.status_code}")
