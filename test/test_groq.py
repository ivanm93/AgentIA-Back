"""
Prueba GroqClient de forma aislada -- sin ChatService, sin Ollama, sin
túnel. Si esto falla, el problema es Groq (API key, modelo, red). Si
esto funciona pero el chat no usa Groq, el problema está en
_generate_answer() o en el rate limiter, no en la conexión con Groq.

Uso:
    export GROQ_API_KEY=gsk_...   # si no está seteada ya en el entorno
    python test_groq.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.getcwd())  # ajustar si se corre desde otro directorio

try:
    from dotenv import load_dotenv, find_dotenv
    dotenv_path = find_dotenv(usecwd=True)
    print(f"CWD: {os.getcwd()}")
    print(f".env encontrado en: {dotenv_path!r} (vacío = no lo encontró)")
    loaded = load_dotenv(dotenv_path)
    print(f"load_dotenv() cargó algo: {loaded}")
except ImportError:
    print(
        "⚠️  python-dotenv no está instalado -- no se carga .env automático. "
        "Si GROQ_API_KEY vive solo en .env (no exportada), este script no "
        "la va a ver. `pip install python-dotenv` o exportá la variable a mano."
    )

print(f"GROQ_API_KEY vista por os.getenv: {os.getenv('GROQ_API_KEY')!r}")

from app.llm.groq_client import GroqClient
from app.llm.rate_limiter import GroqRateLimiter


async def main():
    if not os.getenv("GROQ_API_KEY"):
        print("❌ GROQ_API_KEY no está seteada en este entorno.")
        return

    client = GroqClient()
    print(f"Modelo: {client.model}")

    messages = [
        {"role": "user", "content": "Respondé solo con la palabra: funciona"}
    ]

    limiter = GroqRateLimiter()
    estimated = limiter.estimate_tokens(messages)
    allowed, reason = await limiter.acquire(estimated)
    print(f"Rate limiter -- permitido: {allowed}, motivo si no: {reason}")
    print(f"Estado del cupo: {limiter.status()}")

    if not allowed:
        print("❌ El rate limiter está bloqueando el request antes de llegar a Groq.")
        return

    try:
        answer = await client.chat(messages)
        print(f"✅ Groq respondió: {answer!r}")
    except Exception as e:
        print(f"❌ Groq falló: {e!r}")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())