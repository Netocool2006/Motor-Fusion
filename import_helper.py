#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
import_helper.py - Helper para importar archivos Markdown a NotebookLM
Abre cada archivo y lo copia al portapapeles para paste directo
"""

import sys
import io
import os

# Arreglar encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from pathlib import Path
import pyperclip
import webbrowser
import time
import json

MARKDOWN_DIR = Path(__file__).resolve().parent / "core" / "markdown_exports"
NOTEBOOK_ID = os.environ.get("NOTEBOOKLM_NOTEBOOK_ID", "")
NOTEBOOKLM_URL = f"https://notebooklm.google.com/notebook/{NOTEBOOK_ID}" if NOTEBOOK_ID else ""

class ImportHelper:
    def __init__(self):
        self.files = sorted(MARKDOWN_DIR.glob("*.md"))
        self.import_log = []

    def display_menu(self):
        """Muestra menú de opciones"""
        os.system('cls' if os.name == 'nt' else 'clear')

        print("\n" + "="*70)
        print("IMPORTADOR DE KNOWLEDGE BASE → NOTEBOOKLM")
        print("="*70)
        print(f"\nNotebook ID: {NOTEBOOK_ID}")
        print(f"URL: {NOTEBOOKLM_URL}\n")
        print("Archivos listos para importar:\n")

        for i, file in enumerate(self.files, 1):
            size = file.stat().st_size
            print(f"  {i}. {file.name:<40} ({size/1024:.1f} KB)")

        print(f"\n  {len(self.files) + 1}. Abrir NotebookLM en navegador")
        print(f"  {len(self.files) + 2}. Salir")
        print("\n" + "="*70)
        print("Selecciona un número para copiar el contenido al portapapeles")
        print("Luego pégalo en NotebookLM usando: Ctrl+V")
        print("="*70 + "\n")

    def copy_file_to_clipboard(self, file_path):
        """Copia contenido de archivo al portapapeles"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            pyperclip.copy(content)

            print(f"\n✓ CONTENIDO COPIADO AL PORTAPAPELES")
            print(f"  Archivo: {file_path.name}")
            print(f"  Tamaño: {len(content)} caracteres")
            print(f"\nAhora:")
            print(f"  1. Ve a: {NOTEBOOKLM_URL}")
            print(f"  2. Click en '+Add source' / '+Agregar fuente'")
            print(f"  3. Selecciona 'Paste text' / 'Pegar texto'")
            print(f"  4. Pega el contenido: Ctrl+V")
            print(f"  5. Click en 'Add source' / 'Agregar'")
            print(f"  6. Espera a que NotebookLM procese")

            self.import_log.append({
                "file": file_path.name,
                "timestamp": str(time.time()),
                "status": "copied_to_clipboard"
            })

            return True

        except Exception as e:
            print(f"\n✗ Error: {e}")
            return False

    def open_notebooklm(self):
        """Abre NotebookLM en navegador"""
        try:
            print(f"\nAbriendo: {NOTEBOOKLM_URL}")
            webbrowser.open(NOTEBOOKLM_URL)
            time.sleep(2)
            print("✓ NotebookLM abierto en navegador")
        except Exception as e:
            print(f"✗ Error abriendo navegador: {e}")
            print(f"  Abre manualmente: {NOTEBOOKLM_URL}")

    def run_interactive(self):
        """Modo interactivo"""
        while True:
            self.display_menu()

            try:
                choice = input("Selecciona opción (número): ").strip()

                if choice == str(len(self.files) + 1):
                    self.open_notebooklm()
                    continue

                elif choice == str(len(self.files) + 2):
                    print("\n✓ Hasta luego!")
                    break

                elif choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(self.files):
                        file = self.files[idx]
                        self.copy_file_to_clipboard(file)
                        input("\n(Presiona ENTER cuando termines en NotebookLM)")
                    else:
                        print("✗ Opción inválida")
                else:
                    print("✗ Opción inválida")

            except KeyboardInterrupt:
                print("\n\n✓ Importación cancelada")
                break
            except Exception as e:
                print(f"\n✗ Error: {e}")

    def run_auto_mode(self):
        """Modo automático - abre NotebookLM y guía al usuario"""
        print("\n" + "="*70)
        print("MODO AUTOMÁTICO - IMPORTAR TODO")
        print("="*70)

        print(f"\nAbriendo NotebookLM...")
        self.open_notebooklm()

        for i, file in enumerate(self.files, 1):
            print(f"\n[{i}/{len(self.files)}] {file.name}")
            print("-" * 70)

            self.copy_file_to_clipboard(file)

            if i < len(self.files):
                input("\nPresiona ENTER cuando hayas agregado esta fuente a NotebookLM...")

        print("\n✓ ¡IMPORTACIÓN COMPLETADA!")
        print("Todos tus archivos están en NotebookLM")

if __name__ == "__main__":
    helper = ImportHelper()

    if len(sys.argv) > 1 and sys.argv[1] == '--auto':
        helper.run_auto_mode()
    else:
        helper.run_interactive()
