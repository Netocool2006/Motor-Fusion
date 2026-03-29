@echo off
chcp 65001 >nul 2>&1
title Motor Fusion - Instalador
echo.
echo  ============================================
echo   Motor Fusion - Instalador v1.0.0
echo  ============================================
echo.
echo  Iniciando instalador grafico...
echo.

REM Detectar directorio del script
set "SCRIPT_DIR=%~dp0"

REM Intentar usar Python embebido del bundle
if exist "%SCRIPT_DIR%installer\bundle\python_win\python.exe" (
    echo  [OK] Python embebido detectado
    "%SCRIPT_DIR%installer\bundle\python_win\python.exe" "%SCRIPT_DIR%installer\installer_gui.py"
    goto :end
)

REM Fallback: intentar Python del sistema
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo  [OK] Python del sistema detectado
    python "%SCRIPT_DIR%installer\installer_gui.py"
    goto :end
)

where python3 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo  [OK] Python3 del sistema detectado
    python3 "%SCRIPT_DIR%installer\installer_gui.py"
    goto :end
)

echo.
echo  [ERROR] No se encontro Python embebido ni del sistema.
echo  Asegurese de que la carpeta installer\bundle\python_win\ existe.
echo.
pause

:end
