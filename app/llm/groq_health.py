# app/llm/groq_health.py
#
# Chequeo liviano de si Groq está activo -- usado por GET /health para
# el indicador de estado de la UI. Mismo patrón que ollama_health.py:
# timeout corto, no rompe el endpoint /health si Groq está lento o caído.
#
# FIX (reemplaza el chequeo de Ollama): Ollama dejó de ser el camino
# principal (ahora es Groq, con Ollama como fallback de emergencia) --
# el badge de la UI debe reflejar lo que realmente le importa al
# usuario: si el chat puede responder, no el estado de un componente
# de respaldo.
#
# Se usa GET /openai/v1/models (listar modelos disponibles) en vez de
# una llamada de chat real -- es la forma más liviana de confirmar que
# la API responde y la API key es válida, sin gastar cupo del rate
# limiter ni generar una respuesta real.
#
# GROQ_API_KEY se lee con os.getenv directo (no desde app.config.config)
# porque no se confirmó si ese módulo la expone -- mismo criterio que
# ya usa groq_client.py.

import os

import httpx

GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"


async def is_groq_alive() -> bool:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return False

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                GROQ_MODELS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        return response.status_code == 200
    except (httpx.TimeoutException, httpx.HTTPError):
        return False