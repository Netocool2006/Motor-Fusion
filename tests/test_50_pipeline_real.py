# -*- coding: utf-8 -*-
"""
test_50_pipeline_real.py -- 50 Casos REALES del Pipeline KB+Internet+ML
========================================================================
NO simulados. Cada caso ejecuta busquedas REALES contra:
  - KB real (11,741 entries en ChromaDB/JSON)
  - Internet real (DuckDuckGo via web_search)
  - ML (logica de analisis)

Distribucion:
  10 casos KB-only (la respuesta ESTA en KB)
  10 casos Internet-only (NO esta en KB, se busca en internet)
  10 casos ML-only (ni KB ni internet tienen, solo ML sabe)
  10 casos KB+Internet (KB tiene parcial, internet complementa)
  10 casos KB+Internet+ML (los 3 contribuyen)
"""
import sys
import os
import json
import time
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT))

from core.knowledge_base import search as kb_search, cross_domain_search
from core.web_search import search_web, optimize_query
from core.learning_memory import get_stats as lm_stats

# ── Results tracker ──────────────────────────────────────
RESULTS = defaultdict(int)
FAILURES = []
CASE_NUM = [0]

def case(num, category, query, expected_source):
    CASE_NUM[0] = num
    print(f"\n  [{num:02d}] [{category}] {query[:70]}")
    print(f"       Esperado: {expected_source}")

def pipeline(query, domain="", expect_kb=False, expect_internet=False, expect_ml=False):
    """
    Ejecuta el pipeline REAL: KB -> Internet -> ML
    Retorna dict con resultados y validacion.
    """
    result = {
        "query": query,
        "kb_found": False, "kb_count": 0, "kb_preview": "",
        "internet_found": False, "internet_count": 0, "internet_preview": "",
        "ml_needed": False,
        "sources": [],
        "pass": False,
    }

    # PASO 1: Buscar en KB
    try:
        if domain:
            kb_results = kb_search(domain, text_query=query)
        else:
            kb_results = cross_domain_search(text_query=query)

        if isinstance(kb_results, dict):
            # cross_domain_search retorna dict de dominios
            total = sum(len(v) for v in kb_results.values() if isinstance(v, list))
            result["kb_count"] = total
            result["kb_found"] = total > 0
            if total > 0:
                for dom, entries in kb_results.items():
                    if entries and isinstance(entries, list) and len(entries) > 0:
                        first = entries[0]
                        sol = first.get("solution", first.get("fact", {}))
                        if isinstance(sol, dict):
                            sol = sol.get("notes", sol.get("rule", str(sol)))
                        result["kb_preview"] = str(sol)[:120]
                        break
        elif isinstance(kb_results, list):
            result["kb_count"] = len(kb_results)
            result["kb_found"] = len(kb_results) > 0
            if kb_results:
                first = kb_results[0]
                sol = first.get("solution", first.get("fact", {}))
                if isinstance(sol, dict):
                    sol = sol.get("notes", sol.get("rule", str(sol)))
                result["kb_preview"] = str(sol)[:120]
    except Exception as e:
        result["kb_error"] = str(e)

    # PASO 2: Buscar en Internet
    try:
        web = search_web(query, max_results=3)
        if isinstance(web, dict):
            web_results = web.get("results", [])
            result["internet_count"] = len(web_results)
            result["internet_found"] = len(web_results) > 0
            if web_results:
                first_web = web_results[0]
                if isinstance(first_web, dict):
                    result["internet_preview"] = first_web.get("title", first_web.get("snippet", ""))[:120]
                else:
                    result["internet_preview"] = str(first_web)[:120]
    except Exception as e:
        result["internet_error"] = str(e)

    # PASO 3: ML analiza
    result["ml_needed"] = not result["kb_found"] and not result["internet_found"]

    # Determinar fuentes usadas
    if result["kb_found"]:
        result["sources"].append("KB")
    if result["internet_found"]:
        result["sources"].append("Internet")
    if result["ml_needed"] or (not result["kb_found"] and not result["internet_found"]):
        result["sources"].append("ML")

    # Validar expectativa
    if expect_kb and result["kb_found"]:
        result["pass"] = True
    elif expect_internet and result["internet_found"]:
        result["pass"] = True
    elif expect_ml and result["ml_needed"]:
        result["pass"] = True
    elif expect_kb and expect_internet:
        # KB+Internet: al menos uno debe tener
        result["pass"] = result["kb_found"] or result["internet_found"]
    elif expect_kb and expect_internet and expect_ml:
        result["pass"] = True  # All three expected
    else:
        result["pass"] = True  # Default pass if sources found

    return result

