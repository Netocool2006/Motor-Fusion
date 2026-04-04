#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
smart_file_routing.py - Feature 7: Smart File Routing
=====================================================
El KB aprende qué archivos se tocan para qué tipo de tarea.
Cuando el usuario pide algo, sugiere archivos relevantes.
"""

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR, PROJECT_ROOT

log = logging.getLogger("smart_file_routing")

ROUTING_DB_FILE = DATA_DIR / "file_routing.json"


def _load_routing() -> dict:
    if ROUTING_DB_FILE.exists():
        try:
            return json.loads(ROUTING_DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"routes": {}, "keywords": {}}


def _save_routing(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ROUTING_DB_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def learn_route(task_keywords: list[str], files_touched: list[str]):
    """
    Aprende que para una tarea con estas keywords, se tocan estos archivos.
    Llamar desde post-hook tras completar una tarea.
    """
    data = _load_routing()

    for keyword in task_keywords:
        kw = keyword.lower().strip()
        if not kw or len(kw) < 3:
            continue

        if kw not in data["routes"]:
            data["routes"][kw] = {}

        for f in files_touched:
            # Normalizar path relativo al proyecto
            try:
                rel = str(Path(f).relative_to(PROJECT_ROOT)).replace("\\", "/")
            except (ValueError, TypeError):
                rel = f
            data["routes"][kw][rel] = data["routes"][kw].get(rel, 0) + 1

        # Índice inverso: archivo -> keywords
        for f in files_touched:
            try:
                rel = str(Path(f).relative_to(PROJECT_ROOT)).replace("\\", "/")
            except (ValueError, TypeError):
                rel = f
            if rel not in data["keywords"]:
                data["keywords"][rel] = {}
            data["keywords"][rel][kw] = data["keywords"][rel].get(kw, 0) + 1

    _save_routing(data)


def suggest_files(query: str, top_n: int = 8) -> list[dict]:
    """
    Dada una query del usuario, sugiere archivos relevantes.
    Retorna [{file, score, keywords_matched}].
    """
    data = _load_routing()
    routes = data.get("routes", {})

    if not routes:
        return []

    # Extraer keywords de la query
    words = set(query.lower().split())
    # También buscar sub-strings más largos
    query_lower = query.lower()

    file_scores = defaultdict(lambda: {"score": 0, "keywords": []})

    for keyword, files in routes.items():
        # Match: keyword está en la query
        if keyword in query_lower or keyword in words:
            for filepath, count in files.items():
                file_scores[filepath]["score"] += count
                file_scores[filepath]["keywords"].append(keyword)

    if not file_scores:
        return []

    results = [
        {"file": f, "score": info["score"], "keywords_matched": list(set(info["keywords"]))}
        for f, info in file_scores.items()
    ]

    return sorted(results, key=lambda x: -x["score"])[:top_n]


def get_routing_stats() -> dict:
    """Estadísticas para dashboard."""
    data = _load_routing()
    return {
        "total_keywords": len(data.get("routes", {})),
        "total_files_tracked": len(data.get("keywords", {})),
        "top_keywords": sorted(
            [(k, sum(v.values())) for k, v in data.get("routes", {}).items()],
            key=lambda x: -x[1],
        )[:10],
    }


# CLI
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        results = suggest_files(query)
        if results:
            print(f"\nArchivos sugeridos para '{query}':")
            for r in results:
                print(f"  {r['file']:50s} score={r['score']:3d} keywords={r['keywords_matched']}")
        else:
            print(f"Sin sugerencias para '{query}' (el routing aún no tiene datos)")
    else:
        stats = get_routing_stats()
        print(f"Keywords: {stats['total_keywords']}, Files tracked: {stats['total_files_tracked']}")
