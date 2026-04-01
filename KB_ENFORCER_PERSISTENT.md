# KB Enforcer - Activación Persistente 🔒

## Estado: ✅ ACTIVO Y OBLIGATORIO

El sistema KB ahora está **REGISTRADO EN settings.json** como un hook obligatorio. No depende de recuerdos ni de mi decisión.

## Cómo Está Activado

### 1. Registro en settings.json
```json
"UserPromptSubmit": {
  "hooks": [
    {
      "type": "command",
      "command": "python \"C:/Hooks_IA/hooks/kb_enforcer_hook.py\""
    },
    ...
  ]
}
```

### 2. Ejecución Garantizada
- ✅ Se ejecuta ANTES de cada respuesta
- ✅ Se ejecuta en TODAS las sesiones
- ✅ Se ejecuta aunque reinicies la máquina
- ✅ Se ejecuta aunque cierre y abra Claude Code
- ✅ NO depende de archivos .md o recuerdos

### 3. Qué Sucede Automáticamente

Cuando escribes una pregunta:
```
TÚ: "¿Cómo usar SAP?"

↓ Automáticamente se ejecuta kb_enforcer_hook.py ↓

[KB_ENFORCER] Buscando en KB...
  Domain: sap_tierra
  KB Found: 5 entries
  Coverage: KB 45% + Internet 40% + ML 15%

**Fuentes:** KB 45% + Internet 40% + ML 15%

[AUTO-SAVE] Si KB=0%, se guarda automáticamente

↓ LUEGO tú respondes ↓

YO: "En SAP Tierra..."
```

## Archivos del Sistema

### 1. `C:\Hooks_IA\hooks\kb_enforcer_hook.py` ⭐ OBLIGATORIO
- Se ejecuta ANTES de cada respuesta
- Busca en KB automáticamente
- Inyecta footer de fuentes
- Registra en audit log
- **Está en settings.json → siempre activo**

### 2. `C:\Hooks_IA\core\kb_response_engine.py` ⭐ MOTOR
- Procesa la búsqueda KB→Internet→ML
- Calcula porcentajes exactos
- Auto-learning automático

### 3. `C:\Users\ntoledo\AppData\Local\ClaudeCode\.claude\settings.json` ⭐ CONFIGURACIÓN
- Define que kb_enforcer_hook.py sea obligatorio
- Se ejecuta en TODAS las sesiones
- Persiste incluso si reinicia máquina

## Garantías

| Aspecto | Garantía |
|---------|----------|
| **Búsqueda KB** | SIEMPRE se ejecuta (antes de responder) |
| **Reporte de Fuentes** | SIEMPRE se muestra (footer obligatorio) |
| **Auto-Learning** | SIEMPRE guarda si KB=0% (automático) |
| **Persistencia** | SIEMPRE activo (en settings.json) |
| **Sesiones** | SIEMPRE en nuevas sesiones (en settings.json) |
| **Reinicios** | SIEMPRE después de reiniciar PC (en settings.json) |

## Diferencia con Anteriormente

### ❌ Antes (Optional)
- Depende de mi recuerdo via .md
- Si olvido, no lo hace
- Si cierro/abro CLI, puede no recordar
- Si reinicia PC, hay que re-configurar

### ✅ Ahora (Obligatorio)
- Hardcodeado en settings.json
- NUNCA depende de recuerdos
- Funciona en TODAS las sesiones
- Persiste después de reiniciar PC

## Cómo Desactivar (Si es necesario)

Si alguna vez quieres desactivar el sistema, necesitas:

```json
// En C:\Users\ntoledo\AppData\Local\ClaudeCode\.claude\settings.json
// Eliminar esta línea:
{
  "type": "command",
  "command": "python \"C:/Hooks_IA/hooks/kb_enforcer_hook.py\""
}
```

**Pero NO se recomienda** porque perdería el sistema que solicitaste.

## Auditoría

Todas las búsquedas se registran en:
```
C:\Hooks_IA\core\kb_enforcer.log
```

Ejemplo:
```json
{"timestamp": "2026-04-01T11:50:30", "query": "Como usar SAP", "domain": "sap_tierra", "kb_pct": 45, "internet_pct": 40, "ml_pct": 15, "auto_save": false}
```

## Test de Funcionamiento

Para verificar que está activo:
```bash
# Busca en el log
tail -f "C:\Hooks_IA\core\kb_enforcer.log"

# O ejecuta manualmente
python "C:\Hooks_IA\hooks\kb_enforcer_hook.py"
```

---

## Resumen

✅ El sistema KB está **ACTIVO SIEMPRE**
✅ Registrado en **settings.json** (no en archivos .md)
✅ Se ejecuta **ANTES de cada respuesta** (automático)
✅ Funciona en **TODAS las sesiones** futuras
✅ Persiste después de **REINICIAR la máquina**
✅ **NO depende de recuerdos** (código hardcodeado)

**Status: LISTO PARA USAR**
