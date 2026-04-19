import os
from typing import Iterator

from agent.chunker import FileChunk
from agent.providers.base import LLMProvider

MODEL = "gemini-2.0-flash"


class GeminiProvider(LLMProvider):

    def __init__(self, api_key: str | None = None):
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise RuntimeError(
                "google-genai is not installed. Run: python -m pip install google-genai"
            )

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")

        self._client = genai.Client(api_key=key)
        self._types = types

    def _build_user_message(self, chunk: FileChunk, context: str) -> str:
        msg = f"Please review the following code.\n\n{chunk.content}"
        if context:
            msg = f"Previous findings context:\n{context}\n\n---\n\n{msg}"
        return msg

    def review_chunk(self, chunk: FileChunk, system_prompt: str, context: str = "") -> str:
        response = self._client.models.generate_content(
            model=MODEL,
            contents=self._build_user_message(chunk, context),
            config=self._types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
        )
        return response.text

    def review_chunk_stream(self, chunk: FileChunk, system_prompt: str, context: str = "") -> Iterator[str]:
        for part in self._client.models.generate_content_stream(
            model=MODEL,
            contents=self._build_user_message(chunk, context),
            config=self._types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
        ):
            if part.text:
                yield part.text
