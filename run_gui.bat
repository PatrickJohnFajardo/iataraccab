@echo off
TITLE Baccarat Bot V2
CLS

:: Check for virtual environment
IF NOT EXIST ".venv" (
    ECHO [ERROR] Virtual environment not found! 
    ECHO Please run 'setup.bat' first.
    PAUSE
    EXIT /B
)

:: Activate and Run
ECHO Starting Baccarat Bot V2...
call .venv\Scripts\activate.bat
python gui.py
PAUSE
