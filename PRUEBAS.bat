@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title LSV principal - Pruebas OFFLINE
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m unittest discover -s tests -v
) else (
  py -3 -m unittest discover -s tests -v
)
if errorlevel 1 echo ERROR en pruebas. Ver salida.
pause
