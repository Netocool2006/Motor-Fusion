# -*- coding: utf-8 -*-
"""
episodic_index.py -- Memoria episodica cross-sesion con SQLite FTS5
===================================================================
Indexa session_history.json en SQLite FTS5 para busqueda full-text
de sesiones anteriores por keywords.

API publica:
  index_session(record)    -- indexa/actualiza una sesion
  search(query, limit=3)   -- FTS5 search, retorna [{date, domain, snippet}]
  rebuild_from_history()   -- reconstruye desde session_history.json
  get_stats()              -- estadisticas del indice

Usado por:
  on_user_message hook  -> search()        (inyecta contexto de sesiones pasadas)
  auto_learn hook       -> index_session() (indexa al cerrar cada sesion)
"""

import json
import sqlite3
import re
from pathlib import Path
from datetime import datetime

from config import EPISODIC_DB, SESSION_HISTORY_FILE


# -- Conexion y esquema --------------------------------------------------------

def _connect() -> sqlite3.Connection:
    EPISODIC_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(EPISODIC_DB))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection):
    """
    Tabla FTS5 standalone (almacena su propio contenido).
    Mas simple y confiable que content= mode con triggers.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions_meta (
            session_id  TEXT PRIMARY KEY,
            date        TEXT,
            domain      TEXT,
            body        TEXT,
            indexed_at  TEXT
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts
        USING fts5(session_id, date, domain, body, tokenize='unicode61');
    """)
    conn.commit()


# -- Construccion del texto indexable ------------------------------------------

def _build_body(record: dict) -> str:
    """
    Construye el texto indexable de una sesion combinando todos los campos
    relevantes: summary, mensajes de usuario, decisiones, errores, archivos.
    """
    parts = []

    summary = record.get("summary", "")
    if summary:
        parts.append(summary[:400])

    skip_prefixes = (
        "This session is being continued", "Summary:", "<task-notification",
        "<system-reminder", "<available-deferred-tools",
    )
    for msg in record.get("user_messages", [])[:20]:
        if isinstance(msg, str) and msg.strip():
            m = msg.strip()
            if len(m) > 3 and not any(m.startswith(p) for p in skip_prefixes):
                parts.append(m[:200])

    for dec in record.get("decisions", [])[:10]:
        if isinstance(dec, str):
            parts.append(dec[:150])

    for err in record.get("errors", [])[:5]:
        if isinstance(err, dict):
            d = err.get("detail", "")
            if d:
                parts.append(d[:150])
        elif isinstance(err, str) and err:
            parts.append(err[:150])

    for f in list(record.get("files_edited", []))[:10] + list(record.get("files_created", []))[:10]:
        if f:
            parts.append(Path(f).name)

    cwd = record.get("cwd", "")
    if cwd:
        parts.append(Path(cwd).name)

    return " | ".join(p for p in parts if p.strip())[:3000]


def _load_domain_keywords_map() -> list:
    """
    Carga el mapa keyword->dominio desde domains.json.
    Retorna lista de (keyword, domain_name) ordenada para matching.
    """
    if not SESSION_HISTORY_FILE.parent.exists():
        return []
    domains_file = SESSION_HISTORY_FILE.parent / "knowledge" / "domains.json"
    if not domains_file.exists():
        return []
    try:
        data = json.loads(domains_file.read_text(encoding="utf-8"))
        pairs = []
        for domain_name, domain_info in data.items():
            for kw in domain_info.get("keywords", []):
                pairs.append((kw.lower(), domain_name))
        return pairs
    except Exception:
        return []


def _detect_domain(record: dict) -> str:
    """Extrae el dominio dominante del registro usando keywords de domains.json."""
    domain = record.get("domain", "")
    if domain:
        return domain
    text = " ".join(
        record.get("user_messages", []) +
        record.get("files_edited", []) +
        record.get("files_created", [])
    ).lower()

    # Intentar con keywords dinamicas de domains.json
    kw_map = _load_domain_keywords_map()
    if kw_map:
        scores: dict = {}
        for kw, dom in kw_map:
            if kw in text:
                scores[dom] = scores.get(dom, 0) + 1
        if scores:
            return max(scores, key=scores.get)

    return "files"


# -- API publica ---------------------------------------------------------------

def index_session(record: dict):
    """
    Indexa o actualiza una sesion.
    Usa DELETE + INSERT para garantizar consistencia en ambas tablas.
    """
    session_id = record.get("session_id", "")
    if not session_id:
        return

    date = record.get("date", "")
    if not date and record.get("timestamp"):
        date = record["timestamp"][:10]
    domain = _detect_domain(record)
    body = _build_body(record)
    now = datetime.now().isoformat()

    if not body.strip():
        return

    try:
        conn = _connect()
        _ensure_schema(conn)

        # Eliminar entrada previa (meta + fts)
        conn.execute("DELETE FROM sessions_fts WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions_meta WHERE session_id = ?", (session_id,))

        # Insertar nueva
        conn.execute(
            "INSERT INTO sessions_meta (session_id, date, domain, body, indexed_at) VALUES (?,?,?,?,?)",
            (session_id, date, domain, body, now)
        )
        conn.execute(
            "INSERT INTO sessions_fts (session_id, date, domain, body) VALUES (?,?,?,?)",
            (session_id, date, domain, body)
        )

        conn.commit()
        conn.close()
    except Exception:
        pass


