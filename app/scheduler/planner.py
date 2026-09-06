"""Materialize a bounded SQL outbox. Redis is only a disposable delivery queue."""

import hashlib
import json
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.config import Settings
from app.domain.enums import (
    AppointmentStatus,
    DeliveryStatus,
    MedicationDoseStatus,
    OutboundCallPurpose,
    OutboundCallStatus,
    ReminderStatus,
    ReminderType,
)
from app.domain.exceptions import ValidationError
from app.repositories.protocols import Store
from app.scheduler.recurrence import occurrences
from app.schemas import NotificationRecord, OutboundCallRecord
from app.services.audit import write_audit
from app.services.medication_plans import MedicationPlanService

PENDING = {OutboundCallStatus.SCHEDULED}
IN_FLIGHT = {OutboundCallStatus.DIALING, OutboundCallStatus.RINGING, OutboundCallStatus.ANSWERED}
ACTIVE_APPOINTMENTS = {AppointmentStatus.SCHEDULED, AppointmentStatus.RESCHEDULED, AppointmentStatus.CONFIRMED}


def fingerprint(*values: object) -> str:
    return hashlib.sha256(json.dumps(values, default=str, sort_keys=True).encode()).hexdigest()


class SchedulerPlanner:
    def __init__(self, store: Store, settings: Settings) -> None:
        self.store, self.settings = store, settings

    def version(self, kind: str, entity_id: UUID) -> str:
        if kind == "reminder":
            r = self.store.reminders[entity_id]
            return fingerprint(r.scheduled_for, r.recurrence_rule, r.message, r.timezone, r.target_user_id)
        if kind == "medication_dose":
            p = self.store.medication_plans[self.store.medication_doses[entity_id].medication_plan_id]
            return fingerprint(p.schedule_rule, p.local_schedule_time, p.timezone, p.display_name)
        if kind == "appointment":
            a = self.store.appointments[entity_id]
            return fingerprint(
                a.scheduled_for, a.reminder_offsets_minutes, a.provider_name, a.location, a.notify_user_ids
            )
        return ""

    def active(self, call: OutboundCallRecord) -> bool:
        member = self.store.family_members.get(call.target_user_id)
        if member is None or not member.is_active:
            return False
        kind, entity_id = call.related_entity_type, call.related_entity_id
        if any(
            c.related_entity_type == kind
            and c.related_entity_id == entity_id
            and c.occurrence_for == call.occurrence_for
            and c.user_outcome in {"completed", "taken"}
            and c.purpose != OutboundCallPurpose.FAMILY_NOTIFICATION
            for c in self.store.outbound_calls.values()
        ):
            return False
        try:
            if kind == "reminder":
                r = self.store.reminders[entity_id]
                enabled = r.status in {ReminderStatus.SCHEDULED, ReminderStatus.EXECUTING}
            elif kind == "medication_dose":
                d = self.store.medication_doses[entity_id]
                p = self.store.medication_plans[d.medication_plan_id]
                enabled = p.is_active and d.status not in {
                    MedicationDoseStatus.USER_REPORTED_TAKEN,
                    MedicationDoseStatus.CANCELLED,
                    MedicationDoseStatus.USER_REPORTED_NOT_TAKEN,
                    MedicationDoseStatus.UNCLEAR_RESPONSE,
                }
            elif kind == "appointment":
                enabled = self.store.appointments[entity_id].status in ACTIVE_APPOINTMENTS
            elif kind == "notification":
                n = self.store.notifications[entity_id]
                enabled = n.delivery_status == DeliveryStatus.PENDING
                if n.notification_type == "low_stock":
                    p = self.store.medication_plans[n.related_entity_id]
                    enabled = enabled and p.is_active and p.current_inventory is not None
                    enabled = (
                        enabled and p.current_inventory is not None and p.current_inventory <= p.low_stock_threshold
                    )
            else:
                return False
            return enabled and (not call.source_version or call.source_version == self.version(kind, entity_id))
        except KeyError:
            return False

    def ensure_call(
        self,
        *,
        kind: str,
        entity_id: UUID,
        target_id: UUID,
        due: datetime,
        message: str,
        purpose: OutboundCallPurpose,
        now: datetime,
        priority: int = 0,
    ) -> OutboundCallRecord:
        version = self.version(kind, entity_id)
        key = "scheduled:" + fingerprint(kind, entity_id, target_id, due, version)
        if key in self.store.idempotency:
            existing = self.store.outbound_calls[self.store.idempotency[key]]
            if existing.status == OutboundCallStatus.SCHEDULED:
                existing.message = message
            return existing
        call = OutboundCallRecord(
            target_user_id=target_id,
            scheduled_for=due,
            occurrence_for=due,
            purpose=purpose,
            message=message,
            related_entity_type=kind,
            related_entity_id=entity_id,
            source_version=version,
            priority=priority,
            idempotency_key=key,
            created_at=now,
            updated_at=now,
        )
        self.store.outbound_calls[call.id] = call
        self.store.idempotency[key] = call.id
        return call

    def dispatchable(self, call: OutboundCallRecord, now: datetime) -> bool:
        if not self.active(call):
            return False
        if call.related_entity_type == "appointment":
            return self.store.appointments[call.related_entity_id].scheduled_for > now
        if call.purpose == OutboundCallPurpose.MEDICATION_DOSE:
            due = self.store.medication_doses[call.related_entity_id].scheduled_for
            if call.attempt_number > 1 and any(
                c.related_entity_type == "medication_dose"
                and c.related_entity_id == call.related_entity_id
                and c.user_outcome == "call_later"
                for c in self.store.outbound_calls.values()
            ):
                due = call.scheduled_for  # Honor an explicit user-requested postponement.
            if now - due > timedelta(minutes=self.settings.medication_catchup_minutes):
                call.error_code = "medication_window_missed"
                self._audit(call.id, "medication.reminder_window_missed", now)
                return False
        if call.related_entity_type == "reminder":
            r = self.store.reminders[call.related_entity_id]
            if r.recurrence_rule and call.occurrence_for is not None:
                try:
                    recent = list(
                        occurrences(
                            r.recurrence_rule,
                            r.scheduled_for.astimezone(ZoneInfo(r.timezone)).time(),
                            r.timezone,
                            start=max(r.scheduled_for, now - timedelta(days=7)),
                            end=now,
                        )
                    )
                except ValidationError:
                    return False
                if recent and call.occurrence_for < recent[-1]:
                    return False
        return True

    def materialize(self, now: datetime) -> list[OutboundCallRecord]:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        horizon = now + timedelta(minutes=self.settings.scheduler_lookahead_minutes)
        self._reminders(now, horizon)
        self._medications(now, horizon)
        self._appointments(now, horizon)
        self._notifications(now, horizon)
        for call in self.store.outbound_calls.values():
            if (call.status == OutboundCallStatus.SCHEDULED and not self.active(call)) or (
                call.status == OutboundCallStatus.SCHEDULED
                and call.scheduled_for <= now
                and not self.dispatchable(call, now)
            ):
                call.status, call.updated_at = OutboundCallStatus.CANCELLED, now
            if call.status in IN_FLIGHT and (now - (call.started_at or call.updated_at)).total_seconds() > (
                self.settings.scheduler_stale_call_seconds
            ):
                call.status = OutboundCallStatus.DELIVERY_UNKNOWN
                call.error_code, call.updated_at = "missing_provider_outcome", now
                self._audit(call.id, "outbound_call.needs_reconciliation", now)
        self.store.save()
        return sorted(
            (
                c
                for c in self.store.outbound_calls.values()
                if c.status == OutboundCallStatus.SCHEDULED and c.scheduled_for <= horizon
            ),
            key=lambda c: (-c.priority, c.scheduled_for, str(c.id)),
        )

    def _reminders(self, now: datetime, horizon: datetime) -> None:
        for r in self.store.reminders.values():
            if r.status not in {ReminderStatus.SCHEDULED, ReminderStatus.EXECUTING}:
                continue
            dates = [r.scheduled_for] if r.scheduled_for <= horizon else []
            if r.recurrence_rule:
                try:
                    dates = list(
                        occurrences(
                            r.recurrence_rule,
                            r.scheduled_for.astimezone(ZoneInfo(r.timezone)).time(),
                            r.timezone,
                            start=max(r.scheduled_for, now - timedelta(days=7)),
                            end=horizon,
                        )
                    )
                    # After downtime call only for the latest missed occurrence.
                    past = [date for date in dates if date <= now]
                    dates = past[-1:] + [date for date in dates if date > now]
                except ValidationError:
                    r.status = ReminderStatus.FAILED
                    self._audit(r.id, "reminder.unsupported_recurrence", now)
                    continue
            for due in dates:
                purpose = (
                    OutboundCallPurpose.HOUSEHOLD_SAFETY
                    if r.reminder_type == ReminderType.HOUSEHOLD_SAFETY
                    else OutboundCallPurpose.GENERAL_REMINDER
                )
                self.ensure_call(
                    kind="reminder",
                    entity_id=r.id,
                    target_id=r.target_user_id,
                    due=due,
                    message=r.message,
                    purpose=purpose,
                    now=now,
                    priority=r.priority,
                )

    def _medications(self, now: datetime, horizon: datetime) -> None:
        cutoff = now - timedelta(minutes=self.settings.medication_catchup_minutes)
        for p in self.store.medication_plans.values():
            if not p.is_active:
                continue
            try:
                dates = list(
                    occurrences(
                        p.schedule_rule,
                        p.local_schedule_time,
                        p.timezone,
                        start=max(p.created_at, cutoff),
                        end=horizon,
                        clock_override=True,
                    )
                )
            except ValidationError:
                self._audit(p.id, "medication.unsupported_recurrence", now)
                continue
            for due in dates:
                key = f"scheduled-dose:{p.id}:{due.isoformat()}"
                if not any(
                    d.medication_plan_id == p.id and d.scheduled_for == due
                    for d in self.store.medication_doses.values()
                ):
                    MedicationPlanService(self.store).create_dose(p.id, due, key)
            self._low_stock(p.id, now)
        for d in self.store.medication_doses.values():
            if d.status not in {MedicationDoseStatus.SCHEDULED, MedicationDoseStatus.REMINDER_STARTED}:
                continue
            effective_due = d.scheduled_for
            dose_calls = [
                c
                for c in self.store.outbound_calls.values()
                if c.related_entity_type == "medication_dose"
                and c.related_entity_id == d.id
                and c.purpose == OutboundCallPurpose.MEDICATION_DOSE
            ]
            if any(c.user_outcome == "call_later" for c in dose_calls):
                effective_due = max([effective_due, *(c.scheduled_for for c in dose_calls)])
            if effective_due < cutoff:
                d.status = MedicationDoseStatus.CANCELLED
                d.notes = "Propušten vremenski prozor podsjetnika; uzimanje lijeka nije zaključeno."
                self._audit(d.id, "medication.reminder_window_missed", now)
                continue
            p = self.store.medication_plans[d.medication_plan_id]
            if p.is_active and d.scheduled_for <= horizon:
                # A changed plan must not leave future doses at the old time.
                try:
                    matching = list(
                        occurrences(
                            p.schedule_rule,
                            p.local_schedule_time,
                            p.timezone,
                            start=d.scheduled_for,
                            end=d.scheduled_for,
                            clock_override=True,
                        )
                    )
                except ValidationError:
                    matching = []
                if not matching:
                    d.status = MedicationDoseStatus.CANCELLED
                    continue
                self.ensure_call(
                    kind="medication_dose",
                    entity_id=d.id,
                    target_id=d.user_id,
                    due=d.scheduled_for,
                    message=f"Podsjetnik za tabletu {p.display_name} u dogovoreno vrijeme.",
                    purpose=OutboundCallPurpose.MEDICATION_DOSE,
                    now=now,
                    priority=5,
                )

    def _low_stock(self, plan_id: UUID, now: datetime) -> None:
        p = self.store.medication_plans[plan_id]
        if p.current_inventory is None or p.current_inventory > p.low_stock_threshold:
            return
        crossings = [
            e
            for e in self.store.inventory_events.values()
            if e.medication_plan_id == p.id and e.previous_quantity > p.low_stock_threshold >= e.new_quantity
        ]
        episode = str(max(crossings, key=lambda e: (e.created_at, str(e.id))).id) if crossings else "initial"
        key = f"low-stock:{p.id}:{p.low_stock_threshold}:{episode}"
        message = (
            f"Prema evidenciji preostalo je {p.current_inventory} tableta {p.display_name}. "
            "Podsjećam te da dogovoriš termin s doktoricom za obnovu terapije."
        )
        if key in self.store.idempotency:
            existing = self.store.notifications[self.store.idempotency[key]]
            if existing.delivery_status == DeliveryStatus.PENDING:
                existing.message = message
            return
        n = NotificationRecord(
            target_user_id=p.user_id,
            notification_type="low_stock",
            message=message,
            related_entity_type="medication_plan",
            related_entity_id=p.id,
            idempotency_key=key,
            created_at=now,
        )
        self.store.notifications[n.id], self.store.idempotency[key] = n, n.id

    def _appointments(self, now: datetime, horizon: datetime) -> None:
        for a in self.store.appointments.values():
            if a.status not in ACTIVE_APPOINTMENTS or a.scheduled_for <= now:
                continue
            for offset in set(a.reminder_offsets_minutes):
                due = a.scheduled_for - timedelta(minutes=offset)
                if offset <= 0 or due < a.created_at or due > horizon:
                    continue
                label = a.scheduled_for.astimezone(ZoneInfo(a.timezone)).strftime("%d.%m. u %H:%M")
                for target in dict.fromkeys([a.patient_user_id, *a.notify_user_ids]):
                    self.ensure_call(
                        kind="appointment",
                        entity_id=a.id,
                        target_id=target,
                        due=due,
                        message=f"Podsjetnik na pregled {label} kod {a.provider_name or 'liječnika'}.",
                        purpose=OutboundCallPurpose.APPOINTMENT_REMINDER,
                        now=now,
                    )

    def _notifications(self, now: datetime, horizon: datetime) -> None:
        for n in self.store.notifications.values():
            if n.delivery_status == DeliveryStatus.PENDING and n.created_at <= horizon:
                self.ensure_call(
                    kind="notification",
                    entity_id=n.id,
                    target_id=n.target_user_id,
                    due=n.created_at,
                    message=n.message,
                    purpose=OutboundCallPurpose.FAMILY_NOTIFICATION,
                    now=now,
                )

    def _audit(self, entity_id: UUID, action: str, now: datetime) -> None:
        key = f"scheduler-audit:{action}:{entity_id}"
        if key not in self.store.idempotency:
            record = write_audit(
                self.store,
                actor_user_id=None,
                action=action,
                entity_type="scheduler",
                entity_id=entity_id,
                source_call_id=None,
                metadata={"at": now.isoformat()},
            )
            self.store.idempotency[key] = record.id
