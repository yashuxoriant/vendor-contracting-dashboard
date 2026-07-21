@echo off
echo Starting IT BOM Backend Server...
echo.
echo Backend will run at: http://localhost:8000
echo API docs will be at: http://localhost:8000/api/docs
echo.
cd backend
"C:\Users\singh_y\workspace\ma-workstream-planner\.venv\Scripts\python.exe" -m uvicorn main:app --reload --port 8000
