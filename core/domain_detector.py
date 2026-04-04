# -*- coding: utf-8 -*-
"""
domain_detector.py -- Deteccion hibrida de dominios
====================================================
Detecta el dominio de un texto usando keywords dinamicas cargadas desde
domains.json (sin hardcoding). Combina la arquitectura dinamica del Motor 2
con las funciones de aprendizaje automatico del Motor 1.

Logica:
  1. Cargar dominios conocidos desde KB (domains.json)
  2. Extraer keywords del texto
  3. Matching contra keywords de cada dominio (aprendidas de sesiones previas)
  4. Si match >= threshold -> auto-asignar
  5. Si match bajo pero hay candidatos -> retornar sugerencias (list)
  6. Si no hay nada -> retornar "general"

API:
  detect(text: str) -> str              -- retorna dominio (o "general")
  suggest(text: str) -> list[str]       -- retorna candidatos posibles
  detect_multi(text, max_domains) -> list[str] -- multiples dominios (tareas mixtas)
  learn_domain_keywords(domain, keywords) -- expande las keywords de un dominio
  detect_from_session(record: dict) -> str -- para el episodic_index
  auto_learn_from_session(domain, text)   -- aprende keywords de sesion confirmada
"""

import json
import re
from pathlib import Path

from config import DOMAINS_FILE, DATA_DIR, AUTO_ASSIGN_THRESHOLD, SUGGEST_THRESHOLD


# -- Carga de dominios ---------------------------------------------------------

def _load_domain_keywords() -> dict:
    """
    Carga los dominios y sus keywords desde domains.json.
    Retorna {domain_name: {keywords: [...], description: ...}}.
    Soporta dos formatos:
      - Legacy: {domain_name: {keywords: [...]}, ...}
      - Fusion: {domains: [{name: "x", keywords: [...]}], ...}
    """
    if not DOMAINS_FILE.exists():
        return {}
    try:
        data = json.loads(DOMAINS_FILE.read_text(encoding="utf-8"))
        # Formato Fusion: {domains: [{name: ..., keywords: [...]}, ...], ...}
        if isinstance(data.get("domains"), list):
            result = {}
            for entry in data["domains"]:
                if isinstance(entry, dict) and "name" in entry:
                    result[entry["name"]] = {
                        "keywords": entry.get("keywords", []),
                        "description": entry.get("description", ""),
                    }
            return result
        # Formato Legacy: {domain_name: {keywords: [...]}, ...}
        # Filtrar solo entradas que son dicts (ignorar metadata como version, initialized_at)
        return {k: v for k, v in data.items() if isinstance(v, dict)}
    except Exception:
        return {}


# -- Extraccion de keywords ----------------------------------------------------

STOP_WORDS = {
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "que",
    "y", "a", "por", "con", "para", "es", "se", "no", "lo", "le", "su",
    "me", "te", "si", "mi", "tu", "al", "hay", "ya", "pero", "como",
    "the", "an", "in", "of", "to", "is", "it", "for", "and", "or",
    "puedo", "quiero", "hacer", "haz", "dame", "muestra", "dime",
    "necesito", "ver", "este", "esta", "esto", "cuando", "donde",
    "algo", "mas", "muy", "bien", "ok", "eso", "asi", "cual",
}


def _extract_keywords(text: str) -> list:
    """Extrae keywords relevantes del texto (sin stop words)."""
    words = re.findall(r'\b[a-zA-Z0-9_\u00e0-\u00ff]{3,}\b', text.lower())
    return [w for w in words if w not in STOP_WORDS][:30]


# -- Scoring -------------------------------------------------------------------

def _score_domains(keywords: list, domains: dict) -> dict:
    """
    Calcula score de coincidencia entre keywords del texto y
    keywords de cada dominio.

    Score = numero de keywords del texto que aparecen en las keywords del dominio.
    """
    text_kw_set = set(keywords)
    scores = {}

    for domain_name, domain_data in domains.items():
        domain_keywords = set(domain_data.get("keywords", []))
        # Tambien incluir el nombre del dominio y sus variaciones
        domain_keywords.add(domain_name)
        domain_keywords.add(domain_name.replace("_", ""))
        domain_keywords.add(domain_name.replace("_", " "))

        # Contar keywords en comun
        common = text_kw_set & domain_keywords
        if common:
            scores[domain_name] = len(common)

    return scores


# -- API publica ---------------------------------------------------------------

def detect(text: str) -> str:
    """
    Detecta el dominio dominante del texto.

    Returns:
        Nombre del dominio con mayor score (>= AUTO_ASSIGN_THRESHOLD),
        o "general" si no hay match suficiente.
    """
    if not text or not text.strip():
        return "general"

    keywords = _extract_keywords(text)
    if not keywords:
        return "general"

    domains = _load_domain_keywords()
    if not domains:
        return "general"

    scores = _score_domains(keywords, domains)
    if not scores:
        return "general"

    best_domain = max(scores, key=scores.get)
    best_score = scores[best_domain]

    if best_score >= AUTO_ASSIGN_THRESHOLD:
        return best_domain

    return "general"


