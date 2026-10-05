# Task 08 — Integration branding and icon assets

## Goal
Replace the generic/missing integration artwork with a distinctive Entity Controller icon that remains readable in Home Assistant at small sizes and works in both light and dark themes.

## Selected visual direction

The selected identity is the user's newer concept: **a white open C with two dots on a cyan rounded square**.

Final concept to reproduce as production artwork:

- cyan `#03A9F4` rounded-square base;
- thick white open C, rounded ends;
- small white dot in the middle and a larger white dot at the right;
- geometric, modern, flat/vector-like;
- no text, no `EC` monogram, no node graph, no Wi-Fi/cloud motif;
- preserve the selected silhouette at small sizes.

The previous navy dial with home/light/clock artwork is superseded.

## Production simplification

The generated concept is a visual direction, not a pixel-perfect production asset. The final artwork should:

- simplify unnecessary gradients, gloss and shadows;
- use consistent ring/stroke thickness;
- keep strong negative space and a clear silhouette;
- remain recognizable at 32–64 px;
- keep both dots separate from the C after resizing;
- avoid visual similarity to the Home Assistant logo or another integration mark.

## Asset requirements

Prepare at minimum:

- `custom_components/entity_controller/brand/icon.png` — 256×256 PNG;
- `custom_components/entity_controller/brand/icon@2x.png` — 512×512 PNG;
- source/master artwork retained in the repository for future resizing, preferably vector/SVG as a source asset.

Optional only if testing shows one universal icon is insufficient:

- `dark_icon.png`;
- `dark_icon@2x.png`.

A separate logo is not required initially. Home Assistant can use the icon as the fallback when no logo is supplied.

## Home Assistant branding mechanism

Starting with Home Assistant 2026.3, custom integrations can ship their own brand images directly inside the integration under a local `brand/` directory. Local brand images take priority over the old Home Assistant brands CDN path.

For Entity Controller, use:

```text
custom_components/entity_controller/
├── __init__.py
├── manifest.json
└── brand/
    ├── icon.png
    └── icon@2x.png
```

Official reference:
https://developers.home-assistant.io/docs/core/integration/brand_images/

No separate PR to `home-assistant/brands` is needed for this custom integration on supported Home Assistant versions.

## Validation

Before closing the task:

- verify the integration no longer shows `icon not available`;
- verify the icon in the Integrations page and Config Entry header;
- inspect it in both light and dark themes;
- inspect at small integration-list/device-page sizes;
- verify no cropping from Home Assistant's rounded/circular presentation;
- verify `icon.png` is exactly 256×256 and `icon@2x.png` exactly 512×512;
- update README branding/screenshots only after the final assets are committed;
- add the branding addition to `CHANGELOG.md`.

## Acceptance criteria

- Entity Controller no longer presents as “icon not available” on supported Home Assistant versions.
- The selected newer concept is used: cyan square, open C, small centre dot and larger right dot.
- It does not depend on text to be understood.
- It remains legible in light and dark Home Assistant themes and at 32–64 px.
- PNG assets are shipped locally under `custom_components/entity_controller/brand/`.
- Source/master artwork is retained for future resizing.

## Related

Entity-specific MDI icons are covered separately by entity/UI work. This task is only the integration/product brand mark.

## HACS 2.0.5 limitation verified 2026-10-05

The installed HACS frontend still reads `brands.home-assistant.io` for custom
repositories. The local HA assets cannot change that dashboard URL. Upstream
[integration PR 5388](https://github.com/hacs/integration/pull/5388) and
[frontend PR 945](https://github.com/hacs/frontend/pull/945) remain open.
Do not claim that updating Entity Controller alone fixes HACS' missing icon.
