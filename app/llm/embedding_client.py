import httpx
from app.config.config import OLLAMA_URL


class EmbeddingClient:

    async def embed(self, text: str):

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={
                    "model": "nomic-embed-text",
                    "prompt": text
                }
            )

        data = response.json()

        if "embedding" not in data:
            raise ValueError(f"Ollama embedding error: {data}")

        return data["embedding"]