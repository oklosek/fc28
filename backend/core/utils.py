# -*- coding: utf-8 -*-
# backend/core/utils.py – drobiazgi
def to_float(x, default=0.0):
    try: return float(x)
    except: return default
