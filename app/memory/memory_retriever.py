import time

class MemoryRetriever:

    def retrieve(self, profile: dict, query: str) -> dict:

        return {
            "identity": self._retrieve_identity(profile.get("identity", {})),
            "facts": self._retrieve_facts(profile.get("facts", []), query),
            "topics": self._retrieve_topics(profile.get("topics", []), query),
        }
    
    def _retrieve_identity(self, identity):

        return identity

    def _retrieve_facts(self, facts, query):

        query = query.lower()
        query_words = set(query.split())

        # FIX: antes se devolvían siempre los top 5 facts por "strength",
        # incluso cuando NINGUNO tenía relación con el mensaje actual --
        # el bonus de +0.5 por coincidencia de palabras era solo para
        # ordenar, no para filtrar. Resultado real observado: un fact
        # viejo con mucho "strength" (ej. "preocupado por el dinero")
        # se colaba en CADA turno de la conversación sin importar el
        # tema, y el modelo terminaba mencionándolo sin venir a cuento.
        #
        # Ahora solo se devuelven facts que efectivamente comparten
        # alguna palabra con el mensaje actual -- si no hay ningún match
        # real, no se manda nada (es preferible no usar memoria a
        # inyectar memoria irrelevante en cada turno).
        scored = []

        for fact in facts:

            value = fact.get("value", "").lower()
            matched = any(word in value for word in query_words if len(word) >= 4)

            if not matched:
                continue

            score = fact.get("strength", 1.0) + 0.5
            scored.append((score, fact))

        scored.sort(reverse=True, key=lambda x: x[0])

        return [f for _, f in scored[:5]]
        
    def _retrieve_topics(self, topics, query):

        query = query.lower()
        query_words = set(query.split())

        # FIX: mismo problema y misma solución que en _retrieve_facts --
        # solo devolver topics con relevancia real al mensaje actual.
        scored = []

        for topic in topics:

            value = topic.get("value", "").lower()
            matched = value in query or any(
                w in value for w in query_words if len(w) >= 4
            )

            if not matched:
                continue

            score = topic.get("strength", 1.0) + 0.5
            scored.append((score, topic))

        scored.sort(reverse=True, key=lambda x: x[0])

        return [t for _, t in scored[:5]]

    def retrieve_emotions(self, profile):

        return profile["emotions"][-5:]

    def cosine_similarity(self, a, b):

        dot = sum(x * y for x, y in zip(a, b))

        norm_a = sum(x * x for x in a) ** 0.5

        norm_b = sum(x * x for x in b) ** 0.5

        return dot / (norm_a * norm_b + 1e-8)

    def calculate_score(
        self,
        topic,
        similarity
    ):

        strength = topic.get("strength", 1)
        priority = topic.get("priority", 1)
        evidence = topic.get("evidence_count", 1)
        last = topic.get("last_accessed", time.time())
        days = (time.time() - last) / 86400
        recency = 1 / (1 + days)

        return (
            similarity * 0.50 +
            strength  * 0.20 +
            priority  * 0.15 +
            evidence  * 0.10 +
            recency   * 0.05
        )