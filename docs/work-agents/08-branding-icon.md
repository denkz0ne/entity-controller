# Task 08 — Integration branding and icon assets

## Goal
Replace the generic/missing integration artwork with a distinctive Entity Controller icon that remains readable in Home Assistant at small sizes and works in both light and dark themes.

## Selected visual direction

The earlier node/flow-graph direction is discarded. The selected identity is **a central control center governing multiple entities**.

Final concept to reproduce as production artwork:

- dark navy / indigo rounded-square base;
- one large **master control dial** in the upper center;
- the dial uses a cyan/aqua ring and a short vertical indicator;
- three subordinate circular entity symbols below, connected to the master control;
- left symbol: **home**;
- center symbol: **light bulb**;
- right symbol: **time / clock** — explicitly a clock, not thermometer/climate;
- geometric, modern, flat/vector-like;
- no text, no `EC` monogram, no node graph, no Wi-Fi/cloud motif;
- the icon should read first as “one controller governing multiple entities”.

The Home / Light / Time glyphs are illustrative examples only. They must not imply that Entity Controller is restricted to those domains.

## Production simplification

The generated concept is a visual direction, not a pixel-perfect production asset. The final artwork should:

- simplify unnecessary gradients, gloss and shadows;
- use consistent ring/stroke thickness;
- keep strong negative space and a clear silhouette;
- remain recognizable at 32–64 px;
- keep enough spacing that the three lower symbols do not merge after resizing;
- keep the clock face simple enough to remain readable at small size;
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
- The selected control-center concept is used: master dial + Home + Light + Clock.
- It does not depend on text to be understood.
- It remains legible in light and dark Home Assistant themes and at 32–64 px.
- PNG assets are shipped locally under `custom_components/entity_controller/brand/`.
- Source/master artwork is retained for future resizing.

## Related

Entity-specific MDI icons are covered separately by entity/UI work. This task is only the integration/product brand mark.
