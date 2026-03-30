# -*- coding: utf-8 -*-
"""
session_end.py -- Hook de fin de sesion
=======================================
Se dispara con el evento de fin de sesion del CLI.

RECIBE en stdin JSON con:
  - session_id
  - transcript_path
  - last_assistant_message
  - cwd
  - stop_hook_active (evitar loops)

Lo que captura:
  - Resumen DETALLADO de toda la conversacion (del transcript JSONL)
  - Errores encontrados y corregidos
  - Archivos tocados (read, edit, write)
  - Comandos ejecutados y resultados
  - Decisiones tecnicas
  - JSON de aprendizaje explicito
  - Trazas de razonamiento (texto antes de cada tool call)
  - Momentos episodicos (insights verbatim)
  - Pares conversacionales (pregunta/respuesta)

Guarda en:
  - session_history.json (historial de sesiones)
  - episodic_index.db (indice FTS5 para busqueda cross-sesion)
  - knowledge_base (patrones auto-aprendidos)
  - domain_cooccurrence.json + domain_markov.json (prediccion)

Fusion de Motor 1 (auto_learn_hook.py) + Motor 2 (session_end.py).
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
    SESSION_HISTORY_FILE, CO_OCCUR_FILE, MARKOV_FILE,
    INJECTION_FILE, HINT_EFFECT_FILE, DEBUG_LOG, ACTIONS_LOG,
    LAST_MSG_FILE, DATA_DIR,
)
from core.file_lock import file_lock

try:
    from core.knowledge_base import add_pattern, add_fact, _load_all_domains
    DOMAINS = _load_all_domains()
except ImportError:
    DOMAINS = {}


def debug_log(message: str):
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {message}\n")
    except Exception:
        pass


# ======================================================================
#  LECTURA DEL TRANSCRIPT JSONL
# ======================================================================

def read_transcript(transcript_path: str) -> list:
    """
    Lee el archivo JSONL del transcript completo.
    Soporta formato Claude Code (mensaje anidado) y formato directo.
    """
    messages = []
    path = Path(transcript_path)
    if not path.exists():
        return messages

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if "message" in obj and isinstance(obj["message"], dict):
                        inner = obj["message"]
                        if "role" in inner and "content" in inner:
                            messages.append(inner)
                    elif "role" in obj and "content" in obj:
                        messages.append(obj)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return messages


def extract_text_from_messages(messages: list) -> str:
    parts = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(f"[{role}] {content}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(f"[{role}] {block.get('text', '')}")
                    elif block.get("type") == "tool_use":
                        tool = block.get("name", "?")
                        tool_input = json.dumps(
                            block.get("input", {}), ensure_ascii=False
                        )[:300]
                        parts.append(f"[{role}/tool:{tool}] {tool_input}")
                    elif block.get("type") == "tool_result":
                        result_text = str(block.get("content", ""))[:500]
                        parts.append(f"[tool_result] {result_text}")
                elif isinstance(block, str):
                    parts.append(f"[{role}] {block}")
    return "\n".join(parts)


# ======================================================================
#  EXTRACCION DE INFORMACION
# ======================================================================

def extract_user_messages(messages: list) -> list:
    user_msgs = []
    system_prefixes = (
        "<task-notification", "<system-reminder", "<available-deferred-tools"
    )
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str) and len(content.strip()) > 3:
                text = content.strip()
                if not any(text.startswith(p) for p in system_prefixes):
                    user_msgs.append(text[:500])
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if len(text) > 3 and not any(
                            text.startswith(p) for p in system_prefixes
                        ):
                            user_msgs.append(text[:500])
    return user_msgs


def extract_tool_usage(messages: list) -> dict:
    tools = {
        "files_read": [],
        "files_edited": [],
        "files_created": [],
        "commands_run": [],
        "searches": [],
    }
    seen_read = set()
    seen_edit = set()
    seen_write = set()
    seen_cmds = set()

    for msg in messages:
        content = msg.get("content", "")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            tool_name = block.get("name", "")
            tool_input = block.get("input", {})

            if tool_name == "Read":
                fp = tool_input.get("file_path", "")
                if fp and fp not in seen_read:
                    seen_read.add(fp)
                    tools["files_read"].append(fp)
            elif tool_name == "Edit":
                fp = tool_input.get("file_path", "")
                if fp and fp not in seen_edit:
                    seen_edit.add(fp)
                    tools["files_edited"].append(fp)
            elif tool_name == "Write":
                fp = tool_input.get("file_path", "")
                if fp and fp not in seen_write:
                    seen_write.add(fp)
                    tools["files_created"].append(fp)
            elif tool_name == "Bash":
                cmd = tool_input.get("command", "")
                if cmd and cmd not in seen_cmds:
                    seen_cmds.add(cmd)
                    tools["commands_run"].append(cmd[:300])
            elif tool_name in ("Grep", "Glob"):
                pattern = tool_input.get("pattern", "")
                if pattern:
                    tools["searches"].append(f"{tool_name}: {pattern}")

    return tools


def extract_tool_usage_from_iter_actions(session_id: str) -> dict:
    """
    Fallback: lee ACTIONS_LOG (escrito por post_tool_use en tiempo real)
    y extrae tool usage para el session_id dado.
    Resuelve el timing bug donde el transcript no tiene tool_use blocks
    al momento en que el hook de fin de sesion dispara (sesiones cortas).
    """
    tools = {
        "files_read": [],
        "files_edited": [],
        "files_created": [],
        "commands_run": [],
        "searches": [],
    }
    if not ACTIONS_LOG.exists() or not session_id:
        return tools

    seen_read = set()
    seen_edit = set()
    seen_write = set()
    seen_cmds = set()

    try:
        with open(ACTIONS_LOG, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    a = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not a.get("_sid", "").startswith(session_id[:8]):
                    continue

                tool = a.get("tool", "")
                fp = a.get("file", "")
                cmd = a.get("action", "")

                if tool == "Read" and fp:
                    if fp not in seen_read:
                        seen_read.add(fp)
                        tools["files_read"].append(fp)
                elif tool == "Edit" and fp:
                    if fp not in seen_edit:
                        seen_edit.add(fp)
                        tools["files_edited"].append(fp)
                elif tool == "Write" and fp:
                    if fp not in seen_write:
                        seen_write.add(fp)
                        tools["files_created"].append(fp)
                elif tool == "Bash" and cmd:
                    short_cmd = cmd[:300]
                    if short_cmd not in seen_cmds:
                        seen_cmds.add(short_cmd)
                        tools["commands_run"].append(short_cmd)
                elif tool in ("Grep", "Glob") and cmd:
                    tools["searches"].append(cmd[:150])
    except Exception:
        pass

    return tools


def merge_tool_usage(from_transcript: dict, from_iter: dict) -> dict:
    """Fusiona tool usage del transcript con el de iter_actions (sin duplicados)."""
    return {
        "files_read": list(dict.fromkeys(
            from_transcript["files_read"] + from_iter["files_read"]
        )),
        "files_edited": list(dict.fromkeys(
            from_transcript["files_edited"] + from_iter["files_edited"]
        )),
        "files_created": list(dict.fromkeys(
            from_transcript["files_created"] + from_iter["files_created"]
        )),
        "commands_run": list(dict.fromkeys(
            from_transcript["commands_run"] + from_iter["commands_run"]
        )),
        "searches": list(dict.fromkeys(
            from_transcript["searches"] + from_iter["searches"]
        )),
    }


def extract_errors_from_messages(messages: list) -> list:
    errors = []
    TRIVIAL = [
        "no longer exists", "No tab available", "No task found",
        "unexpected EOF", "command not found", "charmap_encode",
        "tool_use_error", "Permission denied",
    ]
    for msg in messages:
        content = msg.get("content", "")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result" and block.get("is_error"):
                error_text = str(block.get("content", ""))[:400]
                if any(trivial in error_text for trivial in TRIVIAL):
                    continue
                errors.append({"type": "tool_error", "detail": error_text})
            if block.get("type") == "text":
                text = block.get("text", "")
                for match in re.findall(
                    r'(?:Error|Traceback|Failed|FAILED)[\s:]+(.{20,300})', text
                ):
                    detail = match.strip()[:300]
                    if any(trivial in detail for trivial in TRIVIAL):
                        continue
                    errors.append({"type": "error_in_response", "detail": detail})
    return errors[:10]


def extract_learning_json_from_messages(messages: list) -> dict:
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        patterns = [
            r'```json\s*(\{[^`]*?"status"[^`]*?\})\s*```',
            r'(\{[^{}]*"status"\s*:\s*"(?:success|modified|partial|failed)"[^{}]*\})',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match)
                    if "status" in data:
                        return data
                except json.JSONDecodeError:
                    continue
    return None


def extract_decisions_from_messages(messages: list) -> list:
    decisions = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        for match in re.findall(
            r'(?:voy a|decid[io]|el fix es|la soluci[on] es|the fix is|going to|'
            r'la estrategia es|recomiendo|mejor opci[on]|hay que|deber[io]amos)\s+(.{10,200})',
            text, re.IGNORECASE
        ):
            if match.strip() not in decisions:
                decisions.append(match.strip()[:200])
    return decisions[:15]


def build_conversation_summary(user_messages: list) -> str:
    if not user_messages:
        return "Sesion sin mensajes del usuario"
    real_msgs = []
    for msg in user_messages:
        if msg.startswith("This session is being continued"):
            continue
        if msg.startswith("Summary:"):
            continue
        if len(msg) > 400:
            msg = msg[:150] + "..."
        clean = msg.replace("\n", " ").strip()[:150]
        if clean:
            real_msgs.append(clean)
    if not real_msgs:
        return "Sesion sin mensajes del usuario"
    return " -> ".join(real_msgs[:8])[:600]


# ======================================================================
#  TRAZAS DE RAZONAMIENTO (texto antes de cada tool call)
# ======================================================================

def extract_reasoning_traces(messages: list) -> list:
    traces = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        pending_text = ""
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text", "").strip()
                if len(text) > 30:
                    pending_text = text
            elif block.get("type") == "tool_use" and pending_text:
                traces.append({
                    "reasoning": pending_text[:400],
                    "tool": block.get("name", "?"),
                    "action_summary": str(block.get("input", {}))[:120],
                })
                pending_text = ""
    return traces[:12]


# ======================================================================
#  MOMENTOS EPISODICOS VERBATIM
# ======================================================================

EPISODIC_SIGNALS = [
    r'(?:descubri que|encontre que|resulta que|la causa es|root cause|causa raiz)\s+(.{20,250})',
    r'(?:para la proxima vez|next time|recordar que|importante notar)\s*[:\-]?\s*(.{20,250})',
    r'(?:el problema era|el error fue|the issue was|el bug era)\s+(.{20,250})',
    r'(?:la solucion clave|key insight|insight clave|lo que funciono|lo que resolvio)\s*[:\-]?\s*(.{20,250})',
    r'(?:nunca usar|siempre usar|never use|always use)\s+(.{20,250})',
]


def extract_episodic_moments(messages: list) -> list:
    moments = []
    seen: set = set()
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        for pattern in EPISODIC_SIGNALS:
            for match in re.findall(pattern, text, re.IGNORECASE | re.DOTALL):
                clean = match.strip()[:250].replace("\n", " ")
                if len(clean) > 20 and clean not in seen:
                    seen.add(clean)
                    moments.append(clean)
    return moments[:8]


# ======================================================================
#  PARES CONVERSACIONALES
# ======================================================================

def extract_conversation_pairs(messages: list) -> list:
    pairs = []
    system_prefixes = (
        "<task-notification", "<system-reminder", "<available-deferred-tools"
    )
    current_user = None
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            text = ""
            if isinstance(content, str):
                text = content.strip()
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        text = b.get("text", "").strip()
                        break
            if text and len(text) > 5 and not any(
                text.startswith(p) for p in system_prefixes
            ):
                current_user = text[:300]
        elif role == "assistant" and current_user:
            assistant_text = ""
            files_touched = []
            if isinstance(content, str):
                assistant_text = content[:400]
            elif isinstance(content, list):
                text_parts = []
                for b in content:
                    if isinstance(b, dict):
                        if b.get("type") == "text":
                            text_parts.append(b.get("text", ""))
                        elif b.get("type") == "tool_use":
                            fp = b.get("input", {}).get("file_path", "")
                            if fp:
                                files_touched.append(Path(fp).name)
                assistant_text = " ".join(text_parts)[:400]
            if assistant_text and len(assistant_text) > 20:
                pairs.append({
                    "user": current_user,
                    "assistant": assistant_text,
                    "files": files_touched[:5],
                })
            current_user = None
    return pairs


# ======================================================================
#  SESSION HISTORY
# ======================================================================

def load_session_history() -> list:
    SESSION_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with file_lock("session_history"):
        if SESSION_HISTORY_FILE.exists():
            try:
                with open(SESSION_HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
    return []


def save_session_history(history: list):
    SESSION_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with file_lock("session_history"):
        tmp = SESSION_HISTORY_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        tmp.replace(SESSION_HISTORY_FILE)


def _merge_lists(existing: list, new: list) -> list:
    seen = set()
    merged = []
    for item in existing + new:
        if isinstance(item, dict):
            key = item.get("detail", item.get("type", str(item)))
        else:
            key = str(item)
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return merged


def _merge_sessions(existing: dict, new: dict) -> dict:
    merged = existing.copy()
    list_fields = [
        "user_messages", "files_read", "files_edited", "files_created",
        "commands_run", "searches", "errors", "decisions"
    ]
    for field in list_fields:
        old_list = existing.get(field, [])
        new_list = new.get(field, [])
        if new_list:
            merged[field] = _merge_lists(old_list, new_list)
    old_summary = existing.get("summary", "")
    new_summary = new.get("summary", "")
    if len(new_summary) > len(old_summary):
        merged["summary"] = new_summary
    if new.get("learning_json") and not existing.get("learning_json"):
        merged["learning_json"] = new["learning_json"]
    old_metrics = existing.get("metrics", {})
    new_metrics = new.get("metrics", {})
    merged_metrics = {}
    for key in set(list(old_metrics.keys()) + list(new_metrics.keys())):
        merged_metrics[key] = max(old_metrics.get(key, 0), new_metrics.get(key, 0))
    merged["metrics"] = merged_metrics
    merged["merged"] = True
    merged["merge_count"] = existing.get("merge_count", 1) + 1
    return merged


def find_existing_session(history: list, new_record: dict) -> int:
    new_id = new_record.get("session_id", "")
    new_date = new_record.get("date", "")
    new_msgs = set(m[:80] for m in new_record.get("user_messages", []))
    for i, existing in enumerate(history):
        existing_id = existing.get("session_id", "")
        clean_new = new_id.replace("manual_", "")
        clean_existing = existing_id.replace("manual_", "")
        if clean_new and clean_existing and clean_new == clean_existing:
            return i
        if new_date and existing.get("date", "") == new_date and new_msgs:
            existing_msgs = set(m[:80] for m in existing.get("user_messages", []))
            if existing_msgs:
                overlap = len(new_msgs & existing_msgs)
                total = max(len(new_msgs), len(existing_msgs))
                if total > 0 and overlap / total > 0.4:
                    return i
    return -1


def save_or_merge_session(new_record: dict):
    history = load_session_history()
    idx = find_existing_session(history, new_record)
    if idx >= 0:
        history[idx] = _merge_sessions(history[idx], new_record)
        debug_log(f"Session merged at index {idx}")
    else:
        history.append(new_record)
        debug_log(f"New session added. History: {len(history)} sessions")
    save_session_history(history)


# ======================================================================
#  REGISTRO EN KB
# ======================================================================

def register_learning_in_kb(learning: dict):
    """Registra JSON de aprendizaje explicito en la KB."""
    if not learning or not DOMAINS:
        return

    domain = learning.get("domain", "general")
    task_type = learning.get("task_type", "auto_learned")

    key = f"auto_{task_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    solution = {
        "strategy": learning.get("strategy", "auto_captured"),
        "code_snippet": learning.get("code_snippet", "")[:2000],
        "notes": learning.get("notes", ""),
        "auto_learned": True,
        "source": "hook_stop_event",
    }
    tags = learning.get("tags", [task_type, domain, "auto_learned"])

    try:
        add_pattern(domain, key, solution, tags=tags)
        debug_log(f"KB: registered explicit learning {key} in {domain}")
    except Exception as e:
        debug_log(f"KB: failed to register pattern: {e}")


# ======================================================================
#  DETECCION DE DOMINIOS
# ======================================================================

# Mapeo de archivos/paths a dominios de KB
_DOMAIN_FILE_HINTS = {
    "sap_": "sap_tierra", "sap_playbook": "sap_tierra",
    "brand_mirror": "files", "dashboard": "files",
    "index.html": "files", "knowledge_base": "files",
    "learning_memory": "files", "ingest_": "files",
    "sow": "sow", "bom": "bom", "monday": "monday",
    "outlook": "outlook", "pptx": "pptx", "hook": "files",
}

_DOMAIN_KW_HINTS = {
    "sap": "sap_tierra", "oportunidad": "sap_tierra", "quote": "sap_tierra",
    "sow": "sow", "propuesta": "sow", "contrato": "sow",
    "bom": "bom", "listado": "bom", "material": "bom",
    "monday": "monday", "pipeline": "monday",
    "outlook": "outlook", "correo": "outlook",
    "pdf": "files", "excel": "files", "script": "files",
}


def detect_domain_for_session(files_edited: list, files_created: list,
                               user_messages: list) -> str:
    """Detecta el dominio dominante de la sesion."""
    # Intento 1: domain_detector modular
    try:
        from core.domain_detector import detect_from_session
        record = {
            "files_edited": files_edited,
            "files_created": files_created,
            "user_messages": user_messages,
        }
        return detect_from_session(record)
    except (ImportError, Exception):
        pass

    # Fallback: inline
    all_files = files_edited + files_created
    domain_scores: dict = {}
    for f in all_files:
        f_lower = f.lower().replace("\\", "/")
        for hint, domain in _DOMAIN_FILE_HINTS.items():
            if hint in f_lower:
                domain_scores[domain] = domain_scores.get(domain, 0) + 1

    all_text = " ".join(user_messages).lower()
    for kw, domain in _DOMAIN_KW_HINTS.items():
        if kw in all_text:
            domain_scores[domain] = domain_scores.get(domain, 0) + 1

    if domain_scores:
        return max(domain_scores, key=domain_scores.get)
    return "general"


def detect_all_active_domains(files_edited: list, files_created: list,
                               user_messages: list) -> list:
    """Detecta TODOS los dominios activos en la sesion."""
    # Intento 1: domain_detector modular
    try:
        from core.domain_detector import detect_multi
        all_text = " ".join(
            user_messages +
            [Path(f).name for f in files_edited + files_created if f]
        )
        result = detect_multi(all_text, max_domains=5)
        if result:
            return result
    except (ImportError, Exception):
        pass

    # Fallback: inline
    all_files = files_edited + files_created
    domain_scores: dict = {}
    for f in all_files:
        f_lower = f.lower().replace("\\", "/")
        for hint, domain in _DOMAIN_FILE_HINTS.items():
            if hint in f_lower:
                domain_scores[domain] = domain_scores.get(domain, 0) + 1

    all_text = " ".join(user_messages).lower()
    for kw, domain in _DOMAIN_KW_HINTS.items():
        if kw in all_text:
            domain_scores[domain] = domain_scores.get(domain, 0) + 1

    return [d for d, s in domain_scores.items() if s > 0]


def detect_domains_in_order(files_edited: list, files_created: list,
                             user_messages: list) -> list:
    """Retorna dominios en orden de primera aparicion en la sesion."""
    # Intento 1: domain_detector modular
    try:
        from core.domain_detector import detect_multi, _extract_keywords, _load_domain_keywords
        domains_data = _load_domain_keywords()
        seen = []
        for f in files_edited + files_created:
            fname = Path(f).name.lower()
            for dname in domains_data:
                if dname in fname and dname not in seen:
                    seen.append(dname)
                    break
        all_text = " ".join(user_messages)
        kws = _extract_keywords(all_text)
        remaining = detect_multi(" ".join(kws))
        for d in remaining:
            if d not in seen:
                seen.append(d)
        if seen:
            return seen
    except (ImportError, Exception):
        pass

    # Fallback: inline
    seen = []
    for f in files_edited + files_created:
        f_lower = f.lower().replace("\\", "/")
        for hint, domain in _DOMAIN_FILE_HINTS.items():
            if hint in f_lower and domain not in seen:
                seen.append(domain)
                break
    all_text = " ".join(user_messages).lower()
    kw_order = [
        ("sap", "sap_tierra"), ("oportunidad", "sap_tierra"),
        ("sow", "sow"), ("propuesta", "sow"),
        ("bom", "bom"), ("listado", "bom"),
        ("monday", "monday"), ("pipeline", "monday"),
        ("outlook", "outlook"), ("correo", "outlook"),
        ("pdf", "files"), ("excel", "files"), ("script", "files"),
    ]
    for kw, domain in kw_order:
        if kw in all_text and domain not in seen:
            seen.append(domain)
    return seen


# ======================================================================
#  CO-OCURRENCIA + MARKOV
# ======================================================================

def record_domain_cooccurrence(domains: list):
    if len(domains) < 2:
        return
    try:
        CO_OCCUR_FILE.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if CO_OCCUR_FILE.exists():
            data = json.loads(CO_OCCUR_FILE.read_text(encoding="utf-8"))
        for d1 in domains:
            for d2 in domains:
                if d1 != d2:
                    data.setdefault(d1, {})[d2] = data.get(d1, {}).get(d2, 0) + 1
        CO_OCCUR_FILE.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        debug_log(f"Co-occurrence updated for domains: {domains}")
    except Exception as e:
        debug_log(f"Co-occurrence update failed: {e}")


def record_domain_sequence(domains_ordered: list):
    if len(domains_ordered) < 2:
        return
    try:
        MARKOV_FILE.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if MARKOV_FILE.exists():
            data = json.loads(MARKOV_FILE.read_text(encoding="utf-8"))
        for i in range(len(domains_ordered) - 1):
            d1 = domains_ordered[i]
            d2 = domains_ordered[i + 1]
            data.setdefault(d1, {})[d2] = data.get(d1, {}).get(d2, 0) + 1
        MARKOV_FILE.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        debug_log(f"Markov sequence: {' -> '.join(domains_ordered)}")
    except Exception as e:
        debug_log(f"Markov record failed: {e}")


# ======================================================================
#  AUTO-LEARNING
# ======================================================================

def auto_extract_learning(session_record: dict, messages: list = None) -> bool:
    """Extrae aprendizaje automatico de la sesion con contexto rico."""
    if not DOMAINS:
        debug_log("KB: DOMAINS not available, skipping auto-extract")
        return False

    files_edited = session_record.get("files_edited", [])
    files_created = session_record.get("files_created", [])
    user_messages = session_record.get("user_messages", [])
    decisions = session_record.get("decisions", [])
    errors = session_record.get("errors", [])
    summary = session_record.get("summary", "")

    if not files_edited and not files_created:
        debug_log("KB auto: no files edited/created, skipping")
        return False
    if len(user_messages) < 2:
        debug_log("KB auto: less than 2 user messages, skipping")
        return False

    domain = detect_domain_for_session(files_edited, files_created, user_messages)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    key = f"session_auto_{timestamp}"

    notes_parts = []

    # Trazas de razonamiento -- el PORQUE detras de cada accion
    if messages:
        reasoning = extract_reasoning_traces(messages)
        if reasoning:
            notes_parts.append("Razonamiento (texto antes de cada tool call):")
            for t in reasoning[:5]:
                tool = t.get("tool", "?")
                why = t.get("reasoning", "")[:200].replace("\n", " ")
                notes_parts.append(f"  [{tool}] {why}")

    # Momentos episodicos verbatim
    if messages:
        episodic = extract_episodic_moments(messages)
        if episodic:
            notes_parts.append("Momentos clave (verbatim):")
            for m in episodic[:5]:
                notes_parts.append(f"  {m}")
            try:
                add_fact("sessions", f"episodic_{timestamp}", {
                    "rule": "; ".join(episodic[:3]),
                    "applies_to": f"sesion {timestamp}, dominio {domain}",
                    "confidence": "observed",
                    "source": "auto_episodic_extraction",
                }, tags=["episodic", "auto-learned", domain])
                debug_log(f"KB episodic: {len(episodic)} moments saved")
            except Exception as ep_err:
                debug_log(f"KB episodic save failed: {ep_err}")

    # Pares conversacionales
    if messages:
        pairs = extract_conversation_pairs(messages)
        if pairs:
            notes_parts.append("Interacciones clave:")
            for p in pairs[-6:]:
                user_q = p["user"][:100].replace("\n", " ")
                assistant_a = p["assistant"][:150].replace("\n", " ")
                notes_parts.append(f"  P: {user_q}")
                notes_parts.append(f"  R: {assistant_a}")
                if p["files"]:
                    notes_parts.append(f"  Archivos: {', '.join(p['files'])}")

    if summary:
        notes_parts.append(f"Resumen: {summary[:200]}")
    if files_edited:
        notes_parts.append(
            f"Editados: {', '.join(Path(f).name for f in files_edited[:8])}"
        )
    if files_created:
        notes_parts.append(
            f"Creados: {', '.join(Path(f).name for f in files_created[:8])}"
        )
    if decisions:
        notes_parts.append(f"Decisiones: {'; '.join(decisions[:5])}")
    if errors:
        error_details = [e.get("detail", "")[:80] for e in errors[:3]]
        notes_parts.append(f"Errores resueltos: {'; '.join(error_details)}")

    solution = {
        "strategy": "auto_captured_from_session",
        "notes": "\n".join(notes_parts)[:2000],
        "auto_learned": True,
        "source": "hook_session_end",
        "files_touched": (files_edited + files_created)[:10],
        "domain_detected": domain,
    }
    tags = ["auto-learned", "session", domain]

    try:
        add_pattern(domain, key, solution, tags=tags)
        debug_log(f"KB auto: saved {key} in {domain}")
        return True
    except Exception as e:
        debug_log(f"KB auto: failed: {e}")
        return False


# ======================================================================
#  AUDIT DE EFECTIVIDAD DE HINTS
# ======================================================================

def audit_hint_usage(messages: list) -> dict:
    """Verifica si el CLI uso los patrones inyectados en esta sesion."""
    try:
        if not INJECTION_FILE.exists():
            return {}

        injection = json.loads(INJECTION_FILE.read_text(encoding="utf-8"))

        assistant_text = " ".join(
            b.get("text", "")
            for m in messages
            if m.get("role") == "assistant"
            for b in (m.get("content") if isinstance(m.get("content"), list) else [])
            if isinstance(b, dict) and b.get("type") == "text"
        ).lower()

        if not assistant_text:
            return {}

        keywords = injection.get("keywords", [])
        domains = injection.get("domains", [])
        intent = injection.get("intent", "general")

        used_kw = [k for k in keywords if k.lower() in assistant_text]
        used_dom = [d for d in domains if d.replace("_", " ") in assistant_text]
        usage_rate = len(used_kw) / max(len(keywords), 1)

        record = {
            "ts": datetime.now().isoformat(),
            "usage_rate": round(usage_rate, 2),
            "used_kw": used_kw,
            "ignored_dom": [d for d in domains if d not in used_dom],
            "intent": intent,
            "had_lm": injection.get("has_lm", False),
            "had_kb": injection.get("has_kb", False),
            "had_ep": injection.get("has_ep", False),
        }

        eff: dict = {}
        if HINT_EFFECT_FILE.exists():
            try:
                eff = json.loads(HINT_EFFECT_FILE.read_text(encoding="utf-8"))
            except Exception:
                eff = {}

        history = eff.get("history", [])
        history.append(record)
        history = history[-100:]
        avg = sum(h["usage_rate"] for h in history) / len(history)
        eff["history"] = history
        eff["avg_usage_rate"] = round(avg, 2)
        eff["sessions_count"] = len(history)
        eff["alert_low_usage"] = avg < 0.30 and len(history) >= 5

        HINT_EFFECT_FILE.write_text(
            json.dumps(eff, ensure_ascii=False), encoding="utf-8"
        )
        debug_log(f"Hint audit: usage_rate={usage_rate:.0%}")
        return record

    except Exception as e:
        debug_log(f"Hint audit failed: {e}")
        return {}


# ======================================================================
#  MAIN
# ======================================================================

def main():
    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)
    except (json.JSONDecodeError, Exception) as e:
        debug_log(f"STDIN parse error: {e}")
        sys.exit(0)

    debug_log(f"Hook session_end fired. Fields: {list(input_data.keys())}")

    # Evitar loops
    if input_data.get("stop_hook_active"):
        debug_log("stop_hook_active=True, skipping")
        sys.exit(0)

    session_id = input_data.get("session_id", "unknown")
    transcript_path = input_data.get("transcript_path", "")
    last_message = input_data.get("last_assistant_message", "")
    cwd = input_data.get("cwd", "")
    now = datetime.now(timezone.utc)

    debug_log(f"session_id={session_id}")
    debug_log(f"transcript_path={transcript_path}")

    # Leer transcript
    messages = []
    if transcript_path:
        messages = read_transcript(transcript_path)
        debug_log(f"Transcript: {len(messages)} messages loaded")

    if not messages and last_message:
        messages = [{"role": "assistant", "content": last_message}]

    if not messages:
        debug_log("No messages to process, exiting")
        sys.exit(0)

    # Extraer informacion
    user_messages = extract_user_messages(messages)
    tool_usage = extract_tool_usage(messages)
    errors = extract_errors_from_messages(messages)
    learning = extract_learning_json_from_messages(messages)
    decisions = extract_decisions_from_messages(messages)
    summary = build_conversation_summary(user_messages)

    # Fallback: si el transcript no tiene tools (timing bug en sesiones cortas),
    # leer desde ACTIONS_LOG que post_tool_use escribe en tiempo real
    transcript_tools_total = (
        len(tool_usage["files_read"]) + len(tool_usage["files_edited"])
        + len(tool_usage["files_created"]) + len(tool_usage["commands_run"])
    )
    if transcript_tools_total == 0:
        iter_tools = extract_tool_usage_from_iter_actions(session_id)
        iter_total = (
            len(iter_tools["files_read"]) + len(iter_tools["files_edited"])
            + len(iter_tools["files_created"]) + len(iter_tools["commands_run"])
        )
        if iter_total > 0:
            tool_usage = merge_tool_usage(tool_usage, iter_tools)
            debug_log(
                f"Tools fallback from iter_actions: {len(iter_tools['files_read'])} reads, "
                f"{len(iter_tools['files_edited'])} edits, "
                f"{len(iter_tools['commands_run'])} commands"
            )
    else:
        iter_tools = extract_tool_usage_from_iter_actions(session_id)
        tool_usage = merge_tool_usage(tool_usage, iter_tools)

    debug_log(f"Extracted: {len(user_messages)} user msgs, {len(errors)} errors")
    debug_log(
        f"Tools (final): {len(tool_usage['files_read'])} reads, "
        f"{len(tool_usage['files_edited'])} edits, "
        f"{len(tool_usage['commands_run'])} commands"
    )

    # Validacion
    total_extracted = (
        len(user_messages) + len(tool_usage['files_read'])
        + len(tool_usage['files_edited'])
        + len(tool_usage['commands_run'])
    )
    if len(messages) > 10 and total_extracted == 0:
        debug_log(
            "ALERTA: transcript tiene mensajes pero se extrajo 0. "
            "Revisar read_transcript() y formato del JSONL."
        )

    # Construir registro de sesion
    session_record = {
        "session_id": session_id,
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S UTC"),
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "cwd": cwd,
        "summary": summary,
        "user_messages": user_messages[:50],
        "files_read": tool_usage["files_read"][:30],
        "files_edited": tool_usage["files_edited"][:30],
        "files_created": tool_usage["files_created"][:30],
        "commands_run": tool_usage["commands_run"][:30],
        "searches": tool_usage["searches"][:20],
        "errors": errors,
        "decisions": decisions,
        "learning_json": learning,
        "reasoning_traces": extract_reasoning_traces(messages) if messages else [],
        "metrics": {
            "total_messages": len(messages),
            "user_messages": len(user_messages),
            "errors_count": len(errors),
            "files_touched": (
                len(tool_usage["files_read"])
                + len(tool_usage["files_edited"])
                + len(tool_usage["files_created"])
            ),
            "commands_count": len(tool_usage["commands_run"]),
            "decisions_count": len(decisions),
        },
    }

    # Detectar dominios ANTES de guardar
    active_domains = detect_all_active_domains(
        tool_usage["files_edited"], tool_usage["files_created"], user_messages
    )
    domain = detect_domain_for_session(
        tool_usage["files_edited"], tool_usage["files_created"], user_messages
    )
    session_record["domains"] = active_domains if active_domains else [domain]

    # Guardar o mergear session history
    try:
        save_or_merge_session(session_record)
    except Exception as e:
        debug_log(f"Failed to save/merge session: {e}")

    # Registrar aprendizaje explicito en KB
    if learning and learning.get("status") in ("success", "partial", "modified"):
        register_learning_in_kb(learning)
        debug_log("KB: explicit learning JSON registered")

    # Actualizar co-ocurrencia y Markov si hay 2+ dominios
    if len(active_domains) >= 2:
        record_domain_cooccurrence(active_domains)
        ordered_domains = detect_domains_in_order(
            tool_usage["files_edited"], tool_usage["files_created"], user_messages
        )
        record_domain_sequence(ordered_domains)

    # Auto-extraer aprendizaje
    auto_saved = auto_extract_learning(session_record, messages=messages)
    if auto_saved:
        debug_log("KB: auto-learning extracted and saved")

    # Flush iteracion pendiente
    try:
        from core.iteration_learn import flush_pending
        flushed = flush_pending()
        if flushed:
            debug_log("KB: flushed pending iteration")
    except (ImportError, Exception) as e:
        debug_log(f"KB: flush attempt: {e}")

    # Indexar en FTS5 (episodic_index)
    try:
        from core.episodic_index import index_session as ep_index
        ep_index(session_record)
        debug_log("Episodic FTS5: session indexed")
    except Exception as e:
        debug_log(f"Episodic FTS5 index failed: {e}")

    # Audit de hints
    if messages:
        audit_record = audit_hint_usage(messages)
        if audit_record:
            rate = audit_record.get("usage_rate", 0)
            debug_log(f"Hint effectiveness: {rate:.0%} usage rate this session")

    # ── ENGRAM GAPS: nuevas capas de memoria ──────────────────────────
    # 1) Feedback loop: puntuar hints inyectados contra el transcript
    try:
        from core.hint_tracker import score_injection
        full_text = extract_text_from_messages(messages)
        score_injection(session_id, full_text)
        debug_log("HintTracker: injection effectiveness scored")
    except Exception as e:
        debug_log(f"HintTracker: {e}")

    # 2) Auto-pruning de patrones de baja calidad (cada sesion)
    try:
        from core.memory_pruner import auto_prune
        prune_result = auto_prune()
        if prune_result.get("pruned", 0) > 0:
            debug_log(f"MemoryPruner: {prune_result['pruned']} patrones podados")
    except Exception as e:
        debug_log(f"MemoryPruner: {e}")

    # 3) Consolidacion periodica (cada 10 sesiones aprox.)
    try:
        import random
        if random.random() < 0.10:  # ~10% de sesiones
            from core.memory_consolidator import consolidate
            cons_result = consolidate()
            if cons_result.get("consolidated", 0) > 0:
                debug_log(f"Consolidator: {cons_result['consolidated']} grupos consolidados")
    except Exception as e:
        debug_log(f"Consolidator: {e}")

    # 4) Limpiar working memory al cerrar sesion
    try:
        from core.working_memory import wm_clear
        wm_clear(session_id=session_id)
        debug_log("WorkingMemory: cleared for next session")
    except Exception as e:
        debug_log(f"WorkingMemory clear: {e}")
    # ─────────────────────────────────────────────────────────────────

    # Limpiar archivos de crash recovery
    for fpath in [LAST_MSG_FILE]:
        try:
            if fpath.exists():
                fpath.unlink()
        except Exception:
            pass

    debug_log("Hook session_end completed successfully")
    sys.exit(0)


if __name__ == "__main__":
    main()
