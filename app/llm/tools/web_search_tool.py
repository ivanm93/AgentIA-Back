# app/llm/tools/web_search_tool.py
#
# Herramienta de búsqueda web vía Tavily -- pensada específicamente para
# agentes de IA (a diferencia de Google/Bing, que están pensados para
# humanos navegando). Tier gratis: 1000 búsquedas/mes, sin tarjeta.
#
# ⚠️ Privacidad: cuando el modelo decide usar esta herramienta, la
# consulta de búsqueda (que el modelo arma, normalmente una versión
# corta del tema que preguntó la persona) viaja a Tavily -- un tercero.
# No es tan sensible como mandar la conversación completa a un LLM en
# la nube, pero sigue siendo información saliendo hacia afuera. Vale la
# pena reflejar esto en el disclaimer de onboarding en algún momento.

import httpx
from app.config.config import TAVILY_API_KEY
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# Schema de la herramienta, en el formato que Ollama espera (compatible
# con el formato de function-calling de OpenAI). El campo "description"
# es lo que el modelo lee para decidir CUÁNDO usar la herramienta --
# por eso es tan explícito sobre cuándo SÍ y cuándo NO usarla.
WEB_SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "buscar_en_internet",
        "description": (
            "Busca información actual en internet: noticias, tendencias, "
            "eventos recientes, o cualquier dato que pueda haber cambiado "
            "desde que se entrenó el modelo. Usar SOLO cuando la persona "
            "pregunte específicamente por algo de actualidad, noticias, o "
            "pida buscar algo explícitamente. NO usar para temas "
            "personales, emocionales, o charla común -- la gran mayoría "
            "de los mensajes NO necesitan esta herramienta."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "La consulta de búsqueda, en pocas palabras clave "
                        "(no una oración completa)."
                    ),
                }
            },
            "required": ["query"],
        },
    },
}


async def execute_web_search(query: str, max_results: int = 3) -> str:
    """
    Ejecuta la búsqueda real contra Tavily. Devuelve un texto formateado
    con los resultados (título + extracto + fuente), listo para
    insertarse como resultado de la tool call en la conversación.
    """
    if not TAVILY_API_KEY:
        logger.warning("TAVILY_API_KEY no configurada -- búsqueda no disponible.")
        return "La búsqueda web no está configurada en este momento."

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": query,
                    "max_results": max_results,
                },
            )
        response.raise_for_status()
        data = response.json()

    except (httpx.TimeoutException, httpx.HTTPError) as e:
        logger.warning(f"Error consultando Tavily: {e!r}")
        return "No pude buscar en internet en este momento."

    results = data.get("results", [])

    if not results:
        return "No encontré resultados relevantes para esa búsqueda."

    formatted = []
    for r in results:
        title = r.get("title", "")
        content = (r.get("content") or "")[:300]
        url = r.get("url", "")
        formatted.append(f"- {title}: {content} (fuente: {url})")

    return "\n".join(formatted)