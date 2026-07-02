# app/auth/security.py
#
# Utilidades de seguridad: hashing de passwords y creación/verificación
# de JWT (PyJWT).
#
# FIX: se usa la librería `bcrypt` directamente, en vez de pasar por
# `passlib`. passlib (última versión estable, de 2020) tiene un bug de
# compatibilidad conocido con bcrypt>=4.1: bcrypt le sacó el atributo
# `__about__` que passlib usa para detectar la versión instalada, y esa
# falla en cascada termina rompiendo la lógica interna de passlib de
# forma rara (el error "password cannot be longer than 72 bytes" es un
# síntoma secundario de ese bug, no un problema real de la password).
# bcrypt solo, sin el wrapper de passlib, funciona sin problemas.

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config.config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    JWT_EXPIRATION_MINUTES,
)


# bcrypt trunca (y algunas implementaciones fallan) con inputs de más de
# 72 bytes -- se trunca explícitamente acá para evitar sorpresas con
# passwords largas o con caracteres multi-byte (emojis, tildes, etc.)
_MAX_PASSWORD_BYTES = 72


def _prepare_password(password: str) -> bytes:
    encoded = password.encode("utf-8")
    return encoded[:_MAX_PASSWORD_BYTES]


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(_prepare_password(password), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        _prepare_password(plain_password),
        hashed_password.encode("utf-8")
    )


def create_access_token(user_id: str) -> str:
    """
    Genera un JWT con el user_id en el claim "sub" (subject, estándar de
    JWT para identificar al usuario) y una fecha de expiración.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=JWT_EXPIRATION_MINUTES
    )

    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """
    Decodifica y valida un JWT. Devuelve el user_id (claim "sub").
    Lanza jwt.PyJWTError (o subclases como ExpiredSignatureError,
    InvalidTokenError) si el token es inválido o expiró -- el caller
    (dependencies.py) se encarga de convertir eso en un 401.
    """
    payload = jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM]
    )
    return payload["sub"]