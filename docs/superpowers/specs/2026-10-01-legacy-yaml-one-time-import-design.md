# One-time import of legacy YAML configuration

## Goal

When an installation upgrades to the flat per-controller config-entry model, import controllers from the existing `entity_controller` YAML configuration once. The import is migration plumbing, not a new user-facing import feature. The source YAML remains untouched so it can serve as a rollback reference until the user validates the migrated setup.

## Scope and constraints

- Home Assistant supplies the integration's parsed YAML mapping to `async_setup`; the integration must not open an arbitrary filesystem path such as `/config/entitycontroller.yaml` itself.
- Convert each legacy controller using the existing `migrate_legacy_yaml` conversion logic.
- Create one config entry per controller through the integration's `SOURCE_IMPORT` config flow.
- Keep the source YAML file unchanged. Log concise completion and warning details, including unsupported fields and malformed controller records.
- Do not add an import button, options flow, persistent import switch, or repeated import behavior.
- Existing v10-to-v11 config-entry migration remains independent and unchanged.

## Startup and idempotency

`async_setup(hass, config)` checks for the integration domain's legacy YAML mapping. If absent or empty, setup returns successfully without starting an import. If present, it converts the mapping and submits each valid controller to `hass.config_entries.flow.async_init` with `context={"source": SOURCE_IMPORT}`.

The import flow assigns each entry a deterministic unique ID derived from its legacy controller ID, names the entry from converted data, and stores the flat controller data expected by the current entry setup path. Home Assistant's domain-wide unique-ID check prevents duplicates on restart or when an existing imported entry is already present. A duplicate is treated as already imported, not as an error. The import flow must not replace an existing entry's user-edited values.

The migration helper's existing `existing_subentry_ids` terminology is updated or wrapped so the runtime import can skip already-present controller unique IDs without changing the existing v10 subentry migration behavior.

## Error handling

- Invalid top-level YAML is rejected by Home Assistant's YAML loader before integration setup; if a malformed mapping nevertheless reaches the helper, log a migration error and return setup success so unrelated Home Assistant startup is not blocked.
- A malformed individual controller is skipped; valid controllers continue importing.
- Unsupported legacy fields produce warnings. They are not silently treated as migrated settings.
- A flow failure for one controller is logged with its controller ID; remaining controllers are still attempted.
- If no valid controllers remain, do not create a placeholder config entry.

## Data compatibility

Reuse the current converter for entity lists, delays, blocking, backoff, night mode, and transition behaviors. Preserve legacy controller IDs as stable imported IDs where Home Assistant permits it, so entity identity behavior follows the current migration mapping. Existing external helper references remain references; this migration does not create helper entities. After successful validation, cleanup guidance tells the user to remove the old YAML include manually.

## Tests

- Startup with no legacy YAML does not start a flow.
- One valid legacy controller creates one `SOURCE_IMPORT` config entry with expected flat data and stable unique ID.
- Multiple valid controllers create separate entries.
- Re-running startup/import with those IDs creates no duplicates and does not overwrite edited existing entries.
- A malformed controller and a per-controller flow failure do not block imports for other controllers.
- Unsupported fields emit migration warnings.
- Existing config-entry version migration tests continue to pass.

## Operational limitation

The importer first uses YAML that Home Assistant has already loaded for the integration. If no configuration was loaded, it may read only the conventional HAOS path `/config/entitycontroller.yaml`; it does not scan other paths or write to the source. Differently named files must be included under the integration domain. Stable controller IDs make setup retries idempotent. The old file should remain in place until the EC01–EC10 HAOS checks pass.
