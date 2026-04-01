# Sistema Motor-IA: Persistencia y Auto-arranque

**Fecha de creación:** 2026-04-01  
**Estado:** ✅ COMPLETAMENTE PERSISTENTE

---

## ¿Qué está GUARDADO y será AUTOMÁTICO en la próxima sesión?

### 1. ✅ DASHBOARD EN TIEMPO REAL
**Ubicación:** `C:\Hooks_IA\dashboard\`
- `server.py` — Servidor modificado con SSE (Server-Sent Events)
- `index.html` — UI conectada a stream en tiempo real

**Comportamiento automático:**
- Se inicia automáticamente al abrir sesión (hook session_start.py)
- Escucha en `http://localhost:7070`
- Se actualiza cada 500ms mientras escribes
- Muestra: Motor ACTIVO, Hooks REGISTRADOS, KB stats, iteración actual

### 2. ✅ PROTOCOLO DE BÚSQUEDA INTELIGENTE
**Ubicación:** `C:\Hooks_IA\core\search_protocol.py`

**Funciones:**
- `search_kb()` — Busca en knowledge base local
- `calculate_coverage()` — Calcula % de cobertura KB
- `save_to_kb()` — Guarda nuevas respuestas en KB
- `detect_domain()` — Detecta dominio automáticamente
- `should_save_to_kb()` — Decide si guardar

**Flujo automático:**
```
Tu pregunta
  ↓ [En mis respuestas]
  → Busco en KB
  → Si KB < 100%: complemento con Internet/ML
  → Si KB = 0%: automáticamente guardo en KB
  ↓
Respuesta con "Fuentes: KB X% + Internet Y% + ML Z%"
```

### 3. ✅ AUTO-LEARNING (Guardar nuevas respuestas)
**Ubicación:** `C:\Hooks_IA\hooks\kb_search_integration.py`

**Flujo automático (al cerrar sesión):**
1. Extrae tu pregunta + mi respuesta del transcript
2. Busca en KB
3. Si no encontró nada (KB = 0%):
   - Detecta el dominio
   - Guarda en `C:\Hooks_IA\knowledge\[dominio]\facts.json`
   - Clave: hash del contenido
   - Metadata: timestamp, fuente="auto_learned"

**Resultado:** Próxima pregunta igual → ya estará en KB al 100%

### 4. ✅ HOOKS REGISTRADOS EN settings.json
**Ubicación:** `C:\Users\ntoledo\AppData\Local\ClaudeCode\.claude\settings.json`

**Hooks configurados:**
```json
{
  "UserPromptSubmit": [
    "session_start.py",      // Carga contexto
    "user_prompt_submit.py"  // Procesa prompt
  ],
  "PostToolUse": [
    "post_tool_use.py"       // Después de cada tool
  ],
  "Stop": [
    "session_end.py",               // Guarda sesión
    "kb_search_integration.py"      // AUTO-LEARNING: guarda en KB
  ]
}
```

**Comportamiento automático:**
- `session_start.py` → Arranca dashboard + carga contexto
- `kb_search_integration.py` → Guarda respuestas nuevas en KB

### 5. ✅ MEMORIA Y REGLAS
**Ubicación:** `C:\Users\ntoledo\AppData\Local\ClaudeCode\.claude\projects\C--Chance1\memory\`

- `feedback_kb_search_protocol.md` — Reglas de búsqueda
- `MEMORY.md` — Índice de memoria

**Comportamiento automático:**
- Se cargan en cada sesión como reminder
- Yo aplico las reglas automáticamente

### 6. ✅ KNOWLEDGE BASE CON AUTO-LEARNED
**Ubicación:** `C:\Hooks_IA\knowledge\`

Ejemplo:
```
C:\Hooks_IA\knowledge\general\facts.json
  ├─ entry_943d19ef60a2
  │   ├─ query: "¿Cómo hacer WebSockets en Python sin librerías externas?"
  │   ├─ answer: "Para WebSockets sin librerías..."
  │   ├─ timestamp: "2026-04-01T10:26:25.032829"
  │   └─ source: "auto_learned"
```

**Crece automáticamente:** Cada vez que respondo algo nuevo (KB=0%), se guarda.

---

## Checklist: ¿Funcionará igual en la próxima sesión?

| Item | Guardado? | Auto-inicio? | Funciona en próxima sesión? |
|------|-----------|--------------|------------------------------|
| Dashboard servidor | ✅ | ✅ | ✅ Sí, inicia automáticamente |
| Protocolo búsqueda KB | ✅ | ✅ | ✅ Sí, integrado en hooks |
| Auto-learning KB | ✅ | ✅ | ✅ Sí, hook Stop guarda |
| Reglas/Memoria | ✅ | ✅ | ✅ Sí, en reminder |
| Hooks registrados | ✅ | ✅ | ✅ Sí, settings.json |

---

## Flujo completo en próxima sesión:

```
1. Abres Claude CLI nueva sesión
   ↓
2. Hook "session_start.py" se ejecuta:
   ├─ Arranca dashboard (puerto 7070)
   ├─ Carga contexto + memoria
   └─ Inyecta reminder con reglas
   ↓
3. Yo veo el reminder:
   ├─ Leo feedback_kb_search_protocol.md
   ├─ Sé que debo buscar KB → Internet → ML
   └─ Sé que debo reportar fuentes
   ↓
4. Respondes una pregunta:
   ├─ Busco en KB automáticamente
   ├─ Complemento con Internet/ML si falta
   ├─ Guardo en KB si KB=0%
   └─ Respondo con "Fuentes: KB X% + Internet Y% + ML Z%"
   ↓
5. Cierras sesión:
   ├─ Hook "kb_search_integration.py" extrae pregunta+respuesta
   ├─ Guarda automáticamente en `knowledge\[dominio]\facts.json`
   └─ Próxima pregunta igual → ya estará en KB
```

---

## ¿Qué NO es persistente? (requiere acciones manuales)

- Dashboard browser: No se abre automáticamente (debes navegar a `http://localhost:7070`)
- Búsqueda manual con CLI: Debes usar `python core/knowledge_base.py export --query "..."`

---

## Verificación rápida en próxima sesión:

```bash
# Verificar que está todo en lugar
ls -la C:\Hooks_IA\core\search_protocol.py
ls -la C:\Hooks_IA\hooks\kb_search_integration.py
ls -la C:\Hooks_IA\dashboard\server.py
ls -la C:\Users\ntoledo\AppData\Local\ClaudeCode\.claude\projects\C--Chance1\memory\MEMORY.md

# Verificar dashboard corriendo
curl http://localhost:7070/api/status

# Verificar KB aprendida
cat C:\Hooks_IA\knowledge\general\facts.json
```

---

## Resumen:
✅ **TODO está guardado y será automático en la próxima sesión.**
- Dashboard se inicia solo
- Protocolo de búsqueda se aplica automáticamente
- KB crece sola con auto-learning
- Memoria y reglas se cargan en el reminder
- Próxima pregunta igual → ya estará en KB
