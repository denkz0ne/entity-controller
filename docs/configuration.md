# Entity Controller v10 configuration reference

> Source baseline: `v10-modernization`, `10.0.0-rc.3` (`86893e7`). This page documents the behavior implemented by the current source. Planned RC polish is tracked separately and must not be assumed to exist yet.

Entity Controller uses one root Home Assistant config entry. Every automation rule is stored as a `controller` config subentry and is represented by its own virtual device.

## Quick start

For a normal motion-light rule you only need four values:

1. **Name** — e.g. `Living room`.
2. **Trigger entities** — e.g. a motion or door binary sensor.
3. **Control entities** — lights, switches, groups, or other entities that support `turn_on` / `turn_off`.
4. **Day delay** — how long an `active_timer` activation lasts before expiry.

The default transition behavior is intentionally simple: entering an active state turns the control entities on, and entering `idle` turns them off. All other state changes do nothing unless you change their transition behavior.

## The four concepts that are easiest to confuse

### Manual-control blocking

`blocking_enabled` protects a user's manual change from being immediately undone by EC.

The controller always watches its `control_entities` and additionally watches any `state_entities`. EC-originated changes are ignored using Home Assistant context tracking. A significant external/manual state change can move an active controller to `blocked`.

This is an internal behavior of the controller; it is not a Helper.

### Interlock

An **interlock** is an external Home Assistant entity used as a gate. It can be an `input_boolean`, switch, binary sensor, or other entity. The Helper is not owned by EC and may be shared by any number of controllers.

In RC.3 an interlock is considered active when its state is anything except `off`, `unavailable`, `unknown`, or an empty string. When an assigned interlock changes, the controller reconciles its state; an active interlock resolves to `blocked`.

Use an interlock for conditions such as "guest mode blocks these motion-light controllers".

### Override

An **override** is also an external entity, but it represents a different controller state: `overridden`, not `blocked`. Override entities use the configurable `override_on_states` mapping. If any assigned override is active, reconcile selects `overridden`.

Use override when the automation is deliberately being superseded by another mode or rule rather than merely inhibited.

### Constraint

A **constraint** is the controller's allowed operating time window. Inside the configured window the controller may work normally. Outside it, the controller becomes `constrained` and triggers cannot activate it.

Constraint has the highest priority during reconcile. The window can use a fixed local time, sunrise, or sunset, with a positive or negative offset. Cross-midnight windows are supported.

## Reconcile priority

Whenever EC rebuilds logical state without replaying transition actions (startup, restore, reconfigure, enable, interlock change), the current RC.3 priority is:

1. Disabled -> `disabled`
2. Outside allowed constraint window -> `constrained`
3. Any active override -> `overridden`
4. Any active interlock -> `blocked`
5. Any active trigger -> `active_timer` or `active_stay_on`
6. A monitored state/control entity is on while manual blocking is enabled -> `blocked`
7. Otherwise -> `idle`

This order matters when more than one condition is true at the same time.

---

## Identity

| Field | Default | What it does |
| --- | --- | --- |
| `name` | required | Human-readable controller/device name. |
| `icon` | none | Optional controller icon. In RC.3 the same controller icon is also returned by all native entities. |

## Triggers

| Field | Default | What it does |
| --- | --- | --- |
| `trigger_entities` | required | One or more entities that activate the controller when their state matches `trigger_on_states`. |
| `sensor_type` | `event` | Chooses event or duration semantics. |
| `sensor_resets_timer` | `false` | Duration mode only: when the last duration trigger is released, reset the active timer and start the full delay again. |

### Event trigger

An event trigger starts the timer. EC does not require the trigger to return to OFF before the timer can expire. Re-triggering while `active_timer` resets the timer.

### Duration trigger

A duration trigger represents an ongoing condition. If the timer expires while a duration trigger is still active, EC keeps the controller active and records a pending expiry. With `sensor_resets_timer = false`, it returns to idle when the trigger is finally released. With `sensor_resets_timer = true`, release starts a fresh full timer instead.

