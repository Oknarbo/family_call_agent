"""Deterministic Croatian intent and response classification for local operation."""

import re
import unicodedata

from app.domain.enums import Intent, MedicationDoseStatus


def normalize_utterance(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().strip().split())


def classify_intent(text: str) -> Intent:
    value = normalize_utterance(text)
    if any(phrase in value for phrase in ("otkaži", "otkazi", "ne treba više", "ipak ne treba")):
        if any(word in value for word in ("doktor", "pregled", "termin")):
            return Intent.APPOINTMENT_CANCEL
        return Intent.REMINDER_CANCEL
    if any(word in value for word in ("kad imam doktora", "sljedeći pregled", "kad mama ide doktoru", "sutra naručen")):
        return Intent.APPOINTMENT_QUERY
    if any(word in value for word in ("pomakni pregled", "promijeni termin", "ne sutra, prekosutra")):
        return Intent.APPOINTMENT_UPDATE
    if any(word in value for word in ("imam doktora", "imam pregled", "naručena sam", "idem doktor")):
        return Intent.APPOINTMENT_CREATE
    if any(word in value for word in ("kupila sam još", "dodaj novu kutiju", "još jednu kutiju")):
        return Intent.MEDICATION_INVENTORY_ADD
    if any(word in value for word in ("krivo je stanje", "imam još", "postavi stanje")) and "tablet" in value:
        return Intent.MEDICATION_INVENTORY_SET
    if any(word in value for word in ("koliko mi je tableta", "koliko je tableta", "stanje tableta")):
        return Intent.MEDICATION_INVENTORY_QUERY
    if any(word in value for word in ("svaki dan", "svako jutro", "svaku večer")) and any(
        word in value for word in ("tabletu", "lijek", "terapij")
    ):
        return Intent.MEDICATION_PLAN_CREATE
    if any(word in value for word in ("popila sam", "uzela sam lijek", "nisam je popila", "još nisam")):
        return Intent.MEDICATION_RESPONSE
    if any(word in value for word in ("koje podsjetnike", "sljedeći podsjetnik", "podsjetnike imam")):
        return Intent.REMINDER_LIST
    if any(word in value for word in ("čaj", "plamenik", "pećnic", "lonac", "štednjak", "glačalo")) and any(
        word in value for word in ("nazovi", "zovni", "podsjeti", "javi")
    ):
        return Intent.SAFETY_REMINDER_CREATE
    if any(word in value for word in ("nazovi", "zovni", "pozovi", "podsjeti", "sjeti me", "javi mi")):
        return Intent.GENERAL_REMINDER_CREATE
    return Intent.UNKNOWN


CONFIRMATIONS = {
    "da",
    "može",
    "u redu",
    "tako je",
    "točno",
    "potvrđujem",
    "dobro",
    "može tako",
    "jesam",
    "ajde",
}
REJECTIONS = {"ne", "nije", "otkaži", "ipak ne treba", "čekaj"}


def classify_confirmation(text: str) -> str:
    value = normalize_utterance(text)
    value = value.replace("đ", "d")
    value = "".join(c for c in unicodedata.normalize("NFD", value) if not unicodedata.combining(c))
    value = " ".join(re.sub(r"[^\w\s]", " ", value).split())
    if value in REJECTIONS:
        return "rejected"
    if any(
        phrase in value
        for phrase in (
            "krivo si razumio",
            "nisam to rekla",
            "promijeni",
            "nije u",
            "nego",
            "rekla sam",
        )
    ):
        return "correction_requested"
    # Consume the whole answer, including repeated short confirmations. A
    # positive prefix never overrides a negative or corrective clause.
    phrases = {
        "".join(c for c in unicodedata.normalize("NFD", p.replace("đ", "d")) if not unicodedata.combining(c))
        for p in CONFIRMATIONS
    }
    pattern = "|".join(re.escape(p) for p in sorted(phrases, key=len, reverse=True))
    if re.fullmatch(rf"(?:{pattern})(?:\s+(?:{pattern}))*", value):
        return "confirmed"
    if value in {"otkazi", "cekaj"}:
        return "rejected"
    return "unclear"


def classify_medication_response(text: str) -> MedicationDoseStatus:
    value = normalize_utterance(text)
    if any(phrase in value for phrase in ("nazovi me za", "podsjeti me kasnije", "zovni me za", "pijem kavu")):
        return MedicationDoseStatus.CALL_LATER_REQUESTED
    if any(phrase in value for phrase in ("nisam", "još nisam", "neću sada", "zaboravila sam")):
        return MedicationDoseStatus.USER_REPORTED_NOT_TAKEN
    if any(phrase in value for phrase in ("možda", "ne znam", "mislim da jesam", "ne sjećam se", "valjda")):
        return MedicationDoseStatus.UNCLEAR_RESPONSE
    if any(phrase in value for phrase in ("jesam", "popila sam", "uzela sam", "upravo sam")):
        return MedicationDoseStatus.USER_REPORTED_TAKEN
    return MedicationDoseStatus.UNCLEAR_RESPONSE


def extract_integer(text: str) -> int | None:
    match = re.search(r"\b(\d{1,4})\b", text)
    return int(match.group(1)) if match else None


def extract_safety_subtype(text: str) -> str:
    value = normalize_utterance(text)
    mapping = {
        "čaj": "tea",
        "pećnic": "oven",
        "lonac": "pot",
        "hranu": "food",
        "glačalo": "iron",
        "štednjak": "stove",
        "plamenik": "stove",
    }
    return next((subtype for phrase, subtype in mapping.items() if phrase in value), "other")


def extract_provider_name(text: str) -> str | None:
    match = re.search(r"(?:kod|doktor(?:ice|a)?)\s+([A-ZČĆĐŠŽ][\wČĆĐŠŽčćđšž-]+)", text)
    if not match:
        return None
    value = match.group(1)
    if value.casefold() in {"doktora", "doktorice"}:
        return None
    return value
