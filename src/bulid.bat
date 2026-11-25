#25/11/2026
@echo off
echo ====================================
echo   Compilazione StampaChiusura.exe
echo ====================================
call venv\Scripts\activate.bat
python -m PyInstaller --noconfirm --onefile --windowed ^
    --collect-all customtkinter ^
    --hidden-import=pywin32 ^
    --hidden-import=win32print ^
    --hidden-import=psycopg ^
    --hidden-import=psycopg_binary ^
    --name StampaChiusura main.py
echo.
echo ====================================
echo   FINE! File: dist\StampaChiusura.exe
echo ====================================
pause