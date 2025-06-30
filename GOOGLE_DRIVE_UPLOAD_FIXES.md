# Google Drive Upload Error Fixes

## Common Error: "Cannot retrieve the public link of the file"

### Problem
The error occurs when:
- Google Drive file/folder doesn't have proper sharing permissions
- File is not accessible publicly
- Network connectivity issues
- Too many download attempts

### Solutions

#### 1. Fix Google Drive Permissions (Most Important)
```
Step 1: Open Google Drive in your browser
Step 2: Right-click on your file or folder
Step 3: Click "Share"
Step 4: Click "Change to anyone with the link"
Step 5: Ensure permission is set to "Viewer" or "Editor"
Step 6: Click "Copy link"
Step 7: Use this new link in the upload form
```

#### 2. Use Folder URLs Instead of File URLs
✅ **Correct**: `https://drive.google.com/drive/folders/1d3BzkHVSUh5dromR7w-f0PvD1JbBbpBq`
❌ **Incorrect**: `https://drive.google.com/file/d/1xPZTK5S0k8a1pSWs0t8vAIJyQ9M_Yqjo/view`

#### 3. Check File Name Exactly
- File name must match exactly (case-sensitive)
- Include the correct extension (.tif, .tiff)
- No extra spaces or special characters

#### 4. Network and Access Issues
- Clear browser cache and cookies
- Try from a different network/location
- Wait a few minutes between attempts
- Use incognito/private browsing mode

## Enhanced Error Handling Features

### 1. Multiple Download Methods
The system now tries 4 different download approaches:
```python
1. Standard gdown with fuzzy matching
2. gdown with cookies enabled  
3. Direct file ID download
4. Alternative URL format
```

### 2. Detailed Error Messages
- Shows exact cause of failure
- Lists available files in folder
- Provides step-by-step troubleshooting
- Includes file permission instructions

### 3. Better User Feedback
- Real-time progress updates
- Clear error descriptions
- Helpful alerts with solutions
- Visual troubleshooting guides

## File Size Limits

### Current Limits
- **Maximum File Size**: 50GB per file
- **Supported Formats**: .tif, .tiff, .zip, .shp, .geojson, .csv
- **Upload Timeout**: 30 minutes with retry
- **Network Timeout**: 2 hours for large files

### Performance Optimization
- Chunked processing (8MB chunks)
- Streaming uploads to cloud storage
- GDAL compression (COG format)
- Background processing

## Testing Your Upload

### Before Uploading
1. ✅ Check file permissions in Google Drive
2. ✅ Verify folder URL format
3. ✅ Confirm exact file name
4. ✅ Test with small file first
5. ✅ Ensure stable internet connection

### During Upload
- Monitor progress bar
- Check status messages  
- Watch for error alerts
- Keep browser tab active

### After Upload
- Verify file appears in audit
- Check S3 storage location
- Review upload logs
- Confirm file integrity

## Troubleshooting Checklist

### ❌ Upload Fails Immediately
- [ ] Check Google Drive permissions
- [ ] Verify URL format (folder vs file)
- [ ] Test URL in browser first
- [ ] Try with different file

### ❌ Upload Starts but Fails During Download
- [ ] Check internet connection stability
- [ ] Verify file exists in folder
- [ ] Check file name spelling/case
- [ ] Try smaller file first

### ❌ File Not Found Error
- [ ] Confirm exact file name
- [ ] Check file extension (.tif/.tiff)
- [ ] Verify file is in correct folder
- [ ] Look at available files list

### ❌ Permission Denied
- [ ] Change to "Anyone with the link"
- [ ] Use folder sharing instead of file
- [ ] Check organization restrictions
- [ ] Try different Google account

## API Error Responses

### Standard Error Format
```json
{
  "status": false,
  "error": "Error description",
  "upload_id": "unique-id",
  "troubleshooting": {
    "step1": "Right-click the file in Google Drive",
    "step2": "Click 'Share'",
    "step3": "Change permission to 'Anyone with the link'",
    "step4": "Copy the sharing link and try again"
  },
  "available_files": ["file1.tif", "file2.tif"],
  "total_files": 5
}
```

### Success Response Format
```json
{
  "status": true,
  "message": "File uploaded completed",
  "upload_id": "unique-id"
}
```

## Support and Debugging

### Log Files
- Server logs: `app.log`
- Browser console: F12 → Console tab
- Network logs: F12 → Network tab

### Contact Support
Include these details:
- Upload ID from error message
- Google Drive URL (sanitized)
- File name and size
- Error message text
- Browser and OS version

---

**Note**: Most upload issues are resolved by setting proper Google Drive permissions. Always start with the permission fix first.
