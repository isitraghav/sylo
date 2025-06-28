#!/usr/bin/env python3
"""
Render-compatible server startup script
Alternative to server.py that works without waitress
"""
import os
import sys
from main import app

if __name__ == '__main__':
    # Get port from environment (Render sets this automatically)
    port = int(os.environ.get('PORT', 10000))
    
    print(f"🚀 Starting Solar Plant Management System on port {port}...")
    print(f"📱 Server will be available at: http://0.0.0.0:{port}")
    print("⏹️  Press Ctrl+C to stop the server")
    
    try:
        # Use Flask's built-in server (suitable for Render)
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,                    # Disable debug in production
            use_reloader=False,             # Disable auto-reload
            use_debugger=False,             # Disable debugger
            use_evalex=False,               # Disable code evaluation
            threaded=True                   # Enable threading for concurrent requests
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)
