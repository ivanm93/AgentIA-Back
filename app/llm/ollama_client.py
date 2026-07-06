import httpx
from app.config.config import OLLAMA_MODEL, OLLAMA_URL
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class OllamaClient:

    async def chat(
        self,
        messages: list,
        tools: list | None = None,
        tool_executors: dict | None = None,
        options: dict | None = None,
    ) -> str:
        """
        Si se pasan `tools` (schemas de function-calling) y el modelo
        decide usar alguna, se ejecuta el executor correspondiente (de
        `tool_executors`, un dict nombre -> función async) y se hace una
        segunda llamada a Ollama con el resultado, para que arme la
        respuesta final ya con esa información.

        Si el modelo no pide ninguna herramienta (el caso normal, la
        gran mayoría de los mensajes), se comporta exactamente igual que
        antes: una sola llamada, devuelve el texto de la respuesta.

        `options` (FIX): mapea directo al campo "options" que la API
        nativa de Ollama ya soporta en el body (num_predict,
        temperature, etc. -- ver docs de /api/chat). Antes este
        parámetro no existía en la firma, aunque chat_service.py ya lo
        llamaba con options={"num_predict": 5} para el clasificador de
        búsqueda -- eso tiraba TypeError en cada llamada, y como
        _needs_web_search() atrapa la excepción y devuelve False, el
        efecto real era que la búsqueda web NUNCA se activaba, en
        silencio.
        """

        tools = tools or []
        tool_executors = tool_executors or {}

        body = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
        }
        if tools:
            body["tools"] = tools
        if options:
            body["options"] = options

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        message = data["message"]
        tool_calls = message.get("tool_calls")

        if not tool_calls:
            return message["content"]

        # FIX (tool calling): el modelo pidió usar una herramienta.
        # Ejecutamos cada una y le devolvemos el resultado como mensajes
        # de rol "tool", para que en la segunda llamada arme la
        # respuesta final ya con esa información -- en vez de que el
        # modelo "invente" un resultado de búsqueda que no existe.
        logger.info(f"El modelo solicitó {len(tool_calls)} tool call(s).")

        messages = messages + [message]

        for call in tool_calls:
            fn_name = call["function"]["name"]
            fn_args = call["function"].get("arguments", {}) or {}

            executor = tool_executors.get(fn_name)

            if executor:
                try:
                    result = await executor(**fn_args)
                except Exception as e:
                    logger.warning(f"Error ejecutando tool '{fn_name}': {e!r}")
                    result = f"Hubo un error usando la herramienta '{fn_name}'."
            else:
                logger.warning(f"Tool '{fn_name}' solicitada pero no está registrada.")
                result = f"La herramienta '{fn_name}' no está disponible."

            logger.debug(f"Resultado de tool '{fn_name}': {result[:200]}")

            messages.append({
                "role": "tool",
                "content": result,
            })

        # FIX: la versión anterior de este recordatorio usaba un mensaje
        # nuevo con role="system" DESPUÉS de los resultados de la
        # herramienta -- pero la plantilla de conversación de Llama 3.1
        # solo espera UN mensaje de sistema, al principio de todo. Meter
        # uno de más en esa posición rompió el formato interno y el
        # modelo terminó filtrando texto de la plantilla ("assistant"
        # apareciendo literal al inicio de la respuesta).
        #
        # Ahora el recordatorio se agrega al final del CONTENIDO del
        # último mensaje "tool" -- una posición que el modelo sí espera,
        # sin inventar una estructura de conversación nueva.
        if messages and messages[-1]["role"] == "tool":
            messages[-1]["content"] += (
                "\n\n[Los resultados de arriba son reales y actuales -- "
                "ACABAS de buscarlos. Usalos para responder. NO digas "
                "que no tenés acceso a internet ni que no podés buscar "
                "información actual.]"
            )

        # Segunda llamada, ya sin `tools` -- el modelo solo tiene que
        # redactar la respuesta final usando lo que le devolvimos.
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": messages,
                    "stream": False,
                },
            )
            response.raise_for_status()
            return response.json()["message"]["content"]