#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
web_search.py - Búsqueda web FORZADA por código
================================================
Cuando el KB no cubre la consulta, este módulo ejecuta
la búsqueda en internet directamente (no depende de Claude).

Usa DuckDuckGo (sin API key, sin límites duros).
"""

import logging
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

log = logging.getLogger("web_search")


def search_web(query, max_results=5):
    """
    Busca en internet via DuckDuckGo.

    Returns:
        dict con:
          - found: bool
          - results: list[dict] con title, url, snippet
          - summary: str (texto consolidado para inyectar a Claude)
          - internet_pct: int (cobertura estimada)
    """
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results, region="wt-wt"))

        if not raw:
            log.info(f"Web search: 0 results for '{query[:60]}'")
            return {"found": False, "results": [], "summary": "", "internet_pct": 0}

        results = []
        summary_parts = []

        for i, r in enumerate(raw, 1):
            title = r.get("title", "")
            url = r.get("href", r.get("link", ""))
            snippet = r.get("body", r.get("snippet", ""))

            results.append({"title": title, "url": url, "snippet": snippet})
            summary_parts.append(f"{i}. **{title}**\n   {snippet}\n   Fuente: {url}")

        summary = "\n".join(summary_parts)

        # Estimar cobertura por cantidad/calidad de resultados
        total_text = sum(len(r["snippet"]) for r in results)
        if total_text > 800:
            internet_pct = 70
        elif total_text > 400:
            internet_pct = 50
        elif total_text > 150:
            internet_pct = 30
        else:
            internet_pct = 15

        log.info(f"Web search: {len(results)} results, ~{total_text} chars, internet_pct={internet_pct}%")
        return {
            "found": True,
            "results": results,
            "summary": summary,
            "internet_pct": internet_pct,
        }

    except Exception as e:
        log.error(f"Web search error: {e}")
        return {"found": False, "results": [], "summary": "", "internet_pct": 0}
