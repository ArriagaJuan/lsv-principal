@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set /p "COM_PORT=Indica el puerto COM de Arduino (ej. COM6): "
if not defined COM_PORT exit /b 1
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" diagnostico_arduino.py "%COM_PORT%"
) else (
  py -3 diagnostico_arduino.py "%COM_PORT%"
)
pause
