#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
motor_ia_hook.py - Hook principal Motor_IA
==========================================
Flujo FORZADO por código (no por sugerencia):

  1. Usuario pregunta en CLI
  2. Busca en NotebookLM (KB semántico)
  3. Si KB < 80% -> EJECUTA búsqueda web (DuckDuckGo) automáticamente
  4. Inyecta KB + Internet como contexto a Claude
  5. Claude solo complementa con ML lo que falte
  6. Post-hook guarda conocimiento nuevo en NotebookLM

Hook type: UserPromptSubmit
Output: additionalContext (inyectado al contexto de Claude)
"""

import sys
import json
import logging
import re
from pathlib import Path
from datetime import datetime

# Setup paths
_HOOK_DIR = Path(__file__).resolve().parent
_PROJECT = _HOOK_DIR.parent
sys.path.insert(0, str(_PROJECT))

# Logging
_LOG_FILE = _PROJECT / "core" / "motor_ia_hook.log"
logging.basicConfig(
    filename=str(_LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("motor_ia")

# State file - stores last query result for post-response processing
_STATE_FILE = _PROJECT / "core" / "motor_ia_state.json"


def sanitize_text(text):
    """Limpia caracteres problemáticos (surrogates, control chars)."""
    if not text:
        return ""
    # Remove surrogate characters that crash utf-8 encoding
    return text.encode("utf-8", errors="replace").decode("utf-8")


def is_valid_query(query):
    """Filtra queries que NO deben ir al KB (basura, system tags, etc)."""
    if not query or len(query) < 5:
        return False
    if query.startswith("/"):
        return False
    # Filtrar task-notifications y XML del sistema
    if "<task-notification>" in query or "<task-id>" in query:
        return False
    if query.startswith("<") and ">" in query[:50]:
        return False
    return True


def get_user_query():
    """Extrae la pregunta del usuario desde stdin (UserPromptSubmit)."""
    try:
        raw_input = sys.stdin.read()
        raw_input = sanitize_text(raw_input)
        input_data = json.loads(raw_input)
        query = input_data.get("prompt", "")
        if not query and "messages" in input_data:
            msgs = input_data["messages"]
            if msgs:
                last = msgs[-1]
                if isinstance(last, dict):
                    query = last.get("content", "")
        return sanitize_text(query.strip()) if query else None
    except Exception as e:
        log.error(f"Error reading input: {e}")
        return None


def search_kb(query):
    """
    PASO 1: Busca en KB vectorial (ChromaDB local).
    Sin límites, instantáneo, offline.
    Returns: (kb_content_str, kb_pct)
    """
    try:
        from core.vector_kb import ask_kb
        result = ask_kb(query)

        if not result["found"]:
            log.info("KB: no relevant knowledge found")
            return "", 0

        answer = result["answer"]
        answer_len = len(answer)

        if answer_len > 500:
            kb_pct = 85
        elif answer_len > 200:
            kb_pct = 65
        elif answer_len > 80:
            kb_pct = 40
        else:
            kb_pct = 20

        source = result.get("source", "notebooklm")
        kb_content = f"[NotebookLM]: {answer}"
        log.info(f"KB: found={result['found']}, len={answer_len}, kb_pct={kb_pct}%, source={source}")
        return kb_content, kb_pct

    except Exception as e:
        log.error(f"KB search error: {e}")
        return "", 0


def search_internet(query):
    """
    PASO 2 (FORZADO): Búsqueda web via DuckDuckGo.
    Se ejecuta automáticamente cuando KB < 80%.
    Returns: (internet_content_str, internet_pct)
    """
    try:
        from core.web_search import search_web
        result = search_web(query)

        if not result["found"]:
            log.info("Web search: no results found")
            return "", 0

        internet_content = f"[Internet Search Results]:\n{result['summary']}"
        internet_pct = result["internet_pct"]

        log.info(f"Web search: FORCED, found={result['found']}, internet_pct={internet_pct}%")
        return internet_content, internet_pct

    except Exception as e:
        log.error(f"Web search error: {e}")
        return "", 0


_SESSION_FILE = _PROJECT / "core" / "session_summary.json"


def _check_session_continuity(query):
    """
    Detecta si el usuario quiere continuar la sesión anterior.
    Busca frases como "sigue", "continua", "donde quedamos", etc.
    Retorna el resumen de la sesión anterior o None.
    """
    continue_phrases = [
        "sigue", "continua", "continúa", "donde quedamos", "que estabas haciendo",
        "sesion anterior", "sesión anterior", "lo que dejaste", "retoma",
        "en que ibamos", "en qué íbamos", "que falta", "qué falta",
        "pendiente", "ultimo que hiciste", "último que hiciste",
    ]

    query_lower = query.lower()
    is_continue = any(phrase in query_lower for phrase in continue_phrases)

    if not is_continue:
        return None

    # Cargar resumen de sesión anterior
    try:
        if not _SESSION_FILE.exists():
            log.info("Session continuity: no previous session found")
            return None

        with open(_SESSION_FILE, "r", encoding="utf-8") as f:
            summary = json.load(f)

        interactions = summary.get("interactions", [])
        if not interactions:
            return None

        # Construir resumen legible
        session_start = summary.get("session_start", "desconocido")
        count = summary.get("interaction_count", len(interactions))

        lines = [f"Sesion anterior ({session_start[:10]}, {count} interacciones):"]
        for i in interactions[-10:]:  # Últimas 10
            lines.append(f"  [{i.get('time','')}] Q: {i.get('query','')}")
            if i.get("answer_preview"):
                lines.append(f"         A: {i['answer_preview']}")

        session_text = "\n".join(lines)
        log.info(f"Session continuity: loaded {count} interactions from previous session")
        return session_text

    except Exception as e:
        log.error(f"Session continuity error: {e}")
        return None


def build_context(query, kb_content, kb_pct, internet_content, internet_pct, session_context=None):
    """
    Construye el additionalContext con datos REALES de KB + Internet.
    Claude solo complementa con ML lo que falte.
    """
    timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    # Los % ya vienen normalizados desde main()
    ml_pct = max(0, 100 - kb_pct - internet_pct)

    context_parts = [
        "<motor_ia>",
        f"<timestamp>{timestamp}</timestamp>",
        f'<fuentes_estimadas kb="{kb_pct}%" internet="{internet_pct}%" ml="{ml_pct}%" />',
    ]

    if session_context:
        context_parts.append("<session_anterior>")
        context_parts.append("El usuario quiere continuar. Aqui esta lo que se hizo en la sesion anterior:")
        context_parts.append(session_context)
        context_parts.append("</session_anterior>")

    if kb_content:
        context_parts.append("<kb_knowledge>")
        context_parts.append("Se encontro conocimiento previo en el KB:")
        context_parts.append(kb_content)
        context_parts.append("</kb_knowledge>")

    if internet_content:
        context_parts.append("<internet_knowledge>")
        context_parts.append("Busqueda web EJECUTADA automaticamente (resultados reales):")
        context_parts.append(internet_content)
        context_parts.append("</internet_knowledge>")

    # Instrucciones para Claude
    context_parts.append("<instrucciones>")
    if kb_pct >= 80:
        context_parts.append(
            f"El KB tiene buena cobertura ({kb_pct}%). "
            "Usa el conocimiento del KB como base principal. "
            "Complementa con tu inteligencia (ML) solo lo que falte. "
        )
    elif kb_pct > 0 and internet_pct > 0:
        context_parts.append(
            f"El KB tiene informacion parcial ({kb_pct}%). "
            f"Se complemento con busqueda en Internet ({internet_pct}%). "
            "Lo que no encuentres en Internet, completalo con tu inteligencia (ML). "
        )
    elif internet_pct > 0:
        context_parts.append(
            "No se encontro conocimiento en el KB. "
            f"Se busco en Internet y se encontraron resultados ({internet_pct}%). "
            "Usa los resultados de Internet como base. "
            "Complementa con tu inteligencia (ML) lo que falte. "
        )
    else:
        context_parts.append(
            "No se encontro conocimiento en el KB ni en Internet. "
            "Usa tu inteligencia (ML) para responder. "
        )
    context_parts.append("</instrucciones>")

    context_parts.append(
        "<reporte_fuentes>"
        "AL FINAL de tu respuesta, incluye SIEMPRE una linea con el formato: "
        "**Fuentes:** KB X% + Internet Y% + ML Z% "
        "donde X+Y+Z = 100. Ajusta los % segun de donde vino realmente cada parte. "
        "Si usaste WebSearch, Internet sube. Si KB tenia la respuesta, KB sube. "
        "Si usaste tu conocimiento, ML sube."
        "</reporte_fuentes>"
    )

    context_parts.append(
        "<auto_save>"
        "IMPORTANTE: Despues de responder, el sistema guardara automaticamente "
        "el conocimiento nuevo (de Internet y ML) en el KB para futuras consultas."
        "</auto_save>"
    )

    context_parts.append("</motor_ia>")
    return "\n".join(context_parts)


def save_state(query, kb_pct, internet_pct):
    """Guarda estado para el post-hook (auto-save al KB)."""
    try:
        # needs_save = TRUE si Internet o ML contribuyeron algo
        # Porque TODO lo que no vino del KB debe subir al KB para futuras consultas
        ml_pct = max(0, 100 - kb_pct - internet_pct)
        needs_save = (internet_pct > 0) or (ml_pct > 0)
        state = {
            "timestamp": datetime.now().isoformat(),
            "query": sanitize_text(query),
            "kb_pct": kb_pct,
            "internet_pct": internet_pct,
            "ml_pct": ml_pct,
            "needs_save": needs_save,
        }
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Save state error: {e}")


def main():
    """Entry point del hook."""
    try:
        query = get_user_query()

        if not is_valid_query(query):
            print(json.dumps({}))
            return

        log.info(f"{'='*60}")
        log.info(f"QUERY: {query[:120]}")

        # PASO 0: Detectar si pide continuar sesión anterior
        session_context = _check_session_continuity(query)

        # PASO 1: Buscar en KB (ChromaDB)
        kb_content, kb_pct = search_kb(query)

        # PASO 2: Si KB < 80%, FORZAR búsqueda web (no sugerencia, EJECUCIÓN)
        internet_content = ""
        internet_pct = 0
        if kb_pct < 80:
            log.info(f"KB={kb_pct}% < 80% -> FORCING web search...")
            internet_content, internet_pct = search_internet(query)

        # Normalizar porcentajes ANTES de usarlos en contexto y estado
        total_sources = kb_pct + internet_pct
        if total_sources > 100:
            ratio = 100.0 / total_sources
            kb_pct = int(kb_pct * ratio)
            internet_pct = int(internet_pct * ratio)
        ml_pct = max(0, 100 - kb_pct - internet_pct)

        # Construir contexto con datos REALES (ya normalizados)
        context = build_context(query, kb_content, kb_pct, internet_content, internet_pct, session_context)

        # Guardar estado para post-hook
        save_state(query, kb_pct, internet_pct)

        # Output para Claude Code
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context,
            }
        }
        print(json.dumps(output))

        log.info(f"RESULT: KB={kb_pct}%, Internet={internet_pct}%, ML={ml_pct}%, context_len={len(context)}")

    except Exception as e:
        log.error(f"Hook error: {e}")
        print(json.dumps({}))


if __name__ == "__main__":
    main()
