# Entity Controller

Entity Controller v10 is a Home Assistant helper integration for reusable "when this happens, keep that active for a while" automations. The v10 line is being rebuilt around Config Entries, Config Subentries, native controller entities, hot reconfiguration, diagnostics, and controlled migration from legacy v9 YAML.

Current prerelease: `10.0.0-beta.2`

## Status

The `v10-modernization` branch is active prerelease work. It targets Home Assistant `2026.9.0` and newer. Do not treat beta builds as a finished production migration until the release candidate smoke gate is complete.

## Documentation

- [Configuration](docs/configuration.md)
- [Actions](docs/actions.md)
- [Behavior](docs/behavior.md)
- [Migration from v9 YAML](docs/migration-v9-to-v10.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Development notes](docs/development.md)

## Migration model

Legacy YAML is imported into v10 controller subentry data, but Entity Controller does not delete Helpers or rewrite `ec.yaml`. External Helpers stay ordinary Home Assistant entities and can be selected by one or more controller rules.

## Development

The maintained v10 CI path is `.github/workflows/v10-modernization.yml`. It runs repository metadata checks, Ruff, and the v10 pytest suite.
