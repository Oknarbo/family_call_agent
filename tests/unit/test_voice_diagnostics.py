import pytest

from app.config import Settings
from app.domain.exceptions import ProviderUnavailableError
from app.telephony.diagnostics import safe_error
from scripts import check_voice


def test_error_summary_never_exposes_arbitrary_provider_content() -> None:
    for error in (RuntimeError("secret-token"), ProviderUnavailableError("Azure Speech returned HTTP 401 secret")):
        result = safe_error(error)
        assert "reason" not in result
        assert "secret" not in str(result)
    assert safe_error(ProviderUnavailableError("Azure Speech returned HTTP 401"))["reason"].endswith("401")
    assert safe_error(ProviderUnavailableError("Deepgram returned HTTP 403"))["reason"].endswith("403")


async def test_checks_continue_after_failure_without_printing_secrets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    called = []

    async def redis(_settings: Settings) -> str:
        called.append("redis")
        raise RuntimeError("redis://private-password@host")

    async def azure(_settings: Settings) -> str:
        called.append("azure")
        raise ProviderUnavailableError("Azure Speech returned HTTP 401")

    async def deepgram(_settings: Settings) -> str:
        called.append("deepgram")
        return "accepted"

    monkeypatch.setattr(check_voice, "check_redis", redis)
    monkeypatch.setattr(check_voice, "check_azure", azure)
    monkeypatch.setattr(check_voice, "check_deepgram", deepgram)
    assert not await check_voice.run(Settings(_env_file=None))
    output = capsys.readouterr().out
    assert "private-password" not in output
    assert "HTTP 401" in output
    assert "Deepgram: OK" in output
    assert called == ["redis", "azure", "deepgram"]
