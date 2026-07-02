import re
import unicodedata


class ClinicalSignalDetector:
    """
    Detector de señales de que un tema (ansiedad, depresión, estrés
    crónico, sueño, frustración) se está acercando a terreno donde
    convendría sugerir ayuda profesional -- por duración, frecuencia o
    intensidad, no por una sola mención puntual.

    A diferencia de RiskDetector, esto NO interrumpe el flujo de
    conversación ni dispara una respuesta fija. Es una señal de contexto
    que se suma al perfil del usuario; cuando se acumula evidencia
    suficiente, se le pide al LLM (vía PROFESSIONAL_SUGGESTION_ADDENDUM)
    que sugiera consulta profesional UNA vez, de forma delicada.

    Esto tampoco es diagnóstico: solo mira patrones de lenguaje que
    sugieren cronicidad/severidad (duración, frecuencia, impacto
    funcional), no síntomas específicos con precisión clínica.
    """

    _CATEGORIES = {
        "ansiedad": [
            r"ataques? de panico",
            r"me cuesta respirar",
            r"todo el tiempo (nervios|preocupad)",
            r"no puedo dejar de preocuparme",
            r"ansiedad (todo el tiempo|todos los dias|constante)",
        ],
        "depresion": [
            r"no siento nada",
            r"no le encuentro sentido a nada",
            r"hace (semanas|meses) que me siento asi",
            r"no tengo ganas de nada",
            r"me cuesta levantarme de la cama",
            r"aislad[oa] de (todos|todo el mundo)",
        ],
        "estres_cronico": [
            r"hace (semanas|meses) que estoy asi",
            r"no paro de trabajar",
            r"no puedo desconectar",
            r"estres todo el tiempo",
            r"agotad[oa] todo el tiempo",
        ],
        "sueno": [
            r"no duermo (hace|desde hace)",
            r"insomnio",
            r"me despierto (varias veces|todo el tiempo)",
            r"no puedo dormir (bien )?hace",
            r"duermo muy poco (hace|desde)",
        ],
        "frustracion": [
            r"exploto por (todo|cualquier cosa)",
            r"pierdo el control (todo el tiempo|seguido)",
            r"no puedo controlar mi enojo",
            r"me enojo por (todo|nada)",
        ],
    }

    # palabras que refuerzan que se trata de algo sostenido en el tiempo,
    # no un evento puntual -- se usan para subir la confianza de un match
    _CHRONICITY_HINTS = {
        "hace", "desde", "siempre", "todo", "todos", "constante",
        "constantemente", "cada", "diario", "diariamente",
    }

    def __init__(self):
        self._compiled = {
            category: [re.compile(p) for p in patterns]
            for category, patterns in self._CATEGORIES.items()
        }

    def _normalize(self, text: str) -> str:
        text = text.lower().strip()
        text = "".join(
            c for c in unicodedata.normalize("NFD", text)
            if unicodedata.category(c) != "Mn"
        )
        return text

    def detect(self, message: str) -> list:
        """
        Devuelve la lista de categorías (strings) para las que el mensaje
        matchea alguna señal de cronicidad/severidad. Puede devolver
        varias si el mensaje toca más de un tema, o una lista vacía.
        """
        if not message:
            return []

        normalized = self._normalize(message)
        matched = []

        for category, patterns in self._compiled.items():
            if any(p.search(normalized) for p in patterns):
                matched.append(category)

        return matched