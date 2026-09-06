"""Safe error summaries: never log provider bodies, credentials or transcripts."""

import re

from app.domain.exceptions import ProviderUnavailableError


def safe_error(exc: Exception) -> dict[str, str]:
    result = {"error_type": type(exc).__name__}
    if isinstance(exc, ProviderUnavailableError) and re.fullmatch(
        r"(?:Azure Speech|Deepgram) (?:returned HTTP [1-5][0-9]{2}|connection failed|"
        r"speech connection failed|returned invalid audio|rejected the audio stream|"
        r"Speech key is missing|API key is not configured)", str(exc)
    ):
        result["reason"] = str(exc)
    return result
