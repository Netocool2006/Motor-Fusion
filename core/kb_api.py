#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kb_api.py - Feature 14: REST API para acceso externo al KB
===========================================================
API HTTP ligera (Flask) que expone el KB y features de Hooks_IA.
Permite que dashboards, apps externas y otros servicios consulten.

Endpoints:
  GET  /api/health          - Status del sistema
  GET  /api/kb/search       - Busqueda en KB (?q=query&domain=X)
  GET  /api/kb/domains      - Lista de dominios
  GET  /api/kb/stats        - Estadisticas del KB
  POST /api/kb/add          - Agregar entry al KB
  GET  /api/graph           - Grafo de dominios
  GET  /api/graph/related   - Dominios relacionados (?domain=X)
  GET  /api/memory/tiers    - Estado de memory tiers
  GET  /api/memory/search   - Busqueda en memory tiers (?q=query)
  GET  /api/semantic/search - Busqueda semantica (?q=query)
  GET  /api/metrics         - Metricas consolidadas
  GET  /api/harvest         - Ultimo harvest de sesiones
  GET  /api/benchmark       - Ultimo benchmark
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR, KNOWLEDGE_DIR, PROJECT_ROOT

log = logging.getLogger("kb_api")

API_PORT = int(__import__("os").environ.get("HOOKS_IA_API_PORT", "7071"))
API_HOST = __import__("os").environ.get("HOOKS_IA_API_HOST", "127.0.0.1")

try:
    from flask import Flask, request, jsonify
    from flask_cors import CORS
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

