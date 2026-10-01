# Flat controller config entries implementation plan

**Goal:** Show each Entity Controller controller as one Home Assistant device entry, with no user-facing Hub parent or controller subentry nesting, while keeping controller identity and entity history through v10 prerelease migration.

**Architecture:** Use one `device` config entry per controller. Each entry owns one runtime and its native controller device. Keep the old subentry-backed root entry only as migration input. Preserve old registry identity by carrying the old controller identifier and entity unique-ID prefix into each new entry. New controllers use stable generated identifiers. Root `+` creates another config entry; that entry's configure action edits only its controller.

## Steps

1. **Prove entry migration primitives.** Add focused tests for converting old root/subentry data into per-controller entry payloads, preserving old controller ID and entity unique-ID prefix, and making repeated migration idempotent. Verify the installed Home Assistant API signatures used for adding entries and updating/removing the old entry.
2. **Adapt runtime ownership.** Let `EntityControllerManager` load and persist one controller from a per-controller entry while retaining its subentry path for migration compatibility. Keep the controller runtime key unchanged.
3. **Switch flows and manifest.** Make the user config flow create one controller entry directly, let the per-entry options flow reconfigure that controller, remove add-via-root-options and subentry creation, and change the manifest to the matching `device` type with multiple entries allowed.
4. **Migrate prerelease entries.** Reuse the old root entry for the first controller. Create deterministic entries for the remaining controllers, preserve entity unique IDs and device identifiers, and ensure retries do not duplicate entries. Clear legacy subentry ownership and update the reused root only after every secondary target entry is successfully set up.
5. **Verify behavior and document it.** Add regression tests for top-level add, per-controller edit, migration identity, unique-ID preservation and no duplicate entries/devices; run the complete maintained CI command; update migration/UI docs and changelog.

## Risks and constraints

- The local test runtime is Home Assistant 2025.1.4, while the integration targets 2026.9; subentry migration and integration-page rendering must still be smoke-tested on 2026.9.
- Home Assistant must re-associate existing registry entries by the preserved `unique_id` when the owning config entry changes. Do not remove the legacy root until all new entries are loaded and adoption is verified.
- The original `entitycontroller.yaml` on the user's HAOS is a separate one-time migration input, not a new recurring integration feature. This workspace cannot access the user's LAN; the migration can only be run after that file is supplied or access is available from an authorized network.
