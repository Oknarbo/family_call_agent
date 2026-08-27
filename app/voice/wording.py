"""Assistant grammatical-gender wording."""

from typing import Literal


def recorded_phrase(gender: Literal["masculine", "feminine"] = "masculine") -> str:
    return "zabilježio sam" if gender == "masculine" else "zabilježila sam"
