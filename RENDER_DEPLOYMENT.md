# Render.com Deployment Guide for 50GB Solar Plant Management System

## 🚀 Render Deployment Configuration

### render.yaml
```yaml
services:
  - type: web
    name: solar-plant-app
    env: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "python server.py"
    plan: standard  # Required for 100GB disk space
    autoDeploy: false
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
      - key: PORT
        value: 10000
      - key: MAX_CONTENT_LENGTH
        value: 53687091200  # 50GB
    disk:
      name: solar-uploads
      mountPath: /opt/render/project/src/uploads_data
      sizeGB: 100  # 100GB disk for file storage
```

## 📋 Render Plan Requirements for 50GB Uploads

### ❌ **Free Tier**: Not suitable
- 512MB RAM (insufficient)
- No persistent disk
- Request timeout issues

### ⚠️ **Starter ($7/month)**: Limited
- 512MB RAM
- 20GB disk (not enough for 50GB files)
- 10-minute timeout (problematic)

### ✅ **Standard ($25/month)**: Recommended
- 2GB RAM ✅
- 100GB disk ✅
- 10-minute timeout (solved with chunking)

### 🚀 **Pro ($85/month)**: Optimal
- 8GB RAM ✅
- 1TB disk ✅
- Better performance

## 🔧 Deployment Steps

### 1. Prepare Repository
```bash
# Ensure these files exist:
- requirements.txt
- server.py
- main.py
- render_upload_endpoints.py
- templates/render_upload.html
- .env (with your credentials)
```

### 2. Deploy to Render
1. Connect GitHub repository to Render
2. Choose "Web Service"
3. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python server.py`
   - **Plan**: Standard ($25/month minimum)

### 3. Environment Variables
Add to Render dashboard:
```
MONGO_CONNECTION=mongodb+srv://...
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET_NAME=sylo-energy
PORT=10000
```

### 4. Custom Domain (Optional)
- Add custom domain in Render dashboard
- Update CORS settings if needed

## 🌐 Access URLs

After deployment:
- **Main App**: `https://your-app.onrender.com`
- **Chunked Upload**: `https://your-app.onrender.com/render-upload`
- **Health Check**: `https://your-app.onrender.com/health`

## ⚡ Render-Specific Optimizations

### 1. **Chunked Upload Strategy**
- 5MB chunks (optimized for Render)
- Each chunk uploads in <10 minutes
- Resume capability for failed chunks

### 2. **Memory Management**
```python
# Streaming upload to avoid memory issues
def save_streaming(self):
    with open(self.upload_path, 'wb') as f:
        while True:
            chunk = self.file_obj.read(CHUNK_SIZE)
            if not chunk:
                break
            f.write(chunk)
```

### 3. **Disk Space Management**
```python
# Automatic cleanup after S3 upload
def cleanup_local_file(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"Cleaned up: {file_path}")
```

## 📊 Performance Expectations on Render

### Upload Times (50GB file):
- **Home Internet (25 Mbps)**: 4-6 hours
- **Business (100 Mbps)**: 1-2 hours  
- **Fiber (1 Gbps)**: 15-30 minutes

### Render Benefits:
✅ **Global CDN**: Fast worldwide access
✅ **Auto-scaling**: Handles multiple uploads
✅ **SSL/HTTPS**: Automatic certificates
✅ **Monitoring**: Built-in logs and metrics

## 🔍 Troubleshooting

### Common Issues:
1. **Timeout errors**: Use chunked upload
2. **Memory errors**: Ensure streaming upload
3. **Disk space**: Monitor usage, cleanup old files
4. **S3 errors**: Verify AWS credentials

### Monitoring:
```bash
# Check app logs
render logs --service solar-plant-app

# Monitor disk usage
df -h /opt/render/project/src/uploads_data
```

## 💰 Cost Estimation

### Monthly Costs:
- **Render Standard**: $25/month
- **MongoDB Atlas**: $0-9/month (depends on usage)
- **AWS S3**: $1-5/month (for backup storage)
- **Total**: ~$26-39/month

## 🎯 Alternative: Hybrid Approach

For cost optimization:
1. **Render**: Host main application (Starter $7/month)
2. **AWS S3**: Direct upload for large files
3. **Frontend**: Direct-to-S3 upload with presigned URLs

This reduces Render disk usage and costs.

## 🚀 Ready to Deploy?

Your application is now Render-ready with:
- ✅ Chunked uploads for 50GB files
- ✅ Timeout handling
- ✅ Progress tracking
- ✅ S3 integration
- ✅ Database logging

Use the `/render-upload` endpoint for the optimized upload interface!
