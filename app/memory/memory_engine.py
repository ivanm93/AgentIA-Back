from app.memory.conversation_manager import ConversationManager
from app.memory.user_profile_manager import UserProfileManager
from app.memory.memory_retriever import MemoryRetriever

from app.llm.summarizer import Summarizer
from app.core.logging_config import get_logger

logger = get_logger(__name__)
from app.memory.memory_extractor import MemoryExtractor
from app.llm.embedding_client import EmbeddingClient
from app.memory.memory_consolidator import MemoryConsolidator
from app.memory.memory_consistency import MemoryConsistency
from app.memory.memory_validator import MemoryValidator
from app.memory.memory_scorer import MemoryScorer
from app.memory.memory_ranker import MemoryRanker
from app.memory.topic_builder import TopicBuilder

import time

class MemoryEngine:

    # FIX (resumen de conversación): cada N mensajes que "caen" fuera de
    # la ventana de contexto reciente (ConversationManager.max_messages),
    # se genera/actualiza un resumen -- así ese contexto no se pierde
    # sin dejar rastro cuando la conversación se alarga.
    _SUMMARY_TRIGGER_INTERVAL = 10

    def __init__(self):

        self._conversation = ConversationManager()
        self._profile = UserProfileManager()
        self._retriever = MemoryRetriever()
        self._summarizer = Summarizer()
        self._extractor = MemoryExtractor()
        self._embedding = EmbeddingClient()
        self._consolidator = MemoryConsolidator()
        self._consistency = MemoryConsistency()
        self._validator = MemoryValidator()
        self._scorer = MemoryScorer()
        self._ranker = MemoryRanker()
        self._topic_builder = TopicBuilder()

    async def apply_forgetting_curve(self, user_id: str):
        await self._profile.apply_forgetting(user_id)

    async def mark_risk_event(self, user_id: str):
        await self._profile.mark_risk_event(user_id)

    async def is_in_care_mode(self, user_id: str) -> bool:
        return await self._profile.is_in_care_mode(user_id)

    async def mark_clinical_signal(self, user_id: str, category: str):
        await self._profile.mark_clinical_signal(user_id, category)

    async def should_suggest_professional(
        self, user_id: str, category: str
    ) -> bool:
        return await self._profile.should_suggest_professional(
            user_id, category
        )

    async def mark_professional_suggested(self, user_id: str, category: str):
        await self._profile.mark_professional_suggested(user_id, category)

    async def get_profile(self, user_id: str) -> dict:
        return await self._profile.get_profile(user_id)

    # -----------------------------------------------------
    # FIX (múltiples conversaciones): wrappers de metadata de
    # conversación. El perfil (identity/facts/emotions/riesgo) sigue
    # siendo por user_id -- cruza todas las conversaciones. Solo el
    # historial de mensajes vive por conversation_id.
    # -----------------------------------------------------

    async def create_conversation(self, user_id: str, title: str = "Nueva conversación") -> str:
        return await self._conversation.create_conversation(user_id, title)

    # FIX (título automático): wrappers para que ChatService pueda saber
    # si un mensaje es el primero de la conversación, y ponerle un
    # título derivado de ese mensaje en vez de dejar "Nueva conversación"
    # para siempre.
    async def count_conversation_messages(self, conversation_id: str) -> int:
        return await self._conversation.count_messages(conversation_id)

    async def set_conversation_title(self, conversation_id: str, title: str):
        await self._conversation.set_title(conversation_id, title)

    async def list_conversations(self, user_id: str) -> list:
        return await self._conversation.list_conversations(user_id)

    async def get_conversation(self, conversation_id: str, user_id: str) -> dict | None:
        return await self._conversation.get_conversation(conversation_id, user_id)

    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        return await self._conversation.delete_conversation(conversation_id, user_id)

    async def get_paginated_history(
        self,
        conversation_id: str,
        limit: int = 20,
        before: float = None,
    ) -> list:
        return await self._conversation.get_paginated_history(
            conversation_id, limit, before
        )

    # -----------------------------------------------------
    # FIX (mood manual): reutiliza UserProfileManager.add_emotion tal
    # cual -- un mood elegido a mano por el usuario y una emoción
    # detectada automáticamente del mensaje terminan en la misma lista
    # de "emotions" del perfil. No se distingue el origen (no hay campo
    # "source"); es una simplificación consciente para no tocar el
    # esquema del perfil por una funcionalidad chica.
    # -----------------------------------------------------

    async def log_manual_mood(self, user_id: str, mood: str):
        await self._profile.add_emotion(user_id, mood)

    # -----------------------------------------------------
    # FIX (mejora #4 pendiente -- patrón sostenido): agrega tendencia
    # emocional por día, para la pantalla de "Mi progreso". No es
    # diagnóstico, es solo la cuenta de qué emociones aparecieron cada
    # día en los últimos `days`.
    # -----------------------------------------------------

    async def get_emotion_trend(self, user_id: str, days: int = 14) -> list:
        profile = await self._profile.get_profile(user_id)
        emotions = profile.get("emotions", [])

        cutoff = time.time() - (days * 86400)
        recent = [e for e in emotions if e.get("timestamp", 0) >= cutoff]

        # agrupar por día (YYYY-MM-DD) sumando cuántas veces apareció
        # cada emoción ese día
        from datetime import datetime, timezone

        by_day = {}
        for e in recent:
            day = datetime.fromtimestamp(
                e["timestamp"], tz=timezone.utc
            ).strftime("%Y-%m-%d")
            by_day.setdefault(day, {})
            emotion_value = e.get("value", "neutral")
            by_day[day][emotion_value] = by_day[day].get(emotion_value, 0) + 1

        return [
            {"date": day, "counts": counts}
            for day, counts in sorted(by_day.items())
        ]

    # -----------------------------------------------------

    async def delete_user_data(self, user_id: str) -> bool:
        """
        Elimina todos los datos conocidos de un usuario: perfil (identity,
        facts, topics, emotions), y TODAS sus conversaciones/mensajes.
        Devuelve True si había datos para borrar.
        """
        profile_existed = await self._profile.delete_profile(user_id)
        history_existed = await self._conversation.delete_history(user_id)

        return profile_existed or history_existed

    # -----------------------------------------------------
    # Flujo principal de chat
    # -----------------------------------------------------

    async def process(
        self,
        user_id,
        conversation_id,
        message,
        emotion
    ):
        # FIX (bug real, no relacionado al resumen): antes se guardaba el
        # mensaje del usuario ANTES de traer el historial, así que
        # get_history() lo incluía como último ítem -- y PromptBuilder
        # lo volvía a agregar aparte, mandando el mismo mensaje DOS VECES
        # al modelo. Esto causaba respuestas raras tipo "hay una
        # repetición innecesaria" -- el modelo no alucinaba, reaccionaba
        # (mal) a una duplicación real que nosotros mismos introducíamos.
        #
        # Ahora se trae el historial PRIMERO (sin el mensaje actual
        # todavía), y recién después se persiste -- así PromptBuilder es
        # el único lugar que agrega el mensaje actual, una sola vez.
        await self._profile.apply_forgetting(user_id)

        # FIX (independencia de proveedor externo): embed() ahora llama
        # a una API externa (Gemini) -- puede fallar por red, cupo
        # agotado, timeout, etc. Antes esto rompía el request ENTERO con
        # un 500 (lo vimos en producción con el túnel de Ollama caído).
        # Ahora un fallo acá se loguea y el flujo sigue sin el embedding
        # -- degradación, no caída total. (Nota aparte, sin tocar por
        # ahora: query_embedding no se usa en ningún lado después de
        # calcularse -- self._retriever.retrieve() recibe profile/message
        # crudos, no el embedding. Parece una integración a medio hacer;
        # se mantiene el cálculo por si acaso, pero vale la pena revisar
        # si hace falta en absoluto.)
        try:
            query_embedding = await self._embedding.embed(message)
        except Exception as e:
            logger.warning(
                f"Error generando embedding del mensaje -- se continúa "
                f"sin él: {e!r}"
            )
            query_embedding = None

        profile = await self._profile.get_profile(user_id)

        relevant_memory = self._retriever.retrieve(
            profile,
            message
        )

        history = await self._conversation.get_history(conversation_id)
        summary = await self._conversation.get_summary(conversation_id) or ""
        profile = await self._profile.get_profile(user_id)

        await self._conversation.add_user_message(conversation_id, message)

        return history, summary, relevant_memory, profile

    async def after_response(
        self,
        user_id,
        conversation_id,
        user_message,
        assistant_answer,
        emotion
    ):

        await self._conversation.add_assistant_message(
            conversation_id,
            assistant_answer
        )

        profile = await self._profile.get_profile(user_id)

        extracted = await self._extractor.extract(
            user_message,
            emotion,
            profile
        )
        extracted = self._validator.validate(extracted, user_message)

        if not extracted:
            return

        identity = extracted.get("identity")
        profile = self._consistency.apply(profile, extracted)

        scored_facts = [
            f for f in extracted["facts"]
            if self._scorer.score_fact(f) > 0.5
        ]
        if identity:
            await self._profile.update_identity(
                user_id,
                identity
            )

        cleared_fields = extracted.get("cleared_fields", [])
        await self._profile.clear_identity_fields(user_id, cleared_fields)

        for fact in scored_facts:
            await self._profile.add_fact(
                user_id,
                fact["value"],
                fact.get("priority", 1)
            )

        current_topics = profile.get("topics", [])

        for topic in (extracted.get("topics") or []):
            # FIX (mismo criterio que en process()): un fallo generando
            # el embedding del topic no debe tumbar el resto de
            # after_response() -- el guardado de memoria de este turno
            # es un "bonus" desde la perspectiva del usuario (la
            # respuesta ya se le mandó antes de llegar acá). (Misma nota
            # que arriba: `embedding` tampoco se usa después -- se pasa
            # solo `[topic]`, no el embedding, a topic_builder.build().)
            try:
                embedding = await self._embedding.embed(topic["value"])
            except Exception as e:
                logger.warning(
                    f"Error generando embedding de topic -- se continúa "
                    f"sin él: {e!r}"
                )
                embedding = None

            current_topics = self._topic_builder.build(
                current_topics,
                [topic]
            )

        await self._profile.set_topics(user_id, current_topics)

        await self._profile.add_emotion(user_id, emotion)
        await self._profile.cleanup(user_id)
        await self._profile.apply_forgetting(user_id)
        profile = await self._profile.get_profile(user_id)

        self._consolidator.consolidate(profile)
        profile = self._ranker.rank(profile)
        profile = self._ranker.cleanup(profile)

        await self._profile.set_facts(user_id, profile.get("facts", []))
        await self._profile.set_topics(user_id, profile.get("topics", []))

        # FIX (resumen de conversación): Summarizer existía como clase
        # pero nunca se llamaba en ningún lado -- get_summary() siempre
        # devolvía None, y en conversaciones largas todo lo anterior a
        # los últimos `max_messages` se perdía sin ninguna compensación.
        await self._maybe_update_summary(conversation_id)

        # FIX: esto era un print() de debug que se colaba en TODOS los
        # logs de producción, con el perfil completo en cada turno --
        # mucho ruido. Ahora es nivel DEBUG, así que con el LOG_LEVEL
        # por defecto (INFO) no aparece. Para volver a verlo mientras
        # testeás localmente, seteá la variable de entorno:
        #   LOG_LEVEL=DEBUG
        logger.debug(f"Perfil actualizado para user_id={user_id}: {profile}")

    async def _maybe_update_summary(self, conversation_id: str):
        total_messages = await self._conversation.count_messages(conversation_id)
        outside_window = total_messages - self._conversation.max_messages

        if outside_window <= 0:
            return

        if outside_window % self._SUMMARY_TRIGGER_INTERVAL != 0:
            return

        older_messages = await self._conversation.get_messages_outside_recent_window(
            conversation_id, keep_last=self._conversation.max_messages
        )

        if not older_messages:
            return

        summary = await self._summarizer.summarize(older_messages)

        # Si falla (Ollama caído, timeout, etc.), no rompemos el flujo --
        # simplemente no se actualiza el resumen esta vez, se reintenta
        # en el próximo disparo.
        if summary:
            await self._conversation.set_summary(conversation_id, summary)