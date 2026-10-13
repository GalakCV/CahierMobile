#!/usr/bin/env sh
# Alternativa para macOS/Linux: ./run.sh (instalação: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# && .venv/bin/python manage.py migrate && .venv/bin/python manage.py seed_content)
cd "$(dirname "$0")" && exec .venv/bin/python launch.py "$@"
