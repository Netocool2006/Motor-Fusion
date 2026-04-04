#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
dashboard_metrics.py - Feature 5: Métricas de valor en Dashboard
================================================================
Agrega métricas de ROI al dashboard:
  - Hit rate del KB
  - Dominios más consultados
  - Patrones más reutilizados
  - Errores recurrentes sin resolver
  - Tendencia temporal
"""

import json
import logging
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import DATA_DIR, KNOWLEDGE_DIR

log = logging.getLogger("dashboard_metrics")

METRICS_CACHE_FILE = DATA_DIR / "dashboard_metrics_cache.json"
EXECUTION_LOG = DATA_DIR / "execution_log.json"
SESSION_HISTORY = DATA_DIR / "session_history.json"


def compute_kb_hit_rate() -> dict:
    """Calcula el % de queries donde el KB tuvo respuesta útil."""
    if not EXECUTION_LOG.exists():
        return {"hit_rate": 0, "total_queries": 0, "hits": 0}

    try:
        data = json.loads(EXECUTION_LOG.read_text(encoding="utf-8"))
        entries = data if isinstance(data, list) else []
    except Exception:
        return {"hit_rate": 0, "total_queries": 0, "hits": 0}

    total = 0
    hits = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("event") in ("query", "search", "kb_search"):
            total += 1
            if entry.get("found") or entry.get("kb_pct", 0) > 20:
                hits += 1

    return {
        "hit_rate": round((hits / total) * 100, 1) if total > 0 else 0,
        "total_queries": total,
        "hits": hits,
    }


def compute_top_domains(limit: int = 15) -> list[dict]:
    """Top dominios más consultados."""
    domain_counts = Counter()

    # Contar desde execution_log
    if EXECUTION_LOG.exists():
        try:
            data = json.loads(EXECUTION_LOG.read_text(encoding="utf-8"))
            entries = data if isinstance(data, list) else []
            for entry in entries:
                if isinstance(entry, dict) and "domain" in entry:
                    domain_counts[entry["domain"]] += 1
        except Exception:
            pass

    # Contar desde session_history
    if SESSION_HISTORY.exists():
        try:
            data = json.loads(SESSION_HISTORY.read_text(encoding="utf-8"))
            sessions = data if isinstance(data, list) else data.get("sessions", [])
            for session in sessions:
                if isinstance(session, dict):
                    for d in session.get("domains_used", []):
                        domain_counts[d] += 1
        except Exception:
            pass

    # Si no hay datos de logs, contar por tamaño de KB
    if not domain_counts:
        for domain_dir in KNOWLEDGE_DIR.iterdir():
            if domain_dir.is_dir():
                patterns_file = domain_dir / "patterns.json"
                if patterns_file.exists():
                    try:
                        data = json.loads(patterns_file.read_text(encoding="utf-8"))
                        entries = data.get("entries", {})
                        domain_counts[domain_dir.name] = len(entries)
                    except Exception:
                        pass

    return [{"domain": d, "count": c} for d, c in domain_counts.most_common(limit)]


def compute_top_patterns(limit: int = 10) -> list[dict]:
    """Patrones más reutilizados (por success_rate * reuses)."""
    top = []
    for domain_dir in KNOWLEDGE_DIR.iterdir():
        if not domain_dir.is_dir():
            continue
        patterns_file = domain_dir / "patterns.json"
        if not patterns_file.exists():
            continue
        try:
            data = json.loads(patterns_file.read_text(encoding="utf-8"))
            for eid, entry in data.get("entries", {}).items():
                if not isinstance(entry, dict):
                    continue
                reuses = entry.get("reuses", entry.get("lookups", 0))
                success = entry.get("success_rate", 0.5)
                score = reuses * success
                if reuses > 0:
                    top.append({
                        "domain": domain_dir.name,
                        "key": entry.get("key", eid)[:60],
                        "reuses": reuses,
                        "success_rate": round(success, 2),
                        "score": round(score, 2),
                    })
        except Exception:
            continue

    return sorted(top, key=lambda x: x["score"], reverse=True)[:limit]


def compute_unresolved_errors(limit: int = 10) -> list[dict]:
    """Errores recurrentes que no se han resuelto."""
    error_counts = Counter()
    error_details = {}

    if EXECUTION_LOG.exists():
        try:
            data = json.loads(EXECUTION_LOG.read_text(encoding="utf-8"))
            entries = data if isinstance(data, list) else []
            for entry in entries:
                if isinstance(entry, dict) and entry.get("event") == "error":
                    error_key = entry.get("error_type", entry.get("message", "unknown"))[:80]
                    error_counts[error_key] += 1
                    if error_key not in error_details:
                        error_details[error_key] = {
                            "first_seen": entry.get("timestamp", ""),
                            "last_seen": entry.get("timestamp", ""),
                        }
                    else:
                        error_details[error_key]["last_seen"] = entry.get("timestamp", "")
        except Exception:
            pass

    return [
        {
            "error": err,
            "count": cnt,
            **error_details.get(err, {}),
        }
        for err, cnt in error_counts.most_common(limit)
    ]


def compute_temporal_trend(days: int = 30) -> list[dict]:
    """Tendencia: KB creciendo o estancado? Entries por día."""
    if not EXECUTION_LOG.exists():
        return []

    daily = Counter()
    try:
        data = json.loads(EXECUTION_LOG.read_text(encoding="utf-8"))
        entries = data if isinstance(data, list) else []
        for entry in entries:
            if isinstance(entry, dict) and "timestamp" in entry:
                ts = entry["timestamp"][:10]  # YYYY-MM-DD
                if entry.get("event") in ("pattern_added", "fact_added", "domain_created"):
                    daily[ts] += 1
    except Exception:
        pass

    return sorted([{"date": d, "new_entries": c} for d, c in daily.items()])[-days:]


def compute_all_metrics() -> dict:
    """Calcula todas las métricas y las cachea."""
    metrics = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kb_hit_rate": compute_kb_hit_rate(),
        "top_domains": compute_top_domains(),
        "top_patterns": compute_top_patterns(),
        "unresolved_errors": compute_unresolved_errors(),
        "temporal_trend": compute_temporal_trend(),
    }

    # Agregar benchmark si existe
    try:
        from core.kb_benchmark import get_latest_benchmark
        metrics["benchmark"] = get_latest_benchmark()
    except Exception:
        metrics["benchmark"] = {"score": 0, "message": "Not available"}

    # Agregar graph stats si existe
    try:
        from core.domain_graph import get_graph_stats
        metrics["graph_stats"] = get_graph_stats()
    except Exception:
        metrics["graph_stats"] = {}

    # Agregar token stats si existe
    try:
        from core.token_budget import get_token_stats
        metrics["token_stats"] = get_token_stats()
    except Exception:
        metrics["token_stats"] = {}

    # Agregar sync status si existe
    try:
        from core.cloud_sync import get_sync_status
        metrics["sync_status"] = get_sync_status()
    except Exception:
        metrics["sync_status"] = {}

    # Cachear
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_CACHE_FILE.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return metrics


def get_cached_metrics() -> dict:
    """Retorna métricas cacheadas (rápido para dashboard)."""
    if METRICS_CACHE_FILE.exists():
        try:
            return json.loads(METRICS_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return compute_all_metrics()


# CLI
if __name__ == "__main__":
    import sys
    import io
    if sys.stdout and hasattr(sys.stdout, "buffer"):
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass

    metrics = compute_all_metrics()
    print(f"\n{'='*60}")
    print("DASHBOARD METRICS")
    print(f"{'='*60}")
    hr = metrics["kb_hit_rate"]
    print(f"\nKB Hit Rate: {hr['hit_rate']}% ({hr['hits']}/{hr['total_queries']} queries)")
    print(f"\nTop Dominios:")
    for d in metrics["top_domains"][:10]:
        print(f"  {d['domain']:30s} {d['count']} queries")
    print(f"\nTop Patrones:")
    for p in metrics["top_patterns"][:5]:
        print(f"  [{p['domain']}] {p['key'][:40]} reuses={p['reuses']} score={p['score']}")
    bm = metrics.get("benchmark", {})
    print(f"\nBenchmark Score: {bm.get('score', 'N/A')}%")
    gs = metrics.get("graph_stats", {})
    print(f"Graph: {gs.get('nodes', 0)} nodos, {gs.get('edges', 0)} edges")
