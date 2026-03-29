# -*- coding: utf-8 -*-
"""
session_start.py -- Hook SessionStart: inyecta contexto completo al iniciar sesion
===================================================================================
Se ejecuta AUTOMATICAMENTE al iniciar cualquier sesion del CLI.
Su stdout se inyecta directamente en el contexto.

CARGA:
1. CRASH RECOVERY -- acciones no guardadas de sesion anterior
2. ULTIMA SESION -- resumen detallado (que se hizo, errores, soluciones)
3. HISTORIAL -- ultimas 10 sesiones en resumen compacto
4. LEARNING MEMORY -- patrones aprendidos mas relevantes
5. KB INDEX -- indice de dominios disponibles (lazy-load)
6. MEMORIA CROSS-SESION -- sesiones previas relevantes al ultimo mensaje
7. INSTRUCCIONES -- como usar este contexto

Fusion de Motor 1 (session_start_kb.py) + Motor 2 (session_start.py).
"""

import sys
import json
import re
import time
from pathlib import Path
from datetime import datetime, timedelta

# -- path setup: parent = Motor_IA root
_MOTOR_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_MOTOR_DIR))

from config import (
    SESSION_HISTORY_FILE, LAST_MSG_FILE, STATE_FILE, ACTIONS_LOG,
    DATA_DIR, HOOK_STATE_DIR,
)

RECENT_HOURS = 1  # Ventana de contexto: ultima hora de trabajo


# ======================================================================
#  UTILIDADES DE HISTORIAL
# ======================================================================

def filter_recent_sessions(history: list) -> list:
    """
    Filtra sesiones de la ultima hora.
    Los registros se guardan en UTC (campo time: "HH:MM:SS UTC").
    Si no hay nada reciente, devuelve la ultima sesion para mantener continuidad.
    """
    from datetime import timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RECENT_HOURS)
    recent = []
    for s in history:
        try:
            raw = f"{s.get('date', '')} {s.get('time', '')}".replace(" UTC", "").strip()
            dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                recent.append(s)
        except Exception:
            pass
    if not recent and history:
        recent = [history[-1]]
    return recent


