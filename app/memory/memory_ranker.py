import time


class MemoryRanker:

    def rank(self, profile: dict) -> dict:

        self._rank_facts(profile.get("facts", []))
        self._rank_topics(profile.get("topics", []))

        return profile
    
    def _rank_facts(self, facts):

        now = time.time()

        for fact in facts:

            last = fact.get("last_accessed", now)
            age = now - last

            # decay natural
            decay = fact.get("decay", 0.01)
            fact["strength"] = fact.get("strength", 1.0) - (age * decay)

            # clamp
            fact["strength"] = max(0.0, fact["strength"])

    def _rank_topics(self, topics):

        for topic in topics:

            strength = topic.get("strength", 1.0)

            # reforzar si es técnico
            if any(k in topic["value"].lower() for k in ["python", "ai", "backend"]):
                strength += 0.2

            # penalizar ruido
            if len(topic["value"]) < 4:
                strength -= 0.3

            # FIX: max(3.0, strength) forzaba un MÍNIMO de 3.0, no un techo.
            # min() sí limita el máximo, y clamp con 0.0 evita que quede negativo
            # por la penalización de ruido.
            topic["strength"] = max(0.0, min(strength, 3.0))
    def cleanup(self, profile: dict, threshold: float = 0.2):

        profile["facts"] = [
            f for f in profile.get("facts", [])
            if f.get("strength", 1.0) > threshold
        ]

        profile["topics"] = [
            t for t in profile.get("topics", [])
            if t.get("strength", 1.0) > threshold
        ]

        return profile