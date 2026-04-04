#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kb_versioning.py - Feature 8: Git-Backed Memory con Rollback
=============================================================
Cada cambio al KB genera un micro-commit en un branch dedicado.
Permite rollback por dominio y fecha.

Usa el repo git existente del proyecto, branch 'kb-history'.
"""

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from config import PROJECT_ROOT, KNOWLEDGE_DIR, DATA_DIR

log = logging.getLogger("kb_versioning")

VERSION_LOG_FILE = DATA_DIR / "kb_version_log.json"
MAX_VERSION_LOG = 500


def _run_git(*args, timeout=10) -> tuple[bool, str]:
    """Ejecuta comando git y retorna (success, output)."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout.strip() or result.stderr.strip()
    except Exception as e:
        return False, str(e)


def record_change(domain: str, change_type: str, key: str = "", details: str = ""):
    """
    Registra un cambio en el KB en el log de versiones.
    No hace git commit automático (sería muy lento), solo log.
    Los commits se hacen en batch con commit_pending().
    """
    log_data = _load_version_log()
    log_data.append({
        "domain": domain,
        "type": change_type,
        "key": key[:100],
        "details": details[:200],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "committed": False,
    })

    # Limitar tamaño
    if len(log_data) > MAX_VERSION_LOG:
        log_data = log_data[-MAX_VERSION_LOG:]

    _save_version_log(log_data)


def _load_version_log() -> list:
    if VERSION_LOG_FILE.exists():
        try:
            return json.loads(VERSION_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_version_log(data: list):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VERSION_LOG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_pending_changes() -> list[dict]:
    """Retorna cambios no commiteados."""
    log_data = _load_version_log()
    return [e for e in log_data if not e.get("committed")]


def commit_pending(message: str = "") -> dict:
    """Commitea cambios pendientes del KB."""
    pending = get_pending_changes()
    if not pending:
        return {"success": True, "message": "Sin cambios pendientes"}

    # Construir mensaje de commit
    if not message:
        domains = list(set(p["domain"] for p in pending))[:5]
        types = list(set(p["type"] for p in pending))
        message = f"kb: {len(pending)} changes in {', '.join(domains)} ({', '.join(types)})"

    # Stage archivos de knowledge
    ok, out = _run_git("add", "knowledge/")
    if not ok:
        return {"success": False, "message": f"git add failed: {out}"}

    ok, out = _run_git("commit", "-m", message, timeout=30)
    if not ok:
        if "nothing to commit" in out:
            return {"success": True, "message": "Sin cambios en disco"}
        return {"success": False, "message": f"git commit failed: {out}"}

    # Marcar como commiteados
    log_data = _load_version_log()
    for entry in log_data:
        if not entry.get("committed"):
            entry["committed"] = True
    _save_version_log(log_data)

    return {"success": True, "message": f"Committed: {message}", "changes": len(pending)}


def rollback_domain(domain: str, target_date: str = "") -> dict:
    """
    Rollback de un dominio específico a una fecha.
    Usa git log + git checkout para restaurar archivos.
    """
    domain_path = f"knowledge/{domain}/"

    # Buscar commits que tocaron este dominio
    ok, log_output = _run_git(
        "log", "--oneline", "--follow", "-20", "--", domain_path,
        timeout=15,
    )
    if not ok or not log_output:
        return {"success": False, "message": f"Sin historial para {domain}"}

    commits = []
    for line in log_output.split("\n"):
        parts = line.strip().split(" ", 1)
        if len(parts) >= 2:
            commits.append({"hash": parts[0], "message": parts[1]})

    if not commits:
        return {"success": False, "message": "No hay commits"}

    if target_date:
        # Buscar commit más cercano a la fecha
        ok, date_commit = _run_git(
            "log", "--oneline", f"--before={target_date}", "-1", "--", domain_path,
            timeout=15,
        )
        if ok and date_commit:
            target_hash = date_commit.split(" ")[0]
        else:
            return {"success": False, "message": f"Sin commit antes de {target_date}"}
    else:
        # Rollback al commit anterior (el penúltimo)
        if len(commits) < 2:
            return {"success": False, "message": "Solo hay un commit, no se puede rollback"}
        target_hash = commits[1]["hash"]

    # Restaurar archivos del dominio desde ese commit
    ok, out = _run_git("checkout", target_hash, "--", domain_path, timeout=15)
    if not ok:
        return {"success": False, "message": f"Rollback failed: {out}"}

    return {
        "success": True,
        "message": f"Dominio {domain} restaurado a {target_hash}",
        "commit": target_hash,
        "available_commits": commits[:10],
    }


def get_domain_history(domain: str, limit: int = 20) -> list[dict]:
    """Historial de commits para un dominio específico."""
    domain_path = f"knowledge/{domain}/"
    ok, log_output = _run_git(
        "log", "--oneline", f"-{limit}", "--", domain_path,
        timeout=15,
    )
    if not ok:
        return []

    commits = []
    for line in log_output.split("\n"):
        parts = line.strip().split(" ", 1)
        if len(parts) >= 2:
            commits.append({"hash": parts[0], "message": parts[1]})
    return commits


def get_versioning_stats() -> dict:
    """Estadísticas para dashboard."""
    pending = get_pending_changes()
    log_data = _load_version_log()
    return {
        "total_changes_logged": len(log_data),
        "pending_commits": len(pending),
        "committed": len([e for e in log_data if e.get("committed")]),
    }
