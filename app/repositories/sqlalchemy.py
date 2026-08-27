"""Small async SQLAlchemy repositories used by production composition."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FamilyMember


class SqlAlchemyFamilyMemberRepository:
    """Database-backed caller directory."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def by_phone(self, phone_e164: str) -> FamilyMember | None:
        result = await self.session.execute(select(FamilyMember).where(FamilyMember.phone_number_e164 == phone_e164))
        return result.scalar_one_or_none()

    async def by_id(self, member_id: UUID) -> FamilyMember | None:
        return await self.session.get(FamilyMember, member_id)
