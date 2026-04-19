"""
Abstract base class for LLM providers.
To add a new provider: subclass LLMProvider, implement both methods, register in factory.py.
"""

from abc import ABC, abstractmethod
from typing import Iterator

from agent.chunker import FileChunk


class LLMProvider(ABC):

    @abstractmethod
    def review_chunk(self, chunk: FileChunk, system_prompt: str, context: str = "") -> str:
        """Blocking call — returns full review text."""

    @abstractmethod
    def review_chunk_stream(self, chunk: FileChunk, system_prompt: str, context: str = "") -> Iterator[str]:
        """Streaming call — yields text deltas."""
