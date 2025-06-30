# Large File Upload Guide (Up to 50GB)

## Overview
The thermal audit system now supports uploading files up to **50GB** via Google Drive integration with real-time progress tracking.

## Configuration Summary

### Server Configuration
- **Maximum File Size**: 50GB (53,687,091,200 bytes)
- **Socket Timeout**: 2 hours (7200 seconds)
- **Thread Stack Size**: 32KB for improved performance
- **Progress Tracking**: Real-time updates every 2 seconds
- **Upload Timeout**: 30 minutes with automatic retry

### File Types Supported
- **Visual Ortho GeoTIFF**: `.tiff`, `.tif` (Max 50GB)
- **Thermal Ortho GeoTIFF**: `.tiff`, `.tif` (Max 50GB)
- **Layout Files**: `.shp`, `.geojson`
- **ZIP Archives**: `.zip`
- **CSV Data**: `.csv`

## Google Drive Upload Process

### Prerequisites
1. **Google Drive Folder**: Must be publicly accessible
2. **File Naming**: Exact filename required (including extension)
3. **Plant & Audit**: Must be selected before upload
4. **Network**: Stable internet connection recommended

### Upload Steps
1. Navigate to `/data` (Data Upload page)
2. Select Plant and Audit from dropdowns
3. Enter Project Code
4. Choose file type (Visual/Thermal Ortho)
5. Paste Google Drive folder URL
6. Click "☁️ Upload from Google Drive"
7. Enter exact TIF filename when prompted
8. Monitor real-time progress

### Progress Tracking Features
- **Real-time Progress Bar**: Visual percentage complete
- **Stage Tracking**: Current operation (Downloading, Converting, Uploading)
- **Speed Monitor**: MB/s upload speed
- **ETA Display**: Estimated time remaining
- **Detailed Logs**: Step-by-step operation logs

### Upload Stages
1. **Validating**: Checking Google Drive folder access
2. **Downloading**: Downloading from Google Drive to server
3. **Converting**: Converting to Cloud Optimized GeoTIFF (COG)
4. **Uploading**: Uploading to AWS S3 cloud storage
5. **Cleaning**: Removing temporary files
6. **Completed**: Upload successful

## Technical Implementation

### Backend Processing
```python
# File size limit
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 * 1024  # 50 GB

# Timeout configuration
socket.setdefaulttimeout(7200)  # 2 hours

# Progress tracking
tracker = UploadProgressTracker(upload_id, filename, total_size)
```

### Frontend Progress Monitoring
```javascript
// Real-time progress updates
const response = await fetch(`/upload_progress/${currentUploadId}`);
const data = await response.json();

// Update UI elements
progressFill.style.width = `${percentage}%`;
statusElement.textContent = data.stage;
```

## Performance Optimizations

### Large File Handling
- **Chunked Processing**: 8MB chunks for memory efficiency
- **Streaming Upload**: Direct memory-to-cloud transfer
- **COG Conversion**: GDAL with DEFLATE compression
- **Background Processing**: Non-blocking upload operations

### Error Handling
- **Automatic Retry**: Failed chunks are retried
- **Progress Recovery**: Resume from last successful point
- **Detailed Logging**: Complete operation audit trail
- **Timeout Management**: Graceful handling of network issues

## Testing Large Files

### Recommended Test Scenarios
1. **Small File (< 100MB)**: Verify basic functionality
2. **Medium File (1-5GB)**: Test progress tracking
3. **Large File (10-20GB)**: Test timeout handling
4. **Very Large File (30-50GB)**: Full stress test

### Monitoring Tools
- **Browser Console**: JavaScript logs and errors
- **Server Logs**: Backend processing details
- **Progress API**: `/upload_progress/{upload_id}`
- **Network Monitor**: Browser DevTools Network tab

## Troubleshooting

### Common Issues
1. **File Not Found**: Check exact filename and Google Drive access
2. **Upload Timeout**: Verify network stability
3. **Progress Stuck**: Check server logs for errors
4. **Memory Issues**: Large files processed in chunks

### Error Recovery
- **Manual Retry**: Use same upload parameters
- **File Verification**: Ensure Google Drive accessibility
- **Server Restart**: If memory issues persist
- **Network Check**: Verify bandwidth and stability

## API Endpoints

### Upload Endpoints
- `POST /audi_tif/upload`: Start Google Drive upload
- `GET /upload_progress/{upload_id}`: Get progress status
- `GET /data`: Data upload page

### Response Format
```json
{
  "upload_id": "uuid-string",
  "status": "uploading|completed|failed",
  "stage": "downloading|converting|uploading",
  "progress_percentage": 45.5,
  "upload_speed_mbps": 12.3,
  "eta_seconds": 1800
}
```

## Security Considerations

### File Validation
- **Size Limits**: Enforced at multiple levels
- **Type Checking**: File extension validation
- **Virus Scanning**: Recommended for production
- **Access Control**: User authentication required

### Google Drive Security
- **Public Access**: Required for download
- **URL Validation**: Drive URL format checking
- **Rate Limiting**: Prevent abuse
- **Audit Trail**: Complete upload logging

## Deployment Notes

### Production Recommendations
1. **Load Balancer**: Handle multiple concurrent uploads
2. **CDN**: Improve download speeds
3. **Monitoring**: Real-time performance metrics
4. **Backup**: Automatic file backup to multiple locations
5. **Scaling**: Auto-scaling for peak usage

### Infrastructure Requirements
- **Storage**: Adequate disk space for temporary files
- **Memory**: Minimum 8GB RAM for large file processing
- **Network**: High-bandwidth connection
- **CPU**: Multi-core for parallel processing

---

**Note**: This system has been tested with files up to 50GB and provides robust error handling and progress tracking for thermal imaging workflows.
