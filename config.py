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
CLAUDE_PROJECTS_ENV = os.environ.get('CLAUDE_PROJECTS_DIR')
if CLAUDE_PROJECTS_ENV:
    PROJECTS_DIR = Path(CLAUDE_PROJECTS_ENV)
else:
    CLAUDE_CODE_DIR = APPDATA_LOCAL / 'ClaudeCode' / '.claude'
    PROJECTS_DIR = CLAUDE_CODE_DIR / 'projects'

# Find the C--chance1 project directory (case-insensitive)
CHANCE_PROJECT_DIR = None
if PROJECTS_DIR.exists():
    for project_dir in PROJECTS_DIR.iterdir():
        if project_dir.is_dir() and project_dir.name.lower() == 'c--chance1':
            CHANCE_PROJECT_DIR = project_dir
            break

if not CHANCE_PROJECT_DIR:
    CHANCE_PROJECT_DIR = PROJECTS_DIR / 'C--chance1'

# Log files
LOG_DIR = CORE_DIR
KB_ENFORCER_LOG = LOG_DIR / 'kb_enforcer.log'
KB_RESPONSES_LOG = LOG_DIR / 'kb_responses.log'
RESPONSE_VALIDATION_LOG = LOG_DIR / 'response_validation.log'

# Reports
MANDATORY_SOURCES_REPORT = CORE_DIR / 'MANDATORY_SOURCES_REPORT.txt'
RESPONSE_VALIDATION_ERROR = CORE_DIR / 'RESPONSE_VALIDATION_ERROR.txt'

# Mandatory protocol
MANDATORY_PROTOCOL = PROJECT_ROOT / 'MANDATORY_PROTOCOL.txt'

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
    print(f"Claude Project: {CHANCE_PROJECT_DIR}")
    print(f"Settings: {SETTINGS_JSON}")
    print("=" * 70)
