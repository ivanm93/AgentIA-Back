# app/api/dependencies.py
#
# Dependency compartida para inyectar ChatService en los routers, como
# singleton -- evita recrear todo el pipeline (OllamaClient, MemoryEngine,
# RiskDetector, etc.) en cada request. No hay estado mutable específico
# de un usuario dentro de ChatService (todo vive en Mongo, identificado
# por user_id), así que compartir la instancia entre requests es seguro.

from functools import lru_cache

from app.services.chat_service import ChatService


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService()