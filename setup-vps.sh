#!/bin/bash
# VPS Setup Script for Solar Plant Management System
# Compatible with Ubuntu 20.04/22.04 LTS

echo "🌟 Setting up Solar Plant Management System on VPS"
echo "=================================================="

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install dependencies
echo "🔧 Installing system dependencies..."
sudo apt install -y python3 python3-pip python3-venv nginx git curl ufw

# Setup firewall
echo "🔥 Configuring firewall..."
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable

# Clone repository (replace with your actual repo)
echo "📥 Cloning application repository..."
cd /home/ubuntu
git clone https://github.com/your-username/solar-plant-manager.git
cd solar-plant-manager

# Setup Python environment
echo "🐍 Setting up Python environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create environment file
echo "⚙️  Creating environment configuration..."
cat > .env << EOL
MONGO_CONNECTION=YOUR_MONGODB_CONNECTION_STRING
bucket_name=sylo-energy
s3_prefix=https://sylo-energy.s3.ap-south-1.amazonaws.com
aws_access_key_id=YOUR_AWS_ACCESS_KEY_ID
aws_secret_access_key=YOUR_AWS_SECRET_ACCESS_KEY
region_name=ap-south-1
PORT=1211
EOL

# Create uploads directory
mkdir -p uploads_data

# Configure Nginx
echo "🌐 Configuring Nginx..."
sudo tee /etc/nginx/sites-available/solar-plant << 'EOF'
server {
    listen 80;
    server_name _;
    
    # Large file upload support
    client_max_body_size 50G;
    client_body_timeout 3600s;
    client_header_timeout 60s;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    proxy_request_buffering off;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    
    location / {
        proxy_pass http://127.0.0.1:1211;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Static files
    location /static/ {
        alias /home/ubuntu/solar-plant-manager/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Health check
    location /health {
        proxy_pass http://127.0.0.1:1211/health;
    }
}
EOF

# Enable site
sudo ln -sf /etc/nginx/sites-available/solar-plant /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t

# Create systemd service
echo "🔄 Creating system service..."
sudo tee /etc/systemd/system/solar-plant.service << EOF
[Unit]
Description=Solar Plant Management System
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/solar-plant-manager
Environment=PATH=/home/ubuntu/solar-plant-manager/.venv/bin
ExecStart=/home/ubuntu/solar-plant-manager/.venv/bin/python server.py
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Set permissions
sudo chown -R ubuntu:ubuntu /home/ubuntu/solar-plant-manager

# Start services
echo "🚀 Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable solar-plant
sudo systemctl start solar-plant
sudo systemctl restart nginx

# Install SSL certificate (optional)
echo "🔒 Installing SSL certificate..."
sudo apt install -y certbot python3-certbot-nginx
echo "To enable SSL, run: sudo certbot --nginx -d your-domain.com"

# Create backup script
echo "💾 Creating backup script..."
sudo tee /usr/local/bin/backup-solar-plant.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backup/solar-plant/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# Backup application files
tar -czf $BACKUP_DIR/app-backup.tar.gz -C /home/ubuntu solar-plant-manager

# Backup database (requires mongodump)
# mongodump --uri="$MONGO_CONNECTION" --out=$BACKUP_DIR/db-backup

echo "Backup completed: $BACKUP_DIR"
EOF

sudo chmod +x /usr/local/bin/backup-solar-plant.sh

# Create log rotation
sudo tee /etc/logrotate.d/solar-plant << 'EOF'
/home/ubuntu/solar-plant-manager/app.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF

# Display status
echo ""
echo "🎉 Installation Complete!"
echo "========================"
echo ""
echo "📊 Service Status:"
sudo systemctl status solar-plant --no-pager -l
echo ""
echo "🌐 Application URLs:"
echo "   HTTP:  http://$(curl -s ifconfig.me)"
echo "   Local: http://localhost"
echo ""
echo "🔧 Management Commands:"
echo "   Status:  sudo systemctl status solar-plant"
echo "   Restart: sudo systemctl restart solar-plant"
echo "   Logs:    sudo journalctl -u solar-plant -f"
echo "   Nginx:   sudo systemctl status nginx"
echo ""
echo "🔒 To enable HTTPS:"
echo "   sudo certbot --nginx -d your-domain.com"
echo ""
echo "💾 To backup:"
echo "   sudo /usr/local/bin/backup-solar-plant.sh"
echo ""
echo "✅ Your Solar Plant Management System is now live!"
echo "   Features: 50GB uploads, thermal imaging, full functionality"
