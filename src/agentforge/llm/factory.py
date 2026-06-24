"""LLM provider factory."""

from agentforge.llm.base import LLMProvider
from agentforge.llm.config import LLMConfigError, LLMProviderConfig
from agentforge.llm.mock import MockLLMProvider
from agentforge.llm.openai_compatible import OpenAICompatibleProvider


def create_llm_provider(config: LLMProviderConfig) -> LLMProvider:
    """Create an LLM provider for the effective provider config."""
    if config.provider == "mock":
        return MockLLMProvider()

    if config.provider == "openai-compatible":
        if not config.api_key:
            raise LLMConfigError(
                "LLM provider 'openai-compatible' requires AGENTFORGE_LLM_API_KEY."
            )
        if not config.model:
            raise LLMConfigError("LLM provider 'openai-compatible' requires llm.model.")
        return OpenAICompatibleProvider(
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds,
        )

    raise LLMConfigError(
        f"Unknown LLM provider {config.provider!r}. "
        "Supported providers: mock, openai-compatible."
    )
