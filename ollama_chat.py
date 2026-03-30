"""
ollama_chat.py -- Chat interactivo con Ollama + Motor_IA KB (Motor Unificado)
=============================================================================
Punto de entrada para usar modelos locales con toda la inteligencia
contextual del Motor inyectada automaticamente.

Uso:
    python ollama_chat.py                            # Qwen3:4b, modo interactivo
    python ollama_chat.py --model llama3:8b          # Otro modelo
    python ollama_chat.py --domain sow               # Precarga dominio especifico
    python ollama_chat.py --query "revisa mi bom"    # Consulta unica, no interactivo
    python ollama_chat.py --list-models              # Ver modelos instalados
    python ollama_chat.py --no-kb                    # Sin inyeccion de KB
    python ollama_chat.py --no-stream                # Respuesta completa al final
"""

import sys
import json
import argparse
from pathlib import Path

# Asegurar path del Motor
_MOTOR_DIR = Path(__file__).parent
if str(_MOTOR_DIR) not in sys.path:
    sys.path.insert(0, str(_MOTOR_DIR))

from adapters.ollama import OllamaAdapter, DEFAULT_MODEL
from config import SESSION_HISTORY_FILE, NOTIFY_FILE, MAX_KB_CHARS
from core.knowledge_base import cross_domain_search, export_context
from core.domain_detector import detect as detect_domain_auto
from core.learning_memory import register_pattern


# -- Carga de contexto KB --------------------------------------------------

def load_kb_context(domain: str = "", query: str = "") -> str:
    """
    Carga contexto relevante de la KB para inyectar en el system prompt.
    Combina: sesiones recientes + ultimo aprendizaje + patrones relevantes.
    """
    lines = []

    # Sesiones recientes (max 2)
    try:
        if SESSION_HISTORY_FILE.exists():
            hist   = json.loads(SESSION_HISTORY_FILE.read_text(encoding="utf-8"))
            recent = [s for s in hist[-3:] if s.get("metrics", {}).get("user_messages", 0) > 0]
            if recent:
                lines.append("=== SESIONES RECIENTES ===")
                for s in recent[-2:]:
                    summary = s.get("summary", "")
                    if summary and "sin mensajes" not in summary.lower():
                        lines.append(f"[{s.get('date','?')}] {summary[:200]}")
    except Exception:
        pass

    # Ultimo aprendizaje registrado
    try:
        if NOTIFY_FILE.exists():
            last = NOTIFY_FILE.read_text(encoding="utf-8").strip().splitlines()[-1]
            if last:
                lines.append(f"\n=== ULTIMO APRENDIZAJE ===\n{last}")
    except Exception:
        pass

    # Patrones KB relevantes al query (cross-domain)
    try:
        if query:
            results = cross_domain_search(text_query=query, limit=5)
            if results:
                lines.append("\n=== PATRONES RELEVANTES ===")
                for dom, hits in list(results.items())[:3]:
                    for h in hits[:2]:
                        sol = h.get("solution", {})
                        key = h.get("key", "?")
                        strat = sol.get("strategy", "")[:120]
                        notes = sol.get("notes", "")[:150]
                        lines.append(f"[{dom}] {key}: {strat}")
                        if notes:
                            lines.append(f"  {notes}")

        # Dominio especifico preconfigurado
        if domain:
            ctx = export_context(domain, limit=3)
            if ctx:
                lines.append(f"\n=== KB / {domain.upper()} ===")
                lines.append(ctx[:1500])
    except Exception:
        pass

    result = "\n".join(lines)
    return result[:MAX_KB_CHARS]


def detect_domain(text: str) -> str:
    """Detecta dominio del texto usando el domain_detector del Motor."""
    try:
        return detect_domain_auto(text)
    except Exception:
        return "general"


def save_to_kb(prompt: str, response: str, domain: str, model: str):
    """Registra la interaccion en learning_memory para enriquecer la KB."""
    try:
        register_pattern(
            domain=domain or "general",
            task_type="ollama_query",
            solution={
                "strategy":     "ollama_local_response",
                "code_snippet": "",
                "notes":        f"Q: {prompt[:200]} | A: {response[:300]}",
            },
            tags=["ollama", model.replace(":", "_"), domain or "general"],
        )
    except Exception:
        pass


# -- Modos de ejecucion ---------------------------------------------------

