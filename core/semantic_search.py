#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
semantic_search.py - Feature 11: Busqueda Vectorial con Embeddings Reales
=========================================================================
Usa sentence-transformers para generar embeddings locales y buscar
por similitud semantica real. "error de conexion" matchea "fallo de red".

Modelo: all-MiniLM-L6-v2 (rapido, 384 dims, 80MB)
Fallback: TF-IDF si sentence-transformers no esta instalado.
"""

import json
import logging
import time
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

from config import DATA_DIR, KNOWLEDGE_DIR

log = logging.getLogger("semantic_search")

EMBEDDINGS_CACHE_FILE = DATA_DIR / "embeddings_cache.json"
SEMANTIC_METRICS_FILE = DATA_DIR / "semantic_metrics.json"
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
MAX_CACHE_SIZE = 10000

# Lazy-load model
_model = None
_use_tfidf_fallback = False


def _load_model():
    """Carga sentence-transformers model (lazy, solo una vez)."""
    global _model, _use_tfidf_fallback
    if _model is not None:
        return _model
    try:
        import os
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from sentence_transformers import SentenceTransformer
        try:
            _model = SentenceTransformer(MODEL_NAME)
        except OSError:
            os.environ.pop("HF_HUB_OFFLINE", None)
            os.environ.pop("TRANSFORMERS_OFFLINE", None)
            _model = SentenceTransformer(MODEL_NAME)
        log.info(f"Loaded sentence-transformers model: {MODEL_NAME}")
        return _model
    except ImportError:
        log.warning("sentence-transformers not installed, using TF-IDF fallback")
        _use_tfidf_fallback = True
        return None
    except Exception as e:
        log.error(f"Error loading model: {e}")
        _use_tfidf_fallback = True
        return None


def encode_text(text: str) -> list[float]:
    """Genera embedding para un texto."""
    model = _load_model()
    if model is not None:
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()
    else:
        return _tfidf_encode(text)


def encode_batch(texts: list[str]) -> list[list[float]]:
    """Genera embeddings para un batch de textos."""
    model = _load_model()
    if model is not None:
        embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32)
        return embeddings.tolist()
    else:
        return [_tfidf_encode(t) for t in texts]


def _tfidf_encode(text: str) -> list[float]:
    """Fallback: pseudo-embedding basado en hash de palabras."""
    import hashlib
    words = text.lower().split()
    vec = [0.0] * EMBEDDING_DIM
    for w in words:
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        for i in range(EMBEDDING_DIM):
            vec[i] += ((h >> (i % 64)) & 1) * 2 - 1
    # Normalize
    norm = sum(v * v for v in vec) ** 0.5
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similitud coseno entre dos vectores."""
    a_arr = np.array(a, dtype=np.float32)
    b_arr = np.array(b, dtype=np.float32)
    dot = np.dot(a_arr, b_arr)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


class EmbeddingsCache:
    """Cache persistente de embeddings pre-computados."""

    def __init__(self):
        self._cache = {}
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        if EMBEDDINGS_CACHE_FILE.exists():
            try:
                data = json.loads(EMBEDDINGS_CACHE_FILE.read_text(encoding="utf-8"))
                self._cache = data.get("embeddings", {})
            except Exception:
                self._cache = {}
        self._loaded = True

    def get(self, key: str) -> list[float] | None:
        self._load()
        return self._cache.get(key)

    def put(self, key: str, embedding: list[float]):
        self._load()
        self._cache[key] = embedding
        if len(self._cache) > MAX_CACHE_SIZE:
            # Eliminar los mas viejos (FIFO por orden de insercion)
            keys = list(self._cache.keys())
            for k in keys[:len(keys) - MAX_CACHE_SIZE]:
                del self._cache[k]

    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "embeddings": self._cache,
            "count": len(self._cache),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        EMBEDDINGS_CACHE_FILE.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    def size(self) -> int:
        self._load()
        return len(self._cache)


_cache = EmbeddingsCache()


def semantic_search(query: str, entries: list[dict], top_n: int = 5,
                    threshold: float = 0.3) -> list[dict]:
    """
    Busqueda semantica sobre una lista de entries del KB.
    Cada entry debe tener al menos 'key' y opcionalmente 'solution'/'fact'.

    Returns: lista de {entry, similarity, rank}
    """
    start = time.time()

    # Encode query
    query_emb = _cache.get(f"q:{query}")
    if query_emb is None:
        query_emb = encode_text(query)
        _cache.put(f"q:{query}", query_emb)

    results = []
    texts_to_encode = []
    entry_indices = []

    for i, entry in enumerate(entries):
        sol = entry.get("solution", entry.get("fact", ""))
        if isinstance(sol, dict):
            sol = sol.get("notes", sol.get("rule", str(sol)))
        text = entry.get("key", "") + " " + str(sol)
        cache_key = f"e:{text[:200]}"
        cached = _cache.get(cache_key)
        if cached is not None:
            sim = cosine_similarity(query_emb, cached)
            if sim >= threshold:
                results.append({"entry": entry, "similarity": round(sim, 4), "rank": 0})
        else:
            texts_to_encode.append(text)
            entry_indices.append(i)

    # Batch encode los que no estaban en cache
    if texts_to_encode:
        embeddings = encode_batch(texts_to_encode)
        for idx, emb in zip(entry_indices, embeddings):
            entry = entries[idx]
            sol = entry.get("solution", entry.get("fact", ""))
            if isinstance(sol, dict):
                sol = sol.get("notes", sol.get("rule", str(sol)))
            text = entry.get("key", "") + " " + str(sol)
            _cache.put(f"e:{text[:200]}", emb)
            sim = cosine_similarity(query_emb, emb)
            if sim >= threshold:
                results.append({"entry": entry, "similarity": round(sim, 4), "rank": 0})

    # Sort by similarity
    results.sort(key=lambda x: x["similarity"], reverse=True)
    for i, r in enumerate(results[:top_n]):
        r["rank"] = i + 1

    elapsed_ms = (time.time() - start) * 1000

    # Save cache periodically
    if len(texts_to_encode) > 0:
        try:
            _cache.save()
        except Exception:
            pass

    # Metrics
    _record_metrics(query, len(results), elapsed_ms)

    return results[:top_n]


