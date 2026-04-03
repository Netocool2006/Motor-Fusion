#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Motor_IA Dashboard v2 - Monitoreo del sistema RAG completo"""
import sys
import json
import os
import subprocess
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime

_PROJECT = Path(__file__).resolve().parent.parent
HTML_FILE = Path(__file__).parent / "index.html"


def _read_log_tail(filepath, n=30):
    """Lee las últimas n líneas de un log."""
    try:
        if not filepath.exists():
            return []
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-n:]
        return [l.strip() for l in lines if l.strip()]
    except Exception:
        return []


def _check_chromadb():
    """Verifica estado de ChromaDB."""
    try:
        sys.path.insert(0, str(_PROJECT))
        from core.vector_kb import get_stats
        stats = get_stats()
        return {
            "status": "OK" if stats.get("total", 0) > 0 else "EMPTY",
            "total_docs": stats.get("total", 0),
            "facts": stats.get("facts", 0),
            "patterns": stats.get("patterns", 0),
            "learned": stats.get("learned", 0),
            "sessions": stats.get("sessions", 0),
        }
    except Exception as e:
        return {"status": "ERROR", "error": str(e), "total_docs": 0}


def _check_kb_cache():
    """Verifica estado del cache TF-IDF."""
    cache_file = _PROJECT / "core" / "kb_cache.json"
    try:
        if not cache_file.exists():
            return {"status": "EMPTY", "entries": 0}
        with open(cache_file, encoding="utf-8") as f:
            data = json.load(f)
        active = [e for e in data if (time.time() - e.get("timestamp", 0)) / 3600 < 168]
        return {"status": "OK", "entries": len(data), "active": len(active)}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def _check_knowledge_local():
    """Verifica knowledge/ local (backup)."""
    kb_path = _PROJECT / "knowledge"
    if not kb_path.exists():
        return {"status": "MISSING", "domains": 0, "size_mb": 0}
    domains = [d for d in kb_path.iterdir() if d.is_dir()]
    total_size = sum(f.stat().st_size for d in domains for f in d.rglob("*") if f.is_file())
    return {
        "status": "OK",
        "domains": len(domains),
        "size_mb": round(total_size / 1024 / 1024, 1),
        "domain_list": sorted(d.name for d in domains),
    }


def _check_hooks():
    """Verifica que los hooks estén registrados en settings.json."""
    # Find settings.json
    settings_paths = [
        Path.home() / "AppData" / "Local" / "ClaudeCode" / ".claude" / "settings.json",
        Path.home() / ".claude" / "settings.json",
    ]
    for sp in settings_paths:
        if sp.exists():
            try:
                with open(sp, encoding="utf-8") as f:
                    settings = json.load(f)
                hooks = settings.get("hooks", {})
                pre = hooks.get("UserPromptSubmit", [])
                post = hooks.get("Stop", [])
                pre_ok = any("motor_ia_hook" in str(h) for h in pre) if pre else False
                post_ok = any("motor_ia_post_hook" in str(h) for h in post) if post else False
                return {
                    "status": "OK" if pre_ok and post_ok else "PARTIAL",
                    "pre_hook": "REGISTERED" if pre_ok else "MISSING",
                    "post_hook": "REGISTERED" if post_ok else "MISSING",
                    "settings_path": str(sp),
                }
            except Exception as e:
                return {"status": "ERROR", "error": str(e)}
    return {"status": "NOT_FOUND", "pre_hook": "UNKNOWN", "post_hook": "UNKNOWN"}


def _parse_motor_ia_log():
    """Parsea el log principal para métricas."""
    log_file = _PROJECT / "core" / "motor_ia_hook.log"
    lines = _read_log_tail(log_file, 100)

    queries_today = 0
    cache_hits = 0
    vector_hits = 0
    internet_searches = 0
    auto_saves = 0
    errors = 0
    last_query = ""
    last_result = ""
    today = datetime.now().strftime("%Y-%m-%d")

    recent_activity = []

    for line in lines:
        if today not in line:
            continue
        if "QUERY:" in line:
            queries_today += 1
            last_query = line.split("QUERY:")[1].strip()[:80]
        if "CACHE HIT" in line:
            cache_hits += 1
        if "source=vector_kb" in line:
            vector_hits += 1
        if "FORCING web search" in line or "Web search:" in line:
            internet_searches += 1
        if "AUTO-SAVED" in line:
            auto_saves += 1
        if "[ERROR]" in line:
            errors += 1
        if "RESULT:" in line:
            last_result = line.split("RESULT:")[1].strip()[:100]
            # Extract for recent activity
            ts = line[:19] if len(line) > 19 else ""
            recent_activity.append({"time": ts, "result": last_result})

    return {
        "queries_today": queries_today,
        "cache_hits": cache_hits,
        "vector_hits": vector_hits,
        "internet_searches": internet_searches,
        "auto_saves": auto_saves,
        "errors": errors,
        "last_query": last_query,
        "last_result": last_result,
        "recent_activity": recent_activity[-10:],
    }


def _check_state():
    """Lee el estado actual del motor."""
    state_file = _PROJECT / "core" / "motor_ia_state.json"
    try:
        if not state_file.exists():
            return {"status": "NO_STATE", "query": "", "kb_pct": 0}
        with open(state_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"status": "ERROR"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/":
            try:
                html = HTML_FILE.read_text(encoding="utf-8")
            except Exception:
                html = "<h1>Dashboard HTML not found</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif self.path == "/api/status":
            now = datetime.now()

            # Collect all component statuses
            chromadb = _check_chromadb()
            cache = _check_kb_cache()
            knowledge = _check_knowledge_local()
            hooks = _check_hooks()
            metrics = _parse_motor_ia_log()
            state = _check_state()

            # Overall health
            components_ok = sum([
                chromadb["status"] == "OK",
                hooks.get("pre_hook") == "REGISTERED",
                hooks.get("post_hook") == "REGISTERED",
                knowledge["status"] == "OK",
            ])

            if components_ok == 4:
                overall = "HEALTHY"
            elif components_ok >= 2:
                overall = "DEGRADED"
            else:
                overall = "CRITICAL"

            status = {
                "timestamp": now.strftime("%d-%m-%Y %H:%M:%S"),
                "overall_health": overall,
                "components_ok": components_ok,
                "components_total": 4,

                # Component: ChromaDB (KB principal)
                "chromadb": chromadb,

                # Component: Cache TF-IDF
                "cache": cache,

                # Component: Knowledge local (backup)
                "knowledge_local": knowledge,

                # Component: Hooks
                "hooks": hooks,

                # Metrics del día
                "metrics": metrics,

                # Estado actual
                "current_state": state,

                # Log reciente
                "log_tail": _read_log_tail(_PROJECT / "core" / "motor_ia_hook.log", 15),
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(status, ensure_ascii=False, default=str).encode())

        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("DASHBOARD_PORT", "8080"))
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    print(f"Motor_IA Dashboard v2 on {host}:{port}", flush=True)
    srv = HTTPServer((host, port), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
