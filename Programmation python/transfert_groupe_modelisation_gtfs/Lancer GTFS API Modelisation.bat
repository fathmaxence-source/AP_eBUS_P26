@echo off
setlocal

set "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"

set "SCRIPT_PATH=%BASE_DIR%gtfs_api_modelisation.py"
set "EMBEDDED_PYTHON=%BASE_DIR%..\Codes AP2025\Outil\Outil\WPy64-31180\python-3.11.8.amd64\python.exe"
set "RUN_ARGS=%*"
set "PAUSE_ON_SUCCESS=0"

if "%~1"=="" (
    set "RUN_ARGS=--list-networks"
    set "PAUSE_ON_SUCCESS=1"
)

if not exist "%SCRIPT_PATH%" (
    echo Script introuvable :
    echo %SCRIPT_PATH%
    pause
    exit /b 1
)

if exist "%EMBEDDED_PYTHON%" (
    "%EMBEDDED_PYTHON%" "%SCRIPT_PATH%" %RUN_ARGS%
    if errorlevel 1 goto :run_error
    goto :run_success
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "%SCRIPT_PATH%" %RUN_ARGS%
    if errorlevel 1 goto :run_error
    goto :run_success
)

where py >nul 2>nul
if %errorlevel%==0 (
    py "%SCRIPT_PATH%" %RUN_ARGS%
    if errorlevel 1 goto :run_error
    goto :run_success
)

echo Aucun interprete Python n'a ete detecte.
pause
exit /b 1

:run_success
if "%PAUSE_ON_SUCCESS%"=="1" (
    echo.
    echo Astuce : pour afficher les lignes d'un reseau, utilisez par exemple :
    echo   Lancer GTFS API Modelisation.bat --network compiegne --list-lines
    echo.
    pause
)
exit /b 0

:run_error
echo.
echo Erreur : execution du script impossible.
echo Exemple d'utilisation :
echo   Lancer GTFS API Modelisation.bat --network compiegne --line 1 --show-stops
pause
exit /b %errorlevel%
