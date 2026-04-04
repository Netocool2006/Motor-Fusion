#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
offline_install.py -- Instalador offline de Motor Fusion IA
===========================================================
Funciona sin internet y sin Python del sistema.
Se ejecuta desde el Python embebido incluido en installer/bundle/python_win/.

Pasos de instalacion:
  1. Copia Motor_IA al directorio de instalacion
  2. Copia el Python embebido al directorio de instalacion (python_runtime/)
  3. Crea ~/.adaptive_cli/ con subdirectorios
  4. Registra hooks en Claude Code settings.json (usando el Python instalado)
  5. Verifica la instalacion

Uso:
  python offline_install.py [--dir <ruta_instalacion>] [--no-hooks]

Ejemplos:
  python offline_install.py
  python offline_install.py --dir "C:/Motor_IA"
  python offline_install.py --no-hooks
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Asegurar salida sin buffering (necesario cuando stdout va a archivo o pipe)
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
VERSION = "1.0.1-fusion"
APP_NAME = "Motor Fusion IA"
DATA_DIR_NAME = ".adaptive_cli"

MOTOR_FILES = [
    "config.py",
    "__init__.py",
    "mcp_kb_server.py",
    "ingest_knowledge.py",
    "ollama_chat.py",
    "sync_to_github.py",
    "restore_from_github.py",
    # Documentacion - Hardening & Claude CLI Integration (2026-04-01)
    "CLAUDE_CLI_INTEGRATION.md",
    "CONSOLIDATION_SUMMARY.md",
    "FINDINGS_REPORT.md",
    "TEST_RESULTS.md",
    "ENV_SETUP.md",
    "TEST_PLAN.md",
]
MOTOR_DIRS = ["core", "adapters", "hooks", "dashboard", "knowledge", "docs"]
HOOK_EVENTS = ["PreToolUse", "UserPromptSubmit", "PostToolUse", "Stop"]
HOOK_SCRIPTS = {
    "PreToolUse":       "session_start.py",
    "UserPromptSubmit": "user_prompt_submit.py",
    "PostToolUse":      "post_tool_use.py",
    "Stop":             "session_end.py",
}

# ---------------------------------------------------------------------------
# Helpers de consola
# ---------------------------------------------------------------------------

def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")

def _info(msg: str) -> None:
    print(f"  ... {msg}")

def _warn(msg: str) -> None:
    print(f"  [!] {msg}")

def _err(msg: str) -> None:
    print(f"  [ERROR] {msg}")

def _sep(title: str = "") -> None:
    line = "=" * 60
    if title:
        print(f"\n{line}")
        print(f"  {title}")
        print(line)
    else:
        print(line)


# ---------------------------------------------------------------------------
# Localizacion de directorios fuente
# ---------------------------------------------------------------------------

def _find_motor_source() -> Path:
    """
    Encuentra el directorio raiz del Motor_IA.
    Buscamos en el padre del directorio del installer (estructura de desarrollo).
    """
    installer_dir = Path(__file__).resolve().parent
    motor_root = installer_dir.parent
    if (motor_root / "core" / "knowledge_base.py").is_file():
        return motor_root
    raise FileNotFoundError(
        f"No se encontro Motor_IA en {motor_root}. "
        "Ejecuta el instalador desde el directorio correcto."
    )


def _find_bundle_python() -> Path | None:
    """
    Encuentra el Python embebido en installer/bundle/python_win/.
    Retorna la ruta al python.exe o None si no existe.
    """
    installer_dir = Path(__file__).resolve().parent
    embedded = installer_dir / "bundle" / "python_win" / "python.exe"
    if embedded.is_file():
        return embedded
    return None


# ---------------------------------------------------------------------------
# Directorio de instalacion por defecto
# ---------------------------------------------------------------------------

def _default_install_dir() -> Path:
    """Directorio de instalacion por defecto segun OS."""
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(local_app) / "Motor_IA"
    return Path.home() / ".local" / "share" / "Motor_IA"


# ---------------------------------------------------------------------------
# Paso 1: Copiar Motor_IA
# ---------------------------------------------------------------------------

