# Migrating Entity Controller v9 YAML to v10

`10.0.0-alpha.6` introduces the first controlled migration-test importer for legacy v9 YAML.

The importer converts each legacy controller into one v10 controller subentry data payload. It preserves configured external Helper/entity references such as `input_boolean.navsteva_block` and `input_boolean.izba_block`; Entity Controller does not create, rename, duplicate, or delete those Helpers.

The migration report includes:
- imported controller subentries;
- skipped controller ids when an existing subentry already exists;
- unknown-field warnings;
- legacy `entity_controller.<object_id>` to new state sensor mapping;
- cleanup guidance telling the user to remove legacy YAML manually after validation.

This alpha is for migration testing only. Keep backups of existing YAML and validate imported controllers before removing the old include.
