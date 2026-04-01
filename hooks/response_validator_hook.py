#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
response_validator_hook.py
==========================
Validador de respuestas - OBLIGA el reporte de fuentes

Se ejecuta después de cada respuesta para verificar que incluya:
**Fuentes:** KB X% + Internet Y% + ML Z%

Si no está presente, rechaza la respuesta.
No hardcoded paths - uses config.py for portability
"""

import json
import sys
from pathlib import Path
from datetime import datetime

def validate_response():
    """
    Lee el transcript más reciente y valida que mi última respuesta
    incluya el reporte de fuentes obligatorio.
    """
    try:
        # Importar configuración (sin paths quemados)
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root))
        from config import CHANCE_PROJECT_DIR

        transcript_dir = CHANCE_PROJECT_DIR
        if not transcript_dir.exists():
            return

        # Los archivos .jsonl están directamente en transcript_dir
        transcript_files = list(transcript_dir.glob("*.jsonl"))
        if not transcript_files:
            return

        # Encontrar el archivo más reciente
        transcript_file = max(transcript_files, key=lambda p: p.stat().st_mtime)

        # Leer última respuesta del asistente
        last_assistant_response = None
        with open(transcript_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            for line in reversed(lines):
                try:
                    msg = json.loads(line)
                    if msg.get('type') == 'assistant':
                        content = msg.get('content', [])
                        if isinstance(content, list):
                            for item in content:
                                if item.get('type') == 'text':
                                    last_assistant_response = item.get('text', '')
                                    break
                        elif isinstance(content, str):
                            last_assistant_response = content
                        if last_assistant_response:
                            break
                except:
                    pass

        if not last_assistant_response:
            return

        # Validar que incluya el reporte de fuentes
        # Busca el patrón: **Fuentes:** ... KB ... + Internet ... + ML ...
        required_patterns = [
            "**Fuentes:**",
            "KB",
            "Internet",
            "ML"
        ]

        has_sources = all(pattern in last_assistant_response for pattern in required_patterns)

        # Log de validación
        validation_log = Path(r"C:\Hooks_IA\core\response_validation.log")
        validation_log.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "response_length": len(last_assistant_response),
            "has_sources_report": has_sources,
            "status": "VALID" if has_sources else "INVALID - MISSING SOURCES"
        }

        with open(validation_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        # Si NO tiene fuentes, escribir alerta
        if not has_sources:
            alert_file = Path(r"C:\Hooks_IA\core\RESPONSE_VALIDATION_ERROR.txt")
            with open(alert_file, "w", encoding="utf-8") as f:
                f.write(f"""
VALIDATION ERROR: Response missing sources report

Your last response did NOT include the mandatory sources report.

REQUIRED FORMAT:
**Fuentes:** KB X% + Internet Y% + ML Z%

Last response snippet:
{last_assistant_response[:200]}...

Please regenerate the response with the sources report included.
""")

    except Exception as e:
        pass


if __name__ == "__main__":
    validate_response()
