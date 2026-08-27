"""Provider-neutral end-of-turn policy placeholder."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TurnDetectionPolicy:
    silence_ms: int = 700
    maximum_utterance_seconds: int = 20
