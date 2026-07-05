# main.py
#
# Punto de entrada de la API.

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse

from app.core.logging_config import configure_logging, get_logger
from app.core.rate_limiter import limiter
from app.db.mongo import MongoDatabase
from app.llm.ollama_health import is_ollama_alive
from app.api.routers import auth as auth_router
from app.api.routers import chat as chat_router


configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Se ejecuta al arrancar la app
    MongoDatabase.connect()
    logger.info("Aplicación iniciada, conexión a Mongo establecida.")
    yield
    # Se ejecuta al apagar la app
    MongoDatabase.close()
    logger.info("Aplicación detenida.")


app = FastAPI(
    title="API de apoyo emocional",
    lifespan=lifespan,
)

# FIX (rate limiting): sin esto, /auth/login y /auth/register no tenían
# ningún límite de intentos -- alguien podía probar miles de passwords
# por minuto contra una cuenta, o crear cuentas en bucle. slowapi cuenta
# requests por IP y devuelve 429 (Too Many Requests) al pasarse del
# límite definido en cada endpoint (ver app/api/routers/auth.py).
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Demasiados intentos. Esperá un momento y probá de nuevo."
        },
    )


# FIX: sin esto, el navegador bloquea las requests del frontend (Vercel/
# Vite) al backend por ser orígenes distintos -- el preflight OPTIONS que
# manda el navegador antes de cada POST/DELETE devolvía 405 porque
# FastAPI no sabía qué responder.
#
# ⚠️ Antes de un dominio de producción DEFINITIVO, revisá que esta lista
# tenga exactamente las URLs reales que vayas a usar -- nunca dejar "*"
# combinado con allow_credentials=True, es un hueco de seguridad real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://agent-ia-front.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(chat_router.router)


@app.get("/health")
async def health():
    mongo_ok = await MongoDatabase.ping()
    ollama_ok = await is_ollama_alive()
    return {
        "status": "ok" if (mongo_ok and ollama_ok) else "degraded",
        "mongo": mongo_ok,
        "ollama": ollama_ok,
    }