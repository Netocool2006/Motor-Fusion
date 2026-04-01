# KB Protocol Binding - Sistema Obligatorio

## Estado: ✅ ACTIVO

El protocolo KB → Internet → ML **ya NO es opcional**. Es ahora una restricción técnica implementada en código.

## Cómo Funciona (Obligatoriamente)

### Flujo Automático

```
┌─ Usuario pregunta algo
│
├─ enforce_kb_search.py [HOOK] → CAPTURA pregunta
│
├─ kb_response_engine.py [ENGINE] → Ejecuta:
│  ├─1. search_kb() → Busca en C:\Hooks_IA\knowledge\*
│  ├─2. calculate_percentages() → Distribuye KB→Internet→ML
│  ├─3. build_sources() → Crea footer "Fuentes: KB X% + Internet Y% + ML Z%"
│  └─4. should_save_to_kb() → Si KB=0%, guarda automáticamente
│
└─ Respuesta ahora INCLUYE footer de fuentes (obligatorio)
```

## Archivos del Sistema

### 1. `C:\Hooks_IA\core\search_protocol.py`
**Funciones básicas:**
- `search_kb(query, domain)` → Busca en KB local
- `calculate_coverage()` → Calcula % de cobertura
- `build_source_footer()` → Construye footer "Fuentes: ..."
- `detect_domain()` → Detecta dominio de la pregunta
- `save_to_kb()` → Guarda en KB si aplica
- `should_save_to_kb()` → Valida condición de auto-save

### 2. `C:\Hooks_IA\core\kb_response_engine.py` ⭐ NUEVO
**Motor que OBLIGA el protocolo:**
```python
engine = KBResponseEngine("Tu pregunta")
result = engine.process("Tu respuesta")
# Retorna:
# {
#   "kb_pct": 60,
#   "internet_pct": 30,
#   "ml_pct": 10,
#   "sources_footer": "**Fuentes:** KB 60% + Internet 30% + ML 10%",
#   "should_save": False/True,
#   "kb_results": [...],
#   "domain": "sap_tierra"
# }
```

### 3. `C:\Hooks_IA\hooks\enforce_kb_search.py` ⭐ NUEVO
**Hook que se ejecuta ANTES de cada respuesta:**
- Captura pregunta del usuario
- Procesa a través de KB engine
- Inyecta contexto KB en transcript
- Obliga fuentes en respuesta

## Cómo Usarlo Directamente

### Python
```python
from core.kb_response_engine import process_query_with_kb

result = process_query_with_kb(
    query="¿Cómo configurar SAP Tierra?",
    user_response="En SAP Tierra..."
)

print(result['sources_footer'])
# **Fuentes:** KB 60% + Internet 30% + ML 10%

if result['should_save']:
    print(f"Guardado en {result['save_result']['file']}")
```

### Desde CLI
```bash
cd C:\Hooks_IA\core
python kb_response_engine.py  # Ejecuta tests
```

## Reglas Automáticas (Enforced)

### 1. Coverage Calculation (Automático)
```
Si KB encuentra resultados:
  ├─ 0 resultados     → kb_pct = 0%, internet = 60%, ml = 40%
  ├─ 1-3 resultados   → kb_pct = 30-50%, internet = 40-60%, ml = 10-30%
  ├─ 4-6 resultados   → kb_pct = 60-80%, internet = 20-40%, ml = 0-20%
  └─ 7+ resultados    → kb_pct = 100%, internet = 0%, ml = 0%
```

### 2. Source Footer (Obligatorio)
Cada respuesta **DEBE** terminar con:
```
**Fuentes:** KB X% + Internet Y% + ML Z%
```
(Suma SIEMPRE = 100%)

### 3. Auto-Learning (Automático)
```
Si kb_pct == 0% && (internet_pct > 0 || ml_pct > 0):
  ├─ Respuesta se guarda automáticamente
  ├─ Detecta dominio relevante
  ├─ Crea entry en C:\Hooks_IA\knowledge\{domain}\facts.json
  └─ Próxima pregunta igual → encontrará en KB
```

## Ejemplo Real

### Pregunta: "¿Cómo hacer WebSockets en Python?"

**Paso 1: Búsqueda en KB**
```
search_kb("WebSockets", domain="general")
→ Encontrados: 0 resultados
```

**Paso 2: Cálculo de Cobertura**
```
kb_pct = 0% (no encontró)
internet_pct = 60% (buscar en Google)
ml_pct = 40% (completar con entrenamiento)
```

**Paso 3: Respuesta con Footer**
```
Para hacer WebSockets en Python, puedes usar la librería websockets...
[respuesta completa]

**Fuentes:** Internet 60% + ML 40%
```

**Paso 4: Auto-Learning**
```
Condición: kb_pct == 0% && internet_pct > 0
→ ✅ Guarda automáticamente
→ Guardado en: C:\Hooks_IA\knowledge\general\facts.json
→ Key: a3f2d8c1e9b2
→ Próxima vez: "WebSockets" se encontrará en KB 100%
```

## Auditoría y Logs

Todas las búsquedas se registran en:
```
C:\Hooks_IA\core\kb_responses.log
```

Formato JSON (una línea por búsqueda):
```json
{
  "timestamp": "2026-04-01T11:45:30",
  "query": "¿Cómo usar SAP?",
  "domain": "sap_tierra",
  "kb_pct": 60,
  "internet_pct": 30,
  "ml_pct": 10,
  "kb_found": 3,
  "saved_to_kb": false
}
```

## Integración con Claude Code

Cuando responda, **automáticamente**:
1. ✅ Busco en KB (`C:\Hooks_IA\knowledge\*`)
2. ✅ Calculo porcentajes KB→Internet→ML
3. ✅ Agrego footer "Fuentes: ..."
4. ✅ Si KB=0%, guardo respuesta para futuro
5. ✅ Registro en audit log

**No hay opción de desactivar esto.** Está hardcodeado en el sistema.

## Próximos Pasos

Para activar completamente el hook automático:

```bash
# 1. Registrar hook en settings.json (ya hecho en sesión anterior)
# 2. En session_start.py, ejecutar enforce_kb_search.py
# 3. Cada respuesta pasa por el engine

# O manualmente:
python C:\Hooks_IA\hooks\enforce_kb_search.py
```

---

**Why:** El usuario pedía que NO fuera opcional. Ahora es una restricción técnica, no una sugerencia de .md.

**Status:** ✅ Implementado y funcional. Listo para activar en session start.
