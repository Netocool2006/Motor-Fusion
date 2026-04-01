# -*- coding: utf-8 -*-
"""
tui.py -- Terminal UI para Motor_IA (Engram-style)
===================================================
Visualiza memoria, grafo asociativo, patrones y working memory
directamente en la terminal.

Usa `rich` (ya instalado con Claude Code) para tablas, paneles y
resaltado de sintaxis. Sin dependencias adicionales.

Motor_IA ventaja sobre Engram:
  Engram usa Bubbletea (Go/TUI completo con input interactivo).
  Nuestra TUI usa rich para visualizacion inmediata desde CLI.
  Mas simple de mantener, sin dependencias de Go.

Uso:
  python -m core.tui                    # menu principal
  python -m core.tui memory             # tabla de patrones
  python -m core.tui working            # working memory actual
  python -m core.tui graph              # grafo asociativo
  python -m core.tui stats              # estadisticas completas
  python -m core.tui search <query>     # buscar en episodic index
  python -m core.tui timeline <query>   # timeline search
  python -m core.tui kb <query>         # buscar en knowledge base
"""

import sys
import json
from datetime import datetime, timezone
from pathlib import Path

_MOTOR_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_MOTOR_DIR))

# -- rich import con fallback a texto plano --
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    _RICH = True
except ImportError:
    _RICH = False

_console = None


def _get_console():
    global _console
    if _console is None:
        if _RICH:
            from rich.console import Console
            _console = Console()
        else:
            class _PlainConsole:
                def print(self, *args, **kwargs):
                    print(*args)
                def rule(self, title=""):
                    print(f"\n{'='*60} {title} {'='*60}")
            _console = _PlainConsole()
    return _console


# ======================================================================
#  VISTAS
# ======================================================================

def show_stats():
    """Estadisticas de todos los modulos."""
    console = _get_console()

    stats = {}
    modules = [
        ("learning_memory",  "core.learning_memory",  "get_stats"),
        ("working_memory",   "core.working_memory",   "get_stats"),
        ("associative",      "core.associative_memory","get_stats"),
        ("episodic_index",   "core.episodic_index",   "get_stats"),
        ("memory_pruner",    "core.memory_pruner",    "get_stats"),
        ("hint_tracker",     "core.hint_tracker",     "get_stats"),
        ("consolidator",     "core.memory_consolidator","get_stats"),
    ]

    for label, module, fn in modules:
        try:
            import importlib
            mod = importlib.import_module(module)
            stats[label] = getattr(mod, fn)()
        except Exception as e:
            stats[label] = {"error": str(e)[:50]}

    if _RICH:
        from rich.table import Table
        from rich import box
        t = Table(title="Motor_IA Stats", box=box.ROUNDED, show_header=True)
        t.add_column("Modulo", style="cyan", min_width=20)
        t.add_column("Datos", style="white")
        for label, data in stats.items():
            t.add_row(label, json.dumps(data, ensure_ascii=False))
        console.print(t)
    else:
        print("\n=== Motor_IA Stats ===")
        for label, data in stats.items():
            print(f"  {label}: {json.dumps(data, ensure_ascii=False)}")


def show_memory(scope: str = None, task_type: str = None, limit: int = 30):
    """Tabla de patrones de learning_memory."""
    console = _get_console()

    try:
        from core.learning_memory import _load_memory
        mem = _load_memory()
    except Exception as e:
        console.print(f"[red]Error cargando learning_memory: {e}[/red]" if _RICH else f"Error: {e}")
        return

    patterns = [
        p for p in mem.get("patterns", {}).values()
        if not p.get("deleted_at")
        and (scope is None or p.get("scope") == scope)
        and (task_type is None or p.get("task_type") == task_type)
    ]

    patterns.sort(key=lambda p: p.get("last_used", ""), reverse=True)
    patterns = patterns[:limit]

    if _RICH:
        from rich.table import Table
        from rich import box
        t = Table(
            title=f"Learning Memory — {len(patterns)} patrones",
            box=box.SIMPLE_HEAD, show_header=True, expand=True
        )
        t.add_column("ID",       style="dim",    width=12)
        t.add_column("Tipo",     style="cyan",   width=14)
        t.add_column("Key",      style="yellow", width=25)
        t.add_column("Scope",    style="green",  width=8)
        t.add_column("Exito%",   style="white",  width=7)
        t.add_column("Reusos",   style="white",  width=7)
        t.add_column("Tags",     style="dim",    width=20)
        t.add_column("Ultimo",   style="dim",    width=16)

        for p in patterns:
            sr = p.get("success_rate", 0)
            sr_str = f"{sr:.0%}" if isinstance(sr, float) else str(sr)
            last = (p.get("last_used") or "")[:16].replace("T", " ")
            tags = ", ".join((p.get("tags") or [])[:3])
            t.add_row(
                p.get("id", "")[:10],
                p.get("task_type", "")[:13],
                p.get("context_key", "")[:24],
                p.get("scope", "project"),
                sr_str,
                str(p.get("reuse_count", 0)),
                tags[:19],
                last,
            )
        console.print(t)
    else:
        print(f"\n=== Learning Memory ({len(patterns)} patrones) ===")
        for p in patterns:
            print(f"  [{p.get('task_type','')}] {p.get('context_key','')[:40]} | "
                  f"scope={p.get('scope','project')} | "
                  f"exito={p.get('success_rate',0):.0%} | "
                  f"reusos={p.get('reuse_count',0)}")


