@echo off
TITLE Baccarat Bot Headless
COLOR 0E
CLS

:: Check for virtual environment
IF NOT EXIST ".venv" (
    ECHO [ERROR] Virtual environment not found! 
    ECHO Please run 'setup.bat' first.
    PAUSE
    EXIT /B
)

:: Run using the venv python
ECHO Starting Baccarat Bot in Headless Mode...
.\.venv\Scripts\python.exe main.py --headless
IF %ERRORLEVEL% NEQ 0 (
    ECHO Bot crashed or was stopped.
    PAUSE
)
