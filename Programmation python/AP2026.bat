@echo off
setlocal

set "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"
title Lancement de l'outil d'aide a la decision

set "SCRIPT_PATH=%BASE_DIR%Programme AP.py"
set "EMBEDDED_PYTHON=%BASE_DIR%Codes AP2025\Outil\Outil\WPy64-31180\python-3.11.8.amd64\python.exe"

if not exist "%SCRIPT_PATH%" (
    echo Erreur : script introuvable :
    echo %SCRIPT_PATH%
    pause
    exit /b 1
)

if exist "%EMBEDDED_PYTHON%" (
    "%EMBEDDED_PYTHON%" "%SCRIPT_PATH%" %*
    if errorlevel 1 (
        echo.
        echo Erreur : le programme s'est arrete avec un code %errorlevel%.
        pause
        exit /b %errorlevel%
    )
    exit /b 0
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "%SCRIPT_PATH%" %*
    if errorlevel 1 (
        echo.
        echo Erreur : le programme s'est arrete avec un code %errorlevel%.
        pause
        exit /b %errorlevel%
    )
    exit /b 0
)

where py >nul 2>nul
if %errorlevel%==0 (
    py "%SCRIPT_PATH%" %*
    if errorlevel 1 (
        echo.
        echo Erreur : le lanceur py semble mal configure sur cette machine.
        echo Utilisation recommandee : verifier l'installation Python ou utiliser le Python embarque du projet.
        pause
        exit /b %errorlevel%
    )
    exit /b 0
)

echo Erreur : aucun interpreteur Python detecte.
echo Le Python embarque n'a pas ete trouve et aucune commande python / py n'est disponible.
pause
exit /b 1
