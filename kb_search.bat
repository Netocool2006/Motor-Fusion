@echo off
REM kb_search.bat - Comando rápido para buscar en KB desde cmd
REM 
REM USO DESDE CMD:
REM   kb_search "tu pregunta"
REM
REM EJEMPLO:
REM   kb_search "¿Qué es un catálogo?"

python C:\Hooks_IA\kb_search_cli.py %*
