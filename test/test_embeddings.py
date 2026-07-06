"""
Prueba EmbeddingClient de forma aislada -- sin Ollama, sin túnel, sin
Mongo. La primera corrida va a tardar más porque descarga el modelo
(~0.22GB) desde Hugging Face; las siguientes son instantáneas porque
queda cacheado en disco.

Uso:
    python test_embeddings.py
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.getcwd())

from app.llm.embedding_client import EmbeddingClient


async def main():
    print("Cargando modelo (puede tardar la primera vez, descarga ~0.22GB)...")
    t0 = time.time()
    client = EmbeddingClient()
    print(f"Instanciado en {time.time() - t0:.2f}s")

    textos = [
        "hola, como estas",
        "me siento muy ansioso últimamente",
        "cual es el dolar blue hoy",
    ]

    for texto in textos:
        t0 = time.time()
        vector = await client.embed(texto)
        elapsed = time.time() - t0
        print(
            f"✅ {texto!r} -> vector de {len(vector)} dimensiones "
            f"en {elapsed:.3f}s (primeros 3 valores: {vector[:3]})"
        )


if __name__ == "__main__":
    asyncio.run(main())