Multiple trigger entities use OR semantics: the controller is considered sensor-active while at least one trigger matches an active state.

## Controlled and monitored entities

| Field | Default | What it does |
| --- | --- | --- |
| `control_entities` | required | Entities on which transition behavior executes `turn_on` / `turn_off`. They are also monitored for manual state changes. |
| `state_entities` | empty | Additional entities whose state is used for manual-control blocking/reconciliation. These are additional to the control entities, not a replacement for them. |

A controller can therefore control one entity while monitoring another representation of its real state.

## Timer and backoff

| Field | Default | What it does |
| --- | --- | --- |
| `delay_seconds` | `180` | Base daytime timer duration. |
| `backoff_enabled` | `false` | Enables adaptive timer extension after repeated resets while active. |
| `backoff_factor` | `1.1` | Multiplier applied once per active timer reset. |
| `backoff_max_seconds` | `300` | Maximum effective delay after backoff. |

With backoff enabled, the effective delay is `base_delay * factor^reset_count`, capped at `backoff_max_seconds`. The count resets when the controller leaves its active state.

Changing the delay while the controller is active does not restart the controller. RC.3 recalculates the expiry from the original `last_triggered_at`; if the new expiry is already in the past, expiry logic runs immediately.

## Manual-control blocking

| Field | Default | What it does |
| --- | --- | --- |
| `blocking_enabled` | `true` | Enables protection against external/manual changes to monitored control/state entities. |
| `block_timeout_seconds` | none | Optional automatic timeout for the internal blocked state. `0` in the UI is normalized to no timeout. |

Important current rules:

- If a trigger arrives while a monitored controlled/state entity is already ON and blocking is enabled, the controller enters `blocked` instead of claiming control.
- While `active_timer`, an external monitored ON change enters `blocked` when blocking is enabled.
- While `active_timer`, an external monitored OFF change returns to `idle`.
- If blocking is disabled, an external monitored ON change while `active_timer` resets the timer instead.
- While `blocked` or `active_stay_on`, a monitored OFF change returns to `idle`.
- EC's own service calls are ignored through context tracking and should not be mistaken for manual intervention.

## Override and interlock inputs

| Field | Default | What it does |
| --- | --- | --- |
| `override_entities` | empty | External entities that put this controller into `overridden` when their state matches `override_on_states`. |
| `interlock_entities` | empty | External gate entities. Any state other than `off`/`unavailable`/`unknown`/empty is treated as active and reconcile selects `blocked`. |

External Helpers are never owned, renamed, persisted, or deleted by Entity Controller. An automation can control a Helper and that same Helper can be selected by several EC controllers.

## Allowed operating window (constraint)

| Field | Default | What it does |
| --- | --- | --- |
| `constraint_enabled` | `false` | Enables the allowed operating window. |
| `constraint_start_source` / `constraint_end_source` | `fixed` | `fixed`, `sunrise`, or `sunset`. |
| `constraint_start_time` / `constraint_end_time` | `06:00` / `23:00` in the current form | Used when source is `fixed`. |
| `constraint_*_offset_seconds` | `0` | Positive/negative offset from the selected fixed/sun anchor. |

The window means **allowed time**, not blocked time. Outside it, state is `constrained`.

RC.3 reevaluates configured time windows every minute and also refreshes them before processing a trigger event.

## Night profile

Night profile is separate from constraint. It does not block the controller; it changes how an active controller behaves during its own time window.

| Field | Default | What it does |
| --- | --- | --- |
| `night_mode_enabled` | `false` | Enables night profile evaluation. |
| `night_start_source` / `night_end_source` | `sunset` / `sunrise` | Schedule anchors. |
| `night_*_time` | `20:00` / `06:00` | Fixed-time fallback/input when source is fixed. |
| `night_*_offset_seconds` | `0` | Offset from the schedule anchor. |
| `night_delay_seconds` | `0` in UI -> none | Night timer duration. When unset/zero, day delay is used. |
| `night_service_data_on` | empty | Replacement service data for night `turn_on` when non-empty. |
| `night_service_data_off` | empty | Replacement service data for night `turn_off` when non-empty. |

