"""
iteration_learn.py -- Tracking de iteraciones y acciones (Motor Unificado)
==========================================================================
Se dispara despues de CADA uso de herramienta.
Detecta nueva iteracion (= nuevo mensaje del usuario) por gap temporal >15s.

CAPTURA TODO con contexto real:
  - Lecturas: que archivo, que se encontro
  - Ediciones: que cambio y por que
  - Busquedas: que se busco, cuantos resultados
  - Comandos: que se ejecuto, si funciono
  - Browser: que acciones se tomaron

DEDUPLICACION: fingerprint por combinacion de tools+archivos.
NOTIFICACION: escribe archivo de status que el CLI puede leer.
"""

import sys
import json
import re
import time
from pathlib import Path
from datetime import datetime

from config import (
    STATE_FILE, ACTIONS_LOG, ITERATION_GAP_SECS, DATA_DIR, MSG_TYPE_FILE,
    NOTIFY_FILE, FINGERPRINTS_FILE, FAILURES_FILE, DEBUG_LOG, LAST_MSG_FILE,
)
from core.file_lock import file_lock
from core.learning_memory import register_pattern, detect_errors, detect_success
from core.knowledge_base import search as kb_search, add_pattern as kb_add

# Cuantos explores consecutivos sin actuar = territorio nuevo -> busqueda proactiva
EXPLORE_THRESHOLD = 3

try:
    from core.knowledge_base import _load_all_domains
    HAS_KB = bool(_load_all_domains())
except Exception:
    HAS_KB = False


def debug_log(msg: str):
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] [iter] {msg}\n")
    except Exception:
        pass


def load_state() -> dict:
    try:
        with file_lock("iteration_state"):
            if STATE_FILE.exists():
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "sid" in data:
                    return data
    except Exception:
        pass
    return {"sid": "", "actions": [], "iteration": 0, "last_ts": 0}


