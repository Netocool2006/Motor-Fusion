#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
web_search.py - Búsqueda web INTELIGENTE
=========================================
Pipeline:
  1. Recibe la pregunta conversacional del usuario
  2. Extrae keywords/intent para optimizar la query
  3. Busca en DuckDuckGo con query optimizada
  4. Filtra resultados por relevancia REAL vs la pregunta original
  5. Solo retorna internet_pct > 0 si los resultados SON relevantes

Usa DuckDuckGo (sin API key, sin límites duros).
"""

import logging
import re

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

log = logging.getLogger("web_search")

# Palabras que NO aportan a una búsqueda web
STOP_WORDS = {
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "que", "es",
    "por", "para", "con", "no", "se", "si", "ya", "al", "lo", "le", "me",
    "te", "su", "mi", "tu", "yo", "eso", "esto", "esta", "ese", "como",
    "pero", "mas", "o", "y", "a", "e", "u", "muy", "ser", "hay", "puede",
    "solo", "todo", "hace", "haz", "bien", "mal", "aqui", "ahi", "asi",
    "fue", "ser", "son", "está", "estan", "tiene", "tienen", "voy", "vamos",
    "quiero", "puedes", "podrias", "realiza", "mira", "dime", "sabes",
    "recuerdas", "entiendes", "listo", "ok", "bueno", "dale", "pues",
    "the", "is", "are", "was", "do", "does", "did", "can", "could",
    "would", "should", "will", "have", "has", "had", "not", "and", "or",
    "but", "if", "then", "so", "just", "also", "too", "this", "that",
    "what", "how", "why", "when", "where", "which", "who",
    # Meta-conversacionales (usuario hablando con Claude)
    "necesito", "quieres", "crees", "piensas", "opinas", "favor",
    "gracias", "porfa", "please", "thanks", "hey", "hola", "hello",
    "commit", "push", "procede", "procedes", "continua", "sigue",
}

# Indicadores de que la query es conversacional/meta (no buscar en internet)
META_PATTERNS = [
    r"^(hola|hey|gracias|ok|listo|dale|bueno|perfecto)",
    r"^(realiza|haz|ejecuta|crea|agrega|quita|borra|mueve)\s",
    r"(commit|push|pull|merge|branch|checkout)\b",
    r"^(si|no|correcto|exacto|entiendo)\b",
    r"(recuerdas|sabes|entiendes|puedes)\s+(lo|que|el|la)",
    # Preguntas sobre el propio sistema/hook/pipeline
    r"(hooks?\s*_?\s*ia|motor.?ia|pipeline|pre.?hook|post.?hook)",
    r"(kb|knowledge.?base|chromadb|internet_pct|ml_pct|kb_pct)",
    r"(funciona|funcionando|mintiendo|bypass|realmente|verdad)",
    # Preguntas dirigidas al asistente (meta-conversacion)
    r"(entenderte|explicame|te pregunto|te estoy|te pido|me dices)",
    r"(no esta buscando|no busca|busca otra cosa|busca mal)",
    # Instrucciones directas al asistente
    r"^(arregla|mejora|implementa|agrega|integra|cambia|modifica)\s",
    r"(este (proyecto|codigo|archivo|modulo|feature|sistema))",
    r"(comparativa|comparacion|versus|diferencia entre)",
]


def optimize_query(raw_query):
    """
    Convierte pregunta conversacional en search query optimizada.

    'esto de que primero busca en KB y luego en internet si funciona'
    → 'KB knowledge base internet search pipeline'

    'como solucionar error SAP GUI connection refused'
    → 'error SAP GUI connection refused solución'
    """
    # Si es muy corta o meta-conversacional, no buscar
    if len(raw_query) < 15:
        return None

    for pattern in META_PATTERNS:
        if re.search(pattern, raw_query.lower()):
            log.info(f"Query is meta/conversational, skipping web search: '{raw_query[:60]}'")
            return None

    # Extraer palabras significativas
    words = re.findall(r'\b\w+\b', raw_query.lower())
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 2]

    if len(keywords) < 2:
        log.info(f"Too few keywords ({len(keywords)}), skipping web search")
        return None

    # Limitar a las 8 keywords más largas/específicas (más largas = más específicas)
    keywords.sort(key=len, reverse=True)
    keywords = keywords[:8]

    optimized = " ".join(keywords)
    log.info(f"Query optimized: '{raw_query[:60]}' → '{optimized}'")
    return optimized


def compute_relevance(query_keywords, snippet):
    """
    Calcula relevancia REAL de un snippet vs la query.
    Retorna score 0.0 a 1.0
    """
    if not snippet or not query_keywords:
        return 0.0

    snippet_lower = snippet.lower()
    snippet_words = set(re.findall(r'\b\w+\b', snippet_lower))

    # Cuántas keywords de la query aparecen en el snippet
    query_words = set(re.findall(r'\b\w+\b', query_keywords.lower()))
    query_words -= STOP_WORDS

    if not query_words:
        return 0.0

    matches = query_words & snippet_words
    overlap = len(matches) / len(query_words)

    return round(overlap, 3)


def search_web(query, max_results=5):
    """
    Busca en internet via DuckDuckGo con query OPTIMIZADA
    y filtro de relevancia.

    Returns:
        dict con:
          - found: bool
          - results: list[dict] con title, url, snippet
          - summary: str (texto consolidado para inyectar a Claude)
          - internet_pct: int (cobertura estimada, 0 si irrelevante)
          - original_query: str
          - optimized_query: str
          - relevance_score: float
    """
    base_result = {
        "found": False, "results": [], "summary": "",
        "internet_pct": 0, "original_query": query[:200],
        "optimized_query": "", "relevance_score": 0.0,
    }

    try:
        # PASO 1: Optimizar query
        optimized = optimize_query(query)
        if not optimized:
            log.info(f"Web search SKIPPED: query not suitable for web search")
            return base_result

        base_result["optimized_query"] = optimized

        # PASO 2: Buscar en DuckDuckGo con query optimizada
        with DDGS() as ddgs:
            raw = list(ddgs.text(optimized, max_results=max_results, region="wt-wt"))

        if not raw:
            log.info(f"Web search: 0 results for '{optimized}'")
            return base_result

        # PASO 3: Filtrar por relevancia
        results = []
        summary_parts = []
        total_relevance = 0.0

        for i, r in enumerate(raw, 1):
            title = r.get("title", "")
            url = r.get("href", r.get("link", ""))
            snippet = r.get("body", r.get("snippet", ""))

            # Calcular relevancia de ESTE resultado vs la query
            relevance = compute_relevance(optimized, f"{title} {snippet}")

            # Solo incluir resultados con relevancia mínima
            if relevance < 0.15:
                log.info(f"Web result FILTERED (relevance={relevance:.2f}): {title[:60]}")
                continue

            results.append({
                "title": title, "url": url, "snippet": snippet,
                "relevance": relevance,
            })
            summary_parts.append(f"{len(results)}. **{title}**\n   {snippet}\n   Fuente: {url}")
            total_relevance += relevance

        if not results:
            log.info(f"Web search: {len(raw)} raw results but ALL filtered as irrelevant")
            return base_result

        summary = "\n".join(summary_parts)
        avg_relevance = total_relevance / len(results)

        # PASO 4: Calcular internet_pct basado en RELEVANCIA, no solo largo
        total_text = sum(len(r["snippet"]) for r in results)

        if avg_relevance >= 0.5 and total_text > 800:
            internet_pct = 70
        elif avg_relevance >= 0.4 and total_text > 400:
            internet_pct = 50
        elif avg_relevance >= 0.3 and total_text > 200:
            internet_pct = 30
        elif avg_relevance >= 0.2:
            internet_pct = 15
        else:
            internet_pct = 5

        log.info(
            f"Web search: {len(results)}/{len(raw)} relevant results, "
            f"~{total_text} chars, avg_relevance={avg_relevance:.2f}, "
            f"internet_pct={internet_pct}%"
        )

        return {
            "found": True,
            "results": results,
            "summary": summary,
            "internet_pct": internet_pct,
            "original_query": query[:200],
            "optimized_query": optimized,
            "relevance_score": round(avg_relevance, 3),
        }

    except Exception as e:
        log.error(f"Web search error: {e}")
        return base_result
