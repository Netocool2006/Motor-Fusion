"""
mcp_kb_server.py -- MCP Server para Claude Desktop (Motor Unificado)
====================================================================
Expone el KB del Motor_IA como herramientas MCP.
Claude Desktop las llama automaticamente segun instrucciones del sistema.

Importa directamente desde core modules (sin subprocess).

Instalar: pip install mcp
Correr:   python "<ruta-instalacion>/mcp_kb_server.py"

Configurar en Claude Desktop -> Settings -> MCP:
{
  "mcpServers": {
    "motor-ia": {
      "command": "python",
      "args": ["<ruta-instalacion>/mcp_kb_server.py"]
    }
  }
}
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Asegurar path del Motor
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

from core.knowledge_base import (
    search as kb_search,
    cross_domain_search,
    add_pattern as kb_add_pattern,
    add_fact as kb_add_fact,
    get_global_stats,
    export_context,
)
from core.learning_memory import (
    register_pattern,
    get_stats as lm_stats,
    export_for_context as lm_export,
    search_pattern as lm_search,
)

server = Server("motor-ia-kb")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="buscar_kb",
            description=(
                "Busca en la base de conocimiento GBM. "
                "USAR SIEMPRE antes de responder sobre: SOW, BoM, SAP CRM, "
                "Monday.com, propuestas economicas, precios, clientes Guatemala. "
                "Devuelve recetas y patrones aprendidos especificos de GBM."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Tema a buscar (ej: 'SOW estructura', 'SAP login', 'IVA Guatemala')"
                    },
                    "domain": {
                        "type": "string",
                        "description": "Dominio especifico (sow, bom, sap_tierra, monday, business_rules, catalog). Opcional.",
                        "default": ""
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="guardar_aprendizaje",
            description=(
                "Guarda automaticamente un aprendizaje nuevo en el KB. "
                "LLAMAR SIN QUE EL USUARIO LO PIDA cuando: "
                "1) Se resolvio un error o problema, "
                "2) Se descubrio como funciona algo (SAP, Monday, cliente), "
                "3) Se aplico una formula o estructura nueva, "
                "4) El usuario confirmo que algo funciono. "
                "Esto es aprendizaje automatico -- hacerlo siempre."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "titulo": {
                        "type": "string",
                        "description": "Nombre corto del patron (ej: 'sap_campo_cantidad_requiere_tab')"
                    },
                    "dominio": {
                        "type": "string",
                        "description": "Dominio: sow, bom, sap_tierra, monday, business_rules, catalog, general"
                    },
                    "contenido": {
                        "type": "string",
                        "description": "Que se aprendio: descripcion, pasos, codigo, error y solucion"
                    },
                    "tags": {
                        "type": "string",
                        "description": "Tags separados por coma (ej: 'sap,campo,validacion')"
                    }
                },
                "required": ["titulo", "dominio", "contenido"]
            }
        ),
        types.Tool(
            name="listar_patrones",
            description="Lista los patrones aprendidos en learning_memory con sus tasas de exito.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dominio": {
                        "type": "string",
                        "description": "Filtrar por dominio. Vacio = todos.",
                        "default": ""
                    }
                }
            }
        ),
        types.Tool(
            name="registrar_error_resuelto",
            description=(
                "Registra un error y su solucion en learning_memory. "
                "LLAMAR AUTOMATICAMENTE cuando se corrigio un error -- "
                "sin esperar que el usuario lo pida. "
                "Esto evita repetir el mismo error en sesiones futuras."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "error": {
                        "type": "string",
                        "description": "Descripcion del error que ocurrio"
                    },
                    "solucion": {
                        "type": "string",
                        "description": "Como se resolvio"
                    },
                    "dominio": {
                        "type": "string",
                        "description": "Dominio donde ocurrio: sow, bom, sap_tierra, monday, general"
                    }
                },
                "required": ["error", "solucion", "dominio"]
            }
        ),
        types.Tool(
            name="estadisticas",
            description="Muestra cuantos patrones, recetas y errores hay en el KB.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    if name == "buscar_kb":
        query = arguments["query"]
        domain = arguments.get("domain", "")

        lines = []

        # Buscar en KB (knowledge_base)
        try:
            if domain:
                results = kb_search(domain=domain, text_query=query)
                if results:
                    lines.append(f"=== KB/{domain} ({len(results)} resultados) ===")
                    for r in results[:5]:
                        sol = r.get("solution", r.get("fact", {}))
                        key = r.get("key", "?")
                        notes = ""
                        if isinstance(sol, dict):
                            notes = sol.get("notes", sol.get("rule", ""))[:300]
                        lines.append(f"[{key}] {notes}")
            else:
                results = cross_domain_search(text_query=query, limit=5)
                if results:
                    for dom, entries in results.items():
                        lines.append(f"=== KB/{dom} ({len(entries)} resultados) ===")
                        for e in entries[:3]:
                            sol = e.get("solution", e.get("fact", {}))
                            key = e.get("key", "?")
                            notes = ""
                            if isinstance(sol, dict):
                                notes = sol.get("notes", sol.get("rule", ""))[:300]
                            lines.append(f"[{key}] {notes}")
        except Exception as ex:
            lines.append(f"[KB error] {ex}")

        # Buscar en learning_memory
        try:
            lm_results = lm_search(text_query=query, limit=3)
            if lm_results:
                lines.append(f"\n=== Learning Memory ({len(lm_results)} patrones) ===")
                for p in lm_results[:3]:
                    sol = p.get("solution", {})
                    sr = p.get("stats", {}).get("success_rate", 0)
                    notes = sol.get("notes", "")[:200]
                    lines.append(f"[{p.get('task_type','?')}] exito={sr*100:.0f}% | {notes}")
        except Exception:
            pass

        result = "\n".join(lines) if lines else f"Sin resultados para '{query}' en el KB."
        return [types.TextContent(type="text", text=result)]

    elif name == "guardar_aprendizaje":
        titulo    = arguments["titulo"]
        dominio   = arguments["dominio"]
        contenido = arguments["contenido"]
        tags_str  = arguments.get("tags", "general,mcp")
        tags_list = [t.strip() for t in tags_str.split(",") if t.strip()]

        msgs = []

        # Guardar como fact en knowledge_base
        try:
            kb_add_fact(
                domain=dominio,
                key=titulo,
                fact={"rule": contenido, "source": "claude_desktop_mcp"},
                tags=tags_list + ["mcp_learned"],
            )
            msgs.append(f"[KB] Guardado en dominio '{dominio}': {titulo}")
        except Exception as e:
            msgs.append(f"[KB error] {e}")

        # Registrar en learning_memory como patron exitoso
        try:
            register_pattern(
                domain=dominio,
                task_type=titulo,
                solution={
                    "strategy": "mcp_learned",
                    "notes": contenido[:500],
                },
                tags=tags_list + ["mcp_learned"],
            )
            msgs.append("[LM] Patron registrado en learning_memory")
        except Exception as e:
            msgs.append(f"[LM error] {e}")

        return [types.TextContent(type="text", text="\n".join(msgs))]

    elif name == "listar_patrones":
        dominio = arguments.get("dominio", "")
        try:
            result = lm_export(task_type=dominio if dominio else None, limit=20)
            return [types.TextContent(type="text", text=result or "Sin patrones registrados.")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {e}")]

    elif name == "registrar_error_resuelto":
        error    = arguments["error"]
        solucion = arguments["solucion"]
        dominio  = arguments["dominio"]

        patron_id = f"error_resuelto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        contenido = f"ERROR: {error}\nSOLUCION: {solucion}"

        msgs = []

        # Guardar en KB
        try:
            kb_add_fact(
                domain=dominio,
                key=patron_id,
                fact={"rule": contenido, "source": "error_fix_mcp"},
                tags=[dominio, "error_fix", "auto_captured"],
            )
            msgs.append(f"[KB] Error+solucion guardados en '{dominio}': {patron_id}")
        except Exception as e:
            msgs.append(f"[KB error] {e}")

        # Registrar en learning_memory
        try:
            register_pattern(
                domain=dominio,
                task_type=patron_id,
                solution={
                    "strategy": "error_fix",
                    "error_messages": [error[:300]],
                    "fix_command": solucion[:500],
                    "notes": contenido[:500],
                },
                tags=[dominio, "error_fix", "auto_captured"],
            )
            msgs.append("[LM] Patron error->fix registrado")
        except Exception as e:
            msgs.append(f"[LM error] {e}")

        return [types.TextContent(type="text", text="\n".join(msgs))]

    elif name == "estadisticas":
        lines = []

        # Stats de knowledge_base
        try:
            kb_stats = get_global_stats()
            lines.append("=== Knowledge Base ===")
            lines.append(f"  Dominios: {kb_stats.get('domain_count', 0)}")
            lines.append(f"  Patrones totales: {kb_stats.get('total_patterns', 0)}")
            lines.append(f"  Facts totales: {kb_stats.get('total_facts', 0)}")
            for dom, info in kb_stats.get("domains", {}).items():
                p_count = info.get("patterns", 0)
                f_count = info.get("facts", 0)
                if p_count or f_count:
                    lines.append(f"  {dom}: {p_count}p / {f_count}f")
        except Exception as e:
            lines.append(f"[KB stats error] {e}")

        # Stats de learning_memory
        try:
            lm_s = lm_stats()
            lines.append("\n=== Learning Memory ===")
            lines.append(f"  Patrones totales: {lm_s.get('total_patterns', 0)}")
            lines.append(f"  Exito promedio: {lm_s.get('avg_success_rate', 0)*100:.0f}%")
            by_type = lm_s.get("by_type", {})
            if by_type:
                for t, count in list(by_type.items())[:10]:
                    lines.append(f"  {t}: {count}")
        except Exception as e:
            lines.append(f"[LM stats error] {e}")

        return [types.TextContent(type="text", text="\n".join(lines))]

    return [types.TextContent(type="text", text=f"Herramienta desconocida: {name}")]


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
