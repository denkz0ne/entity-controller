# Entity Controller

Entity Controller v10 is a Home Assistant hub integration for reusable "when this happens, keep that active for a while" automations. The v10 line is being rebuilt around Config Entries, Config Subentries, native controller entities, hot reconfiguration, diagnostics, and controlled migration from legacy v9 YAML.

Current prerelease: `10.0.0-rc.5`

The setup flow immediately opens the first controller form. Entity Controller
appears once on the Integrations page; each configured controller appears below
it as a device with native State, Enabled, Stay Mode, Blocked, and Activate
entities. Controllers directly control the selected Home Assistant entities.
The controller form includes allowed operating windows, sunrise/sunset offsets,
day and night delays/service data, timer backoff, manual-control blocking,
override/interlock inputs, transition behavior, and custom state mappings.

Entity Controller intentionally uses Home Assistant's stock integration UI:
one permanent root entry groups multiple controller devices, and controllers
are added from its settings. The `hub` type is retained for this model; no
custom frontend patch is used merely to rename Home Assistant controls.

## Status

The `v10-modernization` branch is active prerelease work. It targets Home Assistant `2026.9.0` and newer. Do not treat beta builds as a finished production migration until the release candidate smoke gate is complete.

## Documentation

- [Configuration](docs/configuration.md)
- [Actions](docs/actions.md)
- [Behavior](docs/behavior.md)
- [Migration from v9 YAML](docs/migration-v9-to-v10.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Development notes](docs/development.md)
- [Release checklist](docs/release-checklist.md)

## Migration model

Legacy YAML is imported into v10 controller subentry data, but Entity Controller does not delete Helpers or rewrite `ec.yaml`. External Helpers stay ordinary Home Assistant entities and can be selected by one or more controller rules.

## Development

The maintained v10 CI path is `.github/workflows/v10-modernization.yml`. It runs repository metadata checks, Ruff, and the v10 pytest suite.
