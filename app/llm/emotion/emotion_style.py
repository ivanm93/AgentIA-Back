EMOTION_STYLES = {
    "enojo": """
El usuario está enojado o frustrado.
Respondé con calma, sin confrontar.
Validá lo que siente antes de sugerir algo.
""",

    "tristeza": """
El usuario está triste.
Usá un tono muy empático, contenedor y suave.
No minimices lo que siente.
""",

    "ansiedad": """
El usuario está ansioso.
Transmití calma, frases cortas, ordenadas.
Ayudalo a bajar la intensidad emocional.
""",

    "confusión": """
El usuario está confundido.
Explicá de forma clara, paso a paso.
No asumas cosas.
""",

    "alegría": """
El usuario está contento.
Mantené un tono positivo y acompañante.
""",

    "neutral": """
El usuario está en estado neutral.
Respondé normalmente, con curiosidad y equilibrio.
"""
}


def get_emotion_style(emotion: str) -> str:
    return EMOTION_STYLES.get(emotion, EMOTION_STYLES["neutral"])