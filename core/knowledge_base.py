"""
knowledge_base.py -- Base de Conocimiento Multi-Dominio (Motor Unificado)
=========================================================================
Fusion de Motor 1 (IDF + decay + ingest) y Motor 2 (dominios dinamicos,
clean architecture, Path-based).

Estructura en disco:
    <KNOWLEDGE_DIR>/
        domains.json              <- registro de dominios conocidos
        <dominio>/patterns.json   <- selectores, scripts, workarounds
        <dominio>/facts.json      <- reglas, procesos, conocimiento declarativo
    <DATA_DIR>/
        execution_log.jsonl       <- log global

API publica:
    add_pattern(domain, key, solution, tags, error_context) -> str
    add_fact(domain, key, fact, tags) -> str
    search(domain, key, tags, text_query) -> list[dict]
    cross_domain_search(tags, text_query, domains) -> dict[str, list]
    export_context(domain, tags, text_query, limit) -> str
    get_global_stats() -> dict
    list_domains() -> list[str]
    ingest_business_rules_from_text(text, source) -> list[str]
    ingest_catalog_from_text(text, source) -> list[str]
"""

import io
import json
import hashlib
import math
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# -- Windows cp1252 stdout fix (module-level) --------------------------------
def _fix_windows_stdout():
    """Fix Unicode en Windows (cp1252 no soporta emojis). Solo al ejecutar como script."""
    if sys.stdout and hasattr(sys.stdout, "buffer"):
        try:
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
        except Exception:
            pass


# -- Configuracion central ---------------------------------------------------
from config import KNOWLEDGE_DIR, DATA_DIR, EXECUTION_LOG, DOMAINS_FILE
from core.file_lock import file_lock, _atomic_replace

# Alias para compatibilidad con usos internos del modulo
LOG_FILE = EXECUTION_LOG


# ============================================================================
#  GESTION DE DOMINIOS DINAMICOS
# ============================================================================

