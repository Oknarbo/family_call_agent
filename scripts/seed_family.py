"""Explicitly seed an empty database; never overwrite existing family settings."""

import asyncio

from app.config import get_settings
from app.dependencies import application_store
from app.domain.enums import FamilyRole
from app.services.family_directory import FamilyDirectory


async def async_main() -> None:
    settings = get_settings()
    async with application_store(settings) as store:
        if store.family_members:
            if settings.sven_phone_e164:
                added = FamilyDirectory(store).seed(settings, only_role=FamilyRole.SVEN)
                print("Sven je dodan u bazu." if added else "Sven već postoji; postojeće postavke su sačuvane.")
            print("Obitelj već postoji; postojeći brojevi i postavke ostaju sačuvani.")
            return
        if settings.app_env == "production" and not all(
            (
                settings.mama_phone_e164,
                settings.tata_phone_e164,
                settings.branko_phone_e164,
                settings.natasa_phone_e164,
            )
        ):
            raise ValueError("Za početni produkcijski seed unesi sva četiri obiteljska broja.")
        FamilyDirectory(store).seed(settings)
    print("Obitelj je spremljena u bazu.")


if __name__ == "__main__":
    asyncio.run(async_main())
