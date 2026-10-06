from __future__ import annotations

from pathlib import Path

from PIL import Image

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


def test_integration_brand_assets_are_transparent_and_high_resolution() -> None:
    brand_dir = Path("custom_components/entity_controller/brand")

    for filename, dimensions in (("icon.png", (256, 256)), ("icon@2x.png", (512, 512))):
        with Image.open(brand_dir / filename) as image:
            assert image.size == dimensions
            assert image.mode == "RGBA"
            assert image.getchannel("A").getextrema() == (0, 255)

    assert (brand_dir / "icon.svg").is_file()
    assert not (brand_dir / "dark_icon.svg").exists()
    assert not (brand_dir / "dark_icon.png").exists()


def test_brand_icon_matches_selected_c_and_two_dots() -> None:
    # Sample stable interior points, not antialiased edges. This rejects the
    # old navy dial/home/bulb/clock artwork and verifies the added centre dot.
    with Image.open("custom_components/entity_controller/brand/icon@2x.png") as image:
        assert image.getpixel((256, 70)) == (3, 169, 244, 255)
        assert image.getpixel((240, 256)) == (255, 255, 255, 255)
        assert image.getpixel((350, 256)) == (255, 255, 255, 255)
        assert image.getpixel((120, 256)) == (255, 255, 255, 255)
        assert image.getpixel((280, 256)) == (3, 169, 244, 255)
