@echo off
setlocal
title TDL Music Launcher
cd /d "%~dp0"

set "PYTHON=venv\Scripts\python.exe"
set "PYTHONW=venv\Scripts\pythonw.exe"

if not exist "%PYTHON%" (
    echo [TDL Music] First run detected. Creating virtual environment...
    where py >nul 2>nul
    if errorlevel 1 (
        python -m venv venv
    ) else (
        py -3 -m venv venv
    )
    if errorlevel 1 goto :setup_failed
)

"%PYTHON%" -c "import customtkinter, aiohttp, aiofiles, mutagen, imageio_ffmpeg, PIL, yt_dlp" >nul 2>nul
if errorlevel 1 (
    echo [TDL Music] Installing dependencies. This may take a minute...
    "%PYTHON%" -m pip install --upgrade pip
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 goto :setup_failed
    "%PYTHON%" -c "import customtkinter, aiohttp, aiofiles, mutagen, imageio_ffmpeg, PIL, yt_dlp" >nul 2>nul
    if errorlevel 1 goto :setup_failed
)

start "" "%PYTHONW%" "main.py"
exit /b 0

:setup_failed
echo.
echo [TDL Music] Setup failed. Install Python 3.8+ and check your internet connection, then try again.
pause
exit /b 1