def load_session_history() -> list:
    if SESSION_HISTORY_FILE.exists():
        try:
            with open(SESSION_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


# ======================================================================
#  FORMATEO DE LA ULTIMA SESION (detalle accionable)
# ======================================================================

def format_last_session(session: dict) -> list:
    """Formatea la ultima sesion con detalle ACCIONABLE."""
    lines = []
    lines.append("=" * 60)
    lines.append("  >>> ULTIMA SESION <<<")
    lines.append("=" * 60)
    lines.append(f"  Fecha: {session.get('date', '?')} {session.get('time', '?')}")
    lines.append("")

    # Resumen
    summary = session.get("summary", "")
    if summary and "sin mensajes" not in summary.lower():
        lines.append(f"  RESUMEN: {summary[:600]}")
        lines.append("")

    # Que pidio el usuario
    user_msgs = session.get("user_messages", []) or session.get("user_requests", [])
    if user_msgs:
        lines.append("  LO QUE SE PIDIO:")
        for r in user_msgs[:10]:
            lines.append(f"    - {r[:200]}")
        lines.append("")

    # Archivos tocados (campos directos + formato viejo anidado)
    files_edited = session.get("files_edited", [])
    files_created = session.get("files_created", [])
    actions = session.get("actions_taken", {})
    if not files_edited:
        files_edited = actions.get("files_edited", [])
    if not files_created:
        files_created = actions.get("files_created", [])

    if files_edited:
        lines.append("  ARCHIVOS EDITADOS:")
        for f in files_edited[:15]:
            lines.append(f"    * {f}")
        lines.append("")
    if files_created:
        lines.append("  ARCHIVOS CREADOS:")
        for f in files_created[:10]:
            lines.append(f"    + {f}")
        lines.append("")

    # Decisiones tecnicas -- muy valiosas para continuidad
    decisions = session.get("decisions", [])
    if decisions:
        lines.append("  DECISIONES TECNICAS (por que se hizo asi):")
        for d in decisions[:10]:
            lines.append(f"    >> {d[:250]}")
        lines.append("")

    # Errores encontrados
    errors = session.get("errors", [])
    if errors:
        lines.append("  ERRORES Y SOLUCIONES:")
        for e in errors[:8]:
            lines.append(f"    [{e.get('type', '?')}] {e.get('detail', '')[:300]}")
        lines.append("")

    # Aprendizaje explicito (JSON que Claude imprime al final)
    learning = session.get("learning_json") or session.get("learning_captured", {})
    if isinstance(learning, dict) and learning.get("explicit_json"):
        learning = learning["explicit_json"]
    if isinstance(learning, dict) and learning.get("status"):
        lines.append("  APRENDIZAJE REGISTRADO:")
        lines.append(f"    Tipo: {learning.get('task_type', '?')}")
        lines.append(f"    Estrategia: {learning.get('strategy', '?')}")
        if learning.get("notes"):
            lines.append(f"    Notas: {learning['notes'][:400]}")
        if learning.get("business_rules_applied"):
            lines.append(f"    Reglas aplicadas: {', '.join(learning['business_rules_applied'])}")
        lines.append("")

    # Metricas
    metrics = session.get("metrics", {})
    if metrics and metrics.get("total_messages", 0) > 0:
        lines.append(
            f"  METRICAS: {metrics.get('user_messages', 0)} msgs, "
            f"{metrics.get('files_touched', 0)} archivos, "
            f"{metrics.get('commands_count', 0)} comandos, "
            f"{metrics.get('errors_count', 0)} errores"
        )
        lines.append("")

    return lines


# ======================================================================
#  HISTORIAL COMPACTO
# ======================================================================

def format_session_history(history: list) -> list:
    """Formatea el historial en formato compacto. Solo sesiones con contenido real."""
    lines = []
    if len(history) <= 1:
        return lines

    lines.append("-" * 60)
    lines.append("  HISTORIAL SESIONES ANTERIORES")
    lines.append("-" * 60)

    older = history[:-1][-10:]
    shown = 0
    for s in reversed(older):
        metrics = s.get("metrics", {})
        if metrics.get("total_messages", 0) < 5 and metrics.get("user_messages", 0) == 0:
            continue

        date = s.get("date", "?")
        time_str = s.get("time", "?")
        summary = s.get("summary", "")[:200]
        user_msgs = s.get("user_messages", []) or s.get("user_requests", [])
        req_text = "; ".join(r[:80] for r in user_msgs[:3]) if user_msgs else ""
        files_edited = s.get("files_edited", [])
        decisions = s.get("decisions", [])
        errors = s.get("errors", [])

        lines.append(f"  [{date} {time_str}]")
        if summary and "sin mensajes" not in summary.lower():
            lines.append(f"    {summary}")
        if req_text:
            lines.append(f"    Pidio: {req_text}")
        if files_edited:
            lines.append(f"    Edito: {', '.join(Path(f).name for f in files_edited[:5])}")
        if decisions:
            lines.append(f"    Decidio: {'; '.join(d[:80] for d in decisions[:2])}")
        if errors:
            lines.append(f"    Errores: {'; '.join(e.get('detail','')[:80] for e in errors[:2])}")
        lines.append("")
        shown += 1

    if shown == 0:
        lines.append("  (Sin sesiones anteriores con contenido)")
        lines.append("")

    return lines


# ======================================================================
#  LEARNING MEMORY
# ======================================================================

def format_learning_memory() -> list:
    """Exporta los patrones de learning memory."""
    lines = []
    try:
        from core.learning_memory import export_for_context, get_stats
        lm_stats = get_stats()
        total_p = lm_stats.get("total_patterns", 0)
        total_r = lm_stats.get("total_reuses", 0)
        avg_sr = lm_stats.get("avg_success_rate", 0)

        lines.append("-" * 60)
        lines.append(
            f"  LEARNING MEMORY -- {total_p} patrones, "
            f"{total_r} reusos, {avg_sr*100:.0f}% exito"
        )
        lines.append("-" * 60)

        if total_p > 0:
            by_type = lm_stats.get("patterns_by_type", {})
            lines.append(f"  Distribucion: {json.dumps(by_type, ensure_ascii=False)}")
            lines.append("")
            export = export_for_context(limit=5)
            if export and "No hay patrones" not in export:
                lines.append(export)
        lines.append("")
    except Exception as e:
        lines.append(f"  Learning Memory: error cargando ({e})")
        lines.append("")

    return lines


# ======================================================================
#  KB INDEX (lazy-load)
# ======================================================================

def format_kb_index() -> list:
    """Muestra indice de dominios con conteo de entries (lazy-load)."""
    lines = []
    try:
        from core.knowledge_base import _load_all_domains, _load_domain

        lines.append("-" * 60)
        lines.append("  KNOWLEDGE BASE -- Indice (lazy-load)")
        lines.append("-" * 60)
        lines.append("  Para buscar: python core/knowledge_base.py export --query \"<tema>\"")
        lines.append("  Cross-domain: python core/knowledge_base.py cross-search --query \"<tema>\"")
        lines.append("")

        all_domains = _load_all_domains()
        total = 0
        for domain_name, domain_info in all_domains.items():
            data = _load_domain(domain_name)
            entries = data.get("entries", {})
            count = len(entries)
            if count == 0:
                continue
            desc = domain_info.get("description", "")[:60]
            lines.append(f"  [{domain_name.upper()}] {count} entries -- {desc}")
            total += count

        if total > 0:
            lines.append("")
            lines.append(f"  TOTAL en disco: {total} entries (buscar on-demand)")
        lines.append("")

    except Exception as e:
        lines.append(f"  KB index: error ({e})")
        lines.append("")

    return lines


# ======================================================================
#  CRASH RECOVERY (fusion Motor 1 + Motor 2)
# ======================================================================

def recover_crashed_session() -> list:
    """
    Detecta si la sesion anterior termino sin guardar (crash).
    Compara el timestamp de STATE_FILE con la ultima entrada en session_history.
    Si STATE_FILE es mas reciente, recupera las acciones del ACTIONS_LOG.
    Guarda la sesion recuperada en session_history para no perder el trabajo.
    """
    try:
        if not STATE_FILE.exists() or not ACTIONS_LOG.exists():
            return []

        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        old_sid = state.get("sid", "")
        last_ts = state.get("last_ts", 0)

        if not old_sid or not last_ts:
            return []

        # Solo crash relevante si fue en las ultimas 24h
        if time.time() - last_ts > 86400:
            return []

        # Verificar si ya fue guardado normalmente en session_history
        history = load_session_history()
        if history:
            last_saved = history[-1]
            try:
                raw_dt = f"{last_saved.get('date', '')} {last_saved.get('time', '')}".replace(" UTC", "").strip()
                saved_dt = datetime.strptime(raw_dt, "%Y-%m-%d %H:%M:%S")
                state_dt = datetime.fromtimestamp(last_ts)
                if saved_dt >= state_dt:
                    return []  # Se guardo correctamente
            except Exception:
                pass

        # Leer acciones no guardadas del ACTIONS_LOG
        recovered = []
        try:
            with open(ACTIONS_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        a = json.loads(line)
                        if a.get("_sid") == old_sid:
                            recovered.append(a)
                    except Exception:
                        pass
        except Exception:
            return []

        if not recovered:
            return []

        # Construir resumen de la sesion recuperada
        files_touched = list(set(a.get("file", "") for a in recovered if a.get("file")))
        tools_used = [a.get("tool", "") for a in recovered]
        last_actions = [a.get("action", "") for a in recovered[-5:] if a.get("action")]

        lines = []
        lines.append("  [SESION RECUPERADA - crash detectado]:")
        lines.append(f"  {len(recovered)} acciones de la sesion anterior no fueron guardadas.")
        if files_touched:
            lines.append(
                f"  Archivos trabajados: {', '.join(Path(f).name for f in files_touched[:8])}"
            )
        if last_actions:
            lines.append("  Ultimas acciones antes del crash:")
            for a in last_actions:
                lines.append(f"    - {a[:120]}")
        lines.append("")

        # Guardar como sesion recuperada en session_history para no perder el trabajo
        recovery_entry = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M:%S"),
            "summary": f"[RECUPERADA] {len(recovered)} acciones de sesion que termino sin guardar",
            "user_messages": [],
            "files_edited": [a.get("file", "") for a in recovered if a.get("tool") == "Edit" and a.get("file")],
            "files_created": [a.get("file", "") for a in recovered if a.get("tool") == "Write" and a.get("file")],
            "errors": [],
            "decisions": [],
            "metrics": {
                "total_messages": len(recovered),
                "user_messages": 0,
                "files_touched": len(files_touched),
                "commands_count": sum(1 for t in tools_used if t == "Bash"),
                "errors_count": 0,
            },
            "_recovered": True,
            "_original_sid": old_sid,
        }
        history.append(recovery_entry)
        try:
            SESSION_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            SESSION_HISTORY_FILE.write_text(
                json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

        # Marcar STATE_FILE como procesado para no recuperar dos veces
        state["_recovered"] = True
        try:
            STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        return lines

    except Exception:
        return []


# ======================================================================
#  MAIN
# ======================================================================

def main():
    lines = []

    # ---- HEADER ----
    lines.append("=" * 60)
    lines.append("  MOTOR_IA -- Contexto automatico (ultima hora)")
    lines.append("=" * 60)
    lines.append("")

    # ---- 0) CRASH RECOVERY ----
    crash_lines = []

    # Recuperar acciones del JSONL si la sesion anterior crasheo
    recovered = recover_crashed_session()
    if recovered:
        crash_lines.extend(recovered)

    # Ultimo mensaje del usuario y ultima accion de Claude
    if LAST_MSG_FILE.exists():
        try:
            content = LAST_MSG_FILE.read_text(encoding="utf-8").strip()
            if content:
                msg_text = "\n".join(content.split("\n")[1:]).strip()
                if msg_text:
                    crash_lines.append(f"  Tu ultimo mensaje: {msg_text[:300]}")
        except Exception:
            pass

    last_action_file = DATA_DIR / "last_claude_action.txt"
    if last_action_file.exists():
        try:
            content = last_action_file.read_text(encoding="utf-8").strip()
            if content:
                action_lines = content.split("\n")
                crash_lines.append(f"  Yo estaba en: {action_lines[0]}")
                for al in action_lines[1:]:
                    crash_lines.append(f"    {al.strip()}")
        except Exception:
            pass

    if crash_lines:
        lines.append("  >>> CRASH RECOVERY <<<")
        lines.extend(crash_lines)
        lines.append("")

    # ---- 1) SESIONES RECIENTES ----
    history = load_session_history()
    recent = filter_recent_sessions(history) if history else []

    if recent:
        last = recent[-1]

        # Health check de captura
        last_metrics = last.get("metrics", {})
        last_total_msgs = last_metrics.get("total_messages", 0)
        last_user_msgs = last_metrics.get("user_messages", 0)
        last_files = last_metrics.get("files_touched", 0)
        last_cmds = last_metrics.get("commands_count", 0)
        last_extracted = last_user_msgs + last_files + last_cmds

        if last_total_msgs > 10 and last_extracted == 0:
            lines.append("!" * 60)
            lines.append("  HOOK HEALTH CHECK: FALLO DE CAPTURA")
            lines.append(
                f"  Sesion anterior: {last_total_msgs} msgs pero "
                "0 capturados. Revisar hooks/session_end.py"
            )
            lines.append("!" * 60)
            lines.append("")
        elif last_total_msgs > 5:
            lines.append(
                f"  [Hook OK | {last_user_msgs} msgs, "
                f"{last_files} archivos, {last_cmds} cmds]"
            )
            lines.append("")

        # Detalle de la ultima sesion
        lines.extend(format_last_session(last))

        # Sesiones anteriores dentro de la ultima hora (max 3)
        if len(recent) > 1:
            older = recent[:-1][-3:]
            lines.append("-" * 60)
            lines.append(f"  SESIONES ANTERIORES (ultima hora: {len(older)} sesiones)")
            lines.append("-" * 60)
            for s in reversed(older):
                date = s.get("date", "?")
                time_s = s.get("time", "?")
                summary = s.get("summary", "")[:150]
                errors = s.get("errors", [])
                lines.append(f"  [{date} {time_s}] {summary}")
                if errors:
                    lines.append(
                        f"    Errores: {'; '.join(e.get('detail','')[:80] for e in errors[:2])}"
                    )
            lines.append("")
    else:
        lines.append("  [Sin sesiones en la ultima hora]")
        lines.append("")

    # ---- 2) PATRONES APRENDIDOS ----
    lines.extend(format_learning_memory())

    # ---- 3) KB INDEX ----
    lines.extend(format_kb_index())

    # ---- 4) INSTRUCCIONES ----
    lines.append("=" * 60)
    lines.append("  INSTRUCCIONES -- LEER ANTES DE CADA TAREA")
    lines.append("=" * 60)
    lines.append("  1. El contexto de arriba es tu memoria reciente (ultima hora).")
    lines.append("  2. Al recibir cada tarea, experiencia relevante ya viene inyectada.")
    lines.append("  3. NO repitas errores previos: los patrones muestran que fallo antes.")
    lines.append("  4. Regla mid-execution: si encuentras algo nuevo no en tu contexto,")
    lines.append("     PRIMERO consulta el KB local antes de usar tu entrenamiento:")
    lines.append("       python core/knowledge_base.py export --query \"<tema>\"")
    lines.append("  5. Al resolver algo nuevo, quedara guardado automaticamente.")
    lines.append("")
    lines.append("  PROTOCOLO ANTI-COMPACTION:")
    lines.append("  Si detectas que el contexto fue comprimido/compactado:")
    lines.append("  a) Ejecutar: python core/learning_memory.py export")
    lines.append("  b) Ejecutar: python core/knowledge_base.py cross-search --query \"ultimo trabajo\"")
    lines.append("  c) Leer session_history.json para ultimas sesiones.")
    lines.append("  d) Recien despues de recuperar contexto, continuar el trabajo.")
    lines.append("=" * 60)

    # ---- 5) MEMORIA CROSS-SESION ----
    try:
        if LAST_MSG_FILE.exists():
            last_msg_text = LAST_MSG_FILE.read_text(encoding="utf-8").strip()
            msg_lines = last_msg_text.split("\n")
            msg_body = " ".join(msg_lines[1:]) if len(msg_lines) > 1 else last_msg_text
            kws = re.findall(r'\b[a-zA-Z]{4,}\b', msg_body.lower())
            query = " ".join(kws[:6])
            if query:
                from core.episodic_index import search as ep_search
                cross_results = ep_search(query, limit=3)
                if cross_results:
                    lines.append("-" * 60)
                    lines.append("  MEMORIA CROSS-SESION -- sesiones previas relevantes")
                    lines.append("-" * 60)
                    for r in cross_results:
                        d = r.get("date", "?")
                        dom = r.get("domain", "?")
                        s = r.get("summary", "")[:150]
                        snip = r.get("snippet", "")[:120]
                        lines.append(f"  [{d}/{dom}] {s}")
                        if snip:
                            lines.append(f"    ...{snip}...")
                    lines.append("")
    except Exception:
        pass

    # -- Output a stdout
    output = "\n".join(lines)
    sys.stdout.buffer.write(output.encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(b"\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
