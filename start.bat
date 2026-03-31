@echo off
title Zagadat Capital Fund Management System
color 0A
echo.
echo  ============================================================
echo   ZAGADAT CAPITAL — Fund Management System
echo  ============================================================
echo.

cd /d "%~dp0"

REM ── CHECK PYTHON ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Install Python 3.9+ from python.org
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo  [OK] %%i

REM ── VIRTUAL ENVIRONMENT ───────────────────────────────────────────────────
if not exist venv (
    echo  Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat 2>nul

REM ── DEPENDENCIES ──────────────────────────────────────────────────────────
echo  Installing / checking dependencies...
pip install flask flask-sqlalchemy flask-login flask-bcrypt flask-cors flask-mail ^
    reportlab pillow requests beautifulsoup4 lxml openpyxl python-dateutil --quiet 2>nul
echo  [OK] Dependencies ready

REM ── CREATE FOLDERS ────────────────────────────────────────────────────────
if not exist uploads               mkdir uploads
if not exist uploads\signatures    mkdir uploads\signatures
if not exist uploads\documents     mkdir uploads\documents
if not exist uploads\photos        mkdir uploads\photos

echo.
echo  ============================================================
echo   URL:           http://127.0.0.1:5000
echo.
echo   ADMIN LOGIN:   Staff ID:  SA001
echo                  Password:  ZagadatAdmin@2026
echo.
echo   CLIENT LOGIN:  Account:   ZC-00001
echo                  Phone:     0244000001
echo.
echo   NEW CLIENT:    http://127.0.0.1:5000/signup
echo.
echo   Press Ctrl+C to stop
echo  ============================================================
echo.

start "" http://127.0.0.1:5000
python app.py

pause
