# -*- coding: utf-8 -*-
# backend/core/db.py – SQLite + SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, Float, String, Boolean, DateTime, JSON
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
from backend.core.config import settings

engine = create_engine(f"sqlite:///{settings.db_path}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

def init_db():
    Base.metadata.create_all(bind=engine)

# MODELE
class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(String)

class SensorLog(Base):
    __tablename__ = "sensor_log"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=datetime.utcnow)
    name = Column(String)
    value = Column(Float)

class EventLog(Base):
    __tablename__ = "event_log"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=datetime.utcnow)
    level = Column(String)       # INFO/WARN/ERROR
    event = Column(String)
    meta = Column(JSON, nullable=True)

class VentState(Base):
    __tablename__ = "vent_state"
    id = Column(Integer, primary_key=True)   # vent_id
    name = Column(String)
    position = Column(Float, default=0.0)
    available = Column(Boolean, default=True)
    user_target = Column(Float, default=0.0)

class RuntimeState(Base):
    __tablename__ = "runtime_state"
    key = Column(String, primary_key=True)   # e.g. 'mode','last_calibration'
    value = Column(String)
