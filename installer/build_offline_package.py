#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_offline_package.py -- Genera paquete instalador 100% offline
==================================================================
Ejecutar en una maquina CON internet para generar el paquete.
El paquete resultante funciona en un PC vacio (solo Windows + nada mas).

Contenido del paquete generado:
  Motor_IA_Installer/
    install.bat              <- Doble-click para instalar
    installer/
      offline_install.py     <- Instalador Python
      bundle/
        python_win/          <- Python 3.12 embebido (~30 MB)
        wheels/              <- Todos los .whl offline (~400 MB)
        model/               <- all-MiniLM-L6-v2 pre-descargado (~90 MB)
    core/                    <- Codigo fuente Motor_IA
    hooks/
    knowledge/
    dashboard/
    config.py
    ...

Uso:
  python build_offline_package.py [--output <dir>]

El resultado es un directorio listo para copiar a USB o comprimir en ZIP.
"""

import os
import sys
import shutil
import subprocess
import json
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
PYTHON_VERSION = "3.12.10"
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

# Paquetes necesarios con versiones fijas para reproducibilidad
REQUIRED_PACKAGES = [
    # Core RAG
    "chromadb",
    "sentence-transformers",
    # Torch CPU-only (mucho mas ligero que CUDA)
    "torch --index-url https://download.pytorch.org/whl/cpu",
    # UI
    "rich",
    # Dependencias que sentence-transformers necesita
    "transformers",
    "huggingface-hub",
    "tokenizers",
    "numpy",
    "scipy",
    "scikit-learn",
    "tqdm",
    # ChromaDB deps
    "onnxruntime",
    "httpx",
    "pydantic",
    "tenacity",
    "typing_extensions",
    # Web search
    "duckduckgo-search",
    # MCP server (opcional pero incluido)
    "mcp",
]

# Archivos y directorios del proyecto a incluir
PROJECT_DIRS = [
    "core", "hooks", "knowledge", "dashboard", "adapters",
    "installer", "docs",
]
PROJECT_FILES = [
    "config.py", "__init__.py", "requirements.txt",
    "mcp_kb_server.py", "ingest_knowledge.py",
    "CLAUDE_CLI_INTEGRATION.md",
]

# Directorios a excluir al copiar
EXCLUDE_DIRS = {
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    "chroma_db", "locks", "data",
}
EXCLUDE_FILES = {
    ".pyc", ".pyo", ".log", ".tmp",
}

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _banner(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def _ok(msg):
    print(f"  [OK] {msg}")


def _info(msg):
    print(f"  ... {msg}")


def _err(msg):
    print(f"  [ERROR] {msg}")


# ---------------------------------------------------------------------------
# Paso 1: Descargar Python embebido
# ---------------------------------------------------------------------------

def download_python_embed(dest_dir: Path):
    """Descarga Python embebido para Windows (si no existe ya)."""
    python_dir = dest_dir / "bundle" / "python_win"

    # Check if already exists with python.exe
    if (python_dir / "python.exe").exists():
        _ok(f"Python embebido ya existe en {python_dir}")
        return python_dir

    # Clean and recreate
    if python_dir.exists():
        shutil.rmtree(str(python_dir))
    python_dir.mkdir(parents=True, exist_ok=True)

    zip_path = dest_dir / "python_embed.zip"
    _info(f"Descargando Python {PYTHON_VERSION} embebido...")

    import urllib.request
    urllib.request.urlretrieve(PYTHON_EMBED_URL, str(zip_path))

    _info("Extrayendo...")
    import zipfile
    with zipfile.ZipFile(str(zip_path), 'r') as zf:
        zf.extractall(str(python_dir))
    zip_path.unlink()

    # Habilitar pip: editar python312._pth para incluir site-packages
    pth_file = python_dir / "python312._pth"
    if pth_file.exists():
        pth_file.write_text(
            "python312.zip\n.\nLib/site-packages\nimport site\n",
            encoding="utf-8",
        )

    # Descargar get-pip.py
    getpip = dest_dir / "bundle" / "get-pip.py"
    if not getpip.exists():
        _info("Descargando get-pip.py...")
        urllib.request.urlretrieve(GET_PIP_URL, str(getpip))

    _ok(f"Python embebido listo: {python_dir}")
    return python_dir


# ---------------------------------------------------------------------------
# Paso 2: Descargar wheels offline
# ---------------------------------------------------------------------------

def download_wheels(dest_dir: Path):
    """Descarga todos los wheels necesarios para instalacion offline."""
    wheels_dir = dest_dir / "bundle" / "wheels"
    wheels_dir.mkdir(parents=True, exist_ok=True)

    _info("Descargando wheels para instalacion offline...")
    _info("(Esto puede tardar varios minutos la primera vez)")

    for pkg_spec in REQUIRED_PACKAGES:
        parts = pkg_spec.split()
        pkg_name = parts[0]
        extra_args = parts[1:] if len(parts) > 1 else []

        _info(f"  Descargando: {pkg_name}")
        cmd = [
            sys.executable, "-m", "pip", "download",
            "--dest", str(wheels_dir),
            "--only-binary=:all:",
            "--platform", "win_amd64",
            "--python-version", "3.12",
        ] + extra_args + [pkg_name]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Retry without --only-binary for pure-python packages
            cmd2 = [
                sys.executable, "-m", "pip", "download",
                "--dest", str(wheels_dir),
                "--platform", "win_amd64",
                "--python-version", "3.12",
            ] + extra_args + [pkg_name]
            result2 = subprocess.run(cmd2, capture_output=True, text=True)
            if result2.returncode != 0:
                _err(f"  No se pudo descargar {pkg_name}: {result2.stderr[:200]}")

    # Count wheels
    wheel_count = len(list(wheels_dir.glob("*.whl")))
    wheel_size = sum(f.stat().st_size for f in wheels_dir.iterdir()) / (1024 * 1024)
    _ok(f"{wheel_count} wheels descargados ({wheel_size:.0f} MB)")
    return wheels_dir


# ---------------------------------------------------------------------------
# Paso 3: Copiar modelo pre-entrenado
# ---------------------------------------------------------------------------

def copy_model(dest_dir: Path):
    """Copia el modelo all-MiniLM-L6-v2 del cache local."""
    model_dir = dest_dir / "bundle" / "model"
    model_dir.mkdir(parents=True, exist_ok=True)

    # Find model in huggingface cache
    cache_locations = [
        Path.home() / ".cache" / "huggingface" / "hub" /
        "models--sentence-transformers--all-MiniLM-L6-v2",
        Path(os.environ.get("HF_HOME", "")) / "hub" /
        "models--sentence-transformers--all-MiniLM-L6-v2",
        Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Local" /
        "ClaudeCode" / ".cache" / "huggingface" / "hub" /
        "models--sentence-transformers--all-MiniLM-L6-v2",
    ]

    source_model = None
    for loc in cache_locations:
        if loc.exists():
            # Find the snapshot directory
            snapshots = loc / "snapshots"
            if snapshots.exists():
                for snap in snapshots.iterdir():
                    if snap.is_dir() and (snap / "config.json").exists():
                        source_model = snap
                        break
            if source_model:
                break

    if not source_model:
        # Try downloading the model
        _info("Modelo no encontrado en cache. Descargando...")
        try:
            from sentence_transformers import SentenceTransformer
            m = SentenceTransformer(MODEL_NAME)
            # Save to our bundle
            m.save(str(model_dir / "all-MiniLM-L6-v2"))
            _ok(f"Modelo descargado y guardado: {model_dir}")
            return model_dir
        except Exception as e:
            _err(f"No se pudo descargar el modelo: {e}")
            return model_dir

    # Copy snapshot to bundle
    dest_model = model_dir / "all-MiniLM-L6-v2"
    if dest_model.exists():
        shutil.rmtree(str(dest_model))

    shutil.copytree(str(source_model), str(dest_model))
    model_size = sum(
        f.stat().st_size for f in dest_model.rglob("*") if f.is_file()
    ) / (1024 * 1024)
    _ok(f"Modelo copiado ({model_size:.0f} MB): {dest_model}")
    return model_dir


# ---------------------------------------------------------------------------
# Paso 4: Copiar proyecto
# ---------------------------------------------------------------------------

def copy_project(dest_dir: Path):
    """Copia los archivos del proyecto Motor_IA."""

    def _ignore(directory, contents):
        ignored = []
        for c in contents:
            if c in EXCLUDE_DIRS:
                ignored.append(c)
            elif any(c.endswith(ext) for ext in EXCLUDE_FILES):
                ignored.append(c)
        return ignored

    for dirname in PROJECT_DIRS:
        src = _PROJECT_ROOT / dirname
        dst = dest_dir / dirname
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(str(dst))
            shutil.copytree(str(src), str(dst), ignore=_ignore)

    for fname in PROJECT_FILES:
        src = _PROJECT_ROOT / fname
        if src.is_file():
            shutil.copy2(str(src), str(dest_dir / fname))

    # Create empty data directories (will be populated at runtime)
    (dest_dir / "core" / "data").mkdir(parents=True, exist_ok=True)
    (dest_dir / "core" / "chroma_db").mkdir(parents=True, exist_ok=True)

    _ok(f"Proyecto copiado a {dest_dir}")


# ---------------------------------------------------------------------------
# Paso 5: Crear install.bat
# ---------------------------------------------------------------------------

def create_install_bat(dest_dir: Path):
    """Crea install.bat que el usuario ejecuta con doble-click."""
    bat_content = r'''@echo off
chcp 65001 >nul 2>&1
title Motor Fusion IA - Instalador Offline
echo.
echo ============================================================
echo   Motor Fusion IA - Instalador Offline
echo ============================================================
echo.

:: Verificar que estamos en el directorio correcto
if not exist "installer\bundle\python_win\python.exe" (
    echo [ERROR] No se encuentra el Python embebido.
    echo         Ejecuta este archivo desde el directorio Motor_IA_Installer.
    pause
    exit /b 1
)

set PYTHON=installer\bundle\python_win\python.exe

:: Paso 1: Instalar pip en el Python embebido
echo [1/4] Instalando pip en Python embebido...
%PYTHON% installer\bundle\get-pip.py --no-index --find-links installer\bundle\wheels 2>nul
if errorlevel 1 (
    echo   Intentando con get-pip.py online fallback...
    %PYTHON% installer\bundle\get-pip.py 2>nul
)

:: Paso 2: Instalar dependencias desde wheels locales
echo [2/4] Instalando dependencias offline (esto tarda ~2 minutos)...
%PYTHON% -m pip install --no-index --find-links installer\bundle\wheels ^
    rich chromadb sentence-transformers torch transformers ^
    huggingface-hub tokenizers numpy scipy scikit-learn ^
    tqdm onnxruntime httpx pydantic tenacity typing_extensions ^
    duckduckgo-search mcp ^
    --quiet --disable-pip-version-check 2>nul

if errorlevel 1 (
    echo [!] Algunas dependencias fallaron. Intentando una por una...
    for %%P in (rich chromadb sentence-transformers torch transformers huggingface-hub numpy scipy scikit-learn tqdm onnxruntime httpx pydantic) do (
        %PYTHON% -m pip install --no-index --find-links installer\bundle\wheels %%P --quiet --disable-pip-version-check 2>nul
    )
)

:: Paso 3: Pre-cargar modelo de embeddings
echo [3/4] Configurando modelo de embeddings...
if exist "installer\bundle\model\all-MiniLM-L6-v2\config.json" (
    :: Copiar modelo al cache de huggingface para que sentence-transformers lo encuentre
    %PYTHON% -c "import os,shutil; cache=os.path.join(os.path.expanduser('~'),'.cache','huggingface','hub','models--sentence-transformers--all-MiniLM-L6-v2','snapshots','offline'); os.makedirs(os.path.dirname(cache),exist_ok=True); shutil.copytree('installer\\bundle\\model\\all-MiniLM-L6-v2',cache) if not os.path.exists(cache) else None" 2>nul
    echo   Modelo pre-cargado OK
) else (
    echo   [!] Modelo no incluido en el paquete. Se descargara en primer uso.
)

:: Paso 4: Ejecutar instalador principal
echo [4/4] Ejecutando instalador de Motor Fusion IA...
%PYTHON% installer\offline_install.py

echo.
echo ============================================================
echo   Instalacion completada!
echo ============================================================
echo.
pause
'''
    bat_path = dest_dir / "install.bat"
    bat_path.write_text(bat_content, encoding="utf-8")
    _ok(f"install.bat creado: {bat_path}")


# ---------------------------------------------------------------------------
# Paso 6: Crear info de paquete
# ---------------------------------------------------------------------------

def create_package_info(dest_dir: Path):
    """Crea archivo de metadatos del paquete."""
    wheels_dir = dest_dir / "installer" / "bundle" / "wheels"
    model_dir = dest_dir / "installer" / "bundle" / "model"

    wheel_count = len(list(wheels_dir.glob("*.whl"))) if wheels_dir.exists() else 0
    model_exists = (model_dir / "all-MiniLM-L6-v2" / "config.json").exists()

    info = {
        "app": "Motor Fusion IA",
        "version": "1.0.2-offline",
        "build_date": datetime.now().isoformat(),
        "build_machine": os.environ.get("COMPUTERNAME", "unknown"),
        "python_version": PYTHON_VERSION,
        "wheel_count": wheel_count,
        "model_included": model_exists,
        "model_name": MODEL_NAME,
        "requires_internet": False,
        "target_platform": "Windows 10/11 x64",
        "instructions": [
            "1. Copia esta carpeta completa al PC destino (USB, red, etc.)",
            "2. En el PC destino, ejecuta install.bat como administrador",
            "3. Sigue las instrucciones en pantalla",
            "4. Abre Claude Code CLI - los hooks se activan automaticamente",
        ],
    }
    info_path = dest_dir / "PACKAGE_INFO.json"
    info_path.write_text(
        json.dumps(info, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    readme = f"""Motor Fusion IA - Paquete Instalador Offline
