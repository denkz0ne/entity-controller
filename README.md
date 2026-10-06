# Entity Controller

![Entity Controller integration icon](custom_components/entity_controller/brand/icon.png)

Entity Controller v10 is a Home Assistant device integration for reusable "when this happens, keep that active for a while" automations. Each controller is one Home Assistant config entry and one device, so the integration page lists controllers directly.

Current stable release: `10.6.0`

The setup flow immediately opens the first controller form. Entity Controller
appears once on the Integrations page; each configured controller appears below
it as a device with native State, Enabled, Stay Mode, Blocked, and Activate
entities. Controllers directly control the selected Home Assistant entities.
The controller form includes allowed operating windows, sunrise/sunset offsets,
day and night delays/service data, timer backoff, manual-control blocking,
override/interlock inputs, transition behavior, and custom state mappings. The
sidebar configuration panel adds a compact inline editor with searchable entity
chips, visual schedule controls, and separate basic and full settings modes.

Entity Controller uses Home Assistant's stock device integration UI. The top
right `+` adds a controller; each controller's settings edit that controller.
No frontend patch is used.

## Status

The v10 stable line targets Home Assistant `2026.9.0` and newer. Review the migration guide before upgrading from v9; legacy YAML and Helpers are preserved for manual validation and cleanup.

## Documentation

- [Configuration](docs/configuration.md)
- [Actions](docs/actions.md)
- [Behavior](docs/behavior.md)
- [Migration from v9 YAML](docs/migration-v9-to-v10.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Development notes](docs/development.md)
- [Release checklist](docs/release-checklist.md)

## Migration model

The migration guide covers legacy YAML and v10 config-entry data. Entity Controller does not delete Helpers or rewrite `ec.yaml`. External Helpers stay ordinary Home Assistant entities and can be selected by one or more controller rules.

## Development

The maintained v10 CI path is `.github/workflows/v10-modernization.yml`. It runs repository metadata checks, Ruff, and the v10 pytest suite.

