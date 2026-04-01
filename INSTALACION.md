# Motor Fusion IA — Guia de Instalacion

## Requisitos

- Windows 10 / 11 (64-bit)
- Claude Code CLI instalado
- **No requiere Python ni conexion a internet**

---

## Instalacion rapida

1. Descarga o clona el repositorio en la PC destino
2. Haz doble clic en **`install.bat`**
3. Espera ~10 segundos mientras se instala
4. Abre Claude Code — los hooks se activan automaticamente

---

## Que hace el instalador

| Paso | Accion |
|------|--------|
| 1 | Copia Motor_IA a `%LOCALAPPDATA%\Motor_IA\` |
| 2 | Instala Python 3.12 embebido en `Motor_IA\python_runtime\` |
| 3 | Crea `~\.adaptive_cli\` (directorio de datos y aprendizaje) |
| 4 | Registra los 4 hooks en `~\.claude\settings.json` |
| 5 | Verifica la instalacion y guarda `install_config.json` |

---

## Opciones de linea de comandos

```bat
REM Instalar en directorio personalizado
install.bat --dir "D:\MiMotor"

REM Instalar sin registrar hooks (manual despues)
install.bat --no-hooks
```

---

## Instalacion manual de hooks

Si instalaste con `--no-hooks` o Claude Code no estaba instalado al momento,
agrega esto a `%USERPROFILE%\.claude\settings.json`:

```json
{
  "hooks": [
    {
      "type": "PreToolUse",
      "command": "\"C:\\Users\\TU_USUARIO\\AppData\\Local\\Motor_IA\\python_runtime\\python.exe\" \"C:\\Users\\TU_USUARIO\\AppData\\Local\\Motor_IA\\hooks\\session_start.py\""
    },
    {
      "type": "UserPromptSubmit",
      "command": "\"C:\\Users\\TU_USUARIO\\AppData\\Local\\Motor_IA\\python_runtime\\python.exe\" \"C:\\Users\\TU_USUARIO\\AppData\\Local\\Motor_IA\\hooks\\user_prompt_submit.py\""
    },
    {
      "type": "PostToolUse",
      "command": "\"C:\\Users\\TU_USUARIO\\AppData\\Local\\Motor_IA\\python_runtime\\python.exe\" \"C:\\Users\\TU_USUARIO\\AppData\\Local\\Motor_IA\\hooks\\post_tool_use.py\""
    },
    {
      "type": "Stop",
      "command": "\"C:\\Users\\TU_USUARIO\\AppData\\Local\\Motor_IA\\python_runtime\\python.exe\" \"C:\\Users\\TU_USUARIO\\AppData\\Local\\Motor_IA\\hooks\\session_end.py\""
    }
  ]
}
```

Reemplaza `TU_USUARIO` con tu nombre de usuario de Windows.

---

## Verificar la instalacion

Abre una terminal y ejecuta:

```bat
%LOCALAPPDATA%\Motor_IA\python_runtime\python.exe -c "import sys; sys.path.insert(0, r'%LOCALAPPDATA%\Motor_IA'); from config import DATA_DIR; print('Motor_IA OK, datos en:', DATA_DIR)"
```

---

## TUI (interfaz visual en terminal)

```bat
%LOCALAPPDATA%\Motor_IA\python_runtime\python.exe -m core.tui
```

Comandos disponibles:

```
memory          — patrones de aprendizaje
working         — working memory actual
graph           — grafo asociativo
stats           — estadisticas completas
search <texto>  — busqueda episodica
timeline <texto>— timeline con contexto
kb <texto>      — busqueda en knowledge base
```

---

## Estructura de archivos instalados

```
%LOCALAPPDATA%\Motor_IA\
  config.py               — configuracion central
  core\                   — modulos de memoria y aprendizaje
  hooks\                  — hooks para Claude Code
  adapters\               — adaptadores para distintos CLIs
  python_runtime\         — Python 3.12 embebido (sin instalacion)
  install_config.json     — registro de instalacion

%USERPROFILE%\.adaptive_cli\
  knowledge\              — base de conocimiento por dominio
  learned_patterns.json   — patrones aprendidos
  session_history.json    — historial de sesiones
  episodic_index.db       — indice de memoria episodica
  locks\                  — control de concurrencia
  hook_state\             — estado entre hooks
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

## Sololucion de problemas

**Los hooks no se activan**
- Verifica que `%USERPROFILE%\.claude\settings.json` tenga las 4 entradas de hooks
- Confirma que `python_runtime\python.exe` existe en el directorio de instalacion

**Error al ejecutar install.bat**
- Ejecuta como administrador si hay errores de permisos
- Verifica que la carpeta `installer\bundle\python_win\python.exe` existe en el repositorio

**Motor_IA no aprende entre sesiones**
- Verifica que `%USERPROFILE%\.adaptive_cli\` existe y tiene permisos de escritura
