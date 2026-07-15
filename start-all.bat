@echo off
setlocal
set ROOT=%~dp0

echo ========================================
echo   IT BOM Creation System
echo ========================================
echo.
echo   Backend  : http://localhost:8001
  echo   Frontend : http://localhost:5173
  echo   API Docs : http://localhost:8001/api/docs
echo.
echo   Starting both servers...
echo ========================================
echo.

REM Install backend deps if needed
if not exist "%ROOT%backend\__pycache__" (
    echo [1/4] Installing backend dependencies...
    cd /d "%ROOT%backend" && pip install -r requirements.txt --quiet
)

REM Install frontend deps if needed
if not exist "%ROOT%frontend\node_modules" (
    echo [2/4] Installing frontend dependencies...
    cd /d "%ROOT%frontend" && npm install --silent
)

REM Start backend in new window
echo [3/4] Starting backend (FastAPI)...
start "IT-BOM Backend" cmd /k "cd /d "%ROOT%backend" && python -m uvicorn main:app --reload --port 8001"

REM Wait for backend to initialize
timeout /t 3 /nobreak > nul

REM Start frontend in new window
echo [4/4] Starting frontend (Vite + React)...
start "IT-BOM Frontend" cmd /k "cd /d "%ROOT%frontend" && npm run dev"

echo.
echo Both servers are running in separate windows.
echo Close those windows to stop the servers.
echo.
echo Opening browser in 3 seconds...
timeout /t 3 /nobreak > nul
start http://localhost:5173

endlocal
