# Solar Plant Management System

A comprehensive web application for managing solar plant audits, monitoring, and data analysis.

## Features

- **Plant Management**: Add, view, and manage solar plant installations
- **Audit System**: Comprehensive audit management with data upload capabilities
- **Data Analysis**: Analytics and reporting for solar plant performance
- **User Authentication**: Secure login system
- **File Upload**: Support for thermal imagery and geospatial data (TIF, GeoJSON)
- **Large File Support**: Up to 50 GB file uploads with streaming optimization
- **Enhanced File Types**: Support for 18+ file formats including TIF, GeoJSON, ZIP, CSV, KML
- **AWS S3 Integration**: Cloud storage for audit data and images
- **MongoDB Database**: Robust data storage and retrieval

## Quick Start

### Prerequisites
- Python 3.11+ 
- MongoDB Atlas account (free tier available)
- AWS S3 account for file storage

### Installation & Running

1. **Virtual Environment**: Already configured at `.venv/`
2. **Dependencies**: All packages installed via requirements.txt
3. **Configuration**: Environment variables configured in `.env`

### Run the Application

#### Option 1: Production Server (Recommended)
```bash
python server.py
```
Access at: http://localhost:1211

#### Option 2: Development Server
```bash
python main.py
```
Access at: http://localhost:3333

#### Option 3: Windows Batch File
```bash
start_server.bat
```

## Environment Setup (Already Done)

✅ Virtual environment created
✅ Dependencies installed
✅ MongoDB configured
✅ AWS S3 configured
✅ Application tested and running
✅ **NEW**: 50 GB maximum file upload capacity
✅ **NEW**: Enhanced file type support (18+ formats)
✅ **NEW**: Streaming upload optimization

## API Endpoints

### Authentication
- `GET/POST /login` - User login
- `POST /api/v1.0/register` - User registration

### Plant Management
- `GET/POST /api/plants` - List/Create plants

### Audit Management
- `POST /api/audits` - Create new audit
- `POST /api/upload` - Upload audit files
- `POST /audi_tif/upload` - Upload TIF files

## File Upload Capabilities

### Maximum File Size: **50 GB**
- Optimized for large thermal imaging and geospatial files
- Streaming upload with 8 MB chunks for reliability
- 1-hour timeout for large file transfers
- 8 concurrent upload threads

### Supported File Types (18+ formats):
- **Thermal Imaging**: `.tif`, `.tiff`
- **Geospatial**: `.geojson`, `.json`, `.kml`, `.kmz`
- **Archives**: `.zip`, `.rar`
- **Data Files**: `.csv`, `.xlsx`
- **Shapefiles**: `.shp`, `.dbf`, `.shx`
- **Images**: `.png`, `.jpg`, `.jpeg`
- **GPS Data**: `.gpx`, `.gps`

### Performance Features:
- Chunked streaming for memory efficiency
- Progress tracking and error recovery
- Concurrent upload processing
- Automatic file validation

📋 **For detailed upload specifications, see**: `UPLOAD_CAPACITY.md`

## Configuration

Environment variables in `.env`:
```env
MONGO_CONNECTION=mongodb+srv://...
bucket_name=sylo-energy
s3_prefix=https://sylo-energy.s3.ap-south-1.amazonaws.com
PORT=1211
```

## Docker (Original)
```bash
docker compose up -d --build
```

## Support
- Developer: Dharmendra Bajiya
- Email: bajiya2024@gmail.com
- Contact: +91-9785540104