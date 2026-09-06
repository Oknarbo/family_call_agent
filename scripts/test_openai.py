"""Configuration check, or one explicitly requested non-personal LLM probe."""

import argparse
import asyncio

from app.config import get_settings
from app.domain.exceptions import ProviderUnavailableError
from app.providers.llm.openai import OpenAILanguageProvider


async def main(request: bool) -> None:
    settings = get_settings()
    if settings.llm_provider != "openai" or not settings.openai_api_key or settings.llm_model == "deterministic-hr":
        raise ProviderUnavailableError("Set LLM_PROVIDER=openai, OPENAI_API_KEY and LLM_MODEL.")
    if not request:
        print("Configuration present. No API request or phone call. Use --request for one billable text probe.")
        return
    result = await OpenAILanguageProvider(settings).normalize_turn(
        "Možeš li me za dvije minute trgnuti da pogledam poštu?", mode="request"
    )
    print("Interpretation:", result or "unclear")
    print("No reminder saved and no phone call placed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", action="store_true")
    try:
        asyncio.run(main(parser.parse_args().request))
    except ProviderUnavailableError as exc:
        print(str(exc))
        raise SystemExit(1) from None
