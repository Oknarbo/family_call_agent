"""Read account-specific Twilio voice rates; never place or verify a call."""

import asyncio

import httpx

from app.config import Settings, get_settings
from app.dependencies import application_store
from app.services.family_directory import FamilyDirectory


async def prices(settings: Settings, target: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise ValueError("Configure Twilio credentials first.")
    origins = [("Purchased number", settings.twilio_from_number)]
    if settings.twilio_outbound_caller_id:
        origins.append(("Separate outbound caller ID", settings.twilio_outbound_caller_id))
    async with httpx.AsyncClient(transport=transport, timeout=15, follow_redirects=False) as client:
        for label, origin in origins:
            if not origin:
                continue
            response = await client.get(
                f"https://pricing.twilio.com/v2/Voice/Numbers/{target}",
                params={"OriginationNumber": origin},
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            )
            if response.status_code != 200:
                print(f"{label}: pricing request failed (HTTP {response.status_code}).")
                continue
            data = response.json()
            rates = data.get("outbound_call_prices", [])
            if not rates:
                print(f"{label}: no outbound price returned.")
            for rate in rates:
                print(f"{label}: {rate.get('current_price')} {data.get('price_unit')} per minute")
    print("No call placed. Carrier charges, speech, streaming, rental and taxes are not included.")


async def main() -> None:
    settings = get_settings()
    async with application_store(settings) as store:
        phone = FamilyDirectory(store).by_name("Branko").phone_number_e164
        store.abort()
    await prices(settings, phone)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"Pricing check failed: {type(exc).__name__}. No call placed.")
        raise SystemExit(1) from None
