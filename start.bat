@echo off
echo ========================================
echo   OCR Application - Quick Start
echo ========================================
echo.

echo [1/2] Starting Backend Server...
start cmd /k "cd backend && python app.py"
timeout /t 3 /nobreak > nul

echo [2/2] Starting Frontend Server...
start cmd /k "cd frontend && npm run dev"

echo.
echo ========================================
echo   Servers Starting...
echo ========================================
echo.
echo Backend:  http://localhost:3000
echo Frontend: http://localhost:5173
echo.
echo Press any key to exit this window...
pause > nul
