import os
from typing import Iterator

from agent.chunker import FileChunk
from agent.http_client import llm_http_client
from agent.providers.base import LLMProvider

MODEL = "llama-3.3-70b-versatile"
MAX_TOKENS = 8192


class GroqProvider(LLMProvider):

    def __init__(self, api_key: str | None = None):
        try:
            from groq import Groq
        except ImportError:
            raise RuntimeError(
                "groq is not installed. Run: python -m pip install groq"
            )

        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set")

        self._client = Groq(api_key=key, http_client=llm_http_client())

    def _messages(self, chunk: FileChunk, system_prompt: str, context: str) -> list:
        user_content = f"Please review the following code.\n\n{chunk.content}"
        if context:
            user_content = f"Previous findings context:\n{context}\n\n---\n\n{user_content}"
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def review_chunk(self, chunk: FileChunk, system_prompt: str, context: str = "") -> str:
        response = self._client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=self._messages(chunk, system_prompt, context),
        )
        return response.choices[0].message.content

    def review_chunk_stream(self, chunk: FileChunk, system_prompt: str, context: str = "") -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=self._messages(chunk, system_prompt, context),
            stream=True,
        )
        for part in stream:
            delta = part.choices[0].delta.content
            if delta:
                yield delta
