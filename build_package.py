#!/usr/bin/env python3
"""
build_package.py - Empaqueta Motor Fusion en un ZIP distribuible.

Uso:
    python build_package.py

Genera:
    dist/Motor-Fusion-v1.0.0-win64.zip  (con Python embebido para Windows)
    dist/Motor-Fusion-v1.0.0-portable.zip (sin Python, para Mac/Linux)
"""

import os
import shutil
import zipfile
import sys
from pathlib import Path

VERSION = "1.0.0"
ROOT = Path(__file__).parent.resolve()
DIST = ROOT / "dist"

# Archivos/carpetas a incluir en el paquete
INCLUDE = [
    "config.py",
    "core/",
    "adapters/",
    "hooks/",
    "mcp_kb_server.py",
    "ingest_knowledge.py",
    "ollama_chat.py",
    "sync_to_github.py",
    "restore_from_github.py",
    "installer/installer_gui.py",
    "installer/manual_usuario.html",
    "installer/setup.py",
    "install.bat",
    "install.sh",
    "README.md",
    "LICENSE",
]

# Archivos a excluir siempre
EXCLUDE_PATTERNS = {
    "__pycache__",
    ".pyc",
    ".pyo",
    ".env",
    "credentials",
    "pending_errors.json",
    "dist/",
    ".git/",
    "tests/",
}


def should_exclude(path: str) -> bool:
    for pat in EXCLUDE_PATTERNS:
        if pat in path:
            return True
    return False


def collect_files(base: Path, rel_prefix: str = "") -> list:
    """Recolecta archivos respetando exclusiones."""
    files = []
    for item in sorted(base.iterdir()):
        rel = f"{rel_prefix}{item.name}" if rel_prefix else item.name
        if should_exclude(rel):
            continue
        if item.is_dir():
            files.extend(collect_files(item, f"{rel}/"))
        elif item.is_file():
            files.append((item, rel))
    return files


def add_to_zip(zf: zipfile.ZipFile, src: Path, arcname: str):
    zf.write(src, arcname)


def build_zip(name: str, include_python_bundle: bool):
    zip_path = DIST / f"{name}.zip"
    print(f"\n  Construyendo: {zip_path.name}")

    arc_prefix = f"Motor-Fusion-v{VERSION}/"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Archivos del motor
        for entry in INCLUDE:
            src = ROOT / entry
            if not src.exists():
                print(f"    [SKIP] {entry} (no existe)")
                continue

            if src.is_dir():
                for fpath, rel in collect_files(src):
                    arcname = f"{arc_prefix}{entry}{rel[len(entry):]}" if rel.startswith(entry) else f"{arc_prefix}{entry}/{rel}"
                    # Fix: use relative path within the dir
                    inner_rel = str(fpath.relative_to(src))
                    arcname = f"{arc_prefix}{entry}{inner_rel}"
                    if not arcname.endswith(inner_rel):
                        arcname = f"{arc_prefix}{entry}/{inner_rel}"
                    add_to_zip(zf, fpath, f"{arc_prefix}{entry}{inner_rel}")
                    print(f"    + {entry}{inner_rel}")
            else:
                add_to_zip(zf, src, f"{arc_prefix}{entry}")
                print(f"    + {entry}")

        # Bundle Python embebido (solo Windows)
        if include_python_bundle:
            bundle_dir = ROOT / "installer" / "bundle" / "python_win"
            if bundle_dir.exists():
                print(f"    + installer/bundle/python_win/ (Python embebido)")
                for fpath, rel in collect_files(bundle_dir):
                    add_to_zip(zf, fpath, f"{arc_prefix}installer/bundle/python_win/{rel}")
            else:
                print("    [WARN] Bundle Python no encontrado en installer/bundle/python_win/")

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  [OK] {zip_path.name} ({size_mb:.1f} MB)")
    return zip_path


def main():
    print("=" * 50)
    print(f"  Motor Fusion - Build Package v{VERSION}")
    print("=" * 50)

    # Crear dist/
    DIST.mkdir(exist_ok=True)

    # Build 1: Windows con Python embebido (para PCs sin Python)
    win_zip = build_zip(f"Motor-Fusion-v{VERSION}-win64", include_python_bundle=True)

    # Build 2: Portable sin Python (para Mac/Linux o PCs con Python)
    portable_zip = build_zip(f"Motor-Fusion-v{VERSION}-portable", include_python_bundle=False)

    print("\n" + "=" * 50)
    print("  Paquetes generados:")
    print(f"    {win_zip}")
    print(f"    {portable_zip}")
    print("")
    print("  Distribucion Windows:")
    print("    1. Copiar Motor-Fusion-*-win64.zip a USB")
    print("    2. Descomprimir en PC destino")
    print("    3. Doble clic en install.bat")
    print("")
    print("  Distribucion Mac/Linux:")
    print("    1. Copiar Motor-Fusion-*-portable.zip")
    print("    2. Descomprimir")
    print("    3. chmod +x install.sh && ./install.sh")
    print("=" * 50)


if __name__ == "__main__":
    main()
