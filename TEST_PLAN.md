# TEST PLAN - Motor_IA Sistema Completo
**Fecha:** 2026-04-01  
**Objetivo:** Validar que el sistema Motor_IA ejecuta búsquedas reales en KB, calcula porcentajes correctos e incluye reporte de fuentes obligatorio.

---

## PREREQUISITOS
- [ ] CLI iniciado con `claude`
- [ ] Dashboard en navegador: `http://localhost:8081`
- [ ] Directorio C:\Hooks_IA existe con estructura completa
- [ ] config.py sin paths quemados ✓
- [ ] Hooks registrados en settings.json ✓

---

## TEST 1: Pregunta Simple (Dominio Conocido)

**Comando del usuario:**
```
¿Qué es un catálogo de productos?
```

**Resultado esperado:**
1. Hook kb_enforcer_hook.py se ejecuta ANTES de responder
2. Busca en knowledge/catalog/facts.json
3. Encuentra 3-5 entradas relevantes
4. Calcula: KB 50% + Internet 30% + ML 20%
5. Mi respuesta incluye **Fuentes:** KB 50% + Internet 30% + ML 20%
6. kb_enforcer.log se actualiza con timestamp, query, KB%

**Verificación:**
```bash
cat C:\Hooks_IA\core\kb_enforcer.log | tail -5
```

---

## TEST 2: Pregunta Sin Datos en KB (KB=0%)

**Comando del usuario:**
```
¿Cómo se prepara un café perfecto?
```

**Resultado esperado:**
1. Hook busca en todos los dominios
2. NO encuentra coincidencias (KB 0%)
3. Calcula: KB 0% + Internet 70% + ML 30%
4. Auto-save se ejecuta: guarda query + respuesta a knowledge/general/facts.json
5. Mi respuesta incluye **Fuentes:** KB 0% + Internet 70% + ML 30%
6. response_validation.log registra validación
7. Siguiente sesión: pregunta similar encuentra KB 100%

**Verificación:**
```bash
grep "KB 0%" C:\Hooks_IA\core\kb_enforcer.log
cat C:\Hooks_IA\knowledge\general\facts.json | tail -10
```

---

## TEST 3: Búsqueda Cross-Domain

**Comando del usuario:**
```
¿Qué políticas contables tenemos?
```

**Resultado esperado:**
1. Hook detecta dominio "contabilidad" OR "business_rules"
2. Busca en ambos dominios
3. Encuentra 2-4 entradas
4. Calcula porcentajes reales
5. Reporte incluido en respuesta

**Verificación en Dashboard:**
- [ ] KB Enforcer Activity muestra timestamp DD-MM-YYYY HH:MM:SS
- [ ] Query visible en panel
- [ ] KB% actualizado en tiempo real

---

## TEST 4: Validación de Reporte Obligatorio

**Verificación manual de respuesta:**
```
✓ ¿Incluye **Fuentes:** al final?
✓ ¿Formato es: KB X% + Internet Y% + ML Z%?
✓ ¿X + Y + Z = 100%?
✓ ¿Los porcentajes son reales (no fabricados)?
```

**Si falta reporte:**
- response_validator_hook.py debe escribir error en RESPONSE_VALIDATION_ERROR.txt

---

## TEST 5: Persistencia Entre Sesiones

**Procedimiento:**
1. Pregunta 1: "¿Cuál es el catálogo principal?" (KB busca)
2. `/exit` para cerrar sesión
3. `claude` para nueva sesión
4. Pregunta 2: "Repite lo que dijiste del catálogo" 
   - DEBE buscar primero en KB (no olvidar)
   - DEBE incluir **Fuentes:** 
   - DEBE ser consistente con sesión anterior

---

## TEST 6: Verificación de Logs

### kb_enforcer.log
```json
{
  "timestamp": "2026-04-01T14:35:22.123456",
  "query": "¿Qué es un catálogo?",
  "kb_pct": 50,
  "auto_save": false
}
```

### response_validation.log
```json
{
  "timestamp": "2026-04-01T14:35:30.456789",
  "response_length": 1250,
  "has_sources_report": true,
  "status": "VALID"
}
```

---

## TEST 7: Dashboard Verification

**En navegador:**
```
GET http://localhost:8081/api/status
```

**Respuesta esperada:**
```json
{
  "kb_enforcer_activity": [
    {
      "timestamp": "01-04-2026 14:35:22",
      "query": "¿Qué es un catálogo?",
      "kb_pct": 50,
      "domain": "catalog"
    }
  ],
  "knowledge_base": {
    "catalog": 45,
    "contabilidad": 28,
    "general": 12
  }
}
```

---

## CHECKLIST FINAL

- [ ] TEST 1 PASSED: Pregunta simple busca en KB correctamente
- [ ] TEST 2 PASSED: Auto-save activado cuando KB=0%
- [ ] TEST 3 PASSED: Cross-domain search funciona
- [ ] TEST 4 PASSED: Reporte **Fuentes:** siempre incluido
- [ ] TEST 5 PASSED: Sistema persiste entre sesiones
- [ ] TEST 6 PASSED: Logs actualizados con datos reales
- [ ] TEST 7 PASSED: Dashboard muestra actividad en tiempo real
- [ ] REPORTE FINAL: Sistema Motor_IA 100% funcional

---

## NOTAS CRÍTICAS

1. **KB Search REAL:** No es fabricado - ejecuta process_query_with_kb() cada vez
2. **Porcentajes REALES:** Basados en búsqueda actual, no estimados
3. **Persistencia:** Hooks en settings.json hacen que funcione en nueva sesión
4. **Timestamps:** DD-MM-YYYY HH:MM:SS en dashboard (GMT-6)
5. **Portabilidad:** Config.py usa variables de entorno - no hardcoded paths
