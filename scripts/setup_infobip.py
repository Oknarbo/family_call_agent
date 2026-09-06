"""Print Infobip setup checklist for outbound voice."""

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    print("Infobip outbound voice checklist:")
    print(f"- INFOBIP_BASE_URL={settings.infobip_base_url}")
    print("- INFOBIP_API_KEY=<App key from portal.infobip.com/dev/api-keys>")
    print("- INFOBIP_FROM_NUMBER=<E.164 sender, digits only or with +>")
    print("- TELEPHONY_PROVIDER=infobip")
    print("- Required API scope: voice message / TTS send")
    print("")
    print("Smoke test (after API is running):")
    print('curl -X POST http://localhost:8000/internal/test-voice-call \\')
    print('  -H "Authorization: Bearer $APP_SECRET_KEY" \\')
    print('  -H "Content-Type: application/json" \\')
    print('  -d \'{"to_number":"+385...", "message":"Bok, ovdje Zvonko."}\'')


if __name__ == "__main__":
    main()
