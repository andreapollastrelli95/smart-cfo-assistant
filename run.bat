@echo off
rem Avvio di Smart CFO Assistant tramite il virtual environment del progetto.
rem Uso: run.bat          -> avvio normale, senza console
rem      run.bat debug    -> avvio con console visibile per leggere eventuali errori
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo [Smart CFO] Virtual environment non trovato. Esegui prima setup.ps1
    pause
    exit /b 1
)

if /i "%~1"=="debug" (
    ".venv\Scripts\python.exe" main.py
    pause
) else (
    start "" ".venv\Scripts\pythonw.exe" main.py
)
endlocal
