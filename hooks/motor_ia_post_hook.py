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
            log.info(f"No need to save. mode={state.get('mode','legacy')}")
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

        # Guardar en KB (ChromaDB local)
        from core.vector_kb import save_to_kb
        source_id = save_to_kb(query, clean_response, source=source)

        if source_id:
            log.info(f"AUTO-SAVED to ChromaDB: query='{query[:60]}' source={source} id={source_id}")
        else:
            log.warning(f"Failed to save to ChromaDB: query='{query[:60]}'")

        # Limpiar state
        _STATE_FILE.unlink(missing_ok=True)

        # Actualizar resumen de sesión (para continuidad entre sesiones)
        _update_session_summary(query, clean_response[:200])

        # -- Feature 6: Captura Pasiva (registrar convenciones detectadas) --
        try:
            from core.passive_capture import record_file_edit
            # Registrar archivos mencionados en la respuesta para co-ocurrencia
            import re as _re
            file_refs = _re.findall(r'[\w/\\]+\.\w{2,4}', clean_response[:500])
            for fr in file_refs[:10]:
                record_file_edit(fr)
        except Exception:
            pass

        # -- Feature 8: KB Versioning (registrar cambio) --
        try:
            from core.kb_versioning import record_change
            record_change(
                domain="auto_save",
                change_type="fact_added",
                key=query[:80],
                details=f"From {source}",
            )
        except Exception:
            pass

        # -- Feature 12: Memory Tiers (guardar en HOT) --
        try:
            from core.memory_tiers import store_memory
            store_memory(
                key=query[:200],
                value=clean_response[:1000],
                domain=source,
                source="auto_save",
                tier="hot",
            )
            log.info(f"MEMORY_TIERS: stored in HOT tier")
        except Exception:
            pass

        # -- Feature 15: Typed Graph (inferir relaciones de la respuesta) --
        try:
            from core.typed_graph import infer_and_store
            n = infer_and_store(clean_response[:1000], context=query[:100])
            if n > 0:
                log.info(f"TYPED_GRAPH: inferred {n} relations from response")
        except Exception:
            pass

        # -- Feature 2: Cloud Sync (encolar cambio) --
        try:
            from core.cloud_sync import enqueue_change, auto_sync_if_needed
            enqueue_change("auto_save", "fact_added", query[:60])
            auto_sync_if_needed()
        except Exception:
            pass

    except Exception as e:
        log.error(f"Post-hook error: {e}")


_SESSION_FILE = _PROJECT / "core" / "session_summary.json"


def _sanitize(text):
    """Remove surrogates and control chars that break JSON serialization."""
    if not text:
        return ""
    return text.encode("utf-8", errors="replace").decode("utf-8")


def _update_session_summary(query, answer_preview):
    """
    Mantiene un resumen corriente de la sesión actual.
    Se acumula con cada interacción y sirve para que la próxima
    sesión sepa qué se estaba haciendo.
    """
    try:
        # Leer resumen existente
        if _SESSION_FILE.exists():
            with open(_SESSION_FILE, "r", encoding="utf-8") as f:
                summary = json.load(f)
        else:
            summary = {
                "session_start": datetime.now().isoformat(),
                "interactions": [],
                "topics": [],
            }

        # Sanitizar texto para evitar surrogates que crashean json.dump
        safe_query = _sanitize(query)[:100]
        safe_preview = _sanitize(answer_preview)[:100]

        # Agregar interacción (máximo últimas 20)
        summary["interactions"].append({
            "time": datetime.now().strftime("%H:%M"),
            "query": safe_query,
            "answer_preview": safe_preview,
        })
        summary["interactions"] = summary["interactions"][-20:]

        # Actualizar timestamp
        summary["last_update"] = datetime.now().isoformat()
        summary["interaction_count"] = len(summary["interactions"])

        # Guardar con ensure_ascii=True como fallback seguro
        with open(_SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    except Exception as e:
        log.error(f"Session summary error: {e}")


if __name__ == "__main__":
    main()
