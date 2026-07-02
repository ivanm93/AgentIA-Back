class MemoryConsistency:

    def __init__(self):
        pass

    # =========================
    # ENTRY POINT
    # =========================

    def apply(self, profile: dict, extracted: dict) -> dict:

        identity = profile.get("identity", {})

        identity = self._merge_identity(identity, extracted.get("identity", {}))

        facts = self._merge_facts(
            profile.get("facts", []),
            extracted.get("facts", [])
        )

        topics = self._merge_topics(
            profile.get("topics", []),
            extracted.get("topics", [])
        )

        emotions = self._clean_emotions(
            profile.get("emotions", [])
        )

        profile["identity"] = identity
        profile["facts"] = facts
        profile["topics"] = topics
        profile["emotions"] = emotions

        return profile
    
    def _merge_identity(self, current: dict, new: dict):

        current = current or {}
        
        # merge simple fields
        for key in ["name", "profession", "location", "language"]:

            if new.get(key):
                current[key] = new[key]

        # goals cleanup
        goals = set(current.get("goals", []))

        for g in new.get("goals", []):
            if isinstance(g, dict):
                goals.add(g.get("value"))
            else:
                goals.add(g)

        # ❌ evitar duplicación profesión = goal
        profession = current.get("profession")

        if profession and profession in goals:
            goals.remove(profession)

        current["goals"] = list(goals)

        # preferences
        prefs = set(current.get("preferences", []))

        for p in new.get("preferences", []):
            prefs.add(p)

        current["preferences"] = list(prefs)

        return current
    
    def _merge_facts(self, current: list, new: list):

        existing = {f["value"] for f in current}

        for fact in new:

            value = fact.get("value")

            if not value:
                continue

            if value not in existing:
                current.append(fact)
                existing.add(value)

        return current
    
    def _merge_topics(self, current: list, new: list):

        existing = {t["value"] for t in current}

        for topic in new:

            value = topic.get("value")

            if not value:
                continue

            if value in existing:
                continue

            current.append(topic)
            existing.add(value)

        return current
    
    def _clean_emotions(self, emotions: list):

        cleaned = []

        for e in emotions[-20:]:

            val = e.get("value", "").lower()

            # filtrar ruido del LLM
            if "detectada" in val:
                continue

            if len(val) > 30:
                continue

            cleaned.append(e)

        return cleaned