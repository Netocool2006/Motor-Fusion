#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kb_cache.py - Cache semántico para respuestas de NotebookLM
============================================================
Guarda respuestas de NotebookLM localmente para no gastar chats
en preguntas que ya se hicieron (o similares).

Usa TF-IDF + cosine similarity para encontrar queries similares.
Si la similitud > umbral, retorna el cache sin llamar a NotebookLM.
"""

import json
import logging
import time
from pathlib import Path
from datetime import datetime

log = logging.getLogger("kb_cache")

_CACHE_FILE = Path(__file__).resolve().parent / "kb_cache.json"
_SIMILARITY_THRESHOLD = 0.40  # 0-1, queries con >40% similitud usan cache
_CACHE_MAX_AGE_HOURS = 168  # 7 días - después se invalida


def _load_cache():
    """Carga el cache desde disco."""
    if not _CACHE_FILE.exists():
        return []
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_cache(cache):
    """Guarda el cache a disco."""
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Error saving cache: {e}")


def _normalize_text(text):
    """Normaliza texto: quita acentos, lowercase, limpia."""
    import unicodedata
    # NFD decompose → quitar combining chars (acentos)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.lower().strip()


def _compute_similarity(query, cached_query):
    """Calcula similitud entre dos queries usando TF-IDF + cosine + word overlap."""
    q_norm = _normalize_text(query)
    c_norm = _normalize_text(cached_query)

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=1,
            stop_words=None,
        )

        tfidf = vectorizer.fit_transform([q_norm, c_norm])
        tfidf_sim = float(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0])

        # Complement with word overlap (helps with short vs long queries)
        words_q = set(q_norm.split())
        words_c = set(c_norm.split())
        if words_q and words_c:
            overlap = len(words_q & words_c)
            overlap_sim = overlap / min(len(words_q), len(words_c))
        else:
            overlap_sim = 0.0

        # Weighted average: 50% TF-IDF + 50% word overlap
        # Word overlap helps when queries share key terms but differ in structure
        return 0.5 * tfidf_sim + 0.5 * overlap_sim

    except ImportError:
        words_q = set(q_norm.split())
        words_c = set(c_norm.split())
        if not words_q or not words_c:
            return 0.0
        overlap = len(words_q & words_c)
        return overlap / max(len(words_q), len(words_c))


def search_cache(query):
    """
    Busca en cache una respuesta para una query similar.

    Returns:
        dict con:
          - found: bool
          - answer: str (respuesta cacheada)
          - cached_query: str (la query original que generó el cache)
          - similarity: float (0-1)
          - cache_age_hours: float
        O None si no hay match
    """
    cache = _load_cache()
    if not cache:
        return None

    now = time.time()
    best_match = None
    best_sim = 0.0

    for entry in cache:
        # Skip expired entries
        age_hours = (now - entry.get("timestamp", 0)) / 3600
        if age_hours > _CACHE_MAX_AGE_HOURS:
            continue

        sim = _compute_similarity(query, entry["query"])

        if sim > best_sim and sim >= _SIMILARITY_THRESHOLD:
            best_sim = sim
            best_match = entry
            best_match["_age_hours"] = age_hours

    if best_match:
        log.info(
            f"Cache HIT: sim={best_sim:.2f}, "
            f"cached_query='{best_match['query'][:50]}', "
            f"age={best_match['_age_hours']:.1f}h"
        )
        return {
            "found": True,
            "answer": best_match["answer"],
            "cached_query": best_match["query"],
            "similarity": best_sim,
            "cache_age_hours": best_match["_age_hours"],
        }

    return None


def save_to_cache(query, answer, kb_pct=0):
    """
    Guarda una respuesta en el cache.

    Args:
        query: La pregunta original
        answer: Respuesta de NotebookLM
        kb_pct: Porcentaje de KB que cubrió
    """
    if not answer or len(answer) < 20:
        return

    cache = _load_cache()

    # Check if very similar query already exists
    for entry in cache:
        sim = _compute_similarity(query, entry["query"])
        if sim > 0.70:
            # Update existing entry instead of duplicating
            entry["answer"] = answer
            entry["kb_pct"] = kb_pct
            entry["timestamp"] = time.time()
            entry["updated"] = datetime.now().isoformat()
            _save_cache(cache)
            log.info(f"Cache UPDATED: '{query[:50]}' (sim={sim:.2f} with existing)")
            return

    # Add new entry
    cache.append({
        "query": query,
        "answer": answer,
        "kb_pct": kb_pct,
        "timestamp": time.time(),
        "created": datetime.now().isoformat(),
    })

    # Prune old entries (keep max 500)
    if len(cache) > 500:
        cache.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        cache = cache[:500]

    _save_cache(cache)
    log.info(f"Cache SAVED: '{query[:50]}' (total={len(cache)})")


def get_cache_stats():
    """Retorna estadísticas del cache."""
    cache = _load_cache()
    now = time.time()
    active = [e for e in cache if (now - e.get("timestamp", 0)) / 3600 < _CACHE_MAX_AGE_HOURS]
    return {
        "total_entries": len(cache),
        "active_entries": len(active),
        "expired_entries": len(cache) - len(active),
    }
