import pytest

from app.agent.intents import classify_confirmation


@pytest.mark.parametrize("text", ["da", "Da!", "Da, da.", "Da. Potvrđujem.", "potvrđujem", "Potvrdujem.",
                                  "Točno.", "Tocno, tako je!", " U redu, može. "])
def test_spoken_confirmations(text: str) -> None:
    assert classify_confirmation(text) == "confirmed"


@pytest.mark.parametrize("text", ["Da, ne.", "Da, ali nisam siguran.", "Možda da", "Ne potvrđujem", "Da, sutra"])
def test_positive_prefix_is_not_sufficient(text: str) -> None:
    assert classify_confirmation(text) != "confirmed"


def test_correction_after_positive_prefix() -> None:
    assert classify_confirmation("Da, nego za pet minuta") == "correction_requested"
