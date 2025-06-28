# File Upload Configuration - Solar Plant Management System

## Current Upload Capacity: **50 GB Maximum**

### Overview
The application has been optimized to handle very large thermal imaging and geospatial files with the following configuration:

## Technical Specifications

### Flask Application Limits
- **Maximum File Size**: 50 GB (53,687,091,200 bytes)
- **Previous Limit**: 10 GB 
- **Improvement**: 5x increase in upload capacity

### Server Configuration (Waitress)
- **Request Body Size**: 50 GB maximum
- **Timeout**: 5 minutes per chunk, 1 hour total upload
- **Threads**: 8 concurrent threads (increased from 4)
- **Connection Limit**: 1,000 concurrent connections
- **Header Size**: 64 KB for large metadata
- **Send Buffer**: 64 KB chunks for optimization

### Supported File Types
Enhanced support for multiple file formats:
- **Thermal Imaging**: `.tif`, `.tiff`
- **Geospatial**: `.geojson`, `.json`, `.kml`, `.kmz`
- **Shapefiles**: `.shp`, `.dbf`, `.shx`
- **Archives**: `.zip`, `.rar`
- **Data Files**: `.csv`, `.xlsx`
- **Images**: `.png`, `.jpg`, `.jpeg`
- **GPS Data**: `.gpx`, `.gps`

## Why 50 GB is the Practical Maximum

### Technical Reasons:

1. **Memory Constraints**
   - Large files require significant RAM for processing
   - 50 GB is safe for systems with 16-32 GB RAM
   - Prevents system instability from memory exhaustion

2. **Network Timeouts**
   - HTTP connections have practical limits
   - 50 GB uploads take 1-6 hours depending on speed
   - Configured 1-hour timeout balances usability vs reliability

3. **Storage Performance**
   - Writing 50+ GB files can stress disk I/O
   - Streaming upload with 8 MB chunks optimizes performance
   - Reduces disk fragmentation and improves reliability

4. **Database Limitations**
   - MongoDB has 16 MB document limit (metadata only)
   - Large files stored in GridFS or S3
   - 50 GB is well within S3's 5 TB object limit

5. **Browser Limitations**
   - Modern browsers can handle large uploads
   - JavaScript memory limits affect file processing
   - 50 GB is browser-safe for most systems

### Theoretical vs Practical Limits:

| Component | Theoretical Max | Practical Max | Our Setting |
|-----------|----------------|---------------|-------------|
| Flask | No hard limit | System memory dependent | 50 GB |
| Waitress | Configurable | System resources | 50 GB |
| MongoDB GridFS | 16 MB per chunk | Multiple TB total | 50 GB files |
| AWS S3 | 5 TB per object | Network dependent | 50 GB |
| NTFS (Windows) | 256 TB | Disk space | 50 GB |
| Browser | Varies | RAM dependent | 50 GB |

## Upload Optimization Features

### Streaming Upload
- Files uploaded in 8 MB chunks
- Reduces memory usage during upload
- Allows progress tracking
- Enables resume capability (if implemented)

### Concurrent Processing
- 8 threads handle multiple uploads
- Non-blocking I/O operations
- Improved user experience

### Error Handling
- Automatic cleanup of partial uploads
- Timeout detection and recovery
- File size validation during upload

### Monitoring
- Upload progress tracking
- File size conversion (bytes → MB → GB)
- Performance metrics logging

## Increasing Beyond 50 GB

If you need larger uploads, consider:

### 1. Infrastructure Changes
```python
# Increase to 100 GB (requires more RAM)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 * 1024

# Increase timeout to 2 hours
max_request_body_size = 107374182400  # 100 GB
channel_timeout = 7200  # 2 hours
```

### 2. Alternative Approaches
- **Chunked Upload**: Split large files into smaller pieces
- **Resumable Uploads**: Allow pausing and resuming
- **Direct S3 Upload**: Bypass server using pre-signed URLs
- **Background Processing**: Use Celery for async uploads

### 3. System Requirements
- **RAM**: 32+ GB recommended for 100+ GB files
- **Storage**: Fast SSD with ample free space
- **Network**: Stable high-speed connection
- **Bandwidth**: Consider data transfer costs

## Web Server Recommendations

### For Production Deployment:

#### Nginx Configuration
```nginx
client_max_body_size 50G;
client_body_timeout 3600s;
proxy_read_timeout 3600s;
proxy_request_buffering off;
```

#### Apache Configuration
```apache
LimitRequestBody 53687091200
TimeOut 3600
```

#### IIS Configuration
```xml
<requestLimits maxAllowedContentLength="53687091200" />
<httpRuntime maxRequestLength="52428800" executionTimeout="3600" />
```

## Performance Monitoring

### Key Metrics to Track:
- Upload success rate
- Average upload time per GB
- Server memory usage during uploads
- Network bandwidth utilization
- Error rates and types

### Recommended Tools:
- Application logs (built-in)
- System monitoring (CPU, RAM, Disk)
- Network monitoring
- AWS CloudWatch for S3 operations

## Security Considerations

### File Validation:
- File type verification
- Virus scanning (recommended for production)
- Content validation for known formats
- Size limit enforcement

### Access Control:
- User authentication required
- Upload permissions per user role
- Audit trail for file operations
- Secure file storage locations

## Conclusion

**50 GB is the optimal maximum file size** for this application because it:
- Balances functionality with system stability
- Works reliably across different hardware configurations
- Stays within practical network timeout limits
- Provides excellent performance for thermal imaging workflows
- Leaves room for system overhead and concurrent operations

For files larger than 50 GB, consider splitting them or using specialized transfer tools before uploading to the system.
