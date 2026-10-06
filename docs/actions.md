# Svetlo v tme v10 actions

Svetlo v tme v10 keeps compatibility actions for common v9 service workflows while exposing native entities for day-to-day control.

## Available actions

- `entity_controller.activate`
- `entity_controller.clear_block`
- `entity_controller.enable_block`
- `entity_controller.enable_stay_mode`
- `entity_controller.disable_stay_mode`
- `entity_controller.set_night_mode`

Actions target one controller by its stable controller id. They operate on the assigned runtime only and do not rebuild or change other controller entries.

## Native controls

The native Enabled switch disables controller decisions without forcing controlled loads off. The native Stay Mode switch persists Svetlo v tme-owned stay state. External Helpers remain regular Home Assistant entities.

## Migration note

Existing v9 automations can be ported action-by-action, but v10 dashboards should prefer native controller entities where possible.
