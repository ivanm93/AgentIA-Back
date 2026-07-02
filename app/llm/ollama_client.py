import httpx
from app.config.config import OLLAMA_MODEL, OLLAMA_URL


class OllamaClient:

    async def chat(self, messages: list):

        async with httpx.AsyncClient(timeout=120) as client:

            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": messages,
                    "stream": False
                }
            )

            response.raise_for_status()

            return response.json()["message"]["content"]