#!/bin/bash
# Lance PortGuardian avec le venv local, quel que soit l'emplacement du projet.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$SCRIPT_DIR/../venv/bin/python3"

if [ ! -x "$PYTHON" ]; then
    echo "Venv introuvable. Crée-le d'abord :"
    echo "  python3 -m venv $SCRIPT_DIR/../venv"
    echo "  $SCRIPT_DIR/../venv/bin/pip install -r $SCRIPT_DIR/requirements.txt"
    exit 1
fi

exec sudo "$PYTHON" "$SCRIPT_DIR/main.py" "$@"
