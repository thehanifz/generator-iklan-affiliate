@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Generator Iklan dan Affiliate

echo ========================================================
echo       Generator Iklan dan Affiliate
echo ========================================================
echo.

REM 1. Deteksi executable Python
set "PYTHON_EXE="

python --version >nul 2>&1
if not errorlevel 1 (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
        goto :found_python
    )
)

py --version >nul 2>&1
if not errorlevel 1 (
    py -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        goto :found_python
    )
)

if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
    goto :found_python
)

if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    goto :found_python
)

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :found_python
)

if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :found_python
)

if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    goto :found_python
)

if exist "C:\Python312\python.exe" (
    set "PYTHON_EXE=C:\Python312\python.exe"
    goto :found_python
)

if exist "C:\Python311\python.exe" (
    set "PYTHON_EXE=C:\Python311\python.exe"
    goto :found_python
)

if exist "C:\Program Files\Python312\python.exe" (
    set "PYTHON_EXE=C:\Program Files\Python312\python.exe"
    goto :found_python
)

if not defined PYTHON_EXE (
    echo [ERROR] Python tidak ditemukan di sistem Windows Anda!
    echo Silakan install Python dari https://www.python.org/downloads/
    echo dan pastikan centang opsi "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

:found_python
echo [OK] Python ditemukan: %PYTHON_EXE%
echo.

REM 2. Tentukan folder venv (.venv atau venv)
set "VENV_DIR=.venv"
if exist "venv\Scripts\activate.bat" (
    set "VENV_DIR=venv"
)

REM 3. Cek apakah venv sudah ada, jika belum buat venv baru
if exist "%VENV_DIR%\Scripts\activate.bat" goto :venv_ready

echo [SETUP] Virtual environment (%VENV_DIR%) belum ada.
echo [SETUP] Sedang membuat virtual environment baru, mohon tunggu sebentar...
"%PYTHON_EXE%" -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo.
    echo [ERROR] Gagal membuat virtual environment di folder %VENV_DIR%!
    pause
    exit /b 1
)
echo [OK] Virtual environment (%VENV_DIR%) berhasil dibuat.
echo.

:venv_ready
REM 4. Aktifkan virtual environment
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Gagal mengaktifkan virtual environment!
    pause
    exit /b 1
)
echo [OK] Virtual environment (%VENV_DIR%) aktif.

REM 5. Cek dependencies (bila belum ada install, bila ada skip)
python -c "import flask; import playwright; import greenlet" >nul 2>&1
if not errorlevel 1 goto :deps_ready

echo [SETUP] Memperbarui pip ke versi terbaru...
python -m pip install --upgrade pip

echo [SETUP] Menginstal dependensi dari requirements.txt, mohon tunggu...
python -m pip install --prefer-binary -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Gagal menginstal dependensi dari requirements.txt!
    pause
    exit /b 1
)
echo [OK] Seluruh dependensi berhasil diinstal.
echo.

:deps_ready
echo [OK] Dependensi sudah lengkap. Melewati instalasi pip.
echo.

REM 6. Cek file .env
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [OK] File .env berhasil dibuat dari .env.example.
    )
)

REM 7. Bersihkan proses lama di port 5000 jika ada
for /f "tokens=5" %%a in ('netstat -a -n -o ^| findstr :5000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

echo ========================================================
echo Menjalankan aplikasi di http://localhost:5000/
echo Tekan Ctrl+C di jendela ini untuk mematikan server.
echo ========================================================
echo.

REM 8. Buka browser otomatis setelah delay 2-3 detik
start /b "" cmd /c "ping -n 3 127.0.0.1 >nul & start http://localhost:5000/"

REM 9. Jalankan aplikasi Flask
python app.py

echo.
echo ========================================================
echo Server telah dinonaktifkan.
echo ========================================================
pause