def suggest(text: str) -> list:
    """
    Retorna lista de dominios candidatos (con al menos 1 keyword en comun).
    Util para mostrar sugerencias al usuario cuando la confianza es baja.

    Returns:
        Lista de nombres de dominio ordenados por score (mayor primero).
    """
    if not text or not text.strip():
        return []

    keywords = _extract_keywords(text)
    if not keywords:
        return []

    domains = _load_domain_keywords()
    if not domains:
        return []

    scores = _score_domains(keywords, domains)
    if not scores:
        return []

    # Retornar todos los que tienen al menos SUGGEST_THRESHOLD
    candidates = [
        (name, score)
        for name, score in scores.items()
        if score >= SUGGEST_THRESHOLD
    ]
    candidates.sort(key=lambda x: -x[1])
    return [name for name, _ in candidates[:5]]


def detect_multi(text: str, max_domains: int = 3) -> list:
    """
    Detecta multiples dominios en el texto (para tareas mixtas).
    Retorna todos los dominios con score >= 50% del maximo.

    Args:
        text:        Texto a analizar.
        max_domains: Numero maximo de dominios a retornar.

    Returns:
        Lista de nombres de dominio ordenados por score.
    """
    if not text or not text.strip():
        return []

    keywords = _extract_keywords(text)
    if not keywords:
        return []

    domains = _load_domain_keywords()
    if not domains:
        return []

    scores = _score_domains(keywords, domains)
    if not scores:
        return []

    max_score = max(scores.values())
    threshold = max(SUGGEST_THRESHOLD, max_score * 0.50)

    relevant = [
        (name, score)
        for name, score in scores.items()
        if score >= threshold
    ]
    relevant.sort(key=lambda x: -x[1])
    return [name for name, _ in relevant[:max_domains]]


