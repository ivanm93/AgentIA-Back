"""
Prueba EmbeddingClient (Gemini) de forma aislada -- sin Ollama, sin
túnel, sin Mongo, sin fastembed local.

Uso:
    # GEMINI_API_KEY tiene que estar en tu .env o exportada
    python test_embeddings.py
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.getcwd())

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app.llm.embedding_client import EmbeddingClient


async def main():
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ GEMINI_API_KEY no está seteada en este entorno.")
        print("   Conseguila gratis en https://aistudio.google.com/apikey")
        return

    client = EmbeddingClient()
    print(f"Modelo: {client.model}")

    textos = [
        "hola, como estas",
        "me siento muy ansioso últimamente",
        "cual es el dolar blue hoy",
    ]

    for texto in textos:
        t0 = time.time()
        try:
            vector = await client.embed(texto)
            elapsed = time.time() - t0
            print(
                f"✅ {texto!r} -> vector de {len(vector)} dimensiones "
                f"en {elapsed:.3f}s (primeros 3 valores: {vector[:3]})"
            )
        except Exception as e:
            print(f"❌ {texto!r} falló: {e!r}")

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())