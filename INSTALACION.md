# Motor Fusion IA — Manual de Instalación

**Versión:** v1.0.1-fusion
**Fecha:** 2026-04-01
**Estado:** Production-Ready

Motor Fusion IA es un sistema completo de aprendizaje e integración con Claude Code CLI, con hardening de seguridad, MCP Server, y 3 hooks para aprendizaje automático.

## Requisitos

- **Windows 10/11** (64-bit) o **Linux/macOS** con Python 3.8+
- **Claude Code CLI** instalado y funcional
- **No requiere** instalación de Python del sistema (incluye Python 3.12 embebido en Windows)
- **No requiere** conexión a internet (instalador completamente offline)

---

## Instalación Rápida (Windows)

### 1. Descargar/Clonar
```bash
git clone https://github.com/Netocool2006/Motor-Fusion.git
cd Motor-Fusion
```

### 2. Ejecutar instalador
- **Opción A (Recomendado)**: Haz doble clic en **`install.bat`**
- **Opción B (Terminal)**:
  ```bash
  install.bat
  ```

### 3. Esperar a que termine
- La instalación toma ~10-15 segundos
- Se copiarán ~50MB a `%LOCALAPPDATA%\Motor_IA\`

### 4. Verificar en Claude Code
- Abre Claude Code CLI
- Los hooks y MCP Server se activarán automáticamente
- Reinicia Claude Code si es necesario

---

## Qué Hace el Instalador

| Paso | Acción | Ubicación |
|------|--------|-----------|
| 1 | Copia Motor_IA completo | `%LOCALAPPDATA%\Motor_IA\` |
| 2 | Instala Python 3.12 embebido | `Motor_IA\python_runtime\` |
| 3 | Crea directorios de datos | `%USERPROFILE%\.adaptive_cli\` |
| 4 | **Registra 3 hooks Claude Code** | `%USERPROFILE%\.claude\settings.json` |
| 5 | **Configura MCP Server** | `%USERPROFILE%\.claude\settings.json` |
| 6 | Verifica instalación | Genera `install_config.json` |

---

## Opciones de Línea de Comandos

```bat
REM Instalar en directorio personalizado
install.bat --dir "D:\MiMotor_IA"

REM Instalar sin registrar hooks (manual después)
install.bat --no-hooks

REM Ver ayuda
install.bat --help
```

---

## Hooks y MCP Server Configurados

Después de la instalación, tu `%USERPROFILE%\.claude\settings.json` tendrá:

### 3 Hooks Activos

1. **sessionStart** - Carga contexto KB al iniciar sesión
2. **postToolUse** - Aprende de resultados de herramientas ejecutadas
3. **userPromptSubmit** - Clasifica mensajes y sugiere patrones

### MCP Server

**motor-ia** - Servidor con 5 herramientas:
- `buscar_kb` - Buscar en knowledge base
- `guardar_aprendizaje` - Guardar patrones aprendidos
- `listar_patrones` - Listar patrones por dominio
- `registrar_error_resuelto` - Registrar errores solucionados
- `estadisticas` - Obtener estadísticas de KB

---

## Configuración Manual (Si Aplica)

Si instalaste con `--no-hooks` o necesitas configurar manualmente, edita `%USERPROFILE%\.claude\settings.json`:

```json
{
  "hooks": {
    "sessionStart": "python C:\\Users\\TU_USUARIO\\AppData\\Local\\Motor_IA\\hooks\\session_start.py",
    "postToolUse": "python C:\\Users\\TU_USUARIO\\AppData\\Local\\Motor_IA\\hooks\\post_tool_use.py",
    "userPromptSubmit": "python C:\\Users\\TU_USUARIO\\AppData\\Local\\Motor_IA\\hooks\\user_prompt_submit.py"
  },
  "mcpServers": {
    "motor-ia": {
      "command": "python",
      "args": ["C:\\Users\\TU_USUARIO\\AppData\\Local\\Motor_IA\\mcp_kb_server.py"]
    }
  }
}
```

**Reemplaza `TU_USUARIO`** con tu nombre de usuario de Windows.

---

## Verificar la Instalación

### Opción 1: Verificación Rápida

```bash
# Windows
%LOCALAPPDATA%\Motor_IA\python_runtime\python.exe -c "import sys; sys.path.insert(0, r'%LOCALAPPDATA%\Motor_IA'); from config import DATA_DIR; print('✓ Motor_IA OK'); print(f'  Datos: {DATA_DIR}')"

