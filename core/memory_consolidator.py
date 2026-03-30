# -*- coding: utf-8 -*-
"""
memory_consolidator.py -- Consolidacion periodica de patrones similares
========================================================================
Con el tiempo, Motor_IA acumula patrones del mismo task_type que evolucionan
a formas muy similares. Este modulo los fusiona en un patron de mayor calidad.

Diferencia clave con dedup (3-tier en learning_memory):
  - Dedup:          previene duplicados AL CREAR un patron nuevo
  - Consolidacion:  fusiona patrones YA EXISTENTES que son similares

Motor_IA ventaja conservada:
  - Los patrones originales quedan soft-deleted (auditoria intacta)
  - El patron consolidado hereda el reuse_count acumulado de todos
  - Las notas de todos los originales se preservan en _consolidated_notes
  - Los tags se unen (union de todos)

Ejecutado periodicamente desde session_end.
"""

import json
import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from config import (
    MEMORY_FILE,
    CONSOLIDATION_ENABLED,
    CONSOLIDATION_MIN_PATTERNS,
    CONSOLIDATION_SIMILARITY_THRESHOLD,
)
from core.file_lock import file_lock, _atomic_replace


# -- Helpers -------------------------------------------------------------------

def _jaccard(a: str, b: str) -> float:
    """Similitud Jaccard entre dos strings."""
    sa = set(re.findall(r'\w+', a.lower()))
    sb = set(re.findall(r'\w+', b.lower()))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _merge_solutions(solutions: list) -> dict:
    """Fusiona varias solutions en una consolidada."""
    if not solutions:
        return {}
    if len(solutions) == 1:
        return dict(solutions[0]) if isinstance(solutions[0], dict) else {}

    # Base = el mas reciente (ultimo)
    valid = [s for s in solutions if isinstance(s, dict)]
    if not valid:
        return {}

    merged = dict(valid[-1])

    # Recopilar notas de todos
    all_notes = []
    for s in valid:
        for key in ("notes", "note", "description"):
            note = s.get(key, "")
            if note and note not in all_notes:
                all_notes.append(str(note)[:200])

    if all_notes:
        merged["_consolidated_notes"] = all_notes
    merged["_consolidated_from_count"] = len(valid)
    return merged


def _cluster_patterns(type_patterns: list) -> list:
    """
    Agrupa patrones por similitud de context_key.
    Retorna lista de clusters (cada cluster es lista de (pid, pattern)).
    """
    used = set()
    clusters = []

    for i, (pid_a, p_a) in enumerate(type_patterns):
        if pid_a in used:
            continue

        cluster = [(pid_a, p_a)]
        key_a = p_a.get("context_key", "")

        for j, (pid_b, p_b) in enumerate(type_patterns):
            if i == j or pid_b in used:
                continue

            key_b = p_b.get("context_key", "")
            if _jaccard(key_a, key_b) >= CONSOLIDATION_SIMILARITY_THRESHOLD:
                cluster.append((pid_b, p_b))
                used.add(pid_b)

        if len(cluster) >= 2:
            used.add(pid_a)
            clusters.append(cluster)

    return clusters


# -- API publica ---------------------------------------------------------------

def consolidate(dry_run: bool = False) -> dict:
    """
    Encuentra grupos de patrones similares y los fusiona.

    Args:
        dry_run: Si True, retorna candidatos sin modificar nada.

    Returns:
        {"consolidated": N, "groups": [...], "dry_run": bool}
    """
    if not CONSOLIDATION_ENABLED:
        return {"consolidated": 0, "groups": [], "dry_run": dry_run, "disabled": True}

    if not MEMORY_FILE.exists():
        return {"consolidated": 0, "groups": [], "dry_run": dry_run}

    with file_lock("learned_patterns"):
        try:
            data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"consolidated": 0, "groups": [], "dry_run": dry_run}

        patterns = data.get("patterns", {})

        # Agrupar patrones activos por task_type
        by_type = defaultdict(list)
        for pid, p in patterns.items():
            if not p.get("deleted_at"):
                by_type[p.get("task_type", "unknown")].append((pid, p))

        # Encontrar clusters consolidables
        all_clusters = []
        for task_type, type_patterns in by_type.items():
            if len(type_patterns) < CONSOLIDATION_MIN_PATTERNS:
                continue
            clusters = _cluster_patterns(type_patterns)
            for cluster in clusters:
                all_clusters.append((task_type, cluster))

        group_summaries = [
            {"task_type": tt, "size": len(cl), "pids": [p for p, _ in cl]}
            for tt, cl in all_clusters
        ]

        if dry_run or not all_clusters:
            return {
                "consolidated": 0,
                "groups":       group_summaries,
                "dry_run":      dry_run,
            }

        now_iso = datetime.now(timezone.utc).isoformat()
        consolidated_count = 0

        for task_type, cluster in all_clusters:
            pids           = [pid for pid, _ in cluster]
            group_patterns = [p   for _,   p in cluster]

            # Mejor patron = mayor success_rate * max(1, reuse_count)
            best_p = max(
                group_patterns,
                key=lambda p: p.get("success_rate", 0.5) * max(1, p.get("reuse_count", 0))
            )

            # Merge solution y tags
            solutions    = [p.get("solution", {}) for p in group_patterns]
            merged_sol   = _merge_solutions(solutions)

            all_tags = []
            for p in group_patterns:
                for t in p.get("tags", []):
                    if t not in all_tags:
                        all_tags.append(t)

            # ID deterministico del consolidado
            combined_key = "+".join(sorted(pids))
            cid = hashlib.sha256(combined_key.encode()).hexdigest()[:12]

            total_reuses = sum(p.get("reuse_count", 0) for p in group_patterns)
            avg_success  = sum(
                p.get("success_rate", 1.0) for p in group_patterns
            ) / len(group_patterns)

            patterns[cid] = {
                **best_p,
                "solution":            merged_sol,
                "tags":                all_tags,
                "reuse_count":         total_reuses,
                "success_rate":        round(avg_success, 3),
                "_consolidated":       True,
                "_consolidated_from":  pids,
                "_consolidated_at":    now_iso,
                "created_at":          now_iso,
                "last_used":           now_iso,
            }

            # Soft-delete los originales
            for pid in pids:
                patterns[pid]["deleted_at"]      = now_iso
                patterns[pid]["_superseded_by"]  = cid

            consolidated_count += 1

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

    return {
        "consolidated": consolidated_count,
        "groups":       group_summaries,
        "dry_run":      False,
    }


def get_consolidation_candidates() -> list:
    """Retorna grupos candidatos a consolidacion sin ejecutarla."""
    return consolidate(dry_run=True)["groups"]


def get_stats() -> dict:
    """Estadisticas del estado de consolidacion."""
    if not MEMORY_FILE.exists():
        return {"consolidated_patterns": 0, "candidate_groups": 0}
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        patterns = data.get("patterns", {})
        consolidated = sum(
            1 for p in patterns.values()
            if p.get("_consolidated") and not p.get("deleted_at")
        )
        candidates = len(get_consolidation_candidates())
        return {
            "consolidated_patterns": consolidated,
            "candidate_groups":      candidates,
        }
    except Exception:
        return {"consolidated_patterns": 0, "candidate_groups": 0}
