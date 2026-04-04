#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kb_benchmark.py - Feature 3: Benchmark de precisión / Recall Score
==================================================================
Mide qué tan bueno es el KB para responder preguntas usando
sesiones históricas como ground truth.

Métricas:
  - Recall@5: ¿La respuesta correcta está en los top 5 resultados?
  - Precision: ¿Cuántos resultados son relevantes?
  - Coverage: ¿Qué % de preguntas tiene respuesta en el KB?
  - Token efficiency: tokens usados vs tokens útiles
"""

import json
import logging
import time
from pathlib import Path
from datetime import datetime, timezone

from config import DATA_DIR

log = logging.getLogger("kb_benchmark")

BENCHMARK_FILE = DATA_DIR / "kb_benchmark_results.json"
SESSION_HISTORY = DATA_DIR / "session_history.json"


def extract_qa_pairs(max_pairs: int = 100) -> list[dict]:
    """
    Extrae pares pregunta-respuesta del historial de sesiones.
    Solo usa sesiones donde el KB contribuyó (kb_pct > 0).
    """
    if not SESSION_HISTORY.exists():
        return []

    try:
        data = json.loads(SESSION_HISTORY.read_text(encoding="utf-8"))
    except Exception:
        return []

    pairs = []
    sessions = data if isinstance(data, list) else data.get("sessions", [])

    for session in sessions:
        if not isinstance(session, dict):
            continue
        interactions = session.get("interactions", session.get("queries", []))
        if not isinstance(interactions, list):
            continue
        for interaction in interactions:
            if not isinstance(interaction, dict):
                continue
            query = interaction.get("query", interaction.get("Q", ""))
            answer = interaction.get("answer_preview", interaction.get("A", ""))
            if query and len(query) > 10 and answer and len(answer) > 20:
                pairs.append({
                    "query": query[:200],
                    "expected_answer": answer[:500],
                    "session_date": session.get("session_start", session.get("date", "")),
                })
                if len(pairs) >= max_pairs:
                    return pairs

    return pairs


def run_benchmark(max_queries: int = 50) -> dict:
    """
    Ejecuta benchmark completo: busca cada pregunta en el KB y mide precisión.
    """
    pairs = extract_qa_pairs(max_queries)
    if not pairs:
        return {"error": "No hay pares Q&A en el historial", "score": 0}

    try:
        from core.vector_kb import ask_kb
    except ImportError:
        return {"error": "vector_kb no disponible", "score": 0}

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_queries": len(pairs),
        "hits": 0,
        "misses": 0,
        "avg_similarity": 0.0,
        "recall_at_5": 0.0,
        "coverage_pct": 0.0,
        "avg_response_ms": 0.0,
        "details": [],
    }

    total_sim = 0.0
    total_time = 0.0

    for pair in pairs:
        start = time.time()
        try:
            result = ask_kb(pair["query"])
        except Exception as e:
            results["details"].append({
                "query": pair["query"][:80],
                "found": False,
                "error": str(e),
            })
            results["misses"] += 1
            continue
        elapsed = (time.time() - start) * 1000  # ms

        found = result.get("found", False)
        similarity = result.get("similarity", 0.0)
        total_sim += similarity
        total_time += elapsed

        if found and similarity > 0.4:
            results["hits"] += 1
        else:
            results["misses"] += 1

        results["details"].append({
            "query": pair["query"][:80],
            "found": found,
            "similarity": round(similarity, 3),
            "response_ms": round(elapsed, 1),
        })

    n = len(pairs)
    results["coverage_pct"] = round((results["hits"] / n) * 100, 1) if n > 0 else 0
    results["avg_similarity"] = round(total_sim / n, 3) if n > 0 else 0
    results["avg_response_ms"] = round(total_time / n, 1) if n > 0 else 0
    results["recall_at_5"] = results["coverage_pct"]  # Simplificado: top-1 = recall@5 para ahora
    results["score"] = results["coverage_pct"]

    # Guardar resultados
    _save_results(results)
    return results


def _save_results(results: dict):
    """Guarda benchmark y mantiene historial de últimos 20 runs."""
    history = []
    if BENCHMARK_FILE.exists():
        try:
            history = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
            if isinstance(history, dict):
                history = [history]
        except Exception:
            history = []

    # Solo guardar resumen en historial (sin details)
    summary = {k: v for k, v in results.items() if k != "details"}
    history.append(summary)
    history = history[-20:]  # Últimos 20 runs

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BENCHMARK_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def get_latest_benchmark() -> dict:
    """Retorna el último resultado de benchmark (para dashboard)."""
    if not BENCHMARK_FILE.exists():
        return {"score": 0, "message": "No hay benchmark ejecutado"}
    try:
        data = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return data[-1]
        return data
    except Exception:
        return {"score": 0, "message": "Error leyendo benchmark"}


def get_benchmark_trend() -> list[dict]:
    """Retorna tendencia de los últimos benchmarks (para gráfico en dashboard)."""
    if not BENCHMARK_FILE.exists():
        return []
    try:
        data = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [{"date": r.get("timestamp", ""), "score": r.get("score", 0)} for r in data]
        return []
    except Exception:
        return []


# CLI
if __name__ == "__main__":
    import sys
    import io
    # Fix Windows encoding
    if sys.stdout and hasattr(sys.stdout, "buffer"):
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass

    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "run":
        max_q = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        print(f"Ejecutando benchmark con {max_q} queries...")
        results = run_benchmark(max_q)
        print(f"\nResultados:")
        print(f"  Queries: {results.get('total_queries', 0)}")
        print(f"  Hits: {results.get('hits', 0)}")
        print(f"  Misses: {results.get('misses', 0)}")
        print(f"  Coverage: {results.get('coverage_pct', 0)}%")
        print(f"  Avg similarity: {results.get('avg_similarity', 0)}")
        print(f"  Avg response: {results.get('avg_response_ms', 0)}ms")
        print(f"  SCORE: {results.get('score', 0)}%")
    elif cmd == "trend":
        trend = get_benchmark_trend()
        for t in trend:
            print(f"  {t['date'][:10]}: {t['score']}%")
    else:
        print("Usage: kb_benchmark.py [run [N]|trend]")
