# app/schemas/auth.py
#
# Modelos Pydantic para requests/responses de los endpoints de auth.
# FastAPI usa estos para validar el body entrante y para generar la
# documentación automática (/docs).

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: EmailStr