#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kb_enforcer_hook.py - KB Enforcer Hook
Hook obligatorio - MANEJA AMBOS FORMATOS DE TRANSCRIPT
Se ejecuta ANTES de cada respuesta para buscar en KB.
Registrado en settings.json
No hardcoded paths - uses config.py for portability
"""

import sys
import json
from pathlib import Path
from datetime import datetime

def safe_kb_search():
    """
    Busca el último mensaje del usuario en el transcript.
    Maneja ambos formatos: simple y el de Claude Code.
    """
    try:
        # Importar configuración (sin paths quemados)
        hooks_dir = Path(__file__).parent
        project_root = hooks_dir.parent
        sys.path.insert(0, str(project_root))

        from config import CHANCE_PROJECT_DIR
        from core.kb_response_engine import process_query_with_kb

        # Buscar el archivo más reciente (usando config)
        transcript_dir = CHANCE_PROJECT_DIR
        if not transcript_dir.exists():
            return None

        transcript_files = list(transcript_dir.glob("*.jsonl"))
        if not transcript_files:
            return None

        transcript_file = max(transcript_files, key=lambda p: p.stat().st_mtime)

        # Leer el archivo y buscar el último mensaje del usuario
        query = None
        with open(transcript_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        # Buscar en las últimas 200 líneas (de atrás hacia adelante)
        for line in reversed(lines[-200:]):
            try:
                data = json.loads(line)

                # Formato 1: data.get('type') == 'user'
                if data.get('type') == 'user':
                    # Puede estar en data['content'] (formato simple)
                    content = data.get('content')
                    if content and isinstance(content, str):
                        query = content.strip()
                        if query:
                            break

                    # O puede estar en data['message']['content'] (formato Claude Code)
                    msg = data.get('message', {})
                    msg_content = msg.get('content', [])
                    if isinstance(msg_content, list):
                        for item in msg_content:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                query = item.get('text', '').strip()
                                if query:
                                    break

                    if query:
                        break

            except:
                continue

        if not query:
            return None

        # Procesar a través del motor KB
        result = process_query_with_kb(query)
        return result

    except Exception as e:
        return None


def main():
    """
    Hook principal.
    """
    try:
        result = safe_kb_search()

        if result:
            # Construcción del reporte OBLIGATORIO
            mandatory_footer = result['sources_footer']

            separator = "=" * 70
            print("\n" + separator)
            print("*** MANDATORY KB ENFORCER REPORT ***")
            print(separator)
            print(f"\nQuery: {result['query'][:60]}...")
            print(f"Domain: {result['domain']}")
            print(f"KB Entries Found: {result['kb_found']}")
            print(f"\n{separator}")
            print("REQUIRED IN YOUR RESPONSE:")
            print(separator)
            print(f"\n{mandatory_footer}")
            print(f"\n{separator}")
            print("Coverage Breakdown:")
            print(f"  KB:       {result['kb_pct']}%")
            print(f"  Internet: {result['internet_pct']}%")
            print(f"  ML:       {result['ml_pct']}%")
            print(f"  TOTAL:    100%")

            if result['should_save']:
                print(f"\n[AUTO-SAVE] Response will be saved to KB (KB=0%)")

            print(f"\n{separator}")
            print("INCLUDE THE ABOVE SOURCES IN YOUR RESPONSE")
            print(separator + "\n")

            # Log de ejecución
            try:
                log_file = Path(r"C:\Hooks_IA\core\kb_enforcer.log")
                log_file.parent.mkdir(parents=True, exist_ok=True)
                log_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "query": result['query'][:100],
                    "kb_pct": result['kb_pct'],
                    "auto_save": result['should_save']
                }
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            except:
                pass

            # Guardar reporte obligatorio en archivo
            try:
                report_file = Path(r"C:\Hooks_IA\core\MANDATORY_SOURCES_REPORT.txt")
                with open(report_file, "w", encoding="utf-8") as f:
                    f.write(result['sources_footer'] + "\n")
            except:
                pass

            # GUARDAR RESULTADO PARA QUE CLAUDE LEA EN RESPUESTA
            try:
                shared_result = Path(r"C:\Hooks_IA\core\kb_search_result.json")
                result_data = {
                    "timestamp": datetime.now().isoformat(),
                    "query": result['query'],
                    "domain": result['domain'],
                    "kb_pct": result['kb_pct'],
                    "internet_pct": result['internet_pct'],
                    "ml_pct": result['ml_pct'],
                    "sources_footer": result['sources_footer'],
                    "kb_found": result['kb_found']
                }
                with open(shared_result, "w", encoding="utf-8") as f:
                    f.write(json.dumps(result_data, ensure_ascii=False, indent=2))
            except:
                pass

    except:
        # Fallar silenciosamente para no quebrar el hook
        pass


if __name__ == "__main__":
    main()
