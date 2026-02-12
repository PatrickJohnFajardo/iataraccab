@echo off
TITLE Baccarat Bot Setup
CLS

ECHO ======================================================
ECHO      Baccarat Bot - Automatic Setup Script
ECHO ======================================================
ECHO.

:: 1. Check if Python is installed
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO [ERROR] Python is not installed or not in your PATH.
    ECHO Please install Python 3.10+ and try again.
    PAUSE
    EXIT /B
)

:: 2. Create Virtual Environment if it doesn't exist
IF NOT EXIST ".venv" (
    ECHO [INFO] Creating virtual environment (.venv)...
    python -m venv .venv
) ELSE (
    ECHO [INFO] Virtual environment already exists.
)

:: 3. Upgrade pip and install requirements
ECHO [INFO] Installing/Upgrading dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

:: 4. Done
ECHO.
ECHO ======================================================
ECHO      Setup Complete! 
ECHO      You can now run 'run_gui.bat' (to be created)
ECHO ======================================================
PAUSE
