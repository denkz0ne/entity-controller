# Task 04 — Runtime diagnostics and rich entity attributes

## Goal
Expose enough low-churn runtime context on native EC entities that dashboards and automations can answer: what state is this controller in, why did it get there, which entity caused it, when did it happen, who is blocking/overriding it, and when will its timers expire?

RC.3 already keeps most of this data internally; this task should expose it coherently rather than creating many noisy helper entities.

## Current RC.3 state sensor attributes

- `last_transition`
- `transition_cause`
- `last_triggered_by`
- `last_triggered_at`
- `effective_delay`
- `profile`
- `expires_at`
- `block_expires_at`
- `blocked_by`
- `overridden_by`

## Runtime data that already exists but is not fully exposed

- `last_reconcile_reason`
- `blocked_at`
- `backoff_count`
- `timer_expired_pending_sensor`
- current `override_active`
- current `interlock_active`
- current `sensor_active`
- current `state_entities_on`
- current `enabled`
- current `stay_mode`

RC.3 also passes `source_entity_id` into `async_transition()` but does not retain it generically.

## Required diagnostics model

Add an explicit generic source field for the latest meaningful state change, e.g. `last_transition_source` / `last_state_change_source`.

Recommended state-sensor attributes:

```yaml
state: blocked
last_transition_at: 2026-10-01T10:30:00+02:00
last_transition_cause: manual_control
last_transition_source: light.obyvacka
last_reconcile_reason: null
last_triggered_by: binary_sensor.obyvacka_motion
last_triggered_at: 2026-10-01T10:29:12+02:00
blocked_by: light.obyvacka
blocked_at: 2026-10-01T10:30:00+02:00
block_reason: manual_control
block_expires_at: null
overridden_by: null
active_overrides: []
active_interlocks: []
profile: day
effective_delay: 180
backoff_count: 0
expires_at: null
timer_expired_pending_sensor: false
```

Names may be adjusted for consistency, but keep them stable once released.

## Blocked binary sensor

Keep it as a convenient boolean, but make its attributes specifically explain blocking:

- `block_reason`
- `blocked_by`
- `blocked_at`
- `block_expires_at`
- `active_interlocks`

Do not simply mirror an unrelated previous transition cause.

## Reconcile versus transition

A state can change because of reconcile without a normal FSM transition. Diagnostics must distinguish this:

- transition: store cause + source + timestamp;
- reconcile: store reconcile reason and, where possible, active source entities that explain the resolved state.

Do not fabricate a transition event just to populate attributes.

## Active source lists

Where cheap to calculate, expose the concrete entities currently responsible for external conditions:

- active override entities;
- active interlock entities;
- active trigger entities if useful.

This is especially important for multiple assigned Helpers.

## Recorder/churn rules

- Do not add a per-second countdown.
- Keep absolute timestamps such as `expires_at`.
- Do not update state attributes every second.
- Avoid copying the entire controller configuration into state attributes.
- Put large/static config in diagnostics output, not entity state.

## Separate diagnostic entities

Do not create a new entity for every runtime field by default.

A separate sensor is justified only if the value has independent historical/automation value and would otherwise cause high churn or awkward attribute access. If such entities are added, mark them diagnostic and disabled by default.

## Diagnostics download

Expand `diagnostics.py` with the same useful runtime fields, controller config summary, and any controller error. Preserve redaction behavior.

## Acceptance criteria

- Every state transition can expose a cause, timestamp, and source when one exists.
- Interlock/override reconcile states show the active responsible external entities.
- `blocked_by` is semantically correct rather than stale/empty for known block sources.
- State sensor attributes remain low-churn.
- No one-second countdown updates.
- Diagnostics export contains the useful runtime context.
- Tests cover transition source retention and reconcile-driven diagnostics.

## Relevant source

- `controller.py`
- `manager.py`
- `sensor.py`
- `binary_sensor.py`
- `diagnostics.py`
- `docs/entities.md`
- `docs/behavior.md`
