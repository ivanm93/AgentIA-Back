import re

from app.llm.ollama_client import OllamaClient
from app.prompts.prompt_builder import PromptBuilder
from app.llm.emotion.rule_detector import detect_by_rules
from app.llm.emotion.emotion_detector import EmotionDetector
from app.llm.emotion.emotion_style import get_emotion_style
from app.memory.memory_engine import MemoryEngine
from app.safety.risk_detector import RiskDetector
from app.safety.crisis_response import CRISIS_RESPONSE_MESSAGE
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

    _GENERIC_REFUSAL_PATTERN = re.compile(
        r"^\s*lo siento,?\s*(pero\s*)?no puedo (ayudarte|ayudar|hacer eso|"
        r"hablar de eso|continuar con eso)[^.!?]*[.!?]\s*"
        r"(si (necesitas|querés|quieres)[^.!?]*[.!?]\s*)?$",
        re.IGNORECASE
    )

    _REFUSAL_FALLBACK = (
        "Dale, sigamos. Contame lo que quieras, estoy para escucharte."
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
        self.client = OllamaClient()
        self.memory = MemoryEngine()
        self.prompt_builder = PromptBuilder()
        self.emotion_detector = EmotionDetector()
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

        if self.risk_detector.detect(message):
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

        answer = await self.client.chat(messages)

        answer = self._strip_meta_comments(answer)
        answer = self._cap_questions(answer)

        if self._GENERIC_REFUSAL_PATTERN.match(answer.strip()):
            print(
                f"[ChatService] Rechazo genérico detectado y reemplazado. "
                f"Respuesta original del modelo: {answer!r}"
            )
            answer = self._REFUSAL_FALLBACK

        await self.memory.after_response(
            user_id,
            conversation_id,
            message,
            answer,
            emotion
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