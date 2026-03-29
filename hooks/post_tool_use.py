# -*- coding: utf-8 -*-
"""
post_tool_use.py -- Hook PostToolUse: aprendizaje por herramienta
================================================================
Se dispara AUTOMATICAMENTE despues de cada uso de herramienta.

Captura:
  - Comandos ejecutados y si tuvieron exito o fallaron
  - Archivos editados/creados y el contexto
  - Errores encontrados (tracebacks, exit codes != 0)
  - Soluciones aplicadas (correlacion error->fix)

Registra en:
  - execution_log.jsonl (todas las acciones)
  - core/knowledge_base.py (patrones significativos)
  - core/learning_memory.py (patrones error->solucion reutilizables)
  - core/iteration_learn.py (tracking de iteraciones, si existe)

Usa message-type-aware recording: solo graba si el mensaje actual es
instruction/informing, o si hubo error, o si no habia KB.

Fusion de Motor 1 (post_action_learn.py) + Motor 2 (post_tool_use.py).
"""

import sys
import json
import re
import time
from pathlib import Path
from datetime import datetime, timezone

# -- path setup: parent = Motor_IA root
_MOTOR_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_MOTOR_DIR))

from config import (
    HOOK_STATE_DIR, PENDING_ERRORS_FILE, MSG_TYPE_FILE,
    ITERATION_GAP_SECS, STATE_FILE, ACTIONS_LOG,
    ERROR_CORRELATION_WINDOW,
)

# ======================================================================
#  PATRONES DE ERROR / EXITO / TRIVIAL
# ======================================================================

ERROR_PATTERNS = [
    r"Traceback \(most recent call last\)",
    r"Error:|ERROR:|error:|Exception:|FAILED",
    r"ModuleNotFoundError|ImportError|FileNotFoundError",
    r"SyntaxError|IndentationError|TypeError|ValueError",
    r"Permission denied|Access denied",
    r"command not found|not recognized",
    r"exit code [1-9]",
    r"ENOENT|EACCES|ECONNREFUSED",
]

SUCCESS_PATTERNS = [
    r"OK|ok|registrad|completado|creado|guardado|actualizado",
    r"successfully|exitosa|correcto|listo",
    r"\d+ (?:files?|archivos?|entradas?|patterns?|facts?)",
    r"Running on http://",
    r"exit code 0",
]

TRIVIAL_PATTERNS = [
    r"^\s*(pwd|which|where)\s*$",
]


# ======================================================================
#  UTILIDADES
# ======================================================================

def _ensure_dirs():
    HOOK_STATE_DIR.mkdir(parents=True, exist_ok=True)


def _is_trivial(command: str) -> bool:
    if not command:
        return True
    for pattern in TRIVIAL_PATTERNS:
        if re.match(pattern, command.strip(), re.IGNORECASE):
            return True
    return len(command.strip()) < 5


def _detect_errors(output: str) -> list:
    errors = []
    for pattern in ERROR_PATTERNS:
        matches = re.findall(pattern, str(output), re.IGNORECASE)
        if matches:
            errors.extend(matches[:3])
    return errors


def _detect_success(output: str) -> bool:
    for pattern in SUCCESS_PATTERNS:
        if re.search(pattern, str(output), re.IGNORECASE):
            return True
    return False


# ======================================================================
#  EXTRACCION DE CONTEXTO PER-TOOL
# ======================================================================

def _extract_key_info(tool_name: str, tool_input: dict,
                      tool_output: str, exit_code) -> dict:
    """Extrae informacion clave de la accion para registrar."""
    info = {
        "tool": tool_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": exit_code == 0 if exit_code is not None else True,
    }

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        info["command"] = cmd[:500]
        info["exit_code"] = exit_code
        info["errors"] = _detect_errors(tool_output)
        info["has_success_indicator"] = _detect_success(tool_output)
        parts = cmd.strip().split()
        if parts:
            info["program"] = parts[0]
            if "python" in parts[0].lower() and len(parts) > 1:
                info["script"] = parts[1]

    elif tool_name in ("Edit", "Write"):
        info["file"] = tool_input.get("file_path", "")
        info["success"] = "error" not in str(tool_output).lower()
        if tool_name == "Edit":
            old = tool_input.get("old_string", "")
            new = tool_input.get("new_string", "")
            info["change_summary"] = f"Replaced {len(old)} chars with {len(new)} chars"
            info["old_preview"] = old[:100]
            info["new_preview"] = new[:100]
        elif tool_name == "Write":
            content_len = len(tool_input.get("content", ""))
            info["change_summary"] = f"Created/overwrote file ({content_len} chars)"

    elif tool_name == "Read":
        info["file"] = tool_input.get("file_path", "")
        info["success"] = True

    elif tool_name in ("Grep", "Glob"):
        info["pattern"] = tool_input.get("pattern", "")
        info["path"] = tool_input.get("path", "")
        info["results_preview"] = str(tool_output)[:200]
        info["success"] = True

    else:
        # Cualquier otra herramienta (MCP, Agent, etc.)
        info["input_preview"] = str(tool_input)[:200]
        info["output_preview"] = str(tool_output)[:200]

    return info


