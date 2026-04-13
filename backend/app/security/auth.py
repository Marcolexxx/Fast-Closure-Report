from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timedelta
from typing import Optional

import jwt

from app.config import get_settings

import bcrypt

def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


def _secret() -> str:
    return get_settings().secret_key


def create_access_token(user_id: str, role: str, username: str = "", department_id: Optional[str] = None) -> str:
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(hours=settings.access_token_expire_hours)
    payload = {
        "sub": user_id,
        "role": role,
        "username": username,
        "department_id": department_id,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def create_refresh_token(user_id: str) -> str:
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError on failure."""
    return jwt.decode(token, _secret(), algorithms=["HS256"])
