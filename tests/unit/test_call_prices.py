from urllib.parse import parse_qs

import httpx
import pytest

from scripts.check_call_prices import prices
from tests.unit.test_twilio import configured


async def test_prices_only_get_and_do_not_print_numbers(capsys: pytest.CaptureFixture[str]) -> None:
    origins = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.host == "pricing.twilio.com"
        origins.extend(parse_qs(request.url.query.decode())["OriginationNumber"])
        return httpx.Response(200, json={"price_unit": "USD", "outbound_call_prices": [{"current_price": "0.095"}]})

    settings = configured(twilio_outbound_caller_id="+385910000004")
    await prices(settings, "+385910000003", transport=httpx.MockTransport(handle))
    output = capsys.readouterr().out
    assert "0.095 USD" in output
    assert "+385" not in output and "fake-token" not in output
    assert origins == [settings.twilio_from_number, settings.twilio_outbound_caller_id]
