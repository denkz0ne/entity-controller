# Task 08 — Integration branding and icon assets

## Goal
Replace the generic/missing integration artwork with a distinctive Entity Controller icon that remains readable in Home Assistant at small sizes and works in both light and dark themes.

## Visual direction
Entity Controller is not a physical hub. The icon should communicate **rule-driven control / state flow** rather than Wi-Fi, cloud, or generic home automation.

Preferred concept:

- one compact central controller/state node;
- 2–3 small input nodes feeding it;
- one controlled output path;
- a subtle loop/flow shape suggesting state-machine logic;
- geometric, modern, flat/vector-like;
- recognizable at 32–64 px;
- no tiny details;
- no full product name inside the mark.

A restrained `EC` monogram may be used only if it stays legible at integration-icon size; symbol-first is preferred.

## Asset requirements

Prepare at minimum:

- square source asset, high resolution;
- transparent-background PNG;
- SVG/vector source if the selected distribution/branding path supports it;
- safe padding so Home Assistant's circular/rounded presentation does not crop the mark;
- variant that works on light and dark backgrounds if one universal mark is not sufficient.

Do not copy Home Assistant's logo or another integration's brand mark.

## Repository / Home Assistant integration

Determine the correct branding mechanism for a custom HACS integration in the current release path. If the icon needs to live in Home Assistant's brands repository rather than this repository, document the exact follow-up and keep a source copy/reference here.

Update README screenshots/branding only after the final mark is selected.

## Acceptance criteria

- Entity Controller no longer presents as “icon not available” once the supported branding path is installed.
- Icon is clearly recognizable at integration-list size.
- It does not depend on text to be understood.
- It remains legible in light and dark Home Assistant themes.
- Source/master artwork is retained for future resizing.

## Related

Entity-specific MDI icons are covered by Task 03; this task is only the integration/product brand mark.