def save_state(state: dict):
    """Guarda solo metadatos livianos (sid, iteration, last_ts)."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        light = {k: v for k, v in state.items() if k != "actions"}
        with file_lock("iteration_state"):
            STATE_FILE.write_text(json.dumps(light, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def append_action(action: dict, session_id: str, iteration: int):
    """Escribe una accion al log JSONL. O(1), sin lock, sin reescribir."""
    try:
        ACTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        action["_sid"] = session_id
        action["_iter"] = iteration
        with open(ACTIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(action, ensure_ascii=False) + "\n")
    except Exception:
        pass


def load_actions_for_session(session_id: str, iteration: int) -> list:
    """Lee del JSONL solo las acciones de esta sesion e iteracion."""
    actions = []
    try:
        if not ACTIONS_LOG.exists():
            return []
        with open(ACTIONS_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    a = json.loads(line)
                    if a.get("_sid") == session_id and a.get("_iter") == iteration:
                        actions.append(a)
                except Exception:
                    pass
    except Exception:
        pass
    return actions


def trim_actions_log(max_lines: int = 5000):
    """Rota el JSONL si crece demasiado."""
    try:
        if not ACTIONS_LOG.exists():
            return
        lines = ACTIONS_LOG.read_text(encoding="utf-8").splitlines()
        if len(lines) > max_lines:
            ACTIONS_LOG.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")
    except Exception:
        pass


# ================================================================
#  CAPTURA DE CONTEXTO REAL
# ================================================================

def extract_context(tool_name: str, tool_input: dict, tool_result) -> dict:
    """Extrae contexto REAL de cada accion."""
    result_text = ""
    if isinstance(tool_result, str):
        result_text = tool_result
    elif isinstance(tool_result, dict):
        result_text = tool_result.get("content", "") or tool_result.get("output", "")
        if isinstance(result_text, list):
            result_text = " ".join(
                b.get("text", "") for b in result_text
                if isinstance(b, dict) and b.get("type") == "text"
            )
    result_text = str(result_text)

    ctx = {"tool": tool_name, "t": datetime.now().isoformat()}

    if tool_name == "Read":
        fp = tool_input.get("file_path", "?")
        ctx["file"] = fp
        ctx["action"] = f"Leyo {Path(fp).name}"
        preview = result_text[:300].replace("\n", " ").strip()
        if preview:
            ctx["found"] = preview

    elif tool_name == "Edit":
        fp = tool_input.get("file_path", "?")
        old = tool_input.get("old_string", "")[:100]
        new = tool_input.get("new_string", "")[:100]
        ctx["file"] = fp
        ctx["action"] = f"Edito {Path(fp).name}"
        ctx["change"] = (
            f"{old[:60].replace(chr(10), ' ').replace(chr(13), '')} -> "
            f"{new[:60].replace(chr(10), ' ').replace(chr(13), '')}"
        )

    elif tool_name == "Write":
        fp = tool_input.get("file_path", "?")
        content_preview = tool_input.get("content", "")[:150]
        ctx["file"] = fp
        ctx["action"] = f"Creo {Path(fp).name}"
        ctx["preview"] = content_preview.replace("\n", " ")[:100]

    elif tool_name == "Bash":
        cmd = tool_input.get("command", "?")[:120]
        ctx["action"] = f"Ejecuto: {cmd}"
        if "error" in result_text.lower()[:200] or "traceback" in result_text.lower()[:200]:
            ctx["result"] = "ERROR: " + result_text[:150].replace("\n", " ")
        else:
            ctx["result"] = result_text[:150].replace("\n", " ").strip()

    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "?")
        path = tool_input.get("path", ".")
        ctx["action"] = f"Busco '{pattern}' en {Path(path).name if path != '.' else 'proyecto'}"
        lines = result_text.strip().split("\n") if result_text.strip() else []
        ctx["results_count"] = len(lines)
        if lines:
            ctx["sample"] = lines[0][:100]

    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "?")
        ctx["action"] = f"Glob: {pattern}"
        lines = result_text.strip().split("\n") if result_text.strip() else []
        ctx["results_count"] = len(lines)

    elif tool_name == "Agent":
        desc = tool_input.get("description", "?")
        ctx["action"] = f"Agente: {desc}"
        ctx["result"] = result_text[:200].replace("\n", " ").strip()

    elif "chrome" in tool_name.lower():
        short = tool_name.split("__")[-1] if "__" in tool_name else tool_name
        ctx["action"] = f"Browser: {short}"
        url = tool_input.get("url", "")
        if url:
            ctx["url"] = url[:100]
        text = tool_input.get("text", "") or tool_input.get("value", "")
        if text:
            ctx["input"] = str(text)[:80]

    else:
        ctx["action"] = f"{tool_name}"
        if tool_input:
            ctx["input_summary"] = str(tool_input)[:100]

    return ctx


# ================================================================
#  DOMINIO Y DEDUPLICACION
# ================================================================

def detect_domain(actions: list) -> str:
    """
    Detecta dominio a partir de las acciones de una iteracion.
    Usa los dominios conocidos de KB para clasificar.
    Si no hay match, retorna "general".
    """
    all_text = " ".join(
        a.get("action", "") + " " + a.get("file", "") + " " + a.get("found", "")
        for a in actions
    ).lower()

    # Intentar usar KB para detectar dominio
    try:
        from core.knowledge_base import _load_all_domains
        domains = _load_all_domains()
        scores = {}
        for domain_name in domains:
            # Buscar el nombre del dominio y variaciones en el texto
            variants = [domain_name, domain_name.replace("_", " "), domain_name.replace("_", "")]
            for v in variants:
                if len(v) >= 3 and v in all_text:
                    scores[domain_name] = scores.get(domain_name, 0) + 1
        if scores:
            return max(scores, key=scores.get)
    except Exception:
        pass

    return "general"


def _make_fingerprint(actions: list) -> str:
    """Fingerprint unico por iteracion."""
    parts = []
    for a in actions:
        detail = a.get("action", a.get("tool", ""))[:80]
        parts.append(detail)
    return "|".join(sorted(parts))


def _load_fingerprints() -> dict:
    try:
        if FINGERPRINTS_FILE.exists():
            data = json.loads(FINGERPRINTS_FILE.read_text(encoding="utf-8"))
            cutoff = time.time() - 7200  # 2 horas
            return {k: v for k, v in data.items() if v > cutoff}
    except Exception:
        pass
    return {}


def _save_fingerprint(fp: str):
    try:
        with file_lock("iter_fingerprints"):
            data = _load_fingerprints()
            data[fp] = time.time()
            FINGERPRINTS_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


# ================================================================
#  GUARDAR EN KB CON CONTEXTO RICO
# ================================================================

def kb_save(actions: list, iteration_num: int) -> tuple:
    """Guarda experiencia COMPLETA de una iteracion. Con deduplicacion."""
    if not HAS_KB or not actions:
        return False, ""

    fp = _make_fingerprint(actions)
    if fp in _load_fingerprints():
        debug_log(f"Dedup: skip iter {iteration_num}, fingerprint exists")
        return False, ""

    reads = [a for a in actions if a["tool"] == "Read"]
    edits = [a for a in actions if a["tool"] == "Edit"]
    writes = [a for a in actions if a["tool"] == "Write"]
    commands = [a for a in actions if a["tool"] == "Bash"]
    searches = [a for a in actions if a["tool"] in ("Grep", "Glob")]
    browser = [a for a in actions if "chrome" in a.get("tool", "").lower()]

    parts = []
    if reads:
        file_names = list(set(Path(a.get("file", "?")).name for a in reads if a.get("file")))
        parts.append(f"Leyo: {', '.join(file_names[:5])}")
        for a in reads[:3]:
            found = a.get("found", "")
            if found:
                parts.append(f"  > {Path(a.get('file','?')).name}: {found[:120]}")
    if edits:
        for a in edits[:5]:
            change = a.get("change", "")
            parts.append(f"Edito {Path(a.get('file','?')).name}: {change[:100]}")
    if writes:
        for a in writes[:3]:
            parts.append(f"Creo {Path(a.get('file','?')).name}: {a.get('preview','')[:80]}")
    if commands:
        for a in commands[:3]:
            result = a.get("result", "")
            if result:
                parts.append(f"CMD: {a.get('action','')} > {result[:80]}")
            else:
                parts.append(a.get("action", ""))
    if searches:
        for a in searches[:3]:
            count = a.get("results_count", 0)
            parts.append(f"{a.get('action','')} ({count} resultados)")
    if browser:
        parts.append(f"{len(browser)} acciones browser")

    summary = " | ".join(parts) if parts else "Interaccion de texto"
    domain = detect_domain(actions)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    key = f"iter_{timestamp}_i{iteration_num}"
    all_files = list(set(a.get("file", "") for a in actions if a.get("file")))

    notes_parts = [f"Iteracion {iteration_num}:"]
    for a in actions[:15]:
        action = a.get("action", "")
        found = a.get("found", "")
        change = a.get("change", "")
        result = a.get("result", "")
        detail = action
        if found:
            detail += f" > encontro: {found[:80]}"
        elif change:
            detail += f" > cambio: {change[:80]}"
        elif result:
            detail += f" > {result[:80]}"
        notes_parts.append(f"  {detail}")

    # Leer contexto del tipo de mensaje para etiquetar correctamente
    msg_type = "instruction"
    had_kb   = False
    try:
        if MSG_TYPE_FILE.exists():
            _mc = json.loads(MSG_TYPE_FILE.read_text(encoding="utf-8"))
            msg_type = _mc.get("type", "instruction")
            had_kb   = _mc.get("has_kb", False)
    except Exception:
        pass

    # Determinar estrategia de guardado
    if had_kb and (edits or writes or commands):
        strategy   = "differential_capture"      # habia KB, esto es lo NUEVO
        extra_note = "[DIFERENCIAL] Complemento a KB existente."
    elif not had_kb and (edits or writes or commands):
        strategy   = "new_experience_capture"    # sin KB, experiencia completamente nueva
        extra_note = "[NUEVO] Sin conocimiento previo en KB."
    elif msg_type == "informing":
        strategy   = "context_capture"           # el usuario nos informo algo
        extra_note = "[CONTEXTO] Informacion recibida del usuario."
    else:
        strategy   = "auto_iteration_capture"
        extra_note = ""

    if extra_note:
        notes_parts.insert(1, extra_note)

    try:
        kb_add(domain, key, {
            "strategy": strategy,
            "notes": "\n".join(notes_parts)[:1500],
            "auto_learned": True,
            "source": "post_tool_hook",
            "msg_type": msg_type,
            "had_kb_match": had_kb,
            "files_touched": all_files[:10],
            "activity": {
                "reads": len(reads), "edits": len(edits), "writes": len(writes),
                "commands": len(commands), "searches": len(searches),
                "browser": len(browser), "total": len(actions),
            },
            "iteration": iteration_num,
        }, tags=["auto-learned", "iteration", domain, strategy.split("_")[0]])

        _save_fingerprint(fp)
        debug_log(f"KB saved iter {iteration_num}: {len(actions)} actions, domain={domain}")
        return True, summary
    except Exception as e:
        debug_log(f"KB save failed: {e}")
        return False, ""


# ================================================================
#  NOTIFICACION
# ================================================================

def write_notification(iteration_num: int, action_count: int,
                       summary: str, domain: str, saved: bool):
    """Escribe archivo de notificacion que indica que el aprendizaje se acumula."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status = "GUARDADO" if saved else "DEDUP-SKIP"

    lines = []
    try:
        if NOTIFY_FILE.exists():
            lines = NOTIFY_FILE.read_text(encoding="utf-8").strip().split("\n")
            lines = lines[-19:]
    except Exception:
        pass

    clean_summary = (summary[:120]
                     .replace("\n", " ")
                     .replace("\r", "")
                     .encode("ascii", "replace")
                     .decode("ascii"))
    new_line = (f"[{now}] {status} iter {iteration_num} | "
                f"KB/{domain} | {action_count} acciones | {clean_summary}")
    lines.append(new_line)

    try:
        with file_lock("last_learning"):
            NOTIFY_FILE.parent.mkdir(parents=True, exist_ok=True)
            NOTIFY_FILE.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass


