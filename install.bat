@echo off
chcp 65001 >nul 2>&1
title Motor Fusion IA - Instalador Offline

echo.
echo  ============================================================
echo   Motor Fusion IA - Instalador Offline v1.0.1-fusion
echo   Funciona sin internet y sin Python del sistema
echo  ============================================================
echo.

REM Detectar directorio del script (donde esta install.bat)
set "SCRIPT_DIR=%~dp0"
set "BUNDLE_PYTHON=%SCRIPT_DIR%installer\bundle\python_win\python.exe"
set "OFFLINE_INSTALLER=%SCRIPT_DIR%installer\offline_install.py"

REM --- Usar Python embebido del bundle (primer opcion, sin internet) ---
if exist "%BUNDLE_PYTHON%" (
    echo  [OK] Python embebido detectado
    echo  [>>] Iniciando instalacion offline...
    echo.
    "%BUNDLE_PYTHON%" "%OFFLINE_INSTALLER%" %*
    goto :check_result
)

REM --- Fallback: Python del sistema ---
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo  [OK] Python del sistema detectado
    echo  [>>] Iniciando instalacion offline...
    echo.
    python "%OFFLINE_INSTALLER%" %*
    goto :check_result
)

where python3 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo  [OK] Python3 del sistema detectado
    echo  [>>] Iniciando instalacion offline...
    echo.
    python3 "%OFFLINE_INSTALLER%" %*
    goto :check_result
)

REM --- Sin Python disponible ---
echo.
echo  [ERROR] No se encontro Python embebido ni Python del sistema.
echo.
echo  Verifica que exista la carpeta:
echo    %SCRIPT_DIR%installer\bundle\python_win\
echo.
echo  Si esta carpeta falta, descarga el repositorio completo de nuevo.
echo.
pause
exit /b 1

:check_result
if %ERRORLEVEL% EQU 0 (
    echo.
    echo  Instalacion completada. Presiona cualquier tecla para cerrar.
) else (
    echo.
    echo  La instalacion tuvo problemas (codigo: %ERRORLEVEL%).
    echo  Revisa los mensajes de error arriba.
)
echo.
pause
