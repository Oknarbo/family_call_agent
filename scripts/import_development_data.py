"""Explicit, atomic JSON import into an empty SQL database; source stays untouched."""

import argparse
import asyncio
from pathlib import Path

from app.dependencies import application_store
from app.repositories.memory import MemoryStore


async def import_data(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError("JSON source file does not exist")
    source = MemoryStore(path)
    async with application_store() as target:
        if target.idempotency or any(getattr(target, name) for name in source._collections):
            raise ValueError("Import requires an empty database; existing data will not be overwritten")
        for name in source._collections:
            getattr(target, name).update(getattr(source, name))
        target.idempotency.update(source.idempotency)
    print("Razvojni podaci su uvezeni. Izvorna JSON datoteka nije promijenjena.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    asyncio.run(import_data(args.path))


if __name__ == "__main__":
    main()
