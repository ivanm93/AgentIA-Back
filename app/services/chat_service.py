import asyncio
import re

from app.llm.ollama_client import OllamaClient
from app.llm.groq_client import GroqClient
from app.llm.rate_limiter import GroqRateLimiter
from app.prompts.prompt_builder import PromptBuilder
from app.llm.emotion.rule_detector import detect_by_rules
from app.llm.emotion.emotion_detector import EmotionDetector
from app.llm.emotion.emotion_style import get_emotion_style
from app.memory.memory_engine import MemoryEngine
from app.safety.risk_detector import RiskDetector
from app.safety.crisis_response import CRISIS_RESPONSE_MESSAGE
from app.core.logging_config import get_logger
from app.llm.tools.web_search_tool import WEB_SEARCH_TOOL_SCHEMA, execute_web_search

logger = get_logger(__name__)
from app.safety.clinical_signal_detector import ClinicalSignalDetector


class ChatService:

    _META_COMMENT_PATTERN = re.compile(
        r"\s*\((?:[^()]*?\b(?:escucho|valido|aplicando|reencuadr\w*|"
        r"sin pedir|sin juzgar|validando|escuchando)\b[^()]*?)\)",
        re.IGNORECASE
    )

    _BARE_INFINITIVE_META_PATTERN = re.compile(
        r"(?:^|(?<=[.!?]\s))(?:Validar|Reencuadrar|Escuchar)\b[^.!?]*[.!?]",
    )

    # FIX: después de parchear esto tres veces con verbos específicos
    # ("no puedo ayudarte", "no puedo continuar con esta conversación",
    # "no puedo buscar información...") y seguir encontrando variantes
    # nuevas que se escapaban, se generaliza el patrón: en vez de listar
    # verbos, matchea CUALQUIER frase corta de "no puedo <algo>." al
    # inicio, siempre que la respuesta COMPLETA sea básicamente eso (el
    # anclaje con $ al final evita falsos positivos -- una respuesta
    # real y sustanciosa que arranque con "no puedo comprarte un auto,
    # pero puedo ayudarte a pensar un plan de ahorro..." NO matchea,
    # porque sigue con contenido real después que no entra en los
    # grupos opcionales de cierre).
    _GENERIC_REFUSAL_PATTERN = re.compile(
        r"^\s*lo siento,?\s*(pero\s*)?no puedo [^.!?]{0,80}[.!?]\s*"
        r"(si (necesitas|querés|quieres)[^.!?]*[.!?]\s*)?"
        r"(¿?hay algo m[aá]s[^.!?]*[.!?]\s*)?$",
        re.IGNORECASE
    )

    _REFUSAL_FALLBACK = (
        "Dale, sigamos. Contame lo que quieras, estoy para escucharte."
    )

    # FIX: otra variante del mismo patrón de fondo (el modelo "narrando su
    # propio proceso" en vez de responder directo) -- esta vez inventa que
    # hubo "un problema con la respuesta anterior" (que no existió) y arma
    # una respuesta corregida entre comillas. La buena noticia es que la
    # respuesta real y usable está adentro de las comillas -- no hay que
    # descartarla, solo extraerla, en vez de mostrarle al usuario todo el
    # preámbulo de auto-crítica inventada.
    _SELF_CORRECTION_PATTERN = re.compile(
        r'^[^"“]{0,250}?(problema|error)[^"“]{0,120}(respuesta anterior|respuesta)'
        r'[^"“]{0,120}[:\-]?\s*["“](?P<quoted>.+)["”]\s*$',
        re.IGNORECASE | re.DOTALL
    )

    # FIX: bug de "disculpa refleja sin sentido" -- el modelo a veces
    # abre la respuesta con algo tipo "Lo siento, pero puedo hablar
    # contigo sobre eso..." (se disculpa por algo que SÍ puede hacer).
    # Ya existe una regla en system_prompt.py ("Sobre disculparte") que
    # pide no hacer esto, pero como con los otros bugs de este archivo,
    # el prompt solo no alcanza -- hace falta el backstop determinístico.
    #
    # El "pero" pegado a "lo siento" es la señal clave: una apertura
    # empática genuina ("Lo siento mucho, debe ser difícil...") no
    # suele encadenar "pero" ahí. Exigirlo evita pisar una empatía real
    # -- este patrón NO debe tocar esos casos.
    _LEADING_APOLOGY_PATTERN = re.compile(
        r"^\s*lo siento,?\s+pero\s+",
        re.IGNORECASE
    )

    # FIX (mood manual): mapeo de las etiquetas en español que muestra la
    # UI (selector de ánimo) hacia el set interno de 7 emociones que ya
    # usa EmotionDetector. "Perdido" no tiene un equivalente exacto --
    # se mapea a "confusión" por ser lo más cercano.
    _MOOD_LABEL_MAP = {
        "triste": "tristeza",
        "ansioso": "ansiedad",
        "enojado": "enojo",
        "perdido": "confusión",
        "bien": "calma",
    }

    def __init__(self):
        # FIX (Groq): self.client (Ollama) se mantiene con dos roles:
        # (1) fallback si Groq no tiene cupo o falla en el momento, y
        # (2) motor del clasificador _needs_web_search, a propósito --
        # es una tarea de sí/no barata y no vale la pena gastarle cupo
        # gratis a Groq en eso, dejándolo libre para respuestas reales.
        self.client = OllamaClient()
        self.groq_client = GroqClient()
        self.rate_limiter = GroqRateLimiter()
        self.memory = MemoryEngine()
        self.prompt_builder = PromptBuilder()
        self.emotion_detector = EmotionDetector(self.groq_client, self.rate_limiter)
        self.risk_detector = RiskDetector()
        self.clinical_detector = ClinicalSignalDetector()

    async def ask(
        self,
        user_id: str,
        message: str,
        conversation_id: str | None = None,
    ) -> dict:
        """
        Devuelve {"answer": str, "is_crisis_response": bool,
        "conversation_id": str} -- si no se pasa conversation_id, se crea
        una conversación nueva automáticamente (primer mensaje de una
        sesión nueva).
        """

        if not conversation_id:
            conversation_id = await self.memory.create_conversation(user_id)
            is_first_message = True
        else:
            existing_count = await self.memory.count_conversation_messages(conversation_id)
            is_first_message = existing_count == 0

        is_crisis = self.risk_detector.detect(message)

        # FIX (título automático): se deriva del primer mensaje de la
        # conversación, en vez de dejar "Nueva conversación" para
        # siempre. EXCEPCIÓN deliberada: si ese primer mensaje dispara
        # el detector de riesgo, NO se usa como título -- dejaría una
        # frase sensible visible permanentemente en el listado del
        # sidebar (mismo criterio que ya aplicamos al no mostrar
        # risk_events en crudo en la pantalla de perfil).
        if is_first_message and not is_crisis:
            title = self._derive_title(message)
            await self.memory.set_conversation_title(conversation_id, title)

        if is_crisis:
            await self._record_crisis_turn(user_id, conversation_id, message)
            await self.memory.mark_risk_event(user_id)
            return {
                "answer": CRISIS_RESPONSE_MESSAGE,
                "is_crisis_response": True,
                "conversation_id": conversation_id,
            }

        rule_emotions = detect_by_rules(message)

        emotion = await self.emotion_detector.detect(
            message,
            rule_emotions
        )

        history, summary, relevant_memory, profile = await self.memory.process(
            user_id,
            conversation_id,
            message,
            emotion
        )

        emotion_style = get_emotion_style(emotion)

        clinical_categories = self.clinical_detector.detect(message)
        for category in clinical_categories:
            await self.memory.mark_clinical_signal(user_id, category)

        suggest_professional_category = None
        for category in clinical_categories:
            if await self.memory.should_suggest_professional(user_id, category):
                suggest_professional_category = category
                break

        care_mode = await self.memory.is_in_care_mode(user_id)

        messages = self.prompt_builder.build(
            message=message,
            history=history,
            emotion_style=emotion_style,
            summary=summary,
            profile=profile,
            relevant_memory=relevant_memory,
            care_mode=care_mode,
            suggest_professional=bool(suggest_professional_category)
        )

        needs_search = await self._needs_web_search(message)

        answer = await self._generate_answer(
            messages,
            tools=[WEB_SEARCH_TOOL_SCHEMA] if needs_search else None,
            tool_executors=(
                {"buscar_en_internet": execute_web_search}
                if needs_search else None
            ),
        )

        answer = self._strip_meta_comments(answer)
        answer = self._cap_questions(answer)
        answer = self._extract_self_correction(answer)

        if self._GENERIC_REFUSAL_PATTERN.match(answer.strip()):
            logger.warning(
                f"Rechazo genérico detectado y reemplazado. "
                f"Respuesta original del modelo: {answer!r}"
            )
            answer = self._REFUSAL_FALLBACK
        else:
            answer = self._strip_leading_apology(answer)

        try:
            await self.memory.after_response(
                user_id,
                conversation_id,
                message,
                answer,
                emotion
            )
        except Exception as e:
            logger.error(
                f"Error en after_response (memoria) -- la respuesta al "
                f"usuario ya se generó bien y no debe perderse por esto: {e!r}"
            )

        if suggest_professional_category:
            await self.memory.mark_professional_suggested(
                user_id,
                suggest_professional_category
            )

        return {
            "answer": answer,
            "is_crisis_response": False,
            "conversation_id": conversation_id,
        }

    def _derive_title(self, message: str, max_length: int = 45) -> str:
        """
        Deriva un título corto a partir del primer mensaje de la
        conversación -- truncado en un límite de palabra (no corta una
        palabra a la mitad), con "..." si hizo falta recortar.
        """
        text = message.strip()

        if len(text) <= max_length:
            return text

        truncated = text[:max_length].rsplit(" ", 1)[0]
        return f"{truncated}..."
    
    # FIX (Groq + rate limiter): antes había una sola llamada directa a
    # self.client.chat() (Ollama). Ahora se intenta primero con Groq
    # (mejor modelo, sin los bugs erráticos del 8B local), pero
    # protegido por el rate limiter -- si no hay cupo (RPM/TPM/RPD) o
    # si Groq falla en el momento (network, 429 igual, etc.), cae a
    # Ollama local sin que el usuario note nada distinto más que la
    # latencia. El usuario NUNCA se queda sin respuesta por esto.
    async def _generate_answer(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_executors: dict | None = None,
    ) -> str:
        estimated_tokens = GroqRateLimiter.estimate_tokens(messages)
        allowed, reason = await self.rate_limiter.acquire(estimated_tokens)

        if allowed:
            try:
                return await self.groq_client.chat(
                    messages, tools=tools, tool_executors=tool_executors
                )
            except Exception as e:
                logger.warning(
                    f"Groq falló pese a tener cupo disponible -- "
                    f"cae a Ollama local: {e!r}"
                )
        else:
            logger.info(
                f"Cupo gratis de Groq agotado ({reason}) -- "
                f"cae a Ollama local para esta respuesta."
            )

        return await self.client.chat(
            messages, tools=tools, tool_executors=tool_executors
        )

    def _strip_meta_comments(self, text: str) -> str:
        cleaned = self._META_COMMENT_PATTERN.sub("", text)
        cleaned = self._BARE_INFINITIVE_META_PATTERN.sub("", cleaned)
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        return cleaned.strip()

    # FIX: red de seguridad para la regla "máximo una pregunta por
    # respuesta" del system prompt -- ya vimos que el modelo (incluso
    # con la regla explícita y ejemplos) a veces sigue encadenando
    # preguntas. Esto es un backstop determinístico: si aparece más de
    # una oración que termina en "?", se descartan las preguntas extra,
    # dejando solo la primera. División de oraciones por heurística
    # simple (puntuación) -- pensada para respuestas de chat cortas, no
    # para texto largo con abreviaciones/decimales.
    def _cap_questions(self, text: str) -> str:
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())

        result = []
        seen_question = False

        for sentence in sentences:
            is_question = sentence.rstrip().endswith('?')

            if is_question and seen_question:
                continue  # descartar preguntas extra

            if is_question:
                seen_question = True

            result.append(sentence)

        return ' '.join(result)

    def _extract_self_correction(self, text: str) -> str:
        """
        Si el modelo inventó un preámbulo tipo "hubo un problema con la
        respuesta anterior" y armó una versión corregida entre comillas,
        se extrae SOLO lo que está entre comillas (la respuesta real y
        usable), descartando el preámbulo de auto-crítica inventada.
        Si no matchea ese patrón, devuelve el texto sin tocar.
        """
        match = self._SELF_CORRECTION_PATTERN.match(text.strip())

        if match:
            return match.group("quoted").strip()

        return text

    def _strip_leading_apology(self, text: str) -> str:
        """
        Saca un "Lo siento, pero" vacío del inicio de la respuesta
        (ej. "Lo siento, pero puedo ayudarte con eso" -> "Puedo
        ayudarte con eso"), capitalizando la letra siguiente.

        A diferencia de _GENERIC_REFUSAL_PATTERN (que reemplaza TODA
        la respuesta por un fallback cuando es un rechazo genuino real),
        acá solo se recorta el prefijo -- lo que viene después de "pero"
        ya es contenido real y útil, no hace falta descartarlo.

        Este método debe llamarse SOLO cuando _GENERIC_REFUSAL_PATTERN
        ya determinó que no es un rechazo genuino -- si lo fuera, ese
        caso ya se resolvió reemplazando toda la respuesta antes de
        llegar acá.
        """
        match = self._LEADING_APOLOGY_PATTERN.match(text)

        if not match:
            return text

        remainder = text[match.end():]

        if not remainder:
            # No debería pasar en la práctica (matchear "lo siento,
            # pero" y no dejar nada después) -- pero si pasa, mejor
            # devolver el texto original que una respuesta vacía.
            return text

        return remainder[0].upper() + remainder[1:]

    async def _record_crisis_turn(
        self, user_id: str, conversation_id: str, message: str
    ):
        await self.memory._conversation.add_user_message(conversation_id, message)
        await self.memory._conversation.add_assistant_message(
            conversation_id,
            CRISIS_RESPONSE_MESSAGE
        )

    # -----------------------------------------------------
    # Gestión de conversaciones
    # -----------------------------------------------------

    async def list_conversations(self, user_id: str) -> list:
        return await self.memory.list_conversations(user_id)

    async def get_conversation_messages(
        self,
        user_id: str,
        conversation_id: str,
        limit: int = 20,
        before: float = None,
    ) -> list | None:
        """Devuelve None si la conversación no existe o no pertenece a
        este usuario (para que el router devuelva 404, no datos ajenos)."""
        conversation = await self.memory.get_conversation(conversation_id, user_id)
        if not conversation:
            return None

        return await self.memory.get_paginated_history(
            conversation_id, limit, before
        )

    async def delete_conversation(self, user_id: str, conversation_id: str) -> bool:
        return await self.memory.delete_conversation(conversation_id, user_id)

    # -----------------------------------------------------
    # Mood manual
    # -----------------------------------------------------

    async def log_mood(self, user_id: str, mood_label: str) -> str:
        """
        Recibe la etiqueta en español del selector de la UI (ej.
        "triste"), la traduce al set interno de emociones, y la guarda.
        Devuelve la emoción interna guardada.
        """
        normalized = mood_label.strip().lower()
        internal_emotion = self._MOOD_LABEL_MAP.get(normalized, normalized)

        await self.memory.log_manual_mood(user_id, internal_emotion)
        return internal_emotion

    # -----------------------------------------------------
    # Progreso
    # -----------------------------------------------------

    async def get_emotion_trend(self, user_id: str, days: int = 14) -> list:
        return await self.memory.get_emotion_trend(user_id, days)

    # -----------------------------------------------------
    # Perfil / borrado
    # -----------------------------------------------------

    async def delete_user_data(self, user_id: str) -> bool:
        return await self.memory.delete_user_data(user_id)

    async def get_profile(self, user_id: str) -> dict:
        profile = await self.memory.get_profile(user_id)
        profile.pop("_id", None)
        return profile
    
    # FIX: reemplaza el enfoque de keywords -- una lista fija nunca
    # generaliza bien ("cartelera", "estreno", "dólar", "restaurante
    # abierto ahora" son infinitos casos nuevos que se escapan). En vez
    # de eso, se le pregunta al propio modelo, con un prompt acotado a
    # una sola pregunta de sí/no, sin herramientas ni contexto pesado --
    # una tarea de clasificación simple donde el LLM es confiable, en
    # vez de dejarle la decisión de usar o no una tool en medio de una
    # respuesta larga (que es donde vimos que fallaba).
    
    async def _needs_web_search(self, message: str) -> bool:
        classifier_messages = [
            {
                "role": "system",
                "content": (
                    "Respondé ÚNICAMENTE con la palabra SI o NO, sin "
                    "explicación ni puntuación adicional.\n\n"
                    "¿El siguiente mensaje de un usuario requiere buscar "
                    "información actual en internet para responder bien "
                    "(noticias, precios, horarios, cartelera, resultados, "
                    "clima, eventos, datos que cambian con el tiempo o "
                    "que dependen de dónde/cuándo está la persona)?\n\n"
                    "Los mensajes personales, emocionales, de charla "
                    "general, o preguntas que se pueden responder con "
                    "conocimiento general (sin necesidad de datos de HOY) "
                    "son NO."
                )
            },
            {"role": "user", "content": message}
        ]

        try:
            raw = await self.client.chat(
                classifier_messages,
                options={"num_predict": 5}
            )
        except Exception as e:
            logger.warning(f"Error en clasificador de búsqueda: {e!r}")
            return False

        return raw.strip().upper().startswith("SI")
    
    # FIX (background memory): after_response ya no bloquea la respuesta
    # al usuario. Antes, si el MemoryExtractor tardaba o fallaba, el
    # usuario se quedaba esperando (o directamente recibía un 500) por
    # un paso que es "bonus" desde su perspectiva -- él ya tiene su
    # respuesta generada, guardar la memoria puede pasar en paralelo sin
    # que lo note. El try/except adentro asegura que un fallo acá nunca
    # se propague -- como corre en background, una excepción sin capturar
    # quedaría silenciosa en el event loop, así que se loguea explícito.
    async def _safe_after_response(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        answer: str,
        emotion: str,
    ):
        try:
            asyncio.create_task(
            self._safe_after_response(
                user_id, conversation_id, message, answer, emotion
            )
        )
        except Exception as e:
            logger.error(
                f"Error en after_response (memoria, background) -- "
                f"la respuesta al usuario ya se había enviado antes de "
                f"este fallo, no se ve afectada: {e!r}"
            )