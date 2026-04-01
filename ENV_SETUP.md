# Environment Configuration - Motor-Fusion

Motor-Fusion supports both environment variables and a `.env` file for configuration. This ensures the system is portable across different machines and deployment environments.

## Quick Start

1. **Copy the example configuration:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` for your environment** (optional - defaults work for local development):
   ```bash
   nano .env        # Linux/Mac
   notepad .env     # Windows
   ```

3. **Run Motor-Fusion** - it will automatically load variables from `.env`:
   ```bash
   python main.py
   python -m dashboard.server
   python mcp_kb_server.py
   ```

## Environment Variable Loading

Motor-Fusion loads environment variables in this order (highest to lowest precedence):

1. **OS Environment Variables** - Set in your shell/system
2. **.env file** - Auto-loaded from `.env` in Motor-Fusion root directory
3. **Default values** - Hard-coded defaults in Python code

### Load Priority Example

```bash
# Set in shell - takes precedence
export OLLAMA_BASE_URL=http://custom.ollama.server:11434

# .env file - used if not in shell
OLLAMA_BASE_URL=http://localhost:11434

# Result: custom.ollama.server:11434 is used
```

## Configuration Files

### `.env.example`
Template showing all available variables with descriptions.

### `.env`
Your actual configuration. Create by copying `.env.example`:
```bash
cp .env.example .env
```

## Configuration Sections

### Data Directory
```
MOTOR_IA_DATA=               # Leave empty for auto-detection
```

**Fallback Chain (if MOTOR_IA_DATA not set):**
1. `$HOME/.adaptive_cli`
2. `$LOCALAPPDATA/ClaudeCode/.adaptive_cli` (Windows only)
3. `$HOME/.adaptive_cli` (fallback)

### Ollama (Local LLM Provider)
```
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_DEFAULT_MODEL=qwen3:4b
OLLAMA_TIMEOUT_SECS=300
```

### Dashboard Web Interface
```
DASHBOARD_PORT=7070
DASHBOARD_HOST=localhost
```

Start dashboard with custom port:
```bash
python -m dashboard.server          # Uses .env or default
python -m dashboard.server 8080     # Override port via CLI
```

Or use environment variable:
```bash
DASHBOARD_PORT=8080 python -m dashboard.server
```

### Claude CLI Integration
```
CLAUDE_CLI_HOME=
CLAUDE_SETTINGS_PATH=
```

The system auto-detects Claude CLI settings.json in standard locations. Set `CLAUDE_SETTINGS_PATH` if in a non-standard location:

```bash
export CLAUDE_SETTINGS_PATH="/custom/path/.claude/settings.json"
```

### Knowledge Base
```
KNOWLEDGE_BASE_DIR=knowledge        # Path relative to Motor-Fusion root
MAX_KB_CHARS=3000                   # Context injection limit
```

### Learning and Patterns
```
CONFIDENCE_THRESHOLD=0.6            # Reuse pattern confidence threshold
MAX_PENDING_ERRORS=15               # Error buffer size
AUTO_DOMAIN_MIN_SESSIONS=3          # Sessions for auto-promotion
```

## Platform-Specific Setup

### Windows

1. **Using .env file (Recommended):**
   ```bash
   copy .env.example .env
   # Edit .env with Notepad or VS Code
   python main.py
   ```

2. **Using System Environment Variables:**
   - Open Settings → System → Environment Variables
   - Add Variable: `MOTOR_IA_DATA = C:\path\to\data`
   - Add Variable: `OLLAMA_BASE_URL = http://localhost:11434`
   - Restart terminal/IDE

3. **Using PowerShell:**
   ```powershell
   $env:MOTOR_IA_DATA = "C:\path\to\data"
   $env:DASHBOARD_PORT = "7070"
   python main.py
   ```

4. **Using .bat script:**
   ```batch
   @echo off
   set MOTOR_IA_DATA=C:\path\to\data
   set OLLAMA_BASE_URL=http://localhost:11434
   python main.py
   ```

### Linux / macOS

1. **Using .env file (Recommended):**
   ```bash
   cp .env.example .env
   # Edit .env with nano, vim, or your editor
   python main.py
   ```

