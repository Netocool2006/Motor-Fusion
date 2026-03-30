"""
learning_memory.py -- Motor de Memoria Adaptativa Unificado
============================================================
Fusion de Motor 1 (Asistente IA) + Motor 2 (Motor_Inteligente_IA).

Sistema de aprendizaje incremental local que registra:
- Patrones de interaccion exitosos
- Errores encontrados y sus soluciones
- Contexto de ejecucion
- Correlacion automatica error -> fix

Inspirado en Engram (github.com/Gentleman-Programming/engram):
- Deduplicacion por hash + topic_key (3 tiers)
- Clasificacion por tipo (bugfix, decision, architecture, etc.)
- Scoping proyecto vs personal
- Soft deletes con deleted_at
- Protocolo anti-compaction
- Topic key suggestion para evitar fragmentacion

Flujo: intentar -> fallar -> corregir -> registrar -> reutilizar
"""

import json
import re
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import (
    MEMORY_FILE,
    ATTEMPTS_FILE,
    PENDING_ERRORS_FILE,
    EXECUTION_LOG,
    LOCK_DIR,
    DEDUP_WINDOW_SECS,
    ERROR_CORRELATION_WINDOW,
    CONFIDENCE_THRESHOLD,
    MAX_PENDING_ERRORS,
)
from core.file_lock import file_lock, _atomic_replace

# -- Tipos de memoria (17 tipos, inspirado en Engram) --
VALID_TYPES = {
    "bugfix", "decision", "architecture", "discovery", "pattern",
    "config", "preference", "manual", "session_summary", "file_change",
    "command", "file_read", "search", "tool_use", "passive", "learning",
    "bug", "error_fix",
}

# -- Scopes --
VALID_SCOPES = {"project", "personal"}

ERROR_PATTERNS = [
    r"Traceback \(most recent call last\)",
    r"Error:|ERROR:|Exception:",
    r"ModuleNotFoundError|ImportError|FileNotFoundError",
    r"Permission denied|command not found",
    r"exit code [1-9]",
    r"No such file or directory",
    r"SyntaxError|TypeError|ValueError|KeyError|AttributeError",
    r"FAILED|FAIL|fatal:",
    r"Cannot|cannot|Could not|could not",
    r"refused|denied|timeout|timed out",
]

SUCCESS_PATTERNS = [
    r"exit code 0",
    r"OK|completado|exitosa|correcto|successfully",
    r"Running on http://",
    r"created|installed|updated|saved|done",
    r"\d+ (?:files?|archivos?|rows?|items?|results?)",
]


# ══════════════════════════════════════════════════════════════
#  INTERNALS -- IO & Hashing
# ══════════════════════════════════════════════════════════════

def _ensure_dirs():
    """Crea directorios padre si no existen."""
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_memory() -> dict:
    """Carga la base de patrones aprendidos (con lock)."""
    _ensure_dirs()
    with file_lock("learned_patterns"):
        if MEMORY_FILE.exists():
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Ensure stats keys exist (self-healing)
                defaults = {"total_patterns": 0, "total_reuses": 0, "total_ai_calls_saved": 0}
                if "stats" not in data:
                    data["stats"] = defaults
                else:
                    for k, v in defaults.items():
                        if k not in data["stats"]:
                            data["stats"][k] = v
                if "patterns" not in data:
                    data["patterns"] = {}
                if "tag_index" not in data:
                    data["tag_index"] = {}
                return data
            except (json.JSONDecodeError, OSError):
                pass
    return {
        "version": "1.0",
        "patterns": {},
        "tag_index": {},
        "stats": {
            "total_patterns": 0,
            "total_reuses": 0,
            "total_ai_calls_saved": 0,
        },
    }


def _save_memory(mem: dict):
    """Guarda la base de patrones con atomic replace."""
    _ensure_dirs()
    with file_lock("learned_patterns"):
        tmp = MEMORY_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(mem, f, indent=2, ensure_ascii=False)
        _atomic_replace(tmp, MEMORY_FILE)


