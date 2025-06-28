# Render Deployment Configuration Guide

## 🚀 Environment Variables to Set in Render Dashboard

Go to your Render service settings → Environment → Add Environment Variable

### Required Environment Variables:

```bash
# MongoDB Configuration
MONGO_CONNECTION=mongodb+srv://USERNAME:PASSWORD@your-cluster.mongodb.net/database_name?retryWrites=true&w=majority

# AWS S3 Configuration  
aws_access_key_id=YOUR_AWS_ACCESS_KEY_ID
aws_secret_access_key=YOUR_AWS_SECRET_ACCESS_KEY
bucket_name=your-bucket-name
s3_prefix=https://your-bucket-name.s3.region.amazonaws.com
region_name=your-region

# Server Configuration
PORT=10000
HOST=0.0.0.0

# Application Settings
MAX_FILE_SIZE=53687091200
UPLOAD_TIMEOUT=3600
CHUNK_SIZE=8388608
```

## 📋 Render Service Configuration

### Build Settings:
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python server.py`

### Advanced Settings:
- **Plan**: Standard ($25/month) - Required for 100GB disk space
- **Python Version**: 3.11.x
- **Auto-Deploy**: Enabled (optional)

## 🔧 Steps to Deploy:

1. **Connect Repository**:
   - Link your GitHub repository in Render
   - Select branch: `main`

2. **Configure Service**:
   - Service Type: Web Service
   - Runtime: Python 3
   - Plan: Standard (required for large files)

3. **Set Environment Variables**:
   - Copy all variables from above section
   - Add them one by one in Render dashboard

4. **Deploy**:
   - Click "Create Web Service"
   - Wait for deployment to complete

## 🌐 Access URLs:

After successful deployment:
- **Main App**: `https://your-app-name.onrender.com`
- **Upload Interface**: `https://your-app-name.onrender.com/audi_tif/new_upload`
- **Health Check**: `https://your-app-name.onrender.com/health`

## ⚠️ Important Notes:

1. **Disk Space**: Standard plan provides 100GB disk space for file uploads
2. **Memory**: 2GB RAM included with Standard plan
3. **Timeout**: 10-minute request timeout (handled by chunked uploads)
4. **Environment**: All sensitive data is stored in environment variables (secure)

## 🔍 Troubleshooting:

### Common Issues:
- **Missing ENV vars**: Add all required environment variables
- **Build failures**: Check requirements.txt has all dependencies
- **Import errors**: Ensure all files are committed to GitHub
- **Database connection**: Verify MongoDB connection string

### Logs:
Check Render deployment logs for specific error messages.
