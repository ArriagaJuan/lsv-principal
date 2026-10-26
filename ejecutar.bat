@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title LSV Principal - Arduino TTL V1
set "PY_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    for %%V in (3.11 3.12 3.13 3.10) do (
        if not defined PY_CMD (
            py -%%V --version >nul 2>nul
            if not errorlevel 1 set "PY_CMD=py -%%V"
        )
    )
)
if not defined PY_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python"
)
if not defined PY_CMD (
    echo ERROR: no se detecto Python. Instala Python 3.11 o 3.12.
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creando entorno con %PY_CMD%...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo ERROR: no se pudo crear el entorno.
        pause
        exit /b 1
    )
)
echo [2/3] Comprobando librerias...
".venv\Scripts\python.exe" -c "import PySide6, serial, openpyxl" 2>nul
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: no fue posible instalar librerias.
        pause
        exit /b 1
    )
)
echo [3/3] Iniciando aplicacion...
".venv\Scripts\python.exe" sincronizador_laser_lsv.py
if errorlevel 1 (
    echo ERROR: fallo la aplicacion. Copia este mensaje.
    pause
)
