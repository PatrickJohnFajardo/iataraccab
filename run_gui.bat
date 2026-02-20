@echo off
TITLE Baccarat Bot V2
COLOR 0A
CLS

:: Check for virtual environment
IF NOT EXIST ".venv" (
    ECHO [ERROR] Virtual environment not found! 
    ECHO Please run 'setup.bat' first.
    PAUSE
    EXIT /B
)

:: Run using the venv python
ECHO Starting Baccarat Bot V2...
.\.venv\Scripts\python.exe main.py
IF %ERRORLEVEL% NEQ 0 (
    ECHO Bot crashed or was stopped.
    PAUSE
)