# ================================================================
#  FLUSH (llamado por el hook de fin de sesion)
# ================================================================

def flush_pending() -> bool:
    """Lee acciones del JSONL para la iteracion actual y guarda en KB."""
    state = load_state()
    sid = state.get("sid", "")
    itr = state.get("iteration", 1)
    if not sid:
        return False
    actions = load_actions_for_session(sid, itr)
    if actions:
        saved, summary = kb_save(actions, itr)
        domain = detect_domain(actions)
        write_notification(itr, len(actions), summary, domain, saved)
        if saved:
            debug_log(f"Flush: saved iter {itr} ({len(actions)} actions)")
        trim_actions_log()
        return saved
    return False


# ================================================================
#  BUSQUEDA EN KB TRAS FALLO
# ================================================================

ERROR_SIGNALS = [
    "traceback", "error:", "exception:", "failed", "errno",
    "not found", "permission denied", "syntaxerror", "importerror",
    "modulenotfounderror", "filenotfounderror", "typeerror",
    "cannot", "invalid", "refused", "timed out",
]


def _is_failure(tool_name: str, tool_result, exit_code) -> bool:
    if exit_code is not None and exit_code != 0:
        return True
    result_lower = str(tool_result)[:600].lower()
    return any(sig in result_lower for sig in ERROR_SIGNALS)


