#!/bin/bash
# Railway Deployment Script for Solar Plant Management System

echo "🚀 Deploying Solar Plant Management System to Railway..."
echo "=================================================="

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Installing..."
    npm install -g @railway/cli
fi

# Login to Railway
echo "🔐 Logging into Railway..."
railway login

# Initialize project
echo "📦 Initializing Railway project..."
railway init

# Set environment variables
echo "⚙️  Setting environment variables..."
railway variables set MONGO_CONNECTION "YOUR_MONGODB_CONNECTION_STRING"
railway variables set bucket_name "sylo-energy"
railway variables set s3_prefix "https://sylo-energy.s3.ap-south-1.amazonaws.com"
railway variables set aws_access_key_id "YOUR_AWS_ACCESS_KEY_ID"
railway variables set aws_secret_access_key "YOUR_AWS_SECRET_ACCESS_KEY"
railway variables set region_name "ap-south-1"
railway variables set PORT "1211"

# Deploy
echo "🚀 Deploying to Railway..."
railway up

echo "✅ Deployment complete!"
echo "🌐 Your application will be available at:"
railway domain

echo ""
echo "🎉 Your Solar Plant Management System is now live!"
echo "📋 Features available:"
echo "   • 50 GB file upload capacity"
echo "   • 18+ file format support"
echo "   • Full thermal imaging capabilities"
echo "   • MongoDB database integration"
echo "   • AWS S3 storage"
echo "   • User authentication"
echo "   • Plant and audit management"
