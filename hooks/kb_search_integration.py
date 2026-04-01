#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kb_search_integration.py
========================
Hook que se ejecuta ANTES de que Claude responda.
Guarda en KB cualquier respuesta que NO fue encontrada en KB.

Se dispara: Post-respuesta (cuando se cierra la sesión)
"""

import json
import sys
from pathlib import Path

# Agregar Hooks_IA al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.search_protocol import search_kb, save_to_kb, should_save_to_kb
from core.timezone_utils import format_ca_datetime


def extract_from_transcript(transcript_path: str) -> dict:
    """
    Lee el transcript y extrae:
    - La pregunta del usuario (último mensaje)
    - La respuesta de Claude (penúltimo mensaje si es assistant)
    """
    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        messages = data.get('messages', [])
        if len(messages) < 2:
            return None

        # Última pregunta del usuario
        user_msg = None
        asst_msg = None

        # Buscar hacia atrás
        for msg in reversed(messages):
            if msg.get('role') == 'user' and not user_msg:
                user_msg = msg.get('content', '')
            elif msg.get('role') == 'assistant' and not asst_msg:
                asst_msg = msg.get('content', '')

            if user_msg and asst_msg:
                break

        if not user_msg or not asst_msg:
            return None

        return {
            'query': user_msg[:200],  # Primeros 200 chars
            'answer': asst_msg[:500],  # Primeros 500 chars
        }
    except Exception as e:
        print(f"[KB_SEARCH] Error extrayendo transcript: {e}")
        return None


def process_session(transcript_path: str, verbose: bool = False) -> dict:
    """
    Procesa una sesión y guarda respuestas nuevas en KB.
    """
    result = {
        'processed': False,
        'saved': False,
        'query': None,
        'domain': None,
        'key': None
    }

    extracted = extract_from_transcript(transcript_path)
    if not extracted:
        return result

    query = extracted['query']
    answer = extracted['answer']

    if verbose:
        print(f"[KB_SEARCH] Query: {query[:100]}...")

    # Buscar en KB
    kb_results = search_kb(query, limit=3)
    kb_coverage = 100 if kb_results else 0

    if verbose:
        print(f"[KB_SEARCH] KB Coverage: {kb_coverage}%")

    # Si no hay en KB, guardar
    if should_save_to_kb(kb_coverage, 50, 50):  # Asumir 50/50 Internet/ML
        save_result = save_to_kb(query, answer)
        if save_result['saved']:
            result['processed'] = True
            result['saved'] = True
            result['query'] = query
            result['domain'] = save_result['domain']
            result['key'] = save_result['key']

            if verbose:
                print(f"[KB_SEARCH] Guardado en {save_result['domain']}: {save_result['key']}")

    return result


if __name__ == "__main__":
    # Uso: python kb_search_integration.py <transcript_path>
    if len(sys.argv) > 1:
        transcript = sys.argv[1]
        result = process_session(transcript, verbose=True)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("[KB_SEARCH] Uso: python kb_search_integration.py <transcript_path>")
