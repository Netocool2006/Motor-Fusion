# -*- coding: utf-8 -*-
"""
agent_memory.py -- Memoria del agente: preferencias y facts del proyecto
=========================================================================
Almacena lo que el agente "recuerda" sobre el usuario y el proyecto actual.
Inspirado en Engram pero persistente entre sesiones y CLI-agnostico.

Tipos de memoria:
  preference  -- Preferencias del usuario ("usa snake_case", "no mockear DB")
  project_fact -- Hechos del proyecto ("usa PostgreSQL 15", "deploy en AWS")
  feedback    -- Correcciones del usuario ("no hagas X", "si haz Y")
  note        -- Notas generales del usuario

Almacenamiento:
  <DATA_DIR>/agent_memory.json

API:
  remember(text, mem_type, scope, tags) -> str (id)
  forget(memory_id) -> bool
  recall(query, mem_type, scope, limit) -> list[dict]
  recall_all(mem_type, scope) -> list[dict]
  export_for_context(limit) -> str  (para inyectar en session_start)
  detect_preference(text) -> dict | None  (auto-detect de preferencias)
  get_stats() -> dict
"""

import json
import hashlib
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import sys
_MOTOR_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_MOTOR_DIR))

from config import DATA_DIR
from core.file_lock import file_lock, _atomic_replace

# -- Archivo de memoria -------------------------------------------------------
AGENT_MEMORY_FILE = DATA_DIR / "agent_memory.json"

# -- Tipos validos -------------------------------------------------------------
VALID_TYPES = {"preference", "project_fact", "feedback", "note"}
VALID_SCOPES = {"personal", "project", "global"}

# -- Patrones para auto-deteccion de preferencias ----------------------------
# Frases que indican una preferencia del usuario
PREFERENCE_PATTERNS = [
    # Español
    (r"(?:prefiero|uso|utilizo|quiero)\s+(.+)", "preference"),
    (r"(?:no\s+(?:uses?|hagas?|pongas?|agregues?))\s+(.+)", "feedback"),
    (r"(?:siempre|siempre que)\s+(.+)", "preference"),
    (r"(?:nunca|jamas)\s+(.+)", "feedback"),
    (r"(?:recuerda que|ten en cuenta que|nota que)\s+(.+)", "note"),
    (r"(?:este proyecto|el proyecto)\s+(?:usa|utiliza|tiene|es)\s+(.+)", "project_fact"),
    (r"(?:estamos usando|trabajamos con)\s+(.+)", "project_fact"),
    (r"(?:el stack es|stack:)\s+(.+)", "project_fact"),
    (r"(?:deploy en|desplegamos en|corremos en)\s+(.+)", "project_fact"),
    (r"(?:la base de datos es|db:)\s+(.+)", "project_fact"),
    # English
    (r"(?:i prefer|i use|i like|i want)\s+(.+)", "preference"),
    (r"(?:don'?t|do not|never)\s+(.+)", "feedback"),
    (r"(?:always)\s+(.+)", "preference"),
    (r"(?:remember that|note that|keep in mind)\s+(.+)", "note"),
    (r"(?:this project uses?|we use|we're using)\s+(.+)", "project_fact"),
    (r"(?:deployed? (?:on|to|in)|running on)\s+(.+)", "project_fact"),
    (r"(?:the (?:database|db|stack) is)\s+(.+)", "project_fact"),
]


# =============================================================================
#  CARGA / GUARDADO
# =============================================================================

def _load() -> dict:
    """Carga la memoria del agente desde disco."""
    AGENT_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if AGENT_MEMORY_FILE.exists():
        try:
            with file_lock("agent_memory"):
                data = json.loads(AGENT_MEMORY_FILE.read_text(encoding="utf-8"))
                # Self-healing: asegurar estructura
                if "memories" not in data:
                    data["memories"] = {}
                if "stats" not in data:
                    data["stats"] = {"total": 0, "by_type": {}, "by_scope": {}}
                return data
        except Exception:
            pass
    return {
        "memories": {},
        "stats": {"total": 0, "by_type": {}, "by_scope": {}},
    }


def _save(data: dict):
    """Guarda la memoria con escritura atomica."""
    AGENT_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with file_lock("agent_memory"):
        tmp = AGENT_MEMORY_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _atomic_replace(tmp, AGENT_MEMORY_FILE)


