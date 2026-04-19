"""
Returns the correct provider instance based on a name string.
To add a new provider: import it here and add an entry to PROVIDERS.
"""

from agent.providers.base import LLMProvider

PROVIDERS: dict[str, str] = {
    "anthropic": "agent.providers.anthropic_provider.AnthropicProvider",
    "gemini": "agent.providers.gemini_provider.GeminiProvider",
    "groq": "agent.providers.groq_provider.GroqProvider",
    # Future: "ollama": "agent.providers.ollama_provider.OllamaProvider",
    # Future: "openai": "agent.providers.openai_provider.OpenAIProvider",
}


def get_provider(name: str, api_key: str | None = None) -> LLMProvider:
    name = name.lower().strip()
    if name not in PROVIDERS:
        supported = ", ".join(PROVIDERS.keys())
        raise ValueError(f"Unknown provider '{name}'. Supported: {supported}")

    module_path, class_name = PROVIDERS[name].rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(api_key=api_key)


def available_providers() -> list[str]:
    return list(PROVIDERS.keys())
