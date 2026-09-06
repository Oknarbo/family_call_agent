import json

import httpx
import pytest

from app.config import Settings
from app.domain.exceptions import ProviderUnavailableError
from app.providers.llm.openai import OpenAILanguageProvider


def settings() -> Settings:
    return Settings(_env_file=None, llm_provider="openai", llm_model="gpt-4.1-mini", openai_api_key="fake-secret")


def payload(text: str, understood: bool = True) -> dict[str, object]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": json.dumps({"understood": understood, "canonical_utterance": text})}
                ],
            }
        ],
    }


async def test_private_bounded_structured_request() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url == "https://api.openai.com/v1/responses"
        assert body["store"] is False
        assert body["text"]["format"]["strict"] is True
        assert body["max_output_tokens"] == 700
        assert "+385910000001" not in body["input"]
        assert "tools" not in body
        return httpx.Response(200, json=payload("Podsjeti me za dvije minute da provjerim poštu"))

    result = await OpenAILanguageProvider(settings(), transport=httpx.MockTransport(handle)).normalize_turn(
        "Nazovi me na +385910000001 za dvije minute", mode="request"
    )
    assert result and "dvije minute" in result


@pytest.mark.parametrize("code", [401, 429, 500])
async def test_no_retry_no_secret_in_error(code: int) -> None:
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(code, text="fake-secret private transcript")

    with pytest.raises(ProviderUnavailableError) as exc:
        await OpenAILanguageProvider(settings(), transport=httpx.MockTransport(handle)).normalize_turn(
            "da", mode="confirmation"
        )
    assert len(requests) == 1 and "fake-secret" not in str(exc.value)


@pytest.mark.parametrize(
    "body",
    [
        {"status": "incomplete"},
        {"status": "completed", "output": []},
        {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]},
    ],
)
async def test_incomplete_and_refusal_never_become_confirmation(body: dict[str, object]) -> None:
    with pytest.raises(ProviderUnavailableError):
        await OpenAILanguageProvider(
            settings(), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
        ).normalize_turn("da", mode="confirmation")


async def test_negative_clause_cannot_become_approval() -> None:
    provider = OpenAILanguageProvider(
        settings(), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload("da")))
    )
    assert await provider.normalize_turn("Da, ali nisam siguran", mode="confirmation") is None
