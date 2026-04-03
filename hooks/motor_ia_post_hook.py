#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
motor_ia_post_hook.py - Post-response hook
===========================================
Se ejecuta DESPUES de cada respuesta de Claude.
Lee el estado guardado por motor_ia_hook.py y:
  - Si KB no cubrio el 100%, guarda la respuesta en NotebookLM (sources.add_text)
  - Asi el conocimiento nuevo queda disponible para futuras consultas

Hook type: PostResponse / Notification
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

_HOOK_DIR = Path(__file__).resolve().parent
_PROJECT = _HOOK_DIR.parent
sys.path.insert(0, str(_PROJECT))

_LOG_FILE = _PROJECT / "core" / "motor_ia_hook.log"
logging.basicConfig(
    filename=str(_LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("motor_ia_post")

_STATE_FILE = _PROJECT / "core" / "motor_ia_state.json"


def get_assistant_response():
    """Lee la respuesta de Claude desde stdin (Stop event)."""
    try:
        input_data = json.loads(sys.stdin.read())
        # Stop event pasa la respuesta en "last_assistant_message"
        response = input_data.get("last_assistant_message", "")
        return response.strip() if response else None
    except Exception as e:
        log.error(f"Error reading response: {e}")
        return None


def extract_source_percentages(response):
    """
    Extrae los porcentajes reales de la respuesta de Claude.
    Busca el patron: **Fuentes:** KB X% + Internet Y% + ML Z%
    """
    import re

    pattern = r"KB\s*(\d+)%.*?Internet\s*(\d+)%.*?ML\s*(\d+)%"
    match = re.search(pattern, response, re.IGNORECASE)

    if match:
        return {
            "kb_pct": int(match.group(1)),
            "internet_pct": int(match.group(2)),
            "ml_pct": int(match.group(3)),
        }
    return None


def main():
    try:
        # Leer estado del pre-hook
        if not _STATE_FILE.exists():
            return

        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)

        if not state.get("needs_save"):
            log.info(f"KB cubrio 100% solo, no need to save. (kb={state.get('kb_pct',0)}%, internet={state.get('internet_pct',0)}%, ml={state.get('ml_pct',0)}%)")
            return

        query = state.get("query", "")
        if not query:
            return

        # Leer respuesta de Claude
        response = get_assistant_response()
        if not response or len(response) < 50:
            return

        # Extraer porcentajes reales reportados por Claude
        real_pcts = extract_source_percentages(response)

        if real_pcts:
            source_label = []
            if real_pcts["internet_pct"] > 0:
                source_label.append(f"Internet {real_pcts['internet_pct']}%")
            if real_pcts["ml_pct"] > 0:
                source_label.append(f"ML {real_pcts['ml_pct']}%")
            source = " + ".join(source_label) if source_label else "ML"
        else:
            source = "ML"

        # Limpiar respuesta (quitar la linea de fuentes para el KB)
        clean_response = response
        import re
        clean_response = re.sub(
            r"\*\*Fuentes:\*\*.*$", "", clean_response, flags=re.MULTILINE
        ).strip()

        # Guardar en KB (NotebookLM)
        from core.notebooklm_kb import save_to_kb
        source_id = save_to_kb(query, clean_response, source=source)

        if source_id:
            log.info(f"AUTO-SAVED to NotebookLM: query='{query[:60]}' source={source} id={source_id}")
        else:
            log.warning(f"Failed to save to NotebookLM: query='{query[:60]}'")

        # Limpiar state
        _STATE_FILE.unlink(missing_ok=True)

    except Exception as e:
        log.error(f"Post-hook error: {e}")


if __name__ == "__main__":
    main()