def run_interactive(adapter: OllamaAdapter, domain: str, use_kb: bool, stream: bool):
    """Loop REPL interactivo con historial de sesion."""
    print(f"\n  Motor_IA -- Ollama ({adapter.model})")
    print(f"  KB: {'activa' if use_kb else 'desactivada'} | "
          f"Dominio: {domain or 'auto-detectar'} | "
          f"stream: {'si' if stream else 'no'}")
    print("  Escribe tu consulta. Ctrl+C o 'exit' para salir.\n")

    history = []   # historial de la sesion actual (max 6 turnos)

    while True:
        try:
            user_input = input("  Tu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Hasta luego.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "salir", "quit"):
            print("  Hasta luego.")
            break

        active_domain = domain or detect_domain(user_input)

        # Construir lista de mensajes
        messages = []
        if use_kb:
            kb_ctx        = load_kb_context(domain=active_domain, query=user_input)
            system_prompt = adapter.build_system_prompt(kb_context=kb_ctx)
            messages.append({"role": "system", "content": system_prompt})

        messages.extend(history[-6:])
        messages.append({"role": "user", "content": user_input})

        # Llamar al modelo
        print(f"\n  [{adapter.model}] ", end="", flush=True)
        try:
            response = adapter.chat(messages, stream=stream)
            if not stream:
                print(response)
        except ConnectionError as e:
            print(f"\n  ERROR: {e}")
            continue
        except Exception as e:
            print(f"\n  ERROR inesperado: {e}")
            continue

        print()

        # Actualizar historial de sesion
        history.append({"role": "user",      "content": user_input})
        history.append({"role": "assistant", "content": response})

        # Guardar en KB para enriquecer futuras sesiones
        save_to_kb(user_input, response, active_domain, adapter.model)


def run_single_query(adapter: OllamaAdapter, query: str, domain: str,
                     use_kb: bool, stream: bool):
    """Modo no interactivo: una query, una respuesta, salir."""
    active_domain = domain or detect_domain(query)
    messages      = []

    if use_kb:
        kb_ctx        = load_kb_context(domain=active_domain, query=query)
        system_prompt = adapter.build_system_prompt(kb_context=kb_ctx)
        messages.append({"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": query})

    try:
        response = adapter.chat(messages, stream=stream)
        if not stream:
            print(response)
        save_to_kb(query, response, active_domain, adapter.model)
    except ConnectionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


# -- Entry point -----------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Chat con Ollama + Motor_IA KB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--model",       default=DEFAULT_MODEL,
                        help=f"Modelo Ollama a usar (default: {DEFAULT_MODEL})")
    parser.add_argument("--domain",      default="",
                        help="Dominio KB a precargar (ej: sow, bom, sap_tierra)")
    parser.add_argument("--query",       default="",
                        help="Consulta unica (modo no interactivo)")
    parser.add_argument("--no-kb",       action="store_true",
                        help="Deshabilitar inyeccion de KB")
    parser.add_argument("--no-stream",   action="store_true",
                        help="Respuesta completa al final (sin streaming)")
    parser.add_argument("--list-models", action="store_true",
                        help="Listar modelos disponibles en Ollama y salir")
    args = parser.parse_args()

    adapter = OllamaAdapter(model=args.model)

    # Solo listar modelos
    if args.list_models:
        models = adapter.list_models()
        if models:
            print("Modelos instalados en Ollama:")
            for m in models:
                marker = " <-" if args.model in m else ""
                print(f"  - {m}{marker}")
        else:
            print("Ollama no disponible o sin modelos instalados.")
            print("Instalar Ollama: https://ollama.com")
        return

    # Verificar que Ollama este corriendo y el modelo disponible
    if not adapter.is_available():
        models = adapter.list_models()
        if not models:
            print("ERROR: Ollama no esta corriendo.", file=sys.stderr)
            print("Ejecuta: ollama serve", file=sys.stderr)
        else:
            print(f"ERROR: Modelo '{args.model}' no encontrado.", file=sys.stderr)
            print(f"Modelos disponibles: {', '.join(models)}", file=sys.stderr)
            print(f"Instalar: ollama pull {args.model}", file=sys.stderr)
        sys.exit(1)

    use_kb = not args.no_kb
    stream = not args.no_stream

    if args.query:
        run_single_query(adapter, args.query, args.domain, use_kb, stream)
    else:
        run_interactive(adapter, args.domain, use_kb, stream)


if __name__ == "__main__":
    main()
