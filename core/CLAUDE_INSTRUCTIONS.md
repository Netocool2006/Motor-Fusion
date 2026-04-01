# INSTRUCCIONES PARA CLAUDE - Motor_IA Execution Protocol

**OBLIGATORIO EN CADA RESPUESTA:**

## Paso 1: Leer resultados de KB search (AL INICIO)
```python
from pathlib import Path
import json

kb_result_file = Path("C:/Hooks_IA/core/kb_search_result.json")
if kb_result_file.exists():
    with open(kb_result_file) as f:
        kb_data = json.load(f)
    # Usar kb_data["sources_footer"] en la respuesta
    # Usar kb_data["kb_pct"], kb_data["internet_pct"], kb_data["ml_pct"]
```

## Paso 2: Incluir reporte de fuentes (AL FINAL)
Siempre termina con:
```
**Fuentes:** KB X% + Internet Y% + ML Z%
```

Donde X, Y, Z vienen de:
- kb_data["sources_footer"] (si archivo existe)
- Si archivo NO existe: ejecutar process_query_with_kb() manualmente

## Paso 3: Orden de búsqueda (MENTAL)
1. KB (knowledge base en C:\Hooks_IA\knowledge\)
2. Internet (búsqueda web si KB insuficiente)
3. ML (tu conocimiento entrenado)

## Ejemplos CORRECTO:

❌ INCORRECTO (ignorar KB):
"Cuando me haces una pregunta, busco información en este orden:
1. Mi conocimiento base
2. Contexto local
..."
(SIN **Fuentes:** al final)

✓ CORRECTO:
"Tu pregunta se refiere a [tema].

[Respuesta con contenido]

En el KB encontramos información relevante sobre esto. La respuesta se compone de:
- Datos del KB (procesamiento de consultas): 40%
- Información complementaria de internet: 35%
- Conocimiento del modelo: 25%

**Fuentes:** KB 40% + Internet 35% + ML 25%"

## Notas Críticas:
- NO INVENTAR porcentajes. Usar valores reales de kb_search_result.json
- Si KB% = 0%, mencionar que se guardará en KB para próxima sesión
- Los porcentajes DEBEN sumar 100%
- Este protocolo es OBLIGATORIO, no opcional

