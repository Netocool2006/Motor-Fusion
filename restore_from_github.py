#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
restore_from_github.py - Restaura datos de aprendizaje desde un repo GitHub
============================================================================
Clona (o pull) el repo de sync y copia los archivos a ~/.adaptive_cli/.
Verifica integridad: cuenta patrones, dominios y sesiones.

Uso:
    python restore_from_github.py [--repo URL_O_PATH] [--data-dir PATH]

Ejemplo (PC nueva):
    python restore_from_github.py --repo https://github.com/Netocool2006/adaptive-cli-data.git

Ejemplo (repo ya clonado localmente):
    python restore_from_github.py --repo ~/adaptive-cli-data
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_DATA_DIR = Path.home() / ".adaptive_cli"
DEFAULT_LOCAL_REPO = Path.home() / "adaptive-cli-data"

# Files and dirs to restore (mirrors sync_to_github.py SAFE lists)
SAFE_FILES = [
    "learned_patterns.json",
    "session_history.json",
    "execution_log.jsonl",
    "episodic_index.db",
    "sap_playbook.db",
]

SAFE_DIRS = [
    "knowledge",
]

NEVER_RESTORE = [
    "pending_errors.json",
    ".env",
    "credentials.json",
    "motor_auth.json",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
    )


def _is_remote_url(value: str) -> bool:
    """Detect if the string is a git remote URL (https, ssh, git://)."""
    return (
        value.startswith("https://")
        or value.startswith("http://")
        or value.startswith("git@")
        or value.startswith("git://")
        or value.startswith("ssh://")
    )


def _ensure_local_repo(repo_arg: str) -> Path:
    """
    If repo_arg is a URL, clone it to ~/adaptive-cli-data.
    If it is a local path, do a git pull.
    Returns the local Path to the repo.
    """
    if _is_remote_url(repo_arg):
        local = DEFAULT_LOCAL_REPO
        if (local / ".git").is_dir():
            print(f"Repo ya existe en {local}, haciendo pull...")
            _git(local, "pull", "--ff-only", check=False)
        else:
            print(f"Clonando {repo_arg} -> {local} ...")
            local.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", repo_arg, str(local)],
                check=True,
                capture_output=True,
                text=True,
            )
        return local
    else:
        local = Path(repo_arg).expanduser().resolve()
        if not (local / ".git").is_dir():
            print(f"Error: {local} no es un repo git.", file=sys.stderr)
            sys.exit(1)
        print(f"Repo local detectado en {local}, haciendo pull...")
        _git(local, "pull", "--ff-only", check=False)
        return local


def _count_patterns(data: object) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        return len(data.get("patterns", data.get("entries", [])))
    return 0


def _count_sessions(data: object) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        return len(data.get("sessions", data.get("entries", [])))
    return 0


# ---------------------------------------------------------------------------
# Core restore
# ---------------------------------------------------------------------------

def restore(repo_dir: Path, data_dir: Path) -> dict:
    """
    Copy safe files from repo_dir into data_dir.
    Returns verification summary.
    """
    data_dir.mkdir(parents=True, exist_ok=True)

    files_restored = 0

    # --- Individual files ---
    for fname in SAFE_FILES:
        src = repo_dir / fname
        if src.exists():
            dst = data_dir / fname
            shutil.copy2(str(src), str(dst))
            files_restored += 1

    # --- Directories ---
    for dirname in SAFE_DIRS:
        src_dir = repo_dir / dirname
        if src_dir.is_dir():
            dst_dir = data_dir / dirname
            dst_dir.mkdir(parents=True, exist_ok=True)
            for item in src_dir.iterdir():
                if item.is_file() and item.name not in NEVER_RESTORE:
                    shutil.copy2(str(item), str(dst_dir / item.name))
                    files_restored += 1

    # --- Verify integrity ---
    n_patterns = 0
    patterns_file = data_dir / "learned_patterns.json"
    if patterns_file.exists():
        try:
            raw = json.loads(patterns_file.read_text(encoding="utf-8"))
            n_patterns = _count_patterns(raw)
        except (json.JSONDecodeError, OSError):
            pass

    n_domains = 0
    knowledge_dir = data_dir / "knowledge"
    if knowledge_dir.is_dir():
        n_domains = len([f for f in knowledge_dir.iterdir() if f.suffix == ".json"])

    n_sessions = 0
    session_file = data_dir / "session_history.json"
    if session_file.exists():
        try:
            raw = json.loads(session_file.read_text(encoding="utf-8"))
            n_sessions = _count_sessions(raw)
        except (json.JSONDecodeError, OSError):
            pass

    summary = f"Restored: {n_patterns} patrones, {n_domains} dominios, {n_sessions} sesiones"
    print(summary)

    return {
        "patterns": n_patterns,
        "domains": n_domains,
        "sessions": n_sessions,
        "files_restored": files_restored,
        "data_dir": str(data_dir),
        "message": summary,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restaura datos de Motor_IA desde un repo GitHub."
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="URL del repo remoto o path local (default: ~/adaptive-cli-data)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Directorio destino de datos (default: ~/.adaptive_cli)",
    )
    args = parser.parse_args()

    repo_arg = args.repo or str(DEFAULT_LOCAL_REPO)
    data_dir = Path(args.data_dir) if args.data_dir else DEFAULT_DATA_DIR

    try:
        repo_dir = _ensure_local_repo(repo_arg)
        result = restore(repo_dir, data_dir)
        sys.exit(0)
    except subprocess.CalledProcessError as exc:
        print(f"Error git: {exc.stderr or exc.stdout}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