# Linux/macOS
python3 -c "from config import DATA_DIR; print('✓ Motor_IA OK'); print(f'  Datos: {DATA_DIR}')"
```

### Opción 2: Verificación Completa

Abre Claude Code CLI y ejecuta:
```
motor-ia: estadisticas
```

Debería mostrar:
- Total de dominios: 33+
- Total de entradas: 1100+
- Patrones aprendidos: 800+

### Opción 3: Revisar Configuración

```bash
# Ver settings.json actualizado
type %USERPROFILE%\.claude\settings.json
```

Verifica que incluya:
- ✅ `hooks` con 3 entradas
- ✅ `mcpServers` con `motor-ia`

---

## Documentación Incluida

El instalador incluye completa documentación en `%LOCALAPPDATA%\Motor_IA\`:

| Documento | Contenido |
|-----------|----------|
| **CLAUDE_CLI_INTEGRATION.md** | Guía completa de integración MCP + hooks (415 líneas) |
| **ENV_SETUP.md** | Configuración de variables de entorno |
| **TEST_PLAN.md** | Plan de pruebas detallado (22.5 KB) |
| **TEST_RESULTS.md** | Resultados: 100% test pass rate (13/13) |
| **CONSOLIDATION_SUMMARY.md** | Resumen de consolidación del sistema |
| **FINDINGS_REPORT.md** | Issues encontrados y soluciones |

---

## Estructura de Archivos Instalados

```
%LOCALAPPDATA%\Motor_IA\
  config.py                      — configuración central
  mcp_kb_server.py              — MCP server para Claude Code
  core\                          — módulos de memoria y aprendizaje
    knowledge_base.py           — base de conocimiento (FIXED v1.0.1)
    learning_memory.py          — sistema de aprendizaje
  hooks\                         — hooks para Claude Code (3 activos)
    session_start.py            — inyecta contexto al iniciar
    post_tool_use.py            — aprende de ejecuciones
    user_prompt_submit.py       — sugiere patrones
  adapters\                      — adaptadores para otros CLIs
  knowledge\                     — 33+ dominios de conocimiento
  python_runtime\               — Python 3.12 embebido
  [documentacion\]              — 6 archivos .md de referencia
  install_config.json           — registro de instalación

%USERPROFILE%\.adaptive_cli\
  knowledge\                     — base de conocimiento por dominio
    [33+ dominio_name]\         — patrones indexados por dominio
  learned_patterns.json         — patrones aprendidos (actualizado por hooks)
  hook_debug.log                — registro de ejecución de hooks
  hook_state\                   — estado compartido entre hooks
  locks\                        — control de concurrencia
```

---

## Desinstalacion

1. Elimina la carpeta `%LOCALAPPDATA%\Motor_IA\`
2. Elimina las entradas de hooks de `%USERPROFILE%\.claude\settings.json`
3. (Opcional) Elimina `%USERPROFILE%\.adaptive_cli\` para borrar todo el historial

---

## Soporte de CLIs

| CLI | Estado |
|-----|--------|
| Claude Code | Soportado — hooks nativos |
| Gemini CLI | Adaptador disponible (`adapters/gemini.py`) |
| Ollama | Adaptador disponible (`adapters/ollama.py`) |

---

## Solución de Problemas

### Los hooks no se activan
```bash
# Verifica que settings.json tenga hooks correctos
type %USERPROFILE%\.claude\settings.json

# Busca "hooks" y "mcpServers"
# Confirma que las rutas existen:
dir "%LOCALAPPDATA%\Motor_IA\python_runtime\python.exe"
dir "%LOCALAPPDATA%\Motor_IA\hooks\"
```

**Solución:**
- Reinicia Claude Code CLI completamente
- O ejecuta nuevamente: `install.bat`

### Error "Motor_IA no encontrado"
```bash
# Verifica la instalación
dir "%LOCALAPPDATA%\Motor_IA\core\knowledge_base.py"
```

**Solución:**
- Ejecuta `install.bat` como administrador
- O especifica directorio: `install.bat --dir "D:\Motor_IA"`

### MCP Server no responde
```bash
# Revisa el log de hooks
type "%USERPROFILE%\.adaptive_cli\hook_debug.log"
```

**Solución:**
- Verifica que `mcp_kb_server.py` existe
- Reinicia Claude Code CLI
- Consulta CLAUDE_CLI_INTEGRATION.md para troubleshooting

### Motor_IA no aprende entre sesiones
```bash
# Verifica permisos en directorio de datos
dir "%USERPROFILE%\.adaptive_cli\"
```

**Solución:**
- Asegúrate de que el directorio existe: `mkdir %USERPROFILE%\.adaptive_cli\`
- Verifica permisos de escritura en la carpeta
- Revisa `hook_debug.log` para errores

---

## Desinstalación

Para remover completamente:

```bash
# 1. Eliminar instalación
rmdir /s /q "%LOCALAPPDATA%\Motor_IA"

# 2. Editar %USERPROFILE%\.claude\settings.json
#    y remover "hooks" y "mcpServers"

# 3. (Opcional) Eliminar historial de aprendizaje
rmdir /s /q "%USERPROFILE%\.adaptive_cli"
```

---

## Próximos Pasos

Después de instalar:

1. **Reinicia Claude Code CLI** para que cargue los hooks
2. **Lee CLAUDE_CLI_INTEGRATION.md** para entender cómo funciona
3. **Ejecuta una búsqueda de prueba** en Claude Code:
   ```
   motor-ia: estadisticas
   ```
4. **Revisa hook_debug.log** después de usar Claude Code:
   ```
   type %USERPROFILE%\.adaptive_cli\hook_debug.log
   ```

---

## Información Adicional

- **Repositorio**: https://github.com/Netocool2006/Motor-Fusion
- **Versión**: v1.0.1-fusion (2026-04-01)
- **Documentación completa**: CLAUDE_CLI_INTEGRATION.md
- **Test Results**: TEST_RESULTS.md (100% pass rate)

---

## Soporte

Si encuentras problemas:

1. Consulta los 6 archivos .md incluidos en la instalación
2. Revisa `hook_debug.log` para diagnosticar
3. Verifica que Claude Code CLI está actualizado
4. Abre un issue en GitHub si el problema persiste
