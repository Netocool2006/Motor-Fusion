# MOTOR_IA - Test Execution Steps
**Solución:** additionalContext en UserPromptSubmit Hook  
**Fecha Implementación:** 01-04-2026

---

## PREPARACION

### Verificar que todo esté en orden
```bash
python C:\Hooks_IA\verify_system.py
```

Debería pasar todos los 6 tests.

---

## FASE DE TESTING

### PASO 1: Abre NUEVA sesión CLI
```bash
claude
```

**Esto dispara el hook automáticamente en tu primer mensaje.**

---

### TEST 1: Pregunta Simple (KB Debe Tener Datos)

**Ejecutar:**
```
¿Qué es un catálogo de productos?
```

**Qué observar:**
1. ¿Ves el contexto inyectado en mi respuesta?
   - Debe incluir líneas como "[KB_SEARCH_EXECUTED]"
   - O debe mencionar KB%

2. ¿Mi respuesta incluye datos del catálogo?

3. ¿Termina con **Fuentes:** KB X% + Internet Y% + ML Z%?

**Verificación de éxito:**
- [ ] Respuesta menciona información de KB sobre catálogos
- [ ] Porcentajes suman 100%
- [ ] KB% > 0 (porque tiene datos)
- [ ] **Fuentes:** presente al final

---

### TEST 2: Pregunta Sin Datos en KB

**Ejecutar:**
```
¿Cuáles son los pasos para hacer un café con espresso?
```

**Qué observar:**
1. ¿Hook ejecutó? (KB% debe ser 0%)
2. ¿Mi respuesta viene de Internet/ML?
3. ¿Auto-save se activó?

**Verificación de éxito:**
- [ ] KB% = 0%
- [ ] Internet% > 0%, ML% > 0%
- [ ] **Fuentes:** KB 0% + Internet X% + ML Y%
- [ ] knowledge/general/facts.json se actualiza (verificar después)

**Verificar después:**
```bash
cat C:\Hooks_IA\knowledge\general\facts.json | tail -20
```

---

### TEST 3: Cross-Domain Search

**Ejecutar:**
```
¿Cuáles son las políticas contables en IFRS?
```

**Qué observar:**
1. Domain detectado: contabilidad o business_rules
2. KB% debería ser > 0 si hay datos relevantes

**Verificación de éxito:**
- [ ] Domain mostrado correcto
- [ ] KB% refleja búsqueda real
- [ ] Respuesta combina múltiples dominios si procede

---

### TEST 4: Validación de Reporte (5 Preguntas)

**Ejecutar 5 preguntas diferentes:**
```
1. ¿Qué es SAP?
2. ¿Cómo funciona BPM?
3. ¿Cuál es el proceso de pedidos?
4. ¿Qué significa ontología?
5. ¿Cómo se programa en Python?
```

**Verificación de éxito - TODAS deben cumplir:**
- [ ] Incluyen **Fuentes:** al final
- [ ] Formato: KB X% + Internet Y% + ML Z%
- [ ] X + Y + Z = 100% en cada una
- [ ] Los porcentajes son diferentes (búsquedas reales)

---

### TEST 5: Persistencia Entre Sesiones

**Sesión 1:**
```
Pregunta: "¿Qué es un catálogo?"
→ Auto-save ocurre (si KB% = 0%)
→ Cierra sesión: /exit
```

**Sesión 2 (nueva):**
```bash
claude
Pregunta: "Dime sobre catálogos otra vez"
```

**Verificación de éxito:**
- [ ] Sesión 2: KB% MAYOR que Sesión 1
- [ ] Respuesta mejora en precisión
- [ ] Sistema recuerda lo aprendido

---

### TEST 6: Verificar Dashboard

```bash
# En navegador:
http://localhost:8081
```

**Qué observar:**
1. KB Enforcer Activity actualiza
2. Muestra cada pregunta con timestamp
3. Formato: DD-MM-YYYY HH:MM:SS

**Verificación de éxito:**
- [ ] Dashboard muestra actividad en tiempo real
- [ ] Timestamps correctos (GMT-6)
- [ ] Query visible en panel
- [ ] KB% actualizado

---

### TEST 7: Verificar Logs

```bash
# Ver último log del hook
cat C:\Hooks_IA\core\kb_enforcer.log | tail -10
```

**Esperado:**
```json
{
  "timestamp": "2026-04-01T...",
  "query": "¿Qué es un catálogo?",
  "domain": "catalog",
  "kb_pct": 50,
  "internet_pct": 30,
  "ml_pct": 20,
  "kb_found": 5,
  "auto_save": false
}
```

**Verificación de éxito:**
- [ ] Logs muestran todas las búsquedas
- [ ] Porcentajes están registrados
- [ ] Timestamps correctos

---

## CHECKLIST FINAL

### Sistema Funcionando:
- [ ] TEST 1: Pregunta simple OK
- [ ] TEST 2: Auto-save ejecutado OK
- [ ] TEST 3: Cross-domain OK
- [ ] TEST 4: Reporte obligatorio (5x) OK
- [ ] TEST 5: Persistencia entre sesiones OK
- [ ] TEST 6: Dashboard actualiza OK
- [ ] TEST 7: Logs registran OK

### Criterios de Éxito Motor_IA:
- [ ] CADA respuesta tiene **Fuentes:** KB X% + Internet Y% + ML Z%
- [ ] Porcentajes son REALES (no fabricados)
- [ ] Búsqueda es SELECTIVA por tema
- [ ] Auto-save funciona (KB% = 0%)
- [ ] Persistencia entre sesiones
- [ ] Sin depender de voluntad (additionalContext forza)

---

## Si Algo Falla

### Problema: additionalContext no se ve
**Solución:**
```bash
# Verificar que hook retorna JSON válido
python C:\Hooks_IA\hooks\kb_enforcer_hook.py

# Debe retornar JSON, no error
```

### Problema: KB% siempre 0%
**Solución:**
```bash
# Verificar que KB tiene datos
python C:\Hooks_IA\kb_search_cli.py "¿Qué es un catálogo?"

# Debería mostrar KB% > 0 si hay datos
```

### Problema: Auto-save no ocurre
**Solución:**
```bash
# Verificar que save_to_kb() está siendo llamado
cat C:\Hooks_IA\core\kb_responses.log | tail -5
```

---

**SIGUIENTE:** Ejecuta los tests en orden. Reporta resultados.

