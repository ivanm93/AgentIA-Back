# app/repositories/user_repository.py
#
# Acceso a la colección "users" (autenticación). Separado de
# UserProfileManager a propósito -- ver diseno_backend.md: nunca se
# mezcla password_hash con datos sensibles de salud mental.

import time

from app.db.mongo import get_collection


class UserRepository:

    def __init__(self):
        self._collection = get_collection("users")

    async def get_by_email(self, email: str) -> dict | None:
        return await self._collection.find_one({"email": email})

    async def get_by_id(self, user_id: str) -> dict | None:
        from bson import ObjectId
        try:
            oid = ObjectId(user_id)
        except Exception:
            return None
        return await self._collection.find_one({"_id": oid})

    async def create(self, email: str, password_hash: str) -> dict:
        doc = {
            "email": email,
            "password_hash": password_hash,
            "created_at": time.time(),
            "last_login": None,
        }
        result = await self._collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    async def update_last_login(self, user_id: str):
        from bson import ObjectId
        await self._collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"last_login": time.time()}}
        )

    async def email_exists(self, email: str) -> bool:
        count = await self._collection.count_documents({"email": email})
        return count > 0