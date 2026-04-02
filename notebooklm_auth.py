#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
notebooklm_auth.py - Configurar autenticación OAuth2 para NotebookLM
Se ejecuta UNA SOLA VEZ para autorizar acceso local

IMPORTANTE: Esto NO requiere compartir credenciales
Se guardan LOCALMENTE en tu máquina en .credentials/
"""

import os
import json
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle

# Configuración
CREDENTIALS_DIR = Path(__file__).parent / ".credentials"
TOKEN_FILE = CREDENTIALS_DIR / "notebooklm_token.pickle"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"

# Scopes necesarios para NotebookLM
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file'
]

def setup_credentials():
    """
    Configura OAuth2 localmente
    Se ejecuta UNA sola vez
    """

    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "="*70)
    print("CONFIGURACION OAUTH2 - NotebookLM")
    print("="*70)

    print("\nPASO 1: Descargar credentials.json")
    print("-" * 70)
    print("""
    1. Ir a: https://console.cloud.google.com/
    2. Crear nuevo proyecto: "Motor_IA"
    3. Habilitar API:
       - Google Drive API
       - Google Sheets API (para NotebookLM)
    4. Crear "OAuth 2.0 Client ID":
       - Tipo: Aplicación de escritorio
    5. Descargar JSON
    6. Guardar en: {CREDENTIALS_DIR}/credentials.json

    Presiona ENTER cuando hayas guardado el archivo...
    """)

    input()

    if not CREDENTIALS_FILE.exists():
        print("[ERROR] credentials.json no encontrado en:")
        print(f"        {CREDENTIALS_FILE}")
        print("\nPor favor, descarga el archivo de Google Cloud Console")
        return False

    print("[OK] credentials.json encontrado")

    print("\nPASO 2: Autorizar en navegador")
    print("-" * 70)
    print("Se abrirá una ventana del navegador...")
    print("Debes autorizar el acceso a tu cuenta Google")
    print("El token se guardará LOCALMENTE en tu máquina")

    input("\nPresiona ENTER para continuar...")

    try:
        # Crear flow de OAuth2
        flow = InstalledAppFlow.from_client_secrets_file(
            CREDENTIALS_FILE, SCOPES)

        # Ejecutar flujo local (abre navegador)
        creds = flow.run_local_server(port=8080)

        # Guardar token localmente
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)

        print("\n[OK] Token guardado exitosamente")
        print(f"     Ubicación: {TOKEN_FILE}")
        print("\nAhora puedes cerrar el navegador")

        return True

    except Exception as e:
        print(f"\n[ERROR] {e}")
        return False

def verify_token():
    """
    Verifica que el token funciona
    """
    if not TOKEN_FILE.exists():
        print("[ERROR] Token no configurado. Ejecuta primero: python notebooklm_auth.py")
        return False

    try:
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)

        # Verificar que no expiró
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        print("[OK] Token válido")
        return True

    except Exception as e:
        print(f"[ERROR] Token inválido: {e}")
        return False

def main():
    print("\n" + "="*70)
    print("NOTEBOOKLM - CONFIGURACION INICIAL")
    print("="*70)

    # Paso 1: Configurar credenciales
    if not setup_credentials():
        print("\n[CANCELADO] No se pudo configurar OAuth2")
        return

    print("\n" + "="*70)
    print("VERIFICACION")
    print("="*70)

    # Paso 2: Verificar que funciona
    if verify_token():
        print("\n[EXITO] Motor_IA está listo para usar NotebookLM")
        print("\nProximos pasos:")
        print("1. Crea un notebook en NotebookLM: 'Motor_IA Knowledge'")
        print("2. Copia su ID (aparece en URL)")
        print("3. Guárdalo en: .env (NOTEBOOKLM_NOTEBOOK_ID=...)")
        print("4. El hook automaticamente consultará y actualizará NotebookLM")
    else:
        print("\n[ERROR] No se pudo verificar el token")
        print("Por favor, reinicia: python notebooklm_auth.py")

    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    main()
