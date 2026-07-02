import httpx
from app.config.config import OLLAMA_MODEL, OLLAMA_URL


class Summarizer:

    async def summarize(self, messages: list):

        prompt = f"""
Resumí esta conversación en 5 líneas.

Incluí:
- tema principal
- emociones del usuario
- decisiones importantes

CONVERSACIÓN:
{messages}
"""

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False
                }
            )

        return response.json()["message"]["content"]