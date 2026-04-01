#!/usr/bin/env python
"""Motor_IA Dashboard Server"""
import sys, os, json, datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

def get_data_dir() -> Path:
    """Resolve data directory with fallback chain"""
    env_val = os.environ.get("MOTOR_IA_DATA")
    if env_val:
        p = Path(env_val)
        if p.is_absolute():
            return p

    home = Path.home()
    candidate = home / ".adaptive_cli"
    if home != Path("/") and home != Path("."):
        return candidate

    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            return Path(local_app) / "ClaudeCode" / ".adaptive_cli"

    return Path.home() / ".adaptive_cli"

DATA_DIR = get_data_dir()
DASHBOARD_DIR = Path(__file__).parent

def get_settings_files():
    """Build settings file list with environment variable support"""
    files = []

    # If CLAUDE_SETTINGS_PATH is set, use it first
    claude_settings = os.environ.get("CLAUDE_SETTINGS_PATH")
    if claude_settings:
        files.append(Path(claude_settings))

    # Standard locations
    files.extend([
        Path.home() / ".claude" / "settings.json",
        Path.home() / "AppData" / "Local" / "ClaudeCode" / ".claude" / "settings.json",
    ])

    return files

SETTINGS_FILES = get_settings_files()


def parse_ts(line):
    """Extrae datetime de linea de log '[2026-03-30T10:20:41...]' o campo 'ts'/'timestamp'"""
    try:
        if line.startswith("["):
            end = line.index("]")
            raw = line[1:end].split(".")[0]  # quita microsegundos si los hay
            return datetime.datetime.fromisoformat(raw)
    except Exception:
        pass
    return None


def latest_ts_from_jsonl(path, field="ts"):
    """Lee las ultimas 20 lineas de un .jsonl y retorna el datetime mas reciente."""
    best = None
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        for ln in lines[-20:]:
            try:
                obj = json.loads(ln)
                raw = obj.get(field) or obj.get("timestamp")
                if raw:
                    ts = datetime.datetime.fromisoformat(str(raw)[:19])
                    if best is None or ts > best:
                        best = ts
            except Exception:
                pass
    except Exception:
        pass
    return best


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

        # Timestamp desde hook_debug.log
        for ln in reversed(recent):
            ts = parse_ts(ln.strip())
            if ts:
                out["ultima_actividad_ts"] = ts.isoformat()
                break

    # ── timestamps de otros archivos de actividad ─────────────────────────────
    # prompt_history.jsonl  → UserPromptSubmit hook (mas frecuente)
    # execution_log.jsonl   → ejecuciones
    # iteration_actions.jsonl → aprendizaje iterativo
    # Solo archivos con timestamps en hora LOCAL (no UTC)
    activity_sources = [
        (DATA_DIR / "prompt_history.jsonl",    "ts"),
        (DATA_DIR / "iteration_actions.jsonl", "ts"),
    ]
    candidates = []
    if out["ultima_actividad_ts"]:
        try:
            candidates.append(datetime.datetime.fromisoformat(out["ultima_actividad_ts"]))
        except Exception:
            pass
    for path, field in activity_sources:
        ts = latest_ts_from_jsonl(path, field)
        if ts:
            candidates.append(ts)

    if candidates:
        best = max(candidates)
        out["ultima_actividad_ts"] = best.isoformat()
        diff = (now - best).total_seconds() / 60
        out["minutos_inactivo"] = round(diff, 1)
        # ACTIVO si hubo actividad en las ultimas 2 horas
        out["motor_activo"] = diff < 120

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
    # Port from command line > environment variable > default
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    else:
        port = int(os.environ.get("DASHBOARD_PORT", "7070"))

    # Host from environment variable > default
    host = os.environ.get("DASHBOARD_HOST", "localhost")

    srv = HTTPServer((host, port), Handler)
    print(f"Motor_IA Dashboard  ->  http://{host}:{port}")
    print("Ctrl+C para detener\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("Servidor detenido.")