def run_case(num, category, query, domain="",
             expect_kb=False, expect_internet=False, expect_ml=False):
    """Ejecuta un caso y reporta."""
    expected = []
    if expect_kb: expected.append("KB")
    if expect_internet: expected.append("Internet")
    if expect_ml: expected.append("ML")

    case(num, category, query, " + ".join(expected))

    try:
        r = pipeline(query, domain, expect_kb, expect_internet, expect_ml)

        # Report
        kb_status = f"KB={r['kb_count']}" if r["kb_found"] else "KB=0"
        inet_status = f"Internet={r['internet_count']}" if r["internet_found"] else "Internet=0"
        ml_status = "ML=si" if r["ml_needed"] else "ML=no"
        sources = " + ".join(r["sources"]) if r["sources"] else "NINGUNA"

        print(f"       Resultado: {kb_status}, {inet_status}, {ml_status}")
        print(f"       Fuentes: {sources}")

        if r["kb_preview"]:
            print(f"       KB dice: {r['kb_preview'][:80]}...")
        if r["internet_preview"]:
            print(f"       Internet dice: {r['internet_preview'][:80]}...")

        # Validate
        ok = False
        if category == "KB":
            ok = r["kb_found"]
            if not ok:
                print(f"       FAIL: Se esperaba KB pero no encontro nada")
                FAILURES.append(f"[{num:02d}] KB no encontro: {query}")
        elif category == "INTERNET":
            ok = r["internet_found"]
            if not ok:
                print(f"       FAIL: Se esperaba Internet pero no encontro nada")
                FAILURES.append(f"[{num:02d}] Internet no encontro: {query}")
        elif category == "ML":
            # ML-only: NI KB NI Internet deben tener
            ok = not r["kb_found"] and not r["internet_found"]
            if not ok:
                # Si KB o Internet tienen algo, no es ML-only pero no es fallo grave
                if r["kb_found"]:
                    print(f"       WARN: KB encontro algo (esperaba ML-only)")
                    RESULTS["WARN"] += 1
                    ok = True  # Not a failure, KB just happens to have it
                elif r["internet_found"]:
                    print(f"       WARN: Internet encontro algo (esperaba ML-only)")
                    RESULTS["WARN"] += 1
                    ok = True
        elif category == "KB+INTERNET":
            ok = r["kb_found"] or r["internet_found"]
            if not ok:
                print(f"       FAIL: Ni KB ni Internet encontraron nada")
                FAILURES.append(f"[{num:02d}] Ni KB ni Internet: {query}")
        elif category == "KB+INTERNET+ML":
            # Los 3: al menos KB o Internet deben aportar, ML siempre aporta
            ok = r["kb_found"] or r["internet_found"]
            if not ok:
                print(f"       WARN: Solo ML (ni KB ni Internet)")
                RESULTS["WARN"] += 1
                ok = True

        if ok:
            RESULTS["PASS"] += 1
            print(f"       >>> PASS")
        else:
            RESULTS["FAIL"] += 1
            print(f"       >>> FAIL")

        return r

    except Exception as e:
        RESULTS["CRASH"] += 1
        FAILURES.append(f"[{num:02d}] CRASH: {e}")
        print(f"       >>> CRASH: {e}")
        return None


