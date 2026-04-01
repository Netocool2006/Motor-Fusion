@echo off
REM kb_search.cmd - Comando para buscar en KB
REM Uso: kb_search "tu pregunta"

cd C:\Hooks_IA
python kb_search_cli.py %*