def copy_motor_files(source: Path, dest: Path) -> int:
    """
    Copia los archivos del motor al directorio de instalacion.
    Retorna el numero de archivos copiados.
    """
    dest.mkdir(parents=True, exist_ok=True)
    count = 0

    # Archivos raiz
    for fname in MOTOR_FILES:
        src_f = source / fname
        if src_f.is_file():
            shutil.copy2(str(src_f), str(dest / fname))
            count += 1

    # Directorios core
    for dname in MOTOR_DIRS:
        src_d = source / dname
        if src_d.is_dir():
            dst_d = dest / dname
            if dst_d.exists():
                shutil.rmtree(str(dst_d))

            def _ignore(directory: str, contents: list) -> list:
                return [n for n in contents if n in ("__pycache__",) or n.endswith(".pyc")]

            shutil.copytree(str(src_d), str(dst_d), ignore=_ignore)
            count += sum(1 for _ in dst_d.rglob("*.py"))

    return count


# ---------------------------------------------------------------------------
# Paso 2: Copiar Python embebido
# ---------------------------------------------------------------------------

def copy_embedded_python(bundle_python: Path, dest: Path) -> Path:
    """
    Copia un runtime minimo de Python a <dest>/python_runtime/.
    Solo copia los archivos necesarios para ejecutar los hooks de Motor_IA.
    Excluye tkinter, tcl y otros componentes pesados no necesarios para CLI.
    Retorna la ruta al python.exe instalado.
    """
    runtime_dir = dest / "python_runtime"
    bundle_dir = bundle_python.parent

    if runtime_dir.exists():
        shutil.rmtree(str(runtime_dir))
    runtime_dir.mkdir(parents=True)

    # Archivos individuales esenciales para ejecutar scripts Python
    _ESSENTIAL_FILES = {
        "python.exe", "pythonw.exe",
        "python3.dll", "python312.dll",
        "python312.zip", "python312._pth",
        "python.cat",
        # Extensiones necesarias para el motor
        "_asyncio.pyd", "_bz2.pyd", "_ctypes.pyd", "_decimal.pyd",
        "_elementtree.pyd", "_hashlib.pyd", "_lzma.pyd", "_multiprocessing.pyd",
        "_overlapped.pyd", "_queue.pyd", "_socket.pyd", "_sqlite3.pyd",
        "_ssl.pyd", "_uuid.pyd", "_wmi.pyd", "_zoneinfo.pyd",
        "pyexpat.pyd", "select.pyd", "unicodedata.pyd",
        # DLLs del runtime
        "libcrypto-3.dll", "libffi-8.dll", "libssl-3.dll",
        "sqlite3.dll", "vcruntime140.dll", "vcruntime140_1.dll",
        "zlib1.dll",
    }

    # Copiar archivos individuales
    for fname in _ESSENTIAL_FILES:
        src = bundle_dir / fname
        if src.is_file():
            shutil.copy2(str(src), str(runtime_dir / fname))

    # Copiar solo los paquetes necesarios para Motor_IA
    # (rich + markdown_it + mdurl - pygments no es necesario para tablas/paneles)
    _NEEDED_PKGS = {
        "rich", "rich-",
        "markdown_it", "markdown_it_py",
        "mdurl", "mdurl-",
    }

    src_site = bundle_dir / "Lib" / "site-packages"
    if src_site.is_dir():
        dst_site = runtime_dir / "Lib" / "site-packages"
        dst_site.mkdir(parents=True)

        def _skip_pycache(directory: str, contents: list) -> list:
            return [n for n in contents if n == "__pycache__" or n.endswith(".pyc")]

        def _is_needed(name: str) -> bool:
            name_lower = name.lower()
            return any(name_lower.startswith(p.lower()) for p in _NEEDED_PKGS)

        for pkg in src_site.iterdir():
            if not _is_needed(pkg.name):
                continue  # saltar pip, setuptools, etc.
            if pkg.is_dir():
                shutil.copytree(str(pkg), str(dst_site / pkg.name),
                                ignore=_skip_pycache)
            elif pkg.is_file():
                shutil.copy2(str(pkg), str(dst_site / pkg.name))

    # Ajustar _pth para runtime minimo: apunta a Lib/site-packages
    pth_content = "python312.zip\n.\nimport site\n"
    (runtime_dir / "python312._pth").write_text(pth_content, encoding="utf-8")

    installed_python = runtime_dir / "python.exe"
    if not installed_python.is_file():
        raise FileNotFoundError(f"python.exe no encontrado en {runtime_dir}")
    return installed_python


