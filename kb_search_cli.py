#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kb_search_cli.py - Comando CLI para buscar en KB ANTES de preguntarme

USO:
  python C:\Hooks_IA\kb_search_cli.py "tu pregunta aqui"

EJEMPLO:
  python C:\Hooks_IA\kb_search_cli.py "¿Qué es un catálogo?"

Esto:
  1. Busca en Knowledge Base
  2. Calcula KB% + Internet% + ML%
  3. Muestra resultados CLARAMENTE
  4. Guarda en archivo para que Claude use
  5. Entonces TÚ me haces la pregunta
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Setup paths
sys.path.insert(0, str(Path(__file__).parent))

def main():
    if len(sys.argv) < 2:
        print("\n" + "="*70)
        print("MOTOR_IA KB SEARCH")
        print("="*70)
        print("\nUSO: python C:\\Hooks_IA\\kb_search_cli.py \"tu pregunta\"")
        print("\nEJEMPLO:")
        print("  python C:\\Hooks_IA\\kb_search_cli.py \"¿Qué es un catálogo?\"")
        print("\n" + "="*70 + "\n")
        return

    query = " ".join(sys.argv[1:])

    try:
        from core.kb_response_engine import process_query_with_kb

        print("\n" + "="*70)
        print("BUSCANDO EN KNOWLEDGE BASE...")
        print("="*70)
        print(f"\nQuery: {query}\n")

        result = process_query_with_kb(query)

        print("[RESULTADOS]")
        print(f"Dominio detectado: {result['domain']}")
        print(f"Entradas encontradas en KB: {result['kb_found']}")
        print("\n[PORCENTAJES REALES]")
        print(f"  KB:       {result['kb_pct']}%  (busqueda en Knowledge Base)")
        print(f"  Internet: {result['internet_pct']}%  (informacion complementaria)")
        print(f"  ML:       {result['ml_pct']}%  (conocimiento del modelo)")
        print("  " + "-"*20)
        print(f"  TOTAL:    {result['kb_pct'] + result['internet_pct'] + result['ml_pct']}%")

        print("\n[REPORTE OBLIGATORIO]")
        print(result['sources_footer'])

        if result['kb_pct'] == 0:
            print("\n[AUTO-SAVE]")
            print("KB%=0, así que cuando respondas esto se guardará automáticamente")
            print("en el Knowledge Base para la próxima vez.")

        # Guardar resultado para que Claude lo use en su respuesta
        result_file = Path(__file__).parent / "core" / "kb_search_result.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)

        saved_result = {
            "timestamp": datetime.now().isoformat(),
            "query": result['query'],
            "domain": result['domain'],
            "kb_pct": result['kb_pct'],
            "internet_pct": result['internet_pct'],
            "ml_pct": result['ml_pct'],
            "kb_found": result['kb_found'],
            "sources_footer": result['sources_footer']
        }

        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(saved_result, f, ensure_ascii=False, indent=2)

        print("\n[ARCHIVO GUARDADO]")
        print(f"Resultados guardados en: {result_file}")
        print("\nAHORA puedes hacerme la pregunta y usaré estos porcentajes")

        print("\n" + "="*70 + "\n")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
