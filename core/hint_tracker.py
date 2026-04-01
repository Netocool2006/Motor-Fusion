# -*- coding: utf-8 -*-
"""
hint_tracker.py -- Feedback loop de efectividad de hints inyectados
====================================================================
Cierra el ciclo de aprendizaje: Motor_IA inyecta contexto -> trackea si
ese contexto fue realmente utilizado -> mejora la seleccion futura.

Flujo:
  1. user_prompt_submit: llama record_injection(hint_keys, session_id)
  2. session_end:        llama score_injection(session_id, transcript_text)
  3. Proximo session:    get_hint_score(key) prioriza hints con mejor score

Score por hint_key: EMA (media movil exponencial)
  score_new = DECAY * score_old + (1 - DECAY) * used(0 o 1)

HINT_EFFECT_FILE = DATA_DIR/hint_effectiveness.json (ya definido en config.py)

Motor_IA ventaja sobre Engram:
  Engram trackea efectividad globalmente. Nosotros la trackeamos
  POR DOMINIO (el hint_key incluye dominio/tipo), lo que da precision fina.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from config import HINT_EFFECT_FILE, HINT_EFFECTIVENESS_DECAY, DATA_DIR
from core.file_lock import file_lock, _atomic_replace

# Archivo temporal de inyecciones de la sesion activa
_INJECTION_LOG = DATA_DIR / "current_injection.json"


# -- I/O -----------------------------------------------------------------------

def _load_effectiveness() -> dict:
    if HINT_EFFECT_FILE.exists():
        try:
            return json.loads(HINT_EFFECT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_effectiveness(data: dict):
    HINT_EFFECT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = HINT_EFFECT_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _atomic_replace(tmp, HINT_EFFECT_FILE)


def _load_injection_log() -> dict:
    if _INJECTION_LOG.exists():
        try:
            return json.loads(_INJECTION_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


# -- API publica ---------------------------------------------------------------

def record_injection(hint_keys: list, session_id: str):
    """
    Registra que estos hint_keys fueron inyectados en esta sesion.
    Llamar desde user_prompt_submit despues de seleccionar hints.

    Args:
        hint_keys:  Lista de strings identificando patrones/hechos inyectados
        session_id: ID de la sesion actual
    """
    if not hint_keys or not session_id:
        return

    existing = _load_injection_log()
    session_hints = existing.get(session_id, [])

    for key in hint_keys:
        if key and key not in session_hints:
            session_hints.append(key)

    existing[session_id] = session_hints

    _INJECTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    _INJECTION_LOG.write_text(
        json.dumps(existing, ensure_ascii=False), encoding="utf-8"
    )


def score_injection(session_id: str, transcript_text: str):
    """
    Al fin de sesion, verifica cuales hints inyectados aparecen en el
    transcript (fueron referenciados/usados) y actualiza scores EMA.

    Args:
        session_id:      ID de la sesion que termino
        transcript_text: Texto completo del transcript de la sesion
    """
    if not session_id or not transcript_text:
        return

    injections = _load_injection_log()
    injected_hints = injections.get(session_id, [])
    if not injected_hints:
        return

    effectiveness = _load_effectiveness()
    transcript_lower = transcript_text.lower()
    now_iso = datetime.now(timezone.utc).isoformat()

    for hint_key in injected_hints:
        # Detectar si el hint fue usado: palabras del key en el transcript
        hint_words = re.findall(r'[a-z0-9_]{3,}', hint_key.lower())
        if not hint_words:
            continue

        matches  = sum(1 for w in hint_words if w in transcript_lower)
        used     = matches >= max(1, len(hint_words) // 2)

        if hint_key not in effectiveness:
            effectiveness[hint_key] = {
                "injections": 0,
                "used_count":  0,
                "score":       0.5,   # neutral al inicio
                "last_updated": "",
            }

        e = effectiveness[hint_key]
        e["injections"]  += 1
        if used:
            e["used_count"] += 1

        # EMA update
        new_signal   = 1.0 if used else 0.0
        alpha        = HINT_EFFECTIVENESS_DECAY
        e["score"]   = round(alpha * e["score"] + (1 - alpha) * new_signal, 4)
        e["last_updated"] = now_iso

    _save_effectiveness(effectiveness)

    # Limpiar entrada de esta sesion del log
    injections.pop(session_id, None)
    _INJECTION_LOG.write_text(
        json.dumps(injections, ensure_ascii=False), encoding="utf-8"
    )


def get_hint_score(hint_key: str) -> float:
    """
    Retorna el score de efectividad de un hint (0.0 - 1.0).
    Default 0.5 si el hint nunca fue trackeado.
    """
    effectiveness = _load_effectiveness()
    return effectiveness.get(hint_key, {}).get("score", 0.5)


def sort_hints_by_effectiveness(hints: list, key_fn=None) -> list:
    """
    Ordena una lista de hints por score de efectividad (mayor primero).

    Args:
        hints:  Lista de objetos hint (dict o str)
        key_fn: Funcion para extraer el hint_key de cada hint (None = es str)

    Returns:
        Lista ordenada por score descendente
    """
    def score(hint):
        k = key_fn(hint) if key_fn else str(hint)
        return get_hint_score(k)

    return sorted(hints, key=score, reverse=True)


def get_top_hints(limit: int = 20) -> list:
    """Retorna los hints mas efectivos."""
    effectiveness = _load_effectiveness()
    sorted_h = sorted(
        [(k, v["score"]) for k, v in effectiveness.items()],
        key=lambda x: -x[1]
    )
    return [{"key": k, "score": s} for k, s in sorted_h[:limit]]


def get_stats() -> dict:
    effectiveness = _load_effectiveness()
    if not effectiveness:
        return {"total_tracked": 0, "avg_score": 0.0, "top_hints": []}

    scores = [v["score"] for v in effectiveness.values()]
    return {
        "total_tracked": len(effectiveness),
        "avg_score":     round(sum(scores) / len(scores), 3),
        "top_hints":     get_top_hints(5),
    }
