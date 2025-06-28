#!/usr/bin/env python3
"""
Server startup script for Solar Plant Management System
"""
import os
import sys
from waitress import serve
import main

if __name__ == '__main__':
    print("Starting Solar Plant Management System...")
    print("Server will be available at: http://localhost:1211")
    print("Press Ctrl+C to stop the server")
    
    try:
        # Use waitress for Windows compatibility with optimized settings for large uploads
        serve(main.app, 
              host='0.0.0.0', 
              port=1211, 
              threads=8,                    # Increased threads for concurrent uploads
              connection_limit=1000,        # Maximum concurrent connections
              cleanup_interval=30,          # Connection cleanup interval
              channel_timeout=300,          # 5 minutes timeout for slow uploads
              max_request_header_size=65536, # 64KB headers for large metadata
              max_request_body_size=53687091200,  # 50GB maximum body size
              send_bytes=65536)             # Send buffer size
    except KeyboardInterrupt:
        print("\nServer stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)
