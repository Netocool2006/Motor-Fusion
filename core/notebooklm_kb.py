#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
notebooklm_kb.py - Motor KB via NotebookLM (reemplaza drive_kb.py)
==================================================================
Consulta y alimenta NotebookLM directamente usando notebooklm-py.

Funciones principales:
  ask_kb(query)       -> Pregunta a NotebookLM IA (semántica, no keyword)
  save_to_kb(query, answer, source) -> Sube conocimiento nuevo como source
"""

import asyncio
import logging
from pathlib import Path
from datetime import datetime

log = logging.getLogger("notebooklm_kb")

_PROJECT = Path(__file__).resolve().parent.parent

# Notebook ID desde .env
_NOTEBOOK_ID = None


def _load_notebook_id():
    global _NOTEBOOK_ID
    if _NOTEBOOK_ID:
        return _NOTEBOOK_ID

    env_file = _PROJECT / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("NOTEBOOKLM_NOTEBOOK_ID="):
                    _NOTEBOOK_ID = line.split("=", 1)[1].strip()
                    return _NOTEBOOK_ID

    raise ValueError("NOTEBOOKLM_NOTEBOOK_ID not found in .env")


async def _get_client():
    """Crea y retorna un NotebookLMClient autenticado."""
    from notebooklm import NotebookLMClient
    client = await NotebookLMClient.from_storage()
    await client.__aenter__()
    return client


async def _ask_kb_async(query):
    """Pregunta a NotebookLM y retorna respuesta con citas."""
    notebook_id = _load_notebook_id()
    client = await _get_client()
    try:
        result = await client.chat.ask(notebook_id, query)
        return result
    finally:
        await client.__aexit__(None, None, None)


async def _save_to_kb_async(title, content):
    """Sube texto como nueva source a NotebookLM."""
    notebook_id = _load_notebook_id()
    client = await _get_client()
    try:
        source = await client.sources.add_text(
            notebook_id, title, content, wait=True, wait_timeout=60.0
        )
        return source
    finally:
        await client.__aexit__(None, None, None)


def ask_kb(query):
    """
    Pregunta al KB - primero busca en cache local, luego en NotebookLM.

    Returns:
        dict con:
          - answer: str (respuesta de NotebookLM IA o cache)
          - raw: objeto AskResult completo (None si viene de cache)
          - found: bool (si encontró conocimiento relevante)
          - source: str ("cache" o "notebooklm")
    """
    # PASO 0: Buscar en cache local (no gasta chats de NotebookLM)
    try:
        from core.kb_cache import search_cache, save_to_cache
        cached = search_cache(query)
        if cached and cached["found"]:
            log.info(
                f"CACHE HIT: sim={cached['similarity']:.2f}, "
                f"age={cached['cache_age_hours']:.1f}h, "
                f"original='{cached['cached_query'][:50]}'"
            )
            return {
                "answer": cached["answer"],
                "raw": None,
                "found": True,
                "source": "cache",
            }
    except Exception as e:
        log.warning(f"Cache search error (continuing to NotebookLM): {e}")

    # PASO 1: Cache miss - preguntar a NotebookLM (gasta 1 chat)
    try:
        result = asyncio.run(_ask_kb_async(query))

        # AskResult tiene .raw_response - extraer la respuesta
        raw = result.raw_response if result else None

        if raw:
            answer_text = _extract_answer(raw)
        else:
            answer_text = ""

        # Detectar si NotebookLM realmente encontró algo
        found = bool(answer_text and len(answer_text) > 20)

        # Detectar respuestas "no encontré nada" o meta-respuestas sin contenido real
        no_info_phrases = [
            "no tengo información",
            "no encuentro",
            "no hay información",
            "i don't have",
            "i cannot find",
            "not mentioned",
            "no relevant",
            "provided sources don't",
            # Meta-respuestas donde NotebookLM describe su proceso en vez de dar info
            "i'm currently",
            "i'm now focusing",
            "i'm reviewing",
            "i'm deep-diving",
            "i'm thinking about",
            "my current focus",
            "my next phase",
            "checking recipe",
            "checking availability",
            "reviewing the provided sources",
            "exploring the provided",
            "analyzing the provided",
            "let me check",
            "let me review",
            "based on the sources provided, i",
        ]
        if any(phrase in answer_text.lower() for phrase in no_info_phrases):
            found = False

        log.info(f"NotebookLM ask: found={found}, len={len(answer_text)}")

        # Guardar en cache si encontró algo (para no gastar chat la próxima vez)
        if found and answer_text:
            try:
                save_to_cache(query, answer_text)
            except Exception as e:
                log.warning(f"Cache save error: {e}")

        return {
            "answer": answer_text,
            "raw": raw,
            "found": found,
            "source": "notebooklm",
        }

    except FileNotFoundError:
        log.error("NotebookLM not authenticated. Run: notebooklm login")
        return {"answer": "", "raw": None, "found": False, "source": "error"}
    except Exception as e:
        log.error(f"NotebookLM ask error: {e}")
        return {"answer": "", "raw": None, "found": False, "source": "error"}


def save_to_kb(query, answer, source="ML"):
    """
    Guarda conocimiento nuevo en NotebookLM como source de texto.

    Args:
        query: Pregunta original
        answer: Respuesta a guardar
        source: Origen ("Internet", "ML", etc.)

    Returns:
        str: source_id del source creado, o None si falla
    """
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        title = f"Learned: {query[:80]}"
        content = (
            f"# {query}\n\n"
            f"**Fuente:** {source}\n"
            f"**Fecha:** {timestamp}\n\n"
            f"{answer}\n"
        )

        result = asyncio.run(_save_to_kb_async(title, content))

        if result:
            source_id = getattr(result, "id", None) or str(result)
            log.info(f"NotebookLM save OK: '{title}' -> {source_id}")
            return source_id
        return None

    except FileNotFoundError:
        log.error("NotebookLM not authenticated. Run: notebooklm login")
        return None
    except Exception as e:
        log.error(f"NotebookLM save error: {e}")
        return None


def _extract_answer(raw):
    """Extrae texto de respuesta del raw_response de NotebookLM.

    Formato streaming batchexecute:
      )]}'
      <length>
      [["wrb.fr",null,"[[\"answer text\\n...\",null,...]]",...]]
      <length>
      [["wrb.fr",null,"[[\"refined answer\\n...\",null,...]]",...]]

    El último chunk wrb.fr tiene la respuesta más completa.
    """
    import json

    if not isinstance(raw, str):
        return str(raw)

    text = raw
    if text.startswith(")]}'"):
        text = text[4:]

    # Parse each line - find all JSON array lines
    answers = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line.startswith('[["wrb.fr"'):
            continue
        try:
            outer = json.loads(line)
            # outer = [["wrb.fr", null, "<inner json string>", ...], ...]
            inner_str = outer[0][2]
            if not inner_str:
                continue
            inner = json.loads(inner_str)
            # inner = [["answer text", null, [conversation_id, ...], ...]]
            if isinstance(inner, list) and inner:
                first = inner[0] if not isinstance(inner[0], list) else inner[0][0] if inner[0] else None
                if isinstance(first, str) and len(first) > 10:
                    answers.append(first)
        except (json.JSONDecodeError, IndexError, TypeError, KeyError):
            continue

    if answers:
        # Last answer is the most complete (streaming refinement)
        return answers[-1].strip()

    # Fallback: regex extract from partially parsed streaming response
    import re
    # Look for the answer text pattern: \"**Title**\\n\\nContent
    match = re.search(r'\[\[\\?"\\?\*\*(.+?)(?:\\\\n|")', text)
    if match:
        # Try to extract the full text block
        # Find the largest escaped string that starts with **
        blocks = re.findall(r'\\?"(\*\*[^"]{20,}?)\\?"', text)
        if blocks:
            answer = max(blocks, key=len)
            return answer.replace("\\\\n", "\n").replace("\\n", "\n").replace('\\"', '"').strip()

    return text[:500]
