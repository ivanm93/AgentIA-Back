from app.memory.conversation_manager import ConversationManager
from app.memory.user_profile_manager import UserProfileManager
from app.memory.memory_retriever import MemoryRetriever

from app.llm.summarizer import Summarizer
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
        await self._conversation.add_user_message(conversation_id, message)
        await self._profile.apply_forgetting(user_id)
        query_embedding = await self._embedding.embed(message)

        profile = await self._profile.get_profile(user_id)

        relevant_memory = self._retriever.retrieve(
            profile,
            message
        )

        history = await self._conversation.get_history(conversation_id)
        summary = await self._conversation.get_summary(conversation_id) or ""
        profile = await self._profile.get_profile(user_id)

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
            embedding = await self._embedding.embed(topic["value"])
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

        print("\n===== PROFILE =====")
        print(profile)
        print("===================\n")
