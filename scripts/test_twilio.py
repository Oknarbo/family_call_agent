"""One explicitly requested call to registered Branko; repeat keys never redial."""

import argparse
import asyncio
from datetime import timedelta

from app.config import get_settings
from app.dependencies import application_store
from app.domain.enums import ReminderType
from app.domain.exceptions import DomainError
from app.scheduler.jobs import dispatch_outbound_call
from app.scheduler.planner import SchedulerPlanner
from app.services.family_directory import FamilyDirectory
from app.services.reminders import ReminderService
from app.telephony.twilio_security import voice_configured
from app.utils.datetime import utc_now


async def run(key: str, place_call: bool) -> None:
    settings = get_settings()
    voice_configured(settings)
    if settings.telephony_provider != "twilio":
        raise ValueError("Postavi TELEPHONY_PROVIDER=twilio.")
    async with application_store(settings) as store:
        branko = FamilyDirectory(store).by_name("Branko")
        if not branko.is_active:
            raise ValueError("Branko nije aktivan.")
        print("Postavke su popunjene i Branko je u bazi. Ključevi još nisu provjereni kod providera.")
        if not place_call:
            print("Nema poziva. Za jedan stvarni poziv koristi --call. To troši kvotu/novac providera.")
            return
        idem = "twilio-smoke:" + key
        if idem in store.idempotency:
            print("Ovaj test već je izrađen; isti ključ neće pokrenuti još jedan poziv.")
            return
        due = utc_now() + timedelta(seconds=2)
        reminder = ReminderService(store).schedule(
            requester_user_id=branko.id,
            target_user_id=branko.id,
            message="Ovo je probni poziv. Ako me čuješ, reci da.",
            scheduled_for=due,
            reminder_type=ReminderType.GENERAL,
            reminder_subtype=None,
            recurrence_rule=None,
            source_call_id=idem,
            idempotency_key=idem,
        )
        planner = SchedulerPlanner(store, settings)
        from app.domain.enums import OutboundCallPurpose

        call = planner.ensure_call(
            kind="reminder",
            entity_id=reminder.id,
            target_id=branko.id,
            due=due,
            message=reminder.message,
            purpose=OutboundCallPurpose.GENERAL_REMINDER,
            now=utc_now(),
        )
        call_id = str(call.id)
    await asyncio.sleep(max(0, (due - utc_now()).total_seconds()))
    result = await dispatch_outbound_call({"settings": settings, "allow_twilio_test": True}, call_id)
    print("Rezultat slanja:", result["status"])
    print("Zahtjev za poziv nije potvrda da je osoba odgovorila; ishode bilježi Twilio webhook.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call", action="store_true", help="Place one real, billable call to Branko")
    parser.add_argument("--key", default="first-test", help="Use a new key only to intentionally start another test")
    args = parser.parse_args()
    if not 1 <= len(args.key) <= 60:
        parser.error("Test key must contain 1-60 characters")
    try:
        asyncio.run(run(args.key, args.call))
    except (DomainError, ValueError) as exc:
        print(str(exc))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