The state sensor reports `profile: day` or `profile: night`.

## Initial runtime state

| Field | Default | What it does |
| --- | --- | --- |
| `enabled_default` | `true` | Initial Enabled state when the controller is first created. |
| `stay_mode_default` | `false` | Initial Stay Mode state when first created. |

After creation, current Enabled and Stay Mode values are controller-owned runtime state and are persisted back into the subentry as `enabled` and `stay_mode`. Reconfiguration preserves those live values.

## Stay Mode

Stay Mode is exposed as a native switch. When enabled while `active_timer`, the controller changes to `active_stay_on` and no main expiry timer is used. Disabling it while `active_stay_on` changes back to `active_timer` and starts a timer.

Both active substates map to the generic `active` transition behavior. With the current defaults, entering either active state runs the ON behavior.

## Turn-on / turn-off service data

`service_data_on` and `service_data_off` are dictionaries merged into the `turn_on` / `turn_off` service call for every controlled domain. This can carry supported parameters such as brightness, transition, color, etc.

During an active night profile, non-empty `night_service_data_on/off` replaces the corresponding day service data.

## Transition behavior

Each state family can define an action on enter and exit:

- `on_enter_idle`, `on_exit_idle`
- `on_enter_active`, `on_exit_active`
- `on_enter_overridden`, `on_exit_overridden`
- `on_enter_constrained`, `on_exit_constrained`
- `on_enter_blocked`, `on_exit_blocked`

The current UI supports:

- `on` -> call `turn_on` for all control entities
- `off` -> call `turn_off` for all control entities
- `ignore` -> no service call

Defaults are:

- enter idle -> `off`
- enter active -> `on`
- everything else -> `ignore`

`TransitionBehavior.CUSTOM` exists in the Python enum but is not currently exposed/implemented as a usable custom action in RC.3.

## Advanced state mapping

| Field | Current use |
| --- | --- |
| `trigger_on_states` | Used to decide whether trigger entities are active. |
| `trigger_off_states` | Stored by RC.3, but the runtime currently treats "not in ON states" as inactive; this explicit OFF list is not consulted. |
| `state_on_states` | Used to decide whether monitored control/state entities are ON. |
| `state_off_states` | Stored, but not currently consulted by the runtime. |
| `override_on_states` | Used to decide whether override entities are active. |
| `override_off_states` | Stored, but not currently consulted by the runtime. |
| `state_attributes_ignore` | Used to ignore state events where the base state is unchanged and all changed attributes belong to this list. |

The unused explicit OFF mappings are a known RC.3 polish item; documentation intentionally describes actual source behavior rather than implying they already work.

## Hot reconfiguration

Editing a controller updates only that controller runtime. Trigger/state/override/interlock listeners are removed and rebuilt for the changed configuration. Unrelated controllers are not reloaded.

Startup, restore, reconfiguration, interlock changes, and enabling use **reconcile**, which computes the logical state from current Home Assistant reality without replaying enter/exit ON/OFF behaviors just because configuration was reconstructed.

## Current RC.3 limitations relevant to UI polish

- Root integration is still declared as `integration_type: hub` and does not yet use manifest `single_config_entry`; the frontend can therefore show an unnecessary add-hub affordance even though the config flow manually rejects a second instance.
- Native entity IDs/names are not yet guaranteed to use the planned `ec_<controller>_<function>` naming convention.
- Entity names are generated in Python and are not yet localized through entity translation keys.
- Interlock reconcile does not currently record which interlock caused the block.
- Transition `source_entity_id` is accepted by the FSM but not retained as a general transition-source diagnostic.
- The explicit OFF-state mappings described above are not wired into current runtime decisions.

These are tracked as RC polish work, not documented as finished functionality.
