import asyncio
import os
import time
from collections import deque

import httpx

from app.core.logging_config import get_logger

logger = get_logger(__name__)

GEMINI_EMBED_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
)


class _EmbeddingRateLimiter:
    """
    Limitador simple para el free tier de Gemini Embedding: 1.500
    requests/día es la restricción real (el TPM de 10M es tan generoso
    que no importa para este volumen de uso). Mismo espíritu que
    GroqRateLimiter -- colchón de seguridad bajo el límite real, y
    compartido a nivel de clase (no por instancia) para que sea un
    solo contador real, sin importar cuántas veces se instancie
    EmbeddingClient.
    """

    def __init__(self, rpd_limit: int | None = None):
        self.rpd_limit = rpd_limit or int(os.getenv("GEMINI_EMBED_RPD_LIMIT", "1400"))
        self._daily_count = 0
        self._daily_date = self._today()
        self._lock = asyncio.Lock()

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    async def acquire(self) -> bool:
        async with self._lock:
            today = self._today()
            if today != self._daily_date:
                self._daily_date = today
                self._daily_count = 0

            if self._daily_count >= self.rpd_limit:
                return False

            self._daily_count += 1
            return True


class EmbeddingClient:
    """
    FIX (independencia de RAM en Render free tier): la versión anterior
    corría el modelo LOCAL con fastembed -- funcionaba, pero el proceso
    completo (FastAPI + Motor + ONNX Runtime + el modelo) superaba los
    512MB del free tier de Render y el proceso moría por OOM,
    reiniciándose solo (afectando a TODOS los usuarios conectados en
    ese momento, no solo a quien disparó el mensaje).

    Se vuelve a una API hosteada (Gemini Embedding, gemini-embedding-001)
    -- decisión consciente de priorizar estabilidad del proceso sobre
    "cero dependencias externas". Igual que con Groq, esto suma otra
    API key y otro cupo gratis a vigilar (acá: 1.500 requests/día).

    El rate limiter vive a nivel de CLASE (no de instancia) por el
    mismo motivo que en GroqRateLimiter: si MemoryEngine crea un
    EmbeddingClient() nuevo en cada llamada, el contador tiene que
    seguir siendo el mismo para reflejar el cupo real de la cuenta.
    """

    _rate_limiter: _EmbeddingRateLimiter | None = None

    def __init__(self, model: str | None = None):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        self._http = httpx.AsyncClient(timeout=30.0)

        if EmbeddingClient._rate_limiter is None:
            EmbeddingClient._rate_limiter = _EmbeddingRateLimiter()

    async def embed(self, text: str) -> list[float]:
        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY no configurada -- no se puede generar "
                "el embedding."
            )

        allowed = await EmbeddingClient._rate_limiter.acquire()
        if not allowed:
            raise RuntimeError(
                "Cupo gratis diario de Gemini Embedding agotado "
                f"({EmbeddingClient._rate_limiter.rpd_limit} requests/día)."
            )

        url = GEMINI_EMBED_URL_TEMPLATE.format(model=self.model)
        payload = {
            "model": f"models/{self.model}",
            "content": {"parts": [{"text": text}]},
        }

        response = await self._http.post(
            url,
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        if "embedding" not in data or "values" not in data["embedding"]:
            raise ValueError(f"Gemini embedding error: {data}")

        return data["embedding"]["values"]

    async def aclose(self):
        await self._http.aclose()