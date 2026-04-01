# TEST PLAN - Motor_IA Sistema Completo
**Fecha:** 01-04-2026  
**Status:** LISTO PARA PRUEBA

---

## RESULTADO DEL SISTEMA DE VERIFICACION
```
Verificaciones pasadas: 6/6

[OK] SISTEMA MOTOR_IA LISTO
```

**Lo que está funcionando:**
- Config.py importa correctamente (rutas portables)
- Knowledge Base: 33 dominios configurados
- 3 Hooks instalados y registrados en settings.json
- Test de búsqueda real en KB: EJECUTADO EXITOSAMENTE
  
**Test de búsqueda real:**
```
Query: "Que es un catalogo?"
KB%: 0% (no hay entradas en KB para esta pregunta)
Internet%: 60%
ML%: 40%
Reporte generado: **Fuentes:** Internet 60% + ML 40%
```

---

## INSTRUCCIONES PARA PRUEBA COMPLETA

### PASO 1: Abre una NUEVA sesion CLI
```bash
# Desde la linea de comandos, inicia nueva sesion
claude
```

### PASO 2: Haz una pregunta de prueba
```
PREGUNTA: ¿Qué es un catálogo de productos?
```

**Que deberia pasar ANTES de mi respuesta:**
1. Hook `kb_enforcer_hook.py` se ejecuta automaticamente
2. Busca en `C:\Hooks_IA\knowledge\catalog\facts.json`
3. Imprime en CLI:
   ```
   ========================================
   *** MANDATORY KB ENFORCER REPORT ***
   ========================================
   Query: ¿Qué es un catálogo...
   Domain: catalog
   KB Entries Found: X
   
   REQUIRED IN YOUR RESPONSE:
   **Fuentes:** KB X% + Internet Y% + ML Z%
   ========================================
   ```

**Que deberia pasar DESPUES (mi respuesta):**
1. Incluye descripcion del catalogo
2. **OBLIGATORIO:** termina con:
   ```
   **Fuentes:** KB X% + Internet Y% + ML Z%
   ```
3. Hook `response_validator_hook.py` se ejecuta
4. Valida que las fuentes están presentes

### PASO 3: Verificar logs
```bash
# Ver ultimo registro del hook
cat C:\Hooks_IA\core\kb_enforcer.log | tail -3

# Deberia ver algo como:
# {"timestamp": "01-04-2026 14:35:22", "query": "¿Qué es un catálogo?", "kb_pct": 45, "auto_save": false}
```

### PASO 4: Verificar dashboard
```bash
# En navegador: http://localhost:8081/api/status
# Deberia ver en KB Enforcer Activity:
{
  "timestamp": "01-04-2026 14:35:22",
  "query": "¿Qué es un catálogo?",
  "kb_pct": 45,
  "domain": "catalog"
}
```

---

## TEST COMPLETO - 3 Preguntas de Prueba

### TEST 1: Pregunta con KB (Esperado: KB% > 0%)
```
Usuario: ¿Qué procesos tiene BPM para los pedidos?
Esperado: KB 40-50% + Internet 30% + ML 20-30%
Verificar: logs muestran KB% > 0%
```

### TEST 2: Pregunta SIN KB (Esperado: KB% = 0%, Auto-save activado)
```
Usuario: ¿Cuáles son los pasos para hacer una omeleta?
Esperado: KB 0% + Internet 70% + ML 30%
Auto-save: Query se guarda en knowledge/general/facts.json
Verificar: 
  - logs muestran KB 0%
  - knowledge/general/facts.json se actualizo
```

### TEST 3: Cross-Domain Query
```
Usuario: ¿Cuáles son las normas contables IFRS?
Esperado: Busca en contabilidad + business_rules
Esperado: KB 50-60% + Internet 20-30% + ML 10-20%
Verificar: logs muestran domain correcto
```

---

## CHECKLIST DE VERIFICACION

### Después de PREGUNTA 1:
- [ ] Viste el reporte MANDATORY KB ENFORCER en CLI?
- [ ] Mi respuesta incluye **Fuentes:** KB X% + Internet Y% + ML Z%?
- [ ] Los porcentajes suman 100%?
- [ ] cat C:\Hooks_IA\core\kb_enforcer.log existe y tiene datos?

### Después de PREGUNTA 2:
- [ ] KB% mostrado es 0%?
- [ ] Auto-save se ejecuto (verificar knowledge/general/facts.json)?
- [ ] Los porcentajes son diferentes a Pregunta 1?

### Después de PREGUNTA 3:
- [ ] Domain mostrado en logs es correcto?
- [ ] KB% es > 0% si el tema está en el KB?

### Dashboard (http://localhost:8081):
- [ ] KB Enforcer Activity se actualiza en tiempo real?
- [ ] Timestamps estan en formato DD-MM-YYYY HH:MM:SS?
- [ ] Query es visible en cada entrada?

---

## SI ALGO NO FUNCIONA

### Problema: No veo el reporte MANDATORY KB ENFORCER
**Solucion:**
```bash
# Verifica que el hook este registrado
cat "C:\Users\ntoledo\AppData\Local\ClaudeCode\.claude\settings.json" | grep -A5 "UserPromptSubmit"

# Deberia ver algo como:
# "UserPromptSubmit": [{"path": "C:\Hooks_IA\hooks\kb_enforcer_hook.py", ...}]

# Si no ve nada, necesitas reiniciar Claude Code completamente
```

### Problema: Las fuentes no están incluidas en respuesta
**Solucion:**
```bash
# Verifica el archivo de validacion
cat C:\Hooks_IA\core\RESPONSE_VALIDATION_ERROR.txt

# Esto te dirá que falta el reporte
```

### Problema: KB% es siempre 0%
**Solucion:**
```bash
# Verifica que los facts.json tengan datos
python -c "
import json
from pathlib import Path

kb_dir = Path('C:/Hooks_IA/knowledge')
for domain in kb_dir.iterdir():
    facts_file = domain / 'facts.json'
    if facts_file.exists():
        with open(facts_file) as f:
            data = json.load(f)
            count = len(data.get('facts', []))
            if count > 0:
                print(f'{domain.name}: {count} facts')
"
```

---

## PROXIMOS PASOS DESPUES DEL TEST

Si todo funciona:
1. Cierra sesion CLI (`/exit`)
2. Abre NUEVA sesion CLI (`claude`)
3. Haz la MISMA pregunta (ej: "¿Qué es un catálogo?")
4. Deberia ver KB% MAYOR porque aprendio de la sesion anterior

---

## CRONOGRAMA

- [x] Sistema de verificacion: COMPLETO
- [x] config.py con portabilidad: COMPLETO
- [x] Hooks instalados: COMPLETO
- [ ] TEST en nueva sesion CLI: PENDIENTE (usuario)
- [ ] Validar persistencia: PENDIENTE (usuario)
- [ ] Documentar problemas: PENDIENTE (usuario)

---

**Estatus Final:** Sistema Motor_IA esta LISTO para prueba completa.

Ejecuta: `python C:\Hooks_IA\verify_system.py` en cualquier momento para verificar estado del sistema.
