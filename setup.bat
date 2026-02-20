@echo off
TITLE Baccarat Bot Setup
COLOR 0B
CLS

ECHO ======================================================
ECHO      Baccarat Bot - Automatic Setup Script
ECHO ======================================================
ECHO.

:: 1. Check if Python is installed
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO [ERROR] Python is not installed or not in your PATH.
    ECHO.
    ECHO Please install Python 3.10+ from python.org
    ECHO IMPORTANT: Check "Add Python to PATH" during install.
    ECHO.
    PAUSE
    EXIT /B
)

:: 2. Create Virtual Environment
IF NOT EXIST ".venv" (
    ECHO [INFO] Creating virtual environment (.venv)...
    python -m venv .venv
    IF %ERRORLEVEL% NEQ 0 (
        ECHO [ERROR] Failed to create virtual environment. 
        PAUSE
        EXIT /B
    )
) ELSE (
    ECHO [INFO] Virtual environment already exists.
)

:: 3. Install Requirements
ECHO [INFO] Installing/Upgrading dependencies...
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

:: 4. Verify Tesseract
IF NOT EXIST "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    ECHO.
    ECHO [WARNING] Tesseract OCR not found at default location!
    ECHO Please install Tesseract-OCR to:
    ECHO C:\Program Files\Tesseract-OCR\
    ECHO.
)

:: 5. Done
ECHO.
ECHO ======================================================
ECHO      Setup Complete! 
ECHO      You can now run 'run_gui.bat'
ECHO ======================================================
PAUSE
