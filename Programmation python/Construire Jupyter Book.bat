@echo off
setlocal

set "BASE_DIR=%~dp0"
set "PYTHON_EXE=%BASE_DIR%Codes AP2025\Outil\Outil\WPy64-31180\python-3.11.8.amd64\python.exe"
set "RUNNER=%BASE_DIR%documentation\build_jupyter_book.py"
set "BOOK_DIR=%BASE_DIR%documentation\jupyter_book_outil_bus"
set "INDEX_FILE=%BOOK_DIR%\_build\html\index.html"
set "SERVER_SCRIPT=%BASE_DIR%documentation\serve_jupyter_book.py"

if not exist "%PYTHON_EXE%" (
    echo Python embarque introuvable :
    echo %PYTHON_EXE%
    pause
    exit /b 1
)

if not exist "%RUNNER%" (
    echo Script de lancement introuvable :
    echo %RUNNER%
    pause
    exit /b 1
)

cd /d "%BASE_DIR%"
"%PYTHON_EXE%" "%RUNNER%" build --html

if errorlevel 1 (
    echo.
    echo La construction du Jupyter Book a echoue.
    pause
    exit /b 1
)

echo.
echo Construction terminee.
echo La documentation est disponible ici :
echo %INDEX_FILE%
echo.
echo Lancement du serveur local de documentation...

if not exist "%SERVER_SCRIPT%" (
    echo Script du serveur introuvable :
    echo %SERVER_SCRIPT%
    pause
    exit /b 1
)

"%PYTHON_EXE%" "%SERVER_SCRIPT%"
