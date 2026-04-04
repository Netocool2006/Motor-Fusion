#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
motor_ia_hook.py - Hook principal Motor_IA
==========================================
REGLA PURA Y DURA - Los 3 pasos se ejecutan SIEMPRE, sin excepciones:

  1. Usuario pregunta en CLI
  2. PASO 1: Busca en KB (ChromaDB) - SIEMPRE
  3. PASO 2: Busca en Internet (DuckDuckGo) - SIEMPRE
  4. PASO 3: ML complementa lo que falte - SIEMPRE
  5. Inyecta los 3 como contexto a Claude
  6. Post-hook guarda conocimiento nuevo en KB

NO hay atajos. NO se salta ningún paso.
Los % se calculan por calidad real de cada fuente.

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
    PASO 1 (OBLIGATORIO): Busca en KB vectorial (ChromaDB local).
    SIEMPRE se ejecuta. Retorna contenido y % de cobertura real.
    Returns: (kb_content_str, kb_pct, similarity)
    """
    try:
        from core.vector_kb import ask_kb
        result = ask_kb(query)

        if not result["found"]:
            log.info("PASO1-KB: sin resultados relevantes -> kb_pct=0%")
            return "", 0, 0.0

        answer = result["answer"]
        answer_len = len(answer)
        similarity = result.get("similarity", 0.5)

        # Cobertura = largo x calidad (similitud)
        if answer_len > 500:
            base_pct = 85
        elif answer_len > 200:
            base_pct = 65
        elif answer_len > 80:
            base_pct = 40
        else:
            base_pct = 20

        # Factor de similitud: penaliza resultados de baja calidad
        if similarity >= 0.75:
            sim_factor = 1.0
        elif similarity >= 0.55:
            sim_factor = 0.5 + (similarity - 0.55) * 2.5
        else:
            sim_factor = max(0.3, similarity / 0.55 * 0.5)

        kb_pct = int(base_pct * sim_factor)
        kb_pct = max(5, min(90, kb_pct))  # Max 90% - siempre deja espacio para Internet+ML

        source = result.get("source", "vector_kb")
        kb_content = f"[NotebookLM]: {answer}"
        log.info(f"PASO1-KB: found=True, len={answer_len}, sim={similarity:.3f}, kb_pct={kb_pct}%")
        return kb_content, kb_pct, similarity

    except Exception as e:
        log.error(f"PASO1-KB error: {e}")
        return "", 0, 0.0


def search_internet(query):
    """
    PASO 2 (OBLIGATORIO): Busca en Internet via DuckDuckGo.
    SIEMPRE se ejecuta, sin importar el resultado del KB.
    Returns: (internet_content_str, internet_pct)
    """
    try:
        from core.web_search import search_web
        result = search_web(query)

        if not result["found"]:
            log.info("PASO2-INTERNET: sin resultados -> internet_pct=0%")
            return "", 0

        internet_content = f"[Internet Search Results]:\n{result['summary']}"
        internet_pct = result["internet_pct"]

        log.info(f"PASO2-INTERNET: found=True, internet_pct={internet_pct}%")
        return internet_content, internet_pct

    except Exception as e:
        log.error(f"PASO2-INTERNET error: {e}")
        return "", 0


_SESSION_FILE = _PROJECT / "core" / "session_summary.json"


def _check_session_continuity(query):
    """
    SIEMPRE carga el contexto de la sesión anterior.
    Solo se limpia si el usuario escribe /clean.
    Así Claude siempre sabe qué se estaba haciendo.
    """
    # Cargar resumen de sesión anterior (SIEMPRE)
    # Se inyecta como contexto para que Claude sepa qué se estaba haciendo
    # Si el usuario usa /clear de Claude CLI, limpia la conversación
    # pero el session_summary persiste como referencia
    try:
        if not _SESSION_FILE.exists():
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
        for i in interactions[-10:]:
            lines.append(f"  [{i.get('time','')}] Q: {i.get('query','')}")
            if i.get("answer_preview"):
                lines.append(f"         A: {i['answer_preview']}")

        session_text = "\n".join(lines)
        log.info(f"Session context loaded: {count} interactions")
        return session_text

    except Exception as e:
        log.error(f"Session continuity error: {e}")
        return None


def build_context(query, kb_content, kb_pct, internet_content, internet_pct, session_context=None):
    """
    Construye el additionalContext con los 3 pasos OBLIGATORIOS.
    SIEMPRE muestra el status de KB, Internet y ML.
    """
    timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    # Los % ya vienen normalizados desde main()
    ml_pct = max(0, 100 - kb_pct - internet_pct)

    context_parts = [
        "<motor_ia>",
        f"<timestamp>{timestamp}</timestamp>",
        f'<fuentes_estimadas kb="{kb_pct}%" internet="{internet_pct}%" ml="{ml_pct}%" />',
        '<pipeline_status paso1_kb="EJECUTADO" paso2_internet="EJECUTADO" paso3_ml="EJECUTADO" />',
    ]

    if session_context:
        context_parts.append("<session_anterior>")
        context_parts.append(
            "INSTRUCCION PROACTIVA: Al inicio de tu respuesta, SIEMPRE resume brevemente "
            "lo que se estuvo haciendo en la sesion anterior y pregunta si el usuario quiere "
            "continuar con eso o trabajar en algo nuevo. NO esperes a que el usuario pregunte. "
            "Tu DEBES tomar la iniciativa y decir algo como: "
            "'En la sesion anterior estuvimos trabajando en [X, Y, Z]. Quieres continuar con eso "
            "o prefieres trabajar en algo diferente?'"
        )
        context_parts.append("Aqui esta lo que se hizo en la sesion anterior:")
        context_parts.append(session_context)
        context_parts.append("</session_anterior>")

    # PASO 1: KB - SIEMPRE se muestra (con o sin resultados)
    context_parts.append("<paso1_kb>")
    if kb_content:
        context_parts.append(f"EJECUTADO - Cobertura: {kb_pct}%")
        context_parts.append("Se encontro conocimiento previo en el KB:")
        context_parts.append(kb_content)
    else:
        context_parts.append("EJECUTADO - Sin resultados relevantes (0%)")
    context_parts.append("</paso1_kb>")

    # PASO 2: Internet - SIEMPRE se muestra (con o sin resultados)
    context_parts.append("<paso2_internet>")
    if internet_content:
        context_parts.append(f"EJECUTADO - Cobertura: {internet_pct}%")
        context_parts.append("Busqueda web ejecutada automaticamente:")
        context_parts.append(internet_content)
    else:
        context_parts.append("EJECUTADO - Sin resultados relevantes (0%)")
    context_parts.append("</paso2_internet>")

    # PASO 3: ML - SIEMPRE se muestra
    context_parts.append("<paso3_ml>")
    context_parts.append(f"ACTIVO - Complemento: {ml_pct}%")
    context_parts.append("Claude complementa con su conocimiento lo que KB e Internet no cubrieron.")
    context_parts.append("</paso3_ml>")

    # Instrucciones consolidadas
    context_parts.append("<instrucciones>")
    context_parts.append(
        "REGLA PURA: Los 3 pasos se ejecutaron OBLIGATORIAMENTE. "
        f"KB aporto {kb_pct}%, Internet aporto {internet_pct}%, ML complementa {ml_pct}%. "
        "Usa TODA la informacion disponible de los 3 pasos en orden de prioridad: "
        "1ro KB, 2do Internet, 3ro ML. "
        "Si KB e Internet cubren bien, ML solo valida. "
        "Si KB e Internet no cubren, ML llena los vacios."
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
    """
    Entry point del hook.
    REGLA PURA Y DURA: Los 3 pasos se ejecutan SIEMPRE.
    No hay condicionales, no hay atajos, no hay excepciones.
    """
    try:
        query = get_user_query()

        if not is_valid_query(query):
            print(json.dumps({}))
            return

        log.info(f"{'='*60}")
        log.info(f"QUERY: {query[:120]}")
        log.info("PIPELINE: Ejecutando 3 pasos OBLIGATORIOS...")

        # PASO 0: Cargar contexto de sesion anterior (SIEMPRE)
        session_context = _check_session_continuity(query)

        # ============================================================
        # PASO 1: KB (ChromaDB) - OBLIGATORIO, SIEMPRE SE EJECUTA
        # ============================================================
        log.info("PASO 1/3: Buscando en KB local (ChromaDB)...")
        kb_content, kb_pct, kb_similarity = search_kb(query)
        log.info(f"PASO 1/3 COMPLETADO: kb_pct={kb_pct}%, sim={kb_similarity:.3f}")

        # ============================================================
        # PASO 2: Internet (DuckDuckGo) - OBLIGATORIO, SIEMPRE SE EJECUTA
        # ============================================================
        log.info("PASO 2/3: Buscando en Internet (DuckDuckGo)...")
        internet_content, internet_pct = search_internet(query)
        log.info(f"PASO 2/3 COMPLETADO: internet_pct={internet_pct}%")

        # ============================================================
        # PASO 3: ML - OBLIGATORIO, complementa lo que falta
        # ============================================================
        # Normalizar porcentajes
        total_sources = kb_pct + internet_pct
        if total_sources > 95:
            # Dejar al menos 5% para ML (siempre participa)
            ratio = 95.0 / total_sources
            kb_pct = int(kb_pct * ratio)
            internet_pct = int(internet_pct * ratio)
        ml_pct = max(5, 100 - kb_pct - internet_pct)  # Minimo 5% ML siempre
        log.info(f"PASO 3/3: ML complementa con {ml_pct}%")

        log.info(f"PIPELINE COMPLETO: KB={kb_pct}% + Internet={internet_pct}% + ML={ml_pct}% = 100%")

        # Construir contexto con los 3 pasos
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
