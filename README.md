# Svetlo v tme

![Svetlo v tme integration icon](custom_components/entity_controller/brand/icon.png)

**Svetlo v tme** is a Home Assistant integration for reusable, configurable
controllers that activate devices from triggers, preserve manual control, and
apply separate daytime and nighttime behavior. Each controller is represented
as a Home Assistant device with native state and control entities.

Current stable release: `10.7.0`

The integration includes a compact sidebar panel for monitoring controllers
and editing their settings. It offers searchable entity selection, graphical
schedule controls, basic and advanced settings, and explicit **Save / Close**
actions. Day and night profiles can set supported light brightness and color,
fan percentage, transitions, and other service parameters without requiring
users to write service data by hand.

The integration's internal Home Assistant domain remains `entity_controller`
for compatibility. Existing entity IDs, service IDs, configuration entries,
and automations do not need to be renamed because of the product rebrand.

The integration uses Home Assistant's native device and config-entry UI. The
top-right `+` adds a controller; each controller's settings edit that
controller.

## Status

The stable v10 line targets Home Assistant `2026.9.0` and newer. Review the
migration guide before upgrading from v9; legacy YAML and Helpers are preserved
for manual validation and cleanup.

## Documentation

- [Configuration](docs/configuration.md)
- [Actions](docs/actions.md)
- [Behavior](docs/behavior.md)
- [Migration from v9 YAML](docs/migration-v9-to-v10.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Development notes](docs/development.md)
- [Release checklist](docs/release-checklist.md)

## Migration model

The migration guide covers legacy YAML and v10 config-entry data. Svetlo v tme
does not delete Helpers or rewrite `ec.yaml`. External Helpers stay ordinary
Home Assistant entities and can be selected by one or more controller rules.

## Development

The maintained CI workflow runs repository metadata checks, Ruff, the pytest
suite, and browser tests for the sidebar panel.