def show_working_memory():
    """Working memory actual agrupada por categoria."""
    console = _get_console()

    try:
        from core.working_memory import wm_get, get_stats
        items = wm_get()
        stats = get_stats()
    except Exception as e:
        console.print(f"Error: {e}")
        return

    if not items:
        msg = "Working memory vacia."
        console.print(f"[dim]{msg}[/dim]" if _RICH else msg)
        return

    # Agrupar por categoria
    by_cat: dict = {}
    for item in items:
        cat = item.get("category", "observation")
        by_cat.setdefault(cat, []).append(item)

    CAT_COLORS = {
        "error": "red", "fix": "green", "decision": "blue",
        "hypothesis": "yellow", "observation": "white",
        "context": "cyan", "todo": "magenta",
    }

    if _RICH:
        from rich.panel import Panel
        from rich.text import Text
        console.rule(f"Working Memory — {stats['total_items']} items | sesion: {stats.get('session_id','')[:16]}")
        for cat, cat_items in by_cat.items():
            color = CAT_COLORS.get(cat, "white")
            lines = []
            for item in cat_items[-5:]:
                ts = (item.get("timestamp","")[:16]).replace("T"," ")
                prom = " [promoted]" if item.get("promoted") else ""
                lines.append(f"[dim]{ts}[/dim]  {item['content'][:120]}{prom}")
            panel_content = "\n".join(lines)
            console.print(Panel(panel_content, title=f"[{color}]{cat.upper()}[/{color}]",
                                border_style=color, expand=False))
    else:
        print(f"\n=== Working Memory ({stats['total_items']} items) ===")
        for cat, cat_items in by_cat.items():
            print(f"\n  [{cat.upper()}]")
            for item in cat_items[-5:]:
                ts = (item.get("timestamp","")[:16]).replace("T"," ")
                print(f"    {ts}  {item['content'][:100]}")


def show_graph(limit: int = 20):
    """Grafo asociativo: nodos y edges."""
    console = _get_console()

    try:
        from core.associative_memory import _load_graph, get_stats
        graph = _load_graph()
        stats = get_stats()
    except Exception as e:
        console.print(f"Error: {e}")
        return

    edges = graph.get("edges", [])[:limit]

    if _RICH:
        from rich.table import Table
        from rich import box
        t = Table(
            title=f"Grafo Asociativo — {stats['nodes']} nodos, {stats['edges']} edges",
            box=box.SIMPLE_HEAD
        )
        t.add_column("Desde",    style="cyan",   width=14)
        t.add_column("Relacion", style="yellow", width=12)
        t.add_column("Hacia",    style="green",  width=14)
        t.add_column("Fecha",    style="dim",    width=16)
        for edge in edges:
            ts = (edge.get("created_at","")[:16]).replace("T"," ")
            t.add_row(
                edge.get("from","")[:13],
                edge.get("relation",""),
                edge.get("to","")[:13],
                ts,
            )
        console.print(t)
        # Relaciones por tipo
        if stats.get("relation_types"):
            console.print("\nDistribucion por tipo:")
            for rel, count in sorted(stats["relation_types"].items(),
                                     key=lambda x: -x[1]):
                console.print(f"  [yellow]{rel}[/yellow]: {count}")
    else:
        print(f"\n=== Grafo Asociativo ({stats['nodes']} nodos, {stats['edges']} edges) ===")
        for edge in edges:
            print(f"  {edge.get('from','')[:12]} --[{edge.get('relation','')}]--> {edge.get('to','')[:12]}")


def show_search(query: str):
    """Busqueda episodica."""
    console = _get_console()
    try:
        from core.episodic_index import search
        results = search(query, limit=10)
    except Exception as e:
        console.print(f"Error: {e}")
        return

    if not results:
        console.print("Sin resultados." if not _RICH else "[dim]Sin resultados.[/dim]")
        return

    if _RICH:
        from rich.table import Table
        from rich import box
        t = Table(title=f'Episodic Search: "{query}"', box=box.SIMPLE_HEAD)
        t.add_column("Fecha",   style="dim",    width=12)
        t.add_column("Dominio", style="cyan",   width=12)
        t.add_column("Snippet", style="white")
        for r in results:
            t.add_row(r.get("date",""), r.get("domain",""), r.get("snippet","")[:120])
        console.print(t)
    else:
        print(f'\n=== Episodic Search: "{query}" ===')
        for r in results:
            print(f"  [{r.get('date','')}] [{r.get('domain','')}] {r.get('snippet','')[:100]}")


