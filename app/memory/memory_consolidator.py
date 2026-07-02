class MemoryConsolidator:

    def consolidate(self, profile):

        self.merge_duplicate_facts(profile)
        self.merge_duplicate_topics(profile)

    def merge_duplicate_facts(self, profile):

        unique = {}
        
        for fact in profile["facts"]:

            key = fact["value"].lower().strip()

            if key not in unique:
                unique[key] = fact
            else:
                unique[key]["priority"] = max(
                    unique[key]["priority"],
                    fact["priority"]
                )

        profile["facts"] = list(unique.values())

    def merge_duplicate_topics(self, profile):

        unique = {}

        for topic in profile["topics"]:

            key = topic["value"].lower().strip()

            if key not in unique:
                unique[key] = topic

            else:

                unique[key]["strength"] += topic["strength"]
                unique[key]["evidence_count"] += topic["evidence_count"]

        profile["topics"] = list(unique.values())

    def _consolidate_facts(self, facts):

        seen = {}

        for fact in facts:

            value = fact.get("value")

            if not value:
                continue

            key = value.lower().strip()

            if key in seen:
                # fusionar prioridad
                seen[key]["priority"] = max(
                    seen[key].get("priority", 1),
                    fact.get("priority", 1)
                )
            else:
                seen[key] = fact.copy()

        return list(seen.values())
    
    def _consolidate_topics(self, topics):

        merged = {}

        for topic in topics:

            value = topic.get("value", "")
            key = value.lower().strip()

            if key in merged:

                merged[key]["priority"] = max(
                    merged[key].get("priority", 1),
                    topic.get("priority", 1)
                )

                merged[key]["strength"] = merged[key].get("strength", 1) + 0.1

            else:
                merged[key] = topic.copy()

        return list(merged.values())