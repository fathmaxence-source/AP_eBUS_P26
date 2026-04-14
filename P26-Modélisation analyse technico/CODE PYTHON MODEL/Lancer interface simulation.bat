@echo off
setlocal

set "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"

if not "%PYTHON_EXE%"=="" (
    if exist "%PYTHON_EXE%" (
        "%PYTHON_EXE%" "main_code.py" --interface
        exit /b %errorlevel%
    )
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "main_code.py" --interface
    exit /b %errorlevel%
)

where py >nul 2>nul
if %errorlevel%==0 (
    py "main_code.py" --interface
    exit /b %errorlevel%
)

echo Erreur : aucun interpreteur Python detecte pour lancer l'interface.
echo.
echo Solutions possibles :
echo  1. Installer Python 3 et cocher l'ajout au PATH.
echo  2. Relancer ce script avec la variable d'environnement PYTHON_EXE
echo     pointant vers python.exe.
echo.
echo Exemple PowerShell :
echo   $env:PYTHON_EXE='C:\chemin\vers\python.exe'
echo   .\Lancer interface simulation.bat
pause
exit /b 1
