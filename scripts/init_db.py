"""Inicjalizacja bazy danych.

Skrypt można uruchomić poleceniem ``python scripts/init_db.py`` bez
konieczności modyfikacji ``PYTHONPATH``. Tworzy również katalog na plik
SQLite, dzięki czemu ``sqlite3`` nie zgłasza błędu "unable to open database
file" gdy folder ``data/`` nie istnieje.
"""

import sys
from pathlib import Path

# Dodaj katalog nadrzędny do sys.path, aby import "backend" działał przy
# bezpośrednim uruchomieniu skryptu.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.core.db import init_db, SessionLocal, RuntimeState
from backend.core.config import ensure_dirs

ensure_dirs()
init_db()

with SessionLocal() as s:
    if not s.get(RuntimeState, "mode"):
        s.add(RuntimeState(key="mode", value="auto"))
        s.commit()

print("DB initialized")
