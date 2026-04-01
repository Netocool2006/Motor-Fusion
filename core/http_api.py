# -*- coding: utf-8 -*-
"""
http_api.py -- HTTP API standalone para Motor_IA
=================================================
Expone Motor_IA via HTTP en el puerto 7437 (mismo que Engram por defecto).
Sin dependencias externas: usa http.server de la stdlib.

Endpoints:
  GET  /health                    → status del sistema
  GET  /stats                     → estadisticas de todos los modulos
  POST /mem/search                → buscar patrones en learning_memory
  POST /mem/save                  → guardar patron
  GET  /mem/export                → exportar todos los patrones activos
  POST /mem/timeline              → busqueda con contexto cronologico
  GET  /mem/context               → working memory actual (wm_to_context)
  POST /mem/session/start         → iniciar sesion (wm limpia)
  POST /mem/session/end           → cerrar sesion (prune + score)
  GET  /kb/search?q=<query>       → buscar en knowledge base
  GET  /kb/domains                → listar dominios disponibles
  POST /wm/add                    → agregar item a working memory
  GET  /wm/get                    → obtener working memory actual
  GET  /graph/stats               → estadisticas del grafo asociativo
  POST /graph/associate           → crear asociacion entre patrones

Motor_IA ventaja: API identica a Engram (puerto 7437) pero con
los 13 endpoints extendidos de Motor_IA (SAP, correlacion error->fix, etc.)

Uso:
  python -m core.http_api              # puerto 7437 por defecto
  python -m core.http_api --port 8080  # puerto custom
  python -m core.http_api --host 0.0.0.0 --port 7437
"""

import json
import sys
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

_MOTOR_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_MOTOR_DIR))

DEFAULT_PORT = 7437
DEFAULT_HOST = "127.0.0.1"


# ======================================================================
#  REQUEST HANDLER
# ======================================================================

