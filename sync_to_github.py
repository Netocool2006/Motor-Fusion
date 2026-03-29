#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_to_github.py - Sincroniza datos de aprendizaje a un repo GitHub privado
=============================================================================
Copia archivos seguros desde ~/.adaptive_cli/ a un repo de staging,
luego ejecuta git add + commit + push.

Uso:
    python sync_to_github.py [--repo PATH] [--message "custom commit msg"]

Configuracion:
    - Env MOTOR_IA_SYNC_REPO  o  default ~/adaptive-cli-data
    - Archivos NUNCA sincronizados: pending_errors.json, *.env, credentials*
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve data dir (same logic as config.py, standalone for portability)
# ---------------------------------------------------------------------------

def _resolve_data_dir() -> Path:
    env_val = os.environ.get("MOTOR_IA_DATA")
    if env_val:
        p = Path(env_val)
        if p.is_absolute():
            return p
    return Path.home() / ".adaptive_cli"


DATA_DIR = _resolve_data_dir()

# ---------------------------------------------------------------------------
# What to sync / what to block
# ---------------------------------------------------------------------------

SAFE_FILES = [
    "learned_patterns.json",
    "session_history.json",
    "execution_log.jsonl",
    "episodic_index.db",
    "sap_playbook.db",
]

SAFE_DIRS = [
    "knowledge",  # knowledge/*.json  (13 dominios)
]

NEVER_SYNC_PATTERNS = [
    "pending_errors.json",
    "*.env",
    ".env",
    "credentials*",
    "motor_auth*",
    "*.dll",
    "*.exe",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _matches_block(name: str) -> bool:
    """Return True if filename matches any NEVER_SYNC pattern."""
    from fnmatch import fnmatch
    for pattern in NEVER_SYNC_PATTERNS:
        if fnmatch(name, pattern):
            return True
    return False


def _count_patterns(repo_dir: Path) -> tuple[int, int]:
    """Count patterns and domains synced to the repo."""
    n_patterns = 0
    n_domains = 0

    patterns_file = repo_dir / "learned_patterns.json"
    if patterns_file.exists():
        try:
            data = json.loads(patterns_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                n_patterns = len(data)
            elif isinstance(data, dict):
                n_patterns = len(data.get("patterns", data.get("entries", [])))
        except (json.JSONDecodeError, OSError):
            pass

    knowledge_dir = repo_dir / "knowledge"
    if knowledge_dir.is_dir():
        n_domains = len([f for f in knowledge_dir.iterdir()
                         if f.suffix == ".json" and not _matches_block(f.name)])

    return n_patterns, n_domains


def _git(repo_dir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command inside repo_dir."""
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        check=check,
    )


def _ensure_repo(repo_dir: Path) -> None:
    """Initialize git repo if it does not exist yet."""
    if not (repo_dir / ".git").is_dir():
        repo_dir.mkdir(parents=True, exist_ok=True)
        _git(repo_dir, "init")
        # Create .gitignore inside the sync repo
        gitignore = repo_dir / ".gitignore"
        gitignore.write_text(
            "pending_errors.json\n"
            "*.env\n"
            ".env\n"
            "credentials*\n"
            "motor_auth*\n"
            "*.dll\n"
            "*.exe\n",
            encoding="utf-8",
        )
        _git(repo_dir, "add", ".gitignore")
        _git(repo_dir, "commit", "-m", "Initial: add .gitignore")


# ---------------------------------------------------------------------------
# Core sync
# ---------------------------------------------------------------------------

def sync(repo_dir: Path, commit_message: str | None = None) -> dict:
    """
    Copy safe files from DATA_DIR to repo_dir, then git add + commit + push.

    Returns dict with summary: {patterns, domains, files_copied, pushed}.
    """
    _ensure_repo(repo_dir)

    files_copied = 0

    # --- Copy individual safe files ---
    for fname in SAFE_FILES:
        src = DATA_DIR / fname
        if src.exists():
            dst = repo_dir / fname
            shutil.copy2(str(src), str(dst))
            files_copied += 1

    # --- Copy safe directories ---
    for dirname in SAFE_DIRS:
        src_dir = DATA_DIR / dirname
        if src_dir.is_dir():
            dst_dir = repo_dir / dirname
            dst_dir.mkdir(parents=True, exist_ok=True)
            for item in src_dir.iterdir():
                if item.is_file() and not _matches_block(item.name):
                    shutil.copy2(str(item), str(dst_dir / item.name))
                    files_copied += 1

    # --- Git add + commit ---
    _git(repo_dir, "add", "-A")

    # Check if there is something to commit
    status = _git(repo_dir, "status", "--porcelain", check=False)
    if not status.stdout.strip():
        n_pat, n_dom = _count_patterns(repo_dir)
        summary = f"Sync OK (nada nuevo): {n_pat} patrones, {n_dom} dominios"
        print(summary)
        return {"patterns": n_pat, "domains": n_dom,
                "files_copied": 0, "pushed": False, "message": summary}

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not commit_message:
        commit_message = f"sync: {ts}"

    _git(repo_dir, "commit", "-m", commit_message)

    # --- Push (best-effort: may fail if no remote configured) ---
    pushed = False
    push_result = _git(repo_dir, "push", check=False)
    if push_result.returncode == 0:
        pushed = True

    n_pat, n_dom = _count_patterns(repo_dir)
    summary = f"Sync OK: {n_pat} patrones, {n_dom} dominios"
    if not pushed:
        summary += " (push pendiente: configura remote con 'git remote add origin <url>')"
    print(summary)

    return {
        "patterns": n_pat,
        "domains": n_dom,
        "files_copied": files_copied,
        "pushed": pushed,
        "message": summary,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sincroniza datos de Motor_IA a un repo GitHub privado."
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Path al repo local de sync (default: env MOTOR_IA_SYNC_REPO o ~/adaptive-cli-data)",
    )
    parser.add_argument(
        "--message", "-m",
        type=str,
        default=None,
        help="Mensaje de commit personalizado",
    )
    args = parser.parse_args()

    repo_path = args.repo
    if not repo_path:
        repo_path = os.environ.get("MOTOR_IA_SYNC_REPO")
    if not repo_path:
        repo_path = str(Path.home() / "adaptive-cli-data")

    repo_dir = Path(repo_path)

    try:
        result = sync(repo_dir, args.message)
        sys.exit(0 if result["files_copied"] >= 0 else 1)
    except subprocess.CalledProcessError as exc:
        print(f"Error git: {exc.stderr or exc.stdout}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
