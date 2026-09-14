@echo off
title Smart Web-Printchi Server
chcp 65001 > nul
cls

echo =======================================================
echo          🖨️ SMART WEB-PRINTCHI SERVERI 🖨️
echo =======================================================
echo.

cd /d "%~dp0"

:: Virtual muhitni tekshirish
if not exist ".venv\Scripts\python.exe" (
    echo [!] Virtual muhit topilmadi. Yaratilmoqda...
    if exist "%USERPROFILE%\.local\bin\uv.exe" (
        "%USERPROFILE%\.local\bin\uv.exe" venv .venv
        "%USERPROFILE%\.local\bin\uv.exe" pip install -r requirements.txt
    ) else (
        python -m venv .venv
        .venv\Scripts\pip.exe install -r requirements.txt
    )
)

echo [*] Server ishga tushmoqda...
echo [*] Lokal manzil: http://localhost:5000
echo [*] Netlify sayt: https://smart-printx.netlify.app
echo.
echo =======================================================
echo   Serverni to'xtatish uchun: Ctrl + C tugmalarini bosing
echo =======================================================
echo.

:: Serverni ishga tushirish
".venv\Scripts\python.exe" app.py

pause