def _pattern_id(task_type: str, context_key: str) -> str:
    """Genera ID deterministico para un patron."""
    raw = f"{task_type}::{context_key}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _content_hash(content: str) -> str:
    """Hash normalizado del contenido para deduplicacion (Engram tier 2).
    Lowercase -> collapse whitespace -> SHA-256 -> hex[:16]."""
    normalized = re.sub(r'\s+', ' ', content.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def suggest_topic_key(task_type: str, context_key: str) -> str:
    """Genera topic_key jerarquico estable (Engram-style).
    Ej: 'architecture/sap-login', 'bugfix/iframe-timeout'."""
    family = task_type.lower().replace("_", "-")
    topic = re.sub(r'[^a-z0-9_\-]', '-', context_key.strip().lower())
    topic = re.sub(r'-+', '-', topic).strip('-')[:40]
    return f"{family}/{topic}"


def _normalize_key(text: str) -> str:
    """Normaliza un comando/tarea para matching -- elimina ruido de paths, numeros, strings."""
    t = text.strip().lower()
    t = re.sub(r'["\'].*?["\']', '""', t)
    t = re.sub(r'\b\d+\b', 'N', t)
    t = re.sub(r'[/\\]\S+', '/PATH', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def _similarity(a: str, b: str) -> float:
    """Similitud Jaccard sobre bigramas. Rapido y sin dependencias."""
    def bigrams(s):
        return set(s[i:i+2] for i in range(len(s) - 1))
    ba, bb = bigrams(a), bigrams(b)
    if not ba and not bb:
        return 1.0
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / len(ba | bb)


def _append_log(entry: dict):
    """Escribe una linea al log de ejecucion (append-only)."""
    _ensure_dirs()
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(EXECUTION_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _count_by_key(patterns: dict, key: str) -> dict:
    """Cuenta patrones agrupados por un campo."""
    counts = {}
    for p in patterns.values():
        val = p.get(key, "unknown")
        counts[val] = counts.get(val, 0) + 1
    return counts


# ══════════════════════════════════════════════════════════════
#  PATTERN API -- search, register, delete, reuse, update
# ══════════════════════════════════════════════════════════════

def search_pattern(
    task_type: str,
    context_key: str,
    tags: Optional[list] = None,
) -> Optional[dict]:
    """
    Busca un patron aprendido que coincida con la tarea actual.

    Estrategia de busqueda en 4 niveles:
    1) Exacta por ID deterministico
    2) Difusa por tags (requiere 2+ tags especificos en comun)
    3) Similitud de texto Jaccard > 0.8
    4) Miss -- territorio nuevo

    Returns:
        PatternEntry si encuentra match, None si es territorio nuevo.
    """
    mem = _load_memory()
    pid = _pattern_id(task_type, context_key)

    # 1) Busqueda exacta por ID (excluir soft-deleted)
    if pid in mem["patterns"] and not mem["patterns"][pid].get("deleted_at"):
        pattern = mem["patterns"][pid]
        pattern["stats"]["lookups"] += 1
        pattern["stats"]["last_lookup"] = datetime.now(timezone.utc).isoformat()
        _save_memory(mem)
        _append_log({
            "event": "pattern_hit",
            "pattern_id": pid,
            "task_type": task_type,
            "context_key": context_key,
        })
        return pattern

    # 2) Busqueda difusa por tags (requiere 2+ tags en comun, excluir soft-deleted)
    GENERIC_TAGS = {"bash", "cmd", "powershell", "auto_learned", "error_fix", "claude", "shell"}
    if tags:
        specific_tags = [t for t in tags if t not in GENERIC_TAGS]
        if specific_tags:
            tag_counts: dict = {}
            for tag in specific_tags:
                for cid in mem.get("tag_index", {}).get(tag, []):
                    tag_counts[cid] = tag_counts.get(cid, 0) + 1
            strong = [
                mem["patterns"][cid]
                for cid, count in tag_counts.items()
                if count >= 2 and cid in mem["patterns"]
                and not mem["patterns"][cid].get("deleted_at")
            ]
            if strong:
                best = max(strong, key=lambda p: p["stats"].get("success_rate", 0))
                if best["stats"].get("success_rate", 0) >= CONFIDENCE_THRESHOLD:
                    _append_log({
                        "event": "pattern_fuzzy_hit",
                        "matched_pattern": best["id"],
                        "search_tags": tags,
                    })
                    return best

    # 3) Busqueda por similitud de texto (score > 0.8, excluir soft-deleted)
    normalized = _normalize_key(context_key)
    best_match = None
    best_score = 0.0
    for p in mem["patterns"].values():
        if p.get("deleted_at"):
            continue
        score = _similarity(normalized, _normalize_key(p.get("context_key", "")))
        if score > 0.8 and score > best_score:
            best_score = score
            best_match = p
    if best_match and best_match["stats"].get("success_rate", 0) >= CONFIDENCE_THRESHOLD:
        _append_log({
            "event": "pattern_similarity_hit",
            "matched_pattern": best_match["id"],
            "similarity_score": round(best_score, 4),
        })
        return best_match

    # 4) No hay patron -> territorio nuevo
    _append_log({
        "event": "pattern_miss",
        "task_type": task_type,
        "context_key": context_key,
    })
    return None


def register_pattern(
    task_type: str,
    context_key: str,
    solution: dict,
    tags: Optional[list] = None,
    error_context: Optional[dict] = None,
    mem_type: str = "manual",
    scope: str = "project",
    topic_key: str = "",
    project: str = "",
) -> str:
    """
    Registra un patron con deduplicacion de 3 tiers (Engram-style).

    Tier 1 -- Topic Key Upsert: si topic_key coincide, actualiza.
    Tier 2 -- Content Hash: contenido identico en ventana DEDUP_WINDOW_SECS, incrementa duplicate_count.
    Tier 3 -- Nuevo: si no hay match, crea registro nuevo.

    Returns:
        pattern_id del patron registrado o actualizado.
    """
    mem = _load_memory()
    pid = _pattern_id(task_type, context_key)
    now = datetime.now(timezone.utc).isoformat()

    if mem_type not in VALID_TYPES:
        mem_type = "manual"
    if scope not in VALID_SCOPES:
        scope = "project"
    if not topic_key:
        topic_key = suggest_topic_key(task_type, context_key)

    content_str = json.dumps(solution, sort_keys=True, ensure_ascii=False)
    content_hash = _content_hash(content_str)

    # -- Tier 1: Topic Key Upsert --
    if topic_key:
        for existing_pid, existing in mem["patterns"].items():
            if (existing.get("topic_key") == topic_key
                    and existing.get("scope", "project") == scope
                    and not existing.get("deleted_at")):
                existing["solution"].update(solution)
                existing["updated_at"] = now
                existing["revision_count"] = existing.get("revision_count", 1) + 1
                existing["tags"] = list(set(existing.get("tags", []) + (tags or [])))
                if error_context:
                    existing["error_context"] = error_context
                _save_memory(mem)
                _append_log({
                    "event": "pattern_upsert_topic_key",
                    "pattern_id": existing_pid,
                    "topic_key": topic_key,
                    "revision": existing["revision_count"],
                })
                return existing_pid

    # -- Tier 2: Content Hash Match (ventana DEDUP_WINDOW_SECS) --
    for existing_pid, existing in mem["patterns"].items():
        if (existing.get("normalized_hash") == content_hash
                and existing.get("scope", "project") == scope
                and existing.get("mem_type", "manual") == mem_type
                and not existing.get("deleted_at")):
            try:
                existing_time = datetime.fromisoformat(existing.get("updated_at", now))
                if existing_time.tzinfo is None:
                    existing_time = existing_time.replace(tzinfo=timezone.utc)
                now_dt = datetime.fromisoformat(now)
                if now_dt.tzinfo is None:
                    now_dt = now_dt.replace(tzinfo=timezone.utc)
                elapsed = (now_dt - existing_time).total_seconds()
                if elapsed <= DEDUP_WINDOW_SECS:
                    existing["duplicate_count"] = existing.get("duplicate_count", 1) + 1
                    existing["updated_at"] = now
                    _save_memory(mem)
                    _append_log({
                        "event": "pattern_dedup_hash",
                        "pattern_id": existing_pid,
                        "duplicate_count": existing["duplicate_count"],
                    })
                    return existing_pid
            except (ValueError, TypeError):
                pass

    # -- Tier 3: Nuevo registro --
    entry = {
        "id": pid,
        "task_type": task_type,
        "context_key": context_key,
        "solution": solution,
        "tags": tags or [],
        "error_context": error_context,
        "mem_type": mem_type,
        "scope": scope,
        "topic_key": topic_key,
        "project": project,
        "normalized_hash": content_hash,
        "revision_count": 1,
        "duplicate_count": 1,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
        "stats": {
            "lookups": 0,
            "reuses": 0,
            "success_rate": 1.0,
            "last_lookup": None,
            "last_reuse": None,
        },
    }

    mem["patterns"][pid] = entry
    mem["stats"]["total_patterns"] = mem["stats"].get("total_patterns", len(mem["patterns"]) - 1) + 1

    for tag in (tags or []):
        if tag not in mem["tag_index"]:
            mem["tag_index"][tag] = []
        if pid not in mem["tag_index"][tag]:
            mem["tag_index"][tag].append(pid)

    _save_memory(mem)
    _append_log({
        "event": "pattern_registered",
        "pattern_id": pid,
        "task_type": task_type,
        "mem_type": mem_type,
        "scope": scope,
        "topic_key": topic_key,
        "solution_strategy": solution.get("strategy", "unknown"),
    })
    return pid


def soft_delete(pattern_id: str, reason: str = "") -> bool:
    """Soft delete -- marca con deleted_at pero no borra (Engram-style).
    Preserva para timeline/historial."""
    mem = _load_memory()
    if pattern_id not in mem["patterns"]:
        return False
    mem["patterns"][pattern_id]["deleted_at"] = datetime.now(timezone.utc).isoformat()
    if reason:
        mem["patterns"][pattern_id]["delete_reason"] = reason
    _save_memory(mem)
    _append_log({"event": "pattern_soft_deleted", "pattern_id": pattern_id, "reason": reason})
    return True


def hard_delete(pattern_id: str) -> bool:
    """Hard delete -- elimina completamente el patron."""
    mem = _load_memory()
    if pattern_id not in mem["patterns"]:
        return False
    del mem["patterns"][pattern_id]
    mem["stats"]["total_patterns"] = max(0, mem["stats"].get("total_patterns", 0) - 1)
    for tag, pids in mem["tag_index"].items():
        if pattern_id in pids:
            pids.remove(pattern_id)
    _save_memory(mem)
    _append_log({"event": "pattern_hard_deleted", "pattern_id": pattern_id})
    return True


def record_reuse(pattern_id: str, success: bool, notes: str = ""):
    """Registra que se reutilizo un patron y si funciono.
    Actualiza success_rate con promedio movil exponencial (alpha=0.3)."""
    mem = _load_memory()
    if pattern_id not in mem["patterns"]:
        return

    pattern = mem["patterns"][pattern_id]
    stats = pattern["stats"]
    now = datetime.now(timezone.utc).isoformat()

    stats["reuses"] += 1
    stats["last_reuse"] = now

    # Promedio movil exponencial del success_rate (alpha=0.3)
    alpha = 0.3
    current_rate = stats["success_rate"]
    new_value = 1.0 if success else 0.0
    stats["success_rate"] = round(alpha * new_value + (1 - alpha) * current_rate, 4)

    if success:
        mem["stats"]["total_reuses"] += 1
        mem["stats"]["total_ai_calls_saved"] += 1

    pattern["updated_at"] = now
    _save_memory(mem)

    _append_log({
        "event": "pattern_reuse",
        "pattern_id": pattern_id,
        "success": success,
        "new_success_rate": stats["success_rate"],
        "notes": notes,
    })


def update_pattern(pattern_id: str, solution_updates: dict, reason: str = "") -> bool:
    """Actualiza la solucion de un patron existente (evolucion).
    Guarda version anterior en historial."""
    mem = _load_memory()
    if pattern_id not in mem["patterns"]:
        return False

    pattern = mem["patterns"][pattern_id]
    if "history" not in pattern:
        pattern["history"] = []
    pattern["history"].append({
        "previous_solution": pattern["solution"].copy(),
        "changed_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    })

    pattern["solution"].update(solution_updates)
    pattern["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_memory(mem)

    _append_log({
        "event": "pattern_updated",
        "pattern_id": pattern_id,
        "reason": reason,
    })
    return True


def get_stats() -> dict:
    """Estadisticas globales del sistema de memoria."""
    mem = _load_memory()
    patterns = {k: v for k, v in mem["patterns"].items() if not v.get("deleted_at")}

    # Resync total_patterns from actual count
    base_stats = {
        "total_patterns": len(patterns),
        "total_reuses": mem["stats"].get("total_reuses", 0),
        "total_ai_calls_saved": mem["stats"].get("total_ai_calls_saved", 0),
    }

    if not patterns:
        return {"message": "Sin patrones registrados aun", **base_stats}

    success_rates = [p.get("stats", {}).get("success_rate", 1.0) for p in patterns.values()]
    most_reused = max(patterns.values(), key=lambda p: p.get("stats", {}).get("reuses", 0))

    return {
        **base_stats,
        "avg_success_rate": round(sum(success_rates) / len(success_rates), 4),
        "most_reused_pattern": {
            "id": most_reused.get("id", "unknown"),
            "task_type": most_reused.get("task_type", "unknown"),
            "reuses": most_reused.get("stats", {}).get("reuses", 0),
        },
        "patterns_by_type": _count_by_key(patterns, "task_type"),
    }


def export_for_context(task_type: str = None, limit: int = 10) -> str:
    """
    Exporta patrones relevantes en formato texto para inyectar como
    contexto en el prompt del CLI activo.

    Ordena por relevancia: mas exitosos y mas usados primero.
    Excluye soft-deleted automaticamente.
    """
    mem = _load_memory()
    patterns = [p for p in mem["patterns"].values() if not p.get("deleted_at")]

    if task_type:
        patterns = [p for p in patterns if p.get("task_type") == task_type]

    patterns.sort(
        key=lambda p: (p.get("stats", {}).get("success_rate", 0), p.get("stats", {}).get("reuses", 0)),
        reverse=True,
    )
    patterns = patterns[:limit]

    if not patterns:
        return f"No hay patrones aprendidos para '{task_type or 'cualquier tipo'}'."

    lines = [
        "=== PATRONES APRENDIDOS (memoria local) ===",
        f"Total disponibles: {len(patterns)}",
        "",
    ]
    for p in patterns:
        sol = p.get("solution", {})
        stats = p.get("stats", {})
        lines.append(f"## [{p.get('task_type', 'unknown')}] {p.get('context_key', 'N/A')}")
        lines.append(f"   Estrategia: {sol.get('strategy', 'N/A')}")
        if sol.get("selector_chain"):
            lines.append(f"   Selectores: {' -> '.join(sol['selector_chain'])}")
        if sol.get("code_snippet"):
            lines.append(f"   Codigo: {sol['code_snippet'][:200]}")
        if sol.get("notes"):
            lines.append(f"   Nota: {sol['notes']}")
        lines.append(
            f"   Exito: {stats.get('success_rate', 1.0)*100:.0f}% "
            f"| Reusos: {stats.get('reuses', 0)} "
            f"| Tags: {', '.join(p.get('tags', []))}"
        )
        lines.append("")

    return "\n".join(lines)


# Alias para compatibilidad con Motor 1
export_for_claude_context = export_for_context


# ══════════════════════════════════════════════════════════════
#  TASK ATTEMPTS -- Memoria de callejones sin salida
#  Registra TODOS los metodos intentados (fallidos + exitosos).
#  Proxima sesion -> va directo al mejor metodo, saltea los fallidos
# ══════════════════════════════════════════════════════════════

def _load_attempts() -> dict:
    """Carga base de intentos de tarea."""
    if ATTEMPTS_FILE.exists():
        try:
            return json.loads(ATTEMPTS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_attempts(data: dict):
    """Guarda base de intentos con atomic replace."""
    ATTEMPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ATTEMPTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _atomic_replace(tmp, ATTEMPTS_FILE)


def _task_key(task_description: str) -> str:
    """Hash estable de la descripcion de tarea normalizada."""
    t = task_description.strip().lower()
    t = re.sub(r'["\'].*?["\']', '', t)
    t = re.sub(r'\s+', ' ', t)
    return hashlib.sha256(t.encode()).hexdigest()[:16]


def record_attempt(
    task: str,
    method: str,
    success: bool,
    exit_code: int = -1,
    output_preview: str = "",
    duration_ms: int = 0,
    code_snippet: str = "",
    error_messages: list = None,
) -> dict:
    """
    Registra un intento de resolver una tarea (fallido o exitoso).
    Calcula score basado en velocidad y determina el mejor metodo
    comparando success_rate y avg_score de todos los metodos probados.

    Returns:
        Dict con attempt_num, total_attempts, total_successes,
        total_failures, best_method, failed_methods.
    """
    key = _task_key(task)
    now = datetime.now(timezone.utc).isoformat()

    with file_lock("task_attempts"):
        db = _load_attempts()
        if key not in db:
            db[key] = {
                "task": task,
                "created_at": now,
                "attempts": [],
                "best_method": None,
            }

        entry = db[key]
        attempt_num = len(entry["attempts"]) + 1

        attempt = {
            "num": attempt_num,
            "method": method,
            "success": success,
            "exit_code": exit_code,
            "output_preview": output_preview[:200],
            "error_messages": (error_messages or [])[:5],
            "code_snippet": code_snippet[:500],
            "duration_ms": duration_ms,
            "timestamp": now,
            "score": 0.0,
        }

        if success:
            speed_score = max(0, 1.0 - (duration_ms / 30000))
            attempt["score"] = round(speed_score, 4)

        entry["attempts"].append(attempt)

        successful = [a for a in entry["attempts"] if a["success"]]
        failed = [a for a in entry["attempts"] if not a["success"]]

        if successful:
            method_stats: dict = {}
            for a in entry["attempts"]:
                m = a["method"]
                if m not in method_stats:
                    method_stats[m] = {
                        "successes": 0, "failures": 0, "total_score": 0,
                        "last": a["timestamp"], "best_attempt": a,
                    }
                if a["success"]:
                    method_stats[m]["successes"] += 1
                    method_stats[m]["total_score"] += a["score"]
                    if a["score"] >= method_stats[m]["best_attempt"].get("score", 0):
                        method_stats[m]["best_attempt"] = a
                else:
                    method_stats[m]["failures"] += 1
                method_stats[m]["last"] = a["timestamp"]

            best_name = None
            best_rank = (-1.0, -1.0)
            for m, st in method_stats.items():
                total = st["successes"] + st["failures"]
                sr = st["successes"] / total if total > 0 else 0
                avg = st["total_score"] / st["successes"] if st["successes"] > 0 else 0
                if (sr, avg) > best_rank:
                    best_rank = (sr, avg)
                    best_name = m

            if best_name:
                best = method_stats[best_name]
                entry["best_method"] = {
                    "method": best_name,
                    "success_rate": best_rank[0],
                    "avg_score": best_rank[1],
                    "successes": best["successes"],
                    "failures": best["failures"],
                    "code_snippet": best["best_attempt"].get("code_snippet", ""),
                    "last_used": best["last"],
                }

        entry["updated_at"] = now
        entry["total_attempts"] = len(entry["attempts"])
        entry["total_successes"] = len(successful)
        entry["total_failures"] = len(failed)
        entry["failed_methods"] = list({a["method"] for a in failed})

        _save_attempts(db)

    return {
        "attempt_num": attempt_num,
        "total_attempts": len(entry["attempts"]),
        "total_successes": len(successful),
        "total_failures": len(failed),
        "best_method": entry.get("best_method"),
        "failed_methods": entry.get("failed_methods", []),
    }


def get_best_method(task: str) -> Optional[dict]:
    """Retorna el mejor metodo probado para una tarea, o None si no hay historial.
    Si no hay match exacto, busca por similitud de texto (> 0.6)."""
    key = _task_key(task)
    db = _load_attempts()
    entry = db.get(key)

    # Fallback: similitud de texto
    if not entry or not entry.get("best_method"):
        normalized = task.strip().lower()
        for v in db.values():
            if v.get("best_method") and _similarity(normalized, v["task"].lower()) > 0.6:
                entry = v
                break

    if not entry or not entry.get("best_method"):
        return None

    best = entry["best_method"]
    return {
        "method": best["method"],
        "success_rate": best.get("success_rate", 0),
        "avg_score": best.get("avg_score", 0),
        "code_snippet": best.get("code_snippet", ""),
        "successes": best.get("successes", 0),
        "failed_methods": entry.get("failed_methods", []),
        "total_attempts": entry.get("total_attempts", 0),
        "total_successes": entry.get("total_successes", 0),
        "total_failures": entry.get("total_failures", 0),
        "task": entry.get("task", task),
    }


def format_task_context(task: str) -> str:
    """Genera texto de contexto indicando metodos probados y cuales fallaron.
    Util para inyectar en prompt y evitar repetir metodos fallidos."""
    best = get_best_method(task)
    if not best:
        return ""

    lines = ["HISTORIAL DE INTENTOS PARA ESTA TAREA:"]

    if best["failed_methods"]:
        lines.append(f"  METODOS QUE NO FUNCIONARON ({best['total_failures']} fallos):")
        for fm in best["failed_methods"]:
            lines.append(f"    X {fm}  <-- NO usar, ya fallo antes")

    lines.append(
        f"  MEJOR METODO PROBADO ({best['successes']} exitos, "
        f"tasa: {best['success_rate']*100:.0f}%):"
    )
    lines.append(f"    -> {best['method']}")
    if best["code_snippet"]:
        lines.append(f"    Codigo que funciono:\n    {best['code_snippet'][:300]}")

    lines.append(
        f"  INSTRUCCION: Usa '{best['method']}' directamente. "
        "NO intentes los metodos fallidos."
    )
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
#  ERROR -> FIX CORRELATION (from Motor 1)
#  Detecta errores en output y los correlaciona con el fix
#  que llego despues (ventana configurable via ERROR_CORRELATION_WINDOW).
# ══════════════════════════════════════════════════════════════

def _load_pending_errors() -> list:
    """Carga la cola de errores pendientes esperando fix."""
    if PENDING_ERRORS_FILE.exists():
        try:
            return json.loads(PENDING_ERRORS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_pending_errors(errors: list):
    """Guarda la cola de errores pendientes (max MAX_PENDING_ERRORS)."""
    PENDING_ERRORS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_ERRORS_FILE.write_text(
        json.dumps(errors[-MAX_PENDING_ERRORS:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def detect_errors(output: str) -> list:
    """Detecta patrones de error en el output de un comando."""
    errors = []
    for pattern in ERROR_PATTERNS:
        matches = re.findall(pattern, str(output), re.IGNORECASE)
        if matches:
            errors.extend(matches[:3])
    return errors


def detect_success(output: str, exit_code: int = None) -> bool:
    """Detecta si el output indica exito."""
    if exit_code == 0:
        return True
    for pattern in SUCCESS_PATTERNS:
        if re.search(pattern, str(output), re.IGNORECASE):
            return True
    return False


def correlate_error_fix(
    command: str,
    output: str,
    exit_code: int,
    tags: list = None,
) -> dict:
    """
    Auto-correlacion error -> fix en ventana de ERROR_CORRELATION_WINDOW segundos.

    Llama esto despues de ejecutar un comando para aprendizaje automatico:
    - Si el comando fallo: encola el error para correlacion futura
    - Si el comando tuvo exito y hay un error previo en cola: registra el par error->fix

    Returns:
        Dict con {learned, pattern_id, error_fix, message}
    """
    now = datetime.now(timezone.utc)
    result = {"learned": False, "pattern_id": None, "error_fix": None, "message": ""}

    errors = detect_errors(output)
    success = exit_code == 0 and not errors

    if success and detect_success(output, exit_code):
        # Comando exitoso -- verificar si hay error previo en cola para correlacionar
        pending = _load_pending_errors()
        if pending:
            last_error = pending[-1]
            error_time = datetime.fromisoformat(last_error["timestamp"])
            if error_time.tzinfo is None:
                error_time = error_time.replace(tzinfo=timezone.utc)
            elapsed = (now - error_time).total_seconds()
            if elapsed <= ERROR_CORRELATION_WINDOW:
                fix_solution = {
                    "strategy": "auto_error_fix",
                    "error_command": last_error["command"],
                    "error_messages": last_error["errors"][:3],
                    "fix_command": command,
                    "fix_output_preview": output[:200],
                    "notes": (
                        f"Error: {last_error['command'][:60]} "
                        f"-> Fix: {command[:60]}"
                    ),
                    "auto_learned": True,
                    "attempts_before_fix": len(pending),
                }
                pid = register_pattern(
                    task_type="error_fix",
                    context_key=_normalize_key(command),
                    solution=fix_solution,
                    tags=(tags or []) + ["auto_learned", "error_fix"],
                    error_context={"original_error": last_error},
                )
                _save_pending_errors([])
                result.update({
                    "learned": True,
                    "pattern_id": pid,
                    "error_fix": fix_solution,
                    "message": (
                        f"APRENDIDO: Despues de {len(pending)} intento(s) fallido(s), "
                        f"'{command[:50]}' funciono. Guardado."
                    ),
                })
                return result

    elif errors:
        # Comando fallido -- encolar error esperando fix futuro
        pending = _load_pending_errors()
        pending.append({
            "command": command,
            "errors": errors[:3],
            "output_preview": output[:200],
            "exit_code": exit_code,
            "timestamp": now.isoformat(),
        })
        _save_pending_errors(pending)
        result["message"] = f"Error detectado ({len(errors)} patron(es)). Esperando fix..."

    return result


# ══════════════════════════════════════════════════════════════
#  CLI rapido para inspeccion
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python learning_memory.py [stats|export|search <type> <key>|list|"
              "attempts <tarea>|context <tarea>|soft-delete <id>|hard-delete <id>|"
              "topic-key <type> <key>|dedup-stats]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "stats":
        print(json.dumps(get_stats(), indent=2, ensure_ascii=False))

    elif cmd == "export":
        task_filter = sys.argv[2] if len(sys.argv) > 2 else None
        print(export_for_context(task_filter))

    elif cmd == "search":
        if len(sys.argv) < 4:
            print("Uso: python learning_memory.py search <task_type> <context_key>")
            sys.exit(1)
        result = search_pattern(sys.argv[2], sys.argv[3])
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("No se encontro patron. Territorio nuevo.")

    elif cmd == "list":
        mem = _load_memory()
        for pid, p in mem["patterns"].items():
            status = " [DEL]" if p.get("deleted_at") else ""
            print(f"  {pid}  {p['task_type']:20s}  {p['context_key'][:40]:40s}  "
                  f"exito:{p['stats']['success_rate']*100:.0f}%  "
                  f"reusos:{p['stats']['reuses']}{status}")

    elif cmd == "attempts":
        if len(sys.argv) < 3:
            print("Uso: python learning_memory.py attempts \"descripcion de tarea\"")
            sys.exit(1)
        result = get_best_method(sys.argv[2])
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("Sin historial de intentos para esa tarea.")

    elif cmd == "context":
        if len(sys.argv) < 3:
            print("Uso: python learning_memory.py context \"descripcion de tarea\"")
            sys.exit(1)
        print(format_task_context(sys.argv[2]) or "Sin historial para esa tarea.")

    elif cmd == "soft-delete":
        if len(sys.argv) < 3:
            print("Uso: python learning_memory.py soft-delete <pattern_id> [reason]")
            sys.exit(1)
        reason = sys.argv[3] if len(sys.argv) > 3 else ""
        ok = soft_delete(sys.argv[2], reason)
        print(f"{'OK -- soft deleted' if ok else 'No encontrado'}: {sys.argv[2]}")

    elif cmd == "hard-delete":
        if len(sys.argv) < 3:
            print("Uso: python learning_memory.py hard-delete <pattern_id>")
            sys.exit(1)
        ok = hard_delete(sys.argv[2])
        print(f"{'OK -- eliminado' if ok else 'No encontrado'}: {sys.argv[2]}")

    elif cmd == "topic-key":
        if len(sys.argv) < 4:
            print("Uso: python learning_memory.py topic-key <task_type> <context_key>")
            sys.exit(1)
        print(suggest_topic_key(sys.argv[2], sys.argv[3]))

    elif cmd == "dedup-stats":
        mem = _load_memory()
        total = len(mem["patterns"])
        deleted = sum(1 for p in mem["patterns"].values() if p.get("deleted_at"))
        revisions = sum(p.get("revision_count", 1) for p in mem["patterns"].values())
        duplicates = sum(p.get("duplicate_count", 1) for p in mem["patterns"].values())
        by_type = {}
        by_scope = {"project": 0, "personal": 0}
        for p in mem["patterns"].values():
            if p.get("deleted_at"):
                continue
            t = p.get("mem_type", "manual")
            by_type[t] = by_type.get(t, 0) + 1
            s = p.get("scope", "project")
            by_scope[s] = by_scope.get(s, 0) + 1
        print(json.dumps({
            "total": total,
            "active": total - deleted,
            "soft_deleted": deleted,
            "total_revisions": revisions,
            "total_dedup_hits": duplicates - total,
            "by_type": by_type,
            "by_scope": by_scope,
        }, indent=2, ensure_ascii=False))

    elif cmd == "correlate":
        if len(sys.argv) < 5:
            print("Uso: python learning_memory.py correlate <command> <output> <exit_code>")
            sys.exit(1)
        r = correlate_error_fix(sys.argv[2], sys.argv[3], int(sys.argv[4]))
        print(json.dumps(r, indent=2, ensure_ascii=False))

    else:
        print(f"Comando desconocido: {cmd}")
        print("Comandos: stats | export [tipo] | search <type> <key> | list | "
              "attempts <tarea> | context <tarea> | soft-delete <id> | "
              "hard-delete <id> | topic-key <type> <key> | dedup-stats | "
              "correlate <cmd> <output> <exit_code>")
