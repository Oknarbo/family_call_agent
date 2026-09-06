"""One live connection; pending confirmations disappear safely on disconnect."""

import re
from dataclasses import dataclass, field
from uuid import UUID

from app.agent.intents import classify_confirmation, normalize_utterance
from app.agent.prompts import INTRODUCTION
from app.agent.safety_graph import _classify as classify_safety
from app.agent.state import ConversationState
from app.config import Settings
from app.dependencies import application_store
from app.domain.enums import DeliveryStatus, OutboundCallPurpose, OutboundCallStatus, ReminderStatus
from app.domain.exceptions import DomainError
from app.domain.time_parser import NUMBER_WORDS
from app.repositories.protocols import Store
from app.scheduler.planner import IN_FLIGHT, SchedulerPlanner
from app.services.call_outcomes import CallOutcomeService
from app.services.conversation import conversation_turn
from app.services.family_directory import FamilyDirectory
from app.utils.datetime import utc_now


def response_outcome(text: str, medication: bool) -> str:
    value = normalize_utterance(text).strip(" .!?,")
    if medication:
        # Accept complete declarations, never substring hits such as "popila sam možda".
        if re.fullmatch(
            r"(?:da[, ]+)?(?:jesam|(?:upravo )?(?:popila|popio|uzela|uzeo) sam(?: (?:tabletu|lijek))?)", value
        ):
            return "taken"
        if re.fullmatch(r"(?:ne[, ]+)?(?:još )?nisam(?: (?:popila|popio|uzela|uzeo)(?: (?:tabletu|lijek))?)?", value):
            return "not_taken"
        return "unclear"
    return "completed" if classify_safety(text) == "completed" else "unclear"


def snooze_minutes(text: str) -> int | None:
    value = normalize_utterance(text)
    match = re.search(r"\bza\s+(\d+|" + "|".join(NUMBER_WORDS) + r")\s+(minut\w*|sat\w*)\b", value)
    if not match:
        return None
    token = match[1]
    quantity = int(token) if token.isdigit() else NUMBER_WORDS[token]
    return quantity * (60 if match[2].startswith("sat") else 1)


