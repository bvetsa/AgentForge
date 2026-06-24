from collections.abc import Mapping
from typing import Any

import pytest

from agentforge.llm import (
    AgentInvocation,
    AgentResponse,
    LLMConfigError,
    LLMProviderConfig,
    LLMProviderError,
    MockLLMProvider,
    OpenAICompatibleProvider,
    create_llm_provider,
)


def test_provider_factory_returns_mock_by_default() -> None:
    provider = create_llm_provider(LLMProviderConfig())

    assert isinstance(provider, MockLLMProvider)


def test_provider_factory_rejects_unknown_provider() -> None:
    config = LLMProviderConfig(provider="unknown")

    with pytest.raises(LLMConfigError, match="Unknown LLM provider"):
        create_llm_provider(config)


def test_openai_compatible_provider_requires_api_key() -> None:
    config = LLMProviderConfig(provider="openai-compatible", model="test-model")

    with pytest.raises(LLMConfigError, match="requires AGENTFORGE_LLM_API_KEY"):
        create_llm_provider(config)


def test_openai_compatible_provider_requires_model() -> None:
    config = LLMProviderConfig(provider="openai-compatible", api_key="sk-test")

    with pytest.raises(LLMConfigError, match="requires llm.model"):
        create_llm_provider(config)


def test_openai_compatible_provider_uses_injected_transport() -> None:
    transport = RecordingTransport(
        {
            "id": "chatcmpl-test",
            "model": "response-model",
            "choices": [
                {
                    "message": {"content": "Generated plan"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        }
    )
    provider = OpenAICompatibleProvider(
        api_key="sk-test-secret",
        model="request-model",
        base_url="https://llm.example/v1",
        timeout_seconds=4.5,
        transport=transport,
    )

    response = provider.generate(_invocation())

    assert isinstance(response, AgentResponse)
    assert response.content == "Generated plan"
    assert response.provider == "openai-compatible"
    assert response.model == "response-model"
    assert response.metadata == {
        "id": "chatcmpl-test",
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        "finish_reason": "stop",
    }
    assert transport.calls == [
        {
            "url": "https://llm.example/v1/chat/completions",
            "authorization": "Bearer sk-test-secret",
            "model": "request-model",
            "timeout_seconds": 4.5,
            "messages": [
                {"role": "system", "content": "Plan carefully."},
                {"role": "user", "content": "prompt text"},
            ],
        }
    ]


def test_openai_compatible_provider_handles_provider_errors_clearly() -> None:
    provider = OpenAICompatibleProvider(
        api_key="sk-test-secret",
        model="request-model",
        transport=FailingTransport("provider returned a 500"),
    )

    with pytest.raises(LLMProviderError, match="provider returned a 500"):
        provider.generate(_invocation())


def test_openai_compatible_provider_sanitizes_api_key_from_errors() -> None:
    provider = OpenAICompatibleProvider(
        api_key="sk-test-secret",
        model="request-model",
        transport=FailingTransport("bad Authorization: Bearer sk-test-secret"),
    )

    with pytest.raises(LLMProviderError) as error:
        provider.generate(_invocation())

    message = str(error.value)
    assert "sk-test-secret" not in message
    assert "[REDACTED]" in message


def test_openai_compatible_provider_rejects_invalid_response_shape() -> None:
    provider = OpenAICompatibleProvider(
        api_key="sk-test-secret",
        model="request-model",
        transport=RecordingTransport({"choices": []}),
    )

    with pytest.raises(LLMProviderError, match="did not include choices"):
        provider.generate(_invocation())


def _invocation() -> AgentInvocation:
    return AgentInvocation(
        agent_name="planner",
        description="Plans work.",
        system_prompt="Plan carefully.",
        input_keys=["user_request"],
        output_key="plan",
        inputs={"user_request": "Add a todo endpoint"},
        prompt="prompt text",
    )


class RecordingTransport:
    def __init__(self, response_payload: Mapping[str, Any]) -> None:
        self.response_payload = response_payload
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "url": url,
                "authorization": headers["Authorization"],
                "model": payload["model"],
                "timeout_seconds": timeout_seconds,
                "messages": payload["messages"],
            }
        )
        return self.response_payload


class FailingTransport:
    def __init__(self, message: str) -> None:
        self.message = message

    def __call__(
        self,
        _url: str,
        _headers: Mapping[str, str],
        _payload: Mapping[str, Any],
        _timeout_seconds: float,
    ) -> Mapping[str, Any]:
        raise RuntimeError(self.message)