def _gen_id(text: str) -> str:
    """ID determinista de 12 hex chars."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _recalc_stats(data: dict):
    """Recalcula estadisticas desde las memorias."""
    memories = data.get("memories", {})
    by_type = {}
    by_scope = {}
    for m in memories.values():
        if m.get("deleted"):
            continue
        t = m.get("type", "note")
        s = m.get("scope", "personal")
        by_type[t] = by_type.get(t, 0) + 1
        by_scope[s] = by_scope.get(s, 0) + 1
    active = sum(by_type.values())
    data["stats"] = {"total": active, "by_type": by_type, "by_scope": by_scope}


# =============================================================================
#  API PUBLICA
# =============================================================================

def remember(text: str, mem_type: str = "note", scope: str = "personal",
             tags: list = None, source: str = "") -> str:
    """
    Guarda un recuerdo en la memoria del agente.

    Args:
        text:     Contenido del recuerdo.
        mem_type: preference | project_fact | feedback | note
        scope:    personal | project | global
        tags:     Lista de tags para busqueda.
        source:   Origen del recuerdo ("user_said", "auto_detected", etc.)

    Returns:
        ID del recuerdo creado.
    """
    if mem_type not in VALID_TYPES:
        mem_type = "note"
    if scope not in VALID_SCOPES:
        scope = "personal"

    data = _load()
    mid = _gen_id(text)

    # Deduplicar: si ya existe con el mismo texto, actualizar timestamp
    existing = data["memories"].get(mid)
    if existing and not existing.get("deleted"):
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()
        existing["recall_count"] = existing.get("recall_count", 0) + 1
        _save(data)
        return mid

    data["memories"][mid] = {
        "text": text,
        "type": mem_type,
        "scope": scope,
        "tags": tags or [],
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "recall_count": 0,
        "deleted": False,
    }

    _recalc_stats(data)
    _save(data)
    return mid


def forget(memory_id: str) -> bool:
    """Elimina un recuerdo (soft delete)."""
    data = _load()
    if memory_id in data["memories"]:
        data["memories"][memory_id]["deleted"] = True
        data["memories"][memory_id]["deleted_at"] = datetime.now(timezone.utc).isoformat()
        _recalc_stats(data)
        _save(data)
        return True
    return False


def recall(query: str = "", mem_type: str = "", scope: str = "",
           limit: int = 10) -> list:
    """
    Busca recuerdos relevantes.

    Args:
        query:    Texto a buscar (match parcial en text y tags).
        mem_type: Filtrar por tipo (vacio = todos).
        scope:    Filtrar por scope (vacio = todos).
        limit:    Maximo de resultados.

    Returns:
        Lista de dicts con los recuerdos encontrados, ordenados por relevancia.
    """
    data = _load()
    memories = data.get("memories", {})

    results = []
    query_lower = query.lower()
    query_words = set(re.findall(r'\b[a-z0-9_]{3,}\b', query_lower))

    for mid, m in memories.items():
        if m.get("deleted"):
            continue

        # Filtros de tipo y scope
        if mem_type and m.get("type") != mem_type:
            continue
        if scope and m.get("scope") != scope:
            continue

        # Scoring por relevancia
        score = 0.0
        text_lower = m.get("text", "").lower()
        tags_lower = [t.lower() for t in m.get("tags", [])]

        if query_words:
            text_words = set(re.findall(r'\b[a-z0-9_]{3,}\b', text_lower))
            tag_words = set(t for tag in tags_lower for t in re.findall(r'\b[a-z0-9_]{3,}\b', tag))

            # Match en texto
            text_matches = len(query_words & text_words)
            score += text_matches * 2.0

            # Match en tags
            tag_matches = len(query_words & tag_words)
            score += tag_matches * 3.0

            # Match parcial (substring)
            if query_lower in text_lower:
                score += 5.0

            if score == 0:
                continue  # No hay match
        else:
            score = 1.0  # Sin query, retornar todos

        # Bonus por recall_count (mas consultado = mas relevante)
        score += m.get("recall_count", 0) * 0.1

        results.append({
            "id": mid,
            "score": score,
            **m,
        })

    # Ordenar por score descendente
    results.sort(key=lambda x: -x["score"])

    # Incrementar recall_count de los retornados
    if results:
        for r in results[:limit]:
            rid = r["id"]
            if rid in memories:
                memories[rid]["recall_count"] = memories[rid].get("recall_count", 0) + 1
        _save(data)

    return results[:limit]


def recall_all(mem_type: str = "", scope: str = "") -> list:
    """Retorna todos los recuerdos activos, filtrados opcionalmente."""
    data = _load()
    results = []
    for mid, m in data.get("memories", {}).items():
        if m.get("deleted"):
            continue
        if mem_type and m.get("type") != mem_type:
            continue
        if scope and m.get("scope") != scope:
            continue
        results.append({"id": mid, **m})
    return results


def export_for_context(limit: int = 20) -> str:
    """
    Exporta la memoria del agente para inyectar en el contexto de sesion.
    Formato compacto, agrupado por tipo.

    Returns:
        String formateado para inyeccion directa en el prompt.
    """
    data = _load()
    memories = data.get("memories", {})
    stats = data.get("stats", {})

    active = [m for m in memories.values() if not m.get("deleted")]
    if not active:
        return ""

    # Agrupar por tipo
    by_type = {}
    for m in active:
        t = m.get("type", "note")
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(m)

    lines = []
    lines.append("-" * 60)
    lines.append(f"  MEMORIA DEL AGENTE -- {stats.get('total', len(active))} recuerdos activos")
    lines.append("-" * 60)

    # Orden de tipos para display
    type_labels = {
        "preference": "PREFERENCIAS DEL USUARIO",
        "project_fact": "HECHOS DEL PROYECTO",
        "feedback": "FEEDBACK / CORRECCIONES",
        "note": "NOTAS",
    }

    shown = 0
    for t in ["preference", "project_fact", "feedback", "note"]:
        items = by_type.get(t, [])
        if not items:
            continue

        label = type_labels.get(t, t.upper())
        lines.append(f"\n  {label}:")

        # Ordenar por recall_count (mas consultados primero)
        items.sort(key=lambda x: -x.get("recall_count", 0))

        for m in items:
            if shown >= limit:
                break
            text = m.get("text", "")[:200]
            tags = m.get("tags", [])
            tag_str = f" [{', '.join(tags[:3])}]" if tags else ""
            lines.append(f"    - {text}{tag_str}")
            shown += 1

    lines.append("")
    return "\n".join(lines)


def detect_preference(text: str) -> dict | None:
    """
    Intenta auto-detectar una preferencia o fact del texto del usuario.

    Args:
        text: Mensaje del usuario.

    Returns:
        Dict con {text, type, tags} si se detecto algo, o None.
    """
    text_clean = text.strip()
    if len(text_clean) < 10 or len(text_clean) > 500:
        return None

    text_lower = text_clean.lower()

    for pattern, mem_type in PREFERENCE_PATTERNS:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            captured = match.group(1).strip()
            if len(captured) < 5:
                continue

            # Extraer tags de la captura
            tags = re.findall(r'\b[a-zA-Z0-9_]{3,}\b', captured)
            tags = [t.lower() for t in tags[:5]]

            return {
                "text": text_clean,
                "type": mem_type,
                "tags": tags,
            }

    return None


def get_stats() -> dict:
    """Retorna estadisticas de la memoria del agente."""
    data = _load()
    return data.get("stats", {"total": 0, "by_type": {}, "by_scope": {}})


# =============================================================================
#  CLI
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso:")
        print('  python agent_memory.py remember "texto" [--type preference] [--scope project] [--tags tag1,tag2]')
        print('  python agent_memory.py forget <id>')
        print('  python agent_memory.py recall "query" [--type preference]')
        print('  python agent_memory.py list [--type preference] [--scope project]')
        print('  python agent_memory.py export')
        print('  python agent_memory.py stats')
        print('  python agent_memory.py detect "i prefer snake_case"')
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "remember" and len(sys.argv) >= 3:
        text = sys.argv[2]
        mem_type = "note"
        scope = "personal"
        tags = []
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--type" and i + 1 < len(sys.argv):
                mem_type = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--scope" and i + 1 < len(sys.argv):
                scope = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--tags" and i + 1 < len(sys.argv):
                tags = sys.argv[i + 1].split(",")
                i += 2
            else:
                i += 1
        mid = remember(text, mem_type, scope, tags, source="cli")
        print(f"Guardado: {mid}")

    elif cmd == "forget" and len(sys.argv) >= 3:
        mid = sys.argv[2]
        if forget(mid):
            print(f"Olvidado: {mid}")
        else:
            print(f"No encontrado: {mid}")

    elif cmd == "recall" and len(sys.argv) >= 3:
        query = sys.argv[2]
        mem_type = ""
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--type" and i + 1 < len(sys.argv):
                mem_type = sys.argv[i + 1]
                i += 2
            else:
                i += 1
        results = recall(query, mem_type=mem_type)
        if results:
            for r in results:
                print(f"  [{r['type']}] {r['text'][:100]}  (score: {r['score']:.1f}, id: {r['id']})")
        else:
            print("  Sin resultados")

    elif cmd == "list":
        mem_type = ""
        scope = ""
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--type" and i + 1 < len(sys.argv):
                mem_type = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--scope" and i + 1 < len(sys.argv):
                scope = sys.argv[i + 1]
                i += 2
            else:
                i += 1
        results = recall_all(mem_type, scope)
        if results:
            for r in results:
                tags = ", ".join(r.get("tags", [])[:3])
                print(f"  [{r['type']}] {r['text'][:100]}  (tags: {tags}, id: {r['id']})")
        else:
            print("  Sin recuerdos")

    elif cmd == "export":
        output = export_for_context()
        if output:
            print(output)
        else:
            print("  (memoria vacia)")

    elif cmd == "stats":
        s = get_stats()
        print(f"  Total: {s.get('total', 0)}")
        print(f"  Por tipo: {json.dumps(s.get('by_type', {}))}")
        print(f"  Por scope: {json.dumps(s.get('by_scope', {}))}")

    elif cmd == "detect" and len(sys.argv) >= 3:
        text = sys.argv[2]
        result = detect_preference(text)
        if result:
            print(f"  Detectado: [{result['type']}] {result['text']}")
            print(f"  Tags: {result['tags']}")
        else:
            print("  No se detecto preferencia/fact")

    else:
        print(f"Comando desconocido: {cmd}")
