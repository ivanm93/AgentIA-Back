from app.prompts.system_prompt import (
    SYSTEM_MESSAGE,
    CARE_MODE_ADDENDUM,
    PROFESSIONAL_SUGGESTION_ADDENDUM,
)

class PromptBuilder:

    def build(
        self,
        message,
        history,
        emotion_style,
        summary,
        profile,
        relevant_memory,
        care_mode: bool = False,
        suggest_professional: bool = False
    ):

        memory_context = self._build_memory_context(
            profile,
            relevant_memory
        )

        system_prompt = self._build_system_prompt(
            emotion_style,
            summary,
            memory_context,
            care_mode,
            suggest_professional
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]

        messages.extend(history)

        messages.append({
            "role": "user",
            "content": message
        })

        return messages

    # -----------------------------------------------------

    def _build_memory_context(
        self,
        profile,
        relevant_memory
    ):

        identity = profile.get("identity", {})

        memory = []

        # ---------------- IDENTIDAD ----------------

        if identity.get("name"):
            memory.append(f"Nombre: {identity['name']}")

        if identity.get("profession"):
            memory.append(f"Profesión: {identity['profession']}")

        if identity.get("location"):
            memory.append(f"Ubicación: {identity['location']}")

        if identity.get("language"):
            memory.append(f"Idioma: {identity['language']}")

        if identity.get("goals"):
            memory.append("\nObjetivos:")
            memory.extend(
                f"- {goal}"
                for goal in identity["goals"]
            )

        if identity.get("preferences"):
            memory.append("\nPreferencias:")
            memory.extend(
                f"- {pref}"
                for pref in identity["preferences"]
            )

        # ---------------- FACTS ----------------

        facts = relevant_memory.get("facts") or []

        if facts:
            memory.append("\nHechos importantes:")
            memory.extend(
                f"- {fact['value']}"
                for fact in facts
            )

        # ---------------- TOPICS ----------------

        topics = relevant_memory.get("topics") or []

        if topics:
            memory.append("\nTemas relevantes:")
            memory.extend(
                f"- {topic['value']}"
                for topic in topics
            )

        # ---------------- EMOCIONES ----------------

        emotions = relevant_memory.get("emotions") or []

        if emotions:
            memory.append("\nEstado emocional reciente:")
            memory.extend(
                f"- {emotion['value']}"
                for emotion in emotions
            )

        return "\n".join(memory)
    # -----------------------------------------------------

    # FIX: SYSTEM_MESSAGE se importaba pero nunca se usaba. El prompt real
    # que recibía el modelo era genérico (reglas de memoria únicamente),
    # sin ninguno de los principios de apoyo emocional definidos en
    # system_prompt.py (no juzgar, no diagnosticar, no encadenar preguntas,
    # manejo de señales de riesgo, etc).
    #
    # Ahora SYSTEM_MESSAGE va primero como base de identidad del asistente,
    # y las reglas de memoria + contexto se agregan después como información
    # operativa, sin pisar ni duplicar los principios de la identidad base.
    def _build_system_prompt(
        self,
        emotion_style,
        summary,
        memory_context,
        care_mode: bool = False,
        suggest_professional: bool = False
    ):

        identity_block = SYSTEM_MESSAGE["content"]

        # FIX (mejora #2 -- modo cuidado post-crisis): se agrega al final
        # para no interferir con las reglas de memoria/contexto, pero
        # después de todo lo demás así queda como la instrucción más
        # "reciente" en el prompt (suele pesar más en modelos con
        # seguimiento de instrucciones débil).
        care_block = CARE_MODE_ADDENDUM if care_mode else ""

        # FIX (mejora #3 -- guardrails temáticos): mismo criterio, se
        # agrega al final. Si coinciden care_mode Y suggest_professional
        # en el mismo turno (poco común, pero posible), las reglas de
        # riesgo dentro de CARE_MODE_ADDENDUM ya dejan explícito que
        # tienen prioridad sobre esto.
        professional_block = (
            PROFESSIONAL_SUGGESTION_ADDENDUM if suggest_professional else ""
        )

        return f"""{identity_block}
========================================
REGLAS DE MEMORIA

- Usa "profession" como hecho actual del usuario, no como objetivo.
- Usa "goals" solo si el usuario expresó una aspiración futura explícita
  ("quiero", "me gustaría", "mi objetivo es").
- Nunca confundas profesión con objetivo.
- Usa la memoria solo cuando aporte valor genuino a la conversación; no la
  repitas constantemente ni la uses para interrogar al usuario.
- No inventes recuerdos. Si la memoria contradice lo que el usuario dice
  ahora, considerá válida la información más reciente.
- Si conocés el nombre del usuario, usalo ocasionalmente de forma natural.
- Si el usuario pregunta qué recordás de él, respondé usando la memoria.

========================================
RESUMEN DE CONVERSACIONES

{summary}

========================================
MEMORIA DEL USUARIO

{memory_context}

========================================
ESTILO DE RESPUESTA

{emotion_style}
{care_block}{professional_block}"""