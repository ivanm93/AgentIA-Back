# app/llm/ollama_health.py
#
# Chequeo liviano de si Ollama está activo -- usado por GET /health para
# el indicador "Ollama activo" de la UI.

import httpx
from app.config.config import OLLAMA_URL


async def is_ollama_alive() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
        return response.status_code == 200
    except (httpx.TimeoutException, httpx.HTTPError):
        return False
