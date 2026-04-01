#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
timezone_utils.py
=================
Utilidades para manejar fechas/horas en formato DD-MM-YYYY HH:MM:SS (GMT-6 Centro América)
"""

from datetime import datetime, timezone, timedelta


def get_ca_time() -> datetime:
    """
    Retorna la hora actual en zona horaria de Centro América (GMT-6).
    """
    utc_now = datetime.now(timezone.utc)
    ca_tz = timezone(timedelta(hours=-6))
    return utc_now.astimezone(ca_tz)


def format_ca_datetime(dt: datetime = None) -> str:
    """
    Formatea una datetime en formato DD-MM-YYYY HH:MM:SS (GMT-6).
    Si no se pasa datetime, usa hora actual.
    """
    if dt is None:
        dt = get_ca_time()
    elif dt.tzinfo is None:
        # Si no tiene timezone, asumir UTC y convertir
        dt = dt.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=-6)))
    else:
        # Convertir a GMT-6
        dt = dt.astimezone(timezone(timedelta(hours=-6)))

    return dt.strftime("%d-%m-%Y %H:%M:%S")


def format_ca_date(dt: datetime = None) -> str:
    """
    Formatea solo la fecha: DD-MM-YYYY
    """
    if dt is None:
        dt = get_ca_time()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=-6)))
    else:
        dt = dt.astimezone(timezone(timedelta(hours=-6)))

    return dt.strftime("%d-%m-%Y")


def format_ca_time(dt: datetime = None) -> str:
    """
    Formatea solo la hora: HH:MM:SS
    """
    if dt is None:
        dt = get_ca_time()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=-6)))
    else:
        dt = dt.astimezone(timezone(timedelta(hours=-6)))

    return dt.strftime("%H:%M:%S")


def to_ca_datetime(iso_string: str) -> str:
    """
    Convierte un ISO datetime string a formato DD-MM-YYYY HH:MM:SS (GMT-6).
    Ej: "2026-04-01T10:26:25.032829" → "01-04-2026 04:26:25"
    """
    try:
        # Parsear ISO format
        if 'T' in iso_string:
            dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        else:
            dt = datetime.fromisoformat(iso_string)

        # Si no tiene timezone, asumir UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # Convertir a GMT-6
        ca_tz = timezone(timedelta(hours=-6))
        dt_ca = dt.astimezone(ca_tz)

        return dt_ca.strftime("%d-%m-%Y %H:%M:%S")
    except Exception as e:
        return str(iso_string)


if __name__ == "__main__":
    # Test
    print("=== Timezone Utils Test ===\n")

    print(f"Hora actual (GMT-6): {format_ca_datetime()}")
    print(f"Solo fecha: {format_ca_date()}")
    print(f"Solo hora: {format_ca_time()}")

    # Test conversión ISO
    iso = "2026-04-01T10:26:25.032829"
    print(f"\nConversión ISO:\n  De: {iso}")
    print(f"  A:  {to_ca_datetime(iso)}")