def search(query: str, limit: int = 3) -> list:
    """
    Busqueda FTS5 sobre sesiones anteriores.
    Retorna [{date, domain, snippet}] ordenada por relevancia BM25.
    """
    if not query or not query.strip():
        return []
    if not EPISODIC_DB.exists():
        return []

    try:
        conn = _connect()
        _ensure_schema(conn)

        # Sanitizar: solo palabras alfanumericas, espacios para AND implicito
        tokens = re.findall(r'[a-zA-Z0-9\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1\u00fc\u00c1\u00c9\u00cd\u00d3\u00da\u00d1\u00dc_]{2,}', query)
        if not tokens:
            conn.close()
            return []
        # OR entre tokens: BM25 rankea primero los que tienen mas matches
        safe_query = " OR ".join(tokens)

        rows = conn.execute(
            """
            SELECT date, domain,
                   snippet(sessions_fts, 3, '\u00ab', '\u00bb', '...', 12) AS snip
            FROM sessions_fts
            WHERE body MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (safe_query, limit)
        ).fetchall()

        conn.close()
        return [
            {"date": r["date"] or "?", "domain": r["domain"] or "?", "snippet": r["snip"] or ""}
            for r in rows
        ]

    except Exception:
        return []


def rebuild_from_history() -> int:
    """
    Reconstruye el indice completo desde session_history.json.
    Borra la DB existente y re-indexa todas las sesiones.
    """
    if not SESSION_HISTORY_FILE.exists():
        return 0
    try:
        history = json.loads(SESSION_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(history, list):
        return 0

    # Reset limpio -- unlink preferido, fallback a DROP TABLE si Windows tiene archivo bloqueado
    if EPISODIC_DB.exists():
        try:
            EPISODIC_DB.unlink()
        except OSError:
            try:
                conn = _connect()
                conn.executescript(
                    "DROP TABLE IF EXISTS sessions_fts; DROP TABLE IF EXISTS sessions_meta;"
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

    count = 0
    for record in history:
        if isinstance(record, dict) and record.get("session_id"):
            index_session(record)
            count += 1
    return count


def timeline_search(query: str, before: int = 2, after: int = 2) -> list:
    """
    Busqueda con contexto cronologico (Engram mem_timeline).
    Para cada resultado, incluye las N sesiones anteriores y posteriores
    ordenadas por fecha para navegacion progresiva.

    Args:
        query:  Termino de busqueda
        before: Sesiones anteriores a incluir por resultado
        after:  Sesiones posteriores a incluir por resultado

    Returns:
        Lista de {match, context_before, context_after} donde
        cada elemento tiene {date, domain, snippet}.
    """
    if not query or not EPISODIC_DB.exists():
        return []

    try:
        conn = _connect()
        _ensure_schema(conn)

        tokens = re.findall(
            r'[a-zA-Z0-9\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1\u00fc_]{2,}', query
        )
        if not tokens:
            conn.close()
            return []
        safe_query = " OR ".join(tokens)

        # Obtener matches con fecha
        matches = conn.execute(
            """
            SELECT session_id, date, domain,
                   snippet(sessions_fts, 3, '\u00ab', '\u00bb', '...', 12) AS snip
            FROM sessions_fts
            WHERE body MATCH ?
            ORDER BY rank
            LIMIT 5
            """,
            (safe_query,)
        ).fetchall()

        results = []
        for m in matches:
            match_date = m["date"] or ""

            # Sesiones anteriores (cronologicamente antes)
            ctx_before = conn.execute(
                """
                SELECT date, domain,
                       snippet(sessions_fts, 3, '', '', '...', 8) AS snip
                FROM sessions_fts
                WHERE date < ? AND date != ''
                ORDER BY date DESC
                LIMIT ?
                """,
                (match_date, before)
            ).fetchall() if match_date else []

            # Sesiones posteriores (cronologicamente despues)
            ctx_after = conn.execute(
                """
                SELECT date, domain,
                       snippet(sessions_fts, 3, '', '', '...', 8) AS snip
                FROM sessions_fts
                WHERE date > ? AND date != ''
                ORDER BY date ASC
                LIMIT ?
                """,
                (match_date, after)
            ).fetchall() if match_date else []

            results.append({
                "match": {
                    "date":    m["date"] or "?",
                    "domain":  m["domain"] or "?",
                    "snippet": m["snip"] or "",
                },
                "context_before": [
                    {"date": r["date"], "domain": r["domain"], "snippet": r["snip"]}
                    for r in reversed(ctx_before)
                ],
                "context_after": [
                    {"date": r["date"], "domain": r["domain"], "snippet": r["snip"]}
                    for r in ctx_after
                ],
            })

        conn.close()
        return results

    except Exception:
        return []


def get_stats() -> dict:
    """Estadisticas del indice."""
    if not EPISODIC_DB.exists():
        return {"indexed_sessions": 0, "db_size_kb": 0}
    try:
        conn = _connect()
        _ensure_schema(conn)
        n = conn.execute("SELECT COUNT(*) FROM sessions_meta").fetchone()[0]
        conn.close()
        size_kb = round(EPISODIC_DB.stat().st_size / 1024, 1)
        return {"indexed_sessions": n, "db_size_kb": size_kb}
    except Exception:
        return {"indexed_sessions": 0, "db_size_kb": 0}


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "rebuild":
        n = rebuild_from_history()
        print(f"Rebuilt: {n} sessions indexed")
        print(get_stats())
    elif cmd == "search":
        q = " ".join(sys.argv[2:])
        results = search(q, limit=5)
        if results:
            for r in results:
                print(f"[{r['date']}/{r['domain']}] {r['snippet']}")
        else:
            print("Sin resultados")
    else:
        print(get_stats())
