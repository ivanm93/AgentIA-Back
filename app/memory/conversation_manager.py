# app/memory/conversation_manager.py
#
# FIX (múltiples conversaciones): antes había UN historial continuo por
# usuario. Ahora un usuario puede tener varias conversaciones (como
# "Conversación de hoy", "Esta semana", etc en la UI), cada una con su
# propio hilo de mensajes. El perfil emocional (identity/facts/emotions/
# riesgo) sigue siendo por usuario -- cruza todas las conversaciones,
# vive en UserProfileManager, que no cambia.
#
# Colecciones:
# - "conversations": metadata (uno por conversación: título, resumen,
#   timestamps)
# - "messages": mensajes individuales, cada uno con conversation_id

import time
from bson import ObjectId

from app.db.mongo import get_collection


class ConversationManager:

    def __init__(self):
        self._messages = get_collection("messages")
        self._conversations = get_collection("conversations")
        self.max_messages = 12

    # -----------------------------------------------------
    # Metadata de conversaciones
    # -----------------------------------------------------

    async def create_conversation(self, user_id: str, title: str = "Nueva conversación") -> str:
        now = time.time()
        doc = {
            "user_id": user_id,
            "title": title,
            "summary": None,
            "created_at": now,
            "last_message_at": now,
        }
        result = await self._conversations.insert_one(doc)
        return str(result.inserted_id)

    async def list_conversations(self, user_id: str) -> list:
        cursor = (
            self._conversations
            .find({"user_id": user_id})
            .sort("last_message_at", -1)
        )
        docs = await cursor.to_list(length=None)

        return [
            {
                "id": str(d["_id"]),
                "title": d["title"],
                "created_at": d["created_at"],
                "last_message_at": d["last_message_at"],
            }
            for d in docs
        ]

    async def get_conversation(self, conversation_id: str, user_id: str) -> dict | None:
        """
        Devuelve la conversación SOLO si pertenece a ese user_id --
        chequeo de ownership para que nadie pueda leer/escribir en la
        conversación de otro usuario adivinando/probando IDs.
        """
        try:
            oid = ObjectId(conversation_id)
        except Exception:
            return None

        return await self._conversations.find_one({"_id": oid, "user_id": user_id})

    async def touch_conversation(self, conversation_id: str):
        await self._conversations.update_one(
            {"_id": ObjectId(conversation_id)},
            {"$set": {"last_message_at": time.time()}}
        )

    async def set_title(self, conversation_id: str, title: str):
        await self._conversations.update_one(
            {"_id": ObjectId(conversation_id)},
            {"$set": {"title": title}}
        )

    async def get_summary(self, conversation_id: str):
        doc = await self._conversations.find_one({"_id": ObjectId(conversation_id)})
        return doc.get("summary") if doc else None

    async def set_summary(self, conversation_id: str, summary: str):
        await self._conversations.update_one(
            {"_id": ObjectId(conversation_id)},
            {"$set": {"summary": summary}}
        )

    # -----------------------------------------------------
    # Mensajes
    # -----------------------------------------------------

    async def get_history(self, conversation_id: str) -> list:
        """Últimos `max_messages`, en orden cronológico -- usado como
        contexto para el LLM."""
        cursor = (
            self._messages
            .find({"conversation_id": conversation_id})
            .sort("created_at", -1)
            .limit(self.max_messages)
        )
        docs = await cursor.to_list(length=self.max_messages)
        docs.reverse()

        return [{"role": d["role"], "content": d["content"]} for d in docs]

    async def get_paginated_history(
        self,
        conversation_id: str,
        limit: int = 20,
        before: float = None,
    ) -> list:
        query = {"conversation_id": conversation_id}

        if before is not None:
            query["created_at"] = {"$lt": before}

        cursor = (
            self._messages
            .find(query)
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        docs.reverse()

        return [
            {
                "role": d["role"],
                "content": d["content"],
                "created_at": d["created_at"],
            }
            for d in docs
        ]

    async def add_user_message(self, conversation_id: str, message: str):
        await self._messages.insert_one({
            "conversation_id": conversation_id,
            "role": "user",
            "content": message,
            "created_at": time.time(),
        })
        await self.touch_conversation(conversation_id)

    async def add_assistant_message(self, conversation_id: str, message: str):
        await self._messages.insert_one({
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": message,
            "created_at": time.time(),
        })
        await self.touch_conversation(conversation_id)

    # -----------------------------------------------------
    # Borrado
    # -----------------------------------------------------

    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """Borra una conversación puntual (y sus mensajes), verificando
        ownership."""
        conversation = await self.get_conversation(conversation_id, user_id)
        if not conversation:
            return False

        await self._messages.delete_many({"conversation_id": conversation_id})
        await self._conversations.delete_one({"_id": ObjectId(conversation_id)})
        return True

    async def delete_history(self, user_id: str) -> bool:
        """
        Borra TODAS las conversaciones y mensajes de un usuario -- usado
        por el borrado de cuenta completo (delete_user_data). Se
        mantiene el nombre del método por compatibilidad con
        MemoryEngine.delete_user_data.
        """
        conversations = await self._conversations.find(
            {"user_id": user_id}
        ).to_list(length=None)

        if not conversations:
            return False

        conversation_ids = [str(c["_id"]) for c in conversations]

        await self._messages.delete_many(
            {"conversation_id": {"$in": conversation_ids}}
        )
        await self._conversations.delete_many({"user_id": user_id})

        return True
