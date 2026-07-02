import re
import unicodedata


class RiskDetector:
    """
    Detector de señales de riesgo emocional (ideación suicida, autolesión,
    desesperanza aguda) basado en patrones de texto, NO en el LLM.

    Por qué no usamos el LLM para esto:
    ya confirmamos que una instrucción en el system prompt puede ser
    ignorada por el modelo. Esta capa es determinística: si el patrón
    matchea, la respuesta de contención se activa siempre, sin depender
    de que el modelo "decida" respetar la instrucción.

    Esta NO es una herramienta de diagnóstico ni pretende tener 100% de
    precisión. Es una red de seguridad mínima: prioriza no dejar pasar
    señales claras (menor tasa de falsos negativos) aunque eso implique
    algunos falsos positivos ocasionales (mejor activar contención de más
    que de menos).

    IMPORTANTE: la lista de patrones y el mensaje de contención en
    crisis_response.py deben ser revisados por el desarrollador antes de
    producción. Esto es un punto de partida técnico, no una validación
    clínica.
    """

    # Frases/patrones asociados a riesgo agudo (ideación suicida directa
    # o pasiva, desesperanza extrema, autolesión). Se buscan como
    # substrings normalizados (sin tildes, minúsculas), no como palabras
    # sueltas aisladas, para reducir falsos positivos de palabras comunes.
    _RISK_PATTERNS = [
        # ideación suicida directa
        r"quiero morir",
        r"quiero morirme",
        r"me quiero morir",
        r"no quiero vivir",
        r"no quiero seguir viviendo",
        r"quiero matarme",
        r"me quiero matar",
        r"quitarme la vida",
        r"terminar con (todo|mi vida)",
        r"acabar con (todo|mi vida)",
        r"no quiero (estar|seguir) mas (aqui|aca)",

        # ideación pasiva / desesperanza aguda
        r"no vale la pena seguir",
        r"no vale la pena vivir",
        r"para que seguir( viviendo)?",
        r"ya no aguanto mas",
        r"no le encuentro sentido a (nada|la vida)",
        r"seria mejor (si )?no estar",
        r"nadie me (extranaria|va a extranar)",
        r"estarian mejor sin mi",

        # autolesión
        r"hacerme dano",
        r"lastimarme",
        r"cortarme",
        r"autolesion",
    ]

    def __init__(self):
        self._compiled = [
            re.compile(pattern) for pattern in self._RISK_PATTERNS
        ]

    def _normalize(self, text: str) -> str:
        text = text.lower().strip()
        text = "".join(
            c for c in unicodedata.normalize("NFD", text)
            if unicodedata.category(c) != "Mn"
        )
        return text

    def detect(self, message: str) -> bool:
        """
        Devuelve True si el mensaje contiene alguna señal de riesgo conocida.
        """
        if not message:
            return False

        normalized = self._normalize(message)

        return any(
            pattern.search(normalized)
            for pattern in self._compiled
        )