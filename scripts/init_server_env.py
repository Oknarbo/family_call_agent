"""Create a private server template once; never overwrite existing secrets."""

import os
import secrets
from pathlib import Path


def main() -> None:
    path = Path(__file__).resolve().parents[1] / ".env"
    content = f"""APP_ENV=production
APP_SECRET_KEY={secrets.token_hex(32)}
POSTGRES_PASSWORD={secrets.token_hex(24)}
PUBLIC_BASE_URL=https://voice.example.com
DEFAULT_TIMEZONE=Europe/Zagreb
ASSISTANT_GRAMMATICAL_GENDER=masculine

# Real family numbers in +385... format; Sven is optional.
MAMA_PHONE_E164=
TATA_PHONE_E164=
BRANKO_PHONE_E164=
NATASA_PHONE_E164=
SVEN_PHONE_E164=

# Keep telephony disabled during infrastructure setup; enable for the voice pilot.
TELEPHONY_PROVIDER=development
STT_PROVIDER=development
TTS_PROVIDER=azure
LLM_PROVIDER=development
LLM_MODEL=deterministic-hr
OPENAI_API_KEY=
OPENAI_TIMEOUT_SECONDS=12
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
TWILIO_OUTBOUND_CALLER_ID=
TWILIO_OUTBOUND_ENABLED=false
DEEPGRAM_API_KEY=
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=westeurope
AZURE_SPEECH_VOICE=hr-HR-SreckoNeural
AZURE_SPEECH_RATE_PERCENT=-10
STORE_TRANSCRIPT_SUMMARIES=false
LOG_LEVEL=INFO
# DATABASE_URL and REDIS_URL are supplied by compose.hetzner.yml.
"""
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(".env already exists and was not changed. Edit the existing file manually.")
        return
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
    print("Created .env without printing secrets. Enter family numbers and keys using nano .env.")


if __name__ == "__main__":
    main()
