#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
session_harvest.py - Feature 13: Session Harvest (Minar Transcripciones)
========================================================================
Extrae aprendizajes automaticos de transcripciones pasadas de Claude Code.
Analiza patrones como:
  - Errores que se resolvieron (error -> fix)
  - Comandos frecuentes
  - Archivos mas editados
  - Convenciones descubiertas
  - Preguntas repetidas (candidatas a KB)

Inspirado en: mcp-memory-service Session Harvest
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR

log = logging.getLogger("session_harvest")

HARVEST_FILE = DATA_DIR / "session_harvest_results.json"
HARVEST_METRICS_FILE = DATA_DIR / "session_harvest_metrics.json"

# Donde Claude Code guarda transcripciones
CLAUDE_SESSIONS_DIR = Path(os.environ.get(
    "CLAUDE_SESSIONS_DIR",
    Path.home() / "AppData" / "Local" / "ClaudeCode" / "sessions"
))


def find_session_files(max_files: int = 50) -> list[Path]:
    """Encuentra archivos de sesion/transcripcion de Claude Code."""
    session_files = []

    # Buscar en directorio de sesiones de Claude Code
    search_dirs = [
        CLAUDE_SESSIONS_DIR,
        Path.home() / ".claude" / "projects",
        Path(os.environ.get("APPDATA_LOCAL", Path.home() / "AppData" / "Local"))
        / "ClaudeCode" / ".claude" / "projects",
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        # Buscar .jsonl (transcripciones de Claude Code)
        for f in search_dir.rglob("*.jsonl"):
            if f.stat().st_size > 100:  # Ignorar archivos vacios
                session_files.append(f)
            if len(session_files) >= max_files:
                break
        if len(session_files) >= max_files:
            break

    # Ordenar por fecha de modificacion (mas recientes primero)
    session_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return session_files[:max_files]


def parse_session(file_path: Path) -> dict:
    """Parsea una transcripcion JSONL y extrae datos utiles."""
    messages = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    messages.append(msg)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        log.error(f"Error parsing {file_path}: {e}")
        return {"messages": [], "file": str(file_path)}

    return {
        "messages": messages,
        "file": str(file_path),
        "count": len(messages),
        "modified": datetime.fromtimestamp(
            file_path.stat().st_mtime, tz=timezone.utc
        ).isoformat(),
    }


def extract_error_fix_pairs(messages: list[dict]) -> list[dict]:
    """
    Extrae pares error->fix de la transcripcion.
    Busca patron: mensaje con error seguido de solucion.
    """
    pairs = []
    error_patterns = [
        r"(?i)(error|exception|traceback|failed|failure|crash|bug)",
        r"(?i)(no funciona|no sirve|fallo|rompio|broken)",
    ]

    for i, msg in enumerate(messages):
        content = _extract_content(msg)
        if not content:
            continue

        # Detectar errores
        is_error = any(re.search(p, content) for p in error_patterns)
        if not is_error:
            continue

        # Buscar la solucion en los siguientes 5 mensajes
        for j in range(i + 1, min(i + 6, len(messages))):
            fix_content = _extract_content(messages[j])
            if not fix_content:
                continue

            fix_indicators = [
                r"(?i)(fixed|solved|solution|resuelto|solucion|funciona|working)",
                r"(?i)(the fix|the issue was|el problema era|se arreglo)",
            ]
            is_fix = any(re.search(p, fix_content) for p in fix_indicators)
            if is_fix:
                pairs.append({
                    "error": content[:500],
                    "fix": fix_content[:500],
                    "gap": j - i,
                })
                break

    return pairs


def extract_frequent_commands(messages: list[dict]) -> dict:
    """Extrae comandos ejecutados frecuentemente."""
    commands = {}
    cmd_pattern = r'(?:bash|shell|terminal|cmd).*?[`"\'](.*?)[`"\']'

    for msg in messages:
        content = _extract_content(msg)
        if not content:
            continue

        # Buscar comandos en bloques de codigo
        code_blocks = re.findall(r'```(?:bash|sh|cmd)?\n(.*?)```', content, re.DOTALL)
        for block in code_blocks:
            for line in block.split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and len(line) > 3:
                    cmd_key = line[:100]
                    commands[cmd_key] = commands.get(cmd_key, 0) + 1

        # Buscar comandos inline
        inline_cmds = re.findall(r'`((?:pip|npm|git|python|cd|ls|cat|grep|docker)\s[^`]+)`', content)
        for cmd in inline_cmds:
            cmd_key = cmd[:100]
            commands[cmd_key] = commands.get(cmd_key, 0) + 1

    # Top 20 mas frecuentes
    sorted_cmds = sorted(commands.items(), key=lambda x: x[1], reverse=True)
    return {cmd: count for cmd, count in sorted_cmds[:20]}


def extract_edited_files(messages: list[dict]) -> dict:
    """Extrae archivos mas editados/mencionados."""
    files = {}
    file_patterns = [
        r'[\w/\\]+\.(?:py|js|ts|json|yaml|yml|md|txt|html|css|jsx|tsx)',
        r'(?:Edit|Write|Read)\s+(?:tool\s+)?(?:on\s+)?[`"]?([^`"\s]+\.\w{2,4})',
    ]

    for msg in messages:
        content = _extract_content(msg)
        if not content:
            continue

        for pattern in file_patterns:
            matches = re.findall(pattern, content)
            for m in matches:
                if isinstance(m, tuple):
                    m = m[0]
                m = m.strip("'\"`)( ")
                if len(m) > 3 and not m.startswith("http"):
                    files[m] = files.get(m, 0) + 1

    sorted_files = sorted(files.items(), key=lambda x: x[1], reverse=True)
    return {f: count for f, count in sorted_files[:30]}


def extract_repeated_questions(messages: list[dict]) -> list[dict]:
    """Detecta preguntas que se repiten (candidatas a KB)."""
    questions = {}

    for msg in messages:
        role = msg.get("role", msg.get("type", ""))
        if role not in ("user", "human"):
            continue

        content = _extract_content(msg)
        if not content or len(content) < 10:
            continue

        # Normalizar para detectar similares
        normalized = re.sub(r'\s+', ' ', content.lower().strip())[:200]
        if normalized in questions:
            questions[normalized]["count"] += 1
        else:
            questions[normalized] = {"question": content[:200], "count": 1}

    # Solo las repetidas (count > 1)
    repeated = [q for q in questions.values() if q["count"] > 1]
    repeated.sort(key=lambda x: x["count"], reverse=True)
    return repeated[:20]


def extract_conventions(messages: list[dict]) -> list[str]:
    """Detecta convenciones de codigo mencionadas."""
    conventions = set()
    convention_patterns = [
        r"(?i)(?:always|siempre|never|nunca|convention|convencion|rule|regla|standard)\s*:?\s*(.{10,100})",
        r"(?i)(?:we use|usamos|we prefer|preferimos)\s+(.{10,80})",
        r"(?i)(?:naming convention|estilo de codigo|code style)\s*:?\s*(.{10,80})",
    ]

    for msg in messages:
        content = _extract_content(msg)
        if not content:
            continue
        for pattern in convention_patterns:
            matches = re.findall(pattern, content)
            for m in matches:
                conventions.add(m.strip()[:100])

    return list(conventions)[:20]


def _extract_content(msg: dict) -> str:
    """Extrae texto de un mensaje (soporta varios formatos)."""
    if isinstance(msg, str):
        return msg

    content = msg.get("content", msg.get("text", msg.get("message", "")))
    if isinstance(content, list):
        # Formato con bloques [{"type": "text", "text": "..."}]
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return str(content) if content else ""


def harvest_sessions(max_sessions: int = 20) -> dict:
    """
    Ejecuta el harvest completo sobre las sesiones recientes.
    Returns: resumen de lo extraido.
    """
    files = find_session_files(max_sessions)
    if not files:
        return {"status": "no_sessions_found", "sessions": 0}

    all_error_fixes = []
    all_commands = {}
    all_files = {}
    all_questions = []
    all_conventions = []
    sessions_processed = 0

    for f in files:
        session = parse_session(f)
        messages = session.get("messages", [])
        if not messages:
            continue

        sessions_processed += 1

        # Extraer de cada sesion
        error_fixes = extract_error_fix_pairs(messages)
        all_error_fixes.extend(error_fixes)

        commands = extract_frequent_commands(messages)
        for cmd, count in commands.items():
            all_commands[cmd] = all_commands.get(cmd, 0) + count

        files_used = extract_edited_files(messages)
        for f_name, count in files_used.items():
            all_files[f_name] = all_files.get(f_name, 0) + count

        questions = extract_repeated_questions(messages)
        all_questions.extend(questions)

        conventions = extract_conventions(messages)
        all_conventions.extend(conventions)

    # Consolidar resultados
    result = {
        "harvested_at": datetime.now(timezone.utc).isoformat(),
        "sessions_processed": sessions_processed,
        "session_files": [str(f) for f in files[:5]],
        "error_fix_pairs": all_error_fixes[:50],
        "frequent_commands": dict(sorted(all_commands.items(), key=lambda x: x[1], reverse=True)[:30]),
        "frequently_edited_files": dict(sorted(all_files.items(), key=lambda x: x[1], reverse=True)[:30]),
        "repeated_questions": all_questions[:20],
        "conventions_detected": list(set(all_conventions))[:20],
        "summary": {
            "error_fixes_found": len(all_error_fixes),
            "unique_commands": len(all_commands),
            "unique_files": len(all_files),
            "repeated_questions": len([q for q in all_questions if q["count"] > 1]),
            "conventions": len(set(all_conventions)),
        },
    }

    # Guardar resultados
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HARVEST_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Guardar metricas
    metrics = {
        "last_harvest": result["harvested_at"],
        "sessions_processed": sessions_processed,
        "total_error_fixes": len(all_error_fixes),
        "total_conventions": len(set(all_conventions)),
    }
    HARVEST_METRICS_FILE.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return result


def auto_ingest_to_kb(harvest_result: dict) -> int:
    """Ingesta automatica de los hallazgos del harvest al KB."""
    ingested = 0

    try:
        from core.knowledge_base import add_pattern, add_fact

        # Ingestar error->fix pairs
        for pair in harvest_result.get("error_fix_pairs", [])[:20]:
            add_pattern(
                domain="learning",
                key=pair["error"][:200],
                solution=pair["fix"][:500],
                tags=["harvested", "error_fix"],
            )
            ingested += 1

        # Ingestar convenciones
        for conv in harvest_result.get("conventions_detected", [])[:10]:
            add_fact(
                domain="learning",
                key=f"convention: {conv[:100]}",
                fact=conv,
                tags=["harvested", "convention"],
            )
            ingested += 1

        # Ingestar preguntas repetidas como candidatas
        for q in harvest_result.get("repeated_questions", [])[:10]:
            if q["count"] >= 2:
                add_fact(
                    domain="learning",
                    key=f"frequent_question: {q['question'][:100]}",
                    fact=f"Asked {q['count']} times. Consider adding detailed answer to KB.",
                    tags=["harvested", "frequent_question"],
                )
                ingested += 1

    except Exception as e:
        log.error(f"Auto-ingest error: {e}")

    return ingested


def get_harvest_stats() -> dict:
    """Estadisticas para dashboard."""
    if HARVEST_METRICS_FILE.exists():
        try:
            return json.loads(HARVEST_METRICS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"sessions_processed": 0, "total_error_fixes": 0}


def get_last_harvest() -> dict | None:
    """Retorna el ultimo harvest completo."""
    if HARVEST_FILE.exists():
        try:
            return json.loads(HARVEST_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


# CLI
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"

    if cmd == "run":
        print("Harvesting sessions...")
        result = harvest_sessions()
        summary = result.get("summary", {})
        print(f"\nSessions processed: {result.get('sessions_processed', 0)}")
        print(f"Error->Fix pairs: {summary.get('error_fixes_found', 0)}")
        print(f"Unique commands: {summary.get('unique_commands', 0)}")
        print(f"Unique files: {summary.get('unique_files', 0)}")
        print(f"Repeated questions: {summary.get('repeated_questions', 0)}")
        print(f"Conventions: {summary.get('conventions', 0)}")

    elif cmd == "ingest":
        print("Harvesting + ingesting to KB...")
        result = harvest_sessions()
        n = auto_ingest_to_kb(result)
        print(f"Ingested: {n} items to KB")

    elif cmd == "stats":
        stats = get_harvest_stats()
        print(f"Last harvest: {stats.get('last_harvest', 'never')}")
        print(f"Sessions: {stats.get('sessions_processed', 0)}")
        print(f"Error fixes: {stats.get('total_error_fixes', 0)}")

    elif cmd == "files":
        files = find_session_files()
        print(f"Found {len(files)} session files:")
        for f in files[:10]:
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name} ({size_kb:.0f}KB)")

    else:
        print("Usage: session_harvest.py [run|ingest|stats|files]")
