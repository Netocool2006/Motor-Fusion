# Motor Fusion IA - Manual de Instalacion

**Version:** 1.0.3-offline  
**Fecha:** Abril 2026  
**Plataforma:** Windows 10/11 (64-bit)

---

## Tabla de Contenidos

1. [Requisitos del Sistema](#1-requisitos-del-sistema)
2. [Escenarios de Instalacion](#2-escenarios-de-instalacion)
3. [Instalacion Offline (PC sin internet)](#3-instalacion-offline-pc-sin-internet)
4. [Instalacion con Internet](#4-instalacion-con-internet)
5. [Instalacion GUI (Wizard visual)](#5-instalacion-gui-wizard-visual)
6. [Verificacion Post-Instalacion](#6-verificacion-post-instalacion)
7. [Configuracion de Claude Code](#7-configuracion-de-claude-code)
8. [Dashboard de Monitoreo](#8-dashboard-de-monitoreo)
9. [Ingesta Masiva de Conocimiento](#9-ingesta-masiva-de-conocimiento)
10. [Actualizacion](#10-actualizacion)
11. [Desinstalacion](#11-desinstalacion)
12. [Solucion de Problemas](#12-solucion-de-problemas)

---

## 1. Requisitos del Sistema

### Hardware Minimo
| Componente | Minimo | Recomendado |
|---|---|---|
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8+ GB |
| Disco | 2 GB libres | 5+ GB libres |
| Arquitectura | x64 (64-bit) | x64 (64-bit) |

### Software
| Componente | Requerido | Notas |
|---|---|---|
| Windows | 10 o 11 (64-bit) | Build 1809 o superior |
| Python | **No requerido** | Incluido en el instalador offline |
| Internet | **No requerido** | Solo para la instalacion con internet |
| Claude Code CLI | Recomendado | Se integra automaticamente si esta instalado |

### Espacio en Disco Detallado
| Componente | Tamano |
|---|---|
| Python embebido | ~30 MB |
| Dependencias pip (torch CPU, chromadb, etc.) | ~400 MB |
| Modelo de embeddings (all-MiniLM-L6-v2) | ~90 MB |
| Codigo Motor_IA + Knowledge base | ~30 MB |
| ChromaDB (crece con el uso) | ~10 MB inicial |
| **Total instalacion** | **~560 MB** |
| **Espacio recomendado** | **2 GB** (para crecimiento del KB) |

---

## 2. Escenarios de Instalacion

### Escenario A: PC sin internet (Offline)
**Para:** Maquinas aisladas, entornos corporativos sin acceso a internet.

1. En una maquina CON internet, generar el paquete offline
2. Copiar paquete a USB (~600 MB)
3. En el PC destino, ejecutar `install.bat`

### Escenario B: PC con internet
**Para:** Instalacion rapida con acceso a internet.

1. Clonar o copiar el repositorio
2. Ejecutar `python installer/offline_install.py`

### Escenario C: Instalacion visual (GUI)
**Para:** Usuarios que prefieren un wizard grafico.

1. Ejecutar `python installer/installer_gui.py`
2. Seguir los pasos del wizard

---

## 3. Instalacion Offline (PC sin internet)

### Paso 1: Generar el paquete (en maquina CON internet)

```bash
cd C:\Hooks_IA
python installer/build_offline_package.py -o "D:\Motor_IA_Installer"
```

Opciones disponibles:
```
--output, -o    Directorio de salida (default: ../Motor_IA_Installer)
--skip-wheels   No descargar dependencias pip (solo si ya estan)
--skip-model    No copiar el modelo de embeddings
```

El proceso descarga automaticamente:
- Python 3.12 embebido para Windows
- Todos los wheels pip necesarios (~400 MB)
- Modelo de embeddings all-MiniLM-L6-v2 (~90 MB)
- Copia el proyecto completo (codigo, knowledge, dashboard)

**Tiempo estimado:** 5-15 minutos (depende de la velocidad de internet)

### Paso 2: Copiar a USB

Copiar la carpeta completa `Motor_IA_Installer/` a una unidad USB.

**Estructura del paquete:**
```
Motor_IA_Installer/
  install.bat                   <- Ejecutar esto
  LEEME.txt                     <- Instrucciones rapidas
  PACKAGE_INFO.json             <- Metadatos del paquete
  config.py                     <- Configuracion
  core/                         <- Modulos principales
  hooks/                        <- Hooks para Claude Code
  knowledge/                    <- Base de conocimiento
  dashboard/                    <- Dashboard web
  installer/
    offline_install.py           <- Instalador Python
    build_offline_package.py     <- Generador de paquete
    installer_gui.py             <- Instalador visual
    bundle/
      python_win/                <- Python 3.12 embebido
      wheels/                    <- Dependencias pip offline
      model/                     <- Modelo de embeddings
      get-pip.py                 <- Instalador de pip
```

### Paso 3: Instalar en el PC destino

1. Conectar el USB al PC destino
2. Abrir la carpeta `Motor_IA_Installer/`
3. **Doble-click en `install.bat`**
4. Esperar ~3 minutos

El instalador ejecuta automaticamente:

| Paso | Que hace | Tiempo |
|---|---|---|
| 1 | Instala pip en Python embebido | ~10 seg |
| 2 | Instala todas las dependencias desde wheels | ~2 min |
| 3 | Pre-carga modelo de embeddings | ~10 seg |
| 4 | Copia Motor_IA al directorio de instalacion | ~20 seg |
| 5 | Registra hooks en Claude Code | ~5 seg |
| 6 | Verifica instalacion | ~5 seg |

### Paso 4: Verificar

Al terminar, el instalador muestra:
```
============================================================
  RESULTADO
============================================================
  Motor_IA instalado correctamente.
  Motor:  C:\Users\<usuario>\AppData\Local\Motor_IA
  Python: C:\Users\<usuario>\AppData\Local\Motor_IA\python_runtime\python.exe
  Datos:  C:\Users\<usuario>\.adaptive_cli
```

---

## 4. Instalacion con Internet

Si el PC destino tiene internet, la instalacion es mas sencilla:

### Paso 1: Obtener el codigo
```bash
git clone <repositorio> C:\Hooks_IA
```
O copiar la carpeta del proyecto.

### Paso 2: Instalar dependencias
```bash
cd C:\Hooks_IA
pip install -r requirements.txt
pip install chromadb sentence-transformers torch --index-url https://download.pytorch.org/whl/cpu
pip install duckduckgo-search
```

### Paso 3: Ejecutar instalador
```bash
python installer/offline_install.py
```

### Paso 4: Primer uso
El modelo de embeddings se descarga automaticamente en el primer uso (~90 MB).

---

## 5. Instalacion GUI (Wizard Visual)

```bash
python installer/installer_gui.py
```

El wizard guia paso a paso:
1. **Bienvenida** - Logo y version
2. **Directorio** - Seleccionar donde instalar (default: `C:\Program Files\Motor Fusion IA`)
3. **Componentes** - Seleccionar que instalar
4. **Progreso** - Barra de progreso visual
5. **Completado** - Resumen y opcion de abrir dashboard

---

## 6. Verificacion Post-Instalacion

### Verificacion rapida
```bash
cd C:\Hooks_IA
python -c "from core.vector_kb import get_stats; print(get_stats())"
```

Resultado esperado:
```python
{'total': 300, 'facts': 116, 'patterns': 138, 'learned': 45, 'sessions': 1}
```

### Verificacion completa

| Componente | Comando | Resultado esperado |
|---|---|---|
| Python | `python --version` | Python 3.12.x |
| ChromaDB | `python -c "import chromadb; print('OK')"` | OK |
| Embeddings | `python -c "from sentence_transformers import SentenceTransformer; print('OK')"` | OK |
| Knowledge Base | `python -c "from core.knowledge_base import list_domains; print(len(list_domains()))"` | 90+ (depende de ingesta) |
| Vector KB | `python -c "from core.vector_kb import get_stats; print(get_stats()['total'])"` | >0 |
| Dashboard | `python dashboard/server.py` | Abre en http://127.0.0.1:8080 |

### Verificar hooks registrados

Abrir el archivo `settings.json` de Claude Code:
```
C:\Users\<usuario>\AppData\Local\ClaudeCode\.claude\settings.json
```

Debe contener:
```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "python C:/Hooks_IA/hooks/motor_ia_hook.py"
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "python C:/Hooks_IA/hooks/session_end.py"
      }
    ]
  }
}
```

---

## 7. Configuracion de Claude Code

### Hooks disponibles

| Evento | Script | Funcion |
|---|---|---|
| `UserPromptSubmit` | `motor_ia_hook.py` | Busca en KB + Internet antes de cada respuesta |
| `Stop` | `session_end.py` | Guarda aprendizaje al cerrar sesion |
| `PreToolUse` | `session_start.py` | Inyecta contexto al inicio de sesion |
| `Stop` | `motor_ia_post_hook.py` | Auto-guarda conocimiento nuevo al KB |

### Registro manual de hooks

Si los hooks no se registraron automaticamente:

1. Localizar `settings.json`:
   ```
   Windows: %LOCALAPPDATA%\ClaudeCode\.claude\settings.json
   ```

2. Agregar la seccion de hooks (ver ejemplo arriba en seccion 6)

### Servidor MCP (opcional, para Claude Desktop)

Agregar a la configuracion de Claude Desktop:
```json
{
  "mcpServers": {
    "motor-ia": {
      "command": "python",
      "args": ["C:\\Hooks_IA\\mcp_kb_server.py"]
    }
  }
}
```

---

## 8. Dashboard de Monitoreo

### Iniciar el dashboard
```bash
python C:\Hooks_IA\dashboard\server.py
```
Abre en: **http://127.0.0.1:8080**

### Cambiar puerto
```bash
python C:\Hooks_IA\dashboard\server.py 9090
```
O con variable de entorno:
```bash
set DASHBOARD_PORT=9090
python C:\Hooks_IA\dashboard\server.py
```

### Que muestra el dashboard

| Panel | Informacion | Alerta |
|---|---|---|
| ChromaDB | Total docs, facts, patterns, learned | Rojo si vacio o error |
| Hooks | Pre-hook y Post-hook registrados | Rojo si MISSING |
| Actividad | Queries, cache hits, web searches, errores | Rojo si errores > 0 |
| Knowledge | Dominios, tamano en MB | Rojo si no existe |
| Ultima Consulta | Query, resultado, barra KB/Internet/ML | -- |
| Log | Ultimas 15 lineas coloreadas | ERROR en rojo |
| Health Badge | HEALTHY / DEGRADED / CRITICAL | Segun componentes |
| Log de Ingesta | Ultimas 50 lineas del log de ingesta masiva | Coloreado por nivel |

### Auto-refresh
El dashboard se actualiza automaticamente cada 5 segundos.
El log de ingesta se actualiza cada 10 segundos.

---

## 9. Ingesta Masiva de Conocimiento

### Desde el Dashboard
1. Click en el boton **"+ Ingesta Masiva"** en la esquina superior derecha
2. Ingresar la ruta a escanear manualmente o usar el boton **"Explorar..."** para abrir el explorador de Windows y seleccionar la carpeta
3. Configurar opciones:
   - **Profundidad:** Niveles de carpetas a escanear (default: 3)
   - **Min. archivos por dominio:** Minimo de archivos para crear un dominio (default: 3)
   - **Max. archivos por dominio:** Maximo de archivos a ingerir por dominio (default: 50)
4. Click en **"Iniciar Escaneo e Ingesta"**
5. Ver progreso en tiempo real (dominios, archivos, facts, duplicados)
6. Al terminar, ver tabla de resultados con detalle por dominio

### Desde la linea de comandos
```bash
python C:\Hooks_IA\core\disk_scanner.py ingest D:\MisDocumentos
```

### Deduplicacion en Tiempo Real
El sistema verifica automaticamente antes de guardar cada pieza de informacion:
- Calcula la similitud coseno contra la base de datos existente en ChromaDB
- Si la similitud es > 92% (distancia coseno < 0.08), el contenido se descarta como duplicado
- Cada chunk ingestado se indexa inmediatamente en ChromaDB, permitiendo deteccion de duplicados dentro de la misma sesion de ingesta
- Esto evita llenar el KB con informacion repetida, incluso entre dominios diferentes

### Log de Ingesta
Cada sesion de ingesta genera un log detallado en `core/ingest.log` con:
- Inicio y parametros de la ingesta (ruta, profundidad, limites)
- Dominios creados, omitidos (por baja confianza) y fallidos
- Duplicados detectados por dominio
- Resumen final (dominios, facts, duplicados, tiempo)

### Formatos soportados para ingesta

| Categoria | Extensiones |
|---|---|
| Texto plano | .txt, .md, .csv, .log, .ini, .cfg, .yaml, .yml, .toml |
| Codigo | .py, .js, .ts, .java, .go, .rs, .c, .cpp, .cs, .rb, .php, .sql |
| Office | .docx, .xlsx, .pptx |
| PDF | .pdf |
| Web | .html, .css, .json, .xml |

---

## 10. Actualizacion

### Actualizar el codigo
```bash
cd C:\Hooks_IA
git pull origin master
```

### Re-indexar el KB despues de actualizar
```bash
python -c "from core.vector_kb import index_knowledge_base; print(index_knowledge_base())"
```

---

## 11. Desinstalacion

### Eliminar Motor_IA
1. Borrar el directorio de instalacion:
   ```bash
   rmdir /s /q "C:\Users\<usuario>\AppData\Local\Motor_IA"
   ```

2. Borrar datos de usuario:
   ```bash
   rmdir /s /q "C:\Users\<usuario>\.adaptive_cli"
   ```

3. Remover hooks de Claude Code:
   - Editar `settings.json` de Claude Code
   - Eliminar las entradas de `hooks` y `mcpServers` relacionadas con Motor_IA

---

## 12. Solucion de Problemas

### Error: "python no reconocido"
El instalador offline incluye su propio Python. Usar:
```bash
C:\Users\<usuario>\AppData\Local\Motor_IA\python_runtime\python.exe
```

### Error: "chromadb not found" o "sentence_transformers not found"
Las dependencias no se instalaron. Ejecutar:
```bash
python -m pip install --no-index --find-links installer/bundle/wheels chromadb sentence-transformers torch
```

### Error: "Model not found" en primer uso
Si el modelo no se incluyo en el paquete offline, necesita internet para descargarlo la primera vez:
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

### El dashboard no abre
Verificar que el puerto no este ocupado:
```bash
netstat -an | findstr :8080
```
Si esta ocupado, usar otro puerto:
```bash
python dashboard/server.py 9090
```

### Los hooks no se activan
1. Verificar que Claude Code esta instalado
2. Verificar `settings.json` tiene las entradas correctas
3. Verificar que Python puede ejecutar los hooks:
   ```bash
   echo '{"prompt":"test"}' | python C:\Hooks_IA\hooks\motor_ia_hook.py
   ```

### Logs de diagnostico
| Log | Ubicacion | Contenido |
|---|---|---|
| Hook principal | `core/motor_ia_hook.log` | Queries, KB hits, web searches |
| Debug | `core/debug.log` | Session start/end, errores internos |
| Acciones | `core/actions.log` | Registro de operaciones del KB |

### Reiniciar ChromaDB
Si la base de datos se corrompe:
```bash
rmdir /s /q core\chroma_db
python -c "from core.vector_kb import index_knowledge_base; print(index_knowledge_base())"
```
Esto reconstruye ChromaDB desde los archivos JSON en `knowledge/`.
