"""Caller identification, separate from action authorization."""

from uuid import UUID, uuid5

from app.config import Settings
from app.domain.enums import FamilyRole
from app.domain.exceptions import InactiveCallerError, NotFoundError, UnknownCallerError, ValidationError
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
        aliases = {"mamu": "mama", "mami": "mama", "tatu": "tata", "tati": "tata", "svena": "sven", "svenu": "sven"}
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

    def seed(self, settings: Settings, *, only_role: FamilyRole | None = None) -> list[FamilyMemberRecord]:
        """Add missing members; Sven is optional and existing records are preserved."""

        definitions = [
            ("Mama", FamilyRole.MAMA, settings.mama_phone_e164 or "+385910000001"),
            ("Tata", FamilyRole.TATA, settings.tata_phone_e164 or "+385910000002"),
            ("Branko", FamilyRole.BRANKO, settings.branko_phone_e164 or "+385910000003"),
            ("Nataša", FamilyRole.NATASA, settings.natasa_phone_e164 or "+385910000004"),
        ]
        if settings.sven_phone_e164:
            definitions.append(("Sven", FamilyRole.SVEN, settings.sven_phone_e164))
        definitions = [item for item in definitions if only_role is None or item[1] == only_role]
        numbers = {member.phone_number_e164 for member in self.store.family_members.values()}
        pending = []
        for name, role, phone in definitions:
            if uuid5(SEED_NAMESPACE, role.value) in self.store.family_members:
                continue
            normalized = normalize_phone_number(phone)
            if normalized in numbers:
                raise ValidationError("Each family member needs a distinct phone number")
            numbers.add(normalized)
            pending.append((name, role, normalized))
        now = utc_now()
        created: list[FamilyMemberRecord] = []
        for name, role, phone in pending:
            member_id = uuid5(SEED_NAMESPACE, role.value)
            member = FamilyMemberRecord(
                id=member_id,
                display_name=name,
                phone_number_e164=normalize_phone_number(phone),
                role=role,
                timezone=settings.default_timezone,
                notification_preferences={"channels": ["call"]},
                escalation_preferences={
                    "safety_no_answer_attempts": settings.safety_escalate_after_no_answers,
                    "important_no_answer_contact_ids": [
                        str(uuid5(SEED_NAMESPACE, contact)) for contact in ("branko", "natasa") if contact != role.value
                    ],
                },
                created_at=now,
                updated_at=now,
            )
            self.store.family_members[member.id] = member
            created.append(member)
        self.store.save()
        return created
