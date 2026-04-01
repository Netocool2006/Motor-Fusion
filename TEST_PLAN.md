# Motor-Fusion Comprehensive Test Plan

## Document Information
- **Version**: 1.0
- **Date**: 2026-03-31
- **Scope**: Motor-Fusion after consolidation and environment variable hardening
- **Objective**: Zero failures in all use cases, sub-cases, and sub-sub-cases
- **Environment**: Windows 11, Python 3.9+, Ollama local instance

---

## 1. CONFIGURATION & ENVIRONMENT

### 1.1 Environment Variable Loading
**Use Case**: System loads environment variables from .env file correctly

#### 1.1.1 .env File Presence
- **Case**: .env file exists in Motor-Fusion root
- **Sub-Case 1a**: .env file is readable and not corrupted
  - Verify file exists: `ls -la C:\Hooks_IA\.env`
  - Verify no parse errors: `python -c "from pathlib import Path; Path('C:\\Hooks_IA\\.env').read_text()"`
  - **Expected**: File readable, no syntax errors

- **Sub-Case 1b**: .env contains all required variables
  - Check for key variables: OLLAMA_BASE_URL, DASHBOARD_PORT, MOTOR_IA_DATA
  - **Expected**: All variables present with valid values

#### 1.1.2 Environment Variable Loading Mechanism
- **Case**: Python code loads .env file on startup
- **Sub-Case 2a**: config.py loads .env at import time
  - Execute: `python -c "import config; import os; print(os.environ.get('OLLAMA_BASE_URL'))"`
  - **Expected**: Value from .env is printed (not default)

- **Sub-Case 2b**: env_loader.py works without external dependencies
  - Execute: `python -c "from core.env_loader import load_env_file; load_env_file(); print('OK')"`
  - **Expected**: No ImportError, prints "OK"

