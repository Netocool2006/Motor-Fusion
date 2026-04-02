# Motor_IA + NotebookLM + CLI Claude - Implementación Completa

**Fecha:** 01-04-2026  
**Solución:** NotebookLM → Internet → ML (Flujo Lógico Óptimo)

---

## ARQUITECTURA

```
Pregunta en CLI Claude
        ↓
Hook kb_enforcer_hook_v2.py se ejecuta
        ↓
┌─────────────────────────────────────────┐
│ PASO 1: NotebookLM (KB Aprendido)       │
│ ¿Ya lo sabemos?                         │
└─────────────────────────────────────────┘
        ↓
   SI → KB% = 100% → Responder directo
   NO → Continuar
        ↓
┌─────────────────────────────────────────┐
│ PASO 2: Internet (WebSearch)            │
│ ¿Existe en la web?                      │
└─────────────────────────────────────────┘
        ↓
   SI → Internet% = 100% → Auto-guardar a NotebookLM
   NO → Continuar
        ↓
┌─────────────────────────────────────────┐
│ PASO 3: ML (Mi Conocimiento)            │
│ ¿Lo sé de mi entrenamiento?             │
└─────────────────────────────────────────┘
        ↓
   SI → ML% = 100% → Auto-guardar a NotebookLM
```

---

## INSTALACION (PASO A PASO)

### PASO 1: Configurar Google Cloud (TÚ)

```bash
1. Ir a: https://console.cloud.google.com/
2. Crear nuevo proyecto: "Motor_IA"
3. Habilitar APIs:
   - Google Drive API
   - Google Sheets API (para NotebookLM)
4. Crear OAuth 2.0 Client ID:
   - Tipo: "Aplicación de escritorio"
   - Descargar JSON
5. Guardar en: C:\Hooks_IA\.credentials\credentials.json
```

### PASO 2: Ejecutar autenticación

```bash
cd C:\Hooks_IA
python notebooklm_auth.py

# Esto:
# - Abre navegador
# - Te pide autorizar
# - Guarda token LOCALMENTE (.credentials/notebooklm_token.pickle)
# - Token NUNCA se comparte conmigo
```

### PASO 3: Crear NotebookLM Notebook (TÚ)

```
1. Ir a: https://notebooklm.google.com/
2. Crear notebook: "Motor_IA"
3. Subir documentos relevantes (opcional)
4. Copiar ID de la URL:
   https://notebooklm.google.com/notebook/[ID_AQUI]
5. Guardar ID en .env
```

### PASO 4: Crear archivo .env

```bash
# Copiar template
copy .env.template .env

# Editar y completar
NOTEBOOKLM_NOTEBOOK_ID=tu-id-aqui
```

### PASO 5: Actualizar settings.json

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:/Hooks_IA/hooks/kb_enforcer_hook_v2.py\""
          }
        ]
      }
    ]
  }
}
```

---

## FLUJO DE USO

### Sesión 1: Pregunta nueva

```
TÚ: "¿Cómo configurar Docker?"

Hook ejecuta:
  1. NotebookLM: ¿Existe? NO
  2. Internet: ¿Existe? SÍ (documentación Docker)
  3. YO: Respondo con documentación
  4. AUTO-GUARDAR: Se sube a NotebookLM

**Fuentes:** Internet 100% [Docker Documentation]
```

### Sesión 2: Pregunta similar

```
TÚ: "Ayudame con Docker"

Hook ejecuta:
  1. NotebookLM: ¿Existe? SÍ (del aprendizaje anterior)
  2. YO: Respondo de lo que aprendí
  3. NO BUSCO EN INTERNET (eficiencia)

**Fuentes:** KB 100% [Learned: 01-04-2026]
```

---

## SINCRONIZAR MANUALMENTE

Si quieres sincronizar todo el KB con NotebookLM:

```bash
cd C:\Hooks_IA
python notebooklm_uploader.py

# Convierte: knowledge/*/facts.json → Markdown
# Sube todo a NotebookLM automáticamente
```

---

## VERIFICACIÓN

### Verificar que funciona

```bash
# Ver último hook log
cat C:\Hooks_IA\core\kb_enforcer_v2.log | tail -20

# Debería mostrar:
# - Query encontrada
# - Fuente (KB, Internet, o ML)
# - Timestamp
# - Si auto-guardó
```

### Test en CLI

```bash
# Nueva sesión
claude

# Pregunta 1
¿Cuál es la capital de Francia?
→ Espera resultado del hook
→ Debería decir: **Fuentes:** KB/Internet/ML X%

# Pregunta 2
¿Cuál es la capital de Italia?
→ Hook consulta NotebookLM
→ Si ya lo sabe: KB% más alto
```

---

## ARCHIVOS PRINCIPALES

| Archivo | Propósito |
|---------|-----------|
| `notebooklm_auth.py` | Configuración OAuth2 (ejecutar UNA sola vez) |
| `hooks/kb_enforcer_hook_v2.py` | Hook principal (flujo completo) |
| `notebooklm_uploader.py` | Auto-sync con NotebookLM |
| `.env` | Configuración local (NUNCA compartir) |
| `.credentials/` | Tokens OAuth (NUNCA compartir) |
| `core/kb_enforcer_v2.log` | Logs de ejecución |

---

## CRITERIOS DE ÉXITO

✓ TEST 1: Pregunta nueva → Internet 100% → Auto-guarda  
✓ TEST 2: Pregunta similar → KB 100% → No busca  
✓ TEST 3: Pregunta ML pura → ML 100% → Auto-guarda  
✓ TEST 4: Todas tienen **Fuentes:**  
✓ TEST 5: NotebookLM crece con cada sesión  
✓ TEST 6: No hay búsquedas duplicadas  

---

## TROUBLESHOOTING

### "NOTEBOOKLM_NOTEBOOK_ID not found"
```
Solución: Crear .env con notebook ID
```

### "credentials.json not found"
```
Solución: Ejecutar python notebooklm_auth.py primero
```

### "Token expired"
```
Solución: Ejecutar python notebooklm_auth.py de nuevo
```

### Hook no se ejecuta
```
Solución: Verificar que está registrado en settings.json
         Reiniciar Claude CLI
```

---

## PROXIMOS PASOS

1. Ejecutar: `python notebooklm_auth.py`
2. Crear .env con NOTEBOOKLM_NOTEBOOK_ID
3. Actualizar settings.json
4. Abrir nueva sesión CLI
5. Hacer TEST 1-6

---

**Estado:** Listo para implementar