def show_timeline(query: str):
    """Timeline search con contexto before/after."""
    console = _get_console()
    try:
        from core.episodic_index import timeline_search
        results = timeline_search(query, before=2, after=2)
    except Exception as e:
        console.print(f"Error: {e}")
        return

    if not results:
        console.print("Sin resultados." if not _RICH else "[dim]Sin resultados.[/dim]")
        return

    if _RICH:
        from rich.panel import Panel
        console.rule(f'Timeline: "{query}" — {len(results)} resultado(s)')
        for r in results:
            m = r["match"]
            before_lines = "\n".join(
                f"  [dim]{c['date']}[/dim] [{c['domain']}] {c['snippet'][:80]}"
                for c in r.get("context_before", [])
            )
            match_line = f"  [bold yellow]>> {m['date']} [{m['domain']}] {m['snippet'][:100]}[/bold yellow]"
            after_lines = "\n".join(
                f"  [dim]{c['date']}[/dim] [{c['domain']}] {c['snippet'][:80]}"
                for c in r.get("context_after", [])
            )
            content = "\n".join(filter(None, [before_lines, match_line, after_lines]))
            console.print(Panel(content, border_style="yellow", expand=False))
    else:
        print(f'\n=== Timeline: "{query}" ===')
        for r in results:
            for c in r.get("context_before", []):
                print(f"  {c['date']} [{c['domain']}] {c['snippet'][:80]}")
            m = r["match"]
            print(f"  >> {m['date']} [{m['domain']}] {m['snippet'][:100]}")
            for c in r.get("context_after", []):
                print(f"  {c['date']} [{c['domain']}] {c['snippet'][:80]}")


def show_kb(query: str):
    """Busqueda en knowledge base."""
    console = _get_console()
    try:
        from core.knowledge_base import search_knowledge
        results = search_knowledge(query)
    except Exception as e:
        console.print(f"Error: {e}")
        return

    if not results:
        console.print("Sin resultados." if not _RICH else "[dim]Sin resultados.[/dim]")
        return

    if _RICH:
        from rich.table import Table
        from rich import box
        t = Table(title=f'KB Search: "{query}"', box=box.SIMPLE_HEAD)
        t.add_column("Dominio",  style="cyan",   width=12)
        t.add_column("Tipo",     style="yellow", width=10)
        t.add_column("Contenido",style="white")
        for r in results:
            content = str(r.get("content", r.get("facts", r.get("solution", ""))))[:120]
            t.add_row(r.get("domain",""), r.get("type",""), content)
        console.print(t)
    else:
        print(f'\n=== KB Search: "{query}" ===')
        for r in results:
            print(f"  [{r.get('domain','')}] {str(r.get('content',''))[:100]}")


def show_menu():
    """Menu principal."""
    console = _get_console()
    if _RICH:
        from rich.panel import Panel
        console.print(Panel(
            "[cyan]memory[/cyan]          — patrones de learning_memory\n"
            "[cyan]working[/cyan]         — working memory actual\n"
            "[cyan]graph[/cyan]           — grafo asociativo\n"
            "[cyan]stats[/cyan]           — estadisticas completas\n"
            "[cyan]search <query>[/cyan]  — busqueda episodica\n"
            "[cyan]timeline <query>[/cyan]— timeline con contexto\n"
            "[cyan]kb <query>[/cyan]      — busqueda en knowledge base",
            title="Motor_IA TUI",
            border_style="blue",
        ))
    else:
        print("\n=== Motor_IA TUI ===")
        print("  memory  working  graph  stats")
        print("  search <query>  timeline <query>  kb <query>")


# ======================================================================
#  MAIN
# ======================================================================

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        show_menu()
        sys.exit(0)

    cmd = args[0].lower()
    rest = " ".join(args[1:])

    if cmd == "memory":
        show_memory(
            scope=None if "--all" in args else None,
            limit=int(args[2]) if len(args) > 2 and args[2].isdigit() else 30,
        )
    elif cmd == "working":
        show_working_memory()
    elif cmd == "graph":
        show_graph()
    elif cmd == "stats":
        show_stats()
    elif cmd == "search" and rest:
        show_search(rest)
    elif cmd == "timeline" and rest:
        show_timeline(rest)
    elif cmd == "kb" and rest:
        show_kb(rest)
    else:
        show_menu()
