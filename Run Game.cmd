@echo off
setlocal
cd /d "%~dp0"
if exist "HowHotAreYou.exe" (
    "HowHotAreYou.exe" %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py %*
) else (
    echo First run setup.ps1 using PowerShell. See README.md for setup instructions.
    pause
    exit /b 1
)
set "gameExit=%errorlevel%"
if not "%gameExit%"=="0" pause
exit /b %gameExit%
