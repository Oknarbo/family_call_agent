"""Croatian wording templates kept separate from domain decisions."""

from datetime import datetime
from zoneinfo import ZoneInfo

INTRODUCTION = "Bok, ovdje Zvonko. Kako ti mogu pomoći?"
UNKNOWN_CALLER = "Ovaj broj nije registriran za korištenje Zvonka. Doviđenja."

TARGET_CALL_PHRASES: dict[str, str] = {
    "Mama": "mamu",
    "Tata": "tatu",
    "Branko": "Branka",
    "Nataša": "Natašu",
}


def format_local(value: datetime, timezone: str = "Europe/Zagreb") -> str:
    local = value.astimezone(ZoneInfo(timezone))
    return f"{local.day}. {local.month}. u {local.hour}:{local.minute:02d}"


def target_call_phrase(display_name: str, *, is_self: bool) -> str:
    if is_self:
        return "tebe"
    return TARGET_CALL_PHRASES.get(display_name, display_name)


def reminder_confirmation(
    minutes: int | None,
    message: str,
    *,
    target_phrase: str = "tebe",
    scheduled_label: str | None = None,
) -> str:
    when = scheduled_label or (f"za {minutes} minuta" if minutes is not None else "")
    if target_phrase == "tebe":
        if minutes is not None:
            return f"U redu. Nazvat ću te {when} i podsjetiti {message}. Je li to točno?"
        return f"U redu. Podsjetit ću te {message}. Je li to točno?"
    if minutes is not None:
        return f"U redu. Nazvat ću {target_phrase} {when} i podsjetiti {message}. Je li to točno?"
    label = scheduled_label or message
    return f"U redu. Nazvat ću {target_phrase} {label}. Je li to točno?"


def medication_confirmation(
    name: str,
    hour: int,
    *,
    target_phrase: str = "tebe",
    inventory: int | None = None,
) -> str:
    stock = (
        f" Kod {target_phrase} trenutačno ima {inventory}." if inventory is not None and target_phrase != "tebe" else ""
    )
    if inventory is not None and target_phrase == "tebe":
        stock = f" Trenutačno ih imaš {inventory}."
    if target_phrase == "tebe":
        return f"U redu. Zvat ću te svaki dan u {hour} da uzmeš jednu tabletu {name}.{stock} Je li to točno?"
    return f"U redu. Zvat ću {target_phrase} svaki dan u {hour} da popije tabletu {name}.{stock} Je li to točno?"
