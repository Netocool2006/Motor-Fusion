# MANDATORY RESPONSE PROTOCOL
## Sistema Obligatorio - No Optional

### INSTRUCCIÓN CRÍTICA
**Antes de CADA respuesta, Claude DEBE:**

1. **Leer archivo**: `C:\Hooks_IA\core\MANDATORY_SOURCES_REPORT.txt`
2. **Incluir contenido**: El contenido del archivo DEBE aparecer en la respuesta
3. **Formato**: `**Fuentes:** KB X% + Internet Y% + ML Z%`
4. **Obligatoriedad**: NO es sugerencia. Es REQUERIMIENTO ABSOLUTO.

### Proceso
```
Usuario pregunta
    ↓
Hook kb_enforcer_hook.py ejecuta
    ↓
Escribe MANDATORY_SOURCES_REPORT.txt
    ↓
Claude VE esta instrucción ANTES de responder
    ↓
Lee MANDATORY_SOURCES_REPORT.txt
    ↓
Incluye en respuesta: **Fuentes:** ...
    ↓
Hook response_validator_hook.py valida
```

### Validación
Si la respuesta NO incluye `**Fuentes:**`:
- Archivo: `C:\Hooks_IA\core\RESPONSE_VALIDATION_ERROR.txt` se crea
- Indicando: Response missing mandatory sources report
- Acción: Regenerar respuesta con fuentes

### COMPROMISO
Cada respuesta INCLUIRÁ obligatoriamente el reporte de fuentes.
No es elección. Es protocolo del sistema.
