# REPORTE DE HARDCODES - Motor-Fusion

## Búsqueda realizada
Análisis de archivos Python en Motor-Fusion para identificar valores quemados.


## 1. PATHS ABSOLUTOS (C:\, /home/, etc)
./tests/test_exhaustivo_fusion.py:        "transcript_path": "/tmp/transcript.jsonl",
./tests/test_exhaustivo_fusion.py:    ctx = extract_context("Edit", {"file_path": "/tmp/test.py", "old_string": "x=1", "new_string": "x=2"}, "OK")

## 2. PUERTOS HARDCODEADOS (localhost:XXXX)
./adapters/ollama.py:    POST http://localhost:11434/api/chat
./config.py:OLLAMA_BASE_URL: str          = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
./installer/bundle/python_win/Lib/site-packages/rich/logging.py:    log.info("Listening on http://127.0.0.1:8080")
./tests/test_exhaustivo_fusion.py:        resp = urlopen("http://127.0.0.1:17437/health", timeout=2)
./tests/test_exhaustivo_fusion.py:            "http://127.0.0.1:17438/mem/save",

## 3. URLs HARDCODEADAS
./adapters/gemini.py:  - https://cloud.google.com/gemini/docs (verificar actualizaciones)
./adapters/ollama.py:    POST http://localhost:11434/api/chat
./config.py:OLLAMA_BASE_URL: str          = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
./core/file_extractor.py:    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
./core/file_extractor.py:    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
./core/file_extractor.py:    ns_a = 'http://schemas.openxmlformats.org/drawingml/2006/main'
./core/http_api.py:        print(f"Motor_IA HTTP API corriendo en http://{host}:{port}")
./core/learning_memory.py:    r"Running on http://",
./dashboard/server.py:    print(f"Motor_IA Dashboard  ->  http://localhost:{port}")
./hooks/post_tool_use.py:    r"Running on http://",
./installer/bundle/get-pip.py:# `scripts/generate.py` in https://github.com/pypa/get-pip.
./installer/bundle/get-pip.py:        "Please use https://bootstrap.pypa.io/pip/{}.{}/get-pip.py instead.".format(*this_python),
./installer/bundle/python_win/Lib/site-packages/markdown_it/common/html_blocks.py:http://jgm.github.io/CommonMark/spec.html#html-blocks
./installer/bundle/python_win/Lib/site-packages/markdown_it/common/html_blocks.py:# see https://spec.commonmark.org/0.31.2/#html-blocks
./installer/bundle/python_win/Lib/site-packages/markdown_it/common/normalize_url.py:    # `http://host/`, `https://host/`, `mailto:user@host`, `//host/`
./installer/bundle/python_win/Lib/site-packages/markdown_it/common/normalize_url.py:    # `http://host/`, `https://host/`, `mailto:user@host`, `//host/`
./installer/bundle/python_win/Lib/site-packages/markdown_it/common/normalize_url.py:    # add '%' to exclude list because of https://github.com/markdown-it/markdown-it/issues/720
./installer/bundle/python_win/Lib/site-packages/markdown_it/common/utils.py:    see https://spec.commonmark.org/0.30/#entity-references
./installer/bundle/python_win/Lib/site-packages/markdown_it/common/utils.py:    See http://spec.commonmark.org/0.15/#ascii-punctuation-character
./installer/bundle/python_win/Lib/site-packages/markdown_it/main.py:        [here](https://github.com/markdown-it/markdown-it/tree/master/lib/presets)

## 4. RUTAS RELATIVAS SOSPECHOSAS
./build_package.py:    "hooks/",
./hooks/session_start.py:                "0 capturados. Revisar hooks/session_end.py"
./installer/setup.py:        "command": "python {motor_dir}/hooks/on_user_message.py",
./installer/setup.py:        "command": "python {motor_dir}/hooks/on_session_end.py",
./installer/setup.py:        "command": "python {motor_dir}/hooks/on_tool_use.py",
./installer/setup.py:    Gemini CLI uses GEMINI_CLI_HOOKS env or ~/.gemini/hooks/ directory.
./installer/setup.py:    Creates a wrapper in ~/.ollama/hooks/ for custom integrations.
./sync_to_github.py:    "knowledge",  # knowledge/*.json  (13 dominios)

## 5. VARIABLES DE ENTORNO NO USADAS
./config.py:    env_val = os.environ.get("MOTOR_IA_DATA")
./config.py:        local_app = os.environ.get("LOCALAPPDATA")
./config.py:OLLAMA_BASE_URL: str          = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
./config.py:OLLAMA_DEFAULT_MODEL: str     = os.environ.get("OLLAMA_DEFAULT_MODEL", "qwen3:4b")
./config.py:AUTO_DOMAIN_MIN_SESSIONS: int      = int(os.environ.get("AUTO_DOMAIN_MIN_SESSIONS", "3"))
./config.py:AUTO_DOMAIN_MIN_MSGS: int          = int(os.environ.get("AUTO_DOMAIN_MIN_MSGS", "3"))
./dashboard/server.py:DATA_DIR = Path(os.environ.get(
./installer/bundle/get-pip.py:    env = not os.environ.get("PIP_NO_SETUPTOOLS")
./installer/bundle/get-pip.py:    env = not os.environ.get("PIP_NO_WHEEL")
./installer/bundle/python_win/Lib/site-packages/rich/console.py:        or os.getenv("DATABRICKS_RUNTIME_VERSION")
