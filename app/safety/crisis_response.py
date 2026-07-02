# app/safety/crisis_response.py
#
# ⚠️ REVISAR ANTES DE PRODUCCIÓN ⚠️
#
# Este mensaje se muestra tal cual, sin pasar por el LLM, cuando
# RiskDetector detecta una señal de riesgo. Es la única garantía real de
# que el usuario reciba esta información, ya que no depende de que el
# modelo decida incluirla.
#
# Recomendaciones antes de usar esto en producción:
# - Confirmá los números de las líneas de ayuda (pueden cambiar).
# - Si tu app tiene usuarios fuera de Argentina, este mensaje necesita
#   variantes por país/región, o al menos un recurso internacional.
# - Considerá que alguien con más criterio clínico revise la redacción.
# - Esto es una PRIMERA capa. No reemplaza derivación a profesionales
#   ni protocolos más completos (por ejemplo, notificar a un contacto
#   de confianza, registrar el evento para seguimiento, etc.) si tu
#   producto crece.

CRISIS_RESPONSE_MESSAGE = (
    "Gracias por confiarme esto. Lo que describís suena a un dolor muy "
    "grande, y quiero que sepas que no estás solo con esto.\n\n"
    "No soy un profesional de salud mental y no puedo dar el tipo de "
    "ayuda que esto necesita, pero existen personas preparadas para "
    "acompañarte ahora mismo:\n\n"
    "📞 Centro de Asistencia al Suicida (Argentina): 135 (línea gratuita, "
    "Capital y Gran Buenos Aires) o 011-5275-1135 (desde todo el país).\n"
    "🚨 Si estás en peligro inmediato: 911.\n\n"
    "Si querés, podemos seguir hablando mientras tanto. Estoy acá para "
    "escucharte."
)


def is_crisis_message(text: str) -> bool:
    """Helper simple para identificar en logs/tests si una respuesta dada
    es la respuesta de crisis fija (útil para testing y auditoría)."""
    return text.strip() == CRISIS_RESPONSE_MESSAGE.strip()