# -*- coding: utf-8 -*-
"""
working_memory.py -- Working Memory: capa volatil de memoria de sesion
=======================================================================
Hace explicita la distincion de tres capas de memoria en Motor_IA:

  WORKING  (sesion actual - volatil)       → working_memory.json
  SHORT    (aprendizaje reciente)          → learned_patterns.json (TTL alto)
  LONG     (patrones consolidados)         → learned_patterns.json (permanente)

Motor_IA ya tenia SHORT y LONG de forma implicita. Esta capa agrega
WORKING MEMORY explicita: observaciones, hipotesis y decisiones de la
sesion actual que NO merecen persistencia a largo plazo pero deben
estar disponibles durante la sesion.

Al fin de sesion: wm_clear() o wm_promote() para ascender a LONG.

Motor_IA ventaja sobre Engram:
  Engram no diferencia working/short/long explicitamente en su API.
  Nosotros tenemos los tres niveles con API clara + mecanismo de
  promocion explicita para elevar un insight a largo plazo.

API:
  wm_add(content, category, session_id)  -> item_id
  wm_get(category, session_id)           -> list[dict]
  wm_clear(session_id)                   -> None
  wm_promote(item_id, task_type)         -> bool
  wm_to_context(max_items)               -> str
  get_stats()                            -> dict
"""

import json
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR, WORKING_MEMORY_MAX_ITEMS, WORKING_MEMORY_TTL_HOURS
from core.file_lock import file_lock, _atomic_replace

WORKING_MEMORY_FILE = DATA_DIR / "working_memory.json"

VALID_CATEGORIES = frozenset({
    "observation",   # lo que el agente observo/leyo en esta sesion
    "hypothesis",    # hipotesis en curso (puede ser incorrecta)
    "decision",      # decision tecnica tomada (candidata a long-term)
    "error",         # error encontrado (correlacionar con fix)
    "fix",           # fix aplicado en esta sesion
    "context",       # contexto adicional aportado por el usuario
    "todo",          # pendiente dentro de la sesion
})


# -- I/O -----------------------------------------------------------------------

def _load_wm() -> dict:
    if WORKING_MEMORY_FILE.exists():
        try:
            return json.loads(WORKING_MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"items": [], "session_id": "", "created_at": ""}


def _save_wm(wm: dict):
    WORKING_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = WORKING_MEMORY_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(wm, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _atomic_replace(tmp, WORKING_MEMORY_FILE)


# -- API publica ---------------------------------------------------------------

def wm_add(content: str,
           category: str = "observation",
           session_id: str = "",
           metadata: dict = None) -> str:
    """
    Agrega un item a la working memory de la sesion.

    Args:
        content:    Texto del item (max 500 chars)
        category:   Categoria del item (ver VALID_CATEGORIES)
        session_id: ID de la sesion actual
        metadata:   Datos adicionales opcionales

    Returns:
        item_id (str) para referencia o promocion posterior
    """
    if not content or not content.strip():
        return ""

    if category not in VALID_CATEGORIES:
        category = "observation"

    item_id = hashlib.sha256(
        f"{content.strip()}{time.time()}".encode()
    ).hexdigest()[:8]

    with file_lock("working_memory"):
        wm = _load_wm()

        # Si es nueva sesion, limpiar items anteriores
        if session_id and wm.get("session_id") and wm["session_id"] != session_id:
            wm = {
                "items":      [],
                "session_id": session_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        elif not wm.get("session_id") and session_id:
            wm["session_id"] = session_id
            wm["created_at"] = datetime.now(timezone.utc).isoformat()

        wm.setdefault("items", []).append({
            "id":        item_id,
            "content":   content.strip()[:500],
            "category":  category,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata":  metadata or {},
            "promoted":  False,
        })

        # Mantener solo los ultimos MAX_ITEMS
        if len(wm["items"]) > WORKING_MEMORY_MAX_ITEMS:
            wm["items"] = wm["items"][-WORKING_MEMORY_MAX_ITEMS:]

        _save_wm(wm)

    return item_id


def wm_get(category: str = None, session_id: str = None) -> list:
    """
    Obtiene items de working memory.

    Args:
        category:   Filtrar por categoria (None = todos)
        session_id: Si se especifica, retorna [] si no coincide con sesion activa

    Returns:
        Lista de items dict
    """
    wm = _load_wm()

    if session_id and wm.get("session_id") and wm["session_id"] != session_id:
        return []

    items = wm.get("items", [])
    if category:
        items = [i for i in items if i.get("category") == category]
    return items


def wm_clear(session_id: str = ""):
    """
    Limpia la working memory (llamar al fin de sesion).

    Args:
        session_id: ID de la sesion que termino (para log)
    """
    with file_lock("working_memory"):
        _save_wm({
            "items":            [],
            "session_id":       "",
            "created_at":       datetime.now(timezone.utc).isoformat(),
            "_cleared_session": session_id,
        })


def wm_promote(item_id: str, task_type: str = "decision") -> bool:
    """
    Promueve un item de working memory a long-term (learning_memory).

    Args:
        item_id:   ID del item a promover
        task_type: Tipo de patron para learning_memory

    Returns:
        True si se promovio, False si el item no existe o fallo
    """
    with file_lock("working_memory"):
        wm = _load_wm()
        items = wm.get("items", [])
        target = next((i for i in items if i["id"] == item_id), None)

        if not target:
            return False

        try:
            from core.learning_memory import register_pattern
            register_pattern(
                task_type=task_type,
                context_key=f"wm_{item_id}_{target['category']}",
                solution={
                    "content":  target["content"],
                    "category": target["category"],
                    "source":   "working_memory_promoted",
                },
                tags=["working_memory", "promoted", target["category"]],
            )
            target["promoted"] = True
            _save_wm(wm)
            return True
        except Exception:
            return False


def wm_to_context(max_items: int = 10) -> str:
    """
    Formatea working memory para inyectar en el contexto del agente.
    Agrupa por categoria para mejor legibilidad.

    Returns:
        String formateado listo para inyeccion, o "" si no hay items
    """
    wm = _load_wm()
    items = wm.get("items", [])
    if not items:
        return ""

    # Agrupar por categoria (solo items no-promovidos)
    by_cat: dict = {}
    for item in items[-max_items:]:
        if item.get("promoted"):
            continue
        cat = item.get("category", "observation")
        by_cat.setdefault(cat, []).append(item)

    if not by_cat:
        return ""

    lines = ["-" * 40, "  WORKING MEMORY (sesion actual)"]
    for cat, cat_items in by_cat.items():
        lines.append(f"  [{cat.upper()}]")
        for item in cat_items[-3:]:  # max 3 por categoria
            ts = item.get("timestamp", "")[:16].replace("T", " ")
            lines.append(f"    [{ts}] {item['content'][:200]}")
    lines.append("")

    return "\n".join(lines)


def get_stats() -> dict:
    """Estadisticas del estado actual de working memory."""
    wm = _load_wm()
    items = wm.get("items", [])

    by_cat: dict = {}
    for item in items:
        cat = item.get("category", "observation")
        by_cat[cat] = by_cat.get(cat, 0) + 1

    return {
        "total_items": len(items),
        "session_id":  wm.get("session_id", ""),
        "by_category": by_cat,
        "promoted":    sum(1 for i in items if i.get("promoted")),
    }
