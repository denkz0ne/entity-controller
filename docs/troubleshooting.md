# Svetlo v tme v10 troubleshooting

## Controller starts disabled after restart

If a configured entity cannot be read during startup or reconcile, only that controller is disabled. Other controllers continue to load. Once the entity becomes readable again, reconcile that controller and confirm the state returns to the expected value.

## Active timer after restart

Svetlo v tme restores only valid controller-owned runtime state. An active timer may be restored with its future expiry timestamp, but restore must not replay ON/OFF transition actions. If the old expiry is already in the past, the timer should be rebuilt from live state instead of replaying stale behavior.

## Enabled and Stay Mode

Enabled and Stay Mode are native Svetlo v tme state. They can be restored by Svetlo v tme. External Helpers selected as overrides, interlocks, or rule inputs remain ordinary Home Assistant entities and keep their own state through their own integrations.

## Diagnostics

Diagnostics include root entry metadata, controller state, Enabled, Stay Mode, active timer expiry, last trigger, last reconcile reason, and controller-scoped errors. Sensitive keys such as tokens, secrets, and passwords are redacted.

## Migration Repairs

Migration Repairs are guide-only. They may tell you which legacy YAML include to review, which fields could not be migrated, and which external Helpers were preserved as references. They must not delete Helpers, rename Helpers, or rewrite/remove legacy YAML for you.