=============================================
Fecha de build: {info['build_date'][:10]}
Python: {PYTHON_VERSION}
Wheels: {wheel_count} paquetes
Modelo: {'Incluido' if model_exists else 'No incluido (se descargara)'}

INSTRUCCIONES:
  1. Copia toda esta carpeta al PC destino
  2. Ejecuta install.bat (doble-click)
  3. Espera ~2-3 minutos
  4. Listo! Abre Claude Code CLI

REQUISITOS DEL PC DESTINO:
  - Windows 10/11 (64-bit)
  - NO necesita Python instalado
  - NO necesita Internet
  - ~1.5 GB de espacio en disco
"""
    (dest_dir / "LEEME.txt").write_text(readme, encoding="utf-8")
    _ok("Metadatos del paquete creados")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Genera paquete instalador 100% offline de Motor Fusion IA"
    )
    parser.add_argument(
        "--output", "-o",
        default=str(_PROJECT_ROOT.parent / "Motor_IA_Installer"),
        help="Directorio de salida para el paquete",
    )
    parser.add_argument(
        "--skip-wheels",
        action="store_true",
        help="Omitir descarga de wheels (si ya estan descargados)",
    )
    parser.add_argument(
        "--skip-model",
        action="store_true",
        help="Omitir copia del modelo (se descargara en primer uso)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    installer_dir = output_dir / "installer"

    print()
    _banner(f"Motor Fusion IA - Build Offline Package")
    print(f"  Salida: {output_dir}")
    print(f"  Proyecto: {_PROJECT_ROOT}")
    print()

    # Paso 1: Copiar proyecto PRIMERO (antes de descargar, para no sobreescribir)
    _banner("Paso 1/6: Proyecto Motor_IA")
    copy_project(output_dir)

    # Paso 2: Python embebido (dentro del installer ya copiado)
    _banner("Paso 2/6: Python embebido")
    download_python_embed(installer_dir)

    # Paso 3: Wheels offline
    _banner("Paso 3/6: Dependencias (wheels)")
    if args.skip_wheels:
        _info("Omitido por --skip-wheels")
    else:
        download_wheels(installer_dir)

    # Paso 4: Modelo
    _banner("Paso 4/6: Modelo de embeddings")
    if args.skip_model:
        _info("Omitido por --skip-model")
    else:
        copy_model(installer_dir)

    # Paso 5: install.bat
    _banner("Paso 5/6: Script de instalacion")
    create_install_bat(output_dir)

    # Paso 6: Metadatos
    _banner("Paso 6/6: Metadatos del paquete")
    create_package_info(output_dir)

    # Resumen
    total_size = sum(
        f.stat().st_size
        for f in output_dir.rglob("*")
        if f.is_file()
    ) / (1024 * 1024)

    print()
    _banner("BUILD COMPLETADO")
    print(f"  Directorio:  {output_dir}")
    print(f"  Tamano total: {total_size:.0f} MB")
    print()
    print("  Para instalar en un PC sin internet:")
    print(f"  1. Copia '{output_dir.name}/' completo a un USB")
    print(f"  2. En el PC destino, ejecuta install.bat")
    print()


if __name__ == "__main__":
    main()
