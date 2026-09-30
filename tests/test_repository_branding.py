from __future__ import annotations

from pathlib import Path

FORBIDDEN_BRANDING = (
    "dano" + "bot",
    "daniel" + "bkr",
    "daniel" + "ha",
    "pay" + "pal.me/" + "daniel" + "b160",
    "gofund.me/" + "7a2487d5",
    "The Budget " + "Smart Home",
    "ec-" + "docs",
)


def test_repository_public_files_do_not_reference_legacy_owner_branding() -> None:
    checked_paths = [
        path
        for path in Path(".").rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and ".superpowers" not in path.parts
        and "__pycache__" not in path.parts
    ]

    offenders: list[str] = []
    for path in checked_paths:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lowered = content.lower()
        for forbidden in FORBIDDEN_BRANDING:
            if forbidden.lower() in lowered:
                offenders.append(f"{path}: {forbidden}")

    assert offenders == []
