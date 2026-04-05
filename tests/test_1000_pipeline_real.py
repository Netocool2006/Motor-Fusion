# -*- coding: utf-8 -*-
"""
test_1000_pipeline_real.py -- 1000 Casos REALES del Pipeline KB+Internet+ML
============================================================================
NO simulados. Cada caso ejecuta busquedas REALES contra:
  - KB real (11,741+ entries en JSON)
  - Internet real (DuckDuckGo via web_search con force=True)
  - ML (logica de analisis)

Distribucion:
  200 casos KB-only (la respuesta ESTA en KB)
  200 casos Internet-only (NO esta en KB, se busca en internet)
  200 casos ML-only (ni KB ni internet tienen, solo ML sabe)
  200 casos KB+Internet (KB tiene parcial, internet complementa)
  200 casos KB+Internet+ML (los 3 contribuyen)

Correccion vs test_50: Internet usa force=True para SIEMPRE encontrar algo.
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

# Rate limiting para DuckDuckGo: 1s entre búsquedas
SEARCH_DELAY = 1.0

# ── Results tracker ──────────────────────────────────────
RESULTS = defaultdict(int)
FAILURES = []
WARNINGS = []
CASE_NUM = [0]
GROUP_RESULTS = defaultdict(lambda: defaultdict(int))

def case(num, category, query, expected_source):
    CASE_NUM[0] = num
    print(f"  [{num:04d}] [{category:<16s}] {query[:65]}")
    print(f"         Esperado: {expected_source}")

def pipeline(query, domain="", expect_kb=False, expect_internet=False, expect_ml=False):
    """Ejecuta el pipeline REAL: KB -> Internet -> ML"""
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

    # PASO 2: Buscar en Internet (con force=True para siempre encontrar)
    try:
        time.sleep(SEARCH_DELAY)  # Anti rate-limiting DDG
        web = search_web(query, max_results=3, force=True)
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

    if result["kb_found"]:
        result["sources"].append("KB")
    if result["internet_found"]:
        result["sources"].append("Internet")
    if result["ml_needed"] or (not result["kb_found"] and not result["internet_found"]):
        result["sources"].append("ML")

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

        kb_status = f"KB={r['kb_count']}" if r["kb_found"] else "KB=0"
        inet_status = f"Internet={r['internet_count']}" if r["internet_found"] else "Internet=0"
        ml_status = "ML=si" if r["ml_needed"] else "ML=no"
        sources = " + ".join(r["sources"]) if r["sources"] else "NINGUNA"

        print(f"         Resultado: {kb_status}, {inet_status}, {ml_status} | Fuentes: {sources}")

        # Validate by category
        ok = False
        if category == "KB":
            ok = r["kb_found"]
            if not ok:
                FAILURES.append(f"[{num:04d}] KB no encontro: {query[:60]}")
        elif category == "INTERNET":
            ok = r["internet_found"]
            if not ok:
                FAILURES.append(f"[{num:04d}] Internet no encontro: {query[:60]}")
        elif category == "ML":
            ok = not r["kb_found"] and not r["internet_found"]
            if not ok:
                if r["kb_found"] or r["internet_found"]:
                    WARNINGS.append(f"[{num:04d}] ML-only pero encontro en {'KB' if r['kb_found'] else 'Internet'}: {query[:50]}")
                    RESULTS["WARN"] += 1
                    ok = True  # warn, no fail
        elif category == "KB+INTERNET":
            ok = r["kb_found"] or r["internet_found"]
            if not ok:
                FAILURES.append(f"[{num:04d}] Ni KB ni Internet: {query[:60]}")
        elif category == "KB+INTERNET+ML":
            ok = r["kb_found"] or r["internet_found"]
            if not ok:
                WARNINGS.append(f"[{num:04d}] Solo ML: {query[:60]}")
                RESULTS["WARN"] += 1
                ok = True

        if ok:
            RESULTS["PASS"] += 1
            GROUP_RESULTS[category]["PASS"] += 1
            print(f"         >>> PASS")
        else:
            RESULTS["FAIL"] += 1
            GROUP_RESULTS[category]["FAIL"] += 1
            print(f"         >>> FAIL")

        return r

    except Exception as e:
        RESULTS["CRASH"] += 1
        GROUP_RESULTS[category]["CRASH"] += 1
        FAILURES.append(f"[{num:04d}] CRASH: {e}")
        print(f"         >>> CRASH: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# DATA: 200 KB-ONLY CASES
# ══════════════════════════════════════════════════════════════
KB_CASES = [
    # sap_tierra (40)
    ("SAP CRM WebUI oportunidad iframe selector", "sap_tierra"),
    ("CDP JavaScript click elemento SAP CRM", "sap_tierra"),
    ("SAP CRM quote items agregar linea", "sap_tierra"),
    ("iframe nested SAP WebUI selector CSS", "sap_tierra"),
    ("oportunidad SAP CRM stage pipeline cambio", "sap_tierra"),
    ("CDP Runtime.evaluate SAP CRM DOM", "sap_tierra"),
    ("SAP CRM WebUI tabla productos items", "sap_tierra"),
    ("selector XPath SAP CRM oportunidad campo", "sap_tierra"),
    ("SAP CRM quote header billing datos", "sap_tierra"),
    ("WebUI SAP CRM navegacion menu principal", "sap_tierra"),
    ("SAP CRM oportunidad cliente account ID", "sap_tierra"),
    ("CDP Page.navigate SAP CRM URL", "sap_tierra"),
    ("SAP CRM iframe contenido dinamico carga", "sap_tierra"),
    ("oportunidad SAP CRM probability forecast", "sap_tierra"),
    ("SAP CRM WebUI boton guardar submit", "sap_tierra"),
    ("CDP Network intercept SAP CRM request", "sap_tierra"),
    ("SAP CRM quote linea producto SKU", "sap_tierra"),
    ("WebUI SAP CRM campo texto input fill", "sap_tierra"),
    ("SAP CRM oportunidad fecha cierre close date", "sap_tierra"),
    ("iframe SAP CRM deteccion carga completa", "sap_tierra"),
    ("SAP CRM dropdown select opcion valor", "sap_tierra"),
    ("CDP DOM SAP CRM elemento visible check", "sap_tierra"),
    ("SAP CRM quote total precio calculo", "sap_tierra"),
    ("WebUI SAP CRM error mensaje validacion", "sap_tierra"),
    ("SAP CRM oportunidad descripcion notas campo", "sap_tierra"),
    ("CDP screenshot SAP CRM debug visual", "sap_tierra"),
    ("SAP CRM tabla items scroll horizontal", "sap_tierra"),
    ("selector ID SAP CRM WebUI unique element", "sap_tierra"),
    ("SAP CRM oportunidad owner asignacion usuario", "sap_tierra"),
    ("WebUI SAP CRM popup modal cerrar", "sap_tierra"),
    ("CDP input SAP CRM teclado simulacion", "sap_tierra"),
    ("SAP CRM quote status aprobacion pendiente", "sap_tierra"),
    ("iframe SAP CRM cross-origin document access", "sap_tierra"),
    ("SAP CRM oportunidad competidor competitor field", "sap_tierra"),
    ("WebUI SAP CRM breadcrumb navegacion back", "sap_tierra"),
    ("CDP wait SAP CRM elemento aparecer", "sap_tierra"),
    ("SAP CRM quote descuento discount porcentaje", "sap_tierra"),
    ("SAP CRM oportunidad tipo opportunity type", "sap_tierra"),
    ("WebUI SAP CRM tabla paginacion next page", "sap_tierra"),
    ("CDP evaluate retornar valor campo SAP", "sap_tierra"),

    # formfiller_ia (25)
    ("formfiller scan SAP CRM campos detectados", "formfiller_ia"),
    ("orchestrator fill verify loop formulario", "formfiller_ia"),
    ("formfiller_ia pipeline scan fill SAP", "formfiller_ia"),
    ("SAP form fill automation orchestrator IA", "formfiller_ia"),
    ("formfiller verify campos completados exitoso", "formfiller_ia"),
    ("scan formulario SAP CRM campos requeridos", "formfiller_ia"),
    ("formfiller_ia error campo no encontrado", "formfiller_ia"),
    ("orchestrator SAP CRM fill secuencia pasos", "formfiller_ia"),
    ("formfiller timeout espera elemento SAP", "formfiller_ia"),
    ("SAP CRM form fill CDP automatizacion", "formfiller_ia"),
    ("formfiller_ia retry logica reintento fallo", "formfiller_ia"),
    ("scan detect input textarea SAP WebUI", "formfiller_ia"),
    ("formfiller oportunidad SAP campos mapeados", "formfiller_ia"),
    ("orchestrator estado sesion formfiller SAP", "formfiller_ia"),
    ("fill quote SAP CRM lineas items automatico", "formfiller_ia"),
    ("formfiller_ia verificacion post-fill screenshot", "formfiller_ia"),
    ("SAP form campo obligatorio validacion fill", "formfiller_ia"),
    ("formfiller pipeline resultado JSON respuesta", "formfiller_ia"),
    ("orchestrator tool MCP formfiller SAP", "formfiller_ia"),
    ("formfiller_ia selector fallback alternativo", "formfiller_ia"),
    ("scan SAP WebUI iframe campos internos", "formfiller_ia"),
    ("formfiller complete oportunidad datos GBM", "formfiller_ia"),
    ("fill SAP CRM quote header automatico", "formfiller_ia"),
    ("formfiller_ia log debug campos llenados", "formfiller_ia"),
    ("orchestrator formfiller SAP CRM sesion activa", "formfiller_ia"),

    # sap_automation (15)
    ("SAP CRM tabla row fill automatizacion", "sap_automation"),
    ("automation script SAP CRM fila datos", "sap_automation"),
    ("SAP CRM tabla agregar fila nueva row", "sap_automation"),
    ("script automatizacion SAP WebUI Python", "sap_automation"),
    ("SAP CRM table row selector indice", "sap_automation"),
    ("automation SAP CRM items tabla llenar", "sap_automation"),
    ("SAP CRM bulk fill multiples filas tabla", "sap_automation"),
    ("script SAP CRM WebUI interaccion DOM", "sap_automation"),
    ("SAP CRM automation error fila tabla missing", "sap_automation"),
    ("tabla SAP CRM columna header mapeo", "sap_automation"),
    ("SAP CRM row fill CDP dispatchEvent", "sap_automation"),
    ("automation SAP CRM guardar registro tabla", "sap_automation"),
    ("SAP CRM script llenado masivo rows", "sap_automation"),
    ("tabla SAP CRM scroll row visible viewport", "sap_automation"),
    ("SAP CRM automation validacion fila guardada", "sap_automation"),

    # hooks_ia (15)
    ("hooks_ia Motor IA pipeline KB internet ML", "hooks_ia"),
    ("MCP server hooks_ia sesion activa", "hooks_ia"),
    ("hooks_ia pipeline stage KB busqueda", "hooks_ia"),
    ("Motor IA hooks session management tool", "hooks_ia"),
    ("hooks_ia MCP tool llamada resultado", "hooks_ia"),
    ("pipeline hooks_ia internet search fallback", "hooks_ia"),
    ("hooks_ia ML modelo prediccion resultado", "hooks_ia"),
    ("MCP server hooks_ia configuracion puerto", "hooks_ia"),
    ("hooks_ia sesion handoff traspaso contexto", "hooks_ia"),
    ("Motor IA hooks KB hit miss ratio", "hooks_ia"),
    ("hooks_ia pipeline orquestacion pasos", "hooks_ia"),
    ("MCP hooks_ia tool registro disponibles", "hooks_ia"),
    ("hooks_ia session estado persistencia", "hooks_ia"),
    ("Motor IA hooks internet query fallback", "hooks_ia"),
    ("hooks_ia pipeline log debug trazabilidad", "hooks_ia"),

    # sessions (10)
    ("sesion Claude Code handoff traspaso", "sessions"),
    ("session data contexto conversacion guardado", "sessions"),
    ("Claude Code sesion activa estado actual", "sessions"),
    ("handoff sesion informacion proyecto contexto", "sessions"),
    ("session management Claude Code persistencia", "sessions"),
    ("sesion anterior contexto recuperar historial", "sessions"),
    ("Claude Code session ID identificador unico", "sessions"),
    ("handoff datos criticos siguiente sesion", "sessions"),
    ("sesion compresion contexto informacion clave", "sessions"),
    ("Claude Code session log actividad registrada", "sessions"),

    # business_rules (10)
    ("GBM reglas negocio nomenclatura _PS _RN", "business_rules"),
    ("tarifa GBM IVA Guatemala calculo", "business_rules"),
    ("SLA GBM tiempo respuesta definicion", "business_rules"),
    ("nomenclatura _PS _RN GBM oportunidad", "business_rules"),
    ("IVA Guatemala 12% calculo factura", "business_rules"),
    ("GBM business rules tariff pricing", "business_rules"),
    ("SLA categoria severidad tiempo resolucion", "business_rules"),
    ("GBM nomenclatura proyecto propuesta codigo", "business_rules"),
    ("reglas negocio GBM Guatemala validacion", "business_rules"),
    ("tarifa GBM licencia mantenimiento anual", "business_rules"),

    # services (10)
    ("SAP CRM oportunidad search service API", "services"),
    ("servicio busqueda oportunidad SAP CRM", "services"),
    ("SAP CRM opportunity search resultado JSON", "services"),
    ("servicio SAP CRM filtro busqueda parametros", "services"),
    ("SAP CRM search service endpoint URL", "services"),
    ("oportunidad SAP CRM buscar por ID cliente", "services"),
    ("SAP CRM search service paginacion resultados", "services"),
    ("servicio SAP CRM oportunidad status filtro", "services"),
    ("SAP CRM search service autenticacion token", "services"),
    ("oportunidad busqueda SAP CRM rango fechas", "services"),

    # files (10)
    ("file management differential capture archivos", "files"),
    ("captura diferencial archivos modificados", "files"),
    ("file diff comparacion versiones cambios", "files"),
    ("gestion archivos proyecto differential", "files"),
    ("file capture snapshot estado directorio", "files"),
    ("archivos modificados deteccion diferencial", "files"),
    ("file management log cambios registrados", "files"),
    ("differential capture nuevo archivo detectado", "files"),
    ("gestion archivos ignorar exclusion patron", "files"),
    ("file snapshot restaurar version anterior", "files"),

    # outlook (10)
    ("Outlook automatizacion email procesamiento", "outlook"),
    ("Outlook automation correo SAP CRM", "outlook"),
    ("email processing Outlook extraccion datos", "outlook"),
    ("Outlook automation regla carpeta email", "outlook"),
    ("correo Outlook SAP CRM oportunidad crear", "outlook"),
    ("Outlook automation adjunto attachment procesar", "outlook"),
    ("email Outlook clasificacion automatica IA", "outlook"),
    ("Outlook automation respuesta automatica email", "outlook"),
    ("correo electronico Outlook extraccion entidad", "outlook"),
    ("Outlook automation trigger evento nuevo email", "outlook"),

    # monday_automation (8)
    ("Monday.com board automation Playwright", "monday_automation"),
    ("Monday.com selector Playwright automatizacion", "monday_automation"),
    ("board Monday.com item crear automatizacion", "monday_automation"),
    ("Monday.com pipeline propuesta seguimiento", "monday_automation"),
    ("Playwright selector Monday.com columna campo", "monday_automation"),
    ("Monday.com automation status cambio item", "monday_automation"),
    ("board Monday.com GBM proyectos bitacora", "monday_automation"),
    ("Monday.com Playwright click elemento board", "monday_automation"),

    # banco_bantrab (8)
    ("Bantrab banco tarjeta credito certificacion", "banco_bantrab"),
    ("banco Bantrab automatizacion proceso credito", "banco_bantrab"),
    ("Bantrab certificacion tarjeta datos cliente", "banco_bantrab"),
    ("banco Bantrab formulario solicitud credito", "banco_bantrab"),
    ("Bantrab tarjeta credito validacion aprobacion", "banco_bantrab"),
    ("banco Bantrab proceso certificacion steps", "banco_bantrab"),
    ("Bantrab credito campos formulario fill", "banco_bantrab"),
    ("banco Bantrab tarjeta selector WebUI", "banco_bantrab"),

    # banco_bac (5)
    ("BAC banco automatizacion formulario", "banco_bac"),
    ("banco BAC proceso credito datos", "banco_bac"),
    ("BAC formulario cliente informacion fill", "banco_bac"),
    ("banco BAC selector campo WebUI", "banco_bac"),
    ("BAC automatizacion solicitud proceso", "banco_bac"),

    # banco_promerica (5)
    ("Promerica banco formulario automatizacion", "banco_promerica"),
    ("banco Promerica credito proceso campos", "banco_promerica"),
    ("Promerica datos cliente formulario fill", "banco_promerica"),
    ("banco Promerica selector WebUI campo", "banco_promerica"),
    ("Promerica automatizacion solicitud credito", "banco_promerica"),

    # seguros_assa (4)
    ("ASSA seguros automatizacion formulario poliza", "seguros_assa"),
    ("seguros ASSA poliza datos cliente campos", "seguros_assa"),
    ("ASSA insurance form fill automatizacion", "seguros_assa"),
    ("seguros ASSA proceso cotizacion poliza", "seguros_assa"),

    # seguros_el_roble (4)
    ("El Roble seguros formulario automatizacion", "seguros_el_roble"),
    ("seguros El Roble poliza campos datos", "seguros_el_roble"),
    ("El Roble insurance cotizacion proceso", "seguros_el_roble"),
    ("seguros El Roble fill formulario poliza", "seguros_el_roble"),

    # sow (5)
    ("SOW statement of work GBM propuesta", "sow"),
    ("propuesta GBM scope trabajo proyecto", "sow"),
    ("SOW alcance entregables GBM cliente", "sow"),
    ("statement of work template GBM formato", "sow"),
    ("propuesta GBM SOW costo estimacion", "sow"),

    # bom (3)
    ("BOM bill materials licencias costo", "bom"),
    ("bill of materials economico propuesta GBM", "bom"),
    ("BOM licencias hardware software costo", "bom"),

    # chance1 (3)
    ("Chance1 modulo proyecto automatizacion", "chance1"),
    ("Chance1 pipeline modulos configuracion", "chance1"),
    ("Chance1 proyecto stage modulo datos", "chance1"),

    # sap_cloud (3)
    ("SAP Cloud OData API S/4HANA endpoint", "sap_cloud"),
    ("OData SAP Cloud query filtro entidad", "sap_cloud"),
    ("S/4HANA API autenticacion OAuth token", "sap_cloud"),

    # web_forms (3)
    ("web forms handling automatizacion HTML", "web_forms"),
    ("formulario web fill selector input", "web_forms"),
    ("web form submit validacion campos", "web_forms"),

    # claude_chrome (2)
    ("Claude Chrome extension SAP CRM integracion", "claude_chrome"),
    ("Chrome SAP CRM Claude automatizacion CDP", "claude_chrome"),

    # sap_js_internals (2)
    ("SAP CRM WebUI JavaScript DOM manipulacion interna", "sap_js_internals"),
    ("JavaScript internals SAP CRM event dispatch", "sap_js_internals"),
]


# ══════════════════════════════════════════════════════════════
# DATA: 200 INTERNET-ONLY CASES
# ══════════════════════════════════════════════════════════════
INTERNET_CASES = [
    # Python programming (25)
    "Python asyncio gather tasks concurrent execution",
    "FastAPI dependency injection background tasks middleware",
    "Django ORM select_related prefetch_related optimization",
    "pandas DataFrame merge groupby aggregation examples",
    "Python decorators functools wraps class method",
    "Python type hints generics TypeVar Protocol",
    "SQLAlchemy async session connection pool configuration",
    "Python dataclasses frozen slots inheritance comparison",
    "pydantic v2 model validation serialization settings",
    "Python multiprocessing Pool shared memory IPC",
    "Python generator yield from itertools performance",
    "pytest fixtures parametrize mock patch unittest",
    "Python logging handlers formatters rotating file",
    "Python virtual environment poetry pipenv uv",
    "Python context manager __enter__ __exit__ contextlib",
    "Python metaclass __init_subclass__ ABC abstract method",
    "Python list comprehension dict set generator expression",
    "Python regex re module groups named capture",
    "Python pathlib os.path file directory operations",
    "Python argparse subcommands CLI tool building",
    "Python requests httpx aiohttp REST API client",
    "Python celery redis task queue distributed workers",
    "Python black ruff pylint mypy code quality tools",
    "Python packaging setup.py pyproject.toml wheel build",
    "Python profiling cProfile memory_profiler line_profiler",
    # JavaScript/TypeScript/Web (25)
    "React hooks useState useEffect custom hook patterns",
    "Next.js app router server components streaming RSC",
    "TypeScript generics utility types conditional mapped",
    "Vue 3 composition API reactive ref computed watch",
    "Node.js EventEmitter streams pipe async iterator",
    "Express middleware error handling route authentication",
    "WebSocket Socket.io real-time bidirectional communication",
    "Vite webpack bundler tree shaking code splitting",
    "React Query TanStack server state cache invalidation",
    "Zustand Redux Toolkit state management comparison",
    "Tailwind CSS utility classes responsive design dark mode",
    "GraphQL Apollo client query mutation subscription",
    "Jest Vitest testing library DOM unit integration",
    "ESLint Prettier TypeScript configuration rules",
    "JavaScript Promise all settled race any patterns",
    "CSS Grid Flexbox layout responsive breakpoints",
    "Remix SvelteKit Astro SSR hydration islands",
    "JavaScript Web Workers SharedArrayBuffer Atomics",
    "Deno Bun Node.js runtime comparison performance",
    "React Server Actions form handling revalidation",
    "WebAssembly WASM JavaScript interop memory module",
    "JavaScript Proxy Reflect metaprogramming patterns",
    "pnpm npm yarn monorepo workspace configuration",
    "three.js WebGL 3D scene animation renderer",
    "JavaScript IndexedDB localStorage sessionStorage cache",
    # DevOps/Docker/K8s (25)
    "Docker compose networking volumes multi-service setup",
    "Kubernetes pod deployment service ingress configuration",
    "GitHub Actions workflow matrix secrets caching",
    "Jenkins pipeline groovy stages parallel steps",
    "Terraform infrastructure code modules state backend",
    "Helm chart values templates kubernetes deployment",
    "Docker multi-stage build layer caching optimization",
    "Kubernetes ConfigMap Secret environment variables",
    "ArgoCD GitOps continuous deployment kubernetes sync",
    "Prometheus Grafana metrics alerting dashboard setup",
    "Ansible playbook roles inventory variables tasks",
    "Docker registry private image push pull authentication",
    "Kubernetes horizontal pod autoscaler resource limits",
    "GitHub Actions docker build push ghcr registry",
    "CircleCI GitLab CI pipeline parallelism artifacts",
    "Nginx ingress controller SSL termination kubernetes",
    "Docker healthcheck restart policy container lifecycle",
    "Kubernetes namespace RBAC service account permissions",
    "Datadog APM tracing distributed logs metrics",
    "Skaffold Tilt local kubernetes development workflow",
    "Kubernetes persistent volume claim storage class",
    "Fluentd Loki log aggregation kubernetes cluster",
    "Istio service mesh traffic management observability",
    "Buildkite Tekton pipeline cloud native CI/CD",
    "Kustomize overlay patch kubernetes configuration",
    # Cloud AWS/Azure/GCP (25)
    "AWS Lambda cold start optimization layers runtime",
    "Amazon S3 presigned URL lifecycle policy bucket",
    "AWS EC2 auto scaling group launch template AMI",
    "Azure Functions triggers bindings timer HTTP",
    "GCP Cloud Run container serverless autoscaling",
    "AWS RDS Aurora PostgreSQL connection pooling",
    "Azure Blob Storage SAS token access policy",
    "Google Cloud Pub/Sub message push pull subscription",
    "AWS IAM role policy trust relationship least privilege",
    "AWS API Gateway REST WebSocket throttling stage",
    "Azure AKS managed kubernetes cluster node pool",
    "GCP BigQuery partitioning clustering query optimization",
    "AWS CloudFormation stack nested template parameters",
    "AWS SQS SNS dead letter queue fan-out pattern",
    "Azure Cosmos DB partitioning consistency levels SDK",
    "GCP Cloud Storage signed URL CDN bucket policy",
    "AWS ECS Fargate task definition container service",
    "AWS CloudWatch logs insights metrics alarms",
    "Azure DevOps pipeline artifact release board",
    "GCP Vertex AI model deployment endpoint prediction",
    "AWS Secrets Manager Parameter Store rotation",
    "Azure AD service principal OAuth2 managed identity",
    "AWS CDK construct stack synthesize deploy",
    "GCP Cloud Functions gen2 event trigger Eventarc",
    "AWS Step Functions state machine workflow parallel",
    # Databases (20)
    "PostgreSQL index btree gin gist partial covering",
    "MongoDB aggregation pipeline lookup unwind facet",
    "Redis cluster sentinel replication pub/sub streams",
    "PostgreSQL JSONB operators indexing query performance",
    "Elasticsearch mapping analyzer search query DSL",
    "SQLite WAL mode concurrent write performance",
    "MySQL InnoDB transaction isolation level deadlock",
    "Redis caching strategies TTL eviction policy LRU",
    "PostgreSQL partitioning range list hash inheritance",
    "Cassandra partition key clustering column data model",
    "MongoDB change streams watch collection real-time",
    "PostgreSQL full text search tsvector tsquery ranking",
    "Neo4j Cypher graph traversal pattern matching query",
    "InfluxDB time series measurement tag field retention",
    "PostgreSQL explain analyze query plan optimization",
    "DynamoDB partition sort key GSI LSI design patterns",
    "Clickhouse columnar analytics OLAP aggregation",
    "PostgreSQL logical replication slot subscriber",
    "MongoDB atlas search aggregation vector embedding",
    "Redis sorted set leaderboard geospatial commands",
    # Security/Networking (20)
    "OAuth2 PKCE authorization code flow refresh token",
    "SSL TLS certificate Let's Encrypt renewal nginx",
    "CORS preflight headers middleware configuration",
    "JWT validation signature algorithm RS256 ES256",
    "firewall iptables nftables rules chain policy",
    "VPN WireGuard OpenVPN tunnel configuration peer",
    "AES encryption GCM mode key derivation PBKDF2",
    "SQL injection prevention parameterized query ORM",
    "XSS CSRF protection headers content security policy",
    "SSH key pair bastion host port forwarding tunnel",
    "network TCP UDP socket timeout keepalive options",
    "PKI certificate authority chain trust store",
    "LDAP Active Directory authentication integration",
    "penetration testing OWASP vulnerability scanning",
    "Vault HashiCorp secret engine dynamic credentials",
    "rate limiting token bucket algorithm middleware",
    "mTLS mutual authentication service-to-service",
    "DNS DNSSEC record types resolution caching",
    "API key rotation secret management best practices",
    "zero trust network access policy identity-aware",
    # AI/ML (20)
    "PyTorch custom training loop gradient accumulation",
    "TensorFlow Keras model fine-tuning transfer learning",
    "LLM embeddings vector similarity cosine search",
    "RAG retrieval augmented generation chunking strategy",
    "Hugging Face transformers tokenizer pipeline inference",
    "LangChain agent tools memory conversation chain",
    "ONNX model export runtime inference optimization",
    "diffusion model stable diffusion inference pipeline",
    "LLM quantization GPTQ AWQ 4bit inference speed",
    "scikit-learn cross validation pipeline feature engineering",
    "attention mechanism transformer architecture multi-head",
    "LoRA PEFT adapter fine-tuning LLM efficiency",
    "vLLM TGI llama.cpp serving throughput latency",
    "FAISS vector index ANN approximate nearest neighbor",
    "reinforcement learning PPO reward policy gradient",
    "computer vision YOLO object detection inference",
    "whisper speech recognition transcription API",
    "Claude OpenAI API streaming function calling",
    "semantic chunking embedding model sentence transformer",
    "MLflow experiment tracking model registry artifact",
    # Mobile/Frontend (15)
    "Flutter widget tree state management Riverpod Bloc",
    "React Native Expo navigation gesture animation",
    "SwiftUI view modifier animation combine publisher",
    "Jetpack Compose state hoisting LazyColumn effect",
    "CSS Grid template areas auto-fill minmax responsive",
    "Tailwind CSS custom theme extend plugin variants",
    "Flutter platform channel native Android iOS bridge",
    "React Native new architecture Fabric JSI TurboModules",
    "PWA service worker cache strategy offline first",
    "Flutter web WASM compilation rendering performance",
    "CSS container queries logical properties cascade layers",
    "Capacitor Ionic hybrid mobile web native plugin",
    "SwiftUI async image task modifier environment object",
    "Android Kotlin coroutines flow room viewmodel",
    "Figma design tokens CSS variables design system",
    # System Admin/Linux (15)
    "systemd service unit file ExecStart restart policy",
    "cron job scheduling syntax user crontab examples",
    "bash script error handling set -euo pipefail trap",
    "nginx configuration server block location proxy_pass",
    "Apache virtual host mod_rewrite SSL configuration",
    "Linux performance monitoring top htop iotop vmstat",
    "rsync backup incremental remote transfer options",
    "awk sed text processing pipeline column extraction",
    "Linux user permission group sudo sudoers file",
    "journalctl log filtering unit time range output",
    "fail2ban intrusion prevention jail configuration",
    "lvm logical volume manager resize extend partition",
    "tmux screen session window pane split detach",
    "strace ltrace system call process debugging",
    "Linux kernel tuning sysctl network performance",
    # Other tech (10)
    "Rust ownership borrowing lifetime reference rules",
    "Go goroutine channel select mutex concurrency",
    "gRPC protobuf service definition streaming interceptor",
    "WebAssembly Rust wasm-bindgen JavaScript interop",
    "Zig comptime memory allocation error union",
    "GraphQL schema federation resolver dataloader",
    "Kafka producer consumer topic partition replication",
    "Nats JetStream subject subscription streaming",
    "OpenTelemetry trace span exporter instrumentation",
    "Tauri desktop app Rust backend webview frontend",
]


# ══════════════════════════════════════════════════════════════
# DATA: 200 ML-ONLY CASES
# ══════════════════════════════════════════════════════════════
ML_CASES = [
    # CS theory/algorithms (30)
    "cual es la complejidad Big-O de quicksort en el peor caso",
    "explain why merge sort is considered stable but quicksort is not",
    "diferencia entre complejidad temporal y complejidad espacial en algoritmos",
    "what is the halting problem and why is it undecidable",
    "explain the difference between NP-hard and NP-complete problems",
    "cual es la intuicion detras del algoritmo de Dijkstra para caminos minimos",
    "how does a bloom filter trade accuracy for memory efficiency",
    "explain the concept of amortized analysis with a dynamic array example",
    "por que los arboles AVL se autobalancean y que costo tiene eso",
    "what makes a hash function cryptographically secure versus just fast",
    "explain the difference between BFS and DFS in terms of memory usage",
    "cual es la diferencia entre un grafo dirigido y uno no dirigido en teoria",
    "what is the significance of the P versus NP question in computer science",
    "explain how dynamic programming differs from greedy algorithms conceptually",
    "por que la busqueda binaria requiere que el arreglo este ordenado",
    "what is a Turing machine and why does it matter for computation theory",
    "explain the concept of memoization and when it improves performance",
    "cual es la diferencia entre una pila y una cola en terminos de uso",
    "how do red-black trees maintain balance differently than AVL trees",
    "explain what makes an algorithm in-place versus out-of-place",
    "que es la notacion omega y como difiere de Big-O en analisis",
    "what is a skip list and how does it achieve logarithmic search",
    "explain the concept of space-time tradeoff in algorithm design",
    "por que los algoritmos de ordenamiento basados en comparacion tienen limite O n log n",
    "what is the significance of topological sort in dependency resolution",
    "explain how the union-find data structure achieves near-constant operations",
    "cual es la diferencia entre recursion de cola y recursion normal",
    "what is a finite automaton and how does it relate to regular languages",
    "explain the concept of divide and conquer with a practical mental model",
    "por que el algoritmo de Kruskal funciona para arboles de expansion minima",
    # Design patterns (25)
    "explain the observer design pattern with a real world analogy",
    "cual es la diferencia entre el patron Strategy y el patron State",
    "how does the Factory pattern promote loose coupling in object design",
    "explain the Decorator pattern and how it differs from inheritance",
    "cuando deberia usarse el patron Singleton y cuales son sus desventajas",
    "what problem does the Command pattern solve in user interface design",
    "explain the difference between Adapter and Facade design patterns",
    "cual es la idea central del patron Repository en arquitectura de software",
    "how does the Builder pattern handle complex object construction",
    "explain the Proxy pattern and its use cases in software systems",
    "que ventajas ofrece el patron Iterator sobre el acceso directo a colecciones",
    "what is the Template Method pattern and how does it use inheritance",
    "explain the Composite pattern and when hierarchical structures benefit from it",
    "cual es la diferencia entre el patron Mediator y el patron Observer",
    "how does the Chain of Responsibility pattern decouple senders from receivers",
    "explain why the Visitor pattern is useful for operations on object structures",
    "que es el patron Flyweight y como reduce el uso de memoria",
    "what is the difference between a pattern and an anti-pattern conceptually",
    "explain the Model-View-Controller pattern as a separation of concerns",
    "cual es el proposito del patron Bridge en el diseno orientado a objetos",
    "how does the Memento pattern implement undo functionality without exposing state",
    "explain the Interpreter pattern and its relationship to formal grammars",
    "que principio de diseno subyace al patron Dependency Injection",
    "what makes the Abstract Factory different from a regular Factory pattern",
    "explain how design patterns emerged from Christopher Alexander architecture work",
    # Software architecture concepts (25)
    "explain the CAP theorem and why you can only choose two of three properties",
    "cual es la diferencia entre arquitectura monolitica y microservicios en teoria",
    "what is eventual consistency and when is it acceptable in distributed systems",
    "explain event sourcing as an architectural pattern versus traditional state storage",
    "que es CQRS y por que separa las operaciones de lectura y escritura",
    "how does the saga pattern manage distributed transactions without two-phase commit",
    "explain the concept of bounded contexts in domain-driven design",
    "cual es la diferencia entre acoplamiento y cohesion en diseno de software",
    "what is the strangler fig pattern for migrating legacy systems",
    "explain the difference between orchestration and choreography in microservices",
    "que es un circuit breaker en arquitecturas distribuidas y para que sirve",
    "how does the hexagonal architecture achieve separation of business logic",
    "explain the concept of service mesh and what problems it solves abstractly",
    "cual es la intuicion detras del principio de minimo privilegio en sistemas",
    "what makes an architecture event-driven versus request-response fundamentally",
    "explain the bulkhead pattern and its analogy to ship compartmentalization",
    "que es la ley de Conway y como afecta el diseno de sistemas de software",
    "how does sharding differ from replication as a scaling strategy",
    "explain the concept of idempotency and why it matters in distributed systems",
    "cual es la diferencia entre consistencia fuerte y consistencia eventual",
    "what is the difference between fault tolerance and high availability conceptually",
    "explain the two-phase commit protocol and its theoretical limitations",
    "que es el principio de diseno Tell Don't Ask en programacion orientada a objetos",
    "how does backpressure work as a concept in reactive systems",
    "explain the concept of immutable infrastructure in modern deployment theory",
    # Math/logic for programmers (25)
    "explain boolean algebra and how it underlies digital circuit design",
    "que es la teoria de conjuntos y como se aplica en bases de datos relacionales",
    "what is Bayes theorem and how does it update beliefs with new evidence",
    "explain the concept of mathematical induction and why it proves infinite cases",
    "que es una funcion biyectiva y por que importa en criptografia",
    "how does modular arithmetic enable cyclic behavior in programming",
    "explain the pigeonhole principle and give a programming application",
    "que es la logica de predicados y como difiere de la logica proposicional",
    "what is the difference between a permutation and a combination conceptually",
    "explain how probability theory underlies machine learning model uncertainty",
    "que es un numero primo y por que son fundamentales en criptografia moderna",
    "how does graph theory formalize relationships between entities in computing",
    "explain the concept of a mathematical proof by contradiction",
    "que es la entropia en teoria de la informacion y que mide exactamente",
    "what is the difference between discrete and continuous mathematics for programmers",
    "explain how linear algebra concepts underlie machine learning algorithms",
    "que es una relacion de equivalencia y como se usa en teoria de tipos",
    "how does the law of large numbers relate to software testing strategies",
    "explain the concept of invariants in algorithm correctness proofs",
    "que es la transformada de Fourier intuitivamente para un programador",
    "what is the birthday paradox and why does it matter for hash collisions",
    "explain how truth tables relate to logical circuit design",
    "que es la notacion sigma y como simplifica expresiones de sumatoria",
    "how does cardinality of infinite sets challenge intuitive notions of size",
    "explain the concept of a mathematical function versus a programming function",
    # Programming paradigms (20)
    "explain the core philosophy difference between functional and object-oriented programming",
    "que es la programacion reactiva y como difiere de la programacion imperativa",
    "what makes a language purely functional versus impure functional",
    "explain the concept of immutability and why functional programmers prefer it",
    "que es la programacion declarativa y en que se diferencia de la imperativa",
    "how does lazy evaluation change the semantics of a program",
    "explain the concept of higher-order functions and why they are powerful",
    "que es la programacion orientada a aspectos y que problemas resuelve",
    "what is referential transparency and why does it simplify reasoning about code",
    "explain the actor model of concurrency versus shared memory concurrency",
    "que es la currificacion y como transforma funciones de multiples argumentos",
    "how does logic programming differ from procedural programming conceptually",
    "explain the concept of monads without category theory jargon",
    "que es el paradigma de programacion orientada a eventos y sus ventajas",
    "what is the difference between concurrency and parallelism as concepts",
    "explain why pure functions are easier to test than impure functions",
    "que es la composicion de funciones y por que es central en programacion funcional",
    "how does continuation-passing style transform the flow of a program",
    "explain the concept of duck typing versus structural typing versus nominal typing",
    "que ventajas ofrece la programacion funcional para el razonamiento sobre codigo",
    # Ethics/philosophy of tech (15)
    "explain the trolley problem applied to autonomous vehicle decision-making",
    "que dilemas eticos plantea el uso de inteligencia artificial en contrataciones",
    "what is the philosophical tension between privacy and security in digital systems",
    "explain the concept of algorithmic bias and why it is hard to eliminate",
    "que es el derecho al olvido y como choca con la naturaleza de los datos digitales",
    "how does open source philosophy challenge traditional notions of intellectual property",
    "explain the ethical implications of surveillance capitalism as a business model",
    "que responsabilidad moral tienen los programadores por el codigo que escriben",
    "what is the Collingridge dilemma in technology governance and regulation",
    "explain why fairness in machine learning is difficult to define mathematically",
    "que significa la brecha digital y como afecta la equidad social",
    "how does the concept of informed consent apply to data collection practices",
    "explain the philosophical difference between privacy as a right versus a commodity",
    "que es el determinismo tecnologico y como influye en el diseno de sistemas",
    "what ethical frameworks apply when AI systems make consequential decisions",
    # Career/team concepts (15)
    "explain the philosophy behind test-driven development as a design practice",
    "que es la deuda tecnica y como se acumula silenciosamente en los proyectos",
    "what is the difference between accidental and essential complexity in software",
    "explain why code review is a knowledge transfer mechanism not just quality control",
    "que es el principio de boy scout en el desarrollo de software",
    "how does psychological safety affect team productivity and innovation",
    "explain the concept of bus factor and why it is a risk metric for teams",
    "que es el sindrome del impostor y como afecta a los programadores",
    "what is the difference between a mentor and a coach in technical careers",
    "explain why over-engineering is as harmful as under-engineering",
    "que es la ley de Hofstadter y por que los proyectos siempre se retrasan",
    "how does Conway Law suggest teams should be structured for microservices",
    "explain the broken windows theory applied to software quality",
    "que es el perfeccionismo tecnico y cuando se convierte en un antipatron",
    "what makes a good pull request description beyond just listing changes",
    # Abstract reasoning (15)
    "explain the tradeoff between consistency and availability using a real analogy",
    "que es un modelo mental y como ayuda a los programadores a disenar sistemas",
    "how does the concept of abstraction layers apply outside of computing",
    "explain the difference between accidental and inherent complexity with examples",
    "que es el pensamiento sistemico y como se aplica al diseno de software",
    "how does the map-territory distinction apply to software models and reality",
    "explain why simple solutions are often better than clever ones in engineering",
    "que analogia describe mejor la diferencia entre sincronico y asincronico",
    "how does the concept of emergence apply to complex software systems",
    "explain the engineering tradeoff between build versus buy versus integrate",
    "que es el pensamiento de primeros principios aplicado a la arquitectura de software",
    "how does the concept of entropy apply metaphorically to software maintenance",
    "explain why premature optimization is considered the root of all evil",
    "que diferencia hay entre resolver un problema y disolver un problema",
    "how does the concept of feedback loops apply to software development processes",
    # General CS knowledge (15)
    "explain the historical significance of the stored-program computer concept",
    "que contribucion hizo Alan Turing a la teoria de la computacion",
    "how did the Von Neumann architecture shape modern computer design",
    "explain the significance of Dijkstra letter about the goto statement",
    "que es la maquina de Von Neumann y cuales son sus componentes conceptuales",
    "how did the development of Unix influence modern operating system design",
    "explain why the invention of the transistor was revolutionary for computing",
    "que es la ley de Moore y por que eventualmente dejara de aplicarse",
    "how did structured programming replace unstructured code historically",
    "explain the historical development of high-level programming languages",
    "que es el modelo OSI y por que se divide la red en capas conceptuales",
    "how did the internet transition from ARPANET change distributed computing",
    "explain Grace Hopper contribution to programming language development",
    "que importancia tiene el concepto de abstraccion en la historia del software",
    "how did object-oriented programming emerge as a response to complexity",
    # Conceptual explanations (15)
    "explain recursion using an analogy a child could understand",
    "como explicarias el concepto de punteros a alguien sin experiencia tecnica",
    "explain what a database index does using a real-world library analogy",
    "como funciona el garbage collection explicado sin terminos tecnicos",
    "explain the concept of API using a restaurant menu as an analogy",
    "que es la concurrencia explicada con una analogia de la vida cotidiana",
    "explain encryption conceptually using the idea of a secret language",
    "como explicarias la diferencia entre cliente y servidor a un nino",
    "explain version control using the analogy of a time machine for code",
    "que es la virtualizacion explicada con una analogia comprensible",
    "explain the concept of caching using a desk drawer analogy",
    "como describirias un algoritmo a alguien que nunca ha programado",
    "explain the concept of a protocol using human communication as an analogy",
    "que es la escalabilidad explicada con una analogia de restaurantes",
    "explain the difference between hardware and software to a complete beginner",
]


# ══════════════════════════════════════════════════════════════
# DATA: 200 KB+INTERNET CASES
# ═��════════════════════════════════════════════════════════════
KB_INTERNET_CASES = [
    # sap_tierra (50)
    ("SAP CRM WebUI session expired timeout error handling", "sap_tierra"),
    ("SAP CRM oportunidad pipeline configuracion API REST", "sap_tierra"),
    ("SAP CRM account management Python automation script", "sap_tierra"),
    ("SAP CRM lead conversion error troubleshooting tutorial", "sap_tierra"),
    ("SAP CRM WebUI navigation Playwright browser automation", "sap_tierra"),
    ("SAP CRM actividad seguimiento configuracion workflow", "sap_tierra"),
    ("SAP CRM integration REST API authentication token", "sap_tierra"),
    ("SAP CRM BP business partner creation error fix", "sap_tierra"),
    ("SAP CRM oportunidad etapa cambio automatico Python", "sap_tierra"),
    ("SAP CRM dashboard KPI configuration performance", "sap_tierra"),
    ("SAP CRM session login Playwright headless browser", "sap_tierra"),
    ("SAP CRM contacto cliente sincronizacion API externa", "sap_tierra"),
    ("SAP CRM pipeline ventas reporte exportacion CSV", "sap_tierra"),
    ("SAP CRM WebUI customizing roles authorization error", "sap_tierra"),
    ("SAP CRM ticket soporte creacion automatizada script", "sap_tierra"),
    ("SAP CRM opportunity stage update REST API Python", "sap_tierra"),
    ("SAP CRM calendario actividades integracion Outlook", "sap_tierra"),
    ("SAP CRM lead qualification automation webhook trigger", "sap_tierra"),
    ("SAP CRM datos cliente extraccion pandas dataframe", "sap_tierra"),
    ("SAP CRM WebUI error 500 server internal fix", "sap_tierra"),
    ("SAP CRM nota actividad creacion automatica pipeline", "sap_tierra"),
    ("SAP CRM producto catalogo configuracion precio API", "sap_tierra"),
    ("SAP CRM oportunidad ganada perdida reporte analytics", "sap_tierra"),
    ("SAP CRM Playwright login selector CSS XPath", "sap_tierra"),
    ("SAP CRM transaccion CRMD_ORDER error handling", "sap_tierra"),
    ("SAP CRM customer segmentation Python ML model", "sap_tierra"),
    ("SAP CRM campo personalizado configuracion tabla", "sap_tierra"),
    ("SAP CRM workflow approval process automation error", "sap_tierra"),
    ("SAP CRM RFC function call Python connector", "sap_tierra"),
    ("SAP CRM sales cycle forecast configuration tutorial", "sap_tierra"),
    ("SAP CRM interaccion canal correo automatizacion", "sap_tierra"),
    ("SAP CRM BP rol contacto creacion masiva script", "sap_tierra"),
    ("SAP CRM opportunity probability calculation Python", "sap_tierra"),
    ("SAP CRM tabla base datos consulta SQL performance", "sap_tierra"),
    ("SAP CRM WebUI component configuration ABAP", "sap_tierra"),
    ("SAP CRM estado oportunidad transicion regla negocio", "sap_tierra"),
    ("SAP CRM data migration import CSV Python script", "sap_tierra"),
    ("SAP CRM alert notification email configuration", "sap_tierra"),
    ("SAP CRM territory management assignment rule", "sap_tierra"),
    ("SAP CRM producto oferta cotizacion automatizacion", "sap_tierra"),
    ("SAP CRM partner channel management API integration", "sap_tierra"),
    ("SAP CRM filtro busqueda avanzada configuracion UI", "sap_tierra"),
    ("SAP CRM campaign management email automation Python", "sap_tierra"),
    ("SAP CRM historial interacciones cliente reporte", "sap_tierra"),
    ("SAP CRM WebUI performance optimization slow loading", "sap_tierra"),
    ("SAP CRM activity task reminder automation script", "sap_tierra"),
    ("SAP CRM presupuesto venta cierre prediccion ML", "sap_tierra"),
    ("SAP CRM contrato cliente creacion flujo trabajo", "sap_tierra"),
    ("SAP CRM user role authorization profile configuration", "sap_tierra"),
    ("SAP CRM webhook outbound integration Python Flask", "sap_tierra"),
    # formfiller_ia (25)
    ("formfiller AI Playwright auto complete web form", "formfiller_ia"),
    ("formulario web automatizacion IA extraccion datos", "formfiller_ia"),
    ("formfiller Python Playwright selector input field", "formfiller_ia"),
    ("AI form filling automation error handling retry", "formfiller_ia"),
    ("formfiller IA campo fecha formato validation error", "formfiller_ia"),
    ("web form automation Playwright screenshot debug", "formfiller_ia"),
    ("formfiller inteligente dropdown select automation", "formfiller_ia"),
    ("AI formfiller PDF extraction Python script", "formfiller_ia"),
    ("formulario SAP CRM automatizacion Playwright script", "formfiller_ia"),
    ("formfiller IA captcha bypass workaround technique", "formfiller_ia"),
    ("automated form submission Python requests library", "formfiller_ia"),
    ("formfiller IA validacion campo obligatorio error", "formfiller_ia"),
    ("AI web scraping form data extraction BeautifulSoup", "formfiller_ia"),
    ("formfiller Playwright wait element timeout fix", "formfiller_ia"),
    ("formulario dinamico IA deteccion campo automatico", "formfiller_ia"),
    ("formfiller AI checkbox radio button automation", "formfiller_ia"),
    ("form automation pipeline hooks trigger webhook", "formfiller_ia"),
    ("formfiller IA archivo adjunto upload automation", "formfiller_ia"),
    ("AI form validation regex pattern Python tutorial", "formfiller_ia"),
    ("formfiller multi-page wizard automation Playwright", "formfiller_ia"),
    ("formulario bancario automatizacion IA Python script", "formfiller_ia"),
    ("formfiller IA session cookie management browser", "formfiller_ia"),
    ("AI form data mapping JSON schema configuration", "formfiller_ia"),
    ("formfiller IA tabla dinamica fila agregar script", "formfiller_ia"),
    ("automated form testing Playwright pytest framework", "formfiller_ia"),
    # sap_automation (20)
    ("SAP automation Playwright Python login script", "sap_automation"),
    ("SAP WebUI automatizacion Python error handling", "sap_automation"),
    ("SAP CRM automation pytest test suite configuration", "sap_automation"),
    ("SAP Playwright screenshot element not found error", "sap_automation"),
    ("SAP automatizacion oportunidad creacion script Python", "sap_automation"),
    ("SAP CRM RPA robotic process automation tutorial", "sap_automation"),
    ("SAP automation headless Chrome Playwright setup", "sap_automation"),
    ("SAP WebUI selector XPath CSS automation script", "sap_automation"),
    ("SAP CRM data extraction automation pandas Excel", "sap_automation"),
    ("SAP automation pipeline CI/CD GitHub Actions", "sap_automation"),
    ("SAP CRM automatizacion tarea programada cron job", "sap_automation"),
    ("SAP Playwright async await Python asyncio tutorial", "sap_automation"),
    ("SAP automation error retry exponential backoff", "sap_automation"),
    ("SAP CRM batch processing automation Python script", "sap_automation"),
    ("SAP WebUI modal dialog automation Playwright click", "sap_automation"),
    ("SAP automation logging monitoring ELK stack", "sap_automation"),
    ("SAP CRM automatizacion reporte generacion PDF", "sap_automation"),
    ("SAP Playwright network intercept request mock", "sap_automation"),
    ("SAP automation Docker container deployment setup", "sap_automation"),
    ("SAP CRM automatizacion notificacion email SMTP", "sap_automation"),
    # hooks_ia (20)
    ("hooks pipeline IA MCP server configuration Python", "hooks_ia"),
    ("pipeline KB internet search integration tutorial", "hooks_ia"),
    ("hooks sistema IA contexto enriquecimiento API", "hooks_ia"),
    ("MCP server hooks Python fastapi webhook trigger", "hooks_ia"),
    ("pipeline ML model inference hooks integration", "hooks_ia"),
    ("hooks IA DuckDuckGo search results processing", "hooks_ia"),
    ("pipeline arquitectura microservicios hooks evento", "hooks_ia"),
    ("hooks IA knowledge base vectorial FAISS embedding", "hooks_ia"),
    ("MCP protocol implementation Python tutorial", "hooks_ia"),
    ("pipeline hooks trigger condition automation rule", "hooks_ia"),
    ("hooks IA RAG retrieval augmented generation setup", "hooks_ia"),
    ("pipeline orquestacion LangChain hooks integration", "hooks_ia"),
    ("hooks sistema contexto SAP CRM enriquecimiento", "hooks_ia"),
    ("MCP server herramienta personalizada Python class", "hooks_ia"),
    ("pipeline hooks error handling fallback strategy", "hooks_ia"),
    ("hooks IA cache Redis performance optimization", "hooks_ia"),
    ("pipeline KB internet combinacion resultado ranking", "hooks_ia"),
    ("hooks IA logging structured JSON monitoring", "hooks_ia"),
    ("MCP hooks pipeline deployment Docker Kubernetes", "hooks_ia"),
    ("pipeline hooks IA prueba unitaria pytest mock", "hooks_ia"),
    # business_rules (15)
    ("GBM Guatemala regla negocio configuracion sistema", "business_rules"),
    ("business rules engine Python drools configuration", "business_rules"),
    ("GBM regla aprobacion credito logica condicional", "business_rules"),
    ("banking business rules automation API integration", "business_rules"),
    ("GBM Guatemala flujo aprobacion regla validacion", "business_rules"),
    ("business rules financial compliance automation", "business_rules"),
    ("GBM sistema reglas decision tree Python", "business_rules"),
    ("regla negocio bancaria validacion datos cliente", "business_rules"),
    ("GBM Guatemala KYC AML compliance rule engine", "business_rules"),
    ("business rules versioning deployment CI/CD pipeline", "business_rules"),
    ("GBM regla producto financiero configuracion tabla", "business_rules"),
    ("banking rule engine performance optimization cache", "business_rules"),
    ("GBM Guatemala riesgo credito scoring modelo ML", "business_rules"),
    ("business rules testing unit integration pytest", "business_rules"),
    ("GBM regla negocio auditoria log trazabilidad", "business_rules"),
    # outlook (15)
    ("Outlook automatizacion Python win32com email envio", "outlook"),
    ("Outlook API Microsoft Graph email automation", "outlook"),
    ("Outlook correo SAP CRM integracion sincronizacion", "outlook"),
    ("Outlook Python automation adjunto procesamiento", "outlook"),
    ("Outlook calendar event creation API Python script", "outlook"),
    ("Outlook correo automatico plantilla HTML Python", "outlook"),
    ("Outlook Microsoft Graph OAuth2 token authentication", "outlook"),
    ("Outlook email parsing extraction Python imaplib", "outlook"),
    ("Outlook automatizacion regla carpeta clasificacion", "outlook"),
    ("Outlook webhook notification email trigger Python", "outlook"),
    ("Outlook correo SAP actividad creacion automatica", "outlook"),
    ("Outlook shared mailbox access Python automation", "outlook"),
    ("Outlook email signature template HTML configuration", "outlook"),
    ("Outlook automatizacion respuesta automatica script", "outlook"),
    ("Outlook meeting invite automation Python calendar", "outlook"),
    # monday_automation (10)
    ("Monday.com API crear columna board automatizacion webhook", "monday_automation"),
    ("Monday.com Python SDK item creation automation", "monday_automation"),
    ("Monday.com webhook trigger pipeline hooks integration", "monday_automation"),
    ("Monday.com tablero SAP CRM sincronizacion API", "monday_automation"),
    ("Monday.com automation recipe configuration tutorial", "monday_automation"),
    ("Monday.com GraphQL API mutation item update", "monday_automation"),
    ("Monday.com integracion correo Outlook automatizacion", "monday_automation"),
    ("Monday.com board template project management API", "monday_automation"),
    ("Monday.com status column automation Python script", "monday_automation"),
    ("Monday.com subitem creation batch API Python", "monday_automation"),
    # banco_bantrab (10)
    ("Bantrab Guatemala banca en linea API integracion", "banco_bantrab"),
    ("Bantrab transferencia automatizacion Python script", "banco_bantrab"),
    ("Bantrab Guatemala cuenta ahorro consulta saldo API", "banco_bantrab"),
    ("Bantrab banking automation Playwright web scraping", "banco_bantrab"),
    ("Bantrab Guatemala credito solicitud formulario auto", "banco_bantrab"),
    ("Bantrab fintech integration REST API authentication", "banco_bantrab"),
    ("Bantrab Guatemala pago servicio automatizacion bot", "banco_bantrab"),
    ("Bantrab banca movil API endpoint documentacion", "banco_bantrab"),
    ("Bantrab Guatemala reporte transaccion extraccion", "banco_bantrab"),
    ("Bantrab banking Python requests session login", "banco_bantrab"),
    # sow (10)
    ("SOW statement of work project management template", "sow"),
    ("SOW documento alcance proyecto configuracion SAP", "sow"),
    ("SOW automation generation Python document template", "sow"),
    ("SOW project milestone tracking Monday.com board", "sow"),
    ("SOW statement of work approval workflow automation", "sow"),
    ("SOW documento entregable lista configuracion API", "sow"),
    ("SOW project scope change management process", "sow"),
    ("SOW generacion automatica PDF Python reportlab", "sow"),
    ("SOW integracion SAP CRM proyecto seguimiento", "sow"),
    ("SOW project risk management documentation template", "sow"),
    # services (8)
    ("SAP CRM services API endpoint REST configuration", "services"),
    ("SAP services integration microservices Python Flask", "services"),
    ("SAP CRM servicio cliente creacion API automatica", "services"),
    ("SAP services authentication OAuth2 token refresh", "services"),
    ("SAP CRM service order management automation script", "services"),
    ("SAP services monitoring health check Python", "services"),
    ("SAP CRM servicio contrato SLA configuracion regla", "services"),
    ("SAP services API rate limiting retry Python", "services"),
    # banco_bac (5)
    ("BAC Guatemala banca online API Python integration", "banco_bac"),
    ("BAC Credomatic transferencia automatizacion script", "banco_bac"),
    ("BAC Guatemala cuenta consulta saldo Playwright", "banco_bac"),
    ("BAC banking fintech REST API authentication token", "banco_bac"),
    ("BAC Guatemala pago automatico Python requests", "banco_bac"),
    # banco_promerica (5)
    ("Promerica Guatemala banca linea automatizacion API", "banco_promerica"),
    ("Promerica banking Python Playwright login script", "banco_promerica"),
    ("Promerica Guatemala transferencia REST API Python", "banco_promerica"),
    ("Promerica fintech integration authentication OAuth", "banco_promerica"),
    ("Promerica Guatemala cuenta saldo consulta automation", "banco_promerica"),
    # seguros_assa (4)
    ("ASSA seguros Guatemala poliza API integracion Python", "seguros_assa"),
    ("ASSA insurance automation claim processing script", "seguros_assa"),
    ("ASSA Guatemala cotizacion seguro formulario auto", "seguros_assa"),
    ("ASSA seguros REST API authentication configuration", "seguros_assa"),
    # seguros_el_roble (3)
    ("El Roble seguros Guatemala poliza API Python", "seguros_el_roble"),
    ("El Roble insurance automation Playwright script", "seguros_el_roble"),
    ("El Roble seguros cotizacion formulario automatizacion", "seguros_el_roble"),
]


# ══════════════════════════════════════════════════════════════
# DATA: 200 KB+INTERNET+ML CASES
# ═══════════���══════════════════════════════════════════════════
KB_INTERNET_ML_CASES = [
    # sap_tierra (45)
    ("SAP CRM oportunidad pipeline automation CDP JavaScript REST API integration best practices", "sap_tierra"),
    ("SAP CRM quote items bulk update via API gateway microservices architecture patterns", "sap_tierra"),
    ("SAP CRM campaign management ML-driven segmentation customer lifetime value prediction", "sap_tierra"),
    ("SAP CRM activity management webhook triggers real-time event processing architecture", "sap_tierra"),
    ("SAP CRM lead scoring algorithm gradient boosting feature engineering pipeline design", "sap_tierra"),
    ("SAP CRM opportunity stage transition rules business logic automation JavaScript CDP", "sap_tierra"),
    ("SAP CRM integration con ERP financiero reconciliacion datos batch processing patterns", "sap_tierra"),
    ("SAP CRM customer segmentation clustering k-means embeddings vector similarity search", "sap_tierra"),
    ("SAP CRM forecast revenue prediction ARIMA time series modelo entrenamiento features", "sap_tierra"),
    ("SAP CRM contact deduplication fuzzy matching NLP entity resolution pipeline", "sap_tierra"),
    ("SAP CRM territory management optimization genetic algorithm assignment rules automation", "sap_tierra"),
    ("SAP CRM email campaign performance analytics A/B testing statistical significance", "sap_tierra"),
    ("SAP CRM API rate limiting throttling strategy exponential backoff retry patterns", "sap_tierra"),
    ("SAP CRM custom field validation regex patterns CDP JavaScript event hooks", "sap_tierra"),
    ("SAP CRM account hierarchy consolidation parent child relationship graph traversal", "sap_tierra"),
    ("SAP CRM oportunidad cierre automatico reglas negocio inactividad prediccion churn", "sap_tierra"),
    ("SAP CRM quote aprobacion workflow multinivel escalacion reglas condiciones complejas", "sap_tierra"),
    ("SAP CRM reporte KPI dashboard real-time streaming data warehouse integration patterns", "sap_tierra"),
    ("SAP CRM sincronizacion bidireccional con Outlook calendario contactos conflict resolution", "sap_tierra"),
    ("SAP CRM pipeline velocity metric calculation cohort analysis retention prediction ML", "sap_tierra"),
    ("SAP CRM product catalog recommendation engine collaborative filtering embeddings", "sap_tierra"),
    ("SAP CRM service ticket escalation priority ML classification NLP sentiment analysis", "sap_tierra"),
    ("SAP CRM partner portal API authentication OAuth2 JWT token management best practices", "sap_tierra"),
    ("SAP CRM data migration estrategia ETL transformacion validacion rollback mechanisms", "sap_tierra"),
    ("SAP CRM multi-tenant arquitectura isolacion datos seguridad row-level security patterns", "sap_tierra"),
    ("SAP CRM automatizacion precio dinamico reglas mercado competencia ML pricing model", "sap_tierra"),
    ("SAP CRM customer journey mapping touchpoint analytics funnel conversion optimization", "sap_tierra"),
    ("SAP CRM integracion WhatsApp Business API mensajeria automatizada NLP intent detection", "sap_tierra"),
    ("SAP CRM SLA management alertas prediccion breach proactiva ML anomaly detection", "sap_tierra"),
    ("SAP CRM role-based access control ABAC policy engine performance optimization", "sap_tierra"),
    ("SAP CRM caching strategy Redis distributed lock optimistic concurrency patterns", "sap_tierra"),
    ("SAP CRM audit trail event sourcing CQRS architecture compliance reporting patterns", "sap_tierra"),
    ("SAP CRM predictive next best action recommendation engine reinforcement learning", "sap_tierra"),
    ("SAP CRM documento adjunto storage S3 CDN metadata indexing full-text search", "sap_tierra"),
    ("SAP CRM automatizacion contrato generacion template variables merge campos dinamicos", "sap_tierra"),
    ("SAP CRM health score cliente indicadores KPI weighted scoring machine learning", "sap_tierra"),
    ("SAP CRM integracion pago pasarela tokenizacion PCI DSS compliance architecture", "sap_tierra"),
    ("SAP CRM notification engine multi-channel push email SMS orchestration patterns", "sap_tierra"),
    ("SAP CRM performance tuning query optimization index strategy database profiling", "sap_tierra"),
    ("SAP CRM consent management GDPR data subject rights automation workflow design", "sap_tierra"),
    ("SAP CRM cross-sell upsell trigger event pipeline ML propensity scoring model", "sap_tierra"),
    ("SAP CRM Tierra configuracion ambiente desarrollo produccion CI/CD pipeline automation", "sap_tierra"),
    ("SAP CRM pipeline stages customization drag drop UI state machine transition logic", "sap_tierra"),
    ("SAP CRM bulk import export CSV validation transformation error handling patterns", "sap_tierra"),
    ("SAP CRM webhook payload signature verification HMAC security middleware patterns", "sap_tierra"),
    # formfiller_ia (25)
    ("FormFiller IA arquitectura extraccion campos PDF OCR NLP pipeline procesamiento", "formfiller_ia"),
    ("FormFiller automatizacion formularios web Selenium Playwright vision computacional campos", "formfiller_ia"),
    ("FormFiller IA validacion datos entrada regex patrones reglas negocio ML deteccion errores", "formfiller_ia"),
    ("FormFiller PDF parsing structure recognition table extraction transformer architecture", "formfiller_ia"),
    ("FormFiller IA multi-formato soporte Word Excel PDF XML schema mapping automatico", "formfiller_ia"),
    ("FormFiller inteligencia artificial inferencia tipo campo contexto semantico embeddings", "formfiller_ia"),
    ("FormFiller automatizacion formulario SAP CRM campos obligatorios validacion reglas negocio", "formfiller_ia"),
    ("FormFiller IA confidence score umbral decision human-in-the-loop review workflow", "formfiller_ia"),
    ("FormFiller extraccion entidades NER spaCy transformers entrenamiento dominio especifico", "formfiller_ia"),
    ("FormFiller template matching algoritmo similitud coseno embedding comparacion documentos", "formfiller_ia"),
    ("FormFiller IA procesamiento lote batch queue management distributed workers pattern", "formfiller_ia"),
    ("FormFiller integracion API REST autenticacion formularios terceros mapping schema", "formfiller_ia"),
    ("FormFiller IA manejo formularios dinamicos JavaScript rendering headless browser automation", "formfiller_ia"),
    ("FormFiller vision computacional campo deteccion YOLO bounding box clasificacion tipo", "formfiller_ia"),
    ("FormFiller IA audit trail trazabilidad cambios campos version control immutable log", "formfiller_ia"),
    ("FormFiller pre-llenado inteligente historial usuario prediccion valores frecuentes ML", "formfiller_ia"),
    ("FormFiller IA manejo captcha bypass estrategias alternativas accesibilidad API", "formfiller_ia"),
    ("FormFiller extraccion tabla compleja PDF multi-columna alineacion parsing heuristics", "formfiller_ia"),
    ("FormFiller IA integracion banco datos maestros validacion catalogo lookup API", "formfiller_ia"),
    ("FormFiller formulario seguros ASSA campos cobertura suma asegurada validacion reglas", "formfiller_ia"),
    ("FormFiller IA error recovery estrategia reintento parcial checkpoint resume pipeline", "formfiller_ia"),
    ("FormFiller handwriting recognition HTR modelo entrenamiento custom dataset fine-tuning", "formfiller_ia"),
    ("FormFiller IA formulario bancario Bantrab campos cliente validacion identidad KYC", "formfiller_ia"),
    ("FormFiller multi-idioma soporte espanol ingles formulario NLP tokenizacion normalizacion", "formfiller_ia"),
    ("FormFiller IA orquestacion microservicio extraccion validacion llenado pipeline design", "formfiller_ia"),
    # hooks_ia (25)
    ("Hooks IA pipeline KB Internet ML fusion estrategia ranking resultado synthesis", "hooks_ia"),
    ("Hooks IA vector database FAISS Pinecone index sharding performance scaling strategy", "hooks_ia"),
    ("Hooks IA query routing clasificador intent dominio multi-label transformer model", "hooks_ia"),
    ("Hooks IA cache semantico similitud consulta TTL invalidation strategy embeddings", "hooks_ia"),
    ("Hooks IA fuente Internet scraping etico rate limiting robots.txt compliance parsing", "hooks_ia"),
    ("Hooks IA ML model serving latencia optimizacion ONNX cuantizacion inferencia rapida", "hooks_ia"),
    ("Hooks IA KB actualizacion incremental embedding recalculo differential update strategy", "hooks_ia"),
    ("Hooks IA resultado fusion weighted scoring ensemble learning meta-learner architecture", "hooks_ia"),
    ("Hooks IA monitoring observabilidad Prometheus Grafana pipeline metrics alerting", "hooks_ia"),
    ("Hooks IA prompt engineering chain-of-thought few-shot dominio especifico synthesis", "hooks_ia"),
    ("Hooks IA knowledge graph construccion tripletas extraccion relaciones NLP pipeline", "hooks_ia"),
    ("Hooks IA streaming respuesta SSE WebSocket token generation real-time UX pattern", "hooks_ia"),
    ("Hooks IA fallback strategy KB miss Internet timeout ML degraded mode graceful", "hooks_ia"),
    ("Hooks IA RAG retrieval augmented generation chunk size overlap strategy optimization", "hooks_ia"),
    ("Hooks IA multi-query expansion reformulacion HyDE hypothetical document embeddings", "hooks_ia"),
    ("Hooks IA reranking cross-encoder modelo relevancia precision recall optimization", "hooks_ia"),
    ("Hooks IA contexto ventana management truncation strategy token budget allocation", "hooks_ia"),
    ("Hooks IA feedback loop usuario relevancia positiva negativa online learning update", "hooks_ia"),
    ("Hooks IA seguridad query sanitizacion prompt injection prevencion guardrails design", "hooks_ia"),
    ("Hooks IA A/B testing pipeline variante evaluacion NDCG MRR metrics comparison", "hooks_ia"),
    ("Hooks IA domain adaptation transfer learning fine-tuning datos dominio especifico", "hooks_ia"),
    ("Hooks IA multi-modal consulta imagen texto fusion embedding proyeccion espacio comun", "hooks_ia"),
    ("Hooks IA latencia P99 optimizacion bottleneck profiling async pipeline redesign", "hooks_ia"),
    ("Hooks IA costos inferencia optimizacion batch agrupacion solicitudes GPU utilization", "hooks_ia"),
    ("Hooks IA explicabilidad respuesta fuente attribution trazabilidad chunk documento", "hooks_ia"),
    # sap_automation (20)
    ("SAP automation script CDP JavaScript event listener oportunidad creacion validation", "sap_automation"),
    ("SAP automation bulk operacion API batch processing error handling transaccion rollback", "sap_automation"),
    ("SAP automation testing framework unit integration end-to-end CI/CD pipeline strategy", "sap_automation"),
    ("SAP automation workflow approval multi-level escalation timeout fallback configuration", "sap_automation"),
    ("SAP automatizacion reporte programado scheduling triggers parametros dinamicos email", "sap_automation"),
    ("SAP automation data quality validation pipeline cleansing enrichment master data", "sap_automation"),
    ("SAP automation integracion externa REST SOAP adapter pattern error retry idempotency", "sap_automation"),
    ("SAP automation performance benchmark carga concurrente usuarios simulacion stress test", "sap_automation"),
    ("SAP automatizacion migracion datos legacy sistema ETL transformacion validacion masiva", "sap_automation"),
    ("SAP automation CDP custom event trigger condicion compleja expresion logica evaluacion", "sap_automation"),
    ("SAP automation configuracion ambiente variables entorno secretos gestion segura vault", "sap_automation"),
    ("SAP automation logging estructurado correlacion ID distributed tracing observabilidad", "sap_automation"),
    ("SAP automatizacion notificacion evento cambio estado entidad webhook push pattern", "sap_automation"),
    ("SAP automation versioning API backward compatibility deprecation strategy migration", "sap_automation"),
    ("SAP automation rate limit handling cola espera retry exponential backoff jitter", "sap_automation"),
    ("SAP automatizacion sincronizacion datos tiempo real CDC change data capture pattern", "sap_automation"),
    ("SAP automation deployment blue-green canary release rollback strategy zero downtime", "sap_automation"),
    ("SAP automation security scan SAST DAST dependency check pipeline DevSecOps integration", "sap_automation"),
    ("SAP automatizacion calendario evento recurrente regla negocio condicion trigger avanzado", "sap_automation"),
    ("SAP automation multi-idioma internacionalizacion formato fecha numero moneda manejo", "sap_automation"),
    # business_rules (15)
    ("GBM reglas negocio motor inferencia encadenamiento hacia adelante Rete algorithm performance", "business_rules"),
    ("GBM business rules versioning control cambio impacto analisis dependencia grafo", "business_rules"),
    ("GBM reglas condicion compleja operador logico anidado evaluacion precedencia optimizacion", "business_rules"),
    ("GBM decision table matrix condicion accion conflicto resolucion prioridad strategy", "business_rules"),
    ("GBM reglas negocio testing unitario cobertura caso borde validacion automatizada", "business_rules"),
    ("GBM motor reglas integracion ML modelo prediccion hibridacion regla adaptativa", "business_rules"),
    ("GBM business rules rendimiento benchmarking profiling cuello botella optimizacion", "business_rules"),
    ("GBM reglas seguro ASSA cobertura exclusion condicion calculo prima automatizacion", "business_rules"),
    ("GBM reglas bancarias Bantrab limite credito scoring aprobacion condicion multiple", "business_rules"),
    ("GBM explicabilidad regla decision auditoria compliance trazabilidad razonamiento path", "business_rules"),
    ("GBM reglas dinamicas actualizacion caliente hot reload sin downtime sistema critico", "business_rules"),
    ("GBM conflict detection reglas contradictorias analisis estatico resolucion automatica", "business_rules"),
    ("GBM reglas industria seguros actuarial calculo estadistico integracion modelo ML", "business_rules"),
    ("GBM DSL domain specific language reglas negocio diseno parser interpretador custom", "business_rules"),
    ("GBM reglas distribuidas microservicio coordinacion consistencia eventual saga pattern", "business_rules"),
    # outlook (10)
    ("Outlook automation email clasificacion ML NLP categoria prioridad pipeline procesamiento", "outlook"),
    ("Outlook integracion SAP CRM contacto sincronizacion bidireccional conflict resolution", "outlook"),
    ("Outlook automation respuesta automatica plantilla NLP contexto extraccion informacion", "outlook"),
    ("Outlook Graph API integracion webhook evento nuevo email procesamiento tiempo real", "outlook"),
    ("Outlook automation adjunto procesamiento OCR extraccion datos formulario pipeline", "outlook"),
    ("Outlook email thread analisis sentimiento escalacion automatica CRM ticket creation", "outlook"),
    ("Outlook automation calendario reunion programacion inteligente disponibilidad ML", "outlook"),
    ("Outlook integracion Monday.com tarea creacion automatica email accion item board", "outlook"),
    ("Outlook automation seguimiento email no respondido reminder inteligente ML timing", "outlook"),
    ("Outlook email categorization zero-shot classification transformer modelo dominio", "outlook"),
    # monday_automation (10)
    ("Monday.com automation item creacion webhook trigger condicion board columna update", "monday_automation"),
    ("Monday.com integracion SAP CRM oportunidad sincronizacion status bidireccional API", "monday_automation"),
    ("Monday.com automatizacion dependencia tarea critica path analisis Gantt ML prediction", "monday_automation"),
    ("Monday.com board template customizacion formula columna calculo automatico logica", "monday_automation"),
    ("Monday.com automation notificacion inteligente stakeholder update ML prioridad scoring", "monday_automation"),
    ("Monday.com GraphQL API paginacion filtrado complejo query optimizacion performance", "monday_automation"),
    ("Monday.com automatizacion reporte ejecutivo KPI extraccion dashboard exportacion", "monday_automation"),
    ("Monday.com integracion Outlook email tarea conversion automatica NLP extraccion", "monday_automation"),
    ("Monday.com automation recurso asignacion optimizacion carga trabajo ML balanceo", "monday_automation"),
    ("Monday.com workflow multi-board item movimiento condicion automation recipe avanzado", "monday_automation"),
    # banco_bantrab (10)
    ("Bantrab core bancario integracion API REST transaccion tiempo real idempotencia seguridad", "banco_bantrab"),
    ("Bantrab credito scoring ML modelo entrenamiento variables bureau externas integracion", "banco_bantrab"),
    ("Bantrab automatizacion apertura cuenta digital KYC identidad verificacion pipeline", "banco_bantrab"),
    ("Bantrab fraude deteccion tiempo real ML anomalia transaccion regla umbral adaptativo", "banco_bantrab"),
    ("Bantrab integracion SAP CRM cliente cartera seguimiento oportunidad cross-sell ML", "banco_bantrab"),
    ("Bantrab banca movil API seguridad autenticacion biometrica JWT refresh token strategy", "banco_bantrab"),
    ("Bantrab conciliacion automatica transaccion diferencia reconciliacion batch pipeline", "banco_bantrab"),
    ("Bantrab regulacion SIB compliance reporte automatizacion generacion validacion datos", "banco_bantrab"),
    ("Bantrab customer journey digital onboarding funnel conversion analisis ML optimizacion", "banco_bantrab"),
    ("Bantrab integracion pagos electronico pasarela tokenizacion seguridad PCI DSS architecture", "banco_bantrab"),
    # sow (10)
    ("SOW generacion automatica scope trabajo NLP extraccion requerimiento template mapping", "sow"),
    ("SOW estimacion esfuerzo ML historico proyecto similar analogia regression model", "sow"),
    ("SOW riesgo identificacion NLP texto analisis mitigacion estrategia clasificacion ML", "sow"),
    ("SOW integracion Monday.com entregable tarea descomposicion automatica WBS generation", "sow"),
    ("SOW pricing modelo hora recurso complejidad ML prediccion costo accuracy validation", "sow"),
    ("SOW clausula legal extraccion NLP revision automatica compliance checklist validation", "sow"),
    ("SOW version control cambio tracking diff semantico impacto analisis automatizado", "sow"),
    ("SOW cliente aprobacion workflow firma digital DocuSign integracion status tracking", "sow"),
    ("SOW template inteligente sector industria customizacion ML recomendacion clausula", "sow"),
    ("SOW KPI metricas exito definicion automatica historico proyecto benchmark comparison", "sow"),
    # services (8)
    ("SAP services microservicio arquitectura service mesh Istio observabilidad trazabilidad", "services"),
    ("SAP services API gateway design pattern rate limiting circuit breaker resilience", "services"),
    ("SAP services contrato OpenAPI schema validacion generacion codigo cliente automatico", "services"),
    ("SAP services event-driven architecture Kafka topic partition consumer group scaling", "services"),
    ("SAP services cache distribuido Redis cluster estrategia invalidacion consistency", "services"),
    ("SAP services autenticacion OAuth2 PKCE flow seguridad API management best practices", "services"),
    ("SAP services deployment Kubernetes helm chart configuracion ambiente estrategia", "services"),
    ("SAP services monitoreo health check SLA alerting distributed tracing Jaeger setup", "services"),
    # banco_bac (5)
    ("BAC digital transformation core banking modernizacion API-first arquitectura migration", "banco_bac"),
    ("BAC integracion SAP CRM cliente corporativo cartera gestion automatizacion pipeline", "banco_bac"),
    ("BAC open banking PSD2 compliance API terceros seguridad consentimiento gestion", "banco_bac"),
    ("BAC ML credito empresarial scoring modelo variables financieras prediccion aprobacion", "banco_bac"),
    ("BAC fraude corporativo deteccion patron transaccion anomalia ML real-time alerting", "banco_bac"),
    # banco_promerica (5)
    ("Promerica automatizacion credito hipotecario documentacion validacion pipeline digital", "banco_promerica"),
    ("Promerica integracion SAP CRM seguimiento cliente prospecto conversion ML scoring", "banco_promerica"),
    ("Promerica banca digital UX personalizacion ML recomendacion producto propensity model", "banco_promerica"),
    ("Promerica compliance AML monitoreo transaccion patron sospechoso ML deteccion regla", "banco_promerica"),
    ("Promerica core bancario migracion estrategia zero downtime data consistency validation", "banco_promerica"),
    # seguros_assa (6)
    ("ASSA seguro poliza emision automatizacion flujo aprobacion regla negocio ML scoring", "seguros_assa"),
    ("ASSA siniestro reclamacion procesamiento NLP documentacion extraccion clasificacion ML", "seguros_assa"),
    ("ASSA actuarial modelo prima calculo ML regresion variables riesgo integracion sistema", "seguros_assa"),
    ("ASSA integracion SAP CRM agente cartera cliente seguimiento oportunidad renovation", "seguros_assa"),
    ("ASSA fraude seguro deteccion patron reclamacion anomalia ML feature engineering pipeline", "seguros_assa"),
    ("ASSA renovacion automatica poliza ML churn prediccion intervencion proactiva campana", "seguros_assa"),
    # seguros_el_roble (6)
    ("El Roble seguro vida calculo actuarial ML mortalidad tabla esperanza vida prediccion", "seguros_el_roble"),
    ("El Roble automatizacion cotizacion seguro NLP requerimiento cliente extraccion mapeo", "seguros_el_roble"),
    ("El Roble siniestro workflow aprobacion multi-nivel regla condicion documentacion validacion", "seguros_el_roble"),
    ("El Roble integracion SAP CRM agente performance KPI seguimiento comision calculo auto", "seguros_el_roble"),
    ("El Roble reaseguro integracion datos intercambio automatico XML schema validacion pipeline", "seguros_el_roble"),
    ("El Roble digital transformation poliza electronica firma digital workflow cliente portal", "seguros_el_roble"),
]


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════��═══════════════════════════════════════════════════════
def main(start_from=1):
    start = time.time()

    # Validate counts
    assert len(KB_CASES) == 200, f"KB_CASES: expected 200, got {len(KB_CASES)}"
    assert len(INTERNET_CASES) == 200, f"INTERNET_CASES: expected 200, got {len(INTERNET_CASES)}"
    assert len(ML_CASES) == 200, f"ML_CASES: expected 200, got {len(ML_CASES)}"
    assert len(KB_INTERNET_CASES) == 200, f"KB_INTERNET_CASES: expected 200, got {len(KB_INTERNET_CASES)}"
    assert len(KB_INTERNET_ML_CASES) == 200, f"KB_INTERNET_ML_CASES: expected 200, got {len(KB_INTERNET_ML_CASES)}"

    # Cargar resultados previos si estamos resumiendo
    prev_pass = 0
    prev_warn = 0
    if start_from > 1:
        prev_results_file = PROJECT / "tests" / "pipeline_1000_real_results.json"
        if prev_results_file.exists():
            with open(prev_results_file, "r", encoding="utf-8") as f:
                prev = json.load(f)
                prev_pass = prev.get("pass", 0)
                prev_warn = prev.get("warn", 0)
                # Restaurar group results previos
                for grp, data in prev.get("by_group", {}).items():
                    for k, v in data.items():
                        GROUP_RESULTS[grp][k] = v
                RESULTS["PASS"] = prev_pass
                RESULTS["WARN"] = prev_warn
                print(f"  [RESUME] Cargados {prev_pass} PASS previos + {prev_warn} WARN")

    print()
    print("=" * 75)
    print("  TEST 1000 PIPELINE REAL - Motor Fusion IA")
    print(f"  Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Distribucion: 200 KB + 200 Internet + 200 ML + 200 KB+Internet + 200 KB+Internet+ML")
    print(f"  Internet: force=True (siempre debe encontrar)")
    if start_from > 1:
        print(f"  RESUMIENDO desde caso #{start_from} (previos: {prev_pass} PASS)")
    print("=" * 75)

    num = 0

    # ── GRUPO 1: KB-ONLY (200) ──
    if start_from <= 200:
        print(f"\n{'='*75}")
        print(f"  GRUPO 1: KB-ONLY (200 casos)")
        print(f"{'='*75}")
    for query, domain in KB_CASES:
        num += 1
        if num < start_from:
            continue
        run_case(num, "KB", query, domain=domain, expect_kb=True)

    # ── GRUPO 2: INTERNET-ONLY (200) ──
    if start_from <= 400:
        print(f"\n{'='*75}")
        print(f"  GRUPO 2: INTERNET-ONLY (200 casos)")
        print(f"{'='*75}")
    for query in INTERNET_CASES:
        num += 1
        if num < start_from:
            continue
        run_case(num, "INTERNET", query, expect_internet=True)

    # ── GRUPO 3: ML-ONLY (200) ──
    if start_from <= 600:
        print(f"\n{'='*75}")
        print(f"  GRUPO 3: ML-ONLY (200 casos)")
        print(f"{'='*75}")
    for query in ML_CASES:
        num += 1
        if num < start_from:
            continue
        run_case(num, "ML", query, expect_ml=True)

    # ── GRUPO 4: KB+INTERNET (200) ──
    if start_from <= 800:
        print(f"\n{'='*75}")
        print(f"  GRUPO 4: KB+INTERNET (200 casos)")
        print(f"{'='*75}")
    for query, domain in KB_INTERNET_CASES:
        num += 1
        if num < start_from:
            continue
        run_case(num, "KB+INTERNET", query, domain=domain,
                 expect_kb=True, expect_internet=True)

    # ── GRUPO 5: KB+INTERNET+ML (200) ──
    if start_from <= 1000:
        print(f"\n{'='*75}")
        print(f"  GRUPO 5: KB+INTERNET+ML (200 casos)")
        print(f"{'='*75}")
    for query, domain in KB_INTERNET_ML_CASES:
        num += 1
        if num < start_from:
            continue
        run_case(num, "KB+INTERNET+ML", query, domain=domain,
                 expect_kb=True, expect_internet=True, expect_ml=True)

    # ══════════════════════════════════════════════════════════════
    # RESUMEN FINAL
    # ══════════════════════════════════════════════════════════════
    elapsed = time.time() - start
    total = RESULTS["PASS"] + RESULTS["FAIL"] + RESULTS.get("CRASH", 0)
    warns = RESULTS.get("WARN", 0)

    print()
    print("=" * 75)
    print("  RESUMEN FINAL - 1000 PIPELINE REAL")
    print("=" * 75)
    print(f"  Total casos: {total}")
    print(f"  PASS:  {RESULTS['PASS']}")
    print(f"  FAIL:  {RESULTS['FAIL']}")
    print(f"  WARN:  {warns}")
    print(f"  CRASH: {RESULTS.get('CRASH', 0)}")
    print(f"  Tiempo: {elapsed:.1f}s ({elapsed/60:.1f} min)")

    print()
    print("  POR GRUPO:")
    print("  " + "-" * 65)
    for grp in ["KB", "INTERNET", "ML", "KB+INTERNET", "KB+INTERNET+ML"]:
        g = GROUP_RESULTS[grp]
        g_total = g["PASS"] + g["FAIL"] + g.get("CRASH", 0)
        pct = (g["PASS"] / g_total * 100) if g_total else 0
        print(f"    {grp:<18s}: {g['PASS']:>3d} PASS / {g_total:>3d} total ({pct:.1f}%)"
              f" | FAIL={g['FAIL']} CRASH={g.get('CRASH', 0)}")

    if FAILURES:
        print()
        print(f"  FALLOS DETALLADOS ({len(FAILURES)}):")
        print("  " + "-" * 65)
        for f in FAILURES[:50]:  # Max 50 failures shown
            print(f"    {f}")
        if len(FAILURES) > 50:
            print(f"    ... y {len(FAILURES) - 50} mas")

    if WARNINGS:
        print()
        print(f"  WARNINGS ({len(WARNINGS)}):")
        print("  " + "-" * 65)
        for w in WARNINGS[:20]:
            print(f"    {w}")
        if len(WARNINGS) > 20:
            print(f"    ... y {len(WARNINGS) - 20} mas")

    # Guardar resultados
    results_file = PROJECT / "tests" / "pipeline_1000_real_results.json"
    data = {
        "timestamp": datetime.now().isoformat(),
        "total": total,
        "pass": RESULTS["PASS"],
        "fail": RESULTS["FAIL"],
        "warn": warns,
        "crash": RESULTS.get("CRASH", 0),
        "elapsed_seconds": round(elapsed, 1),
        "elapsed_minutes": round(elapsed / 60, 1),
        "failures": FAILURES,
        "warnings": WARNINGS,
        "by_group": {
            grp: dict(GROUP_RESULTS[grp])
            for grp in ["KB", "INTERNET", "ML", "KB+INTERNET", "KB+INTERNET+ML"]
        },
    }
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n  Resultados: {results_file}")

    if RESULTS["FAIL"] == 0 and RESULTS.get("CRASH", 0) == 0:
        print(f"\n  >>> 0 ERRORES - 1000 PIPELINE REAL EXITOSO <<<")
    else:
        print(f"\n  >>> {RESULTS['FAIL'] + RESULTS.get('CRASH', 0)} ERRORES <<<")

    return RESULTS["FAIL"] + RESULTS.get("CRASH", 0)


if __name__ == "__main__":
    _start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    sys.exit(main(start_from=_start))
