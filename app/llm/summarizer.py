import httpx
from app.config.config import OLLAMA_MODEL, OLLAMA_URL
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class Summarizer:

    async def summarize(self, messages: list, previous_summary: str = None) -> str | None:
        """
        Devuelve un resumen de 5 líneas de los mensajes dados, o None si
        falla (no debe romper el flujo principal de la conversación --
        un resumen fallido es un "nice to have" perdido, no un error
        crítico).

        Si se pasa `previous_summary`, se le pide al modelo que lo
        actualice/extienda con la info nueva, en vez de partir de cero
        cada vez (resumen incremental/rolling).
        """

        # FIX: antes se armaba el prompt con f"{messages}" -- el repr
        # crudo de una lista de dicts de Python (con corchetes, comillas,
        # llaves), que el modelo tiene que "decodificar" en vez de leer
        # como conversación real. Ahora se arma una transcripción legible.
        transcript = self._format_transcript(messages)

        previous_block = ""
        if previous_summary:
            previous_block = f"""
RESUMEN PREVIO (actualizalo con la info nueva, no lo ignores):
{previous_summary}
"""

        prompt = f"""
Resumí esta conversación en 5 líneas como máximo.

Incluí:
- tema principal
- emociones del usuario
- decisiones importantes

No inventes información que no esté en la conversación.
{previous_block}
CONVERSACIÓN:
{transcript}
"""

        # FIX: sin timeout explícito, esta llamada corría el mismo riesgo
        # que ya vimos con Ollama tardando en cargar/generar (ver el bug
        # de ReadTimeout que arreglamos en emotion_detector.py). Mismo
        # criterio acá: connect corto, read generoso.
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
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
            response.raise_for_status()
            return response.json()["message"]["content"].strip()

        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.warning(f"Error generando resumen: {e!r}")
            return None

        except (KeyError, ValueError) as e:
            logger.warning(f"Respuesta inesperada de Ollama al resumir: {e!r}")
            return None

    def _format_transcript(self, messages: list) -> str:
        lines = []
        for m in messages:
            role = "Usuario" if m.get("role") == "user" else "Asistente"
            lines.append(f"{role}: {m.get('content', '')}")
        return "\n".join(lines)