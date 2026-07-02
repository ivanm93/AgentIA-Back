class ResponseGenerator:

    def __init__(self, client):
        self.client = client

    async def generate(self, prompt: str):

        messages = [
            {
                "role": "system",
                "content": "Eres un asistente con memoria persistente."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        return await self.client.generate(messages)