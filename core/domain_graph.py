#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
domain_graph.py - Feature 1: Graph DB de dominios con NetworkX
==============================================================
Convierte las co-ocurrencias y relaciones estáticas de domains.json
en un grafo consultable. Permite:
  - Buscar dominios relacionados por proximidad en el grafo
  - Fortalecer/debilitar edges con uso real
  - Cross-domain search inteligente
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone

try:
    import networkx as nx
except ImportError:
    nx = None

from config import KNOWLEDGE_DIR, DATA_DIR, DOMAINS_FILE

log = logging.getLogger("domain_graph")

GRAPH_FILE = DATA_DIR / "domain_graph.json"
COOCCUR_FILE = DATA_DIR / "domain_cooccurrence.json"
MARKOV_FILE = DATA_DIR / "domain_markov.json"


def _load_cooccurrence() -> dict:
    """Carga la co-ocurrencia de dominios desde disco."""
    if COOCCUR_FILE.exists():
        try:
            return json.loads(COOCCUR_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _load_domains_relations() -> dict:
    """Extrae related_domains desde domains.json."""
    if not DOMAINS_FILE.exists():
        return {}
    try:
        data = json.loads(DOMAINS_FILE.read_text(encoding="utf-8"))
        relations = {}
        if isinstance(data, dict):
            for name, info in data.items():
                if isinstance(info, dict) and "related_domains" in info:
                    relations[name] = info["related_domains"]
        return relations
    except Exception:
        return {}


def build_graph() -> "nx.Graph":
    """
    Construye el grafo de dominios desde:
    1. Co-ocurrencias reales (domain_cooccurrence.json)
    2. Relaciones estáticas (domains.json -> related_domains)
    3. Markov chains (domain_markov.json)
    """
    if nx is None:
        raise ImportError("networkx no está instalado: pip install networkx")

    G = nx.Graph()

    # Agregar todos los dominios como nodos
    if DOMAINS_FILE.exists():
        try:
            data = json.loads(DOMAINS_FILE.read_text(encoding="utf-8"))
            for name, info in data.items():
                if isinstance(info, dict):
                    G.add_node(name, **{
                        "description": info.get("description", ""),
                        "entries": info.get("num_entries", 0),
                    })
        except Exception:
            pass

    # 1. Edges desde co-ocurrencia (peso = cantidad de co-ocurrencias)
    cooccur = _load_cooccurrence()
    for domain_a, neighbors in cooccur.items():
        if not isinstance(neighbors, dict):
            continue
        for domain_b, count in neighbors.items():
            if domain_a == domain_b or not isinstance(count, (int, float)):
                continue
            if G.has_edge(domain_a, domain_b):
                G[domain_a][domain_b]["weight"] += count
                G[domain_a][domain_b]["sources"].add("cooccurrence")
            else:
                G.add_edge(domain_a, domain_b, weight=count, sources={"cooccurrence"})

    # 2. Edges desde relaciones estáticas
    relations = _load_domains_relations()
    for domain, related in relations.items():
        if not isinstance(related, list):
            continue
        for rel in related:
            if G.has_edge(domain, rel):
                G[domain][rel]["weight"] += 5  # Boost para relaciones explícitas
                G[domain][rel]["sources"].add("static")
            else:
                G.add_edge(domain, rel, weight=5, sources={"static"})

    # 3. Edges desde Markov chains
    if MARKOV_FILE.exists():
        try:
            markov = json.loads(MARKOV_FILE.read_text(encoding="utf-8"))
            for domain_a, transitions in markov.items():
                if not isinstance(transitions, dict):
                    continue
                for domain_b, prob in transitions.items():
                    if domain_a == domain_b:
                        continue
                    w = int(prob * 10) if isinstance(prob, float) else 1
                    if G.has_edge(domain_a, domain_b):
                        G[domain_a][domain_b]["weight"] += w
                        G[domain_a][domain_b]["sources"].add("markov")
                    else:
                        G.add_edge(domain_a, domain_b, weight=w, sources={"markov"})
        except Exception:
            pass

    return G


def find_related(domain: str, depth: int = 2, top_n: int = 10) -> list[dict]:
    """
    Encuentra dominios relacionados a `domain` usando el grafo.
    Retorna lista de {domain, weight, path_length} ordenada por peso.
    """
    G = build_graph()
    if domain not in G:
        return []

    related = {}
    for node in G.nodes():
        if node == domain:
            continue
        try:
            path_len = nx.shortest_path_length(G, domain, node)
        except nx.NetworkXNoPath:
            continue
        if path_len > depth:
            continue
        # Peso = suma de pesos en el camino más corto
        try:
            path = nx.shortest_path(G, domain, node, weight="weight")
            total_weight = sum(
                G[path[i]][path[i + 1]].get("weight", 1) for i in range(len(path) - 1)
            )
        except Exception:
            total_weight = 1
        related[node] = {"domain": node, "weight": total_weight, "path_length": path_len}

    return sorted(related.values(), key=lambda x: (-x["weight"], x["path_length"]))[:top_n]


def strengthen_edge(domain_a: str, domain_b: str, amount: int = 1):
    """Fortalece la relación entre dos dominios (llamar tras uso conjunto)."""
    cooccur = _load_cooccurrence()
    if domain_a not in cooccur:
        cooccur[domain_a] = {}
    if domain_b not in cooccur:
        cooccur[domain_b] = {}
    cooccur[domain_a][domain_b] = cooccur[domain_a].get(domain_b, 0) + amount
    cooccur[domain_b][domain_a] = cooccur[domain_b].get(domain_a, 0) + amount
    COOCCUR_FILE.write_text(json.dumps(cooccur, ensure_ascii=False, indent=2), encoding="utf-8")


def get_graph_stats() -> dict:
    """Retorna estadísticas del grafo de dominios."""
    G = build_graph()
    stats = {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "density": round(nx.density(G), 4) if G.number_of_nodes() > 1 else 0,
        "connected_components": nx.number_connected_components(G),
        "top_connected": [],
    }
    # Top 10 nodos más conectados
    degree_list = sorted(G.degree(), key=lambda x: x[1], reverse=True)[:10]
    stats["top_connected"] = [{"domain": d, "connections": c} for d, c in degree_list]
    return stats


def export_graph_json() -> dict:
    """Exporta el grafo completo como JSON (para dashboard)."""
    G = build_graph()
    nodes = []
    for n, data in G.nodes(data=True):
        nodes.append({"id": n, "entries": data.get("entries", 0), "description": data.get("description", "")})
    edges = []
    for u, v, data in G.edges(data=True):
        edges.append({
            "source": u,
            "target": v,
            "weight": data.get("weight", 1),
            "sources": list(data.get("sources", [])),
        })
    return {"nodes": nodes, "edges": edges, "stats": get_graph_stats()}


def save_graph_cache():
    """Guarda el grafo en disco para acceso rápido."""
    graph_data = export_graph_json()
    graph_data["cached_at"] = datetime.now(timezone.utc).isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_FILE.write_text(json.dumps(graph_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return graph_data


# CLI
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "related":
        domain = sys.argv[2] if len(sys.argv) > 2 else "sap_tierra"
        results = find_related(domain)
        print(f"\nDominios relacionados a '{domain}':")
        for r in results:
            print(f"  {r['domain']:30s} peso={r['weight']:3d}  dist={r['path_length']}")
    elif len(sys.argv) > 1 and sys.argv[1] == "stats":
        stats = get_graph_stats()
        print(f"\nGraph Stats:")
        print(f"  Nodos: {stats['nodes']}")
        print(f"  Edges: {stats['edges']}")
        print(f"  Densidad: {stats['density']}")
        print(f"  Componentes: {stats['connected_components']}")
        print(f"  Top conectados:")
        for t in stats['top_connected']:
            print(f"    {t['domain']:30s} {t['connections']} conexiones")
    else:
        data = save_graph_cache()
        print(f"Grafo guardado: {len(data['nodes'])} nodos, {len(data['edges'])} edges")
