# app/auth/dependencies.py
#
# Dependency de FastAPI que se inyecta en cualquier endpoint protegido.
# Lee el header "Authorization: Bearer <token>", valida el JWT, y
# devuelve el user_id -- o tira 401 si el token falta, es inválido, o
# expiró.

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth.security import decode_access_token


_bearer_scheme = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme)
) -> str:

    token = credentials.credentials

    try:
        user_id = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado, iniciá sesión de nuevo",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )

    return user_id