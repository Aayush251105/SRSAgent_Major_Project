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
        host: str = "http://localhost:11434",
        temperature: float = 0.0,
        seed: int = 42,
        num_ctx: int = 8192,
        think: bool | None = None,
    ):
        self.model = model
        self.client = Client(host=host)
        # Deterministic decoding: the same SRS yields the same requirements.
        self.options = {"temperature": temperature, "seed": seed, "num_ctx": num_ctx}
        # Thinking models (e.g. qwen3): False disables the hidden reasoning
        # pass. None sends nothing, so other models are unaffected.
        self.think = think

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
            format=schema.model_json_schema(),
            options=self.options,
            **({} if self.think is None else {"think": self.think}),
        )

        return schema.model_validate_json(
            response["message"]["content"]
        ).model_dump()