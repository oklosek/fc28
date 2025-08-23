# Uruchom raz, aby zainicjalizować bazę i podstawowe wpisy
from backend.core.db import init_db, SessionLocal, RuntimeState
init_db()
with SessionLocal() as s:
    if not s.get(RuntimeState, "mode"):
        s.add(RuntimeState(key="mode", value="auto")); s.commit()
print("DB initialized")
