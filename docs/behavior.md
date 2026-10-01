# Entity Controller v10 behavior

> Source baseline: `v10-modernization`, `10.0.0-rc.8`. This is a source-derived runtime reference, not a description of planned behavior.

Entity Controller v10 implements an explicit async finite-state machine. The controller has seven user-visible runtime states and two different ways to change state:

- **transition** — an actual runtime event; enter/exit behaviors may execute `turn_on`/`turn_off` actions;
- **reconcile** — rebuild logical state from current Home Assistant reality without replaying transition side effects.

Reconcile is used for startup, restore, reconfiguration, enabling, and external interlock changes. This distinction prevents a Home Assistant restart or settings edit from unexpectedly switching loads.

## States

| State | Meaning | Typical cause |
| --- | --- | --- |
| `idle` | Controller is ready but not currently active. | Timer expired, sensor/manual state released, no active conditions. |
| `active_timer` | Controller is active and a main expiry timer is running. | Trigger event or service activation. |
| `active_stay_on` | Controller is active without the normal main expiry timer. | Stay Mode is enabled while active or the controller activates while Stay Mode is already enabled. |
| `blocked` | EC is deliberately not taking normal automatic control. | Manual-control protection, active interlock, or block action. |
| `overridden` | An external override condition supersedes normal trigger behavior. | An assigned override entity is active. |
| `constrained` | Current time lies outside the configured allowed window. | Constraint evaluation. |
| `disabled` | Controller decision-making is disabled. | Native Enabled switch is OFF. |

## Reconcile priority

When several conditions are true simultaneously, RC.3 resolves them in this exact order:

1. disabled
2. constrained
3. overridden
4. blocked by interlock
5. active because a trigger is active
6. blocked because a monitored state/control entity is already on while blocking is enabled
7. idle

This means a constraint currently outranks override, and override outranks interlock.

## Default enter/exit actions

Active timer and active stay-on share the logical behavior name `active`.

Defaults:

| Transition point | Default behavior |
| --- | --- |
| enter `idle` | `off` |
| exit `idle` | `ignore` |
| enter active | `on` |
| exit active | `ignore` |
| enter/exit `blocked` | `ignore` |
| enter/exit `overridden` | `ignore` |
| enter/exit `constrained` | `ignore` |

`on` and `off` call the matching service separately for each controlled entity domain. Service data comes from the day profile or, while night is active, the night profile when that profile provides non-empty service data.

## Trigger behavior

### Trigger ON from idle

The runtime stores `last_triggered_by`, `last_triggered_at`, increments its trigger generation, and marks the sensor condition active.

If a monitored control/state entity is already ON and manual blocking is enabled, EC enters `blocked` instead of turning the load on again. Otherwise it enters the active target:

- Stay Mode OFF -> `active_timer`
- Stay Mode ON -> `active_stay_on`

### Re-trigger while active timer is running

The FSM stays in `active_timer` and resets the timer. If backoff is enabled, every reset increments the backoff count and extends the effective delay up to the configured maximum.

### Event sensor expiry

When the main timer expires, an event controller returns to `idle`.

### Duration sensor expiry

If the timer expires while a duration sensor is still active, the controller remains active and sets `timer_expired_pending_sensor`. It leaves active state only after the duration condition releases, unless `sensor_resets_timer` requests a fresh timer on release.

## Timer and backoff calculation

The base timer is the day delay, except while the night profile is active and supplies a night delay.

With backoff disabled:

`effective_delay = base_delay`

With backoff enabled after N timer resets:

`effective_delay = min(base_delay * backoff_factor^N, backoff_max_seconds)`

Leaving active state resets the backoff count.

Timers use generation guards, so callbacks cancelled by reconfiguration or later scheduling cannot apply stale expiry logic.

## Manual-control protection

The manager listens to both `control_entities` and extra `state_entities`.

Entity Controller-generated service calls use tracked Home Assistant contexts; state events with an EC-owned context are ignored as manual changes.

For a genuine external/manual state change:

- `active_timer` + monitored entity OFF -> `idle`;
- `active_timer` + monitored entity ON + blocking enabled -> `blocked` and `blocked_by` is set to that entity;
- `active_timer` + monitored entity ON + blocking disabled -> reset timer;
- `blocked` or `active_stay_on` + monitored entity OFF -> `idle`.

`state_attributes_ignore` suppresses events only when the base state is unchanged and every changed attribute belongs to the ignore list.

## Block timeout

When the controller enters `blocked` through manual-control protection or the block service, it records `blocked_at` and optionally schedules `block_expires_at`. This timeout does not apply while an interlock is active.

On block timeout:

- if a monitored state entity is still on and the controller uses event semantics (or a duration trigger is still active), it activates;
- otherwise it returns to `idle`.

A persistent external interlock holds the controller in `blocked` until every active interlock clears. A timeout cannot release it. When the last interlock clears, reconciliation evaluates the current trigger, constraint, override, and monitored-state conditions. Constraints and overrides retain their higher priority than interlocks.

## Override

When any assigned override entity enters an active override state, the controller can transition from `idle`, either active state, or `blocked` to `overridden`. `overridden_by` records the event source for normal transition-driven entry.

