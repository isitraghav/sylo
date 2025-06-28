@echo off
REM Railway Deployment Script for Windows
echo 🚀 Deploying Solar Plant Management System to Railway...
echo ==================================================

REM Check if Node.js is installed
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ❌ Node.js not found. Please install Node.js first.
    echo Download from: https://nodejs.org/
    pause
    exit /b 1
)

REM Install Railway CLI
echo 📦 Installing Railway CLI...
npm install -g @railway/cli

REM Login to Railway
echo 🔐 Logging into Railway...
railway login

REM Initialize project
echo 📦 Initializing Railway project...
railway init

REM Set environment variables
echo ⚙️  Setting environment variables...
railway variables set MONGO_CONNECTION "YOUR_MONGODB_CONNECTION_STRING"
railway variables set bucket_name "sylo-energy"
railway variables set s3_prefix "https://sylo-energy.s3.ap-south-1.amazonaws.com"
railway variables set aws_access_key_id "YOUR_AWS_ACCESS_KEY_ID"
railway variables set aws_secret_access_key "YOUR_AWS_SECRET_ACCESS_KEY"
railway variables set region_name "ap-south-1"
railway variables set PORT "1211"

REM Deploy
echo 🚀 Deploying to Railway...
railway up

echo ✅ Deployment complete!
echo 🌐 Getting your application URL...
railway domain

echo.
echo 🎉 Your Solar Plant Management System is now live!
echo 📋 Features available:
echo    • 50 GB file upload capacity
echo    • 18+ file format support
echo    • Full thermal imaging capabilities
echo    • MongoDB database integration
echo    • AWS S3 storage
echo    • User authentication
echo    • Plant and audit management

pause
