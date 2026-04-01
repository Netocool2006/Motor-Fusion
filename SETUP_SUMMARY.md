# Hooks_IA - Setup Summary

## Changes Made (2026-04-01)

### 1. Centralized Configuration (No Hardcoded Paths)
- **Created**: `config.py`
- **Purpose**: All paths use environment variables for portability
- **Key**: No more hardcoded `C:\Users\...` paths
- **Usage**: `from config import CHANCE_PROJECT_DIR, KB_ENFORCER_LOG, etc.`

### 2. Mandatory Protocol Updated
- **Location**: `C:\Hooks_IA\MANDATORY_PROTOCOL.txt` (moved from C:\Chance1)
- **Updated**: Added requirement to REALLY EXECUTE KB search, not just paint numbers
- **Rules**:
  1. ALWAYS execute: `process_query_with_kb(query)`
  2. Report REAL coverage (KB%, Internet%, ML% from actual search)
  3. Include: `**Fuentes:** KB X% + Internet Y% + ML Z%` in EVERY response
  4. Auto-save when KB% = 0%
  5. Use relative/environment paths - NO hardcoding

### 3. Hooks Updated for Portability
- **kb_enforcer_hook.py**: Now uses config.py instead of hardcoded paths
- **response_validator_hook.py**: Now uses config.py instead of hardcoded paths
- **All hooks**: Support environment variable CLAUDE_PROJECTS_DIR for flexibility

### 4. Everything in C:\Hooks_IA
- ALL project-related files must be in C:\Hooks_IA
- Moved MANDATORY_PROTOCOL.txt from C:\Chance1 to C:\Hooks_IA
- Config centralized in config.py

## How It Works Now

### Configuration Chain
1. Script loads `config.py`
2. `config.py` detects actual user directory via environment
3. All paths resolved dynamically - NO hardcoding
4. Portable to any machine with same user structure

### KB Search Execution
1. Hook calls: `process_query_with_kb(user_query)`
2. Function REALLY executes KB search in `knowledge/` directory
3. Returns REAL coverage percentages
4. Auto-saves if needed
5. Reports: `**Fuentes:** KB X% + Internet Y% + ML Z%`

## Files Location
```
C:\Hooks_IA\
├── config.py                 (Centralized config - no hardcoded paths)
├── MANDATORY_PROTOCOL.txt    (Rules for Claude - execute KB, not fake)
├── core/
│   ├── kb_response_engine.py (KB→Internet→ML execution)
│   ├── search_protocol.py
│   └── kb_enforcer.log
├── hooks/
│   ├── kb_enforcer_hook.py   (Uses config.py - portable)
│   ├── response_validator_hook.py (Uses config.py - portable)
│   └── ...
├── knowledge/
│   ├── general/
│   ├── sap_tierra/
│   └── ... (all domains)
└── dashboard/
    ├── server.py
    └── index.html
```

## Portability
- Move C:\Hooks_IA to ANY location
- Paths will still work (uses relative paths and env vars)
- No need to update hardcoded paths
- No breaking on machine moves/reinstalls
