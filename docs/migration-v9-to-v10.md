# Migrating Entity Controller v9 YAML to v10

On the first startup after installing v10, Entity Controller imports the legacy YAML controllers that Home Assistant has already loaded under the `entity_controller` key. For example, `configuration.yaml` can include the existing file like this:

```yaml
entity_controller: !include entitycontroller.yaml
```

The integration does not open `/config/entitycontroller.yaml` itself or search the filesystem. If Home Assistant is not loading the old file under `entity_controller`, the automatic import cannot see it.

Each valid legacy controller becomes its own flat Home Assistant config entry and device. The migration preserves the legacy controller ID for its controller and entity identity, converts supported trigger/control/state/override/interlock entities, day and night service data, sensor/state/override state mappings, ignored state attributes, timing/blocking/backoff/night/transition settings, and keeps existing Helpers as references. Legacy global state strings are applied to supported state mappings; v10 has no separate control-state mapping, so that limitation is logged. The import does not create, rename, duplicate, or delete Helpers.

When a controller uses both singular and plural v9 entity keys (`sensor` and `sensors`, `entity` and `entities`, or the override/interlock equivalents), the importer combines them in order and removes duplicate entity IDs, matching the v9 configuration behavior.

Unknown fields are written to the Home Assistant log as warnings. A malformed controller is skipped without blocking valid sibling controllers. A failed import flow is logged and can be retried on a later startup; already-created controller entries are detected by stable IDs, so they are not duplicated or overwritten.

Keep the old YAML include and its source file untouched as a rollback reference. Validate each migrated controller against the EC01–EC10 HAOS checks first. After all checks pass, remove the `entity_controller` include manually; the integration never edits or deletes the source YAML.

The migration report also retains the legacy `entity_controller.<object_id>` to new state-sensor mapping and cleanup guidance. External Helper references such as `input_boolean.navsteva_block` and `input_boolean.izba_block` remain ordinary Home Assistant entities. The integration does not rewrite or remove `ec.yaml` automatically.
