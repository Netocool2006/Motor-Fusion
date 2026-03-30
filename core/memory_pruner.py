# -*- coding: utf-8 -*-
"""
memory_pruner.py -- Auto-pruning de patrones de baja calidad
=============================================================
Elimina (soft-delete) patrones que no aportan valor al Motor.

Criterios de poda (configurable via config.py):
  1. success_rate < AUTO_PRUNE_MIN_SUCCESS_RATE Y sin uso en X dias
  2. reuse_count == 0 Y creado hace > AUTO_PRUNE_DAYS_UNUSED dias

Motor_IA CONSERVA:
  - Soft-delete (deleted_at) en lugar de borrado fisico -> auditoria intacta
  - Los 3-tier dedup siguen funcionando con patrones activos
  - Los patrones podados son recuperables si se necesita

Ejecutado automaticamente desde session_end cada N sesiones.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from config import (
    MEMORY_FILE,
    AUTO_PRUNE_ENABLED,
    AUTO_PRUNE_MIN_SUCCESS_RATE,
    AUTO_PRUNE_DAYS_UNUSED,
    AUTO_PRUNE_MIN_REUSES,
)
from core.file_lock import file_lock, _atomic_replace


def auto_prune(dry_run: bool = False) -> dict:
    """
    Busca y soft-delete patrones de baja calidad.

    Args:
        dry_run: Si True, retorna candidatos sin modificar nada.

    Returns:
        {"pruned": N, "candidates": [...], "dry_run": bool, "disabled": bool}
    """
    if not AUTO_PRUNE_ENABLED:
        return {"pruned": 0, "candidates": [], "dry_run": dry_run, "disabled": True}

    if not MEMORY_FILE.exists():
        return {"pruned": 0, "candidates": [], "dry_run": dry_run}

    now_ts = time.time()
    stale_cutoff = now_ts - (AUTO_PRUNE_DAYS_UNUSED * 86400)
    candidates = []

    with file_lock("learned_patterns"):
        try:
            data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"pruned": 0, "candidates": [], "dry_run": dry_run}

        patterns = data.get("patterns", {})

        for pid, p in patterns.items():
            if p.get("deleted_at"):
                continue  # ya eliminado

            success_rate = p.get("success_rate", 1.0)
            reuse_count  = p.get("reuse_count", 0)

            # Calcular last_used como timestamp
            last_used_str = p.get("last_used") or p.get("created_at", "")
            last_used_ts  = 0.0
            if last_used_str:
                try:
                    dt = datetime.fromisoformat(
                        last_used_str.replace("Z", "+00:00")
                    )
                    last_used_ts = dt.timestamp()
                except Exception:
                    pass

            is_stale       = last_used_ts < stale_cutoff
            is_low_quality = success_rate < AUTO_PRUNE_MIN_SUCCESS_RATE
            is_never_used  = reuse_count <= AUTO_PRUNE_MIN_REUSES

            if is_stale and (is_low_quality or is_never_used):
                candidates.append({
                    "id":           pid,
                    "task_type":    p.get("task_type", ""),
                    "context_key":  p.get("context_key", ""),
                    "success_rate": round(success_rate, 3),
                    "reuse_count":  reuse_count,
                    "last_used":    last_used_str,
                    "reason":       "low_quality" if is_low_quality else "unused",
                })

        if dry_run or not candidates:
            return {"pruned": 0, "candidates": candidates, "dry_run": dry_run}

        # Aplicar soft-delete
        now_iso = datetime.now(timezone.utc).isoformat()
        for c in candidates:
            pid = c["id"]
            if pid in patterns:
                patterns[pid]["deleted_at"]    = now_iso
                patterns[pid]["_prune_reason"] = c["reason"]

        # Actualizar stats
        if "stats" in data:
            data["stats"]["total_patterns"] = sum(
                1 for p in patterns.values() if not p.get("deleted_at")
            )

        data["patterns"] = patterns
        tmp = MEMORY_FILE.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _atomic_replace(tmp, MEMORY_FILE)

    return {"pruned": len(candidates), "candidates": candidates, "dry_run": False}


def get_prune_candidates() -> list:
    """Retorna candidatos a poda sin ejecutarla (alias dry_run=True)."""
    return auto_prune(dry_run=True)["candidates"]


def get_stats() -> dict:
    """Estadisticas del estado de poda del memory store."""
    if not MEMORY_FILE.exists():
        return {"active": 0, "pruned": 0, "candidates": 0}
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        patterns = data.get("patterns", {})
        active  = sum(1 for p in patterns.values() if not p.get("deleted_at"))
        pruned  = sum(
            1 for p in patterns.values()
            if p.get("deleted_at") and p.get("_prune_reason")
        )
        candidates = len(get_prune_candidates())
        return {"active": active, "pruned": pruned, "candidates": candidates}
    except Exception:
        return {"active": 0, "pruned": 0, "candidates": 0}