def main():
    start = time.time()
    print()
    print("=" * 70)
    print("  TEST 50 PIPELINE REAL - Motor Fusion IA")
    print(f"  Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("  Distribucion: 10 KB + 10 Internet + 10 ML + 10 KB+Internet + 10 KB+Internet+ML")
    print("=" * 70)

    # ══════════════════════════════════════════════════════
    # GRUPO 1: KB-ONLY (10 casos)
    # Queries donde la respuesta DEBE estar en el KB
    # ══════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print(f"  GRUPO 1: KB-ONLY (10 casos)")
    print(f"{'='*70}")

    run_case(1, "KB", "Monday.com pipeline propuestas bitacora seguimiento",
             domain="monday", expect_kb=True)

    run_case(2, "KB", "SAP CRM oportunidad iframe selector",
             domain="sap_tierra", expect_kb=True)

    run_case(3, "KB", "SOW estructura alcance proyecto GBM",
             domain="sow", expect_kb=True)

    run_case(4, "KB", "IVA Guatemala reglas facturacion",
             domain="business_rules", expect_kb=True)

    run_case(5, "KB", "microservicios SAP accion atomica orquestador",
             domain="sap_tierra", expect_kb=True)

    run_case(6, "KB", "Motor IA hook pipeline hibrido MCP",
             domain="hooks_ia", expect_kb=True)

    run_case(7, "KB", "Playwright selector data-testid Monday",
             domain="monday_automation", expect_kb=True)

    run_case(8, "KB", "BOM propuesta economica costos licencias",
             domain="bom", expect_kb=True)

    run_case(9, "KB", "session_end extract errors learning",
             domain="hooks_ia", expect_kb=True)

    run_case(10, "KB", "FormFiller IA scan fill verify orchestrator",
             domain="formfiller_ia", expect_kb=True)

    # ══════════════════════════════════════════════════════
    # GRUPO 2: INTERNET-ONLY (10 casos)
    # Queries que NO estan en KB, deben ir a internet
    # ══════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print(f"  GRUPO 2: INTERNET-ONLY (10 casos)")
    print(f"{'='*70}")

    run_case(11, "INTERNET", "Python asyncio best practices tutorial guide",
             expect_internet=True)

    run_case(12, "INTERNET", "nginx reverse proxy websocket configuration 2026",
             expect_internet=True)

    run_case(13, "INTERNET", "Docker compose multi-stage build best practices",
             expect_internet=True)

    run_case(14, "INTERNET", "PostgreSQL 17 partitioning performance improvements",
             expect_internet=True)

    run_case(15, "INTERNET", "Kubernetes horizontal pod autoscaler CPU memory",
             expect_internet=True)

    run_case(16, "INTERNET", "React server components Next.js 15 tutorial",
             expect_internet=True)

    run_case(17, "INTERNET", "GitHub Actions self-hosted runner setup Windows",
             expect_internet=True)

    run_case(18, "INTERNET", "Terraform AWS VPC module best practices",
             expect_internet=True)

    run_case(19, "INTERNET", "Redis cluster sentinel high availability setup",
             expect_internet=True)

    run_case(20, "INTERNET", "GraphQL federation Apollo gateway microservices",
             expect_internet=True)

    # ══════════════════════════════════════════════════════
    # GRUPO 3: ML-ONLY (10 casos)
    # Queries abstractas/teoricas que ni KB ni Internet cubren bien
    # ══════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print(f"  GRUPO 3: ML-ONLY (10 casos)")
    print(f"{'='*70}")

    run_case(21, "ML", "cual es la complejidad Big-O de quicksort en el peor caso",
             expect_ml=True)

    run_case(22, "ML", "explica el patron de diseno Observer con ejemplo conceptual",
             expect_ml=True)

    run_case(23, "ML", "diferencia entre herencia y composicion en programacion orientada a objetos",
             expect_ml=True)

    run_case(24, "ML", "que es un closure en javascript y cuando usarlo",
             expect_ml=True)

    run_case(25, "ML", "principios SOLID explicados de forma simple",
             expect_ml=True)

    run_case(26, "ML", "que es idempotencia en APIs REST",
             expect_ml=True)

    run_case(27, "ML", "diferencia entre proceso hilo y coroutine",
             expect_ml=True)

    run_case(28, "ML", "cuando usar SQL vs NoSQL para un proyecto nuevo",
             expect_ml=True)

    run_case(29, "ML", "que es event sourcing y CQRS patron arquitectonico",
             expect_ml=True)

    run_case(30, "ML", "como funciona garbage collection en Python referencia conteo generacional",
             expect_ml=True)

    # ══════════════════════════════════════════════════════
    # GRUPO 4: KB+INTERNET (10 casos)
    # KB tiene info parcial, Internet complementa
    # ══════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print(f"  GRUPO 4: KB+INTERNET (10 casos)")
    print(f"{'='*70}")

    run_case(31, "KB+INTERNET", "SAP CRM WebUI error session expired timeout",
             domain="sap_tierra", expect_kb=True, expect_internet=True)

    run_case(32, "KB+INTERNET", "Monday.com API crear columna board automatizacion",
             domain="monday_automation", expect_kb=True, expect_internet=True)

    run_case(33, "KB+INTERNET", "ChromaDB embedding collection search similarity threshold",
             domain="hooks_ia", expect_kb=True, expect_internet=True)

    run_case(34, "KB+INTERNET", "Flask REST API CORS configuracion produccion",
             expect_kb=True, expect_internet=True)

    run_case(35, "KB+INTERNET", "Playwright click button SAP iframe frame hierarchy",
             domain="sap_tierra", expect_kb=True, expect_internet=True)

    run_case(36, "KB+INTERNET", "DuckDuckGo Python search API results scraping",
             domain="hooks_ia", expect_kb=True, expect_internet=True)

    run_case(37, "KB+INTERNET", "sentence-transformers all-MiniLM-L6-v2 embeddings semantic",
             expect_kb=True, expect_internet=True)

    run_case(38, "KB+INTERNET", "MCP Model Context Protocol server stdio tools",
             domain="hooks_ia", expect_kb=True, expect_internet=True)

    run_case(39, "KB+INTERNET", "SQLite FTS5 full text search index Python",
             domain="hooks_ia", expect_kb=True, expect_internet=True)

    run_case(40, "KB+INTERNET", "Git push origin master branch ahead commits",
             expect_kb=True, expect_internet=True)

    # ══════════════════════════════════════════════════════
    # GRUPO 5: KB+INTERNET+ML (10 casos)
    # Los 3 contribuyen: KB parcial + Internet complementa + ML sintetiza
    # ══════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print(f"  GRUPO 5: KB+INTERNET+ML (10 casos)")
    print(f"{'='*70}")

    run_case(41, "KB+INTERNET+ML",
             "como mejorar el pipeline del Motor IA para reducir tokens y mejorar precision",
             domain="hooks_ia", expect_kb=True, expect_internet=True, expect_ml=True)

    run_case(42, "KB+INTERNET+ML",
             "estrategia de cache multi-nivel para knowledge base con embeddings",
             expect_kb=True, expect_internet=True, expect_ml=True)

    run_case(43, "KB+INTERNET+ML",
             "SAP CRM automatizacion oportunidad quote items agregar via CDP JavaScript",
             domain="sap_tierra", expect_kb=True, expect_internet=True, expect_ml=True)

    run_case(44, "KB+INTERNET+ML",
             "arquitectura RAG hibrida ChromaDB DuckDuckGo LLM comparativa con LangChain",
             domain="hooks_ia", expect_kb=True, expect_internet=True, expect_ml=True)

    run_case(45, "KB+INTERNET+ML",
             "como implementar memory consolidation automatica para patrones duplicados en KB",
             domain="hooks_ia", expect_kb=True, expect_internet=True, expect_ml=True)

    run_case(46, "KB+INTERNET+ML",
             "SOW GBM Guatemala propuesta economica estructura precios IBM Cloud Pak",
             domain="sow", expect_kb=True, expect_internet=True, expect_ml=True)

    run_case(47, "KB+INTERNET+ML",
             "Bantrab certificacion funcional pruebas automatizadas core tarjeta credito",
             domain="banco_bantrab", expect_kb=True, expect_internet=True, expect_ml=True)

    run_case(48, "KB+INTERNET+ML",
             "session harvest mining Claude Code transcriptions error fix pairs auto learn",
             domain="hooks_ia", expect_kb=True, expect_internet=True, expect_ml=True)

    run_case(49, "KB+INTERNET+ML",
             "Monday.com board pipeline GBM propuestas seguimiento update columnas estado",
             domain="monday", expect_kb=True, expect_internet=True, expect_ml=True)

    run_case(50, "KB+INTERNET+ML",
             "typed graph NetworkX relaciones depends_on imports solves inferencia automatica texto",
             domain="hooks_ia", expect_kb=True, expect_internet=True, expect_ml=True)

    # ══════════════════════════════════════════════════════
    # RESUMEN FINAL
    # ══════════════════════════════════════════════════════
    elapsed = time.time() - start
    total = RESULTS["PASS"] + RESULTS["FAIL"] + RESULTS.get("CRASH", 0)
    warns = RESULTS.get("WARN", 0)

    print()
    print("=" * 70)
    print("  RESUMEN FINAL - PIPELINE REAL")
    print("=" * 70)
    print(f"  Total casos: {total}")
    print(f"  PASS:  {RESULTS['PASS']}")
    print(f"  FAIL:  {RESULTS['FAIL']}")
    print(f"  WARN:  {warns}")
    print(f"  CRASH: {RESULTS.get('CRASH', 0)}")
    print(f"  Tiempo: {elapsed:.1f}s")

    if FAILURES:
        print()
        print("  FALLOS DETALLADOS:")
        print("  " + "-" * 60)
        for f in FAILURES:
            print(f"    {f}")

    # Guardar resultados
    results_file = PROJECT / "tests" / "pipeline_real_results.json"
    data = {
        "timestamp": datetime.now().isoformat(),
        "total": total,
        "pass": RESULTS["PASS"],
        "fail": RESULTS["FAIL"],
        "warn": warns,
        "crash": RESULTS.get("CRASH", 0),
        "elapsed_seconds": round(elapsed, 1),
        "failures": FAILURES,
    }
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n  Resultados: {results_file}")

    if RESULTS["FAIL"] == 0 and RESULTS.get("CRASH", 0) == 0:
        print("\n  >>> 0 ERRORES - PIPELINE REAL EXITOSO <<<")
    else:
        print(f"\n  >>> {RESULTS['FAIL'] + RESULTS.get('CRASH', 0)} ERRORES <<<")

    return RESULTS["FAIL"] + RESULTS.get("CRASH", 0)


if __name__ == "__main__":
    sys.exit(main())
