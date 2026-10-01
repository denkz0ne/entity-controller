# Task 01 — Single-root integration UX and native Add Controller flow

## Goal
Make Entity Controller present itself as one permanent integration instance with controller subentries beneath it. The user should add controllers, not additional “hubs”.

## Current RC.3 state

- `manifest.json` declares `integration_type: hub`.
- `single_config_entry` is not set.
- `config_flow.py` manually aborts creation of a second root entry.
- Root Options already creates controller subentries.
- Current HA UI therefore still exposes an unnecessary **Add hub / +** affordance.

## Work

1. Add and test `single_config_entry: true` in the manifest.
2. Re-evaluate `integration_type` against the real EC product model. `helper` is semantically closer than `hub`; verify current Home Assistant behavior before changing it.
3. Keep exactly one root Config Entry.
4. Keep every EC controller as a `controller` Config Subentry and its own virtual device.
5. Make the normal growth action inside the integration **Add controller** using native config-subentry APIs.
6. Reduce root-level settings to only what is meaningful. If renaming the root entry adds no value, remove that unnecessary UI path.
7. Do not patch Home Assistant frontend just to remove/relabel a stock button.

## Acceptance criteria

- HA does not allow creating a second root Entity Controller entry.
- Adding another EC rule creates a new controller subentry/device.
- Existing controller subentries load unchanged.
- No runtime FSM behavior changes.
- The integration page is as compact as stock HA allows.
- If HA cannot replace a particular stock control with “Add controller”, document the limitation rather than introducing custom frontend code.
- Config-flow tests cover root creation, single-instance protection, add controller, reconfigure controller, and delete controller.

## Relevant source

- `custom_components/entity_controller/manifest.json`
- `custom_components/entity_controller/config_flow.py`
- `custom_components/entity_controller/__init__.py`

## Documentation

Update `README.md` and `docs/configuration.md` if the visible integration setup path changes.