def semantic_search_kb(query: str, domain: str = "", top_n: int = 5) -> list[dict]:
    """
    Busqueda semantica directa sobre el KB JSON.
    Si domain esta vacio, busca en todos los dominios.
    """
    entries = _load_kb_entries(domain)
    return semantic_search(query, entries, top_n=top_n)


def _load_kb_entries(domain: str = "") -> list[dict]:
    """Carga entries del KB desde archivos JSON."""
    entries = []
    if domain:
        kb_file = KNOWLEDGE_DIR / f"{domain}.json"
        if kb_file.exists():
            try:
                data = json.loads(kb_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for section in data.values():
                        if isinstance(section, list):
                            entries.extend(section)
                elif isinstance(data, list):
                    entries.extend(data)
            except Exception:
                pass
    else:
        # Cargar top dominios (no todos, seria muy lento)
        for kb_file in sorted(KNOWLEDGE_DIR.glob("*.json"))[:20]:
            try:
                data = json.loads(kb_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for section in data.values():
                        if isinstance(section, list):
                            entries.extend(section[:50])  # Limit per domain
                elif isinstance(data, list):
                    entries.extend(data[:50])
            except Exception:
                continue
    return entries


def _record_metrics(query: str, num_results: int, elapsed_ms: float):
    """Registra metricas de busqueda semantica."""
    try:
        metrics = {}
        if SEMANTIC_METRICS_FILE.exists():
            metrics = json.loads(SEMANTIC_METRICS_FILE.read_text(encoding="utf-8"))

        metrics["total_searches"] = metrics.get("total_searches", 0) + 1
        metrics["total_results"] = metrics.get("total_results", 0) + num_results

        prev_avg = metrics.get("avg_latency_ms", 0)
        n = metrics["total_searches"]
        metrics["avg_latency_ms"] = round(prev_avg + (elapsed_ms - prev_avg) / n, 2)
        metrics["last_search"] = datetime.now(timezone.utc).isoformat()
        metrics["cache_size"] = _cache.size()
        metrics["using_transformers"] = not _use_tfidf_fallback

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SEMANTIC_METRICS_FILE.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def get_semantic_stats() -> dict:
    """Estadisticas para dashboard."""
    if SEMANTIC_METRICS_FILE.exists():
        try:
            return json.loads(SEMANTIC_METRICS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"total_searches": 0, "using_transformers": False}


# CLI
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"

    if cmd == "test":
        print("Testing semantic search...")
        q = sys.argv[2] if len(sys.argv) > 2 else "error de conexion SAP"
        results = semantic_search_kb(q, top_n=5)
        print(f"\nQuery: '{q}'")
        print(f"Results: {len(results)}")
        for r in results:
            print(f"  [{r['rank']}] sim={r['similarity']:.4f} | {r['entry'].get('key', '')[:80]}")

    elif cmd == "stats":
        stats = get_semantic_stats()
        print(f"Searches: {stats.get('total_searches', 0)}")
        print(f"Cache: {stats.get('cache_size', 0)} entries")
        print(f"Avg latency: {stats.get('avg_latency_ms', 0)}ms")
        print(f"Using transformers: {stats.get('using_transformers', False)}")

    elif cmd == "cache-build":
        print("Building embeddings cache for top KB domains...")
        total = 0
        for kb_file in sorted(KNOWLEDGE_DIR.glob("*.json"))[:30]:
            entries = []
            try:
                data = json.loads(kb_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for section in data.values():
                        if isinstance(section, list):
                            entries.extend(section[:100])
                elif isinstance(data, list):
                    entries.extend(data[:100])
            except Exception:
                continue
            if entries:
                texts = [e.get("key", "") + " " + e.get("solution", e.get("fact", ""))
                         for e in entries]
                embeddings = encode_batch(texts)
                for text, emb in zip(texts, embeddings):
                    _cache.put(f"e:{text[:200]}", emb)
                total += len(entries)
                print(f"  {kb_file.stem}: {len(entries)} entries cached")
        _cache.save()
        print(f"\nTotal cached: {total} entries")
    else:
        print("Usage: semantic_search.py [test|stats|cache-build] [query]")
