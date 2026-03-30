@echo off
setlocal

set "PYTHON=C:\Users\ntoledo\AppData\Local\Programs\Python\Python312\python.exe"
set "SERVER=%~dp0server.py"
set "PORT=7070"

echo.
echo  Motor_IA Dashboard
echo  ==================
echo  http://localhost:%PORT%
echo.

if not exist "%PYTHON%" (
    echo [ERROR] Python no encontrado: %PYTHON%
    pause
    exit /b 1
)

REM Abrir browser automaticamente despues de 1 segundo
start "" /B cmd /c "timeout /t 1 /nobreak >nul && start http://localhost:%PORT%"

"%PYTHON%" "%SERVER%" %PORT%

pause
