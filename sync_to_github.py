#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_to_github.py - Sincroniza datos de aprendizaje a un repo GitHub privado
=============================================================================
Copia archivos seguros desde ~/.adaptive_cli/ a un repo de staging,
luego ejecuta git add + commit + push.

Formato chunk (anti-merge-conflicts):
  En vez de copiar archivos grandes que causan conflictos al hacer merge
  desde múltiples máquinas, exporta chunks comprimidos con timestamp.
  Cada maquina escribe su propio chunk file (por hostname), nunca pisa
  el de otra. Al restore, se fusionan todos los chunks.

Uso:
    python sync_to_github.py [--repo PATH] [--message "custom commit msg"]
    python sync_to_github.py --chunk           # usar formato chunk
    python sync_to_github.py --export-chunk    # solo exportar chunk local

Configuracion:
    - Env MOTOR_IA_SYNC_REPO  o  default ~/adaptive-cli-data
    - Archivos NUNCA sincronizados: pending_errors.json, *.env, credentials*
"""

import argparse
import gzip
import hashlib
import json
import os
import shutil
import socket
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
# Chunk sync (anti-merge-conflicts)
# ---------------------------------------------------------------------------

CHUNK_DIR_NAME = "chunks"  # subdirectorio dentro del repo para chunks

def _hostname_slug() -> str:
    """Slug del hostname para nombrar chunks por maquina."""
    h = socket.gethostname().lower()
    slug = "".join(c if c.isalnum() else "_" for c in h)[:20]
    return slug or "unknown"


def export_chunk(repo_dir: Path) -> Path:
    """
    Exporta un chunk comprimido del estado actual de Motor_IA.
    El chunk es un archivo .json.gz nombrado por hostname + timestamp.
    Formato: chunks/<hostname>_<timestamp>.json.gz

    Cada maquina escribe SOLO su propio chunk → sin merge conflicts.
    Al restore_from_github, todos los chunks se fusionan.

    Returns: path del chunk creado.
    """
    chunk_dir = repo_dir / CHUNK_DIR_NAME
    chunk_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    hostname = _hostname_slug()
    chunk_path = chunk_dir / f"{hostname}_{ts}.json.gz"

    payload = {
        "hostname":   hostname,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "version":    "1.0",
        "files":      {},
    }

    # Incluir archivos seguros en el payload
    for fname in SAFE_FILES:
        src = DATA_DIR / fname
        if src.exists():
            try:
                content = src.read_text(encoding="utf-8")
                payload["files"][fname] = content
            except Exception:
                pass

    # Incluir directorios seguros
    for dirname in SAFE_DIRS:
        src_dir = DATA_DIR / dirname
        if src_dir.is_dir():
            for item in src_dir.iterdir():
                if item.is_file() and not _matches_block(item.name):
                    try:
                        content = item.read_text(encoding="utf-8")
                        payload["files"][f"{dirname}/{item.name}"] = content
                    except Exception:
                        pass

    # Comprimir y escribir
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    with gzip.open(chunk_path, "wb") as f:
        f.write(raw)

    return chunk_path


def load_chunk(chunk_path: Path) -> dict:
    """Lee un chunk comprimido y retorna su payload."""
    with gzip.open(chunk_path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def merge_chunks(repo_dir: Path, output_dir: Path = None) -> dict:
    """
    Fusiona todos los chunks del repo en un estado unificado.
    El chunk mas reciente por archivo gana (last-write-wins por timestamp).

    Returns: {merged_files: N, chunks_read: N, sources: [hostname, ...]}
    """
    chunk_dir = repo_dir / CHUNK_DIR_NAME
    if not chunk_dir.exists():
        return {"merged_files": 0, "chunks_read": 0, "sources": []}

    if output_dir is None:
        output_dir = DATA_DIR

    # Ordenar chunks por timestamp (nombre de archivo)
    chunk_files = sorted(chunk_dir.glob("*.json.gz"))
    if not chunk_files:
        return {"merged_files": 0, "chunks_read": 0, "sources": []}

    # Acumular: clave = filename, valor = (timestamp, content)
    file_versions: dict = {}
    sources = []

    for cf in chunk_files:
        try:
            payload = load_chunk(cf)
            ts = payload.get("exported_at", cf.stem)
            host = payload.get("hostname", "unknown")
            if host not in sources:
                sources.append(host)
            for fname, content in payload.get("files", {}).items():
                if fname not in file_versions or ts > file_versions[fname][0]:
                    file_versions[fname] = (ts, content)
        except Exception:
            continue

    # Escribir archivos fusionados
    merged = 0
    for fname, (_, content) in file_versions.items():
        dest = output_dir / fname
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_text(content, encoding="utf-8")
            merged += 1
        except Exception:
            pass

    return {
        "merged_files": merged,
        "chunks_read": len(chunk_files),
        "sources": sources,
    }


def get_chunk_stats(repo_dir: Path) -> dict:
    """Estadisticas de chunks disponibles en el repo."""
    chunk_dir = repo_dir / CHUNK_DIR_NAME
    if not chunk_dir.exists():
        return {"chunks": 0, "machines": [], "total_size_kb": 0}

    chunks = list(chunk_dir.glob("*.json.gz"))
    machines = set()
    total_size = 0
    for cf in chunks:
        parts = cf.stem.split("_")
        if parts:
            machines.add(parts[0])
        total_size += cf.stat().st_size

    return {
        "chunks": len(chunks),
        "machines": sorted(machines),
        "total_size_kb": round(total_size / 1024, 1),
    }


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
    parser.add_argument(
        "--chunk",
        action="store_true",
        help="Usar formato chunk comprimido (anti-merge-conflicts para multi-maquina)",
    )
    parser.add_argument(
        "--export-chunk",
        action="store_true",
        dest="export_chunk",
        help="Solo exportar chunk local sin push",
    )
    parser.add_argument(
        "--merge-chunks",
        action="store_true",
        dest="merge_chunks",
        help="Fusionar todos los chunks del repo en DATA_DIR local",
    )
    parser.add_argument(
        "--chunk-stats",
        action="store_true",
        dest="chunk_stats",
        help="Mostrar estadisticas de chunks disponibles",
    )
    args = parser.parse_args()

    repo_path = args.repo
    if not repo_path:
        repo_path = os.environ.get("MOTOR_IA_SYNC_REPO")
    if not repo_path:
        repo_path = str(Path.home() / "adaptive-cli-data")

    repo_dir = Path(repo_path)

    try:
        if args.chunk_stats:
            stats = get_chunk_stats(repo_dir)
            print(json.dumps(stats, indent=2, ensure_ascii=False))
            sys.exit(0)

        if args.merge_chunks:
            result = merge_chunks(repo_dir)
            print(f"Merge OK: {result['merged_files']} archivos de {result['chunks_read']} chunks")
            print(f"Maquinas: {', '.join(result['sources'])}")
            sys.exit(0)

        if args.export_chunk:
            _ensure_repo(repo_dir)
            chunk_path = export_chunk(repo_dir)
            print(f"Chunk exportado: {chunk_path}")
            sys.exit(0)

        if args.chunk:
            _ensure_repo(repo_dir)
            chunk_path = export_chunk(repo_dir)
            _git(repo_dir, "add", str(chunk_path.relative_to(repo_dir)))
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            msg = args.message or f"chunk: {_hostname_slug()} {ts}"
            _git(repo_dir, "commit", "-m", msg)
            pushed = False
            push_result = _git(repo_dir, "push", check=False)
            if push_result.returncode == 0:
                pushed = True
            print(f"Chunk sync OK: {chunk_path.name} | pushed={pushed}")
            sys.exit(0)

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
