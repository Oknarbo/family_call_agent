"""Optional member survives a fresh SQL connection with the existing schema."""

from app.config import Settings
from app.dependencies import application_store
from app.domain.enums import FamilyRole
from app.services.family_directory import FamilyDirectory


async def test_sven_registration_survives_restart(durable_settings: Settings) -> None:
    settings = durable_settings.model_copy(update={"sven_phone_e164": "+385910000005"})
    async with application_store(settings) as store:
        added = FamilyDirectory(store).seed(settings, only_role=FamilyRole.SVEN)
        assert len(added) == 1
        member_id = added[0].id
    async with application_store(settings) as store:
        assert FamilyDirectory(store).identify("+385910000005").id == member_id
        assert store.family_members[member_id].role == FamilyRole.SVEN
        assert FamilyDirectory(store).seed(settings, only_role=FamilyRole.SVEN) == []
