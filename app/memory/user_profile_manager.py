# app/memory/user_profile_manager.py
#
# Versión respaldada por MongoDB (via motor, driver async) de
# UserProfileManager. Mantiene los MISMOS nombres de método y misma forma
# de datos que la versión anterior en memoria (dict/defaultdict) -- la
# diferencia es que ahora cada método es `async def` y hace `await` a
# Mongo en vez de tocar un dict local.
#
# Esto significa que MemoryEngine necesita hacer `await` en cada llamada
# a estos métodos (antes eran llamadas directas, sin await).

import time

from app.db.mongo import get_collection


DEFAULT_IDENTITY = {
    "name": None,
    "profession": None,
    "location": None,
    "language": None,
    "goals": [],
    "preferences": [],
}


class UserProfileManager:

    def __init__(self):
        self._collection = get_collection("profiles")

    # -----------------------------------------------------
    # Helper interno: obtiene el documento de perfil, creándolo si no
    # existe (equivalente al comportamiento de defaultdict de la versión
    # en memoria, que creaba el perfil por defecto al primer acceso).
    # -----------------------------------------------------
    async def _get_or_create(self, user_id: str) -> dict:
        doc = await self._collection.find_one({"user_id": user_id})

        if doc is None:
            doc = {
                "user_id": user_id,
                "identity": dict(DEFAULT_IDENTITY),
                "facts": [],
                "topics": [],
                "emotions": [],
                "risk_events": [],
                "clinical_signals": {},
            }
            await self._collection.insert_one(doc)

        return doc

    # -----------------------------------------------------

    async def get_profile(self, user_id: str) -> dict:
        return await self._get_or_create(user_id)

    async def add_fact(self, user_id: str, fact: str, priority: int = 1):
        await self._get_or_create(user_id)  # asegura que el doc exista
        await self._collection.update_one(
            {"user_id": user_id},
            {"$push": {"facts": {
                "value": fact,
                "priority": priority,
                "timestamp": time.time()
            }}}
        )

    async def add_or_strengthen_topic(
        self,
        user_id: str,
        value: str,
        embedding: list
    ):
        """
        Si existe un topic similar (coseno > 0.85) lo fortalece y promedia
        el embedding. Si no existe, lo crea.
        """
        profile = await self._get_or_create(user_id)
        topics = profile.get("topics", [])

        for topic in topics:
            if "embedding" not in topic:
                continue

            sim = self._cosine_similarity(topic["embedding"], embedding)
            if sim > 0.85:
                topic["strength"] = topic.get("strength", 1.0) + 0.2
                topic["evidence_count"] = topic.get("evidence_count", 0) + 1
                topic["embedding"] = [
                    (a + b) / 2
                    for a, b in zip(topic["embedding"], embedding)
                ]
                topic["last_updated"] = time.time()
                topic["last_accessed"] = time.time()

                await self._collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"topics": topics}}
                )
                return

        # No existe -> crear
        new_topic = {
            "value": value,
            "embedding": embedding,
            "strength": 1.0,
            "evidence_count": 1,
            "priority": 3,
            "last_updated": time.time(),
            "last_accessed": time.time(),
        }

        await self._collection.update_one(
            {"user_id": user_id},
            {"$push": {"topics": new_topic}}
        )

    async def set_topics(self, user_id: str, topics: list):
        await self._get_or_create(user_id)
        await self._collection.update_one(
            {"user_id": user_id},
            {"$set": {"topics": topics}}
        )

    # FIX (migración a Mongo): en la versión en memoria, mutar el dict
    # `profile["facts"]` en el lugar (ej. desde MemoryConsolidator o
    # MemoryRanker) alcanzaba para "guardar" el cambio, porque era el
    # mismo objeto en RAM. Con Mongo, get_profile() devuelve una copia --
    # hace falta este método para persistir explícitamente esos cambios.
    async def set_facts(self, user_id: str, facts: list):
        await self._get_or_create(user_id)
        await self._collection.update_one(
            {"user_id": user_id},
            {"$set": {"facts": facts}}
        )

    async def add_emotion(self, user_id: str, emotion: str):
        await self._get_or_create(user_id)
        await self._collection.update_one(
            {"user_id": user_id},
            {"$push": {"emotions": {
                "value": emotion,
                "timestamp": time.time()
            }}}
        )

    async def apply_forgetting(
        self,
        user_id: str,
        decay_rate: float = 0.02,
        min_strength: float = 0.1,
    ):
        """
        Decaimiento exponencial por días de inactividad.
        Elimina topics que caen por debajo del umbral mínimo.
        """
        profile = await self._get_or_create(user_id)
        now = time.time()
        surviving = []

        for topic in profile.get("topics", []):
            last_accessed = topic.get(
                "last_accessed", topic.get("last_updated", now)
            )
            days_inactive = (now - last_accessed) / 86400
            decay = (1 - decay_rate) ** days_inactive
            topic["strength"] = topic.get("strength", 1.0) * decay

            if topic["strength"] >= min_strength:
                surviving.append(topic)

        await self._collection.update_one(
            {"user_id": user_id},
            {"$set": {"topics": surviving}}
        )

    async def cleanup(self, user_id: str, max_items: int = 20):
        """Mantiene solo los items más relevantes por prioridad y timestamp."""
        profile = await self._get_or_create(user_id)

        topics = profile.get("topics", [])
        topics.sort(
            key=lambda x: (
                x.get("strength", 0),
                x.get("priority", 0),
                x.get("last_updated", 0)
            ),
            reverse=True
        )
        topics = topics[:max_items]

        def sort_and_trim(items):
            items.sort(
                key=lambda x: (x.get("priority", 0), x.get("timestamp", 0)),
                reverse=True
            )
            return items[:max_items]

        facts = sort_and_trim(profile.get("facts", []))
        topics = sort_and_trim(topics)

        await self._collection.update_one(
            {"user_id": user_id},
            {"$set": {"facts": facts, "topics": topics}}
        )

    def _cosine_similarity(self, a: list, b: list) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        return dot / (norm_a * norm_b + 1e-8)

    async def update_identity(self, user_id: str, extracted: dict):
        profile = await self._get_or_create(user_id)
        identity = profile.get("identity", dict(DEFAULT_IDENTITY))

        for key, value in extracted.items():

            if value is None:
                continue

            if isinstance(value, list):

                current = identity.get(key, [])

                if not isinstance(current, list):
                    current = [current] if current else []

                normalized = []
                for v in value:
                    if isinstance(v, dict):
                        normalized.append(v.get("value") or str(v))
                    else:
                        normalized.append(v)

                identity[key] = list(set(current + normalized))

            else:
                identity[key] = value

        await self._collection.update_one(
            {"user_id": user_id},
            {"$set": {"identity": identity}}
        )

    async def get_identity(self, user_id: str) -> dict:
        profile = await self._get_or_create(user_id)
        return profile.get("identity", dict(DEFAULT_IDENTITY))

    async def clear_identity_fields(self, user_id: str, fields: list):
        if not fields:
            return

        _CLEARABLE = {"profession", "location", "language"}

        update = {
            f"identity.{field}": None
            for field in fields
            if field in _CLEARABLE
        }

        if not update:
            return

        await self._get_or_create(user_id)
        await self._collection.update_one(
            {"user_id": user_id},
            {"$set": update}
        )

    async def strengthen_fact(self, user_id: str, fact: str):
        profile = await self._get_or_create(user_id)
        facts = profile.get("facts", [])

        for f in facts:
            if f["value"] == fact:
                f["priority"] += 1
                f["timestamp"] = time.time()
                await self._collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"facts": facts}}
                )
                return

        await self.add_fact(user_id, fact)

    # -----------------------------------------------------
    # Modo cuidado post-crisis
    # -----------------------------------------------------

    async def mark_risk_event(self, user_id: str):
        await self._get_or_create(user_id)
        await self._collection.update_one(
            {"user_id": user_id},
            {"$push": {"risk_events": {"timestamp": time.time()}}}
        )

    async def is_in_care_mode(
        self,
        user_id: str,
        window_seconds: float = 1800,
    ) -> bool:
        profile = await self._get_or_create(user_id)
        risk_events = profile.get("risk_events", [])

        if not risk_events:
            return False

        last_event_time = risk_events[-1]["timestamp"]
        return (time.time() - last_event_time) <= window_seconds

    # -----------------------------------------------------
    # Guardrails temáticos (señales clínicas)
    # -----------------------------------------------------

    async def mark_clinical_signal(self, user_id: str, category: str):
        profile = await self._get_or_create(user_id)
        signals = profile.get("clinical_signals", {})

        if category not in signals:
            signals[category] = {"events": [], "suggested": False}

        signals[category]["events"].append(time.time())

        await self._collection.update_one(
            {"user_id": user_id},
            {"$set": {"clinical_signals": signals}}
        )

    async def get_clinical_signal_count(
        self, user_id: str, category: str
    ) -> int:
        profile = await self._get_or_create(user_id)
        signals = profile.get("clinical_signals", {})
        return len(signals.get(category, {}).get("events", []))

    async def should_suggest_professional(
        self,
        user_id: str,
        category: str,
        threshold: int = 2,
    ) -> bool:
        profile = await self._get_or_create(user_id)
        signals = profile.get("clinical_signals", {})
        entry = signals.get(category)

        if not entry:
            return False

        return len(entry["events"]) >= threshold and not entry["suggested"]

    async def mark_professional_suggested(self, user_id: str, category: str):
        profile = await self._get_or_create(user_id)
        signals = profile.get("clinical_signals", {})

        if category in signals:
            signals[category]["suggested"] = True
            await self._collection.update_one(
                {"user_id": user_id},
                {"$set": {"clinical_signals": signals}}
            )

    # -----------------------------------------------------
    # Borrado de datos
    # -----------------------------------------------------

    async def delete_profile(self, user_id: str) -> bool:
        result = await self._collection.delete_one({"user_id": user_id})
        return result.deleted_count > 0