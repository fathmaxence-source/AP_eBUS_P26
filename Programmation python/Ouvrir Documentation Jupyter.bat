@echo off
setlocal

set "BASE_DIR=%~dp0"
set "BUILD_SCRIPT=%BASE_DIR%Construire Jupyter Book.bat"
set "PYTHON_EXE=%BASE_DIR%Codes AP2025\Outil\Outil\WPy64-31180\python-3.11.8.amd64\python.exe"
set "SERVER_SCRIPT=%BASE_DIR%documentation\serve_jupyter_book.py"
set "INDEX_FILE=%BASE_DIR%documentation\jupyter_book_outil_bus\_build\html\index.html"

if exist "%INDEX_FILE%" (
    if not exist "%PYTHON_EXE%" (
        echo Python embarque introuvable :
        echo %PYTHON_EXE%
        pause
        exit /b 1
    )
    if not exist "%SERVER_SCRIPT%" (
        echo Script du serveur introuvable :
        echo %SERVER_SCRIPT%
        pause
        exit /b 1
    )
    "%PYTHON_EXE%" "%SERVER_SCRIPT%"
    exit /b 0
)

echo La documentation n'a pas encore ete construite.
echo Lancement automatique de la construction...
echo.

if not exist "%BUILD_SCRIPT%" (
    echo Script de construction introuvable :
    echo %BUILD_SCRIPT%
    pause
    exit /b 1
)

call "%BUILD_SCRIPT%"
exit /b %errorlevel%