# ---------------------------------------------------------------------------
# Paso 2b: Instalar dependencias pip desde wheels offline
# ---------------------------------------------------------------------------

def _install_wheels_offline(install_dir: Path, python_exe: Path):
    """
    Instala dependencias pip desde wheels pre-descargados.
    Los wheels estan en installer/bundle/wheels/.
    Si no hay wheels, se salta silenciosamente (instalacion minima).
    """
    installer_dir = Path(__file__).resolve().parent
    wheels_dir = installer_dir / "bundle" / "wheels"
    getpip = installer_dir / "bundle" / "get-pip.py"

    if not wheels_dir.exists() or not any(wheels_dir.glob("*.whl")):
        _info("No se encontraron wheels offline. Saltando instalacion de dependencias.")
        _info("Las dependencias se instalaran cuando haya internet disponible.")
        return

    wheel_count = len(list(wheels_dir.glob("*.whl")))
    _info(f"Encontrados {wheel_count} wheels offline")

    # Paso 1: Instalar pip si no existe
    try:
        import subprocess
        result = subprocess.run(
            [str(python_exe), "-m", "pip", "--version"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            if getpip.exists():
                _info("Instalando pip...")
                subprocess.run(
                    [str(python_exe), str(getpip),
                     "--no-index", "--find-links", str(wheels_dir)],
                    capture_output=True, text=True, timeout=120,
                )
    except Exception as e:
        _warn(f"pip check: {e}")

    # Paso 2: Instalar todos los wheels
    _PACKAGES = [
        "rich", "chromadb", "sentence-transformers", "torch",
        "transformers", "huggingface-hub", "tokenizers",
        "numpy", "scipy", "scikit-learn", "tqdm",
        "onnxruntime", "httpx", "pydantic", "tenacity",
        "typing_extensions", "duckduckgo-search",
    ]

    _info("Instalando dependencias (esto tarda ~2 minutos)...")
    try:
        import subprocess
        result = subprocess.run(
            [str(python_exe), "-m", "pip", "install",
             "--no-index", "--find-links", str(wheels_dir),
             "--quiet", "--disable-pip-version-check"] + _PACKAGES,
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            _ok(f"Todas las dependencias instaladas correctamente")
        else:
            # Intentar una por una
            _warn("Instalacion masiva fallo. Intentando una por una...")
            installed = 0
            for pkg in _PACKAGES:
                r = subprocess.run(
                    [str(python_exe), "-m", "pip", "install",
                     "--no-index", "--find-links", str(wheels_dir),
                     "--quiet", "--disable-pip-version-check", pkg],
                    capture_output=True, text=True, timeout=120,
                )
                if r.returncode == 0:
                    installed += 1
                else:
                    _warn(f"  {pkg}: fallo")
            _ok(f"{installed}/{len(_PACKAGES)} paquetes instalados")
    except Exception as e:
        _err(f"Error instalando dependencias: {e}")


# ---------------------------------------------------------------------------
# Paso 2c: Pre-cargar modelo de embeddings
# ---------------------------------------------------------------------------

def _install_model_offline(install_dir: Path, python_exe: Path):
    """
    Copia el modelo all-MiniLM-L6-v2 al cache de huggingface.
    El modelo esta en installer/bundle/model/all-MiniLM-L6-v2/.
    """
    installer_dir = Path(__file__).resolve().parent
    model_src = installer_dir / "bundle" / "model" / "all-MiniLM-L6-v2"

    if not model_src.exists() or not (model_src / "config.json").exists():
        _info("Modelo no incluido en el paquete. Se descargara en primer uso (requiere internet).")
        return

    # Determinar cache destino
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    model_dest = hf_cache / "models--sentence-transformers--all-MiniLM-L6-v2" / "snapshots" / "offline"

    if model_dest.exists() and (model_dest / "config.json").exists():
        _ok("Modelo ya instalado en cache")
        return

    try:
        model_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(model_src), str(model_dest))
        model_size = sum(
            f.stat().st_size for f in model_dest.rglob("*") if f.is_file()
        ) / (1024 * 1024)
        _ok(f"Modelo instalado ({model_size:.0f} MB): {model_dest}")
    except Exception as e:
        _warn(f"No se pudo copiar el modelo: {e}")
        _info("Se descargara automaticamente en primer uso (requiere internet).")


# ---------------------------------------------------------------------------
# Paso 3: Crear directorio de datos
# ---------------------------------------------------------------------------

def create_data_dir() -> Path:
    """Crea ~/.adaptive_cli/ con subdirectorios necesarios."""
    data_dir = Path.home() / DATA_DIR_NAME
    for sub in ("knowledge", "locks", "hook_state"):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)
    return data_dir


# ---------------------------------------------------------------------------
# Paso 4: Registrar hooks en Claude Code
# ---------------------------------------------------------------------------

def _find_claude_settings() -> list[Path]:
    """Candidatos de settings.json de Claude Code."""
    return [
        Path.home() / ".claude" / "settings.json",
        Path.cwd() / ".claude" / "settings.json",
    ]


def register_claude_hooks(install_dir: Path, python_exe: Path) -> list[Path]:
    """
    Registra los hooks de Motor_IA en Claude Code settings.json.
    Retorna la lista de archivos settings.json actualizados.
    """
    hooks_dir = install_dir / "hooks"
    python_cmd = str(python_exe).replace("\\", "/")
    updated = []

    for settings_path in _find_claude_settings():
        # Solo actualizar si el archivo ya existe (Claude Code ya instalado)
        if not settings_path.is_file():
            # Crear si es el settings global (~/.claude/settings.json)
            if settings_path == Path.home() / ".claude" / "settings.json":
                settings_path.parent.mkdir(parents=True, exist_ok=True)
                settings = {}
            else:
                continue
        else:
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
            except Exception:
                settings = {}

        if "hooks" not in settings:
            settings["hooks"] = []
        if not isinstance(settings["hooks"], list):
            settings["hooks"] = []

        # Eliminar hooks previos de Motor_IA
        motor_marker = str(hooks_dir).replace("\\", "/")
        settings["hooks"] = [
            h for h in settings["hooks"]
            if motor_marker not in h.get("command", "").replace("\\", "/")
        ]

        # Agregar nuevos hooks
        for event, script in HOOK_SCRIPTS.items():
            script_path = str(hooks_dir / script).replace("\\", "/")
            settings["hooks"].append({
                "type": event,
                "command": f'"{python_cmd}" "{script_path}"',
            })

        settings_path.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        updated.append(settings_path)

    return updated


# ---------------------------------------------------------------------------
# Paso 5: Verificacion
# ---------------------------------------------------------------------------

def verify_installation(install_dir: Path, python_exe: Path) -> bool:
    """Verifica que los archivos criticos existen."""
    checks = [
        install_dir / "config.py",
        install_dir / "core" / "knowledge_base.py",
        install_dir / "hooks" / "session_end.py",
        python_exe,
    ]
    ok = True
    for f in checks:
        if f.exists():
            _ok(f"  {f.name}")
        else:
            _err(f"  FALTA: {f}")
            ok = False
    return ok


# ---------------------------------------------------------------------------
# Guardar configuracion de instalacion
# ---------------------------------------------------------------------------

def save_install_config(install_dir: Path, python_exe: Path, data_dir: Path) -> None:
    """Guarda install_config.json en el directorio de instalacion y en datos."""
    # Usar sys.platform / sys.version (rapidos) en vez de platform.system() que
    # puede tardar mucho en algunos contextos de Windows embebido.
    cfg = {
        "version": VERSION,
        "app": APP_NAME,
        "install_dir": str(install_dir),
        "python_runtime": str(python_exe),
        "data_dir": str(data_dir),
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "installed_at": _iso_now(),
    }
    for dest in (install_dir / "install_config.json", data_dir / "install_config.json"):
        dest.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def _iso_now() -> str:
    import time
    t = time.localtime()
    return f"{t.tm_year}-{t.tm_mon:02d}-{t.tm_mday:02d}T{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} - Instalador Offline v{VERSION}"
    )
    parser.add_argument(
        "--dir", "-d",
        default=None,
        help="Directorio de instalacion (default: AppData/Local/Motor_IA en Windows)"
    )
    parser.add_argument(
        "--no-hooks",
        action="store_true",
        default=False,
        help="No registrar hooks en Claude Code CLI",
    )
    args = parser.parse_args()

    install_dir = Path(args.dir) if args.dir else _default_install_dir()

    # Banner
    print()
    print("=" * 60)
    print(f"  {APP_NAME} - Instalador Offline v{VERSION}")
    print("=" * 60)
    print(f"  Directorio de instalacion: {install_dir}")
    print()

    try:
        # ---- Localizar fuentes ----
        _sep("Verificando fuentes")
        motor_source = _find_motor_source()
        _ok(f"Motor_IA encontrado en: {motor_source}")

        bundle_python = _find_bundle_python()
        if bundle_python:
            _ok(f"Python embebido encontrado: {bundle_python}")
        else:
            _warn("Python embebido no encontrado en bundle/. Se usara Python del sistema.")

        # ---- Paso 1: Copiar motor ----
        _sep("Paso 1/5: Copiando Motor_IA")
        n = copy_motor_files(motor_source, install_dir)
        _ok(f"{n} archivos copiados a {install_dir}")

        # ---- Paso 2: Copiar Python embebido ----
        _sep("Paso 2/5: Instalando Python embebido")
        if bundle_python:
            python_exe = copy_embedded_python(bundle_python, install_dir)
            _ok(f"Python instalado en: {python_exe}")
        else:
            python_exe = Path(sys.executable)
            _warn(f"Usando Python del sistema: {python_exe}")

        # ---- Paso 2b: Instalar dependencias desde wheels offline ----
        _sep("Paso 2b/5: Instalando dependencias offline")
        _install_wheels_offline(install_dir, python_exe)

        # ---- Paso 2c: Pre-cargar modelo de embeddings ----
        _sep("Paso 2c/5: Configurando modelo de embeddings")
        _install_model_offline(install_dir, python_exe)

        # ---- Paso 3: Crear directorio de datos ----
        _sep("Paso 3/5: Creando directorio de datos")
        data_dir = create_data_dir()
        _ok(f"Directorio de datos: {data_dir}")

        # ---- Paso 4: Registrar hooks ----
        _sep("Paso 4/5: Registrando hooks en Claude Code")
        if args.no_hooks:
            _info("Omitido por --no-hooks")
        else:
            updated = register_claude_hooks(install_dir, python_exe)
            if updated:
                for p in updated:
                    _ok(f"Hooks registrados en: {p}")
            else:
                _warn("Claude Code settings.json no encontrado.")
                _info("Instala Claude Code CLI y vuelve a ejecutar, o agrega los hooks manualmente.")
                _info(f"Python para hooks: {python_exe}")
                _info(f"Hooks dir: {install_dir / 'hooks'}")

        # ---- Paso 5: Verificacion ----
        _sep("Paso 5/5: Verificando instalacion")
        ok = verify_installation(install_dir, python_exe)

        # Guardar config
        save_install_config(install_dir, python_exe, data_dir)
        _ok("install_config.json guardado")

        # ---- Resultado ----
        print()
        _sep("RESULTADO")
        if ok:
            print(f"  Motor_IA instalado correctamente.")
            print(f"  Motor:  {install_dir}")
            print(f"  Python: {python_exe}")
            print(f"  Datos:  {data_dir}")
            print()
            print("  PROXIMOS PASOS:")
            print("  1. Abre Claude Code CLI")
            print("  2. Los hooks se activan automaticamente")
            print("  3. Para TUI: ejecuta python_runtime\\python.exe -m core.tui")
            print()
            _sep()
            return 0
        else:
            _err("La instalacion tuvo problemas. Revisa los errores arriba.")
            return 1

    except FileNotFoundError as exc:
        _err(str(exc))
        return 2
    except PermissionError as exc:
        _err(f"Error de permisos: {exc}")
        _err("Intenta ejecutar como administrador.")
        return 3
    except Exception as exc:
        _err(f"Error inesperado: {exc}")
        import traceback
        traceback.print_exc()
        return 4


if __name__ == "__main__":
    sys.exit(main())
