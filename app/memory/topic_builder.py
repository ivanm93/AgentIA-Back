import time


class TopicBuilder:

    def build(self, existing_topics, new_topics):

        merged = existing_topics.copy()

        for new_topic in new_topics:

            value = new_topic["value"]
            priority = new_topic.get("priority", 1)

            match = self._find_similar(merged, value)

            if match:
                # FIX: al reforzar un topic existente, ahora también se
                # actualiza evidence_count y last_accessed. Antes solo se
                # tocaba priority, dejando evidence_count/strength/last_accessed
                # desactualizados para topics que pasan por este camino.
                match["priority"] = max(match.get("priority", 1), priority)
                match["evidence_count"] = match.get("evidence_count", 1) + 1
                match["last_accessed"] = time.time()
                continue

            # FIX: los topics nuevos ahora se crean con el mismo esquema que
            # usa UserProfileManager.add_or_strengthen_topic (strength,
            # evidence_count, last_updated, last_accessed). Antes solo tenían
            # value y priority, lo que causaba KeyError en
            # memory_consolidator.merge_duplicate_topics al acceder directo
            # a topic["strength"] / topic["evidence_count"].
            merged.append({
                "value": value,
                "priority": priority,
                "strength": 1.0,
                "evidence_count": 1,
                "last_updated": time.time(),
                "last_accessed": time.time(),
            })

        return merged

    def _find_similar(self, topics, value):

        value = value.lower()

        for topic in topics:

            existing = topic["value"].lower()

            # match simple por inclusión
            if value in existing or existing in value:
                return topic

        return None