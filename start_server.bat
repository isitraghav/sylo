@echo off
echo Starting Solar Plant Management System...
cd /d "d:\syloProject\thermalClient-master (4)\thermalClient-master"
"D:/syloProject/thermalClient-master (4)/thermalClient-master/.venv/Scripts/python.exe" -c "from waitress import serve; import main; serve(main.app, host='0.0.0.0', port=1211)"
pause
