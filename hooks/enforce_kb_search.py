#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
enforce_kb_search.py
====================
Hook que se ejecuta ANTES de cada respuesta.
OBLIGA la búsqueda en KB → Internet → ML.
Inyecta las fuentes en el contexto de la respuesta.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Agregar Hooks_IA al path
sys.path.insert(0, r"C:\Hooks_IA")

from core.kb_response_engine import process_query_with_kb


def extract_user_query(transcript_path: str) -> str:
    """
    Extrae el último mensaje del usuario del transcript.
    """
    try:
        with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        # Buscar último mensaje del usuario
        for line in reversed(lines):
            try:
                msg = json.loads(line)
                if msg.get('type') == 'user':
                    if 'content' in msg:
                        # Buscar el texto dentro de content
                        content = msg['content']
                        if isinstance(content, list):
                            for item in content:
                                if item.get('type') == 'text':
                                    return item.get('text', '')
                        elif isinstance(content, str):
                            return content
            except:
                pass

        return ""
    except:
        return ""


def create_kb_context(query: str) -> str:
    """
    Procesa la query a través del KB engine y retorna contexto.
    """
    try:
        result = process_query_with_kb(query)

        # Construir contexto inyectable
        context = f"""
=== KB SEARCH RESULTS ===
Query: {query}
Domain: {result['domain']}
KB Found: {result['kb_found']} entries
Coverage: KB {result['kb_pct']}% + Internet {result['internet_pct']}% + ML {result['ml_pct']}%

Top KB Results:
"""
        if result['kb_results']:
            for i, res in enumerate(result['kb_results'][:3], 1):
                context += f"\n{i}. [{res['domain']}] {res.get('key', 'N/A')}"
                if 'entry' in res and isinstance(res['entry'], dict):
                    context += f": {str(res['entry'])[:100]}"

        context += f"\n\n🔍 SOURCES FOOTER (MANDATORY):\n{result['sources_footer']}"

        if result['should_save']:
            context += "\n\n⚠️ AUTO-SAVE CONDITION MET: KB=0% && Response from Internet/ML"
            context += "\n(Respuesta será guardada automáticamente en KB)"

        return context

    except Exception as e:
        return f"KB Search Error: {str(e)}"


def inject_kb_context_to_transcript(transcript_path: str, kb_context: str) -> bool:
    """
    Inyecta el contexto KB al final del transcript para que el assistant lo vea.
    """
    try:
        # Leer transcript
        with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # Inyectar contexto antes del closing
        separator = "\n\n===KB_CONTEXT_INJECTION===\n"
        if separator not in content:
            content += separator + kb_context

        # Escribir de vuelta
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return True
    except:
        return False


def main(event_data: dict):
    """
    Hook principal que se ejecuta antes de la respuesta.
    """
    print("[KB_ENFORCE] Iniciando búsqueda obligatoria en KB...")

    try:
        transcript_path = event_data.get('transcript_path')
        if not transcript_path:
            print("[KB_ENFORCE] No transcript path provided")
            return {"status": "skip", "reason": "no_transcript"}

        # Extraer query del usuario
        query = extract_user_query(transcript_path)
        if not query:
            print("[KB_ENFORCE] No user query found")
            return {"status": "skip", "reason": "no_query"}

        print(f"[KB_ENFORCE] Processing query: {query[:50]}...")

        # Procesar a través de KB engine
        kb_context = create_kb_context(query)

        # Inyectar al transcript
        success = inject_kb_context_to_transcript(transcript_path, kb_context)

        if success:
            print("[KB_ENFORCE] ✅ KB context injected successfully")
            return {
                "status": "success",
                "query": query[:50],
                "context_injected": True
            }
        else:
            print("[KB_ENFORCE] ❌ Failed to inject KB context")
            return {"status": "error", "reason": "injection_failed"}

    except Exception as e:
        print(f"[KB_ENFORCE] Error: {str(e)}")
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    # Test manual
    print("=== Manual Test ===")

    # Simular evento
    test_event = {
        "hook_event_name": "before_response",
        "transcript_path": r"C:\Users\ntoledo\AppData\Local\ClaudeCode\.claude\projects\C--chance1\test_transcript.jsonl"
    }

    # Test KB engine directly
    query = "¿Cómo usar SAP Tierra?"
    print(f"\nProcessing: {query}")
    result = process_query_with_kb(query)

    print(f"Domain: {result['domain']}")
    print(f"KB Found: {result['kb_found']}")
    print(f"Coverage: KB {result['kb_pct']}% + Internet {result['internet_pct']}% + ML {result['ml_pct']}%")
    print(f"\n{result['sources_footer']}")
