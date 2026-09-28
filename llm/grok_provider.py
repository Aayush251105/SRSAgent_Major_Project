import os
from typing import Any, Type

from openai import OpenAI

from llm.base_provider import LLMProvider


class GrokProvider(LLMProvider):
    """
    Grok implementation of the LLM provider.

    Grok exposes an OpenAI-compatible API, so the provider only handles
    authentication and model-specific configuration.
    """

    def __init__(
        self,
        model: str = "grok-4",
        api_key: str | None = None
    ):
        self.model = model

        self.client = OpenAI(
            api_key=api_key or os.getenv("XAI_API_KEY"),
            base_url="https://api.x.ai/v1"
        )

    def generate_structured(
        self,
        prompt: str,
        schema: Type[Any]
    ) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema()
                }
            }
        )

        return schema.model_validate_json(
            response.choices[0].message.content
        ).model_dump()