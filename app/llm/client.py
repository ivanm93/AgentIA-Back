import httpx
from app.config.config import OLLAMA_URL, OLLAMA_MODEL


class LLMClient:

    async def generate(self, messages: list):

        async with httpx.AsyncClient(timeout=120) as client:

            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": messages,
                    "stream": False
                }
            )

        return response.json()["message"]["content"]