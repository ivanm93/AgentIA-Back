import json
import os

import httpx

from app.core.logging_config import get_logger

logger = get_logger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqClient:
    """
    Cliente para Groq (API compatible con el formato de OpenAI).
    Expone el mismo contrato que OllamaClient.chat(messages, tools=,
    tool_executors=, options=) para poder intercambiarlos sin tocar el
    resto de chat_service.py.

    SUPUESTO A VERIFICAR: asumo que WEB_SEARCH_TOOL_SCHEMA ya viene en
    formato OpenAI-style ({"type": "function", "function": {...}}),
    porque así es como Ollama expone tool-calling en su API /chat. Si
    resulta que el schema tiene otra forma específica de Ollama, hay
    que adaptarlo acá antes de mandarlo a Groq -- no llegué a confirmar
    esto porque no tuve ollama_client.py ni web_search_tool.py a la
    vista.
    """

    def __init__(self, model: str | None = None):
        self.api_key = os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        self._http = httpx.AsyncClient(timeout=30.0)

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_executors: dict | None = None,
        options: dict | None = None,
        response_format: dict | None = None,
    ) -> str:
        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY no configurada -- no se puede llamar a Groq."
            )

        payload = {
            "model": self.model,
            "messages": messages,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        if response_format:
            payload["response_format"] = response_format

        # FIX: options viene con nombres estilo Ollama (num_predict) en
        # las llamadas existentes de chat_service.py (ver clasificador
        # de _needs_web_search). Groq/OpenAI usa max_tokens -- se
        # traduce acá para no tener que tocar los call sites.
        if options:
            if "num_predict" in options:
                payload["max_tokens"] = options["num_predict"]
            if "temperature" in options:
                payload["temperature"] = options["temperature"]

        response = await self._post(payload)
        message = response["choices"][0]["message"]

        # Loop de tool-calling de UNA sola vuelta: si el modelo pide
        # ejecutar una tool, la ejecutamos y le devolvemos el resultado
        # para que arme la respuesta final. No soporta múltiples
        # rondas encadenadas de tool calls -- alcanza para el caso de
        # uso actual (búsqueda web puntual), pero si en el futuro se
        # agregan tools que se llaman en cadena, esto hay que
        # extenderlo.
        tool_calls = message.get("tool_calls")
        if tool_calls and tool_executors:
            messages_with_tool_result = messages + [message]

            for call in tool_calls:
                function_name = call["function"]["name"]
                executor = tool_executors.get(function_name)

                if not executor:
                    logger.warning(
                        f"Groq pidió ejecutar tool '{function_name}' pero no "
                        f"hay executor registrado para ese nombre."
                    )
                    continue

                try:
                    arguments = json.loads(call["function"]["arguments"])
                except (json.JSONDecodeError, TypeError):
                    arguments = {}

                tool_result = await executor(**arguments)

                messages_with_tool_result.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": str(tool_result),
                })

            follow_up_payload = {
                "model": self.model,
                "messages": messages_with_tool_result,
            }
            follow_up = await self._post(follow_up_payload)
            return follow_up["choices"][0]["message"]["content"]

        return message.get("content", "")

    async def _post(self, payload: dict) -> dict:
        response = await self._http.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def aclose(self):
        await self._http.aclose()