2. **Using .bashrc / .zshrc:**
   ```bash
   # Add to ~/.bashrc or ~/.zshrc
   export MOTOR_IA_DATA="$HOME/.motor_fusion_data"
   export OLLAMA_BASE_URL="http://localhost:11434"

   # Reload
   source ~/.bashrc
   ```

3. **Using inline environment variables:**
   ```bash
   MOTOR_IA_DATA=/tmp/motor OLLAMA_BASE_URL=http://localhost:11434 python main.py
   ```

4. **Using .env.local (ignored by git):**
   ```bash
   cp .env .env.local
   # Edit .env.local with your local overrides
   # .env.local is in .gitignore - safe for secrets
   ```

## Docker / Container Deployment

### Using Environment Variables

```dockerfile
FROM python:3.9

WORKDIR /motor

COPY . .

# Set environment variables
ENV MOTOR_IA_DATA=/data/motor
ENV OLLAMA_BASE_URL=http://ollama:11434
ENV DASHBOARD_PORT=7070

CMD ["python", "main.py"]
```

### Using .env File

```dockerfile
FROM python:3.9

WORKDIR /motor

COPY . .

# Copy .env for container
COPY .env .

CMD ["python", "main.py"]
```

### Docker Compose

```yaml
version: '3'
services:
  motor:
    build: .
    environment:
      MOTOR_IA_DATA: /data/motor
      OLLAMA_BASE_URL: http://ollama:11434
      DASHBOARD_PORT: 7070
    volumes:
      - motor_data:/data/motor
    ports:
      - "7070:7070"

  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"

volumes:
  motor_data:
```

## Debugging

### Check Loaded Configuration

```python
import os
from config import DATA_DIR, OLLAMA_BASE_URL

print(f"Data Directory: {DATA_DIR}")
print(f"Ollama URL: {OLLAMA_BASE_URL}")
print(f"Dashboard Port: {os.environ.get('DASHBOARD_PORT', 'default=7070')}")
```

### Verify .env File Loading

```bash
# Check if .env exists
ls -la .env

# Check specific variable
grep OLLAMA_BASE_URL .env

# Test loading
python -c "from core.env_loader import load_env_file; load_env_file(); import os; print(os.environ.get('OLLAMA_BASE_URL'))"
```

### Environment Variable Precedence

```bash
# Test environment variable takes precedence over .env
export OLLAMA_BASE_URL="http://override:11434"
python -c "import os; print(os.environ.get('OLLAMA_BASE_URL'))"
# Output: http://override:11434
```

## Security Notes

⚠️ **Never commit `.env` to git** - it may contain secrets!

- `.env` is in `.gitignore` - safe to store credentials
- `.env.example` is committed - shows structure without secrets
- Use `CLAUDE_SETTINGS_PATH` for path to Claude credentials
- Never hardcode API keys in code

## Troubleshooting

### Variables Not Loading

1. **Check .env file exists:**
   ```bash
   ls -la .env
   ```

2. **Check for syntax errors in .env:**
   ```bash
   # Should work without errors
   python -c "from pathlib import Path; print(Path('.env').read_text())"
   ```

3. **Verify precedence - shell variable overrides .env:**
   ```bash
   # Unset any shell variables
   unset OLLAMA_BASE_URL

   # Then run
   python main.py
   ```

### Wrong Port Being Used

```bash
# Method 1: Check .env
grep DASHBOARD_PORT .env

# Method 2: Check environment
echo $DASHBOARD_PORT

# Method 3: Check CLI override
python -m dashboard.server 9000  # Uses 9000 if in .env it's 7070
```

### Data Directory Not Found

```bash
# Check MOTOR_IA_DATA is set correctly
echo $MOTOR_IA_DATA

# Or check fallback paths exist
ls -la ~/.adaptive_cli
ls -la "$LOCALAPPDATA/ClaudeCode/.adaptive_cli"  # Windows
```

## Reference

See `.env.example` for complete list of all available variables.

For detailed configuration logic, see `config.py`.

For .env loading implementation, see `core/env_loader.py`.
