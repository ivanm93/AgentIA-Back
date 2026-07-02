class MemoryScorer:

    def score_fact(self, fact: dict) -> float:

        value = fact.get("value", "")

        score = 0.3  # base

        # más largo = más importante
        if len(value) > 20:
            score += 0.2

        # si tiene contexto fuerte
        if any(word in value.lower() for word in ["trabajo", "estoy", "estudiando", "proyecto"]):
            score += 0.3

        # penalizar cosas sueltas
        if len(value.split()) <= 2:
            score -= 0.2

        return max(0.0, min(1.0, score))
    
    def score_topic(self, topic: dict) -> float:

        value = topic.get("value", "")

        score = 0.4

        # temas técnicos valen más
        tech_keywords = [
            "python", "ai", "backend", "llm",
            "ollama", "api", "database"
        ]

        if any(k in value.lower() for k in tech_keywords):
            score += 0.3

        # penalizar ruido
        if len(value) < 4:
            score -= 0.3

        return max(0.0, min(1.0, score))
    
    def score_identity(self, key: str, value: str) -> float:

        score_map = {
            "profession": 1.0,
            "name": 1.0,
            "goals": 0.9,
            "preferences": 0.8,
            "location": 0.6,
            "language": 0.5
        }

        return score_map.get(key, 0.3)