@echo off
chcp 65001 > nul 2>&1
echo ================================
echo   CMS Uploader
echo ================================
echo.

cd /d "%~dp0"
python bootstrap.py || pause && exit /b 1
python main.py
pause