When the last override clears:

- if no monitored state entity is on -> `idle`;
- if state is on and the controller uses event semantics, or a duration trigger is still active -> active target;
- otherwise -> `idle`.

Override entities use OR semantics.

During startup/reconcile the controller can resolve to `overridden` without a transition event. The runtime records the currently active override entity in `overridden_by` and exposes all active override entities in diagnostics attributes.

## Custom state mappings

Trigger, monitored state/control, and override entities each have configured ON and OFF state lists. A state in the ON list is active; a state in the OFF list is inactive. A value in neither list is neutral: a live event does not change that entity's logical condition. On startup and reconcile, only values in the configured ON list count as active. Multiple entities are combined with OR semantics, so one mapped OFF event cannot clear another entity that is still mapped ON. `unknown`, `unavailable`, and transitional values are neutral unless explicitly listed.

## Interlock

An interlock is a normal external HA entity. RC.3 considers it active if its state is not `off`, `unavailable`, `unknown`, or empty.

Interlock state changes request a full reconcile rather than a transition. An active interlock resolves the controller to `blocked`; the state and Blocked sensor expose the active interlock list, and `blocked_by` names the first active configured interlock. Reconcile does not run normal `on_enter_blocked` transition behavior. Clear Block and block timeout cannot release a held interlock. When the final interlock clears, reconciliation evaluates current controller conditions.

This keeps diagnostics accurate without fabricating an FSM transition or changing reconcile side effects.

## Constraint

Constraint defines an **allowed** operating window. Outside the window the manager sets `constrained = true` and reconciles according to normal priority. When the window opens, the manager reconciles current inputs instead of blindly returning to `idle`. If an ON-mapped trigger is already active, it enters the active target through a normal transition so the configured activation behavior runs. Active overrides, interlocks, and disabled state retain their priority.

Schedule points support:

- fixed local time;
- sunrise;
- sunset;
- positive or negative offsets.

Cross-midnight windows are supported. Schedule state is refreshed every minute and before trigger processing.

When the allowed window reopens while the controller is currently constrained, RC.3 transitions directly to `idle`. A future polish pass should verify whether full reconcile is preferable so an already-active override/interlock/trigger is honored immediately.

## Night profile

Night profile is not a controller state. It sets `night_active` and changes:

- base timer delay, when a night delay is configured;
- `turn_on` service data, when non-empty night data exists;
- `turn_off` service data, when non-empty night data exists.

The state sensor exposes the effective profile as `day` or `night`.

## Stay Mode

Stay Mode is controller-owned persistent runtime state.

- Enabling Stay Mode while `active_timer` transitions to `active_stay_on`.
- Disabling it while `active_stay_on` transitions back to `active_timer`, which starts a fresh main timer.
- Activating while Stay Mode is already enabled enters `active_stay_on` directly.

Moving between the two active substates does not replay generic active enter/exit behavior. The timer is cancelled when entering Stay Mode and starts fresh when leaving it; native state entities are updated immediately.

## Enabled

The Enabled native switch controls whether EC makes decisions for that controller.

Turning it OFF does **not** call `turn_off` on controlled loads. It sets the controller-owned flag and reconciles to `disabled`. Turning it ON reconciles current sensors, constraints, overrides, interlocks, and monitored states.

The value is persisted into the controller config entry.

## Activate

Activate enables the controller, persists Enabled when it changes, and requests activation only when current rules allow it. It preserves active constraints, overrides, interlocks, and an existing blocked state. If a monitored entity is already ON while manual blocking is enabled, Activate resolves to `blocked`. Calling Activate on an already active controller leaves its active substate and timer unchanged.

## Hot reconfiguration

Updating one controller applies a config diff to its existing runtime. Listeners are rebuilt and timer/block deadlines are recalculated without rebuilding unrelated controllers. Newly active constraints, overrides, and interlocks are reconciled even when the controller has an active timer; this does not replay load actions. A timer that expires while applying a shorter delay stays expired unless a higher-priority condition must be resolved.

For an active main timer, the new expiry is based on `last_triggered_at + new_effective_delay`; shortening the delay past the current time invokes expiry logic immediately.

## Diagnostics currently retained by runtime

The runtime already tracks:

- `last_triggered_by`
- `last_triggered_at`
- `last_transition_at`
- `last_transition_cause`
- `last_transition_source`
- `last_reconcile_reason`
- `blocked_by`
- `blocked_at`
- `block_reason`
- `block_expires_at`
- `overridden_by`
- `active_overrides`, `active_interlocks`, `active_triggers`, and `active_state_entities`
- current `enabled`, `stay_mode`, `override_active`, `interlock_active`, `sensor_active`, and `state_entities_on`
- `backoff_count`
- `effective_delay_seconds`
- `expires_at`
- `timer_expired_pending_sensor`
- active day/night profile

The State sensor exposes this low-churn runtime context, while config-entry diagnostics also include a redacted configuration summary and controller errors. No per-second countdown is written to entity attributes.

## Known behavior gaps after RC.7

These are source-level gaps, not documentation TODOs:

- `TransitionBehavior.CUSTOM` exists in the model but current UI/executor only implement ON, OFF, and IGNORE.
