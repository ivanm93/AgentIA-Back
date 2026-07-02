import httpx
from app.config.config import OLLAMA_URL, OLLAMA_MODEL


class Embedder:

    async def embed(self, text: str) -> list:

        async with httpx.AsyncClient(timeout=30) as client:

            response = await client.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": text
                }
            )

        return response.json()["embedding"]