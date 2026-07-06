import httpx
import json

from app.config.config import OLLAMA_MODEL, OLLAMA_URL


class MemoryExtractor:

    async def extract(self, message: str, emotion: str, profile: dict):
        prompt = f"""
Eres un sistema de memoria de un asistente personal.

Tu tarea es extraer ÚNICAMENTE información EXPLÍCITA del mensaje del usuario.

Devuelve SOLO JSON válido. No agregues texto adicional, ni explicaciones, ni razonamiento.

---

FORMATO DE SALIDA:

{{
"identity": {{
    "name": null,
    "profession": null,
    "location": null,
    "language": null,
    "goals": [],
    "preferences": []
}},
"facts": [],
"topics": [],
"emotion_pattern": null
}}

---

REGLA ABSOLUTA #1: NO INVENTES NI INFIERAS NADA.
Si el usuario no lo dijo explícitamente en ESTE mensaje, el campo queda null o vacío.
No completes campos "porque tendría sentido" o "porque es probable".

REGLA ABSOLUTA #2: PROFESSION Y GOALS SON MUTUAMENTE EXCLUYENTES PARA LA MISMA FRASE.
Una misma afirmación del usuario NUNCA genera profession Y goal al mismo tiempo.

- profession = lo que el usuario YA ES o YA HACE (tiempo presente, hecho actual)
  Señales: "trabajo como...", "soy...", "me dedico a...", "actualmente hago..."

- goals = lo que el usuario QUIERE llegar a ser o lograr (aspiración futura, no cumplida todavía)
  Señales: "quiero ser...", "mi objetivo es...", "me gustaría...", "estoy tratando de..."

---

EJEMPLOS CORRECTOS (seguí este patrón exactamente):

Mensaje: "Trabajo como Software Engineer."
→ profession: "Software Engineer"
→ goals: [] (NO agregar ningún goal a partir de esta frase)

Mensaje: "Soy técnico electromecánico."
→ profession: "técnico electromecánico"
→ goals: []

Mensaje: "Quiero ser Software Engineer algún día."
→ profession: null
→ goals: ["ser Software Engineer"]

Mensaje: "Mi objetivo es crear la mejor IA local posible."
→ profession: null
→ goals: ["crear la mejor IA local posible"]

Mensaje: "¿Qué profesión tengo?"
→ profession: null
→ goals: []
→ facts: []
(Es una PREGUNTA del usuario, no una afirmación. Las preguntas NUNCA se
extraen como facts, goals ni profession, ni siquiera parafraseadas o
reformuladas. Si el mensaje es una pregunta, TODOS los campos quedan
vacíos/null, salvo que además contenga una afirmación nueva y explícita.)

Mensaje: "Prefiero respuestas cortas."
→ preferences: ["respuestas cortas"]
→ goals: [] (NO es un objetivo, es una preferencia de estilo/interacción)

Mensaje: "Me gusta trabajar de noche."
→ preferences: ["trabajar de noche"]
→ goals: []

Mensaje: "Prefiero que no me hagas tantas preguntas seguidas."
→ preferences: ["evitar preguntas seguidas / una pregunta a la vez"]
→ goals: []
(Una preferencia formulada en negativo ("prefiero que NO...") sigue siendo
 una preferencia real y debe extraerse. Reformulala de forma clara y
 accionable, sin perder el sentido negativo original.)

---

EJEMPLOS INCORRECTOS (NO hagas esto):

Mensaje: "Trabajo como Software Engineer."
✗ INCORRECTO: goals: ["become Software Engineer"]
  (Esto es una invención. El usuario declaró un hecho actual, no una aspiración.
  "Trabajo como X" nunca implica "quiero ser X".)

Mensaje: "¿Qué profesión tengo?"
✗ INCORRECTO: goals: ["¿Qué profesión tengo?"]
  (Las preguntas del usuario nunca son goals, facts, ni ningún otro campo.)

Mensaje: "¿Cuál es mi objetivo?"
✗ INCORRECTO: goals: ["ser mi objetivo"]
  (Esto también es INCORRECTO aunque no tenga el signo "?": es una
  reformulación de la pregunta, no una afirmación nueva del usuario.
  Reformular una pregunta como si fuera una respuesta es inventar
  información. El campo goals debe quedar vacío.)

---

REGLA ABSOLUTA DE ESTABILIDAD:

- NO modifiques profession si el usuario no lo dice directamente EN ESTE mensaje.
- NO uses el contexto de mensajes anteriores para inventar campos nuevos.
- Si el mensaje es una pregunta dirigida al asistente, no extraigas nada de ese
  mensaje salvo que también contenga una afirmación explícita nueva.

---

CLEARED_FIELDS (campos que el usuario NEGÓ explícitamente):

Cuando el usuario indica explícitamente que un dato previo YA NO es válido
(ej. "ya no trabajo como X", "renuncié", "eso ya no es así", "dejé de..."),
y NO da un valor nuevo para reemplazarlo, agregá el nombre del campo a
"cleared_fields". Esto es DISTINTO de simplemente no mencionar el campo:
"cleared_fields" es solo para negaciones EXPLÍCITAS.

Campos válidos para cleared_fields: "profession", "location", "language".
(NO incluyas "goals" ni "preferences" acá, esos se manejan aparte.)

Mensaje: "En realidad ya no trabajo como Software Engineer, renuncié la semana pasada."
→ profession: null
→ cleared_fields: ["profession"]
(El usuario negó explícitamente su profesión anterior, sin dar una nueva.
 Si SÍ hubiera dado una nueva profesión en el mismo mensaje, esa iría en
 "profession" y "cleared_fields" quedaría vacío, porque ya se reemplazó.)

Mensaje: "Hoy llovió todo el día."
→ profession: null
→ cleared_fields: []
(Acá "profession: null" simplemente significa que no se mencionó nada del
 tema en este mensaje -- NO es una negación explícita, así que NO va en
 cleared_fields.)

---

FACTS:
- hechos concretos y verificables que el usuario afirma sobre sí mismo
- NUNCA una pregunta
- formato: {{"value": "...", "priority": 1-5}}

TOPICS:
- temas de interés mencionados explícitamente
- sin duplicados: si el mismo tema aparece varias veces en el mensaje, aparece
  UNA sola vez en la lista de topics
- formato: {{"value": "...", "priority": 1-5}}

---

MENSAJE:
{message}

EMOCIÓN:
{emotion}

PERFIL ACTUAL:
{profile}

RESPONDE SOLO JSON, SIN explicación, SIN razonamiento, SIN texto antes o después:
"""

        # FIX: se agrega un JSON schema explícito, pasado vía el parámetro
        # `format` que soporta la API de Ollama (/api/chat). Esto fuerza
        # ESTRUCTURALMENTE la salida del modelo: no puede devolver campos
        # fuera de este esquema, ni tipos distintos a los declarados.
        #
        # Esto es una mejora independiente de qué modelo uses -- ataca la
        # clase de bug "campo fantasma con tipo inconsistente" (identity
        # con claves inventadas, facts como string suelto en vez de objeto,
        # etc) desde la raíz, en vez de confiar en que el prompt alcance
        # para que el modelo respete el formato.
        #
        # OJO: el schema garantiza ESTRUCTURA (tipos y campos correctos),
        # no SEMÁNTICA. Un modelo puede seguir devolviendo un goal mal
        # clasificado (ej. "todo mal") con esta estructura perfectamente
        # válida -- ese tipo de error sigue dependiendo del prompt/modelo,
        # y de las capas de grounding check que ya tiene memory_validator.
        response_schema = {
            "type": "object",
            "properties": {
                "identity": {
                    "type": "object",
                    "properties": {
                        "name": {"type": ["string", "null"]},
                        "profession": {"type": ["string", "null"]},
                        "location": {"type": ["string", "null"]},
                        "language": {"type": ["string", "null"]},
                        "goals": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "preferences": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                    },
                    "required": [
                        "name", "profession", "location",
                        "language", "goals", "preferences"
                    ],
                },
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "string"},
                            "priority": {"type": "integer"},
                        },
                        "required": ["value", "priority"],
                    },
                },
                "topics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "string"},
                            "priority": {"type": "integer"},
                        },
                        "required": ["value", "priority"],
                    },
                },
                "emotion_pattern": {"type": ["string", "null"]},
                "cleared_fields": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["profession", "location", "language"],
                    },
                },
            },
            "required": [
                "identity", "facts", "topics",
                "emotion_pattern", "cleared_fields"
            ],
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False,
                    "format": response_schema,
                }
            )
        response.raise_for_status()
        content = response.json()["message"]["content"]

        try:
            data = json.loads(content)

        except json.JSONDecodeError:
            # con format forzado esto debería ser muy raro, pero se
            # mantiene el fallback por las dudas (ej. si el modelo no
            # soporta structured outputs y el schema es ignorado)
            return {}

        # FIX: _normalize() existía pero nunca se llamaba, dejando pasar
        # estructuras inconsistentes (facts/topics como strings sueltos,
        # campos de identity faltantes) directo hacia el resto del pipeline.
        # Se mantiene como defensa adicional aunque el schema ya fuerce
        # gran parte de esto -- no todos los modelos/versiones de Ollama
        # respetan el schema al 100%.
        return self._normalize(data)

    def _normalize(self, data):

        if not isinstance(data, dict):
            return {}

        data.setdefault("identity", {})
        data.setdefault("facts", [])
        data.setdefault("topics", [])
        data.setdefault("emotion_pattern", None)
        data.setdefault("cleared_fields", [])

        # whitelist: solo campos escalares conocidos pueden "limpiarse"
        _CLEARABLE = {"profession", "location", "language"}
        if isinstance(data["cleared_fields"], list):
            data["cleared_fields"] = [
                f for f in data["cleared_fields"]
                if isinstance(f, str) and f in _CLEARABLE
            ]
        else:
            data["cleared_fields"] = []

        identity = data["identity"]

        if not isinstance(identity, dict):
            identity = {}

        # FIX: whitelist estricta de campos de identity. Antes se usaba
        # setdefault(), que deja pasar cualquier campo extra que el LLM
        # invente (ej. "hobbies"), con tipo inconsistente entre turnos
        # (string en uno, lista en otro), lo que después rompía
        # update_identity con TypeError al concatenar str + list.
        identity = {
            "name": identity.get("name"),
            "profession": identity.get("profession"),
            "location": identity.get("location"),
            "language": identity.get("language"),
            "goals": identity.get("goals", []),
            "preferences": identity.get("preferences", []),
        }

        if not isinstance(identity["goals"], list):
            identity["goals"] = []

        if not isinstance(identity["preferences"], list):
            identity["preferences"] = []

        data["identity"] = identity

        data["facts"] = self.normalize_facts(
            data["facts"]
        )

        data["topics"] = self.normalize_topics(
            data["topics"]
        )

        return data

    def normalize_topics(self, topics):

        if not isinstance(topics, list):
            return []

        normalized = []
        seen_values = set()

        for topic in topics:

            if isinstance(topic, str):
                value = topic
                priority = 1

            elif isinstance(topic, dict):
                value = topic.get("value") or topic.get("topic")
                priority = topic.get("priority", 1)

            else:
                continue

            if not value:
                continue

            # FIX: de-duplicar topics dentro de la misma extracción, para
            # evitar que memory_consolidator sume strength varias veces por
            # el mismo topic repetido en una sola respuesta del LLM.
            key = value.lower().strip()
            if key in seen_values:
                continue
            seen_values.add(key)

            normalized.append({
                "value": value,
                "priority": priority
            })

        return normalized

    def normalize_facts(self, facts):

        if not isinstance(facts, list):
            return []

        normalized = []

        for fact in facts:

            if isinstance(fact, str):
                value = fact
                priority = 1

            elif isinstance(fact, dict):
                value = fact.get("value")
                priority = fact.get("priority", 1)

            else:
                continue

            if not value:
                continue

            # descartar preguntas coladas como facts
            value = value.strip()
            if value.endswith("?"):
                continue

            normalized.append({
                "value": value,
                "priority": priority
            })

        return normalized