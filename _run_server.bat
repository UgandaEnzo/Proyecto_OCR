@echo off
set PYTHONIOENCODING=utf-8
start /B C:\Users\NigherS\Documents\proyecto\.venv_build\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8001
echo Server starting at http://localhost:8001
