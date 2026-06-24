"""OpenAI-compatible chat completions LLM provider."""

from __future__ import annotations

import json
import re
import socket
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agentforge.llm.base import AgentInvocation, AgentResponse, LLMProvider, LLMProviderError

DEFAULT_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
Transport = Callable[[str, Mapping[str, str], Mapping[str, Any], float], Mapping[str, Any]]


class OpenAICompatibleProvider(LLMProvider):
    """Generate responses through a chat-completions-compatible HTTP API."""

    provider_name = "openai-compatible"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        transport: Transport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.chat_completions_url = _chat_completions_url(base_url)
        self.timeout_seconds = timeout_seconds
        self._transport = transport or UrllibChatCompletionTransport()

    def generate(self, invocation: AgentInvocation) -> AgentResponse:
        """Generate one agent response using chat completions."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": invocation.system_prompt},
                {"role": "user", "content": invocation.prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            response_payload = self._transport(
                self.chat_completions_url,
                headers,
                payload,
                self.timeout_seconds,
            )
            content = _extract_message_content(response_payload)
        except LLMProviderError as error:
            raise LLMProviderError(_sanitize_error_message(str(error), self.api_key)) from error
        except Exception as error:
            message = _sanitize_error_message(str(error), self.api_key)
            raise LLMProviderError(f"OpenAI-compatible LLM request failed: {message}") from error

        response_model = response_payload.get("model")
        return AgentResponse(
            content=content,
            provider=self.provider_name,
            model=response_model if isinstance(response_model, str) else self.model,
            metadata=_response_metadata(response_payload),
        )


class UrllibChatCompletionTransport:
    """Minimal urllib transport for JSON chat-completions requests."""

    def __call__(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=dict(headers),
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as error:
            error_body = _safe_read_error_body(error)
            detail = f": {error_body}" if error_body else ""
            raise LLMProviderError(
                f"OpenAI-compatible API returned HTTP {error.code}{detail}"
            ) from error
        except TimeoutError as error:
            raise LLMProviderError(
                f"OpenAI-compatible API request timed out after {timeout_seconds} seconds."
            ) from error
        except socket.timeout as error:
            raise LLMProviderError(
                f"OpenAI-compatible API request timed out after {timeout_seconds} seconds."
            ) from error
        except URLError as error:
            raise LLMProviderError(
                f"OpenAI-compatible API request failed: {error.reason}"
            ) from error
        except OSError as error:
            raise LLMProviderError(
                f"OpenAI-compatible API request failed: {error}"
            ) from error

        try:
            decoded = json.loads(response_body)
        except json.JSONDecodeError as error:
            raise LLMProviderError(
                "OpenAI-compatible API returned invalid JSON."
            ) from error
        if not isinstance(decoded, dict):
            raise LLMProviderError("OpenAI-compatible API returned a non-object JSON response.")
        return decoded


def _chat_completions_url(base_url: str | None) -> str:
    if base_url is None:
        return DEFAULT_CHAT_COMPLETIONS_URL

    value = base_url.rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    return f"{value}/chat/completions"


def _extract_message_content(response_payload: Mapping[str, Any]) -> str:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMProviderError("OpenAI-compatible API response did not include choices.")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise LLMProviderError("OpenAI-compatible API response choice was invalid.")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise LLMProviderError("OpenAI-compatible API response choice did not include a message.")

    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return _content_parts_to_text(content)
    raise LLMProviderError("OpenAI-compatible API response message did not include text content.")


def _content_parts_to_text(content: list[object]) -> str:
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    if parts:
        return "".join(parts)
    raise LLMProviderError("OpenAI-compatible API response content parts did not include text.")


def _response_metadata(response_payload: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("id", "object", "created", "usage"):
        if key in response_payload:
            metadata[key] = response_payload[key]

    choices = response_payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        finish_reason = choices[0].get("finish_reason")
        if finish_reason is not None:
            metadata["finish_reason"] = finish_reason
    return metadata


def _safe_read_error_body(error: HTTPError) -> str:
    try:
        return error.read().decode("utf-8", errors="replace")[:1000]
    except OSError:
        return ""


def _sanitize_error_message(message: str, api_key: str) -> str:
    sanitized = message.replace(api_key, "[REDACTED]") if api_key else message
    sanitized = re.sub(r"Bearer\s+\S+", "Bearer [REDACTED]", sanitized)
    return re.sub(r"sk-[A-Za-z0-9_\-]+", "[REDACTED]", sanitized)
