#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kb_executor.py - Ejecuta búsqueda en KB y retorna resultados para Claude
Se ejecuta ANTES de cada respuesta de Claude
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def get_kb_result():
    """
    Lee el archivo de resultado KB que escribió el hook.
    Si no existe, ejecuta búsqueda y retorna resultados.
    """
    result_file = Path(__file__).parent / "kb_search_result.json"

    # Si el hook ya ejecutó y guardó resultado
    if result_file.exists():
        try:
            with open(result_file, encoding='utf-8') as f:
                data = json.load(f)
            return data
        except:
            pass

    # Si no existe, no hay búsqueda previa
    return None


if __name__ == "__main__":
    result = get_kb_result()
    if result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"error": "No KB result available"}, ensure_ascii=False))
