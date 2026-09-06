"""Explicit domain state values."""

from enum import StrEnum


class FamilyRole(StrEnum):
    MAMA = "mama"
    TATA = "tata"
    BRANKO = "branko"
    NATASA = "natasa"
    SVEN = "sven"


class CallDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallStatus(StrEnum):
    STARTED = "started"
    ANSWERED = "answered"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    COMPLETED = "completed"


class ReminderType(StrEnum):
    GENERAL = "general"
    MEDICATION = "medication"
    DOCTOR_APPOINTMENT = "doctor_appointment"
    HOUSEHOLD_SAFETY = "household_safety"
    FAMILY_NOTIFICATION = "family_notification"


class ReminderStatus(StrEnum):
    PENDING_CONFIRMATION = "pending_confirmation"
    SCHEDULED = "scheduled"
    EXECUTING = "executing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SafetySubtype(StrEnum):
    TEA = "tea"
    STOVE = "stove"
    OVEN = "oven"
    POT = "pot"
    FOOD = "food"
    IRON = "iron"
    OTHER = "other"


class OutboundCallStatus(StrEnum):
    SCHEDULED = "scheduled"
    DIALING = "dialing"
    RINGING = "ringing"
    ANSWERED = "answered"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DELIVERY_UNKNOWN = "delivery_unknown"


class OutboundCallPurpose(StrEnum):
    GENERAL_REMINDER = "general_reminder"
    MEDICATION_DOSE = "medication_dose"
    APPOINTMENT_REMINDER = "appointment_reminder"
    HOUSEHOLD_SAFETY = "household_safety"
    FAMILY_NOTIFICATION = "family_notification"


class MedicationDoseStatus(StrEnum):
    SCHEDULED = "scheduled"
    REMINDER_STARTED = "reminder_started"
    USER_REPORTED_TAKEN = "user_reported_taken"
    USER_REPORTED_NOT_TAKEN = "user_reported_not_taken"
    UNCLEAR_RESPONSE = "unclear_response"
    CALL_LATER_REQUESTED = "call_later_requested"
    NO_ANSWER = "no_answer"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"


class MedicationInventoryEventType(StrEnum):
    INITIAL_STOCK = "initial_stock"
    DOSE_CONFIRMED = "dose_confirmed"
    BOX_ADDED = "box_added"
    MANUAL_CORRECTION = "manual_correction"
    REVERSAL = "reversal"


class AppointmentStatus(StrEnum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"
    COMPLETED_USER_REPORTED = "completed_user_reported"
    MISSED_USER_REPORTED = "missed_user_reported"
    UNKNOWN = "unknown"


class AppointmentReminderOutcome(StrEnum):
    REMEMBERED = "remembered"
    REPEAT_REQUESTED = "repeat_requested"
    FAMILY_NOTIFICATION_REQUESTED = "family_notification_requested"
    FOLLOWUP_REQUESTED = "followup_requested"
    UNCLEAR = "unclear"
    NO_ANSWER = "no_answer"


class SafetyReminderOutcome(StrEnum):
    COMPLETED = "completed"
    NOT_COMPLETED = "not_completed"
    CALL_AGAIN_REQUESTED = "call_again_requested"
    UNCLEAR = "unclear"
    NO_ANSWER = "no_answer"
    ESCALATED = "escalated"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class ConfirmationStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    AWAITING = "awaiting"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CORRECTION_REQUESTED = "correction_requested"


class Intent(StrEnum):
    GENERAL_REMINDER_CREATE = "general_reminder_create"
    REMINDER_LIST = "reminder_list"
    REMINDER_CANCEL = "reminder_cancel"
    SAFETY_REMINDER_CREATE = "safety_reminder_create"
    MEDICATION_PLAN_CREATE = "medication_plan_create"
    MEDICATION_RESPONSE = "medication_response"
    MEDICATION_INVENTORY_QUERY = "medication_inventory_query"
    MEDICATION_INVENTORY_ADD = "medication_inventory_add"
    MEDICATION_INVENTORY_SET = "medication_inventory_set"
    APPOINTMENT_CREATE = "appointment_create"
    APPOINTMENT_QUERY = "appointment_query"
    APPOINTMENT_UPDATE = "appointment_update"
    APPOINTMENT_CANCEL = "appointment_cancel"
    UNKNOWN = "unknown"


READ_ONLY_INTENTS = {
    Intent.REMINDER_LIST,
    Intent.MEDICATION_INVENTORY_QUERY,
    Intent.APPOINTMENT_QUERY,
}
