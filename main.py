# main.py
#
# Punto de entrada de la API.

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.mongo import MongoDatabase
from app.llm.ollama_health import is_ollama_alive
from app.api.routers import auth as auth_router
from app.api.routers import chat as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Se ejecuta al arrancar la app
    MongoDatabase.connect()
    yield
    # Se ejecuta al apagar la app
    MongoDatabase.close()


app = FastAPI(
    title="API de apoyo emocional",
    lifespan=lifespan,
)

# FIX: sin esto, el navegador bloquea las requests del frontend (Vite,
# localhost:5173) al backend (localhost:8000) por ser orígenes distintos
# -- el preflight OPTIONS que manda el navegador antes de cada
# POST/DELETE devolvía 405 porque FastAPI no sabía qué responder.
#
# ⚠️ allow_origins=["*"] es cómodo para desarrollo local, pero antes de
# producción hay que restringirlo a la URL real del frontend desplegado
# (ej. ["https://tuapp.com"]), nunca dejar "*" con allow_credentials=True
# en producción -- es un hueco de seguridad real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
