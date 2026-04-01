#!/usr/bin/env bash
# Motor Fusion - Instalador (Mac/Linux)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  ============================================"
echo "   Motor Fusion - Instalador v1.0.0"
echo "  ============================================"
echo ""
echo "  Iniciando instalador grafico..."
echo ""

# Buscar Python 3
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    # Verificar que es Python 3
    PY_VER=$(python -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo "2")
    if [ "$PY_VER" = "3" ]; then
        PYTHON="python"
    fi
fi

if [ -z "$PYTHON" ]; then
    echo "  [ERROR] Python 3 no encontrado."
    echo "  Instale Python 3.8+ antes de continuar:"
    echo "    macOS:  brew install python3"
    echo "    Ubuntu: sudo apt install python3 python3-tk"
    echo "    Fedora: sudo dnf install python3 python3-tkinter"
    echo ""
    exit 1
fi

echo "  [OK] Usando: $PYTHON ($($PYTHON --version))"

# Verificar tkinter
if ! $PYTHON -c "import tkinter" 2>/dev/null; then
    echo ""
    echo "  [ERROR] tkinter no disponible."
    echo "  Instale el paquete tkinter:"
    echo "    Ubuntu/Debian: sudo apt install python3-tk"
    echo "    Fedora/RHEL:   sudo dnf install python3-tkinter"
    echo "    macOS:         brew install python-tk"
    echo ""
    exit 1
fi

echo "  [OK] tkinter disponible"
echo ""

$PYTHON "$SCRIPT_DIR/installer/installer_gui.py"
