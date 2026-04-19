import os
from typing import Iterator

import anthropic

from agent.chunker import FileChunk
from agent.http_client import llm_http_client
from agent.providers.base import LLMProvider

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192


class AnthropicProvider(LLMProvider):

    def __init__(self, api_key: str | None = None):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self._client = anthropic.Anthropic(api_key=key, http_client=llm_http_client())

    def _build_user_message(self, chunk: FileChunk, context: str) -> str:
        msg = f"Please review the following code.\n\n{chunk.content}"
        if context:
            msg = f"Previous findings context:\n{context}\n\n---\n\n{msg}"
        return msg

    def _system_block(self, system_prompt: str) -> list:
        return [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]

    def review_chunk(self, chunk: FileChunk, system_prompt: str, context: str = "") -> str:
        response = self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=self._system_block(system_prompt),
            messages=[{"role": "user", "content": self._build_user_message(chunk, context)}],
        )
        return response.content[0].text

    def review_chunk_stream(self, chunk: FileChunk, system_prompt: str, context: str = "") -> Iterator[str]:
        with self._client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=self._system_block(system_prompt),
            messages=[{"role": "user", "content": self._build_user_message(chunk, context)}],
        ) as stream:
            yield from stream.text_stream
