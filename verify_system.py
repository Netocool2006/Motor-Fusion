#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verify_system.py - Script de verificacion del sistema Motor_IA
Ejecutar con: python C:\Hooks_IA\verify_system.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

def check_config():
    """Verifica que config.py exista y este bien"""
    print("\n" + "="*70)
    print("VERIFICACION 1: Config.py")
    print("="*70)
    
    try:
        from config import (
            PROJECT_ROOT, HOOKS_DIR, CORE_DIR, KNOWLEDGE_DIR,
            SESSION_HISTORY_FILE, KB_ENFORCER_LOG
        )
        print("[OK] config.py importado correctamente")
        print("  PROJECT_ROOT: {}".format(PROJECT_ROOT))
        print("  HOOKS_DIR: {}".format(HOOKS_DIR))
        print("  KB_ENFORCER_LOG: {}".format(KB_ENFORCER_LOG))
        return True
    except Exception as e:
        print("[ERROR] config.py: {}".format(e))
        return False

def check_kb_structure():
    """Verifica que la estructura de KB exista"""
    print("\n" + "="*70)
    print("VERIFICACION 2: Estructura de Knowledge Base")
    print("="*70)
    
    from config import KNOWLEDGE_DIR
    
    kb_dirs = list(KNOWLEDGE_DIR.glob("*/"))
    if kb_dirs:
        print("[OK] Directorios de KB encontrados: {}".format(len(kb_dirs)))
        for domain_dir in sorted(kb_dirs)[:5]:
            fact_file = domain_dir / "facts.json"
            if fact_file.exists():
                try:
                    with open(fact_file, encoding='utf-8') as f:
                        data = json.load(f)
                        count = len(data.get('facts', []))
                        print("  [OK] {}: {} facts".format(domain_dir.name, count))
                except:
                    print("  [ERROR] {}: error reading".format(domain_dir.name))
            else:
                print("  [-] {}: sin facts.json".format(domain_dir.name))
        return True
    else:
        print("[ERROR] No se encontraron directorios de KB")
        return False

def check_hooks():
    """Verifica que los hooks existan"""
    print("\n" + "="*70)
    print("VERIFICACION 3: Hooks")
    print("="*70)
    
    from config import HOOKS_DIR
    
    hooks = [
        "kb_enforcer_hook.py",
        "response_validator_hook.py",
        "session_end.py"
    ]
    
    for hook in hooks:
        hook_file = HOOKS_DIR / hook
        if hook_file.exists():
            print("[OK] {} existe".format(hook))
        else:
            print("[ERROR] {} NO ENCONTRADO".format(hook))
    
    return True

def check_logs():
    """Verifica estado de logs"""
    print("\n" + "="*70)
    print("VERIFICACION 4: Logs y Datos")
    print("="*70)
    
    from config import KB_ENFORCER_LOG, DATA_DIR
    
    if KB_ENFORCER_LOG.exists():
        try:
            with open(KB_ENFORCER_LOG, encoding='utf-8') as f:
                lines = f.readlines()
            print("[OK] kb_enforcer.log existe ({} lineas)".format(len(lines)))
            if lines:
                last = json.loads(lines[-1])
                print("  Ultima ejecucion: {}".format(last.get('timestamp')))
                print("  Query: {}...".format(last.get('query')[:50]))
                print("  KB%: {}%".format(last.get('kb_pct')))
        except Exception as e:
            print("  Error leyendo log: {}".format(e))
    else:
        print("[-] kb_enforcer.log no existe (normal si es primera ejecucion)")
    
    if DATA_DIR.exists():
        print("[OK] DATA_DIR existe: {}".format(DATA_DIR))
    
    return True

def test_kb_search():
    """Test real de busqueda en KB"""
    print("\n" + "="*70)
    print("VERIFICACION 5: Test de Busqueda Real en KB")
    print("="*70)
    
    try:
        from core.kb_response_engine import process_query_with_kb
        
        test_query = "Que es un catalogo?"
        print("\nTest query: {}".format(test_query))
        
        result = process_query_with_kb(test_query)
        
        print("[OK] Busqueda ejecutada exitosamente")
        print("  KB%: {}%".format(result.get('kb_pct')))
        print("  Internet%: {}%".format(result.get('internet_pct')))
        print("  ML%: {}%".format(result.get('ml_pct')))
        print("  Dominio: {}".format(result.get('domain')))
        print("  KB Entries Found: {}".format(result.get('kb_found')))
        
        footer = result.get('sources_footer', '')
        print("\nReporte de fuentes (OBLIGATORIO):")
        print("  {}".format(footer))
        
        return True
    except Exception as e:
        print("[ERROR] en busqueda: {}".format(e))
        import traceback
        traceback.print_exc()
        return False

def check_settings():
    """Verifica que hooks esten registrados en settings.json"""
    print("\n" + "="*70)
    print("VERIFICACION 6: Hooks Registrados en settings.json")
    print("="*70)
    
    from config import SETTINGS_JSON
    
    if SETTINGS_JSON.exists():
        try:
            with open(SETTINGS_JSON, encoding='utf-8') as f:
                settings = json.load(f)
            
            hooks = settings.get('hooks', {})
            print("[OK] settings.json encontrado")
            print("  Hooks registrados:")
            for hook_type, hook_list in hooks.items():
                print("    {}: {} hook(s)".format(hook_type, len(hook_list)))
                for h in hook_list:
                    print("      - {}".format(h.get('path', 'unknown')))
            
            return True
        except Exception as e:
            print("[ERROR] leyendo settings.json: {}".format(e))
            return False
    else:
        print("[ERROR] settings.json NO ENCONTRADO en {}".format(SETTINGS_JSON))
        return False

def main():
    print("\n" + "="*70)
    print("  VERIFICACION DEL SISTEMA MOTOR_IA")
    print("="*70)
    print("Timestamp: {}".format(datetime.now().strftime('%d-%m-%Y %H:%M:%S')))
    
    checks = [
        check_config,
        check_kb_structure,
        check_hooks,
        check_logs,
        test_kb_search,
        check_settings
    ]
    
    results = []
    for check in checks:
        try:
            results.append(check())
        except Exception as e:
            print("\n[ERROR] ejecutando verificacion: {}".format(e))
            results.append(False)
    
    print("\n" + "="*70)
    print("RESUMEN")
    print("="*70)
    passed = sum(results)
    total = len(results)
    print("Verificaciones pasadas: {}/{}".format(passed, total))
    
    if passed == total:
        print("\n[OK] SISTEMA MOTOR_IA LISTO - Todos los tests pasaron")
        print("\nProximo paso: Abre nueva sesion CLI y haz una pregunta para")
        print("que los hooks se ejecuten automaticamente")
    else:
        print("\n[ERROR] Algunos tests fallaron - revisar errores arriba")
    
    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    main()
