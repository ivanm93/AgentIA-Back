import re

EMOTION_RULES = [
    ("enojo", [r"enojad", r"furios", r"odio", r"hart", r"molest"]),
    ("tristeza", [r"triste", r"deprim", r"solo", r"vacío", r"mal"]),
    ("ansiedad", [r"ansios", r"nervios", r"preocup", r"estres"]),
    ("confusión", [r"no entiendo", r"confund", r"duda"]),
]


def detect_by_rules(text: str) -> list[str]:
    text = text.lower()

    detected = []

    for emotion, patterns in EMOTION_RULES:
        for pattern in patterns:
            if re.search(pattern, text):
                detected.append(emotion)
                break

    return detected