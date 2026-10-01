# Task 05 — Interlock / blocked semantics and source tracking

## Goal
Make interlock blocking robust and distinguish it from manual-control blocking and service-forced blocking. A held interlock must remain authoritative until it clears.

## Current RC.3 behavior

- Interlock entities are arbitrary external HA entities.
- Any state other than `off`, `unavailable`, `unknown`, or empty is treated as active.
- Interlock changes request a reconcile.
- Reconcile maps active interlock -> `blocked`.
- Because this is reconcile-driven, RC.3 does not populate `blocked_by` with the responsible interlock.
- `block_timeout_seconds` uses the same `blocked` state machinery and therefore needs explicit semantics when an interlock stays active.

## Required semantic split

Introduce an explicit block reason/source model. Suggested reasons:

- `manual_control`
- `interlock`
- `service`
- `preexisting_state` / `state_already_on` if needed

Do not infer the reason later from an unrelated `last_transition_cause`.

## Interlock rules

1. If any assigned interlock is active, the controller resolves to `blocked`.
2. Track all currently active interlock entity IDs, not only the last event source.
3. A block timeout must **not** defeat a still-active interlock.
4. When the last interlock clears, evaluate the current controller reality again instead of blindly returning to idle.
5. If another higher-priority condition is active (constraint, override), resolve according to the documented priority.
6. External Helpers remain untouched. EC never toggles/deletes them.

## Block timeout rules

Clarify timeout ownership:

- Timeout should apply to blocks that EC is allowed to release automatically, such as manual-control/service blocks.
- Interlock blocks are condition-based and should remain blocked while the condition exists.

If the implementation keeps one blocked state, the timer callback must re-check active interlocks before leaving it.

## Clear Block action

Define and test behavior while an interlock is active:

- pressing Clear Block must not permanently bypass a held interlock;
- either reject/no-op with diagnostics, or immediately reconcile back to blocked.

Prefer reconcile so the action cannot leave runtime flags inconsistent.

## Enable Block action

Service-forced block should have a clear source/reason and predictable timeout behavior.

## Acceptance criteria

- Held interlock remains blocked past `block_timeout_seconds`.
- Clearing the last interlock immediately reevaluates override/trigger/state conditions.
- Multiple interlocks are tracked correctly.
- `blocked_by` / active interlock diagnostics identify the responsible entity/entities.
- Clear Block cannot bypass an active interlock.
- Manual block timeout still works where configured.
- Regression tests cover all cases above.

## Relevant source

- `manager.py`
- `controller.py`
- `actions.py`
- `binary_sensor.py`
- `sensor.py`
- `docs/behavior.md`