def _capture_failure_context(pattern_key: str, tool_input: dict, error_text: str):
    try:
        ctx = {
            "ts": datetime.now().isoformat(),
            "file_ext": Path(tool_input.get("file_path", "?")).suffix or "none",
            "hour": datetime.now().hour,
            "weekday": datetime.now().weekday(),
            "error": error_text[:80],
        }
        FAILURES_FILE.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if FAILURES_FILE.exists():
            try:
                data = json.loads(FAILURES_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        key_list = data.get(pattern_key, [])
        key_list.append(ctx)
        data[pattern_key] = key_list[-20:]
        FAILURES_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _get_failure_annotation(pattern_key: str) -> str:
    try:
        if not FAILURES_FILE.exists():
            return ""
        data = json.loads(FAILURES_FILE.read_text(encoding="utf-8"))
        failures = data.get(pattern_key, [])
        if len(failures) < 3:
            return ""

        from collections import Counter
        exts = [f.get("file_ext", "") for f in failures
                if f.get("file_ext") not in ("", "none", "?")]
        if exts:
            top_ext, count = Counter(exts).most_common(1)[0]
            if count >= 3:
                return f" [falla {count}x con {top_ext}]"

        hours = [f.get("hour", -1) for f in failures]
        if hours:
            avg_hour = sum(hours) / len(hours)
            if all(abs(h - avg_hour) < 3 for h in hours):
                return f" [falla frecuente ~{int(avg_hour)}h]"

        return f" [{len(failures)} fallos registrados]"
    except Exception:
        return ""


def search_kb_on_failure(tool_name: str, tool_input: dict, tool_result) -> str:
    """
    Cuando un tool falla, busca en KB y learning_memory si ya vimos
    ese error antes y tenemos un fix probado.
    """
    if tool_name not in ("Bash", "Edit", "Write"):
        return ""

    error_text = str(tool_result)[:800].lower()
    error_words = set(re.findall(r'\b[a-z_][a-z0-9_]{3,}\b', error_text))
    error_words -= {"none", "true", "false", "line", "file", "self", "with",
                    "from", "import", "return", "print", "open", "read"}

    if not error_words:
        return ""

    found_lines = []

    # 1. Buscar en learning_memory
    try:
        from core.learning_memory import _load_memory
        mem = _load_memory()
        candidates = []

        for pid, p in mem["patterns"].items():
            sol = p.get("solution", {})
            searchable = " ".join([
                sol.get("error_command", ""),
                " ".join(str(m) for m in sol.get("error_messages", [])),
                sol.get("notes", ""),
                sol.get("fix_command", ""),
                p.get("context_key", ""),
            ]).lower()

            score = sum(1 for w in error_words if w in searchable)
            if score >= 2:
                candidates.append((score, p))

        if candidates:
            candidates.sort(key=lambda x: (-x[0], -x[1]["stats"].get("success_rate", 0)))
            score, best = candidates[0]
            sol = best.get("solution", {})
            sr = best["stats"].get("success_rate", 0)
            pattern_key = best.get("context_key", best.get("task_type", "unknown"))
            fix = sol.get("fix_command") or sol.get("notes", "")

            _capture_failure_context(pattern_key, tool_input, error_text[:200])
            failure_note = _get_failure_annotation(pattern_key)

            if fix:
                found_lines.append(
                    f"[KB/fix] ESTE ERROR YA OCURRIO -- "
                    f"fix con {sr*100:.0f}% de exito{failure_note}. APLICAR:\n  {fix[:300]}"
                )
                if sol.get("strategy"):
                    found_lines.append(f"  Estrategia probada: {sol['strategy']}")
    except Exception:
        pass

    # 2. Buscar en knowledge_base
    if not found_lines:
        try:
            from core.knowledge_base import cross_domain_search
            query = " ".join(list(error_words)[:6])
            results = cross_domain_search(text_query=query)
            for dom, entries in results.items():
                for e in entries[:1]:
                    sol = e.get("solution", {})
                    notes = sol.get("notes", "")[:200]
                    if notes and len(notes) > 20:
                        found_lines.append(f"[KB/{dom}] Referencia: {notes}")
                        break
                if found_lines:
                    break
        except Exception:
            pass

    return "\n".join(found_lines)


# ================================================================
#  DETECCION DE TERRITORIO NUEVO
# ================================================================

def _is_exploration(tool_name: str) -> bool:
    return tool_name in ("Read", "Grep", "Glob")


def _is_action(tool_name: str) -> bool:
    return tool_name in ("Edit", "Write", "Bash")


def _adaptive_explore_threshold(explored_files: list) -> int:
    threshold = EXPLORE_THRESHOLD
    try:
        if LAST_MSG_FILE.exists():
            last_msg = LAST_MSG_FILE.read_text(encoding="utf-8").lower()
            REVIEW_WORDS = {
                "revisa", "analiza", "audita", "review", "audit",
                "inspect", "lee todos", "recorre", "lista todos",
                "check all", "scan", "busca en", "find all",
            }
            if any(w in last_msg for w in REVIEW_WORDS):
                threshold = 8
    except Exception:
        pass

    if explored_files and threshold < 6:
        dirs = set(str(Path(f).parent) for f in explored_files if f)
        if len(dirs) <= 1:
            threshold = 6

    return threshold


def search_kb_for_territory(action_record: dict, recent_files: list) -> str:
    """
    Busca en KB cuando Claude lleva varios explores consecutivos sin actuar.
    """
    try:
        from core.knowledge_base import cross_domain_search

        _STOP = {
            "none", "true", "false", "line", "file", "self", "with",
            "from", "import", "return", "print", "open", "read",
            "found", "action", "tool", "the", "and", "for", "that",
            "this", "into", "have", "been", "are", "was",
        }

        topic_parts = []

        if action_record.get("file"):
            fname = Path(action_record["file"]).stem.lower()
            if len(fname) > 3:
                topic_parts.append(fname)
            parent = Path(action_record["file"]).parent.name.lower()
            if parent and parent not in (".", ""):
                topic_parts.append(parent)

        if action_record.get("action"):
            words = re.findall(r'\b[a-zA-Z][a-z]{3,}\b', action_record["action"])
            topic_parts.extend(w.lower() for w in words[:4])

        if action_record.get("found"):
            words = re.findall(r'\b[a-zA-Z][a-z]{3,}\b', action_record["found"][:300])
            topic_parts.extend(w.lower() for w in words[:4])

        for fp in recent_files[-3:]:
            fname = Path(fp).stem.lower()
            if len(fname) > 3:
                topic_parts.append(fname)

        keywords = [w for w in topic_parts if w not in _STOP][:8]
        if not keywords:
            return ""

        query = " ".join(keywords)
        results = cross_domain_search(text_query=query)

        lines = []
        for dom, entries in results.items():
            for e in entries[:1]:
                if e.get("type") == "pattern":
                    sol = e.get("solution", {})
                    notes = sol.get("notes", "")[:200]
                    strategy = sol.get("strategy", "")
                    if notes and len(notes) > 20:
                        lines.append(f"[KB/{dom}] {strategy or 'referencia'}: {notes}")
                elif e.get("type") == "fact":
                    fact = e.get("fact", {})
                    rule = fact.get("rule", "")[:200]
                    if rule and len(rule) > 20:
                        lines.append(f"[KB/{dom}] regla: {rule}")
                if lines:
                    break
            if len(lines) >= 2:
                break

        return "\n".join(lines)
    except Exception:
        return ""


# ================================================================
#  MAIN -- PostToolUse handler
# ================================================================

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--flush":
        flush_pending()
        sys.exit(0)

    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    tool_result = data.get("tool_result", "")
    exit_code = data.get("exit_code")
    session_id = data.get("session_id", "")

    # PRIMERO: si fallo, buscar fix en KB antes de que el CLI reintente
    if _is_failure(tool_name, tool_result, exit_code):
        hint = search_kb_on_failure(tool_name, tool_input, tool_result)
        if hint:
            sys.stdout.write(hint + "\n")
            sys.stdout.flush()

    state = load_state()
    action_record_preview = extract_context(tool_name, tool_input, tool_result)

    # TERRITORIO NUEVO: racha de exploracion sin accion
    if _is_exploration(tool_name):
        _read_now = time.time()
        _last_read = state.get("last_read_ts", 0)
        _gap = _read_now - _last_read if _last_read > 0 else 99.0
        state["last_read_ts"] = _read_now
        if _gap >= 2.0:
            state["explore_streak"] = state.get("explore_streak", 0) + 1
        fp_val = action_record_preview.get("file", "")
        if fp_val:
            seen = state.get("explored_files", [])
            if fp_val not in seen:
                seen.append(fp_val)
                state["explored_files"] = seen[-20:]
    elif _is_action(tool_name):
        state["explore_streak"] = 0
        state["last_read_ts"] = 0
        state["territory_searched"] = False

    effective_threshold = _adaptive_explore_threshold(state.get("explored_files", []))
    already_searched = state.get("territory_searched", False)

    if state.get("explore_streak", 0) == effective_threshold and not already_searched:
        recent_files = state.get("explored_files", [])
        territory_hint = search_kb_for_territory(action_record_preview, recent_files)
        if territory_hint:
            header = (f"[MAPA KB -- {effective_threshold} explores sin actuar "
                      f"(territorio nuevo detectado)]:\n")
            sys.stdout.write(header + territory_hint + "\n")
            sys.stdout.flush()
        state["territory_searched"] = True

    now = time.time()

    if state.get("sid") != session_id:
        debug_log(f"New session: {session_id[:20]}")
        state = {
            "sid": session_id, "iteration": 1, "last_ts": now,
            "explore_streak": state.get("explore_streak", 0),
            "explored_files": state.get("explored_files", []),
        }
        save_state(state)

    last_ts = state.get("last_ts", 0)
    gap = now - last_ts if last_ts > 0 else 0

    if gap > ITERATION_GAP_SECS:
        prev_iter = state.get("iteration", 1)
        prev_actions = load_actions_for_session(session_id, prev_iter)
        if prev_actions and prev_iter >= 1:
            saved, summary = kb_save(prev_actions, prev_iter)
            domain = detect_domain(prev_actions)
            write_notification(prev_iter, len(prev_actions), summary, domain, saved)
            debug_log(f"Flushed iter {prev_iter}: {len(prev_actions)} actions, domain={domain}")

        state["iteration"] = prev_iter + 1
        debug_log(f"New iteration (gap={gap:.0f}s) -> {state['iteration']}")

    if state.get("iteration", 0) == 0:
        state["iteration"] = 1

    append_action(action_record_preview, session_id, state["iteration"])

    state["last_ts"] = now
    save_state(state)

    if int(now) % 100 == 0:
        trim_actions_log()


if __name__ == "__main__":
    main()
