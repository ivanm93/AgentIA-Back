import asyncio

from fastembed import TextEmbedding

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class EmbeddingClient:
    """
    FIX (independencia del túnel): antes llamaba a Ollama vía HTTP
    (OLLAMA_URL/api/embeddings) -- dependía de que el túnel de
    Cloudflare estuviera levantado y con la URL actualizada en Render.
    Ahora corre el modelo LOCAL, en el mismo proceso, vía fastembed
    (ONNX Runtime -- no arrastra todo PyTorch, pensado para entornos
    chicos como Render free tier). Cero llamadas de red para esto.

    Se pierde compatibilidad con los embeddings viejos generados por
    Ollama (otro modelo, otra dimensión) -- decisión consciente, se
    aceptó perder la memoria vieja en vez de migrarla.

    El modelo se carga UNA sola vez a nivel de clase (no por instancia)
    -- cargarlo de nuevo en cada request sería carísimo en tiempo y
    memoria. La primera vez que corre en un entorno nuevo (ej. primer
    deploy en Render), fastembed descarga los pesos del modelo desde
    Hugging Face (~0.22GB) -- eso requiere que Render tenga salida a
    internet hacia huggingface.co en ese momento (no debería ser un
    problema, a diferencia del túnel esto es una descarga única, no una
    dependencia de cada request).
    """

    _MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    _model: TextEmbedding | None = None

    def __init__(self):
        if EmbeddingClient._model is None:
            logger.info(f"Cargando modelo de embeddings local: {self._MODEL_NAME}")
            EmbeddingClient._model = TextEmbedding(model_name=self._MODEL_NAME)

    async def embed(self, text: str) -> list[float]:
        # .embed() de fastembed es sync y CPU-bound -- se corre en un
        # thread aparte para no bloquear el event loop de FastAPI
        # mientras calcula (antes, con Ollama, el bloqueo lo evitaba
        # httpx async porque la espera era de red, no de CPU local).
        return await asyncio.to_thread(self._embed_sync, text)

    def _embed_sync(self, text: str) -> list[float]:
        vectors = list(self._model.embed([text]))
        return vectors[0].tolist()