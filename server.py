#!/usr/bin/env python3
"""
Server startup script for Solar Plant Management System
"""
import os
import sys

# Try to import waitress, fallback to Flask's built-in server
try:
    from waitress import serve
    WAITRESS_AVAILABLE = True
except ImportError:
    WAITRESS_AVAILABLE = False
    print("⚠️  Waitress not available, using Flask's built-in server")

import main

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 1211))
    
    print("🚀 Starting Solar Plant Management System...")
    print(f"📱 Server will be available at: http://0.0.0.0:{port}")
    print("⏹️  Press Ctrl+C to stop the server")
    
    try:
        if WAITRESS_AVAILABLE:
            # Use waitress for production (Windows-friendly)
            print("🔧 Using Waitress production server")
            serve(main.app, 
                  host='0.0.0.0', 
                  port=port, 
                  threads=8,                    # Increased threads for concurrent uploads
                  connection_limit=1000,        # Maximum concurrent connections
                  cleanup_interval=30,          # Connection cleanup interval
                  channel_timeout=300,          # 5 minutes timeout for slow uploads
                  max_request_header_size=65536, # 64KB headers for large metadata
                  max_request_body_size=53687091200,  # 50GB maximum body size
                  send_bytes=65536)             # Send buffer size
        else:
            # Fallback to Flask's built-in server
            print("🔧 Using Flask's built-in server")
            main.app.run(
                host='0.0.0.0',
                port=port,
                debug=False,
                use_reloader=False,
                use_debugger=False,
                use_evalex=False,
                threaded=True
            )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)
