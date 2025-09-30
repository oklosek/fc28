# -*- coding: utf-8 -*-
# backend/app.py – punkt wejścia FastAPI/uvicorn
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.core.config import settings, ensure_dirs
from backend.core.db import init_db
from backend.core.mqtt_client import mqtt_start
from backend.core.controller import Controller
from backend.core.rs485 import RS485Manager
from backend.core.scheduler import Scheduler
from backend.core.update_manager import UpdateManager
from backend.routers import api, installer, ws

app = FastAPI(title="FarmCare 2.0", version="2.0.0")

# CORS (ułatwia podmianę frontu zewnętrznego)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serwowanie frontendu (lokalnie)
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
else:
    print("Static frontend directory not found; skipping /static mount")

# Routery
app.include_router(api.router, prefix="/api", tags=["api"])
app.include_router(installer.router, prefix="/installer", tags=["installer"])
app.include_router(ws.router, tags=["ws"])

# Obiekty runtime
controller: Controller = None
rs485: RS485Manager = None
scheduler: Scheduler = None
update_manager: UpdateManager = None

@app.on_event("startup")
async def on_startup():
    ensure_dirs()
    init_db()
    # RS485 – dwie magistrale wg settings.yaml
    global rs485
    rs485 = RS485Manager()
    await rs485.start()  # czyta okresowo i buforuje średnie

    # MQTT (lokalny broker)
    await mqtt_start()

    # Kontroler (logika + grupy/partie + kalibracja)
    global controller
    controller = Controller(rs485_manager=rs485)
    controller.start()  # startuje wątki/async task pętli sterowania

    # Harmonogram (przewietrzanie, kalibracja dzienna)
    global scheduler
    scheduler = Scheduler(controller)
    scheduler.start()
    global update_manager
    update_manager = UpdateManager(current_version=app.version)
    update_manager.start()


@app.on_event("shutdown")
async def on_shutdown():
    if scheduler: scheduler.stop()
    if controller: controller.stop()
    if update_manager: update_manager.stop()
    if rs485: await rs485.stop()

# Strona główna i panel instalatora
@app.get("/")
async def index():
    return {"ok": True, "message": "FarmCare backend running. Open /static/index.html"}

@app.get("/installer")
async def installer_index():
    return {"ok": True, "message": "Open /static/installer.html"}