class MotorAPIHandler(BaseHTTPRequestHandler):
    """Handler HTTP para Motor_IA API."""

    def log_message(self, fmt, *args):
        """Silenciar logs del servidor excepto errores."""
        if args and str(args[1]) not in ("200", "204"):
            super().log_message(fmt, *args)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message: str, status: int = 400):
        self._send_json({"error": message}, status)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        try:
            if path == "/health":
                self._send_json({"status": "ok", "service": "Motor_IA", "port": DEFAULT_PORT})

            elif path == "/stats":
                result = {}
                try:
                    from core.learning_memory import get_stats as lm_stats
                    result["learning_memory"] = lm_stats()
                except Exception as e:
                    result["learning_memory"] = {"error": str(e)}
                try:
                    from core.working_memory import get_stats as wm_stats
                    result["working_memory"] = wm_stats()
                except Exception as e:
                    result["working_memory"] = {"error": str(e)}
                try:
                    from core.associative_memory import get_stats as am_stats
                    result["associative_memory"] = am_stats()
                except Exception as e:
                    result["associative_memory"] = {"error": str(e)}
                try:
                    from core.episodic_index import get_stats as ep_stats
                    result["episodic_index"] = ep_stats()
                except Exception as e:
                    result["episodic_index"] = {"error": str(e)}
                try:
                    from core.memory_pruner import get_stats as pr_stats
                    result["memory_pruner"] = pr_stats()
                except Exception as e:
                    result["memory_pruner"] = {"error": str(e)}
                self._send_json(result)

            elif path == "/mem/export":
                try:
                    from core.learning_memory import _load_memory
                    mem = _load_memory()
                    active = {
                        pid: p for pid, p in mem.get("patterns", {}).items()
                        if not p.get("deleted_at")
                    }
                    self._send_json({"patterns": active, "total": len(active)})
                except Exception as e:
                    self._send_error(str(e), 500)

            elif path == "/mem/context":
                try:
                    from core.working_memory import wm_to_context
                    ctx = wm_to_context(max_items=20)
                    self._send_json({"context": ctx, "empty": ctx == ""})
                except Exception as e:
                    self._send_error(str(e), 500)

            elif path == "/wm/get":
                try:
                    from core.working_memory import wm_get
                    items = wm_get()
                    self._send_json({"items": items, "total": len(items)})
                except Exception as e:
                    self._send_error(str(e), 500)

            elif path == "/kb/search":
                q = qs.get("q", [""])[0].strip()
                if not q:
                    self._send_error("Parametro 'q' requerido")
                    return
                try:
                    from core.knowledge_base import search_knowledge
                    results = search_knowledge(q)
                    self._send_json({"query": q, "results": results})
                except Exception as e:
                    self._send_error(str(e), 500)

            elif path == "/kb/domains":
                try:
                    from core.domains_config import list_domains
                    domains = list_domains()
                    self._send_json({"domains": domains, "total": len(domains)})
                except Exception as e:
                    self._send_error(str(e), 500)

            elif path == "/graph/stats":
                try:
                    from core.associative_memory import get_stats as am_stats
                    self._send_json(am_stats())
                except Exception as e:
                    self._send_error(str(e), 500)

            else:
                self._send_error(f"Endpoint no encontrado: {path}", 404)

        except Exception as e:
            self._send_error(f"Error interno: {e}", 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = self._read_body()

        try:
            if path == "/mem/search":
                task_type = body.get("task_type", "")
                context_key = body.get("context_key", "")
                tags = body.get("tags", [])
                if not task_type or not context_key:
                    self._send_error("task_type y context_key requeridos")
                    return
                try:
                    from core.learning_memory import search_pattern
                    result = search_pattern(task_type, context_key, tags=tags)
                    self._send_json({"found": result is not None, "pattern": result})
                except Exception as e:
                    self._send_error(str(e), 500)

            elif path == "/mem/save":
                task_type = body.get("task_type", "")
                context_key = body.get("context_key", "")
                solution = body.get("solution", {})
                if not task_type or not context_key:
                    self._send_error("task_type y context_key requeridos")
                    return
                try:
                    from core.learning_memory import register_pattern
                    pid = register_pattern(
                        task_type=task_type,
                        context_key=context_key,
                        solution=solution,
                        tags=body.get("tags", []),
                        scope=body.get("scope", "project"),
                        topic_key=body.get("topic_key", ""),
                        project=body.get("project", ""),
                    )
                    self._send_json({"saved": True, "pattern_id": pid})
                except Exception as e:
                    self._send_error(str(e), 500)

            elif path == "/mem/timeline":
                query = body.get("query", "")
                if not query:
                    self._send_error("query requerido")
                    return
                try:
                    from core.episodic_index import timeline_search
                    results = timeline_search(
                        query,
                        before=body.get("before", 2),
                        after=body.get("after", 2),
                    )
                    self._send_json({"query": query, "results": results})
                except Exception as e:
                    self._send_error(str(e), 500)

            elif path == "/mem/session/start":
                session_id = body.get("session_id", "")
                try:
                    from core.working_memory import wm_clear
                    wm_clear(session_id=session_id)
                    self._send_json({"started": True, "session_id": session_id})
                except Exception as e:
                    self._send_error(str(e), 500)

            elif path == "/mem/session/end":
                session_id = body.get("session_id", "")
                transcript = body.get("transcript", "")
                try:
                    from core.hint_tracker import score_injection
                    from core.memory_pruner import auto_prune
                    from core.working_memory import wm_clear
                    if session_id and transcript:
                        score_injection(session_id, transcript)
                    auto_prune(dry_run=False)
                    wm_clear(session_id=session_id)
                    self._send_json({"ended": True, "session_id": session_id})
                except Exception as e:
                    self._send_error(str(e), 500)

            elif path == "/wm/add":
                content = body.get("content", "")
                if not content:
                    self._send_error("content requerido")
                    return
                try:
                    from core.working_memory import wm_add
                    item_id = wm_add(
                        content=content,
                        category=body.get("category", "observation"),
                        session_id=body.get("session_id", ""),
                        metadata=body.get("metadata", {}),
                    )
                    self._send_json({"added": True, "item_id": item_id})
                except Exception as e:
                    self._send_error(str(e), 500)

            elif path == "/graph/associate":
                a = body.get("pattern_id_a", "")
                b = body.get("pattern_id_b", "")
                relation = body.get("relation", "related")
                if not a or not b:
                    self._send_error("pattern_id_a y pattern_id_b requeridos")
                    return
                try:
                    from core.associative_memory import associate
                    ok = associate(a, b, relation, metadata=body.get("metadata", {}))
                    self._send_json({"created": ok, "from": a, "to": b, "relation": relation})
                except Exception as e:
                    self._send_error(str(e), 500)

            else:
                self._send_error(f"Endpoint no encontrado: {path}", 404)

        except Exception as e:
            self._send_error(f"Error interno: {e}", 500)


# ======================================================================
#  SERVER
# ======================================================================

def start_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 quiet: bool = False) -> HTTPServer:
    """
    Inicia el servidor HTTP. Retorna el objeto HTTPServer.
    Llamar server.serve_forever() para bloqueante,
    o server.handle_request() para una sola request.
    """
    server = HTTPServer((host, port), MotorAPIHandler)
    if not quiet:
        print(f"Motor_IA HTTP API corriendo en http://{host}:{port}")
        print("Endpoints: /health /stats /mem/search /mem/save /mem/export")
        print("           /mem/timeline /mem/context /mem/session/start /mem/session/end")
        print("           /wm/add /wm/get /kb/search /kb/domains /graph/stats /graph/associate")
        print("Ctrl+C para detener.")
    return server


def get_endpoints() -> list:
    """Retorna lista de endpoints disponibles (para tests sin levantar servidor)."""
    return [
        {"method": "GET",  "path": "/health"},
        {"method": "GET",  "path": "/stats"},
        {"method": "POST", "path": "/mem/search"},
        {"method": "POST", "path": "/mem/save"},
        {"method": "GET",  "path": "/mem/export"},
        {"method": "POST", "path": "/mem/timeline"},
        {"method": "GET",  "path": "/mem/context"},
        {"method": "POST", "path": "/mem/session/start"},
        {"method": "POST", "path": "/mem/session/end"},
        {"method": "POST", "path": "/wm/add"},
        {"method": "GET",  "path": "/wm/get"},
        {"method": "GET",  "path": "/kb/search"},
        {"method": "GET",  "path": "/kb/domains"},
        {"method": "GET",  "path": "/graph/stats"},
        {"method": "POST", "path": "/graph/associate"},
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Motor_IA HTTP API")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    server = start_server(args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
        server.server_close()
