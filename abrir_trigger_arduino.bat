@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecuta ejecutar.bat para instalar el entorno y pyserial.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "arduino\trigger_ttl_gui.py"
if errorlevel 1 pause
