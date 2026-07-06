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
    """
    FIX (independencia del túnel): antes esta clase llamaba a Ollama
    directo por HTTP, sin pasar por GroqClient. Ahora intenta primero
    con Groq (compartiendo groq_client y rate_limiter con ChatService
    -- MISMA instancia, no una nueva, para que el cupo gratis de Groq
    sea un solo contador real y no dos contadores que no se enteran
    entre sí) y cae a Ollama (la lógica vieja, sin tocar) si no hay
    cupo o si Groq falla en el momento.

    groq_client y rate_limiter se inyectan desde ChatService en vez de
    instanciarse acá adentro -- ver el comentario de arriba sobre por
    qué el rate limiter tiene que ser compartido.
    """

    def __init__(self, groq_client, rate_limiter):
        self._groq_client = groq_client
        self._rate_limiter = rate_limiter

    def _build_prompt(self, message: str, rule_emotions: list[str]) -> str:
        return f"""
Detectá la emoción principal del mensaje.

Mensaje:
{message}

Emociones detectadas por reglas:
{rule_emotions}

Respondé ÚNICAMENTE con un JSON de la forma {{"emotion": "..."}},
usando exactamente uno de estos valores: enojo, tristeza, ansiedad,
confusión, calma, alegría, neutral. No agregues texto fuera del JSON.
"""

    async def detect(self, message: str, rule_emotions: list[str]):
        prompt = self._build_prompt(message, rule_emotions)
        messages = [{"role": "user", "content": prompt}]

        estimated_tokens = self._rate_limiter.estimate_tokens(messages)
        allowed, reason = await self._rate_limiter.acquire(estimated_tokens)

        if allowed:
            try:
                content = await self._groq_client.chat(
                    messages,
                    response_format={"type": "json_object"},
                )
                return self._extract_emotion(content)
            except Exception as e:
                logger.warning(
                    f"Groq falló clasificando emoción -- cae a Ollama: {e!r}"
                )
        else:
            logger.info(
                f"Cupo de Groq agotado ({reason}) para clasificador de "
                f"emoción -- cae a Ollama."
            )

        return await self._detect_with_ollama(message, rule_emotions)

    async def _detect_with_ollama(self, message: str, rule_emotions: list[str]):
        prompt = self._build_prompt(message, rule_emotions)

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

        return self._extract_emotion(content)

    def _extract_emotion(self, content: str) -> str:
        # con el schema forzado (Ollama) o el prompt explícito (Groq),
        # content debería ser JSON tipo {"emotion": "..."}
        try:
            parsed = json.loads(content)
            emotion = parsed.get("emotion", "")
            if emotion in VALID_EMOTIONS:
                return emotion
        except (json.JSONDecodeError, AttributeError):
            pass

        # fallback: si el JSON no fue respetado por algún motivo,
        # se recurre al parsing por regex sobre texto libre
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