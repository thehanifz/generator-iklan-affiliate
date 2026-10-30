@echo off
cd /d "%~dp0"
title Generator Iklan dan Affiliate

echo ========================================================
echo       Generator Iklan dan Affiliate
echo ========================================================

set "PY_EXE=.venv\Scripts\python.exe"

if not exist "%PY_EXE%" (
    echo [ERROR] Virtual environment tidak ditemukan di .venv
    echo Pastikan folder .venv sudah dibuat.
    echo.
    pause
    exit /b 1
)

echo Menjalankan aplikasi di http://localhost:5000/
echo Tekan Ctrl+C di jendela ini untuk mematikan server.
echo ========================================================
echo.

REM Buka browser otomatis setelah delay 2 detik
start /b "" cmd /c "ping -n 3 127.0.0.1 >nul & start http://localhost:5000/"

REM Jalankan aplikasi Flask dengan python dari .venv
"%PY_EXE%" app.py

echo.
echo ========================================================
echo Server telah dinonaktifkan.
echo ========================================================
pause
