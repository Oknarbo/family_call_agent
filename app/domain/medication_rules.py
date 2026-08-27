"""Medication semantics that never infer physical ingestion."""

from app.domain.enums import MedicationDoseStatus

DEDUCTIBLE_DOSE_STATUSES = {MedicationDoseStatus.USER_REPORTED_TAKEN}


def should_decrement_inventory(status: MedicationDoseStatus) -> bool:
    """Only explicit user-reported confirmation permits an inventory deduction."""

    return status in DEDUCTIBLE_DOSE_STATUSES


def assert_not_medical_advice(text: str) -> bool:
    """Return false for common dosage-advice requests handled by a safety response."""

    normalized = text.casefold()
    risky = ("uzmem još jednu", "duplu dozu", "preskočim", "prestanem", "nuspoj")
    return not any(phrase in normalized for phrase in risky)


MEDICAL_SAFETY_RESPONSE = (
    "Ne mogu sigurno savjetovati da uzmeš još jednu. Nazovi liječnika, ljekarnika ili "
    "nekoga iz obitelji koji ti može pomoći."
)
