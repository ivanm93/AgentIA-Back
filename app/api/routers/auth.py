# app/api/routers/auth.py

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.auth import UserRegister, UserLogin, TokenResponse, UserOut
from app.repositories.user_repository import UserRepository
from app.auth.security import (
    hash_password,
    verify_password,
    create_access_token,
)
from app.auth.dependencies import get_current_user_id


router = APIRouter(prefix="/auth", tags=["auth"])


def get_user_repository() -> UserRepository:
    return UserRepository()


@router.post("/register", response_model=TokenResponse)
async def register(
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
async def login(
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