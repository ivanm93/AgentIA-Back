class MemoryFilter:

    def filter(self, extracted):

        extracted["identity"] = self.filter_identity(
            extracted.get("identity", {})
        )

        extracted["facts"] = self.filter_facts(
            extracted.get("facts", [])
        )

        extracted["topics"] = self.filter_topics(
            extracted.get("topics", [])
        )

        return extracted
    def filter_identity(self, identity):

        goals = []

        for goal in identity.get("goals", []):

            if isinstance(goal, str):

                goal = goal.strip()

                if goal.endswith("?"):
                    continue

                goals.append(goal)

        identity["goals"] = goals

        return identity
    def filter_facts(self, facts):

        if not isinstance(facts, list):
            return []

        cleaned = []

        for fact in facts:

            if isinstance(fact, str):

                fact = fact.strip()

                # descartar preguntas o basura
                if fact.endswith("?"):
                    continue

                # descartar cosas demasiado cortas
                if len(fact) < 5:
                    continue

                cleaned.append({
                    "value": fact,
                    "priority": 1
                })

            elif isinstance(fact, dict):

                value = fact.get("value")

                if not value:
                    continue

                value = value.strip()

                if value.endswith("?"):
                    continue

                cleaned.append({
                    "value": value,
                    "priority": fact.get("priority", 1)
                })

        return cleaned