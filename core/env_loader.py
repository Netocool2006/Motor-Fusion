"""
env_loader.py - Load environment variables from .env file

Simple, dependency-free .env loader for Motor-Fusion.
Automatically called at module import time.

Usage:
    import core.env_loader  # Auto-loads from .env
    import os
    value = os.environ.get("MY_VAR")
"""

import os
from pathlib import Path


def load_env_file(env_path: Path = None) -> None:
    """
    Load environment variables from .env file.

    Args:
        env_path: Path to .env file. If None, looks for:
                  1. MOTOR_IA_ENV_PATH environment variable
                  2. .env in current directory
                  3. .env in Motor-Fusion root directory
    """
    # Determine .env file location
    if env_path is None:
        env_path = os.environ.get("MOTOR_IA_ENV_PATH")
        if env_path:
            env_path = Path(env_path)
        else:
            # Try current directory first
            candidates = [
                Path(".env"),
                Path(__file__).parent.parent / ".env",  # Motor-Fusion root
            ]
            for candidate in candidates:
                if candidate.exists():
                    env_path = candidate
                    break

    if not env_path or not isinstance(env_path, Path):
        env_path = Path(env_path) if env_path else None

    if env_path and env_path.exists():
        _parse_env_file(env_path)


def _parse_env_file(path: Path) -> None:
    """Parse .env file and set environment variables."""
    try:
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Parse KEY=VALUE
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()

                # Skip if already set (environment variables take precedence)
                if key and key not in os.environ:
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]

                    os.environ[key] = value
    except Exception as e:
        # Silently fail - .env is optional
        pass


# Auto-load .env at import time
load_env_file()
