#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
multi_agent.py - Feature 9: Multi-Agente con Paso de Estado
============================================================
Permite que sub-agentes especializados manejen sub-tareas
con estado compartido via working memory.

Agentes:
  - kb_researcher: busca en KB antes de responder
  - web_researcher: busca en internet si KB falla
  - domain_classifier: clasifica la query por dominio
  - route_suggester: sugiere archivos relevantes
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR

log = logging.getLogger("multi_agent")

AGENT_STATE_FILE = DATA_DIR / "agent_state.json"
AGENT_LOG_FILE = DATA_DIR / "agent_log.json"
MAX_LOG_ENTRIES = 200


class AgentResult:
    """Resultado de un agente."""
    def __init__(self, agent_name: str, success: bool, data: dict = None, error: str = ""):
        self.agent_name = agent_name
        self.success = success
        self.data = data or {}
        self.error = error
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "agent": self.agent_name,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp,
        }


def _load_state() -> dict:
    if AGENT_STATE_FILE.exists():
        try:
            return json.loads(AGENT_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"working_memory": {}, "last_run": {}}


def _save_state(state: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AGENT_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _log_agent_run(result: AgentResult):
    log_data = []
    if AGENT_LOG_FILE.exists():
        try:
            log_data = json.loads(AGENT_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    log_data.append(result.to_dict())
    if len(log_data) > MAX_LOG_ENTRIES:
        log_data = log_data[-MAX_LOG_ENTRIES:]
    AGENT_LOG_FILE.write_text(json.dumps(log_data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_kb_researcher(query: str) -> AgentResult:
    """Agente que busca en KB (ChromaDB + JSON)."""
    try:
        from core.vector_kb import ask_kb
        result = ask_kb(query)
        return AgentResult(
            "kb_researcher",
            success=result.get("found", False),
            data={
                "answer": result.get("answer", ""),
                "similarity": result.get("similarity", 0),
                "source": result.get("source", ""),
            },
        )
    except Exception as e:
        return AgentResult("kb_researcher", success=False, error=str(e))


def run_web_researcher(query: str) -> AgentResult:
    """Agente que busca en internet."""
    try:
        from core.web_search import search_web
        result = search_web(query)
        return AgentResult(
            "web_researcher",
            success=result.get("found", False),
            data={
                "summary": result.get("summary", ""),
                "internet_pct": result.get("internet_pct", 0),
            },
        )
    except Exception as e:
        return AgentResult("web_researcher", success=False, error=str(e))


def run_domain_classifier(query: str) -> AgentResult:
    """Agente que clasifica la query por dominio."""
    try:
        from core.domain_detector import detect_domain
        domains = detect_domain(query)
        return AgentResult(
            "domain_classifier",
            success=bool(domains),
            data={"domains": domains if isinstance(domains, list) else [domains]},
        )
    except Exception as e:
        return AgentResult("domain_classifier", success=False, error=str(e))


def run_route_suggester(query: str) -> AgentResult:
    """Agente que sugiere archivos relevantes."""
    try:
        from core.smart_file_routing import suggest_files
        files = suggest_files(query)
        return AgentResult(
            "route_suggester",
            success=bool(files),
            data={"suggested_files": files},
        )
    except Exception as e:
        return AgentResult("route_suggester", success=False, error=str(e))


def run_graph_navigator(query: str, domain: str = "") -> AgentResult:
    """Agente que navega el grafo de dominios para encontrar relacionados."""
    try:
        from core.domain_graph import find_related
        if not domain:
            # Primero clasificar
            classifier = run_domain_classifier(query)
            if classifier.success and classifier.data.get("domains"):
                domain = classifier.data["domains"][0]
                if isinstance(domain, dict):
                    domain = domain.get("name", domain.get("domain", ""))

        if not domain:
            return AgentResult("graph_navigator", success=False, error="No domain detected")

        related = find_related(str(domain))
        return AgentResult(
            "graph_navigator",
            success=bool(related),
            data={"domain": domain, "related": related},
        )
    except Exception as e:
        return AgentResult("graph_navigator", success=False, error=str(e))


def run_pipeline(query: str) -> dict:
    """
    Ejecuta el pipeline multi-agente completo.
    Orden: classify -> graph -> kb_search -> route -> (web si KB falla)
    Con paso de estado entre agentes.
    """
    state = _load_state()
    state["working_memory"] = {"query": query, "start_time": time.time()}

    pipeline_results = {}

    # 1. Clasificar dominio
    classifier = run_domain_classifier(query)
    pipeline_results["classifier"] = classifier.to_dict()
    if classifier.success:
        state["working_memory"]["domains"] = classifier.data.get("domains", [])

    # 2. Navegar grafo
    domain = ""
    if classifier.success and classifier.data.get("domains"):
        d = classifier.data["domains"][0]
        domain = d if isinstance(d, str) else d.get("name", "")
    graph = run_graph_navigator(query, domain)
    pipeline_results["graph"] = graph.to_dict()
    if graph.success:
        state["working_memory"]["related_domains"] = graph.data.get("related", [])

    # 3. Buscar en KB
    kb = run_kb_researcher(query)
    pipeline_results["kb"] = kb.to_dict()
    state["working_memory"]["kb_found"] = kb.success

    # 4. Sugerir archivos
    router = run_route_suggester(query)
    pipeline_results["router"] = router.to_dict()

    # 5. Web search solo si KB no encontró suficiente
    if not kb.success or kb.data.get("similarity", 0) < 0.5:
        web = run_web_researcher(query)
        pipeline_results["web"] = web.to_dict()
    else:
        pipeline_results["web"] = {"agent": "web_researcher", "skipped": True, "reason": "KB sufficient"}

    # Guardar estado
    state["working_memory"]["elapsed"] = time.time() - state["working_memory"].get("start_time", time.time())
    state["last_run"] = {
        "query": query[:100],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents_run": len([r for r in pipeline_results.values() if not r.get("skipped")]),
    }
    _save_state(state)

    return pipeline_results


def get_agent_stats() -> dict:
    """Estadísticas para dashboard."""
    if not AGENT_LOG_FILE.exists():
        return {"total_runs": 0, "agents": {}}

    try:
        log_data = json.loads(AGENT_LOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"total_runs": 0, "agents": {}}

    from collections import Counter
    agent_counts = Counter()
    agent_success = Counter()
    for entry in log_data:
        name = entry.get("agent", "unknown")
        agent_counts[name] += 1
        if entry.get("success"):
            agent_success[name] += 1

    agents = {}
    for name, count in agent_counts.items():
        agents[name] = {
            "runs": count,
            "success": agent_success[name],
            "rate": round(agent_success[name] / count * 100, 1) if count > 0 else 0,
        }

    return {"total_runs": len(log_data), "agents": agents}
