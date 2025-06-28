
module.exports = {
  apps: [{
    name: 'sy_main',
    script: 'gunicorn',  // Use Gunicorn instead of Python directly
    args: '--workers 4 --bind 0.0.0.0:1211 --timeout 60000 main:app',  // Key changes
    interpreter: 'python3',
    watch: false,  // Disable file watching
    ignore_watch: ['uploads_data', 'audits/**', '*.log'],  // Ignore uploads and logs
    env: {
      NODE_ENV: 'production',
      FLASK_DEBUG: 'production',
    }
  }]
}