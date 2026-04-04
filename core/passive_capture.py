#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
passive_capture.py - Feature 6: Captura Pasiva / Invisible
==========================================================
Listener silencioso que detecta convenciones, preferencias y
anti-patrones del usuario sin hooks explícitos.

Analiza:
  - Archivos que siempre se editan juntos
  - Patrones de código preferidos
  - Cambios rechazados (anti-patrones)
  - Preferencias validadas silenciosamente
"""

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR

log = logging.getLogger("passive_capture")

PASSIVE_DB_FILE = DATA_DIR / "passive_captures.json"
FILE_COOCCURRENCE_FILE = DATA_DIR / "file_cooccurrence.json"
MAX_CAPTURES = 500


def _load_db() -> dict:
    if PASSIVE_DB_FILE.exists():
        try:
            return json.loads(PASSIVE_DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "conventions": [],
        "preferences": [],
        "anti_patterns": [],
        "file_groups": {},
    }


def _save_db(db: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Limitar tamaño
    for key in ["conventions", "preferences", "anti_patterns"]:
        if key in db and len(db[key]) > MAX_CAPTURES:
            db[key] = db[key][-MAX_CAPTURES:]
    PASSIVE_DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def record_file_edit(file_path: str, session_id: str = ""):
    """Registra que un archivo fue editado (para detectar co-ediciones)."""
    cooccur = {}
    if FILE_COOCCURRENCE_FILE.exists():
        try:
            cooccur = json.loads(FILE_COOCCURRENCE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    session_key = session_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H")
    if session_key not in cooccur:
        cooccur[session_key] = []
    cooccur[session_key].append(file_path)

    # Limpiar sesiones viejas (mantener últimas 100)
    keys = sorted(cooccur.keys())
    if len(keys) > 100:
        for k in keys[:-100]:
            del cooccur[k]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FILE_COOCCURRENCE_FILE.write_text(json.dumps(cooccur, ensure_ascii=False, indent=2), encoding="utf-8")


def record_convention(pattern: str, context: str = "", confidence: float = 0.5):
    """Registra una convención detectada (ej: 'usa pathlib en vez de os.path')."""
    db = _load_db()
    # Dedup: no guardar si ya existe uno similar
    for conv in db["conventions"]:
        if conv.get("pattern") == pattern:
            conv["count"] = conv.get("count", 1) + 1
            conv["confidence"] = min(1.0, conv.get("confidence", 0.5) + 0.1)
            conv["last_seen"] = datetime.now(timezone.utc).isoformat()
            _save_db(db)
            return

    db["conventions"].append({
        "pattern": pattern,
        "context": context,
        "confidence": confidence,
        "count": 1,
        "first_seen": datetime.now(timezone.utc).isoformat(),
        "last_seen": datetime.now(timezone.utc).isoformat(),
    })
    _save_db(db)


def record_preference(action: str, accepted: bool, context: str = ""):
    """Registra si el usuario aceptó o rechazó una acción."""
    db = _load_db()
    key = "preferences" if accepted else "anti_patterns"
    db[key].append({
        "action": action,
        "accepted": accepted,
        "context": context,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save_db(db)


def detect_file_groups(min_cooccurrence: int = 3) -> dict:
    """
    Detecta grupos de archivos que se editan juntos frecuentemente.
    Retorna {grupo_id: [archivos]}.
    """
    if not FILE_COOCCURRENCE_FILE.exists():
        return {}

    try:
        cooccur = json.loads(FILE_COOCCURRENCE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

    # Contar co-ocurrencias de pares de archivos
    pair_counts = Counter()
    for session_files in cooccur.values():
        if not isinstance(session_files, list):
            continue
        unique_files = list(set(session_files))
        for i, f1 in enumerate(unique_files):
            for f2 in unique_files[i + 1:]:
                pair = tuple(sorted([f1, f2]))
                pair_counts[pair] += 1

    # Agrupar archivos frecuentes
    groups = defaultdict(set)
    group_id = 0
    for (f1, f2), count in pair_counts.most_common(50):
        if count < min_cooccurrence:
            break
        # Buscar grupo existente
        found = False
        for gid, files in groups.items():
            if f1 in files or f2 in files:
                files.add(f1)
                files.add(f2)
                found = True
                break
        if not found:
            groups[group_id] = {f1, f2}
            group_id += 1

    return {str(gid): sorted(list(files)) for gid, files in groups.items()}


def get_conventions(min_confidence: float = 0.6) -> list[dict]:
    """Retorna convenciones con alta confianza."""
    db = _load_db()
    return [
        c for c in db.get("conventions", [])
        if c.get("confidence", 0) >= min_confidence
    ]


def get_anti_patterns() -> list[dict]:
    """Retorna anti-patrones (acciones rechazadas)."""
    db = _load_db()
    return db.get("anti_patterns", [])[-20:]


def get_passive_stats() -> dict:
    """Estadísticas para dashboard."""
    db = _load_db()
    return {
        "conventions": len(db.get("conventions", [])),
        "preferences": len(db.get("preferences", [])),
        "anti_patterns": len(db.get("anti_patterns", [])),
        "file_groups": len(detect_file_groups()),
    }
