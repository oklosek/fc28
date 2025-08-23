# -*- coding: utf-8 -*-
# backend/core/security.py – proste uwierzytelnianie tokenem dla operacji wrażliwych (WAN)
from fastapi import Header, HTTPException, status
from backend.core.config import settings, SECURITY

def require_admin(x_admin_token: str | None = Header(default=None)):
    if SECURITY.get("require_token", False):
        if not x_admin_token or x_admin_token != settings.ADMIN_TOKEN:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
