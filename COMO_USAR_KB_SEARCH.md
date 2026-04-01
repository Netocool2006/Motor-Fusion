# Comando KB-SEARCH - Buscar en Knowledge Base ANTES de preguntar

## ¿QUÉ ES?

Un comando que **TÚ ejecutas desde CMD** para buscar en el KB antes de hacerme una pregunta.

Esto te permite:
1. Ver exactamente qué encontró en el KB
2. Ver los porcentajes reales (KB% + Internet% + ML%)
3. Luego hacerme la pregunta sabiendo de dónde vendrá la respuesta

## ¿CÓMO USARLO?

### Opción 1: Comando directo (MÁS SIMPLE)
```cmd
cd C:\Hooks_IA
python kb_search_cli.py "tu pregunta aqui"
```

### Opción 2: Con el batch file
Si creaste C:\Hooks_IA\kb_search.bat, puedes:
```cmd
kb_search "tu pregunta aqui"
```

## EJEMPLOS

### Ejemplo 1: Buscar algo que ESTÁ en el KB
```cmd
python C:\Hooks_IA\kb_search_cli.py "¿Qué es un catálogo de productos?"
```

Resultado esperado:
```
[RESULTADOS]
Dominio detectado: catalog
Entradas encontradas en KB: 5

[PORCENTAJES REALES]
  KB:       50%
  Internet: 30%
  ML:       20%
  TOTAL:    100%

[REPORTE OBLIGATORIO]
**Fuentes:** KB 50% + Internet 30% + ML 20%

[ARCHIVO GUARDADO]
Resultados guardados en: C:\Hooks_IA\core\kb_search_result.json

AHORA puedes hacerme la pregunta y usaré estos porcentajes
```

### Ejemplo 2: Buscar algo que NO está en el KB
```cmd
python C:\Hooks_IA\kb_search_cli.py "¿Cómo se prepara un café?"
```

Resultado esperado:
```
[RESULTADOS]
Dominio detectado: general
Entradas encontradas en KB: 0

[PORCENTAJES REALES]
  KB:       0%
  Internet: 70%
  ML:       30%
  TOTAL:    100%

[AUTO-SAVE]
KB%=0, así que cuando respondas esto se guardará automáticamente
en el Knowledge Base para la próxima vez.

**Fuentes:** Internet 70% + ML 30%
```

## FLUJO COMPLETO

1. **TÚ ejecutas:**
   ```cmd
   python C:\Hooks_IA\kb_search_cli.py "¿Qué es un catálogo?"
   ```

2. **SISTEMA muestra:**
   ```
   [RESULTADOS]
   KB: 50%  Internet: 30%  ML: 20%
   **Fuentes:** KB 50% + Internet 30% + ML 20%
   
   [ARCHIVO GUARDADO]
   Resultados guardados en: C:\Hooks_IA\core\kb_search_result.json
   ```

3. **TÚ me preguntas:**
   ```
   ¿Qué es un catálogo de productos?
   ```

4. **YO respondo:**
   - Leo el archivo que creó tu búsqueda
   - Veo KB 50%, Internet 30%, ML 20%
   - Respondo priorizando KB
   - Termino con: **Fuentes:** KB 50% + Internet 30% + ML 20%

## ¿CÓMO VERIFICAS QUE FUNCIONA?

Después de ejecutar el comando, verifica que el archivo existe:
```cmd
type C:\Hooks_IA\core\kb_search_result.json
```

Deberías ver:
```json
{
  "timestamp": "2026-04-01T...",
  "query": "¿Qué es un catálogo de productos?",
  "domain": "catalog",
  "kb_pct": 50,
  "internet_pct": 30,
  "ml_pct": 20,
  "kb_found": 5,
  "sources_footer": "**Fuentes:** KB 50% + Internet 30% + ML 20%"
}
```

## VENTAJAS

✓ TÚ controlas cuándo se ejecuta la búsqueda
✓ TÚ ves los resultados ANTES de hacerme la pregunta
✓ TÚ sabes exactamente qué KB% tiene
✓ YO leo el archivo que TÚ creaste
✓ No depende de promesas o .md que yo pueda ignorar

## LIMITACIONES HONESTAS

- Si el comando falla, verás el error
- Si el KB está vacío, verás KB 0%
- Pero siempre verás la VERDAD, no ficción

---

**SIGUIENTE PASO:**

1. Ejecuta: `python C:\Hooks_IA\kb_search_cli.py "tu pregunta"`
2. VER resultados
3. Luego hazme la pregunta
4. YO respondo basándome en lo que buscaste
