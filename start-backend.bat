@echo off
echo Starting IT BOM Backend Server...
echo.
echo Backend will run at: http://localhost:8001
echo API docs will be at: http://localhost:8001/docs
echo.
cd backend
python -m uvicorn main:app --reload --port 8001