def learn_domain_keywords(domain: str, new_keywords: list):
    """
    Expande las keywords de un dominio con nuevas keywords aprendidas de sesiones.
    Guarda en domains.json para mejorar deteccion futura.

    Args:
        domain:       Nombre del dominio.
        new_keywords: Lista de keywords nuevas a agregar.
    """
    if not domain or not new_keywords:
        return

    DOMAINS_FILE.parent.mkdir(parents=True, exist_ok=True)

    current = {}
    if DOMAINS_FILE.exists():
        try:
            current = json.loads(DOMAINS_FILE.read_text(encoding="utf-8"))
        except Exception:
            current = {}

    if domain not in current:
        current[domain] = {
            "description": f"Dominio auto-creado: {domain}",
            "file": "patterns.json",
            "entry_type": "pattern",
            "auto_created": True,
            "keywords": [],
        }

    existing_kw = set(current[domain].get("keywords", []))
    clean_kw = [
        kw.lower().strip()
        for kw in new_keywords
        if len(kw.strip()) >= 3 and kw.lower().strip() not in STOP_WORDS
    ]
    existing_kw.update(clean_kw)
    current[domain]["keywords"] = sorted(existing_kw)

    DOMAINS_FILE.write_text(
        json.dumps(current, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def detect_from_session(record: dict) -> str:
    """
    Detecta el dominio a partir de un record de sesion.
    Util para el episodic_index y el hook de fin de sesion.

    Args:
        record: dict de sesion con campos user_messages, files_edited, etc.

    Returns:
        Nombre del dominio o "general".
    """
    # Si el record ya tiene dominio, usarlo
    if record.get("domain"):
        return record["domain"]

    # Construir texto de la sesion para analisis
    parts = []
    for msg in record.get("user_messages", [])[:10]:
        if isinstance(msg, str):
            parts.append(msg)
    for f in record.get("files_edited", []) + record.get("files_created", []):
        if f:
            parts.append(Path(f).name)
    summary = record.get("summary", "")
    if summary:
        parts.append(summary)

    combined_text = " ".join(parts)
    if not combined_text.strip():
        return "general"

    return detect(combined_text)


def auto_promote_domain(domain: str, user_msg_count: int = 0) -> bool:
    """
    Cuenta cuantas sesiones ha aparecido este dominio.
    Cuando llega a AUTO_DOMAIN_MIN_SESSIONS lo promueve: lo crea en
    domains.json si no existia.

    Trigger automatico: llamar desde session_end con el dominio detectado
    y el numero de mensajes del usuario en esa sesion.

    Args:
        domain:         Nombre del dominio detectado en la sesion.
        user_msg_count: Cantidad de mensajes del usuario (filtra sesiones triviales).

    Returns:
        True si el dominio fue promovido (creado) en esta llamada.
        False si ya existia, no llego al umbral, o sesion trivial.
    """
    try:
        from config import (
            AUTO_DOMAIN_MIN_SESSIONS, AUTO_DOMAIN_MIN_MSGS,
            DOMAIN_SESSIONS_COUNTER_FILE, DOMAINS_FILE,
        )
    except ImportError:
        return False

    if not domain or domain in ("general", ""):
        return False

    # Ignorar sesiones triviales
    if user_msg_count < AUTO_DOMAIN_MIN_MSGS:
        return False

    # Verificar si ya existe en domains.json
    current_domains: dict = {}
    if DOMAINS_FILE.exists():
        try:
            current_domains = json.loads(DOMAINS_FILE.read_text(encoding="utf-8"))
        except Exception:
            current_domains = {}

    if domain in current_domains:
        return False  # ya existe, nada que promover

    # Incrementar contador de sesiones para este dominio candidato
    counter: dict = {}
    if DOMAIN_SESSIONS_COUNTER_FILE.exists():
        try:
            counter = json.loads(DOMAIN_SESSIONS_COUNTER_FILE.read_text(encoding="utf-8"))
        except Exception:
            counter = {}

    counter[domain] = counter.get(domain, 0) + 1
    DOMAIN_SESSIONS_COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    DOMAIN_SESSIONS_COUNTER_FILE.write_text(
        json.dumps(counter, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Si llego al umbral, promover: crear entrada en domains.json directamente
    if counter[domain] >= AUTO_DOMAIN_MIN_SESSIONS:
        DOMAINS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if domain not in current_domains:
            current_domains[domain] = {
                "description": f"Dominio auto-promovido tras {AUTO_DOMAIN_MIN_SESSIONS} sesiones",
                "file": "patterns.json",
                "entry_type": "pattern",
                "auto_created": True,
                "auto_promoted": True,
                "keywords": [],
            }
            DOMAINS_FILE.write_text(
                json.dumps(current_domains, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        # Limpiar el contador para este dominio (ya promovido)
        counter.pop(domain, None)
        DOMAIN_SESSIONS_COUNTER_FILE.write_text(
            json.dumps(counter, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True

    return False


def get_domain_promotion_candidates() -> dict:
    """
    Retorna los dominios candidatos a promocion y su conteo actual.
    Util para mostrar en TUI o stats.

    Returns:
        {domain_name: session_count} — solo los que no estan aun en domains.json
    """
    try:
        from config import DOMAIN_SESSIONS_COUNTER_FILE, DOMAINS_FILE
    except ImportError:
        return {}

    if not DOMAIN_SESSIONS_COUNTER_FILE.exists():
        return {}

    try:
        counter = json.loads(DOMAIN_SESSIONS_COUNTER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

    # Filtrar los que ya existen
    existing: set = set()
    if DOMAINS_FILE.exists():
        try:
            existing = set(json.loads(DOMAINS_FILE.read_text(encoding="utf-8")).keys())
        except Exception:
            pass

    return {d: c for d, c in counter.items() if d not in existing}


def auto_learn_from_session(domain: str, text: str):
    """
    Extrae keywords del texto y las asocia al dominio confirmado.
    Llamar desde session_end cuando se conoce el dominio real de la sesion.

    Solo aprende palabras "sustantivas" (>= 4 chars) para evitar ruido.

    Args:
        domain: Nombre del dominio confirmado de la sesion.
        text:   Texto completo de la sesion (mensajes, archivos, etc).
    """
    if not domain or domain == "general" or not text:
        return
    words = _extract_keywords(text)
    # Solo palabras "sustantivas" (>= 4 chars) como keywords
    keywords = [w for w in words if len(w) >= 4][:30]
    if keywords:
        learn_domain_keywords(domain, keywords)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python domain_detector.py detect \"texto a analizar\"")
        print("     python domain_detector.py suggest \"texto a analizar\"")
        print("     python domain_detector.py multi \"texto a analizar\"")
        print("     python domain_detector.py learn <dominio> keyword1 keyword2 ...")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "detect" and len(sys.argv) >= 3:
        text = " ".join(sys.argv[2:])
        print(f"Dominio detectado: {detect(text)}")
        print(f"Candidatos: {suggest(text)}")

    elif cmd == "suggest" and len(sys.argv) >= 3:
        text = " ".join(sys.argv[2:])
        candidates = suggest(text)
        if candidates:
            for c in candidates:
                print(f"  - {c}")
        else:
            print("Sin candidatos (texto muy generico)")

    elif cmd == "multi" and len(sys.argv) >= 3:
        text = " ".join(sys.argv[2:])
        domains = detect_multi(text)
        if domains:
            for d in domains:
                print(f"  - {d}")
        else:
            print("Sin dominios detectados")

    elif cmd == "learn" and len(sys.argv) >= 4:
        domain = sys.argv[2]
        keywords = sys.argv[3:]
        learn_domain_keywords(domain, keywords)
        print(f"Keywords aprendidas para '{domain}': {keywords}")

    else:
        print(f"Comando desconocido: {cmd}")
