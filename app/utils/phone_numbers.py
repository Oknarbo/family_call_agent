"""Phone normalization isolated from authorization."""

import phonenumbers

from app.domain.exceptions import ValidationError


def normalize_phone_number(value: str, default_region: str = "HR") -> str:
    """Normalize a Croatian or international number to E.164."""

    try:
        parsed = phonenumbers.parse(value.strip(), default_region)
    except phonenumbers.NumberParseException as exc:
        raise ValidationError from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValidationError
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
