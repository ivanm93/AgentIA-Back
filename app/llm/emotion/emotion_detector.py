import re
import json
import httpx
from app.config.config import OLLAMA_URL, OLLAMA_MODEL
from app.core.logging_config import get_logger

logger = get_logger(__name__)


VALID_EMOTIONS = [
    "enojo",
    "tristeza",
    "ansiedad",
    "confusión",
    "calma",
    "alegría",
    "neutral",
]


class EmotionDetector:

    async def detect(self, message: str, rule_emotions: list[str]):

        prompt = f"""
Detectá la emoción principal del mensaje.

Mensaje:
{message}

Emociones detectadas por reglas:
{rule_emotions}

Respondé con JSON indicando la emoción principal, usando exactamente uno
de estos valores: enojo, tristeza, ansiedad, confusión, calma, alegría,
neutral.
"""

        # FIX (mejora C): se agrega un JSON schema con "enum" forzando la
        # respuesta a ser EXACTAMENTE una de las 7 emociones válidas. Esto
        # ataca de raíz el mismo problema que ya parcheamos con
        # _parse_emotion() (respuestas verbosas tipo "detectada: [enojo]...
        # razón: ..."), pero a nivel estructural en vez de vía regex sobre
        # texto libre. Se mantiene _parse_emotion() como fallback por si
        # el modelo/versión de Ollama no respeta el schema al 100%.
        response_schema = {
            "type": "object",
            "properties": {
                "emotion": {
                    "type": "string",
                    "enum": VALID_EMOTIONS,
                },
            },
            "required": ["emotion"],
        }

        # FIX: timeout=30 (implícito, aplicado a todo: connect/read/write/pool)
        # era demasiado corto y cortaba la request cuando Ollama tardaba en
        # cargar el modelo o generar la respuesta. Se separa el timeout de
        # conexión (corto, para detectar rápido si Ollama no está levantado)
        # del de lectura (más generoso, para dejar generar al modelo).
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
                        "stream": False,
                        "format": response_schema,
                    }
                )
            response.raise_for_status()
            data = response.json()
            content = data["message"]["content"]

        except (httpx.TimeoutException, httpx.HTTPError) as e:
            # FIX: un timeout o error de red no debería tirar abajo todo el
            # flujo de chat. Se loguea y se cae a un valor neutral por defecto.
            logger.warning(
                f"Error consultando Ollama: {e!r}. Usando emoción por "
                f"defecto 'neutral'."
            )
            return "neutral"

        except (KeyError, ValueError) as e:
            logger.warning(
                f"Respuesta inesperada de Ollama: {e!r}. Usando emoción "
                f"por defecto 'neutral'."
            )
            return "neutral"

        # con el schema forzado, content debería ser JSON tipo {"emotion": "..."}
        try:
            parsed = json.loads(content)
            emotion = parsed.get("emotion", "")
            if emotion in VALID_EMOTIONS:
                return emotion
        except (json.JSONDecodeError, AttributeError):
            pass

        # fallback: si el schema no fue respetado por algún motivo,
        # se recurre al parsing por regex sobre texto libre (igual que antes)
        return self._parse_emotion(content)

    def _parse_emotion(self, content: str) -> str:
        """
        FIX: antes se hacía content.strip().lower() directo, lo que dejaba
        pasar respuestas verbosas del modelo como
        'detectada: [enojo]\\n\\nrazón: ...' en vez de solo 'enojo'.
        Ahora se busca la primera emoción válida dentro del texto devuelto,
        y si no se encuentra ninguna, se cae a 'neutral'.
        """

        text = content.strip().lower()

        for emotion in VALID_EMOTIONS:
            if re.search(rf"\b{re.escape(emotion)}\b", text):
                return emotion

        return "neutral"