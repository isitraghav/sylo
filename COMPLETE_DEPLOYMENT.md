# Complete Deployment Guide - Solar Plant Management System
# Full Features with 50GB Upload Support

## 🎯 Best Deployment Options (No Limitations)

### Option 1: Railway (Recommended - Easiest)
**Perfect for your 50GB file uploads and full Flask features**

#### Why Railway?
- ✅ Supports 50GB file uploads
- ✅ No timeout limitations
- ✅ Persistent storage
- ✅ Automatic HTTPS
- ✅ Easy deployment
- ✅ $5-20/month
- ✅ Full Python/Flask support

#### Deploy Steps:
```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Initialize in your project directory
railway init

# 4. Deploy
railway up
```

#### Set Environment Variables:
```bash
railway variables set MONGO_CONNECTION "YOUR_MONGODB_CONNECTION_STRING"
railway variables set bucket_name "sylo-energy"
railway variables set s3_prefix "https://sylo-energy.s3.ap-south-1.amazonaws.com"
railway variables set aws_access_key_id "YOUR_AWS_ACCESS_KEY_ID"
railway variables set aws_secret_access_key "YOUR_AWS_SECRET_ACCESS_KEY"
railway variables set region_name "ap-south-1"
railway variables set PORT "1211"
```

### Option 2: DigitalOcean App Platform
**Professional grade with full control**

#### Create app.yaml:
```yaml
name: solar-plant-manager
services:
- name: web
  source_dir: /
  github:
    repo: your-username/your-repo
    branch: main
  run_command: python server.py
  environment_slug: python
  instance_count: 1
  instance_size_slug: basic-xs
  routes:
  - path: /
  envs:
  - key: MONGO_CONNECTION
    value: "your-mongo-connection"
  - key: bucket_name
    value: "sylo-energy"
```

### Option 3: VPS Deployment (Maximum Control)
**Best for heavy usage and complete customization**

#### Recommended VPS Providers:
1. **DigitalOcean Droplet** - $10-20/month
2. **Linode** - $10-20/month  
3. **Vultr** - $10-20/month
4. **Hetzner** - $5-15/month (Europe)

#### VPS Setup Script:
```bash
# Ubuntu 22.04 LTS setup
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv nginx git -y

# Clone your repository
git clone https://github.com/your-username/thermalClient-master.git
cd thermalClient-master

# Setup Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure Nginx
sudo tee /etc/nginx/sites-available/solar-plant << 'EOF'
server {
    listen 80;
    server_name your-domain.com;
    client_max_body_size 50G;
    client_body_timeout 3600s;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    
    location / {
        proxy_pass http://127.0.0.1:1211;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_request_buffering off;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/solar-plant /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Setup systemd service
sudo tee /etc/systemd/system/solar-plant.service << 'EOF'
[Unit]
Description=Solar Plant Management System
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/thermalClient-master
Environment=PATH=/home/ubuntu/thermalClient-master/.venv/bin
ExecStart=/home/ubuntu/thermalClient-master/.venv/bin/python server.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Start service
sudo systemctl daemon-reload
sudo systemctl enable solar-plant
sudo systemctl start solar-plant
```

### Option 4: Docker + Cloud Deployment

#### Create Production Dockerfile:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create directories
RUN mkdir -p uploads_data static/images

# Set environment
ENV FLASK_ENV=production
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=30s \
    CMD curl -f http://localhost:1211/ || exit 1

EXPOSE 1211
CMD ["python", "server.py"]
```

#### Deploy to Google Cloud Run:
```bash
# Build and deploy
gcloud builds submit --tag gcr.io/PROJECT-ID/solar-plant
gcloud run deploy solar-plant \
  --image gcr.io/PROJECT-ID/solar-plant \
  --platform managed \
  --memory 4Gi \
  --timeout 3600s \
  --max-instances 10
```

## 🚀 Quick Start - Railway Deployment (5 Minutes)

Since Railway is the easiest and supports all your features:

### Step 1: Prepare Your Repository
```bash
# Ensure your code is in a Git repository
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/your-username/solar-plant-manager.git
git push -u origin main
```

### Step 2: Deploy to Railway
1. Go to https://railway.app
2. Sign up with GitHub
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your repository
5. Railway will auto-detect Python and deploy

### Step 3: Configure Environment Variables
In Railway dashboard:
- Go to Variables tab
- Add all your environment variables from .env file

### Step 4: Custom Domain (Optional)
- Go to Settings → Domains
- Add your custom domain
- Railway provides free subdomain: `your-app.railway.app`

## 🌐 Live Demo URLs

After deployment, your application will be available at:
- **Railway**: `https://your-app.railway.app`
- **DigitalOcean**: `https://your-domain.com`
- **VPS**: `http://your-server-ip` or custom domain
- **Cloud Run**: `https://solar-plant-xxxxx.run.app`

## 📊 Feature Comparison

| Platform | Cost/Month | Setup Time | File Upload | Custom Domain | Scalability |
|----------|------------|------------|-------------|---------------|-------------|
| Railway | $5-20 | 5 minutes | 50GB ✅ | Free ✅ | Auto ✅ |
| DigitalOcean | $10-25 | 15 minutes | 50GB ✅ | Included ✅ | Manual |
| VPS | $10-20 | 30 minutes | Unlimited ✅ | Extra cost | Manual |
| Cloud Run | $10-30 | 20 minutes | 50GB ✅ | Free ✅ | Auto ✅ |

## 🔧 Production Optimizations

### SSL Certificate (Free)
Most platforms provide automatic HTTPS. For VPS:
```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### Database Backup
```bash
# MongoDB backup script
mongodump --uri="your-mongo-connection" --out=/backup/$(date +%Y%m%d)
```

### Log Monitoring
```bash
# Setup log rotation
sudo tee /etc/logrotate.d/solar-plant << 'EOF'
/home/ubuntu/thermalClient-master/app.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
}
EOF
```

## 🎯 Recommended Deployment Path

**For immediate deployment with zero limitations:**

1. **Start with Railway** (5 minutes deployment)
   - Perfect for testing and immediate live demo
   - All features work out of the box
   - Free tier available

2. **Scale to VPS later** (if needed)
   - When you need more control
   - Custom configurations
   - Higher traffic volumes

## 📞 Support & Monitoring

### Health Check Endpoint
Add to your main.py:
```python
@app.route('/health')
def health_check():
    return {'status': 'healthy', 'timestamp': datetime.now().isoformat()}
```

### Monitoring Services
- **Uptime Robot** - Free uptime monitoring
- **New Relic** - Application performance
- **DataDog** - Comprehensive monitoring

Would you like me to help you deploy to Railway right now? It's the fastest way to get your application live with all features intact!
