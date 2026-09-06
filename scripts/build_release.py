"""Package only deployment source files; never include .env, databases or audio."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def build(root: Path, destination: Path) -> int:
    selected: list[Path] = []
    for name in ("app", "evals", "scripts"):
        for path in (root / name).rglob("*"):
            if (
                "__pycache__" not in path.parts
                and path.is_file()
                and path.suffix in {".py", ".json", ".jsonl", ".mako"}
            ):
                selected.append(path)
    selected.extend(
        root / name
        for name in (
            "Dockerfile",
            "compose.hetzner.yml",
            ".dockerignore",
            "pyproject.toml",
            "README.md",
            "ROADMAP.md",
            "OPENAI.md",
            "LOCAL_ACCESS.md",
            "alembic.ini",
        )
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(selected):
            archive.write(path, path.relative_to(root).as_posix())
    return len(selected)


def main() -> None:
    target = ROOT / "dist" / "zvonko-release.zip"
    count = build(ROOT, target)
    print(f"Release ready: {target} ({count} files). No .env, databases or recordings included.")


if __name__ == "__main__":
    main()
