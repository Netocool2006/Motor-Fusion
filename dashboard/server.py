#!/usr/bin/env python
"""Motor_IA Dashboard Server"""
import sys, os, json, datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

DATA_DIR = Path(os.environ.get(
    "MOTOR_IA_DATA",
    Path.home() / "AppData" / "Local" / "ClaudeCode" / ".adaptive_cli"
))
DASHBOARD_DIR = Path(__file__).parent
SETTINGS_FILES = [
    Path.home() / ".claude" / "settings.json",
    Path("C:/Chance1/.claude/settings.json"),
]


def parse_ts(line):
    """Intenta extraer datetime de una linea de log '[YYYY-MM-DD HH:MM:SS]...'"""
    try:
        if line.startswith("["):
            end = line.index("]")
            return datetime.datetime.fromisoformat(line[1:end])
    except Exception:
        pass
    return None


def get_status():
    now = datetime.datetime.now()
    out = {
        "timestamp": now.isoformat(),
        "motor_activo": False,
        "hooks_registrados": False,
        "ultima_actividad_ts": None,
        "minutos_inactivo": None,
        "hooks_log": [],
        "errores": [],
        "kb": {},
        "sesiones": [],
        "ultimo_aprendizaje": None,
        "iteracion": None,
        "ejecuciones": [],
    }

    # ── hooks registrados ─────────────────────────────────────────────────────
    for sf in SETTINGS_FILES:
        if sf.exists():
            try:
                data = json.loads(sf.read_text(encoding="utf-8"))
                hooks = data.get("hooks", [])
                if any("Motor_IA" in str(h) or "motor_ia" in str(h).lower()
                       for h in hooks):
                    out["hooks_registrados"] = True
                    break
            except Exception:
                pass

    # ── hook_debug.log ────────────────────────────────────────────────────────
    log_path = DATA_DIR / "hook_debug.log"
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        recent = lines[-200:]
        log_entries, errors = [], []
        for ln in recent:
            s = ln.strip()
            if not s:
                continue
            if any(k in s for k in ("[ERROR]", "Traceback", "Error:", "Exception")):
                errors.append(s)
            else:
                log_entries.append(s)

        out["hooks_log"] = log_entries[-30:]
        out["errores"] = errors[-15:]

        # Ultima actividad
        for ln in reversed(recent):
            ts = parse_ts(ln.strip())
            if ts:
                out["ultima_actividad_ts"] = ts.isoformat()
                diff = (now - ts).total_seconds() / 60
                out["minutos_inactivo"] = round(diff, 1)
                out["motor_activo"] = diff < 30
                break

    # ── iteration_state.json ──────────────────────────────────────────────────
    iter_f = DATA_DIR / "iteration_state.json"
    if iter_f.exists():
        try:
            out["iteracion"] = json.loads(iter_f.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ── last_learning.txt ─────────────────────────────────────────────────────
    ll = DATA_DIR / "last_learning.txt"
    if ll.exists():
        lines = ll.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        out["ultimo_aprendizaje"] = lines[-1] if lines else None

    # ── execution_log.jsonl ───────────────────────────────────────────────────
    exec_f = DATA_DIR / "execution_log.jsonl"
    if exec_f.exists():
        rows = []
        for ln in exec_f.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]:
            try:
                rows.append(json.loads(ln))
            except Exception:
                pass
        out["ejecuciones"] = rows

    # ── KB stats ──────────────────────────────────────────────────────────────
    kb_dir = DATA_DIR / "knowledge"
    if kb_dir.exists():
        dom_f = kb_dir / "domains.json"
        if dom_f.exists():
            try:
                domains = json.loads(dom_f.read_text(encoding="utf-8"))
                out["kb"]["dominios"] = len(domains)
                out["kb"]["lista_dominios"] = list(domains.keys())
            except Exception:
                pass

        total = 0
        for pf in list(kb_dir.rglob("patterns.json")) + list(kb_dir.rglob("facts.json")):
            try:
                d = json.loads(pf.read_text(encoding="utf-8"))
                total += len(d.get("entries", {}))
            except Exception:
                pass
        out["kb"]["total_entradas"] = total

    # ── session_history ───────────────────────────────────────────────────────
    sh = DATA_DIR / "session_history.json"
    if sh.exists():
        try:
            sessions = json.loads(sh.read_text(encoding="utf-8"))
            out["sesiones"] = sessions[-5:]
        except Exception:
            pass

    # ── pattern_failures ─────────────────────────────────────────────────────
    pf = DATA_DIR / "pattern_failures.json"
    if pf.exists():
        try:
            data = json.loads(pf.read_text(encoding="utf-8"))
            out["pattern_failures"] = data if isinstance(data, list) else []
        except Exception:
            out["pattern_failures"] = []

    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # silencioso

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = (DASHBOARD_DIR / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(html)

        elif self.path == "/api/status":
            try:
                body = json.dumps(get_status(), ensure_ascii=False, indent=2).encode("utf-8")
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7070
    srv = HTTPServer(("localhost", port), Handler)
    print(f"Motor_IA Dashboard  ->  http://localhost:{port}")
    print("Ctrl+C para detener\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("Servidor detenido.")
