@echo off
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
  echo Python wurde nicht gefunden. Bitte von https://www.python.org installieren
  echo und dabei "Add Python to PATH" anhaken.
  pause
  exit /b 1
)
python -m pip install --upgrade pyinstaller
python -m PyInstaller --onefile --windowed --name ZyroClient zyroclient.py
echo.
echo Fertig! Deine Datei liegt in: dist\ZyroClient.exe
pause
