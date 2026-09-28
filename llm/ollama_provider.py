from typing import Any, Type

from ollama import Client

from llm.base_provider import LLMProvider


class OllamaProvider(LLMProvider):
    """
    Ollama implementation of the LLM provider.

    The model and Ollama host are configurable so different local models
    can be tested without changing the SRS Agent.
    """

    def __init__(
        self,
        model: str = "llama3.1",
        host: str = "http://localhost:11434"
    ):
        self.model = model
        self.client = Client(host=host)

    def generate_structured(
        self,
        prompt: str,
        schema: Type[Any]
    ) -> dict:
        response = self.client.chat(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            format=schema.model_json_schema()
        )

        return schema.model_validate_json(
            response["message"]["content"]
        ).model_dump()