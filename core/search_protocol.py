#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
search_protocol.py
===================
Protocolo de búsqueda inteligente:
1. KB primero
2. Internet si falta info
3. ML para completar

Retorna: (respuesta, fuentes_dict)
"""

import sys
from pathlib import Path
import json

# Importar timezone_utils - manejar ambos tipos de import
try:
    from .timezone_utils import format_ca_datetime
except ImportError:
    # Fallback - crear función simple si no existe
    def format_ca_datetime():
        from datetime import datetime
        now = datetime.now()
        return now.strftime("%d-%m-%Y %H:%M:%S")

def search_kb(query: str, domain: str = None, limit: int = 5) -> list:
    """
    Busca en la knowledge base local.
    Retorna lista de resultados con score.
    """
    kb_dir = Path(r"C:\Hooks_IA\knowledge")
    if not kb_dir.exists():
        return []

    results = []

    # Si tiene dominio específico, buscar ahí primero
    if domain:
        domains_to_search = [kb_dir / domain]
    else:
        domains_to_search = list(kb_dir.glob("*/"))

    for dom_dir in domains_to_search:
        if not dom_dir.is_dir():
            continue

        # Buscar en patterns.json
        patterns_f = dom_dir / "patterns.json"
        if patterns_f.exists():
            try:
                data = json.loads(patterns_f.read_text(encoding="utf-8"))
                entries = data.get("entries", {})
                for key, entry in entries.items():
                    if isinstance(entry, dict):
                        text = str(entry).lower()
                        if query.lower() in text:
                            results.append({
                                "source": "KB",
                                "domain": dom_dir.name,
                                "key": key,
                                "entry": entry,
                                "type": "pattern"
                            })
            except Exception:
                pass

        # Buscar en facts.json
        facts_f = dom_dir / "facts.json"
        if facts_f.exists():
            try:
                data = json.loads(facts_f.read_text(encoding="utf-8"))
                entries = data.get("entries", {})
                for key, entry in entries.items():
                    if isinstance(entry, dict):
                        text = str(entry).lower()
                        if query.lower() in text:
                            results.append({
                                "source": "KB",
                                "domain": dom_dir.name,
                                "key": key,
                                "entry": entry,
                                "type": "fact"
                            })
            except Exception:
                pass

    return results[:limit]


def calculate_coverage(query: str, kb_results: list) -> dict:
    """
    Calcula qué % de la pregunta puede responder la KB.
    Retorna: {
        'kb_coverage': 0-100,
        'needs_internet': bool,
        'needs_ml': bool
    }
    """
    if not kb_results:
        return {
            "kb_coverage": 0,
            "needs_internet": True,
            "needs_ml": True
        }

    # Heurística simple: si hay resultados, asumir 60% coverage
    # (esto se puede mejorar con análisis semántico)
    coverage = min(100, 30 + len(kb_results) * 20)

    return {
        "kb_coverage": coverage,
        "needs_internet": coverage < 80,
        "needs_ml": coverage < 100
    }


def build_source_footer(kb_pct: int, internet_pct: int, ml_pct: int) -> str:
    """
    Construye el footer con fuentes.
    """
    sources = []
    if kb_pct > 0:
        sources.append(f"KB {kb_pct}%")
    if internet_pct > 0:
        sources.append(f"Internet {internet_pct}%")
    if ml_pct > 0:
        sources.append(f"ML {ml_pct}%")

    if not sources:
        sources = ["ML 100%"]

    # Verificar que suma 100
    total = sum([kb_pct, internet_pct, ml_pct])
    if total != 100:
        # Ajustar ML si hay diferencia
        ml_pct = 100 - kb_pct - internet_pct
        sources = []
        if kb_pct > 0:
            sources.append(f"KB {kb_pct}%")
        if internet_pct > 0:
            sources.append(f"Internet {internet_pct}%")
        if ml_pct > 0:
            sources.append(f"ML {ml_pct}%")

    return "**Fuentes:** " + " + ".join(sources)


def detect_domain(query: str) -> str:
    """
    Detecta el dominio más relevante basado en la query.
    Retorna el nombre del dominio.
    """
    query_lower = query.lower()

    domain_keywords = {
        "sap_tierra": ["sap", "crm", "webui", "oportunidad", "cliente", "contrato"],
        "sap_automation": ["automation", "playbook", "rpa", "bot"],
        "sap_cloud": ["fiori", "cloud", "s4hana"],
        "sap_js_internals": ["selector", "javascript", "dom", "element"],
        "monday_automation": ["monday", "api", "graphql"],
        "web_forms": ["form", "input", "formulario", "campo"],
        "claude_chrome": ["chrome", "browser", "navegador"],
        "outlook": ["email", "correo", "outlook", "inbox"],
        "files": ["archivo", "carpeta", "path", "directorio"],
        "sessions": ["sesion", "context", "transcript"],
        "general": ["general", "misc"],
    }

    # Buscar coincidencias
    scores = {}
    for domain, keywords in domain_keywords.items():
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > 0:
            scores[domain] = score

    if scores:
        return max(scores, key=scores.get)
    return "general"


def save_to_kb(query: str, answer: str, domain: str = None) -> dict:
    """
    Guarda una pregunta + respuesta en la KB local.
    Retorna: {'saved': bool, 'domain': str, 'key': str}
    """
    if not domain:
        domain = detect_domain(query)

    kb_dir = Path(r"C:\Hooks_IA\knowledge")
    domain_dir = kb_dir / domain
    domain_dir.mkdir(parents=True, exist_ok=True)

    # Usar facts.json para respuestas (más flexible que patterns)
    facts_file = domain_dir / "facts.json"

    # Cargar facts existentes
    facts_data = {"entries": {}}
    if facts_file.exists():
        try:
            facts_data = json.loads(facts_file.read_text(encoding="utf-8"))
        except Exception:
            facts_data = {"entries": {}}

    # Crear nueva entrada
    import hashlib
    from datetime import datetime

    # Key basado en hash de query + timestamp
    now_str = format_ca_datetime()
    key = hashlib.md5(f"{query}_{now_str}".encode()).hexdigest()[:12]

    facts_data["entries"][key] = {
        "query": query,
        "answer": answer,
        "timestamp": now_str,
        "domain": domain,
        "source": "auto_learned"  # Indica que fue aprendido automáticamente
    }

    # Guardar
    try:
        facts_file.write_text(
            json.dumps(facts_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return {
            "saved": True,
            "domain": domain,
            "key": key,
            "file": str(facts_file)
        }
    except Exception as e:
        return {
            "saved": False,
            "error": str(e)
        }


def should_save_to_kb(kb_pct: int, internet_pct: int, ml_pct: int) -> bool:
    """
    Determina si debería guardarse la respuesta en la KB.
    Condición: KB_pct == 0 (no encontré nada) Y respuesta vino de Internet o ML
    """
    return kb_pct == 0 and (internet_pct > 0 or ml_pct > 0)


if __name__ == "__main__":
    # Test
    results = search_kb("hooks")
    print(f"Encontrados {len(results)} resultados para 'hooks'")
    for r in results[:2]:
        print(f"  - {r['domain']}: {r['key']}")

    coverage = calculate_coverage("hooks", results)
    print(f"Coverage: {coverage['kb_coverage']}%")
    print(build_source_footer(60, 20, 20))

    # Test save
    print("\n--- Test save_to_kb ---")
    test_result = save_to_kb(
        "¿Cómo configurar autenticación SSO en SAP?",
        "La autenticación SSO en SAP se configura mediante SAML2...",
        "sap_cloud"
    )
    print(f"Guardado: {test_result['saved']}")
    if test_result['saved']:
        print(f"Domain: {test_result['domain']}, Key: {test_result['key']}")
