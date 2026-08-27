"""Caller identification, separate from action authorization."""

from uuid import UUID, uuid5

from app.config import Settings
from app.domain.enums import FamilyRole
from app.domain.exceptions import InactiveCallerError, NotFoundError, UnknownCallerError
from app.repositories.protocols import Store
from app.schemas import FamilyMemberRecord
from app.utils.datetime import utc_now
from app.utils.phone_numbers import normalize_phone_number

SEED_NAMESPACE = UUID("a2b4c6d8-1f20-4a30-8b40-123456789abc")


class FamilyDirectory:
    """Identify active allowlisted family members by normalized Caller ID."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def identify(self, raw_phone: str) -> FamilyMemberRecord:
        normalized = normalize_phone_number(raw_phone)
        member = next(
            (item for item in self.store.family_members.values() if item.phone_number_e164 == normalized),
            None,
        )
        if member is None:
            raise UnknownCallerError
        if not member.is_active:
            raise InactiveCallerError
        return member

    def by_id(self, member_id: UUID) -> FamilyMemberRecord:
        try:
            member = self.store.family_members[member_id]
        except KeyError as exc:
            raise NotFoundError from exc
        if not member.is_active:
            raise InactiveCallerError
        return member

    def by_name(self, value: str) -> FamilyMemberRecord:
        normalized = value.casefold().strip()
        aliases = {"mamu": "mama", "mami": "mama", "tatu": "tata", "tati": "tata"}
        normalized = aliases.get(normalized, normalized)
        member = next(
            (
                item
                for item in self.store.family_members.values()
                if item.display_name.casefold() == normalized or item.role.value == normalized
            ),
            None,
        )
        if member is None:
            raise NotFoundError
        return member

    def seed(self, settings: Settings) -> list[FamilyMemberRecord]:
        """Seed four stable users using environment-provided or synthetic development numbers."""

        definitions = [
            ("Mama", FamilyRole.MAMA, settings.mama_phone_e164 or "+385910000001"),
            ("Tata", FamilyRole.TATA, settings.tata_phone_e164 or "+385910000002"),
            ("Branko", FamilyRole.BRANKO, settings.branko_phone_e164 or "+385910000003"),
            ("Nataša", FamilyRole.NATASA, settings.natasa_phone_e164 or "+385910000004"),
        ]
        now = utc_now()
        created: list[FamilyMemberRecord] = []
        for name, role, phone in definitions:
            member_id = uuid5(SEED_NAMESPACE, role.value)
            member = FamilyMemberRecord(
                id=member_id,
                display_name=name,
                phone_number_e164=normalize_phone_number(phone),
                role=role,
                timezone=settings.default_timezone,
                notification_preferences={"channels": ["call"]},
                escalation_preferences={"safety_no_answer_attempts": settings.safety_escalate_after_no_answers},
                created_at=now,
                updated_at=now,
            )
            self.store.family_members[member.id] = member
            created.append(member)
        self.store.save()
        return created