def _load_all_domains() -> dict:
    """
    Devuelve todos los dominios conocidos desde disco (domains.json).
    No hay dominios hardcodeados -- todos se crean dinamicamente.
    """
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    if DOMAINS_FILE.exists():
        try:
            return json.loads(DOMAINS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _ensure_domain(name: str, description: str = "") -> dict:
    """
    Garantiza que el dominio existe en disco.
    Si no existe, lo crea automaticamente en domains.json.
    Retorna el dict completo de todos los dominios.
    """
    all_domains = _load_all_domains()
    if name not in all_domains:
        new_entry = {
            "description": description or f"Dominio auto-creado: {name}",
            "file": "patterns.json",
            "entry_type": "pattern",
            "auto_created": True,
            "num_entries": 0,  # Inicialmente vacío
        }
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        all_domains[name] = new_entry
        # Escritura atomica de domains.json
        tmp = DOMAINS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(all_domains, f, indent=2, ensure_ascii=False)
        _atomic_replace(tmp, DOMAINS_FILE)
        _append_log({
            "event": "domain_created",
            "domain": name,
            "description": new_entry["description"],
        })

    # Crear directorio del dominio solo cuando se registra
    _ensure_domain_dir(name)
    return all_domains


def _ensure_domain_dir(domain: str):
    """Crea el directorio de un dominio especifico solo cuando se necesita."""
    (KNOWLEDGE_DIR / domain).mkdir(parents=True, exist_ok=True)


def _ensure_dirs():
    """
    Crea directorios solo para dominios que ya existen en domains.json.
    NOTA: No crea directorios proactivamente si domains.json esta vacio.
    Los directorios se crean on-demand via _ensure_domain_dir().
    """
    for domain in _load_all_domains():
        _ensure_domain_dir(domain)


def list_domains() -> list[str]:
    """Retorna la lista de nombres de dominios conocidos."""
    return list(_load_all_domains().keys())


# ============================================================================
#  ACCESO A ARCHIVOS DE DOMINIO
# ============================================================================

def _domain_path(domain: str) -> Path:
    """Ruta del archivo de datos del dominio. Crea el dominio si no existe."""
    all_domains = _ensure_domain(domain)
    return KNOWLEDGE_DIR / domain / all_domains[domain].get("file", "patterns.json")


def _load_domain(domain: str) -> dict:
    """Carga el JSON completo de un dominio. Si no existe, retorna estructura vacia."""
    all_domains = _ensure_domain(domain)
    path = _domain_path(domain)
    with file_lock(f"kb_{domain}"):
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return {
        "domain": domain,
        "description": all_domains[domain]["description"],
        "entries": {},
        "tag_index": {},
        "stats": {"total_entries": 0, "total_lookups": 0, "total_hits": 0},
    }


def _save_domain(domain: str, data: dict):
    """Guarda el JSON de un dominio con reemplazo atomico (safe en Windows)."""
    _ensure_domain_dir(domain)
    path = _domain_path(domain)
    with file_lock(f"kb_{domain}"):
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _atomic_replace(tmp, path)

    # Actualizar num_entries en domains.json
    try:
        all_domains = _load_all_domains()
        if domain in all_domains:
            all_domains[domain]["num_entries"] = len(data.get("entries", {}))
            tmp = DOMAINS_FILE.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(all_domains, f, indent=2, ensure_ascii=False)
            _atomic_replace(tmp, DOMAINS_FILE)
    except Exception:
        pass  # No fallar si no se puede actualizar metadata


def _entry_id(key: str) -> str:
    """ID determinista a partir de un key (12 hex chars de SHA-256)."""
    return hashlib.sha256(key.encode()).hexdigest()[:12]


# ============================================================================
#  LOG (con rotacion)
# ============================================================================

MAX_LOG_LINES = 5000


def _append_log(entry: dict):
    """Agrega una linea al log global con rotacion automatica."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    with file_lock("execution_log"):
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > MAX_LOG_LINES:
                with open(LOG_FILE, "w", encoding="utf-8") as f:
                    f.writelines(lines[-MAX_LOG_LINES:])
        except Exception:
            pass


# ============================================================================
#  IDF WEIGHTING (de Motor 1)
# ============================================================================

def _compute_idf(entries: dict, query_words: set[str]) -> dict[str, float]:
    """
    Calcula IDF (Inverse Document Frequency) para las palabras del query.
    IDF(t) = log(N / (1 + df(t)))
    donde N = total entries, df(t) = entries que contienen t.

    Nota: Se usa max(..., 0.1) para asegurar IDF > 0 incluso con corpus pequeño.
    Esto permite que palabras exactas tengan score positivo en dominios con pocas entries.
    """
    n = max(len(entries), 1)
    df: Counter = Counter()
    for eid, entry in entries.items():
        searchable = " ".join([
            entry.get("key", ""),
            " ".join(entry.get("tags", [])),
            json.dumps(
                entry.get("solution", entry.get("fact", {})),
                ensure_ascii=False,
            ),
        ]).lower()
        for word in query_words:
            if word in searchable:
                df[word] += 1

    idf = {}
    for word in query_words:
        # max(..., 0.1) asegura que IDF sea siempre > 0 cuando hay match
        raw_idf = math.log(n / (1 + df.get(word, 0)))
        idf[word] = max(raw_idf, 0.1)  # Minimum IDF to ensure searchability
    return idf


# ============================================================================
#  PATTERNS -- soluciones tecnicas
# ============================================================================

def add_pattern(
    domain: str,
    key: str,
    solution: dict,
    tags: list[str] | None = None,
    error_context: dict | None = None,
) -> str:
    """
    Registra un patron tecnico (selector, script, workaround, solucion a error).

    Args:
        domain:        Nombre del dominio (se crea automaticamente si no existe).
        key:           Identificador semantico del patron.
        solution:      Dict con la solucion:
            {
                "strategy": "nombre de la estrategia",
                "code_snippet": "codigo que funciono",
                "notes": "notas sobre por que funciono / que no funciono",
                "attempts_to_solve": 2,
            }
        tags:          Lista de tags para indexar y buscar.
        error_context: Contexto del error que origino este patron (opcional).

    Returns:
        ID del entry creado (12 hex chars).
    """
    data = _load_domain(domain)
    eid = _entry_id(f"{domain}::{key}")
    now = datetime.now(timezone.utc).isoformat()

    data["entries"][eid] = {
        "id": eid,
        "type": "pattern",
        "key": key,
        "solution": solution,
        "tags": tags or [],
        "error_context": error_context,
        "created_at": now,
        "updated_at": now,
        "stats": {
            "lookups": 0,
            "reuses": 0,
            "success_rate": 1.0,
            "last_accessed": now,
            "access_count": 0,
        },
    }
    data["stats"]["total_entries"] += 1

    for tag in (tags or []):
        data["tag_index"].setdefault(tag, []).append(eid)

    _save_domain(domain, data)
    _append_log({"event": "pattern_added", "domain": domain, "key": key, "id": eid})
    return eid


# ============================================================================
#  FACTS -- conocimiento declarativo
# ============================================================================

def add_fact(
    domain: str,
    key: str,
    fact: dict,
    tags: list[str] | None = None,
) -> str:
    """
    Registra un hecho / regla de conocimiento declarativo.

    fact = {
        "rule": "descripcion de la regla o hecho",
        "applies_to": "contexto donde aplica",
        "examples": [
            {"input": "...", "output": "...", "context": "..."},
        ],
        "exceptions": "casos donde NO aplica",
        "source": "origen del conocimiento",
        "confidence": "verified | observed | inferred",
    }

    Returns:
        ID del entry creado (12 hex chars).
    """
    data = _load_domain(domain)
    eid = _entry_id(f"{domain}::{key}")
    now = datetime.now(timezone.utc).isoformat()

    data["entries"][eid] = {
        "id": eid,
        "type": "fact",
        "key": key,
        "fact": fact,
        "tags": tags or [],
        "created_at": now,
        "updated_at": now,
        "stats": {
            "lookups": 0,
            "cited_in_tasks": 0,
            "last_accessed": now,
            "access_count": 0,
        },
    }
    data["stats"]["total_entries"] += 1

    for tag in (tags or []):
        data["tag_index"].setdefault(tag, []).append(eid)

    _save_domain(domain, data)
    _append_log({"event": "fact_added", "domain": domain, "key": key, "id": eid})
    return eid


# ============================================================================
#  BUSQUEDA -- single-domain (IDF + temporal decay)
# ============================================================================

def search(
    domain: str,
    key: str | None = None,
    tags: list[str] | None = None,
    text_query: str | None = None,
) -> list[dict]:
    """
    Busca en UN dominio.

    Modos:
      - key:        busqueda exacta por ID derivado del key
      - tags:       busqueda por tags (union)
      - text_query: busqueda fuzzy con ranking IDF + temporal decay

    Ranking:
      score = sum(idf[word] para cada word que matchea)
              * success_rate
              * exp(-0.01 * dias_sin_acceso)
    """
    data = _load_domain(domain)
    results: list[dict] = []

    # -- Exacta por key -------------------------------------------------------
    if key:
        eid = _entry_id(f"{domain}::{key}")
        if eid in data["entries"]:
            entry = data["entries"][eid]
            entry["stats"]["lookups"] += 1
            entry["stats"]["access_count"] = entry["stats"].get("access_count", 0) + 1
            entry["stats"]["last_accessed"] = datetime.now(timezone.utc).isoformat()
            data["stats"]["total_hits"] += 1
            data["stats"]["total_lookups"] += 1
            _save_domain(domain, data)
            return [entry]

    # -- Por tags -------------------------------------------------------------
    if tags:
        seen: set[str] = set()
        for tag in tags:
            for eid in data["tag_index"].get(tag, []):
                if eid not in seen and eid in data["entries"]:
                    results.append(data["entries"][eid])
                    seen.add(eid)

    # -- Fuzzy por texto (IDF weighted) ---------------------------------------
    if text_query:
        query_lower = text_query.lower()
        query_words = {w for w in re.split(r"\s+", query_lower) if len(w) >= 3}

        if query_words:
            # Calcular IDF sobre todas las entries del dominio
            idf = _compute_idf(data["entries"], query_words)

            existing_ids = {r["id"] for r in results}
            scored: list[tuple[float, dict]] = []

            for eid, entry in data["entries"].items():
                if eid in existing_ids:
                    continue
                searchable = " ".join([
                    entry.get("key", ""),
                    " ".join(entry.get("tags", [])),
                    json.dumps(
                        entry.get("solution", entry.get("fact", {})),
                        ensure_ascii=False,
                    ),
                ]).lower()

                # Sumar IDF de cada palabra que aparece
                idf_score = sum(
                    idf.get(word, 0.0)
                    for word in query_words
                    if word in searchable
                )
                if idf_score > 0:
                    scored.append((idf_score, entry))

            # Ordenar por IDF score * success_rate * temporal decay
            now_ts = datetime.now(timezone.utc)

            def _full_score(pair: tuple[float, dict]) -> float:
                idf_s, e = pair
                stats = e.get("stats", {})
                sr = stats.get("success_rate", 1.0)
                last = stats.get("last_accessed")
                if last:
                    try:
                        days = max(0, (now_ts - datetime.fromisoformat(last)).days)
                        decay = math.exp(-0.01 * days)
                    except Exception:
                        decay = 1.0
                else:
                    decay = 1.0
                return idf_s * sr * decay

            scored.sort(key=_full_score, reverse=True)
            results.extend(entry for _, entry in scored)

    # -- Actualizar last_accessed para resultados retornados -------------------
    now_iso = datetime.now(timezone.utc).isoformat()
    for entry in results:
        eid = entry.get("id")
        if eid and eid in data["entries"]:
            data["entries"][eid]["stats"]["last_accessed"] = now_iso
            data["entries"][eid]["stats"]["access_count"] = (
                data["entries"][eid]["stats"].get("access_count", 0) + 1
            )

    data["stats"]["total_lookups"] += 1
    if results:
        data["stats"]["total_hits"] += 1
    _save_domain(domain, data)
    return results


# ============================================================================
#  BUSQUEDA CROSS-DOMAIN
# ============================================================================

def cross_domain_search(
    tags: list[str] | None = None,
    text_query: str | None = None,
    domains: list[str] | None = None,
) -> dict[str, list[dict]]:
    """
    Busca en MULTIPLES dominios simultaneamente.
    Retorna {domain: [entries]} para cada dominio con resultados.

    Esto permite que la automatizacion SAP consulte reglas de negocio
    sobre nomenclatura de codigos, o que un SOW consulte el catalogo.
    """
    target_domains = domains or list(_load_all_domains().keys())
    results: dict[str, list[dict]] = {}

    for domain in target_domains:
        domain_results = search(domain, tags=tags, text_query=text_query)
        if domain_results:
            results[domain] = domain_results

    _append_log({
        "event": "cross_domain_search",
        "tags": tags,
        "text_query": text_query,
        "domains_searched": target_domains,
        "hits_per_domain": {d: len(r) for d, r in results.items()},
    })

    return results


# ============================================================================
#  EXPORTACION -- contexto formateado para inyeccion en prompts
# ============================================================================

def export_context(
    domain: str | None = None,
    tags: list[str] | None = None,
    text_query: str | None = None,
    limit: int = 10,
) -> str:
    """
    Genera texto legible para inyectar en el prompt del CLI.
    Si domain=None, busca en todos los dominios.

    Formato:
        === BASE DE CONOCIMIENTO ===
        -- DOMINIO (descripcion) --
          [key]
            Estrategia / Regla / Codigo / Nota
    """
    if domain:
        entries = search(domain, tags=tags, text_query=text_query)
        all_results = {domain: entries}
    else:
        all_results = cross_domain_search(tags=tags, text_query=text_query)

    if not any(all_results.values()):
        return "No se encontraron entradas relevantes en la base de conocimiento."

    all_domains = _load_all_domains()
    lines: list[str] = ["=== BASE DE CONOCIMIENTO ===", ""]

    for dom, entries in all_results.items():
        if not entries:
            continue
        dom_desc = all_domains.get(dom, {}).get("description", dom)
        lines.append(f"-- {dom.upper()} ({dom_desc}) --")

        for entry in entries[:limit]:
            if entry["type"] == "pattern":
                sol = entry.get("solution", {})
                lines.append(f"  [{entry['key']}]")
                lines.append(f"    Estrategia: {sol.get('strategy', 'N/A')}")
                if sol.get("code_snippet"):
                    lines.append(f"    Codigo: {sol['code_snippet'][:300]}")
                if sol.get("notes"):
                    lines.append(f"    Nota: {sol['notes']}")
                lines.append(
                    f"    Exito: {entry['stats'].get('success_rate', 'N/A')}"
                )

            elif entry["type"] == "fact":
                fact = entry.get("fact", {})
                lines.append(f"  [{entry['key']}]")
                lines.append(f"    Regla: {fact.get('rule', 'N/A')}")
                if fact.get("applies_to"):
                    lines.append(f"    Aplica a: {fact['applies_to']}")
                if fact.get("examples"):
                    for ex in fact["examples"][:3]:
                        lines.append(
                            f"    Ejemplo: {ex.get('input', '?')} -> "
                            f"{ex.get('output', '?')} ({ex.get('context', '')})"
                        )
                if fact.get("exceptions"):
                    lines.append(f"    Excepcion: {fact['exceptions']}")
                conf = fact.get("confidence", "unknown")
                lines.append(f"    Confianza: {conf}")
            lines.append("")

    return "\n".join(lines)


# ============================================================================
#  INGEST -- carga masiva desde texto semi-estructurado
# ============================================================================

def ingest_business_rules_from_text(
    text: str,
    source: str = "manual",
) -> list[str]:
    """
    Parsea texto semi-estructurado y extrae reglas de negocio.
    Formato esperado (una regla por bloque separado por linea vacia):

        REGLA: Los codigos de contrato llevan sufijo _PS
        APLICA: oportunidades tipo contrato
        EJEMPLO: LLML245 -> LLML245_PS (contrato)
        EJEMPLO: LLML245 -> LLML245 (proyecto)
        EXCEPCION: No aplica a renovaciones _RN
        TAGS: nomenclatura, codigos, contrato, sufijo

    Tambien acepta formato libre -- cada parrafo se registra como un fact.

    Returns:
        Lista de IDs de entries creados.
    """
    ids: list[str] = []
    # Normalizar separadores tipo "---" a doble newline
    normalized = re.sub(r"\n-{3,}\n", "\n\n", text.strip())
    blocks = normalized.split("\n\n")

    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue

        fact: dict = {"source": source, "confidence": "observed"}
        key_parts: list[str] = []
        tags: list[str] = []

        for line in lines:
            line = line.strip()
            upper = line.upper()

            if upper.startswith("REGLA:"):
                fact["rule"] = line[6:].strip()
                key_parts.append(fact["rule"][:50])
            elif upper.startswith("APLICA:") or upper.startswith("APLICA A:"):
                fact["applies_to"] = line.split(":", 1)[1].strip()
            elif upper.startswith("EJEMPLO:"):
                if "examples" not in fact:
                    fact["examples"] = []
                ex_text = line[8:].strip()
                match = re.match(
                    r"(.+?)\s*(?:->|-->)+\s*(.+?)(?:\s*\((.+?)\))?\s*$", ex_text
                )
                if match:
                    fact["examples"].append({
                        "input": match.group(1).strip(),
                        "output": match.group(2).strip(),
                        "context": (match.group(3) or "").strip(),
                    })
                else:
                    fact["examples"].append({
                        "input": ex_text, "output": "", "context": ""
                    })
            elif upper.startswith("EXCEPCION:") or upper.startswith("EXCEPCI\u00d3N:"):
                fact["exceptions"] = line.split(":", 1)[1].strip()
            elif upper.startswith("TAGS:"):
                tags = [t.strip() for t in line[5:].split(",") if t.strip()]
            elif upper.startswith("CONFIANZA:") or upper.startswith("CONFIDENCE:"):
                fact["confidence"] = line.split(":", 1)[1].strip()
            else:
                # Linea sin prefijo -> parte de la regla
                if "rule" not in fact:
                    fact["rule"] = line
                    key_parts.append(line[:50])
                else:
                    fact["rule"] += " " + line

        if "rule" in fact:
            key = "_".join(key_parts) if key_parts else f"rule_{len(ids)}"
            eid = add_fact("business_rules", key, fact, tags)
            ids.append(eid)

    return ids


def ingest_catalog_from_text(
    text: str,
    source: str = "manual",
) -> list[str]:
    """
    Parsea catalogo de productos. Formato:

        CODIGO: LLML245
        NOMBRE: SAP Licencia ML
        TIPO: contrato
        VARIANTES: LLML245_PS (post-sale), LLML245_RN (renovacion)
        PRECIO: $60/hr (8x5), $80/hr (24x7)
        TAGS: sap, licencia, ml

    Tambien acepta CSV-like: codigo,nombre,tipo,precio

    Returns:
        Lista de IDs de entries creados.
    """
    ids: list[str] = []
    normalized = re.sub(r"\n-{3,}\n", "\n\n", text.strip())
    blocks = normalized.split("\n\n")

    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue

        fact: dict = {"source": source, "confidence": "verified"}
        key = ""
        tags: list[str] = []

        for line in lines:
            line = line.strip()
            upper = line.upper()

            if upper.startswith("CODIGO:") or upper.startswith("C\u00d3DIGO:"):
                code = line.split(":", 1)[1].strip()
                fact["code"] = code
                key = code
            elif upper.startswith("NOMBRE:"):
                fact["name"] = line.split(":", 1)[1].strip()
            elif upper.startswith("TIPO:"):
                fact["product_type"] = line.split(":", 1)[1].strip()
            elif upper.startswith("VARIANTES:") or upper.startswith("VARIANTS:"):
                variants_text = line.split(":", 1)[1].strip()
                fact["variants"] = [v.strip() for v in variants_text.split(",")]
            elif upper.startswith("PRECIO:") or upper.startswith("PRICE:"):
                fact["pricing"] = line.split(":", 1)[1].strip()
            elif upper.startswith("RELACION:") or upper.startswith("RELACI\u00d3N:"):
                fact["relations"] = line.split(":", 1)[1].strip()
            elif upper.startswith("TAGS:"):
                tags = [t.strip() for t in line[5:].split(",") if t.strip()]
            else:
                fact.setdefault("notes", "")
                fact["notes"] += " " + line

        if key:
            fact["rule"] = f"Producto {key}: {fact.get('name', 'sin nombre')}"
            eid = add_fact("catalog", key, fact, tags)
            ids.append(eid)

    return ids


# ============================================================================
#  STATS GLOBALES
# ============================================================================

def get_global_stats() -> dict:
    """
    Estadisticas detalladas de todos los dominios.

    Retorna:
        {
            "<domain>": {
                "entries": int,
                "lookups": int,
                "hits": int,
                "patterns": int,
                "facts": int,
                "tags_count": int,
                "avg_success_rate": float,
            },
            ...
            "total_entries": int,
            "total_domains": int,
            "total_lookups": int,
            "total_hits": int,
        }
    """
    all_domains = _load_all_domains()
    stats: dict = {}
    grand_entries = 0
    grand_lookups = 0
    grand_hits = 0

    for domain in all_domains:
        data = _load_domain(domain)
        entries = data.get("entries", {})
        d_stats = data.get("stats", {})

        n_patterns = sum(1 for e in entries.values() if e.get("type") == "pattern")
        n_facts = sum(1 for e in entries.values() if e.get("type") == "fact")
        n_tags = len(data.get("tag_index", {}))

        # Promedio de success_rate (solo patterns)
        rates = [
            e["stats"].get("success_rate", 1.0)
            for e in entries.values()
            if e.get("type") == "pattern" and "stats" in e
        ]
        avg_sr = sum(rates) / len(rates) if rates else 0.0

        d_entries = d_stats.get("total_entries", 0)
        d_lookups = d_stats.get("total_lookups", 0)
        d_hits = d_stats.get("total_hits", 0)

        stats[domain] = {
            "entries": d_entries,
            "lookups": d_lookups,
            "hits": d_hits,
            "patterns": n_patterns,
            "facts": n_facts,
            "tags_count": n_tags,
            "avg_success_rate": round(avg_sr, 3),
        }
        grand_entries += d_entries
        grand_lookups += d_lookups
        grand_hits += d_hits

    stats["total_entries"] = grand_entries
    stats["total_domains"] = len(all_domains)
    stats["total_lookups"] = grand_lookups
    stats["total_hits"] = grand_hits

    return stats


# ============================================================================
#  CLI
# ============================================================================

if __name__ == "__main__":
    _fix_windows_stdout()

    if len(sys.argv) < 2:
        print("Uso:")
        print("  python knowledge_base.py stats")
        print("  python knowledge_base.py domains")
        print("  python knowledge_base.py search <domain> [--tags t1,t2] [--query texto]")
        print("  python knowledge_base.py cross-search [--tags t1,t2] [--query texto]")
        print("  python knowledge_base.py export [domain] [--tags t1,t2] [--query texto]")
        print("  python knowledge_base.py ingest-rules <file.txt>")
        print("  python knowledge_base.py ingest-catalog <file.txt>")
        print("  python knowledge_base.py create-domain <nombre> \"<descripcion>\"")
        print(f"\nDominios: {list_domains()}")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "stats":
        print(json.dumps(get_global_stats(), indent=2))

    elif cmd == "domains":
        domains = _load_all_domains()
        if not domains:
            print("  (sin dominios)")
        for name, info in domains.items():
            print(f"  {name:20s}  {info.get('description', '')[:60]}")

    elif cmd == "create-domain" and len(sys.argv) >= 3:
        dname = sys.argv[2]
        ddesc = sys.argv[3] if len(sys.argv) > 3 else ""
        _ensure_domain(dname, ddesc)
        print(f"Dominio '{dname}' listo.")

    elif cmd == "search" and len(sys.argv) >= 3:
        domain = sys.argv[2]
        tags = None
        query = None
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--tags" and i + 1 < len(sys.argv):
                tags = [t.strip() for t in sys.argv[i + 1].split(",")]
                i += 2
            elif sys.argv[i] == "--query" and i + 1 < len(sys.argv):
                query = sys.argv[i + 1]
                i += 2
            else:
                i += 1
        results = search(domain, tags=tags, text_query=query)
        for r in results:
            print(json.dumps(r, indent=2, ensure_ascii=False))

    elif cmd == "cross-search":
        tags = None
        query = None
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--tags" and i + 1 < len(sys.argv):
                tags = [t.strip() for t in sys.argv[i + 1].split(",")]
                i += 2
            elif sys.argv[i] == "--query" and i + 1 < len(sys.argv):
                query = sys.argv[i + 1]
                i += 2
            else:
                i += 1
        results = cross_domain_search(tags=tags, text_query=query)
        for domain, entries in results.items():
            print(f"\n-- {domain} --")
            for r in entries:
                content = r.get("fact", r.get("solution", {}))
                print(
                    f"  [{r['key']}] "
                    f"{content.get('rule', content.get('strategy', ''))}"
                )

    elif cmd == "export":
        domain = (
            sys.argv[2]
            if len(sys.argv) > 2 and not sys.argv[2].startswith("--")
            else None
        )
        tags = None
        query = None
        i = 3 if domain else 2
        while i < len(sys.argv):
            if sys.argv[i] == "--tags" and i + 1 < len(sys.argv):
                tags = [t.strip() for t in sys.argv[i + 1].split(",")]
                i += 2
            elif sys.argv[i] == "--query" and i + 1 < len(sys.argv):
                query = sys.argv[i + 1]
                i += 2
            else:
                i += 1
        print(export_context(domain, tags=tags, text_query=query))

    elif cmd == "ingest-rules" and len(sys.argv) >= 3:
        fpath = sys.argv[2]
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            print(f"Archivo no encontrado: {fpath}")
            sys.exit(1)
        ids = ingest_business_rules_from_text(text, source=fpath)
        print(f"{len(ids)} reglas importadas")

    elif cmd == "ingest-catalog" and len(sys.argv) >= 3:
        fpath = sys.argv[2]
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            print(f"Archivo no encontrado: {fpath}")
            sys.exit(1)
        ids = ingest_catalog_from_text(text, source=fpath)
        print(f"{len(ids)} productos importados")

    else:
        print(f"Comando desconocido: {cmd}")
