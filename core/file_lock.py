# -*- coding: utf-8 -*-
"""
file_lock.py - File locking cross-platform y atomic replace
============================================================
Context manager que adquiere un lock de archivo de forma segura
en Windows (msvcrt.locking) y Linux/Mac (fcntl.flock).

Incluye _atomic_replace(src, dst) para renombrar archivos de forma
atomica con fallback shutil.copy2 para Windows WinError 5.

Uso:
    from core.file_lock import file_lock, _atomic_replace

    with file_lock("mi_recurso") as acquired:
        if acquired:
            # operar sobre el recurso compartido
            ...

    _atomic_replace(Path("tmp.json"), Path("data.json"))
"""

import os
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


def _get_lock_dir() -> Path:
    """
    Obtiene LOCK_DIR desde config de forma lazy para evitar imports
    circulares cuando otros modulos de core importan file_lock.
    """
    try:
        from config import LOCK_DIR
        return LOCK_DIR
    except ImportError:
        pass
    try:
        # Intento relativo para cuando se ejecuta como submodulo
        from Motor_IA.config import LOCK_DIR
        return LOCK_DIR
    except ImportError:
        return Path.home() / ".adaptive_cli" / "locks"


@contextmanager
def file_lock(name: str, timeout: float = 5.0) -> Generator[bool, None, None]:
    """
    Lock de archivo cross-platform con timeout y retry con backoff exponencial.

    Args:
        name:    Nombre logico del lock (sin extension).
        timeout: Segundos maximos de espera antes de rendirse.

    Yields:
        acquired (bool): True si se obtuvo el lock, False si expiro el timeout.
    """
    lock_dir = _get_lock_dir()
    lock_dir.mkdir(parents=True, exist_ok=True)
    lockfile = lock_dir / f"{name}.lock"

    fd = None
    acquired = False
    backoff = 0.02  # 20ms inicial

    try:
        fd = open(lockfile, "w", encoding="utf-8")
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (OSError, IOError):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                sleep_time = min(backoff, remaining)
                time.sleep(sleep_time)
                backoff = min(backoff * 2, 0.5)  # cap en 500ms

        yield acquired

    finally:
        if fd is not None:
            try:
                if acquired:
                    if sys.platform == "win32":
                        import msvcrt
                        msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            except (OSError, IOError):
                pass
            try:
                fd.close()
            except (OSError, IOError):
                pass


def _atomic_replace(src: Path, dst: Path) -> None:
    """
    Reemplaza dst con src de forma atomica.

    En Unix usa os.replace() que es atomico.
    En Windows, os.replace() puede fallar con WinError 5 (Access Denied)
    cuando otro proceso tiene el archivo abierto. En ese caso se hace
    fallback a shutil.copy2 + os.unlink del src.

    Args:
        src: Archivo temporal de origen (debe existir).
        dst: Archivo destino final.
    """
    src = Path(src)
    dst = Path(dst)

    # Asegurar que el directorio destino existe
    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        os.replace(str(src), str(dst))
    except OSError:
        if sys.platform == "win32":
            # Fallback Windows: copy + remove
            try:
                shutil.copy2(str(src), str(dst))
                try:
                    os.unlink(str(src))
                except OSError:
                    pass  # src queda huerfano pero dst ya es correcto
            except OSError as copy_err:
                raise OSError(
                    f"No se pudo reemplazar {dst}: "
                    f"os.replace fallo y shutil.copy2 tambien: {copy_err}"
                ) from copy_err
        else:
            raise
