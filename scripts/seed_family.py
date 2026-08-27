"""Seed the four allowlisted family members into PostgreSQL."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import create_session_factory
from app.models import FamilyMember
from app.repositories.memory import MemoryStore
from app.services.family_directory import FamilyDirectory


async def seed(session: AsyncSession) -> None:
    settings = get_settings()
    records = FamilyDirectory(MemoryStore()).seed(settings)
    for record in records:
        existing = await session.get(FamilyMember, record.id)
        if existing is None:
            session.add(
                FamilyMember(
                    id=record.id,
                    display_name=record.display_name,
                    phone_number_e164=record.phone_number_e164,
                    role=record.role,
                    timezone=record.timezone,
                    is_active=record.is_active,
                    notification_preferences=record.notification_preferences,
                    escalation_preferences=record.escalation_preferences,
                    preferred_assistant_wording=record.preferred_assistant_wording,
                )
            )
    await session.commit()


async def async_main() -> None:
    factory = create_session_factory()
    async with factory() as session:
        await seed(session)


if __name__ == "__main__":
    asyncio.run(async_main())