- **Sub-Case 2c**: Environment variables take precedence over .env
  - Set shell variable: `set OLLAMA_BASE_URL=http://test:11434`
  - Execute: `python -c "import os; print(os.environ.get('OLLAMA_BASE_URL'))"`
  - **Expected**: Shell value (http://test:11434) is used, not .env value

#### 1.1.3 Data Directory Resolution
- **Case**: DATA_DIR resolves with correct fallback chain
- **Sub-Case 3a**: MOTOR_IA_DATA environment variable is respected
  - Set: `set MOTOR_IA_DATA=C:\test_data`
  - Execute: `python -c "from config import DATA_DIR; print(DATA_DIR)"`
  - **Expected**: C:\test_data

- **Sub-Case 3b**: Fallback to HOME/.adaptive_cli if MOTOR_IA_DATA not set
  - Unset: `set MOTOR_IA_DATA=`
  - Execute: `python -c "from config import DATA_DIR; print(DATA_DIR)"`
  - **Expected**: Returns path containing .adaptive_cli

- **Sub-Case 3c**: Data directories are created automatically
  - Execute: `python -c "from config import DATA_DIR, KNOWLEDGE_DIR; print(DATA_DIR.exists(), KNOWLEDGE_DIR.exists())"`
  - **Expected**: Both True

---

## 2. KNOWLEDGE BASE OPERATIONS

### 2.1 Knowledge Ingestion
**Use Case**: Add new patterns and facts to knowledge base

#### 2.1.1 Pattern Ingestion
- **Case**: Add new patterns via ingest_knowledge.py
- **Sub-Case 1a**: Ingest text file as pattern
  - Create test file: `C:\test_kb\test.txt` with content "Test pattern for motor"
  - Execute: `python ingest_knowledge.py C:\test_kb\test.txt --domain test_domain`
  - Verify: Check `~/.adaptive_cli/knowledge/test_domain/patterns.json` contains entry
  - **Expected**: Pattern added successfully

- **Sub-Case 1b**: Ingest with custom tags
  - Execute: `python ingest_knowledge.py C:\test_kb\test.txt --domain test_domain --tags motor,test,validation`
  - Verify: Pattern has tags in knowledge base
  - **Expected**: Tags stored correctly

- **Sub-Case 1c**: Ingest with type specification
  - Execute: `python ingest_knowledge.py C:\test_kb\test.txt --domain test_domain --type fact`
  - Verify: Added as fact, not pattern
  - **Expected**: Stored in facts.json

- **Sub-Case 1d**: Preview mode (dry-run)
  - Execute: `python ingest_knowledge.py C:\test_kb\test.txt --preview`
  - Verify: No files modified, output shows what would be added
  - **Expected**: Preview only, no KB changes

#### 2.1.2 Multiple File Types
- **Case**: Ingest various file formats
- **Sub-Case 2a**: Text file (.txt)
  - Execute: `python ingest_knowledge.py test.txt --domain general`
  - **Expected**: Successfully ingested

- **Sub-Case 2b**: Markdown file (.md)
  - Execute: `python ingest_knowledge.py readme.md --domain docs`
  - **Expected**: Successfully ingested

- **Sub-Case 2c**: JSON file (.json)
  - Execute: `python ingest_knowledge.py config.json --domain config`
  - **Expected**: Successfully ingested

- **Sub-Case 2d**: Directory ingestion
  - Execute: `python ingest_knowledge.py C:\test_kb\ --domain batch`
  - **Expected**: All files in directory ingested

#### 2.1.3 Domain Management
- **Case**: Domains are created and managed correctly
- **Sub-Case 3a**: Auto-create domain if not exists
  - Execute: `python ingest_knowledge.py test.txt --domain new_domain_123`
  - Verify: Check domains.json for new_domain_123
  - **Expected**: Domain created automatically

- **Sub-Case 3b**: Domain session counter increments
  - Execute ingest twice for same domain
  - Verify: domain_sessions_counter.json shows count >= 2
  - **Expected**: Session count increments

- **Sub-Case 3c**: Auto-promotion of domains
  - Execute 3+ times with AUTO_DOMAIN_MIN_SESSIONS=3
  - Verify: Domain promoted from candidate to active
  - **Expected**: Domain promoted after threshold

---

## 3. KNOWLEDGE SEARCH & RETRIEVAL

### 3.1 Semantic Search
**Use Case**: Search knowledge base with semantic understanding

#### 3.1.1 Single Domain Search
- **Case**: Search within specific domain
- **Sub-Case 1a**: Exact keyword match
  - Ingest: "SAP Tierra integration pattern"
  - Search: `python -c "from core.knowledge_base import search; r=search('SAP', domain='sap_tierra'); print(len(r))"`
  - **Expected**: Returns matches with SAP

- **Sub-Case 1b**: Partial match with scoring
  - Search: Similar terms to ingested content
  - **Expected**: Returns results ranked by relevance

- **Sub-Case 1c**: No results for unknown query
  - Search: "completely_unknown_xyz_query"
  - **Expected**: Returns empty list

#### 3.1.2 Cross-Domain Search
- **Case**: Search across all domains simultaneously
- **Sub-Case 2a**: Multi-domain query
  - Execute: `python -c "from core.knowledge_base import cross_domain_search; r=cross_domain_search('pattern'); print(len(r))"`
  - **Expected**: Returns matches from multiple domains

- **Sub-Case 2b**: Domain ranking in results
  - Search for term present in multiple domains
  - **Expected**: Results sorted by relevance score

- **Sub-Case 2c**: Cross-domain with limit
  - Execute: `search('term', limit=5)`
  - **Expected**: Returns max 5 results

#### 3.1.3 Context Export
- **Case**: Export knowledge as injection context for LLM
- **Sub-Case 3a**: KB context generation
  - Execute: `from core.knowledge_base import export_context; ctx=export_context('Edit'); print(len(ctx))`
  - **Expected**: Returns string with KB context

- **Sub-Case 3b**: Context respects MAX_KB_CHARS limit
  - Set MAX_KB_CHARS=500
  - Export context
  - **Expected**: Returned context <= 500 characters

- **Sub-Case 3c**: Context includes relevant facts
  - Export after ingesting test data
  - **Expected**: Context includes ingested knowledge

---

## 4. OLLAMA INTEGRATION

### 4.1 Ollama Adapter Configuration
**Use Case**: Connect to Ollama local LLM service

#### 4.1.1 Connection Configuration
- **Case**: Adapter reads Ollama configuration from environment
- **Sub-Case 1a**: OLLAMA_BASE_URL environment variable
  - Set: `set OLLAMA_BASE_URL=http://localhost:11434`
  - Execute: `python -c "from adapters.ollama import OllamaAdapter; a=OllamaAdapter(); print(a.base_url)"`
  - **Expected**: Prints http://localhost:11434

- **Sub-Case 1b**: OLLAMA_DEFAULT_MODEL environment variable
  - Set: `set OLLAMA_DEFAULT_MODEL=llama3:8b`
  - Execute: `python -c "from adapters.ollama import DEFAULT_MODEL; print(DEFAULT_MODEL)"`
  - **Expected**: Prints llama3:8b

- **Sub-Case 1c**: Model can be overridden at runtime
  - Execute: `python ollama_chat.py --model qwen3:4b`
  - **Expected**: Uses specified model

#### 4.1.2 Ollama Service Connection
- **Case**: Verify connection to Ollama service
- **Prerequisite**: Ollama running on localhost:11434 with at least one model
- **Sub-Case 2a**: Health check (if /health endpoint exists)
  - Execute: `curl http://localhost:11434/api/tags`
  - **Expected**: Returns list of available models

- **Sub-Case 2b**: Model list retrieval
  - Execute: `python -c "from adapters.ollama import OllamaAdapter; a=OllamaAdapter(); models=a.get_available_models(); print(len(models))"`
  - **Expected**: Returns list of models, count > 0

- **Sub-Case 2c**: Chat completion without streaming
  - Execute: `python ollama_chat.py --query "say hello" --no-stream`
  - **Expected**: Receives complete response

- **Sub-Case 2d**: Chat with KB context injection
  - Execute: `python ollama_chat.py --domain sap_tierra --query "explain pattern"`
  - **Expected**: Response uses KB context

#### 4.1.3 Timeout & Error Handling
- **Case**: Graceful handling of Ollama connection issues
- **Sub-Case 3a**: Timeout handling with OLLAMA_TIMEOUT_SECS
  - Set very low timeout: `set OLLAMA_TIMEOUT_SECS=1`
  - Execute chat with slow model
  - **Expected**: Timeout error (not hanging)

- **Sub-Case 3b**: Connection refused handling
  - Stop Ollama service
  - Execute: `python ollama_chat.py --query "test"`
  - **Expected**: Clear error message, not crash

- **Sub-Case 3c**: Invalid model handling
  - Execute: `python ollama_chat.py --model nonexistent_model_xyz`
  - **Expected**: Error message about missing model

---

## 5. DASHBOARD MONITORING

### 5.1 Dashboard Server Configuration
**Use Case**: Web dashboard monitors Motor-Fusion state

#### 5.1.1 Port Configuration
- **Case**: Dashboard uses configured port
- **Sub-Case 1a**: Default port from environment
  - Set: `set DASHBOARD_PORT=7070`
  - Start: `python -m dashboard.server`
  - Verify: `curl http://localhost:7070/`
  - **Expected**: Dashboard loads successfully

- **Sub-Case 1b**: Environment variable overrides default
  - Set: `set DASHBOARD_PORT=9999`
  - Start: `python -m dashboard.server`
  - Verify: `curl http://localhost:9999/`
  - **Expected**: Dashboard on port 9999

- **Sub-Case 1c**: CLI argument overrides environment
  - Set: `set DASHBOARD_PORT=8888`
  - Start: `python -m dashboard.server 7070`
  - Verify: `curl http://localhost:7070/`
  - **Expected**: Dashboard on port 7070 (CLI wins)

#### 5.1.2 Status API
- **Case**: Dashboard API returns system status
- **Sub-Case 2a**: /api/status endpoint
  - Execute: `curl http://localhost:7070/api/status`
  - **Expected**: Returns JSON with motor status

- **Sub-Case 2b**: Motor active detection
  - Response contains motor_activo field
  - After activity: should be true
  - After inactivity: should be false
  - **Expected**: Correct active status

- **Sub-Case 2c**: KB statistics
  - Response contains kb.dominios and kb.total_entradas
  - After ingesting data: values increase
  - **Expected**: KB stats updated

- **Sub-Case 2d**: Hooks registration detection
  - If hooks registered: hooks_registrados = true
  - **Expected**: Correct hooks detection

#### 5.1.3 Web Interface
- **Case**: Dashboard UI displays information
- **Sub-Case 3a**: HTML loads without errors
  - Open: http://localhost:7070/
  - Check browser console for errors
  - **Expected**: No JavaScript errors

- **Sub-Case 3b**: Status displays update
  - Load page, trigger motor activity
  - Refresh page
  - **Expected**: Updated timestamps and stats

- **Sub-Case 3c**: Error logs display
  - Check for error messages in dashboard
  - **Expected**: Errors visible if present

---

## 6. CLAUDE CLI INTEGRATION

### 6.1 MCP Server Configuration
**Use Case**: Claude CLI accesses Motor knowledge via MCP protocol

#### 6.1.1 MCP Server Startup
- **Case**: MCP server initializes correctly
- **Sub-Case 1a**: Server starts without errors
  - Execute: `python mcp_kb_server.py`
  - Wait for initialization
  - **Expected**: No errors, server ready for connections

- **Sub-Case 1b**: MCP loads configuration from environment
  - Verify: Server uses correct KB paths from config
  - **Expected**: Correct DATA_DIR and KNOWLEDGE_DIR used

- **Sub-Case 1c**: Server accepts connections
  - Start server in background
  - Execute MCP client test
  - **Expected**: Connection successful

#### 6.1.2 MCP Tools Availability
- **Case**: MCP exposes correct tools to Claude CLI
- **Sub-Case 2a**: search_knowledge tool available
  - Query: `search_knowledge "pattern"`
  - **Expected**: Tool executes, returns results

- **Sub-Case 2b**: cross_domain_search tool available
  - Query: `cross_domain_search "term"`
  - **Expected**: Tool executes

- **Sub-Case 2c**: export_context tool available
  - Query: `export_context "Edit"`
  - **Expected**: Tool returns KB context

#### 6.1.3 Claude CLI Hook Integration
- **Case**: Claude CLI hooks connect to Motor-Fusion
- **Sub-Case 3a**: SessionStart hook loads KB context
  - Trigger: New Claude CLI session
  - Verify: Hook executes, loads KB
  - **Expected**: Session has KB context available

- **Sub-Case 3b**: PostToolUse hook learns from actions
  - Trigger: Execute tool via Claude CLI
  - Verify: Hook logs and learns
  - **Expected**: Learning recorded in motor

- **Sub-Case 3c**: UserPromptSubmit hook classifies message
  - Trigger: User submits message
  - Verify: Hook classifies domain
  - **Expected**: Message classified correctly

---

## 7. LEARNING & MEMORY

### 7.1 Learning Memory Operations
**Use Case**: Motor learns from successful patterns

#### 7.1.1 Pattern Learning
- **Case**: Successful patterns are recorded
- **Sub-Case 1a**: Record successful pattern execution
  - Execute action with success
  - Verify: Pattern recorded in learned_patterns.json
  - **Expected**: Pattern added with high confidence

- **Sub-Case 1b**: Pattern reuse ranking
  - Record multiple successful uses
  - Verify: Confidence score increases
  - **Expected**: Confidence >= initial threshold

- **Sub-Case 1c**: Pattern failure handling
  - Record failed pattern execution
  - Verify: Confidence decreases
  - **Expected**: Confidence < initial, pattern less preferred

#### 7.1.2 Memory Consolidation
- **Case**: Similar patterns are consolidated
- **Sub-Case 2a**: Consolidation enabled when configured
  - Set: CONSOLIDATION_ENABLED=true, CONSOLIDATION_SIMILARITY_THRESHOLD=0.7
  - Create similar patterns
  - **Expected**: Similar patterns consolidated into one

- **Sub-Case 2b**: Consolidation respects threshold
  - Set: CONSOLIDATION_SIMILARITY_THRESHOLD=0.9 (high)
  - Create moderately similar patterns
  - **Expected**: Patterns NOT consolidated (below threshold)

#### 7.1.3 Auto-Pruning
- **Case**: Low-value patterns are automatically removed
- **Sub-Case 3a**: Prune patterns with low success rate
  - Set: AUTO_PRUNE_ENABLED=true, AUTO_PRUNE_MIN_SUCCESS_RATE=0.5
  - Create failing pattern
  - **Expected**: Pattern removed after threshold

- **Sub-Case 3b**: Prune unused patterns
  - Set: AUTO_PRUNE_DAYS_UNUSED=1
  - Create pattern, don't use for 1+ days
  - **Expected**: Pattern removed

- **Sub-Case 3c**: Preserve successful patterns
  - Create successful pattern
  - **Expected**: Pattern NOT pruned

---

## 8. GIT SYNCHRONIZATION

### 8.1 Git Integration
**Use Case**: Motor-Fusion syncs knowledge with GitHub repository

#### 8.1.1 Git Status Checking
- **Case**: Check current git state
- **Sub-Case 1a**: Verify motor-fusion repo structure
  - Execute: `git status`
  - **Expected**: Working directory clean (or expected changes)

- **Sub-Case 1b**: Check remotes configured
  - Execute: `git remote -v`
  - **Expected**: origin points to Motor-Fusion GitHub

- **Sub-Case 1c**: Verify branch
  - Execute: `git branch --show-current`
  - **Expected**: On main or development branch

#### 8.1.2 Knowledge Sync
- **Case**: Knowledge changes sync to GitHub
- **Sub-Case 2a**: Add new knowledge locally
  - Ingest new patterns/facts
  - Execute: `python sync_to_github.py --test`
  - **Expected**: Shows what would be synced

- **Sub-Case 2b**: Commit knowledge changes
  - Execute: `python sync_to_github.py --commit`
  - Verify: `git log -1`
  - **Expected**: New commit created

- **Sub-Case 2c**: Push to remote
  - Execute: `git push origin main`
  - **Expected**: Push successful (if authorized)

#### 8.1.3 Knowledge Restore
- **Case**: Restore knowledge from GitHub
- **Sub-Case 3a**: List available knowledge backup
  - Execute: `python restore_from_github.py --list`
  - **Expected**: Lists knowledge domains in repo

- **Sub-Case 3b**: Restore specific domain
  - Execute: `python restore_from_github.py --domain sap_tierra`
  - Verify: Domain populated from GitHub version
  - **Expected**: Domain restored successfully

---

## 9. HOOKS & AUTOMATION

### 9.1 Hook System
**Use Case**: Hooks automate learning and integration

#### 9.1.1 Hook Registration
- **Case**: Hooks are registered with Claude CLI
- **Sub-Case 1a**: SessionStart hook registered
  - Check settings.json for hook entries
  - **Expected**: SessionStart hook configured

- **Sub-Case 1b**: PostToolUse hook registered
  - **Expected**: PostToolUse hook configured

- **Sub-Case 1c**: UserPromptSubmit hook registered
  - **Expected**: UserPromptSubmit hook configured

#### 9.1.2 Hook Execution
- **Case**: Hooks execute when triggered
- **Sub-Case 2a**: SessionStart hook triggers on session begin
  - Start Claude CLI session
  - Check hook_debug.log for execution
  - **Expected**: Hook executed successfully

- **Sub-Case 2b**: PostToolUse hook triggers after tool use
  - Execute tool in Claude CLI
  - Check hook_debug.log
  - **Expected**: Hook executed and learned from action

- **Sub-Case 2c**: Hook errors are logged
  - Trigger hook with error condition
  - Check hook_debug.log
  - **Expected**: Error logged clearly

#### 9.1.3 Hook Context
- **Case**: Hooks have access to Motor knowledge
- **Sub-Case 3a**: SessionStart hook injects KB context
  - Ingest test patterns
  - Start new session
  - Verify KB context available in session
  - **Expected**: Context successfully injected

- **Sub-Case 3b**: PostToolUse hook has tool result context
  - Execute tool, capture result
  - Verify hook has access to result
  - **Expected**: Learning includes result data

---

## 10. END-TO-END WORKFLOWS

### 10.1 Complete Knowledge Lifecycle
**Use Case**: From ingestion to Claude CLI usage

#### 10.1.1 Complete Workflow
- **Case**: Knowledge flows through entire system
  - **Step 1**: Ingest new SAP domain knowledge
    - Execute: `python ingest_knowledge.py sap_patterns.txt --domain sap_tierra`
    - **Expected**: Knowledge stored

  - **Step 2**: Verify in KB search
    - Execute: `python -c "from core.knowledge_base import search; print(search('sap'))"`
    - **Expected**: Knowledge found

  - **Step 3**: Verify in dashboard
    - Open: http://localhost:7070/api/status
    - **Expected**: KB stats updated

  - **Step 4**: Use in Claude CLI via MCP
    - Query: `search_knowledge "sap"`
    - **Expected**: Knowledge accessible

  - **Step 5**: Record learning
    - Use pattern successfully
    - **Expected**: Pattern confidence increases

  - **Step 6**: Sync to GitHub
    - Execute: `python sync_to_github.py --commit`
    - **Expected**: Changes persisted to repo

#### 10.1.2 Multi-User Scenario
- **Case**: Multiple users accessing Motor simultaneously
- **Sub-Case 2a**: Concurrent reads don't conflict
  - Simulate: Multiple search queries simultaneously
  - **Expected**: All queries complete successfully

- **Sub-Case 2b**: Write locking prevents corruption
  - Simulate: Ingest while searching
  - **Expected**: Operations don't corrupt KB

- **Sub-Case 2c**: Learning doesn't conflict
  - Simulate: Multiple users logging learning
  - **Expected**: All learning recorded correctly

---

## TEST EXECUTION PROTOCOL

### Phase 1: Configuration Validation
1. Verify .env file exists and is readable
2. Test environment variable loading
3. Validate all required variables are set
4. **Success Criteria**: All configuration tests pass

### Phase 2: Core Systems
1. Test knowledge ingestion
2. Test knowledge search
3. Test Ollama integration
4. **Success Criteria**: All core tests pass

### Phase 3: Monitoring & Integration
1. Test dashboard
2. Test MCP server
3. Test hooks (if Claude CLI available)
4. **Success Criteria**: All monitoring tests pass

### Phase 4: Advanced Features
1. Test learning & memory
2. Test git sync
3. Test end-to-end workflows
4. **Success Criteria**: All advanced tests pass

### Phase 5: Regression Testing
1. Re-run all Phase 1-4 tests
2. Verify no regressions
3. Document any new issues
4. **Success Criteria**: All tests pass (0 failures)

---

## TEST RESULTS TEMPLATE

```
TEST PLAN EXECUTION REPORT
=========================
Date: [YYYY-MM-DD HH:MM]
Tester: [Name]
Motor-Fusion Version: 1.0.0-fusion
Environment: [Windows 11 / Linux / macOS]

CONFIGURATION & ENVIRONMENT:
  1.1.1 .env File Presence: [PASS/FAIL]
  1.1.2 Variable Loading: [PASS/FAIL]
  1.1.3 Data Directory: [PASS/FAIL]

KNOWLEDGE BASE:
  2.1.1 Pattern Ingestion: [PASS/FAIL]
  2.1.2 File Types: [PASS/FAIL]
  2.1.3 Domain Management: [PASS/FAIL]
  3.1.1 Single Domain Search: [PASS/FAIL]
  3.1.2 Cross-Domain Search: [PASS/FAIL]
  3.1.3 Context Export: [PASS/FAIL]

OLLAMA:
  4.1.1 Configuration: [PASS/FAIL]
  4.1.2 Connection: [PASS/FAIL]
  4.1.3 Error Handling: [PASS/FAIL]

DASHBOARD:
  5.1.1 Port Configuration: [PASS/FAIL]
  5.1.2 Status API: [PASS/FAIL]
  5.1.3 Web Interface: [PASS/FAIL]

CLAUDE CLI:
  6.1.1 MCP Server: [PASS/FAIL]
  6.1.2 MCP Tools: [PASS/FAIL]
  6.1.3 Hook Integration: [PASS/FAIL]

LEARNING & MEMORY:
  7.1.1 Pattern Learning: [PASS/FAIL]
  7.1.2 Memory Consolidation: [PASS/FAIL]
  7.1.3 Auto-Pruning: [PASS/FAIL]

GIT SYNC:
  8.1.1 Git Status: [PASS/FAIL]
  8.1.2 Knowledge Sync: [PASS/FAIL]
  8.1.3 Knowledge Restore: [PASS/FAIL]

HOOKS:
  9.1.1 Hook Registration: [PASS/FAIL]
  9.1.2 Hook Execution: [PASS/FAIL]
  9.1.3 Hook Context: [PASS/FAIL]

END-TO-END:
  10.1.1 Complete Lifecycle: [PASS/FAIL]
  10.1.2 Multi-User: [PASS/FAIL]

OVERALL RESULT: [PASS/FAIL]
Total Tests: [N]
Passed: [N]
Failed: [N]

ISSUES FOUND:
[List of any failures with reproduction steps]

NOTES:
[Any relevant observations]
```

---

## NEXT STEPS

1. Execute test plan following this document
2. Record all results in TEST_RESULTS.md
3. For each failure: Create bug report with reproduction steps
4. Fix all issues
5. Re-run test plan until 0 failures achieved
6. Final sign-off on Motor-Fusion readiness for production
