# MOTOR_IA - Plan de Implementación Final
**Fecha:** 01-04-2026  
**Solución:** additionalContext en UserPromptSubmit Hook  
**Estado:** LISTO PARA IMPLEMENTACIÓN

---

## FASE 1: Actualizar kb_enforcer_hook.py

### Objetivo
Cambiar hook de escribir archivo → retornar JSON con additionalContext

### Cambios
```python
# En lugar de:
with open(report_file, "w") as f:
    f.write(result['sources_footer'])

# Retornar JSON con additionalContext:
json.dumps({
    "additionalContext": f"[KB_SEARCH_RESULT]\nQuery: {result['query']}\nKB%: {result['kb_pct']}\nInternet%: {result['internet_pct']}\nML%: {result['ml_pct']}\n[/KB_SEARCH_RESULT]"
})
```

### Flujo Resultante
```
Usuario: "¿Qué es un catálogo?"
   ↓
Hook UserPromptSubmit ejecuta
   ↓
Ejecuta: process_query_with_kb("catálogo")
   ↓
Retorna JSON con additionalContext
   ↓
CONTEXTO INYECTADO ANTES DE MI RESPUESTA
   ↓
YO genero respuesta viendo: KB 50%, Internet 30%, ML 20%
   ↓
Termino con: **Fuentes:** KB 50% + Internet 30% + ML 20%
```

---

## FASE 2: Test Plan Detallado

### TEST 1: Pregunta Simple (KB Disponible)
```
Precondición: KB tiene datos sobre catálogos (5+ entradas)

Ejecución:
  1. Abrir nueva sesión CLI (claude)
  2. Preguntar: "¿Qué es un catálogo de productos?"
  
Esperado:
  ✓ Hook se ejecuta
  ✓ additionalContext inyectado con KB%
  ✓ Mi respuesta incluye datos del KB priorizados
  ✓ Termina con: **Fuentes:** KB 50% + Internet 30% + ML 20%
  
Verificación:
  - Porcentajes suman 100%
  - KB% es > 0%
  - Respuesta menciona información de catálogos
```

### TEST 2: Pregunta Sin KB (Auto-save)
```
Precondición: KB no tiene datos sobre el tema

Ejecución:
  1. Preguntar: "¿Cómo se prepara un café?"
  
Esperado:
  ✓ Hook ejecuta búsqueda
  ✓ KB% = 0% inyectado
  ✓ Auto-save se dispara
  ✓ Termina con: **Fuentes:** Internet 70% + ML 30%
  
Verificación:
  - knowledge/general/facts.json se actualiza
  - Próxima búsqueda similar: KB% > 0%
```

### TEST 3: Persistencia Entre Sesiones
```
Ejecución:
  1. Sesión 1: Pregunta A → Auto-save ejecutado
  2. /exit (cerrar sesión)
  3. Sesión 2 (nueva): Pregunta similar a A
  
Esperado:
  ✓ Sesión 2: KB% MAYOR (encuentra lo guardado en Sesión 1)
  ✓ Respuesta mejora en precisión
  
Verificación:
  - Comparar KB% entre sesiones
  - Verificar knowledge/general/facts.json actualizado
```

### TEST 4: Cross-Domain Search
```
Ejecución:
  1. Preguntar: "¿Cuáles son las normas IFRS?"
  
Esperado:
  ✓ Hook detecta dominio: contabilidad + business_rules
  ✓ Busca en ambos dominios
  ✓ KB% refleja resultados reales
  
Verificación:
  - Domain mostrado correcto
  - KB% > 0% si datos disponibles
```

### TEST 5: Validación de Reporte Obligatorio
```
Ejecución:
  Hacer 5 preguntas diferentes

Esperado:
  ✓ TODAS incluyen **Fuentes:** al final
  ✓ Formato: KB X% + Internet Y% + ML Z%
  ✓ X + Y + Z = 100% siempre
  
Verificación:
  - Grep respuestas por "**Fuentes:**"
  - Validar suma de porcentajes
```

### TEST 6: Orden de Búsqueda (KB → Internet → ML)
```
Ejecución:
  Preguntar: "¿Qué es [tema en KB]?"

Esperado:
  ✓ Respuesta prioriza información del KB
  ✓ Complementa con Internet si necesario
  ✓ ML solo si falta cobertura
  
Verificación:
  - Contenido de respuesta prioriza KB
  - Estructura refleja KB → Internet → ML
```

### TEST 7: Dashboard Real-time
```
Ejecución:
  1. Abrir http://localhost:8081
  2. Hacer una pregunta en CLI
  
Esperado:
  ✓ KB Enforcer Activity se actualiza
  ✓ Muestra timestamp, query, KB%
  ✓ Formato: DD-MM-YYYY HH:MM:SS
  
Verificación:
  - Dashboard muestra datos nuevos
  - Timestamps correctos (GMT-6)
```

---

## FASE 3: Checklist Final

- [ ] kb_enforcer_hook.py actualizado (retorna additionalContext)
- [ ] Hooks registrados correctamente en settings.json
- [ ] TEST 1 PASSED: Pregunta con KB funciona
- [ ] TEST 2 PASSED: Auto-save ejecutado
- [ ] TEST 3 PASSED: Persistencia entre sesiones
- [ ] TEST 4 PASSED: Cross-domain search
- [ ] TEST 5 PASSED: Reporte obligatorio presente
- [ ] TEST 6 PASSED: Orden KB → Internet → ML
- [ ] TEST 7 PASSED: Dashboard actualiza en tiempo real
- [ ] Sistema Motor_IA 100% FUNCIONAL

---

## CRITERIOS DE ÉXITO

✓ **CADA respuesta** incluye **Fuentes:** KB X% + Internet Y% + ML Z%  
✓ **Porcentajes son REALES** (no fabricados)  
✓ **Búsqueda es SELECTIVA** por tema (no carga todo)  
✓ **Auto-save activado** cuando KB% = 0%  
✓ **Persistencia funciona** entre sesiones  
✓ **Sin depender de voluntad** — additionalContext forza la información en contexto

---

## NOTA IMPORTANTE

**Ya NO depende de:**
- Mi voluntad de buscar (está inyectado)
- Archivos que pueda ignorar (está en contexto)
- systemPrompt que pueda olvidar (está visible)

**Motor_IA será FUNCIONAL TÉCNICAMENTE**

