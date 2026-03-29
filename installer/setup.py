#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
installer/setup.py - Instalador del Motor_IA unificado
======================================================
Detecta OS, crea ~/.adaptive_cli/, copia el motor, registra hooks
en Claude Code CLI (y opcionalmente otros CLIs), y configura MCP server.

Uso:
    python installer/setup.py [--cli claude|gemini|ollama|all] [--mcp]

Ejemplo:
    python installer/setup.py --cli claude --mcp
    python installer/setup.py --cli all
"""

import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MOTOR_IA_VERSION = "1.0.0-fusion"
DATA_DIR_NAME = ".adaptive_cli"
MOTOR_INSTALL_DIR_NAME = "Motor_IA"

SUPPORTED_CLIS = ["claude", "gemini", "ollama", "all"]

# Hooks that Claude Code CLI needs registered
CLAUDE_CODE_HOOKS = {
    "UserMessage": {
        "type": "command",
        "command": "python {motor_dir}/hooks/on_user_message.py",
        "event": "UserMessage",
    },
    "Stop": {
        "type": "command",
        "command": "python {motor_dir}/hooks/on_session_end.py",
        "event": "Stop",
    },
    "ToolUse": {
        "type": "command",
        "command": "python {motor_dir}/hooks/on_tool_use.py",
        "event": "ToolUse",
    },
}


# ---------------------------------------------------------------------------
# OS detection
# ---------------------------------------------------------------------------

def detect_os() -> dict:
    """Return OS info dict."""
    system = platform.system()  # Windows, Darwin, Linux
    info = {
        "system": system,
        "platform": sys.platform,
        "machine": platform.machine(),
        "release": platform.release(),
        "home": str(Path.home()),
    }
    if system == "Windows":
        info["shell"] = "powershell"
        info["local_appdata"] = os.environ.get("LOCALAPPDATA", "")
    elif system == "Darwin":
        info["shell"] = "zsh"
    else:
        info["shell"] = os.environ.get("SHELL", "/bin/bash")
    return info


# ---------------------------------------------------------------------------
# Directory setup
# ---------------------------------------------------------------------------

def ensure_data_dir() -> Path:
    """Create ~/.adaptive_cli/ with required subdirectories."""
    data_dir = Path.home() / DATA_DIR_NAME
    subdirs = ["knowledge", "locks", "hook_state"]
    data_dir.mkdir(parents=True, exist_ok=True)
    for sub in subdirs:
        (data_dir / sub).mkdir(exist_ok=True)
    return data_dir


def get_motor_source_dir() -> Path:
    """Get the Motor_IA source directory (parent of installer/)."""
    return Path(__file__).resolve().parent.parent


def install_motor_code(data_dir: Path) -> Path:
    """
    Copy Motor_IA source to a stable install location.
    On Windows: %LOCALAPPDATA%/Motor_IA/
    On Unix:    ~/.local/share/Motor_IA/
    Returns the install path.
    """
    source = get_motor_source_dir()

    if platform.system() == "Windows":
        local_app = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        install_dir = Path(local_app) / MOTOR_INSTALL_DIR_NAME
    else:
        install_dir = Path.home() / ".local" / "share" / MOTOR_INSTALL_DIR_NAME

    # Copy source tree (skip __pycache__, .git, installer/assets)
    if install_dir.exists():
        shutil.rmtree(str(install_dir), ignore_errors=True)

    def _ignore(directory: str, contents: list[str]) -> list[str]:
        skip = []
        for name in contents:
            if name in ("__pycache__", ".git", ".env", "credentials.json", "motor_auth.json"):
                skip.append(name)
            if name.endswith((".pyc", ".pyo", ".dll", ".exe")):
                skip.append(name)
        return skip

    shutil.copytree(str(source), str(install_dir), ignore=_ignore)
    print(f"  Motor instalado en: {install_dir}")
    return install_dir


# ---------------------------------------------------------------------------
# Claude Code CLI hooks registration
# ---------------------------------------------------------------------------

def _find_claude_settings_paths() -> list[Path]:
    """Return candidate settings.json paths for Claude Code CLI."""
    candidates = []
    home = Path.home()

    # User-level settings
    candidates.append(home / ".claude" / "settings.json")

    # Project-level (current working directory)
    cwd = Path.cwd()
    candidates.append(cwd / ".claude" / "settings.json")

    return candidates


def register_claude_hooks(motor_dir: Path) -> None:
    """Register Motor_IA hooks in Claude Code CLI settings.json."""
    python_cmd = sys.executable  # full path to current Python

    settings_paths = _find_claude_settings_paths()

    for settings_path in settings_paths:
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing settings or start fresh
        settings = {}
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                settings = {}

        # Ensure hooks section exists
        if "hooks" not in settings:
            settings["hooks"] = {}

        for event_name, hook_def in CLAUDE_CODE_HOOKS.items():
            cmd = hook_def["command"].replace(
                "{motor_dir}", str(motor_dir).replace("\\", "/")
            )
            # Use the full Python path
            cmd = cmd.replace("python ", f"{python_cmd} ")

            hook_entry = {
                "type": "command",
                "command": cmd,
            }

            if event_name not in settings["hooks"]:
                settings["hooks"][event_name] = []

            # Check if hook already registered (avoid duplicates)
            existing_cmds = [
                h.get("command", "") for h in settings["hooks"][event_name]
                if isinstance(h, dict)
            ]
            if cmd not in existing_cmds:
                settings["hooks"][event_name].append(hook_entry)

        settings_path.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  Hooks registrados en: {settings_path}")


# ---------------------------------------------------------------------------
# Gemini CLI adapter
# ---------------------------------------------------------------------------

def register_gemini_adapter(motor_dir: Path) -> None:
    """
    Register Motor_IA for Gemini CLI.
    Gemini CLI uses GEMINI_CLI_HOOKS env or ~/.gemini/hooks/ directory.
    """
    gemini_hooks_dir = Path.home() / ".gemini" / "hooks"
    gemini_hooks_dir.mkdir(parents=True, exist_ok=True)

    # Write a wrapper script
    wrapper = gemini_hooks_dir / "motor_ia_hook.py"
    python_cmd = sys.executable
    motor_str = str(motor_dir).replace("\\", "/")

    wrapper.write_text(
        f'#!/usr/bin/env python3\n'
        f'"""Motor_IA hook bridge for Gemini CLI."""\n'
        f'import sys\n'
        f'sys.path.insert(0, "{motor_str}")\n'
        f'from adapters.gemini import GeminiAdapter\n'
        f'adapter = GeminiAdapter()\n'
        f'adapter.run_hook(sys.argv[1] if len(sys.argv) > 1 else "message")\n',
        encoding="utf-8",
    )
    print(f"  Gemini hook registrado en: {wrapper}")


# ---------------------------------------------------------------------------
# Ollama adapter
# ---------------------------------------------------------------------------

def register_ollama_adapter(motor_dir: Path) -> None:
    """
    Register Motor_IA for Ollama-based CLIs.
    Creates a wrapper in ~/.ollama/hooks/ for custom integrations.
    """
    ollama_dir = Path.home() / ".ollama" / "hooks"
    ollama_dir.mkdir(parents=True, exist_ok=True)

    wrapper = ollama_dir / "motor_ia_hook.py"
    motor_str = str(motor_dir).replace("\\", "/")

    wrapper.write_text(
        f'#!/usr/bin/env python3\n'
        f'"""Motor_IA hook bridge for Ollama-based CLIs."""\n'
        f'import sys\n'
        f'sys.path.insert(0, "{motor_str}")\n'
        f'from adapters.ollama import OllamaAdapter\n'
        f'adapter = OllamaAdapter()\n'
        f'adapter.run_hook(sys.argv[1] if len(sys.argv) > 1 else "message")\n',
        encoding="utf-8",
    )
    print(f"  Ollama hook registrado en: {wrapper}")


# ---------------------------------------------------------------------------
# MCP server setup
# ---------------------------------------------------------------------------

def setup_mcp_server(motor_dir: Path) -> None:
    """
    Register Motor_IA as an MCP server for Claude Desktop.
    Writes to ~/Library/Application Support/Claude/claude_desktop_config.json (Mac)
    or %APPDATA%/Claude/claude_desktop_config.json (Windows).
    """
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        config_path = Path(appdata) / "Claude" / "claude_desktop_config.json"
    elif platform.system() == "Darwin":
        config_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        config_path = Path.home() / ".config" / "claude" / "claude_desktop_config.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)

    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            config = {}

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    mcp_script = str(motor_dir / "mcp_server.py").replace("\\", "/")

    config["mcpServers"]["motor-ia"] = {
        "command": sys.executable,
        "args": [mcp_script],
        "env": {
            "MOTOR_IA_DATA": str(Path.home() / DATA_DIR_NAME),
        },
    }

    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  MCP server registrado en: {config_path}")


# ---------------------------------------------------------------------------
# Main installer
# ---------------------------------------------------------------------------

def install(cli_targets: list[str], setup_mcp: bool = False) -> None:
    """Run the full installation."""
    os_info = detect_os()
    print(f"Motor_IA Installer v{MOTOR_IA_VERSION}")
    print(f"  OS: {os_info['system']} ({os_info['machine']})")
    print(f"  Home: {os_info['home']}")
    print()

    # 1. Create data directory
    print("[1/4] Creando directorio de datos...")
    data_dir = ensure_data_dir()
    print(f"  Data dir: {data_dir}")

    # 2. Copy motor code to install location
    print("[2/4] Instalando codigo del motor...")
    motor_dir = install_motor_code(data_dir)

    # 3. Register hooks per CLI
    print("[3/4] Registrando hooks...")
    if "all" in cli_targets:
        cli_targets = ["claude", "gemini", "ollama"]

    for cli in cli_targets:
        if cli == "claude":
            register_claude_hooks(motor_dir)
        elif cli == "gemini":
            register_gemini_adapter(motor_dir)
        elif cli == "ollama":
            register_ollama_adapter(motor_dir)
        else:
            print(f"  WARN: CLI '{cli}' no reconocido, ignorando.")

    # 4. MCP server (optional)
    if setup_mcp:
        print("[4/4] Configurando MCP server...")
        setup_mcp_server(motor_dir)
    else:
        print("[4/4] MCP server: omitido (usa --mcp para activar)")

    # Summary
    print()
    print("=" * 60)
    print("Instalacion completada.")
    print(f"  Motor:  {motor_dir}")
    print(f"  Datos:  {data_dir}")
    print(f"  CLIs:   {', '.join(cli_targets)}")
    if setup_mcp:
        print("  MCP:    configurado")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Instalador del Motor_IA unificado."
    )
    parser.add_argument(
        "--cli",
        type=str,
        default="claude",
        help="CLI target: claude, gemini, ollama, all (default: claude)",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        default=False,
        help="Configurar MCP server para Claude Desktop",
    )
    args = parser.parse_args()

    cli_targets = [c.strip().lower() for c in args.cli.split(",")]
    for c in cli_targets:
        if c not in SUPPORTED_CLIS:
            print(f"Error: CLI '{c}' no soportado. Opciones: {SUPPORTED_CLIS}")
            sys.exit(1)

    install(cli_targets, setup_mcp=args.mcp)


if __name__ == "__main__":
    main()
