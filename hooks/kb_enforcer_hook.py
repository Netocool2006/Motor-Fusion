#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kb_enforcer_hook.py - Hook que ejecuta búsqueda en KB
Se ejecuta ANTES de cada respuesta - escribe resultado a archivo
"""

import sys
import json
from pathlib import Path
from datetime import datetime

def safe_kb_search():
    """
    Busca el último mensaje del usuario y ejecuta búsqueda en KB
    """
    try:
        hooks_dir = Path(__file__).parent
        project_root = hooks_dir.parent
        sys.path.insert(0, str(project_root))

        from config import CHANCE_PROJECT_DIR
        from core.kb_response_engine import process_query_with_kb

        transcript_dir = CHANCE_PROJECT_DIR
        if not transcript_dir.exists():
            return None

        transcript_files = list(transcript_dir.glob("*.jsonl"))
        if not transcript_files:
            return None

        transcript_file = max(transcript_files, key=lambda p: p.stat().st_mtime)

        query = None
        with open(transcript_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        for line in reversed(lines[-200:]):
            try:
                data = json.loads(line)

                if data.get('type') == 'user':
                    content = data.get('content')
                    if content and isinstance(content, str):
                        query = content.strip()
                        if query:
                            break

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
    Hook principal - escribe resultado a archivo compartido
    """
    try:
        result = safe_kb_search()

        if result:
            # GUARDAR RESULTADO EN ARCHIVO PARA QUE CLAUDE LEA
            result_file = Path(r"C:\Hooks_IA\core\kb_search_result.json")
            result_file.parent.mkdir(parents=True, exist_ok=True)

            result_data = {
                "timestamp": datetime.now().isoformat(),
                "query": result['query'],
                "domain": result['domain'],
                "kb_pct": result['kb_pct'],
                "internet_pct": result['internet_pct'],
                "ml_pct": result['ml_pct'],
                "kb_found": result['kb_found'],
                "sources_footer": result['sources_footer'],
                "should_save": result['should_save']
            }

            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)

            # GUARDAR LOGS PARA VERIFICACION
            try:
                log_file = Path(r"C:\Hooks_IA\core\kb_enforcer.log")
                log_file.parent.mkdir(parents=True, exist_ok=True)
                log_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "query": result['query'][:100],
                    "domain": result['domain'],
                    "kb_pct": result['kb_pct'],
                    "internet_pct": result['internet_pct'],
                    "ml_pct": result['ml_pct'],
                    "kb_found": result['kb_found'],
                    "auto_save": result['should_save']
                }
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            except:
                pass

    except:
        # Fallar silenciosamente para no quebrar el hook
        pass


if __name__ == "__main__":
    main()