# ======================================================================
#  PERSISTENCIA: log de acciones, errores pendientes
# ======================================================================

def _save_action(action_info: dict):
    """Guarda la accion en el log de estado del hook."""
    _ensure_dirs()
    state_file = HOOK_STATE_DIR / "last_actions.jsonl"
    try:
        with open(state_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(action_info, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _save_pending_error(error_info: dict):
    """Guarda un error pendiente para correlacionar con su fix posterior."""
    _ensure_dirs()
    pending = []
    if PENDING_ERRORS_FILE.exists():
        try:
            with open(PENDING_ERRORS_FILE, "r", encoding="utf-8") as f:
                pending = json.load(f)
        except (json.JSONDecodeError, Exception):
            pending = []

    pending.append(error_info)
    pending = pending[-10:]  # Mantener solo los ultimos 10

    try:
        with open(PENDING_ERRORS_FILE, "w", encoding="utf-8") as f:
            json.dump(pending, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ======================================================================
#  CORRELACION ERROR -> FIX
# ======================================================================

def _check_error_resolution(action_info: dict):
    """
    Verifica si esta accion exitosa resuelve un error pendiente.
    Si es asi, registra el patron error->solucion en Learning Memory.
    """
    tool = action_info.get("tool", "")
    is_edit_write_success = tool in ("Edit", "Write") and action_info.get("success")
    if not action_info.get("success") or not (
        action_info.get("has_success_indicator") or is_edit_write_success
    ):
        return

    if not PENDING_ERRORS_FILE.exists():
        return

    try:
        with open(PENDING_ERRORS_FILE, "r", encoding="utf-8") as f:
            pending = json.load(f)
    except (json.JSONDecodeError, Exception):
        return

    if not pending:
        return

    last_error = pending[-1]
    error_age_check = last_error.get("timestamp", "")

    # Solo correlacionar si el error es reciente
    try:
        error_time = datetime.fromisoformat(error_age_check)
        now = datetime.now(timezone.utc)
        if (now - error_time).total_seconds() > ERROR_CORRELATION_WINDOW:
            return
    except (ValueError, TypeError):
        return

    # Registrar patron error->solucion
    try:
        from core.learning_memory import register_pattern

        error_cmd = last_error.get("command", "unknown")[:100]
        fix_cmd = action_info.get("command", "unknown")[:200]
        error_msgs = last_error.get("errors", [])

        context_key = f"fix_{hash(error_cmd) % 100000}"
        register_pattern(
            task_type="auto_error_fix",
            context_key=context_key,
            solution={
                "strategy": "auto_captured_fix",
                "error_command": error_cmd,
                "error_messages": error_msgs[:3],
                "fix_command": fix_cmd,
                "notes": f"Error en: {error_cmd[:80]}. Fix: {fix_cmd[:80]}",
                "auto_learned": True,
            },
            tags=["auto_learned", "error_fix", action_info.get("program", "unknown")],
            error_context={
                "original_errors": error_msgs,
                "original_command": error_cmd,
            },
        )

        # Limpiar el error pendiente resuelto
        pending.pop()
        with open(PENDING_ERRORS_FILE, "w", encoding="utf-8") as f:
            json.dump(pending, f, ensure_ascii=False, indent=2)

    except Exception:
        pass


# ======================================================================
#  REGISTRO DE ACCIONES SIGNIFICATIVAS EN KB
# ======================================================================

def _register_significant_action(action_info: dict):
    """Registra acciones significativas en la KB."""
    tool = action_info.get("tool", "")

    if tool in ("Edit", "Write"):
        try:
            from core.knowledge_base import _append_log
            _append_log({
                "event": "file_modified",
                "file": action_info.get("file", ""),
                "change": action_info.get("change_summary", ""),
                "success": action_info.get("success", True),
            })
        except Exception:
            pass

    # Registrar ejecuciones de scripts Python del proyecto
    if tool == "Bash" and action_info.get("script"):
        try:
            from core.knowledge_base import _append_log
            _append_log({
                "event": "script_executed",
                "script": action_info["script"],
                "success": action_info.get("success", False),
                "exit_code": action_info.get("exit_code"),
                "errors": action_info.get("errors", [])[:3],
            })
        except Exception:
            pass


# ======================================================================
#  LECTURA DE TIPO DE MENSAJE
# ======================================================================

def _read_msg_type() -> dict:
    """Lee el tipo del ultimo mensaje del usuario."""
    try:
        if MSG_TYPE_FILE.exists():
            return json.loads(MSG_TYPE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"type": "instruction", "has_kb": False}


# ======================================================================
#  ITERATION TRACKING (delega a core.iteration_learn si existe)
# ======================================================================

def _run_iteration_tracking(input_data: dict, action_info: dict):
    """
    Delega al iteration_learn para tracking completo si el modulo existe.
    Si no existe, hace tracking inline basico con STATE_FILE y ACTIONS_LOG.
    """
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_result = str(input_data.get("tool_result", ""))
    exit_code = input_data.get("exit_code")
    session_id = input_data.get("session_id", "")

    # Intentar usar iteration_learn completo
    try:
        from core.iteration_learn import (
            _is_failure, search_kb_on_failure, extract_context,
            load_state, save_state, append_action, kb_save, detect_domain,
            write_notification, load_actions_for_session,
            _is_exploration, _is_action, _adaptive_explore_threshold,
            search_kb_for_territory, flush_pending, trim_actions_log,
        )

        # KB hint on failure
        if _is_failure(tool_name, tool_result, exit_code):
            hint = search_kb_on_failure(tool_name, tool_input, tool_result)
            if hint:
                sys.stdout.write(hint + "\n")
                sys.stdout.flush()

        state = load_state()
        action_record = extract_context(tool_name, tool_input, tool_result)

        # Exploration streak tracking
        if _is_exploration(tool_name):
            _read_now = time.time()
            _last_read = state.get("last_read_ts", 0)
            _gap = _read_now - _last_read if _last_read > 0 else 99.0
            state["last_read_ts"] = _read_now
            if _gap >= 2.0:
                state["explore_streak"] = state.get("explore_streak", 0) + 1
            fp_val = action_record.get("file", "")
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
            territory_hint = search_kb_for_territory(action_record, recent_files)
            if territory_hint:
                header = f"[MAPA KB -- {effective_threshold} explores sin actuar]:\n"
                sys.stdout.write(header + territory_hint + "\n")
                sys.stdout.flush()
            state["territory_searched"] = True

        now = time.time()

        if state.get("sid") != session_id:
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
                if saved:
                    state["exp_count"] = state.get("exp_count", 0) + 1
                    n = state["exp_count"]
                    sys.stdout.write(
                        f"\n  Iteracion Guardada  |  Experiencia ganada x{n}\n"
                    )
                    sys.stdout.flush()
            state["iteration"] = prev_iter + 1

        if state.get("iteration", 0) == 0:
            state["iteration"] = 1

        append_action(action_record, session_id, state["iteration"])
        state["last_ts"] = now
        save_state(state)

        if int(now) % 100 == 0:
            trim_actions_log()

        return  # iteration_learn handled everything

    except ImportError:
        pass  # iteration_learn no disponible, tracking inline basico

    # Fallback: tracking inline basico con STATE_FILE y ACTIONS_LOG
    try:
        now = time.time()
        state = {}
        if STATE_FILE.exists():
            try:
                state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                state = {}

        if state.get("sid") != session_id:
            state = {"sid": session_id, "iteration": 1, "last_ts": now}

        # Append action al log
        record = {
            "_sid": session_id,
            "_iter": state.get("iteration", 1),
            "tool": tool_name,
            "file": action_info.get("file", ""),
            "action": action_info.get("command", action_info.get("change_summary", ""))[:200],
            "success": action_info.get("success", True),
            "ts": now,
        }
        ACTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(ACTIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        state["last_ts"] = now
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    except Exception:
        pass


# ======================================================================
#  MAIN
# ======================================================================

def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    # Leer tipo de mensaje para decidir nivel de grabacion
    msg_ctx = _read_msg_type()
    msg_type = msg_ctx.get("type", "instruction")
    had_kb = msg_ctx.get("has_kb", False)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_output = str(input_data.get("tool_result", input_data.get("tool_output", "")))
    exit_code = input_data.get("exit_code")
    session_id = input_data.get("session_id", "")

    # Message-type-aware recording:
    # Si el mensaje fue solo informacional (pregunta pura sin ejecucion):
    # Solo registrar si hay error o KB busqueda fallida.
    # Excepcion: herramientas de modificacion (Edit/Write/Bash) siempre grabar.
    is_modifying_tool = tool_name in ("Edit", "Write", "Bash")
    should_record = (
        msg_type in ("instruction", "informing")
        or is_modifying_tool
        or (msg_type == "informational" and not had_kb)
    )

    if not should_record:
        sys.exit(0)

    # Solo ignorar los absolutamente triviales
    if tool_name == "Bash" and _is_trivial(tool_input.get("command", "")):
        sys.exit(0)

    # Extraer informacion clave
    action_info = _extract_key_info(tool_name, tool_input, tool_output, exit_code)

    # Guardar accion en log local
    _save_action(action_info)

    # Si hubo error, guardar como pendiente de resolucion
    if action_info.get("errors") and not action_info.get("success", True):
        _save_pending_error(action_info)

    # Si fue exitoso, verificar si resuelve un error pendiente
    _tool = action_info.get("tool", "")
    _is_success = action_info.get("success") and (
        action_info.get("has_success_indicator") or _tool in ("Edit", "Write")
    )
    if _is_success:
        _check_error_resolution(action_info)

    # Registrar acciones significativas en KB
    _register_significant_action(action_info)

    # Iteration tracking (delega a core.iteration_learn o inline)
    _run_iteration_tracking(input_data, action_info)

    sys.exit(0)


if __name__ == "__main__":
    main()