if FLASK_AVAILABLE:
    app = Flask(__name__)
    CORS(app)

    # ==================== Health ====================

    @app.route("/api/health")
    def health():
        return jsonify({
            "status": "ok",
            "project": "Hooks_IA",
            "version": "2.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "features": _get_feature_status(),
        })

    # ==================== KB Search ====================

    @app.route("/api/kb/search")
    def kb_search():
        q = request.args.get("q", "")
        domain = request.args.get("domain", "")
        top_n = int(request.args.get("top_n", "5"))
        if not q:
            return jsonify({"error": "Missing 'q' parameter"}), 400
        try:
            from core.vector_kb import ask_kb
            result = ask_kb(q)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/kb/domains")
    def kb_domains():
        try:
            domains = []
            for f in sorted(KNOWLEDGE_DIR.glob("*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    count = 0
                    if isinstance(data, dict):
                        for section in data.values():
                            if isinstance(section, list):
                                count += len(section)
                    elif isinstance(data, list):
                        count = len(data)
                    domains.append({"name": f.stem, "entries": count})
                except Exception:
                    domains.append({"name": f.stem, "entries": 0})
            return jsonify({"domains": domains, "count": len(domains)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/kb/stats")
    def kb_stats():
        try:
            total_entries = 0
            domain_count = 0
            for f in KNOWLEDGE_DIR.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    domain_count += 1
                    if isinstance(data, dict):
                        for section in data.values():
                            if isinstance(section, list):
                                total_entries += len(section)
                    elif isinstance(data, list):
                        total_entries += len(data)
                except Exception:
                    continue
            return jsonify({
                "total_entries": total_entries,
                "domains": domain_count,
                "knowledge_dir": str(KNOWLEDGE_DIR),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/kb/add", methods=["POST"])
    def kb_add():
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        domain = data.get("domain", "general")
        key = data.get("key", "")
        value = data.get("value", data.get("solution", data.get("fact", "")))
        if not key or not value:
            return jsonify({"error": "Missing 'key' and 'value'"}), 400
        try:
            from core.knowledge_base import add_fact
            add_fact(domain=domain, key=key, fact=value, tags=data.get("tags", ["api"]))
            return jsonify({"status": "added", "domain": domain, "key": key[:100]})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ==================== Graph ====================

    @app.route("/api/graph")
    def graph_full():
        try:
            from core.domain_graph import export_graph_json
            return jsonify(export_graph_json())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/graph/related")
    def graph_related():
        domain = request.args.get("domain", "")
        if not domain:
            return jsonify({"error": "Missing 'domain' parameter"}), 400
        try:
            from core.domain_graph import find_related
            results = find_related(domain)
            return jsonify({"domain": domain, "related": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ==================== Memory Tiers ====================

    @app.route("/api/memory/tiers")
    def memory_tiers():
        try:
            from core.memory_tiers import get_tier_stats
            return jsonify(get_tier_stats())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/memory/search")
    def memory_search():
        q = request.args.get("q", "")
        if not q:
            return jsonify({"error": "Missing 'q' parameter"}), 400
        try:
            from core.memory_tiers import search_memory
            results = search_memory(q, top_n=10)
            return jsonify({"query": q, "results": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ==================== Semantic Search ====================

    @app.route("/api/semantic/search")
    def semantic_search_endpoint():
        q = request.args.get("q", "")
        domain = request.args.get("domain", "")
        if not q:
            return jsonify({"error": "Missing 'q' parameter"}), 400
        try:
            from core.semantic_search import semantic_search_kb
            results = semantic_search_kb(q, domain=domain, top_n=10)
            return jsonify({"query": q, "results": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ==================== Metrics ====================

    @app.route("/api/metrics")
    def metrics():
        try:
            all_metrics = {}

            # Dashboard metrics
            try:
                from core.dashboard_metrics import compute_all_metrics
                all_metrics["dashboard"] = compute_all_metrics()
            except Exception:
                all_metrics["dashboard"] = {}

            # Semantic stats
            try:
                from core.semantic_search import get_semantic_stats
                all_metrics["semantic"] = get_semantic_stats()
            except Exception:
                all_metrics["semantic"] = {}

            # Memory tier stats
            try:
                from core.memory_tiers import get_tier_stats
                all_metrics["memory_tiers"] = get_tier_stats()
            except Exception:
                all_metrics["memory_tiers"] = {}

            # Token budget
            try:
                token_file = DATA_DIR / "token_budget_metrics.json"
                if token_file.exists():
                    all_metrics["token_budget"] = json.loads(
                        token_file.read_text(encoding="utf-8")
                    )
            except Exception:
                pass

            # Async memory
            try:
                from core.async_memory import get_async_stats
                all_metrics["async_memory"] = get_async_stats()
            except Exception:
                pass

            # Graph
            try:
                from core.domain_graph import get_graph_stats
                all_metrics["graph"] = get_graph_stats()
            except Exception:
                pass

            return jsonify(all_metrics)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ==================== Harvest ====================

    @app.route("/api/harvest")
    def harvest():
        try:
            from core.session_harvest import get_last_harvest, get_harvest_stats
            last = get_last_harvest()
            stats = get_harvest_stats()
            return jsonify({"harvest": last, "stats": stats})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/harvest/run", methods=["POST"])
    def harvest_run():
        try:
            from core.session_harvest import harvest_sessions
            result = harvest_sessions()
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ==================== Benchmark ====================

    @app.route("/api/benchmark")
    def benchmark():
        try:
            from core.kb_benchmark import get_latest_benchmark
            return jsonify(get_latest_benchmark() or {"status": "no_benchmark_yet"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500


def _get_feature_status() -> dict:
    """Retorna estado de cada feature."""
    features = {}
    feature_checks = {
        "semantic_search": "core.semantic_search",
        "memory_tiers": "core.memory_tiers",
        "session_harvest": "core.session_harvest",
        "kb_api": "core.kb_api",
        "typed_graph": "core.typed_graph",
        "domain_graph": "core.domain_graph",
        "cloud_sync": "core.cloud_sync",
        "kb_benchmark": "core.kb_benchmark",
        "token_budget": "core.token_budget",
        "dashboard_metrics": "core.dashboard_metrics",
        "passive_capture": "core.passive_capture",
        "smart_file_routing": "core.smart_file_routing",
        "kb_versioning": "core.kb_versioning",
        "multi_agent": "core.multi_agent",
        "async_memory": "core.async_memory",
    }
    for name, module in feature_checks.items():
        try:
            __import__(module)
            features[name] = "ok"
        except Exception:
            features[name] = "not_available"
    return features


def run_api():
    """Inicia el servidor API."""
    if not FLASK_AVAILABLE:
        print("ERROR: Flask no instalado. Ejecutar: pip install flask flask-cors")
        return
    print(f"Hooks_IA API starting on http://{API_HOST}:{API_PORT}")
    print(f"Endpoints: /api/health, /api/kb/search, /api/metrics, etc.")
    app.run(host=API_HOST, port=API_PORT, debug=False)


# CLI
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"

    if cmd == "run":
        run_api()
    elif cmd == "test":
        print("Testing API imports...")
        status = _get_feature_status()
        for name, st in status.items():
            icon = "OK" if st == "ok" else "MISSING"
            print(f"  [{icon}] {name}")
        print(f"\nFlask available: {FLASK_AVAILABLE}")
        print(f"API would run on: http://{API_HOST}:{API_PORT}")
    else:
        print("Usage: kb_api.py [run|test]")
