#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
token_budget.py - Feature 4: Compresión de contexto / Token Budget
==================================================================
Gestiona un presupuesto máximo de tokens para inyección de contexto.
Prioriza por relevancia + freshness y comprime patrones similares.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR

log = logging.getLogger("token_budget")

DEFAULT_BUDGET = 2000  # tokens máximos para inyección
METRICS_FILE = DATA_DIR / "token_budget_metrics.json"


def estimate_tokens(text: str) -> int:
    """Estima tokens (aprox 4 chars = 1 token para español)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def truncate_to_budget(content: str, budget: int = DEFAULT_BUDGET) -> tuple[str, dict]:
    """
    Trunca contenido al presupuesto de tokens.
    Retorna (contenido_truncado, métricas).
    """
    original_tokens = estimate_tokens(content)
    if original_tokens <= budget:
        return content, {
            "original_tokens": original_tokens,
            "final_tokens": original_tokens,
            "truncated": False,
            "efficiency": 1.0,
        }

    # Estrategia: cortar por secciones, mantener las más valiosas
    sections = _split_sections(content)
    prioritized = _prioritize_sections(sections)

    result_parts = []
    used_tokens = 0
    for section in prioritized:
        section_tokens = estimate_tokens(section["text"])
        if used_tokens + section_tokens > budget:
            # Truncar esta sección para llenar el espacio restante
            remaining = budget - used_tokens
            if remaining > 50:
                chars = remaining * 4
                result_parts.append(section["text"][:chars] + "...")
                used_tokens += remaining
            break
        result_parts.append(section["text"])
        used_tokens += section_tokens

    final_content = "\n".join(result_parts)
    final_tokens = estimate_tokens(final_content)

    metrics = {
        "original_tokens": original_tokens,
        "final_tokens": final_tokens,
        "truncated": True,
        "compression_ratio": round(final_tokens / original_tokens, 2) if original_tokens > 0 else 1,
        "efficiency": round(final_tokens / budget, 2) if budget > 0 else 0,
    }

    return final_content, metrics


def _split_sections(content: str) -> list[dict]:
    """Divide contenido en secciones lógicas."""
    sections = []
    current = ""
    current_type = "unknown"

    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("<paso1_kb>"):
            if current:
                sections.append({"text": current, "type": current_type})
            current = line + "\n"
            current_type = "kb"
        elif stripped.startswith("<paso2_internet>"):
            if current:
                sections.append({"text": current, "type": current_type})
            current = line + "\n"
            current_type = "internet"
        elif stripped.startswith("<paso3_ml>"):
            if current:
                sections.append({"text": current, "type": current_type})
            current = line + "\n"
            current_type = "ml"
        elif stripped.startswith("<session_anterior>"):
            if current:
                sections.append({"text": current, "type": current_type})
            current = line + "\n"
            current_type = "session"
        elif stripped.startswith("<instrucciones>"):
            if current:
                sections.append({"text": current, "type": current_type})
            current = line + "\n"
            current_type = "instructions"
        else:
            current += line + "\n"

    if current:
        sections.append({"text": current, "type": current_type})

    return sections


def _prioritize_sections(sections: list[dict]) -> list[dict]:
    """Prioriza secciones: KB > Instructions > Session > Internet > ML."""
    priority = {
        "kb": 1,
        "instructions": 2,
        "session": 3,
        "internet": 4,
        "ml": 5,
        "unknown": 6,
    }
    return sorted(sections, key=lambda s: priority.get(s["type"], 99))


def compress_similar_entries(entries: list[str], threshold: float = 0.8) -> list[str]:
    """Comprime entradas similares en resúmenes."""
    if len(entries) <= 3:
        return entries

    # Agrupar por similitud simple (primeras N palabras)
    groups = {}
    for entry in entries:
        key = " ".join(entry.split()[:5]).lower()
        if key not in groups:
            groups[key] = []
        groups[key].append(entry)

    compressed = []
    for key, group in groups.items():
        if len(group) == 1:
            compressed.append(group[0])
        else:
            compressed.append(f"{group[0]} (+{len(group)-1} similares)")

    return compressed


def record_metrics(original_tokens: int, final_tokens: int, useful_tokens: int = 0):
    """Registra métricas de uso de tokens (para dashboard)."""
    history = []
    if METRICS_FILE.exists():
        try:
            history = json.loads(METRICS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "original": original_tokens,
        "final": final_tokens,
        "useful": useful_tokens or final_tokens,
        "efficiency": round(final_tokens / original_tokens, 2) if original_tokens > 0 else 1,
    })

    # Mantener últimas 200 mediciones
    history = history[-200:]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def get_token_stats() -> dict:
    """Estadísticas de uso de tokens (para dashboard)."""
    if not METRICS_FILE.exists():
        return {"avg_efficiency": 0, "total_saved": 0, "measurements": 0}
    try:
        history = json.loads(METRICS_FILE.read_text(encoding="utf-8"))
        if not history:
            return {"avg_efficiency": 0, "total_saved": 0, "measurements": 0}
        total_original = sum(h.get("original", 0) for h in history)
        total_final = sum(h.get("final", 0) for h in history)
        return {
            "avg_efficiency": round(sum(h.get("efficiency", 1) for h in history) / len(history), 2),
            "total_saved": total_original - total_final,
            "measurements": len(history),
            "avg_original": round(total_original / len(history)),
            "avg_final": round(total_final / len(history)),
        }
    except Exception:
        return {"avg_efficiency": 0, "total_saved": 0, "measurements": 0}
