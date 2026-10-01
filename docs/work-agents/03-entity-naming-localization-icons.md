# Task 03 — Native entity IDs, localized names, and per-function icons

## Goal
Give every controller-owned native entity a predictable EC-prefixed entity ID, localized visible name, and function-specific icon while preserving stable unique IDs and user customizations.

## Required entity-id pattern

At first registration, suggest:

```text
<domain>.ec_<controller_slug>_<function>
```

Example controller: `Obývačka`

```text
sensor.ec_obyvacka_state
switch.ec_obyvacka_enabled
switch.ec_obyvacka_stay_mode
binary_sensor.ec_obyvacka_blocked
button.ec_obyvacka_activate
```

Slugging must use Home Assistant-compatible entity-id normalization.

## Unique-ID rule

Keep unique IDs independent from the controller's display name:

```text
<root_entry_id>_<controller_subentry_id>_<function_key>
```

Renaming a controller must not change `unique_id`.

## Visible names

Move away from hard-coded Python natural-language names. Use the current Home Assistant entity naming model:

- `has_entity_name = True`
- entity `translation_key`
- controller device supplies the controller name
- entity translation supplies only the function name

Target user-visible Slovak meaning:

| Key | SK | EN |
| --- | --- | --- |
| `state` | `EC Stav` | `EC State` |
| `enabled` | `EC Zapnutý` | `EC Enabled` |
| `stay_mode` | `EC Trvalý režim` | `EC Stay mode` |
| `blocked` | `EC Blokovaný` | `EC Blocked` |
| `activate` | `EC Aktivovať` | `EC Activate` |

For a device named `Obývačka`, Home Assistant should present the combined friendly name equivalent to `Obývačka - EC Stav`, etc. Do not hard-code `Obývačka` into entity translation strings.

Also localize enum state labels for the state sensor if supported by the target HA entity translation model:

- `idle` -> `Nečinný`
- `active_timer` -> `Aktívny – časovač`
- `active_stay_on` -> `Aktívny – trvalý režim`
- `blocked` -> `Blokovaný`
- `overridden` -> `Override` or a concise Slovak equivalent chosen consistently with the config UI
- `constrained` -> `Časovo obmedzený`
- `disabled` -> `Vypnutý`

Raw state values must remain stable English identifiers for automations.

## Function-specific icons

Do not reuse the controller icon for every native entity. Recommended defaults:

| Entity | Icon |
| --- | --- |
| State | `mdi:state-machine` |
| Enabled | `mdi:toggle-switch` |
| Stay Mode | `mdi:pin` |
| Blocked | `mdi:shield-lock` |
| Activate | `mdi:play-circle` |

If state-specific translated icons are supported cleanly, consider:

- idle -> `mdi:pause-circle-outline`
- active_timer -> `mdi:timer-play`
- active_stay_on -> `mdi:pin`
- blocked -> `mdi:shield-lock`
- overridden -> `mdi:gesture-tap-button`
- constrained -> `mdi:clock-lock-outline`
- disabled -> `mdi:power-off`

Verify every MDI icon exists in the target Home Assistant version before merging.

## Existing registry entries

Do not overwrite a user-customized entity ID.

Implement a safe migration only if it is possible to distinguish an integration-generated/default ID from a user-customized ID. If that cannot be proven reliably, leave existing IDs unchanged and apply the new convention only to newly registered entities. Document the behavior.

## Acceptance criteria

- New controller `Obývačka` produces the planned `ec_obyvacka_*` IDs.
- Renaming the controller keeps unique IDs stable.
- User-renamed entity IDs are preserved.
- Entity function names are localized through translation keys rather than hard-coded in Python.
- EN/SK entity translations are complete.
- Each native entity has its own meaningful default icon.
- Tests cover entity registration naming and rename stability.

## Relevant source

- `custom_components/entity_controller/entity.py`
- `sensor.py`
- `switch.py`
- `binary_sensor.py`
- `button.py`
- `strings.json`
- `translations/sk.json`
- `docs/entities.md`
