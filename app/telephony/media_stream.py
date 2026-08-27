"""Voice media stream session correlation boundary."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class MediaStreamSession:
    provider_call_id: str
    stream_id: str | None = None
    connected: bool = False
    received_sequence_numbers: set[int] = field(default_factory=set)

    def accept_sequence(self, sequence_number: int) -> bool:
        """Reject duplicate media frames without storing raw audio."""

        if sequence_number in self.received_sequence_numbers:
            return False
        self.received_sequence_numbers.add(sequence_number)
        return True
