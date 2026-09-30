# Migrating Entity Controller v9 YAML to v10

`10.0.0-beta.1` includes the controlled migration-test importer for legacy v9 YAML plus guide-only Repair issue builders.

The importer converts each legacy controller into one v10 controller subentry data payload. It preserves configured external Helper/entity references such as `input_boolean.navsteva_block` and `input_boolean.izba_block`; Entity Controller does not create, rename, duplicate, or delete those Helpers.

The migration report includes:
- imported controller subentries;
- skipped controller ids when an existing subentry already exists;
- unknown-field warnings;
- legacy `entity_controller.<object_id>` to new state sensor mapping;
- cleanup guidance telling the user to remove legacy YAML manually after validation.

This alpha is for migration testing only. Keep backups of existing YAML and validate imported controllers before removing the old include.

Repairs created from the migration report are advisory. They can explain cleanup guidance, unknown legacy fields, and preserved Helper references, but Entity Controller must not delete Helpers or rewrite/remove `ec.yaml` automatically.
