#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cloud_sync.py - Feature 2: Cloud Sync automático
=================================================
Sync incremental del KB a GitHub automáticamente tras cada cambio.
Solo sincroniza lo nuevo (delta), no el KB completo.

Modos:
  - auto: se dispara tras save de un pattern/fact nuevo
  - manual: python core/cloud_sync.py push
  - restore: python core/cloud_sync.py pull
"""

import json
import hashlib
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from config import PROJECT_ROOT, KNOWLEDGE_DIR, DATA_DIR

log = logging.getLogger("cloud_sync")

SYNC_STATE_FILE = DATA_DIR / "cloud_sync_state.json"
SYNC_QUEUE_FILE = DATA_DIR / "cloud_sync_queue.json"
MAX_QUEUE_SIZE = 100
AUTO_SYNC_INTERVAL = 300  # 5 minutos mínimo entre syncs automáticos


def _load_sync_state() -> dict:
    if SYNC_STATE_FILE.exists():
        try:
            return json.loads(SYNC_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_sync": None, "last_commit": None, "total_syncs": 0, "errors": []}


def _save_sync_state(state: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SYNC_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_queue() -> list:
    if SYNC_QUEUE_FILE.exists():
        try:
            return json.loads(SYNC_QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_queue(queue: list):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Limitar tamaño de cola
    if len(queue) > MAX_QUEUE_SIZE:
        queue = queue[-MAX_QUEUE_SIZE:]
    SYNC_QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")


def enqueue_change(domain: str, change_type: str, key: str = ""):
    """
    Agrega un cambio a la cola de sync.
    Llamar desde knowledge_base.py tras cada add_pattern/add_fact.
    """
    queue = _load_queue()
    queue.append({
        "domain": domain,
        "type": change_type,
        "key": key,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save_queue(queue)
    log.debug(f"Enqueued: {change_type} in {domain}")


def should_auto_sync() -> bool:
    """Determina si debería ejecutarse un auto-sync."""
    queue = _load_queue()
    if not queue:
        return False

    state = _load_sync_state()
    last_sync = state.get("last_sync")
    if last_sync:
        try:
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(last_sync)).total_seconds()
            if elapsed < AUTO_SYNC_INTERVAL:
                return False
        except Exception:
            pass

    return len(queue) >= 5  # Al menos 5 cambios acumulados


def sync_push(message: str = "") -> dict:
    """
    Ejecuta git add + commit + push del proyecto completo.
    Solo commitea si hay cambios reales.
    """
    result = {"success": False, "message": "", "changes": 0}

    try:
        # Verificar que estamos en un repo git
        git_check = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=10,
        )
        if git_check.returncode != 0:
            result["message"] = "No es un repositorio git"
            return result

        # Ver si hay cambios
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=10,
        )
        changes = [l for l in status.stdout.strip().split("\n") if l.strip()]
        if not changes:
            result["message"] = "Sin cambios pendientes"
            result["success"] = True
            return result

        result["changes"] = len(changes)

        # Stage knowledge + core/data
        subprocess.run(
            ["git", "add", "knowledge/", "core/data/", "core/chroma_db/"],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=30,
        )

        # Commit
        if not message:
            queue = _load_queue()
            domains_changed = list(set(q["domain"] for q in queue))[:5]
            message = f"auto-sync: {len(queue)} changes in {', '.join(domains_changed)}"

        commit = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
        )
        if commit.returncode != 0:
            if "nothing to commit" in commit.stdout:
                result["message"] = "Sin cambios para commit"
                result["success"] = True
                return result
            result["message"] = f"Commit failed: {commit.stderr}"
            return result

        # Push
        push = subprocess.run(
            ["git", "push", "origin", "master"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=60,
        )
        if push.returncode != 0:
            result["message"] = f"Push failed: {push.stderr}"
            # El commit local quedó, no es grave
            result["success"] = True  # Commit local OK
            return result

        # Limpiar cola y actualizar estado
        _save_queue([])
        state = _load_sync_state()
        state["last_sync"] = datetime.now(timezone.utc).isoformat()
        state["last_commit"] = message
        state["total_syncs"] = state.get("total_syncs", 0) + 1
        _save_sync_state(state)

        result["success"] = True
        result["message"] = f"Synced: {len(changes)} files pushed"
        log.info(result["message"])

    except subprocess.TimeoutExpired:
        result["message"] = "Timeout durante sync"
    except Exception as e:
        result["message"] = f"Error: {e}"
        log.error(f"Sync error: {e}")

    return result


def sync_pull() -> dict:
    """Pull cambios desde remote."""
    try:
        pull = subprocess.run(
            ["git", "pull", "origin", "master", "--no-rebase"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=60,
        )
        return {
            "success": pull.returncode == 0,
            "message": pull.stdout.strip() or pull.stderr.strip(),
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def get_sync_status() -> dict:
    """Estado actual del sync (para dashboard)."""
    state = _load_sync_state()
    queue = _load_queue()
    return {
        **state,
        "pending_changes": len(queue),
        "should_sync": should_auto_sync(),
    }


def auto_sync_if_needed():
    """Llamar periódicamente (ej: desde post-hook). Sync solo si hay suficientes cambios."""
    if should_auto_sync():
        return sync_push()
    return {"success": True, "message": "No sync needed"}


# CLI
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "push":
        msg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        r = sync_push(msg)
        print(f"{'OK' if r['success'] else 'FAIL'}: {r['message']}")
    elif cmd == "pull":
        r = sync_pull()
        print(f"{'OK' if r['success'] else 'FAIL'}: {r['message']}")
    elif cmd == "status":
        s = get_sync_status()
        print(f"Last sync: {s.get('last_sync', 'never')}")
        print(f"Pending: {s['pending_changes']} changes")
        print(f"Total syncs: {s.get('total_syncs', 0)}")
        print(f"Should sync: {s['should_sync']}")
    else:
        print("Usage: cloud_sync.py [push|pull|status]")
