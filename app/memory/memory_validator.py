import re
import unicodedata


class MemoryValidator:

    # palabras muy comunes que no cuentan como "evidencia" real de que un
    # valor extraído esté anclado al mensaje del usuario
    _STOPWORDS = {
        "que", "el", "la", "los", "las", "un", "una", "de", "del", "en",
        "es", "mi", "me", "tu", "su", "y", "o", "a", "para", "por", "con",
        "se", "lo", "le", "les", "como", "soy", "estoy", "esta", "este",
        "cual", "cuales", "quien", "quienes", "donde", "cuando", "porque",
    }

    # FIX (bug post-cambio de modelo): con llama3.1:8b empezamos a ver
    # expresiones vagas de ánimo ("todo mal", "cansado nomás") coladas
    # como FACTS -- pasan el grounding check porque literalmente están en
    # el mensaje, pero no son un hecho verificable, son una queja de
    # estado de ánimo que ya vive en "emotions". Esta lista es una
    # heurística de palabras: si un fact extraído está compuesto
    # ÚNICAMENTE por palabras de este tipo (sin ningún contenido
    # sustantivo adicional), se descarta como fact.
    _MOOD_ONLY_WORDS = {
        "mal", "bien", "mas", "menos", "muy", "todo", "toda", "todos",
        "todas", "nada", "algo", "asi", "nomas", "nomás", "regular",
        "cansado", "cansada", "cansancio", "triste", "tristeza",
        "feliz", "felicidad", "alegre", "alegria", "alegría",
        "enojado", "enojada", "enojo", "ansioso", "ansiosa", "ansiedad",
        "confundido", "confundida", "confusion", "confusión",
        "tranquilo", "tranquila", "calma", "bien", "peor", "mejor",
    }

    # FIX (bug post-cambio de modelo): topics que en realidad son
    # emociones ("tristeza" como topic) -- se filtran con la misma lista
    # de emociones válidas que usa EmotionDetector.
    _EMOTION_WORDS = {
        "enojo", "tristeza", "ansiedad", "confusion", "confusión",
        "calma", "alegria", "alegría", "neutral",
    }

    def validate(self, extracted, message: str = ""):

        if not isinstance(extracted, dict):
            extracted = {}

        extracted.setdefault("identity", {})
        extracted.setdefault("facts", [])
        extracted.setdefault("topics", [])
        extracted.setdefault("emotion_pattern", None)
        extracted.setdefault("cleared_fields", [])

        # FIX (grounding check, capa 1): si el mensaje del usuario es una
        # pregunta, ninguna extracción de identity/facts/topics/cleared_fields
        # de ESTE turno es confiable — el modelo tiende a "responderse a sí
        # mismo" y colar la pregunta (parafraseada o no) como si fuera
        # información nueva del usuario. En ese caso se descarta todo salvo
        # la emoción, sin importar qué haya devuelto el LLM.
        if self._is_question(message):
            extracted["identity"] = self.validate_identity({}, message="")
            extracted["facts"] = []
            extracted["topics"] = []
            extracted["cleared_fields"] = []
            return extracted

        extracted["identity"] = self.validate_identity(
            extracted["identity"],
            message
        )

        extracted["facts"] = self.validate_facts(
            extracted["facts"],
            message
        )

        extracted["topics"] = self.validate_topics(
            extracted["topics"]
        )

        # cleared_fields: whitelist + grounding check. Una negación
        # explícita también debe estar anclada al mensaje real (evita que
        # el modelo "limpie" un campo sin que el usuario lo haya negado).
        extracted["cleared_fields"] = self._validate_cleared_fields(
            extracted["cleared_fields"],
            message
        )

        return extracted

    def _validate_cleared_fields(self, cleared_fields, message: str):

        if not isinstance(cleared_fields, list):
            return []

        _CLEARABLE = {"profession", "location", "language"}

        valid = [
            f for f in cleared_fields
            if isinstance(f, str) and f in _CLEARABLE
        ]

        # grounding check: la negación debe tener alguna evidencia de
        # negación en el texto (ya, no, renunci, dej, etc), no solo confiar
        # ciegamente en que el LLM marcó el campo correctamente.
        _NEGATION_HINTS = {
            "ya", "no", "renuncie", "renuncio", "deje", "dejo",
            "cambie", "cambio", "termine", "termino",
        }

        if not message:
            return []

        message_words = self._significant_words(message) | set(
            re.findall(r"[a-z]+", self._normalize_text(message))
        )

        if not (message_words & _NEGATION_HINTS):
            return []

        return valid

    def _is_question(self, message: str) -> bool:
        if not message:
            return False
        text = message.strip()
        return "?" in text or text.startswith("¿")

    def validate_identity(self, identity, message: str = ""):

        if not isinstance(identity, dict):
            identity = {}

        # FIX: antes se usaba setdefault() sobre el dict tal cual venía del
        # LLM, lo que dejaba pasar campos fuera del esquema (ej. "hobbies")
        # sin ningún control de tipo. Si el LLM devolvía ese campo como
        # string en un turno y como lista en otro, update_identity crasheaba
        # con TypeError al intentar concatenar str + list.
        #
        # Ahora se reconstruye el dict desde cero usando SOLO los campos
        # conocidos del esquema (whitelist), descartando cualquier otro
        # campo que el LLM haya inventado.
        clean = {
            "name": identity.get("name"),
            "profession": identity.get("profession"),
            "location": identity.get("location"),
            "language": identity.get("language"),
            "goals": identity.get("goals", []),
            "preferences": identity.get("preferences", []),
        }

        # name/profession/location/language deben ser string o None;
        # cualquier otro tipo (ej. una lista devuelta por error) se descarta
        for key in ("name", "profession", "location", "language"):
            if clean[key] is not None and not isinstance(clean[key], str):
                clean[key] = None

        # goals y preferences: filtrado de preguntas/basura + grounding
        clean["goals"] = self._sanitize_text_list(clean["goals"], message)
        clean["preferences"] = self._sanitize_text_list(clean["preferences"], message)

        # grounding check para profession
        if clean["profession"] and message:
            if not self._is_grounded(clean["profession"], message):
                clean["profession"] = None

        return clean

    def _sanitize_text_list(self, items, message: str = "", min_words: int = 2):
        """
        Normaliza y filtra listas de texto libre (goals, preferences).
        Descarta:
        - items vacíos o no-string/no-dict
        - preguntas (terminan en '?' o empiezan con '¿')
        - frases demasiado cortas para ser un objetivo/preferencia real
        - (si se pasa `message`) frases sin evidencia textual real en el
          mensaje del usuario, para prevenir alucinaciones del extractor
        """

        if not isinstance(items, list):
            return []

        sanitized = []

        for item in items:

            if isinstance(item, dict):
                value = item.get("value") or item.get("goal") or item.get("preference")
            elif isinstance(item, str):
                value = item
            else:
                continue

            if not value:
                continue

            value = value.strip()

            if not value:
                continue

            # descartar preguntas
            if value.endswith("?") or value.endswith("¿") or value.startswith("¿"):
                continue

            # descartar frases demasiado cortas para ser un goal/preference real
            if len(value.split()) < min_words:
                continue

            # grounding check: debe haber evidencia real en el mensaje
            if message and not self._is_grounded(value, message):
                continue

            sanitized.append(value)

        return sanitized

    def validate_facts(self, facts, message: str = ""):

        if not isinstance(facts, list):
            return []

        normalized = []

        for fact in facts:

            if isinstance(fact, str):

                normalized.append({
                    "value": fact,
                    "priority": 1
                })

            elif isinstance(fact, dict):

                value = fact.get("value") or fact.get("fact")

                if value:

                    normalized.append({
                        "value": value,
                        "priority": fact.get("priority", 1)
                    })

        # grounding check también para facts
        if message:
            normalized = [
                f for f in normalized
                if self._is_grounded(f["value"], message)
            ]

        # FIX: filtrar facts que son solo expresiones vagas de ánimo
        # ("todo mal", "cansado nomás") -- no son hechos verificables,
        # son queja/estado de ánimo que ya se registra en "emotions".
        normalized = [
            f for f in normalized
            if not self._is_mood_only(f["value"])
        ]

        return normalized

    def _is_mood_only(self, value: str) -> bool:
        """
        True si el valor está compuesto ÚNICAMENTE por palabras de ánimo
        genéricas (sin ningún contenido sustantivo real). Ej: "todo mal",
        "cansado nomás" -> True. "cansado de mi jefe" -> False (tiene
        contenido sustantivo real: "jefe").
        """
        words = re.findall(r"[a-záéíóúñ]+", self._normalize_text(value))

        if not words:
            return False

        content_words = [
            w for w in words
            if w not in self._STOPWORDS and w not in self._MOOD_ONLY_WORDS
        ]

        return len(content_words) == 0

    def validate_topics(self, topics):

        if not isinstance(topics, list):
            return []

        normalized = []

        for topic in topics:

            if isinstance(topic, str):

                normalized.append({
                    "value": topic,
                    "priority": 1
                })

            elif isinstance(topic, dict):

                value = topic.get("value") or topic.get("topic")

                if value:

                    normalized.append({
                        "value": value,
                        "priority": topic.get("priority", 1)
                    })

        # FIX: filtrar topics que en realidad son emociones ("tristeza"
        # como topic). Una emoción no es un tema de interés -- ya vive en
        # "emotions", con su propio tracking.
        normalized = [
            t for t in normalized
            if self._normalize_text(t["value"]) not in self._EMOTION_WORDS
        ]

        return normalized

    # -----------------------------------------------------
    # Grounding check: verifica que un valor extraído tenga evidencia
    # textual real en el mensaje original, comparando palabras
    # significativas (se ignoran stopwords y palabras muy cortas).
    # No es un match exacto: alcanza con que al menos una palabra
    # significativa del valor extraído aparezca en el mensaje.
    # -----------------------------------------------------

    def _normalize_text(self, text: str) -> str:
        text = text.lower().strip()
        text = "".join(
            c for c in unicodedata.normalize("NFD", text)
            if unicodedata.category(c) != "Mn"
        )
        return text

    def _significant_words(self, text: str) -> set:
        text = self._normalize_text(text)
        words = re.findall(r"[a-z0-9]+", text)
        return {
            w for w in words
            if len(w) >= 4 and w not in self._STOPWORDS
        }

    def _is_grounded(self, value: str, message: str) -> bool:

        value_words = self._significant_words(value)

        if not value_words:
            # si el valor no tiene ninguna palabra significativa
            # (ej. solo stopwords/números cortos), no podemos confirmar
            # evidencia real -> se descarta por precaución
            return False

        message_words = self._significant_words(message)

        overlap = value_words & message_words

        return len(overlap) > 0