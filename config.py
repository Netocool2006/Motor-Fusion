#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
config.py - Centralized configuration for Hooks_IA
All paths use environment variables for portability
No hardcoded paths - everything is portable
"""

import os
from pathlib import Path

# Base directories - find actual user profile (robust approach)
HOME = os.path.expanduser('~')
if 'AppData' in HOME:
    # In Claude Code, expanduser might return incorrect path
    # Search for actual user directory
    USERPROFILE = Path(HOME).parents[2]  # Go up to actual user folder
else:
    USERPROFILE = Path(HOME)

APPDATA_LOCAL = USERPROFILE / 'AppData' / 'Local'

# Project paths
PROJECT_ROOT = Path(__file__).parent.absolute()
HOOKS_DIR = PROJECT_ROOT / 'hooks'
CORE_DIR = PROJECT_ROOT / 'core'
KNOWLEDGE_DIR = PROJECT_ROOT / 'knowledge'
DASHBOARD_DIR = PROJECT_ROOT / 'dashboard'

# Claude Code paths - use environment variable if available
CLAUDE_CODE_DIR_ENV = os.environ.get('CLAUDE_CODE_DIR')
CLAUDE_PROJECTS_ENV = os.environ.get('CLAUDE_PROJECTS_DIR')

if CLAUDE_CODE_DIR_ENV:
    CLAUDE_CODE_DIR = Path(CLAUDE_CODE_DIR_ENV)
else:
    CLAUDE_CODE_DIR = Path.home() / '.claude'

if CLAUDE_PROJECTS_ENV:
    PROJECTS_DIR = Path(CLAUDE_PROJECTS_ENV)
else:
    PROJECTS_DIR = CLAUDE_CODE_DIR / 'projects'

# Log files
LOG_DIR = CORE_DIR
KB_ENFORCER_LOG = LOG_DIR / 'kb_enforcer.log'
KB_RESPONSES_LOG = LOG_DIR / 'kb_responses.log'
RESPONSE_VALIDATION_LOG = LOG_DIR / 'response_validation.log'

# Reports
MANDATORY_SOURCES_REPORT = CORE_DIR / 'MANDATORY_SOURCES_REPORT.txt'
RESPONSE_VALIDATION_ERROR = CORE_DIR / 'RESPONSE_VALIDATION_ERROR.txt'

# Settings
SETTINGS_JSON = CLAUDE_CODE_DIR / 'settings.json'

# Session history and learning data
DATA_DIR = CORE_DIR / 'data'
SESSION_HISTORY_FILE = DATA_DIR / 'session_history.json'
CO_OCCUR_FILE = DATA_DIR / 'domain_cooccurrence.json'
MARKOV_FILE = DATA_DIR / 'domain_markov.json'
INJECTION_FILE = DATA_DIR / 'injection_patterns.json'
HINT_EFFECT_FILE = DATA_DIR / 'hint_effects.json'
DEBUG_LOG = CORE_DIR / 'debug.log'
ACTIONS_LOG = CORE_DIR / 'actions.log'
LAST_MSG_FILE = CORE_DIR / 'last_message.txt'

# Session start/end hook state
STATE_FILE = CORE_DIR / 'hook_state.json'
HOOK_STATE_DIR = CORE_DIR / 'hook_state'
RECENT_HOURS = 1  # Cuantas horas atras buscar sesiones recientes

# Learning memory and execution log
MEMORY_FILE = DATA_DIR / 'learning_memory.json'
EXECUTION_LOG = DATA_DIR / 'execution_log.json'
ATTEMPTS_FILE = DATA_DIR / 'attempts.json'
PENDING_ERRORS_FILE = DATA_DIR / 'pending_errors.json'
LOCK_DIR = CORE_DIR / 'locks'
DEDUP_WINDOW_SECS = 60
ERROR_CORRELATION_WINDOW = 600
CONFIDENCE_THRESHOLD = 0.5
MAX_PENDING_ERRORS = 20

# Domain detection
DOMAINS_FILE = KNOWLEDGE_DIR / 'domains.json'
AUTO_ASSIGN_THRESHOLD = 0.7
SUGGEST_THRESHOLD = 0.4
AUTO_DOMAIN_MIN_SESSIONS = 3
AUTO_DOMAIN_MIN_MSGS = 10
DOMAIN_SESSIONS_COUNTER_FILE = DATA_DIR / 'domain_sessions_counter.json'

# Episodic index
EPISODIC_DB = DATA_DIR / 'episodic_index.db'

# Iteration learn
ITERATION_GAP_SECS = 300
MSG_TYPE_FILE = CORE_DIR / 'msg_type.json'
NOTIFY_FILE = CORE_DIR / 'notify.json'
FINGERPRINTS_FILE = DATA_DIR / 'fingerprints.json'
FAILURES_FILE = DATA_DIR / 'failures.json'
EXPLORE_THRESHOLD = 3

# Working memory
WORKING_MEMORY_MAX_ITEMS = 50
WORKING_MEMORY_TTL_HOURS = 24

# Hint tracker
HINT_EFFECTIVENESS_DECAY = 0.95

# SAP playbook
SAP_PLAYBOOK_DB = DATA_DIR / 'sap_playbook.db'
CONFIDENCE_DECAY_DAYS = 30
CONFIDENCE_DECAY_RATE = 0.1

# Feature flags (new features)
GRAPH_DB_ENABLED = True
CLOUD_SYNC_ENABLED = True
KB_BENCHMARK_ENABLED = True
TOKEN_BUDGET_ENABLED = True
TOKEN_BUDGET_MAX = 2000  # max tokens to inject
DASHBOARD_METRICS_ENABLED = True
PASSIVE_CAPTURE_ENABLED = True
SMART_FILE_ROUTING_ENABLED = True
KB_VERSIONING_ENABLED = True
# MULTI_AGENT_ENABLED removed (module deleted)
ASYNC_MEMORY_ENABLED = True

# Graph DB
GRAPH_FILE = DATA_DIR / 'domain_graph.json'

# Cloud sync
SYNC_STATE_FILE = DATA_DIR / 'cloud_sync_state.json'
SYNC_QUEUE_FILE = DATA_DIR / 'cloud_sync_queue.json'
AUTO_SYNC_INTERVAL = 300  # seconds between auto-syncs

# Benchmark
BENCHMARK_FILE = DATA_DIR / 'kb_benchmark_results.json'

# Token budget metrics
TOKEN_METRICS_FILE = DATA_DIR / 'token_budget_metrics.json'

# Dashboard metrics cache
DASHBOARD_METRICS_CACHE = DATA_DIR / 'dashboard_metrics_cache.json'

# Passive capture
PASSIVE_DB_FILE = DATA_DIR / 'passive_captures.json'
FILE_COOCCURRENCE_FILE = DATA_DIR / 'file_cooccurrence.json'

# Smart file routing
ROUTING_DB_FILE = DATA_DIR / 'file_routing.json'

# KB versioning
VERSION_LOG_FILE = DATA_DIR / 'kb_version_log.json'

# Multi-agent (removed - module deleted)

# Async memory
ASYNC_QUEUE_FILE = DATA_DIR / 'async_memory_queue.json'
ASYNC_METRICS_FILE = DATA_DIR / 'async_memory_metrics.json'

# Semantic search (Feature 11)
SEMANTIC_SEARCH_ENABLED = True
EMBEDDINGS_CACHE_FILE = DATA_DIR / 'embeddings_cache.json'
SEMANTIC_METRICS_FILE = DATA_DIR / 'semantic_metrics.json'
SEMANTIC_MODEL = 'all-MiniLM-L6-v2'

# Memory tiers (Feature 12)
MEMORY_TIERS_ENABLED = True
TIERS_FILE = DATA_DIR / 'memory_tiers.json'
TIER_METRICS_FILE = DATA_DIR / 'memory_tier_metrics.json'

# Session harvest (Feature 13)
SESSION_HARVEST_ENABLED = True
HARVEST_FILE = DATA_DIR / 'session_harvest_results.json'
HARVEST_METRICS_FILE = DATA_DIR / 'session_harvest_metrics.json'

# KB REST API (removed - module deleted, MCP server replaces it)

# Typed graph (Feature 15)
TYPED_GRAPH_ENABLED = True
TYPED_GRAPH_FILE = DATA_DIR / 'typed_graph.json'
TYPED_GRAPH_METRICS = DATA_DIR / 'typed_graph_metrics.json'

# Memory pruner
AUTO_PRUNE_ENABLED = True
AUTO_PRUNE_MIN_SUCCESS_RATE = 0.3
AUTO_PRUNE_DAYS_UNUSED = 30
AUTO_PRUNE_MIN_REUSES = 2

# Memory consolidator
CONSOLIDATION_ENABLED = True
CONSOLIDATION_MIN_PATTERNS = 3
CONSOLIDATION_SIMILARITY_THRESHOLD = 0.8

# Helper function to ensure directories exist
def ensure_dirs():
    """Create necessary directories if they don't exist"""
    for directory in [LOG_DIR, KNOWLEDGE_DIR, CORE_DIR, HOOKS_DIR, DASHBOARD_DIR, DATA_DIR]:
        directory.mkdir(parents=True, exist_ok=True)

# Print configuration (for debugging)
if __name__ == '__main__':
    ensure_dirs()
    print("=" * 70)
    print("HOOKS_IA CONFIGURATION")
    print("=" * 70)
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Knowledge Dir: {KNOWLEDGE_DIR}")
    print(f"Settings: {SETTINGS_JSON}")
    print("=" * 70)
