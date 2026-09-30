# Entity Controller v10 Native Entities

Each controller subentry owns one Home Assistant device and a small set of native entities.

Primary entities:
- State sensor: exposes the exact FSM state: `idle`, `active_timer`, `active_stay_on`, `blocked`, `overridden`, `constrained`, or `disabled`.
- Enabled switch: disables or enables EC decision-making for the controller. Turning it off does not turn controlled loads off.
- Stay Mode switch: toggles runtime stay mode.
- Blocked binary sensor: exposes whether the controller is blocked and includes reason/source attributes.
- Activate button: performs the same activation semantics as the compatibility action.

Diagnostics such as last-trigger timestamps are disabled by default where exposed. Entity Controller does not create a persistent native manual-block switch; user-created Helpers remain ordinary external rule inputs selected per controller.
