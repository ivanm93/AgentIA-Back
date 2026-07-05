# app/api/routers/auth.py

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
    UserOut,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    MessageResponse,
)
from app.repositories.user_repository import UserRepository
from app.auth.security import (
    hash_password,
    verify_password,
    create_access_token,
    generate_reset_token,
    hash_reset_token,
)
from app.auth.dependencies import get_current_user_id
from app.services.email_service import send_password_reset_email
from app.core.rate_limiter import limiter
from app.core.logging_config import get_logger


router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


def get_user_repository() -> UserRepository:
    return UserRepository()


# FIX (rate limiting): límites por IP en los 4 endpoints más sensibles a
# abuso -- sin esto, alguien podía probar miles de passwords por minuto
# (fuerza bruta contra /login), crear cuentas en bucle (/register), o
# bombardear el buzón de alguien con emails de reseteo
# (/forgot-password). slowapi necesita que el endpoint reciba
# `request: Request` para poder identificar de dónde viene cada llamada.

@router.post("/register", response_model=TokenResponse)
@limiter.limit("3/minute")
async def register(
    request: Request,
    data: UserRegister,
    users: UserRepository = Depends(get_user_repository),
):
    if await users.email_exists(data.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con ese email",
        )

    password_hash = hash_password(data.password)
    user_doc = await users.create(data.email, password_hash)

    token = create_access_token(str(user_doc["_id"]))
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    data: UserLogin,
    users: UserRepository = Depends(get_user_repository),
):
    user_doc = await users.get_by_email(data.email)

    # FIX: mensaje de error idéntico si el email no existe o si la
    # password es incorrecta. Distinguir ("email no existe" vs
    # "password incorrecta") le permite a un atacante enumerar qué
    # emails están registrados -- un detalle de seguridad chico pero
    # real, sobre todo para una app que maneja datos de salud mental.
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Email o contraseña incorrectos",
    )

    if not user_doc:
        raise invalid_credentials

    if not verify_password(data.password, user_doc["password_hash"]):
        raise invalid_credentials

    await users.update_last_login(str(user_doc["_id"]))

    token = create_access_token(str(user_doc["_id"]))
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(
    user_id: str = Depends(get_current_user_id),
    users: UserRepository = Depends(get_user_repository),
):
    user_doc = await users.get_by_id(user_id)

    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    return UserOut(id=str(user_doc["_id"]), email=user_doc["email"])


# -----------------------------------------------------
# Recuperación de contraseña
# -----------------------------------------------------

@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    users: UserRepository = Depends(get_user_repository),
):
    # FIX (seguridad): siempre devolvemos el mismo mensaje genérico,
    # exista o no ese email en la base -- si el mensaje cambiara según
    # el caso, cualquiera podría usar este endpoint para averiguar qué
    # emails están registrados (mismo criterio que ya usamos en /login).
    generic_response = MessageResponse(
        message="Si ese email existe en nuestro sistema, te enviamos un link para restablecer tu contraseña."
    )

    user_doc = await users.get_by_email(data.email)

    if not user_doc:
        return generic_response

    raw_token, token_hash, expires_at = generate_reset_token()
    await users.set_reset_token(str(user_doc["_id"]), token_hash, expires_at)

    sent = await send_password_reset_email(data.email, raw_token)
    if not sent:
        logger.warning(f"No se pudo enviar el email de reseteo a {data.email}")

    return generic_response


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    data: ResetPasswordRequest,
    users: UserRepository = Depends(get_user_repository),
):
    token_hash = hash_reset_token(data.token)
    user_doc = await users.get_by_reset_token_hash(token_hash)

    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El link es inválido o ya venció. Pedí uno nuevo.",
        )

    new_password_hash = hash_password(data.new_password)
    user_id = str(user_doc["_id"])

    await users.update_password(user_id, new_password_hash)
    await users.clear_reset_token(user_id)  # el token es de un solo uso

    return MessageResponse(message="Tu contraseña se actualizó correctamente.")