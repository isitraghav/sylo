#!/usr/bin/env python3
"""
Quick script to create/update admin user for testing
"""
import os
import sys
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv, dotenv_values

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

# Load environment variables
load_dotenv()

# Get MongoDB connection
mongo_uri = get_config('MONGO_CONNECTION')
if not mongo_uri:
    print("❌ ERROR: MONGO_CONNECTION not found")
    sys.exit(1)

client = MongoClient(mongo_uri)
db = client.thermal_db
users_collection = db.users

# Check if user exists and update or create admin user
user = users_collection.find_one({'email': 'admin@test.com'})

if user:
    print(f"Found user: {user}")
    # Update the user to admin role
    result = users_collection.update_one(
        {'email': 'admin@test.com'},
        {'$set': {'role': 'admin', 'updated_at': datetime.utcnow()}}
    )
    if result.modified_count > 0:
        print("✅ User updated to admin role successfully!")
    else:
        print("❌ Failed to update user role")
else:
    print("User not found, creating new admin user...")
    # Create new admin user
    user_data = {
        'email': 'admin@test.com',
        'password': 'admin123',
        'role': 'admin',
        'status': 1,
        'created_at': datetime.utcnow()
    }
    result = users_collection.insert_one(user_data)
    if result.inserted_id:
        print("✅ Admin user created successfully!")
    else:
        print("❌ Failed to create admin user")

# Verify the final state
user = users_collection.find_one({'email': 'admin@test.com'})
if user:
    print(f"\n📧 Email: {user['email']}")
    print(f"👤 Role: {user['role']}")
    print(f"🔑 Password: {user['password']}")
    print(f"✅ Status: {user['status']}")
else:
    print("❌ User not found after operation")

client.close()