@dataclass
class VoiceConversation:
    settings: Settings
    caller_phone: str
    provider_call_id: str
    outbound_id: UUID | None = None
    state: ConversationState = field(default_factory=lambda: ConversationState())
    outbound_done: bool = False
    awaiting_delay: bool = False
    unclear_outbound_answers: int = 0

    async def greeting(self) -> str:
        async with application_store(self.settings) as store:
            FamilyDirectory(store).identify(self.caller_phone)
            if self.outbound_id is None:
                if self.settings.telephony_provider == "twilio" and not self.settings.twilio_outbound_enabled:
                    return "Probni način rada. Automatski pozivi još nisu uključeni. " + INTRODUCTION
                return INTRODUCTION
            call = store.outbound_calls[self.outbound_id]
            if call.provider_call_id != self.provider_call_id:
                raise ValueError("Call mismatch")
            if call.purpose == OutboundCallPurpose.MEDICATION_DOSE:
                question = " Jesi li uzeo ili uzela tabletu? Ako želiš da nazovem kasnije, reci za koliko minuta."
            elif call.purpose == OutboundCallPurpose.HOUSEHOLD_SAFETY:
                question = " Javi mi kad to napraviš. Možeš zatražiti da nazovem kasnije."
            else:
                question = " Možeš mi potvrditi ili reći da nazovem kasnije."
            return "Bok, ovdje Zvonko. " + call.message + question

    async def reply(self, text: str) -> tuple[str, bool]:
        value = normalize_utterance(text).strip(" .!?,")
        if value in {"doviđenja", "hvala doviđenja", "prekini poziv", "kraj"}:
            return "Doviđenja.", True
        if not value:
            return "Nisam jasno čuo. Možeš li ponoviti?", False
        if self.outbound_id is not None and not self.outbound_done:
            return await self._outbound_reply(text)
        self.state.update(
            {
                "call_id": self.provider_call_id,
                "provider_call_id": self.provider_call_id,
                "caller_phone": self.caller_phone,
                "current_utterance": text,
                "now_iso": utc_now().isoformat(),
            }
        )
        self.state = await conversation_turn(self.state, self.settings)
        return self.state.get("response_text") or "Možeš li ponoviti?", False

    async def _outbound_reply(self, text: str) -> tuple[str, bool]:
        value = normalize_utterance(text)
        wants_snooze = self.awaiting_delay or bool(re.search(r"\b(nazovi|zovni|podsjeti)\b", value))
        if re.search(r"\b(ne|nemoj)\b", value):
            wants_snooze = False
            self.awaiting_delay = False
        delay = snooze_minutes(text) if wants_snooze else None
        if wants_snooze and (delay is None or not 1 <= delay <= 1440):
            self.awaiting_delay = True
            return "Za koliko minuta želiš da te nazovem? Reci, primjerice, za petnaest minuta.", False
        async with application_store(self.settings) as store:
            FamilyDirectory(store).identify(self.caller_phone)
            assert self.outbound_id is not None
            call = store.outbound_calls[self.outbound_id]
            if call.provider_call_id != self.provider_call_id:
                raise ValueError("Call mismatch")
            medication = call.purpose == OutboundCallPurpose.MEDICATION_DOSE
            outcome = "call_later" if wants_snooze else response_outcome(text, medication)
            if (
                not wants_snooze
                and call.purpose == OutboundCallPurpose.GENERAL_REMINDER
                and classify_confirmation(text) == "confirmed"
            ):
                outcome = "completed"
            try:
                CallOutcomeService(store, self.settings).record_response(
                    call.id,
                    outcome,
                    now=utc_now(),
                    delay_minutes=delay,
                )
            except DomainError:
                store.abort()
                return "Nisam mogao spremiti odgovor. Molim te pokušaj ponovno.", False
            if call.user_outcome != outcome:
                return "Ovaj podsjetnik više nije aktivan. Doviđenja.", True
        if outcome == "call_later":
            return f"Dogovoreno, nazvat ću te za {delay} minuta. Doviđenja.", True
        if outcome in {"taken", "completed"}:
            self.outbound_done = True
            return (
                "Zabilježio sam da je tableta uzeta." if medication else "U redu, zabilježeno."
            ) + " Doviđenja.", True
        if outcome == "not_taken":
            return "Zabilježio sam da tableta nije uzeta. Želiš li da te nazovem kasnije? Reci za koliko minuta.", False
        self.unclear_outbound_answers += 1
        if self.unclear_outbound_answers >= 3:
            return "Nisam uspio razumjeti odgovor. Nisam zabilježio potvrdu. Doviđenja.", True
        return "Nisam siguran jesam li razumio. Reci jesi li to napravio ili želiš da nazovem kasnije.", False

    async def transport_failed(self) -> None:
        if self.outbound_id is not None:
            async with application_store(self.settings) as store:
                call = store.outbound_calls[self.outbound_id]
                if call.user_outcome not in {"taken", "completed", "call_later", "message_delivered"}:
                    call.error_code = "voice_transport_failed"
                    call.user_outcome = "voice_failed"
                    call.updated_at = utc_now()

    async def audio_delivered(self) -> None:
        if self.outbound_id is None:
            return
        async with application_store(self.settings) as store:
            call = store.outbound_calls[self.outbound_id]
            if call.purpose in {OutboundCallPurpose.MEDICATION_DOSE, OutboundCallPurpose.HOUSEHOLD_SAFETY}:
                return  # Hearing a prompt is never a medication or safety confirmation.
            if call.user_outcome is None:
                call.user_outcome = "message_delivered"
            if call.status == OutboundCallStatus.COMPLETED and call.user_outcome == "message_delivered":
                if call.purpose == OutboundCallPurpose.GENERAL_REMINDER and call.related_entity_type == "reminder":
                    reminder = store.reminders[call.related_entity_id]
                    if not reminder.recurrence_rule:
                        reminder.status = ReminderStatus.COMPLETED
                elif call.related_entity_type == "notification":
                    notice = store.notifications[call.related_entity_id]
                    notice.delivery_status, notice.delivered_at = DeliveryStatus.SENT, utc_now()


def check_outbound(store: Store, call_id: UUID, sid: str, to_number: str, settings: Settings) -> None:
    """Bind only the dispatched call addressed to the registered recipient."""
    call = store.outbound_calls.get(call_id)
    if call is None or call.status not in IN_FLIGHT | {OutboundCallStatus.DELIVERY_UNKNOWN}:
        raise ValueError("Unknown or undispatched call")
    if not SchedulerPlanner(store, settings).active(call):
        raise ValueError("Inactive call")
    member = FamilyDirectory(store).by_id(call.target_user_id)
    if member.phone_number_e164 != to_number or (call.provider_call_id and call.provider_call_id != sid):
        raise ValueError("Call association mismatch")
    CallOutcomeService(store, settings).record_status(call_id, sid, OutboundCallStatus.ANSWERED, now=utc_now())
