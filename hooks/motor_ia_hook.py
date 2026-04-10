#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
motor_ia_hook.py - Hook principal Motor_IA (Modo Hibrido v2)
============================================================
ARQUITECTURA HIBRIDA:
  - Hook LIGERO: solo inyecta instrucciones + contexto de sesion (~200 tokens)
  - Claude usa herramientas MCP para buscar KB e Internet con INTELIGENCIA
  - Pipeline: KB → Internet → ML (Claude decide el flujo)

El hook ya NO busca en KB ni Internet -- Claude lo hace via MCP tools:
  - buscar_kb: busca en ChromaDB con inteligencia semantica
  - buscar_internet: busca en DuckDuckGo con query optimizada
  - guardar_aprendizaje: guarda conocimiento nuevo en KB

Hook type: UserPromptSubmit
Output: additionalContext (instrucciones minimas para Claude)
"""

import sys
import json
import logging
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

# State file
_STATE_FILE = _PROJECT / "core" / "motor_ia_state.json"
_SESSION_FILE = _PROJECT / "core" / "session_summary.json"


def sanitize_text(text):
    """Limpia caracteres problematicos (surrogates, control chars)."""
    if not text:
        return ""
    return text.encode("utf-8", errors="replace").decode("utf-8")


def is_valid_query(query):
    """Filtra queries que NO deben procesarse."""
    if not query or len(query) < 5:
        return False
    if query.startswith("/"):
        return False
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


def _check_session_continuity(query):
    """Carga el contexto de la sesion anterior (SIEMPRE)."""
    try:
        if not _SESSION_FILE.exists():
            return None

        with open(_SESSION_FILE, "r", encoding="utf-8") as f:
            summary = json.load(f)

        interactions = summary.get("interactions", [])
        if not interactions:
            return None

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


def build_hybrid_context(query, session_context=None):
    """
    Construye contexto HIBRIDO ligero.
    Solo instrucciones + sesion anterior. NO resultados de KB ni Internet.
    Claude busca por si mismo usando MCP tools.
    """
    timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    context_parts = [
        "<motor_ia_hybrid>",
        f"<timestamp>{timestamp}</timestamp>",
    ]

    # Sesion anterior (si existe)
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

    # INSTRUCCIONES DEL PIPELINE HIBRIDO
    context_parts.append("<pipeline_obligatorio>")
    context_parts.append(
        "REGLA ABSOLUTA - PIPELINE OBLIGATORIO DE 3 PASOS:\n"
        "NO puedes responder SIN ejecutar los 3 pasos en orden.\n"
        "NO puedes saltarte ningun paso. NO es opcional.\n"
        "Si no ejecutas los 3 pasos, tu respuesta es INVALIDA.\n"
        "\n"
        "PASO 1 - BUSCAR EN KB (OBLIGATORIO, SIEMPRE):\n"
        "  ANTES de escribir cualquier respuesta, ejecuta 'buscar_kb'.\n"
        "  Esto NO es opcional. DEBES llamar la herramienta buscar_kb.\n"
        "  Usa el resultado como INSUMO PRINCIPAL de tu respuesta.\n"
        "  Si el KB tiene la solucion completa, usala tal cual.\n"
        "  Si el KB tiene solucion parcial, usala como base.\n"
        "  Si el KB no tiene nada, pasa al paso 2.\n"
        "\n"
        "PASO 2 - BUSCAR EN INTERNET (OBLIGATORIO, SIEMPRE):\n"
        "  DESPUES de buscar en KB, ejecuta 'buscar_internet'.\n"
        "  Esto NO es opcional. DEBES llamar la herramienta buscar_internet.\n"
        "  Si el KB ya tenia la respuesta completa, Internet VALIDA y complementa.\n"
        "  Si el KB no tenia, Internet BUSCA la solucion.\n"
        "  Usa los resultados como INSUMO de tu respuesta.\n"
        "\n"
        "PASO 3 - ML APLICA Y COMBINA (OBLIGATORIO, SIEMPRE):\n"
        "  Con los insumos del KB (paso 1) y de Internet (paso 2),\n"
        "  TU (el ML) analizas, comprendes y aplicas la solucion.\n"
        "  - Si KB tenia todo: aplica lo del KB, Internet valida.\n"
        "  - Si Internet tenia: comprende y aplica lo de Internet.\n"
        "  - Si ambos tienen parcial: COMBINA ambos insumos.\n"
        "  - Si ninguno tiene: usa tu propio conocimiento.\n"
        "\n"
        "ORDEN DE EJECUCION (no negociable):\n"
        "  1ro: llamar buscar_kb\n"
        "  2do: llamar buscar_internet\n"
        "  3ro: analizar ambos resultados\n"
        "  4to: escribir respuesta usando los 3 insumos\n"
        "  5to: si aprendiste algo nuevo, llamar guardar_aprendizaje\n"
        "\n"
        "UNICA EXCEPCION (cuando NO buscar):\n"
        "  - Saludos: hola, gracias, ok, listo, dale\n"
        "  - Instrucciones directas de codigo: commit, push, crea archivo, etc.\n"
        "  - Confirmaciones: si, no, correcto, exacto\n"
        "  En estos casos, responde directamente sin buscar.\n"
        "  Para TODO lo demas: los 3 pasos son OBLIGATORIOS."
    )
    context_parts.append("</pipeline_obligatorio>")

    # Reporte de fuentes
    context_parts.append(
        "<reporte_fuentes>"
        "AL FINAL de tu respuesta, incluye SIEMPRE una linea con el formato: "
        "**Fuentes:** KB X% + Internet Y% + ML Z% "
        "donde X+Y+Z = 100. Ajusta los % segun de donde vino realmente cada parte. "
        "Si usaste buscar_kb, KB sube. Si usaste buscar_internet, Internet sube. "
        "Si usaste tu conocimiento, ML sube."
        "</reporte_fuentes>"
    )

    context_parts.append(
        "<auto_save>"
        "IMPORTANTE: Si resolviste algo con Internet o ML que no estaba en KB, "
        "usa guardar_aprendizaje para guardarlo automaticamente."
        "</auto_save>"
    )

    context_parts.append("</motor_ia_hybrid>")
    return "\n".join(context_parts)


def save_state(query):
    """Guarda estado minimo para el post-hook."""
    try:
        state = {
            "timestamp": datetime.now().isoformat(),
            "query": sanitize_text(query),
            "mode": "hybrid",
            "needs_save": True,
        }
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Save state error: {e}")


def main():
    """
    Entry point del hook HIBRIDO.
    Inyecta instrucciones ligeras. Claude hace el trabajo pesado via MCP.
    """
    try:
        # BYPASS: If called from cerebro_v2 or SDK, skip all hook processing
        import os
        entrypoint = os.environ.get("CLAUDE_CODE_ENTRYPOINT", "")
        if entrypoint.startswith("sdk-"):
            # Programmatic call — don't inject session context or instructions
            print(json.dumps({}))
            return

        query = get_user_query()

        if not is_valid_query(query):
            print(json.dumps({}))
            return

        log.info(f"{'='*60}")
        log.info(f"QUERY: {query[:120]}")
        log.info("MODE: HYBRID - Claude searches via MCP tools")

        # Cargar contexto de sesion anterior
        session_context = _check_session_continuity(query)

        # Construir contexto ligero (solo instrucciones)
        context = build_hybrid_context(query, session_context)

        # Guardar estado para post-hook
        save_state(query)

        # -- Background features (no bloquean, no inyectan basura) --

        # Async Memory: procesar pendientes
        try:
            from core.async_memory import process_pending
            processed = process_pending()
            if processed > 0:
                log.info(f"ASYNC_MEMORY: processed {processed} pending operations")
        except Exception:
            pass

        # Memory Tiers: degradar items viejos
        try:
            from core.memory_tiers import run_degradation
            degraded = run_degradation()
            if degraded > 0:
                log.info(f"MEMORY_TIERS: degraded {degraded} items")
        except Exception:
            pass

        # Typed Graph: inferir relaciones
        try:
            from core.typed_graph import infer_and_store
            inferred = infer_and_store(query, context="pre-hook query")
            if inferred > 0:
                log.info(f"TYPED_GRAPH: inferred {inferred} relations from query")
        except Exception:
            pass

        # Output para Claude Code
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context,
            }
        }
        print(json.dumps(output))

        log.info(f"HYBRID: context_len={len(context)} tokens (instructions only)")

    except Exception as e:
        log.error(f"Hook error: {e}")
        print(json.dumps({}))


if __name__ == "__main__":
    main()
