# Task 07 — FSM edge cases: constraints, Activate, and Stay Mode

## Goal
Fix state-machine edge cases that are currently logically inconsistent even though the common motion-light path works.

Keep these fixes focused and test-driven. Do not mix UI redesign into this task.

## A. Leaving a constraint window

### Current RC.3 behavior
When the allowed window opens again while the controller is `constrained`, manager code transitions directly to `idle`.

This can ignore current reality such as:

- active override;
- active interlock;
- active duration trigger;
- monitored state entity already ON.

### Required behavior
Re-evaluate the same precedence used by normal reconcile when a constraint changes.

Do not blindly drop to idle.

The implementation must explicitly decide whether a currently active trigger at the moment the allowed window opens should execute the normal activation behavior. The resulting state must not claim `active_*` while leaving controlled entities unintentionally OFF.

Add tests for at least:

- constraint ends + override active;
- constraint ends + interlock active;
- constraint ends + duration trigger active;
- constraint ends + no active conditions.

## B. Activate button/service from disabled or constrained state

### Current RC.3 behavior
`async_activate()` sets `runtime.enabled = True` and asks for a direct transition to the active target.

The FSM does not allow a direct transition from every state to active, so calling Activate from `disabled` or `constrained` can leave inconsistent state/flags.

### Required semantics
Define Activate as an explicit request to enable and activate **only if current controller rules allow it**.

Recommended behavior:

1. set Enabled true if needed;
2. evaluate constraint / override / interlock / current state;
3. if activation is allowed, enter active target and run normal active-enter behavior;
4. if blocked/constrained/overridden by a higher-priority rule, preserve that state rather than bypassing safety rules.

Do not use Activate as an undocumented “force everything” bypass.

Add tests from every FSM state.

## C. Stay Mode active-substate transitions

### Current RC.3 behavior
`active_timer` and `active_stay_on` both map to the generic transition behavior name `active`.

Switching between them can therefore execute `on_exit_active` and `on_enter_active` even though the controller never actually leaves logical active state. With defaults this can issue another ON service call; with customized behaviors it can be more surprising.

### Required behavior
Changing only active substate for Stay Mode should update timer ownership/state without replaying generic active enter/exit behaviors unless there is a deliberate documented reason to do so.

Tests:

- active_timer -> active_stay_on cancels timer and does not duplicate active-enter action;
- active_stay_on -> active_timer schedules the timer and does not replay full active transition behavior;
- state sensor still updates immediately.

## D. Reconfigure while active

Retain existing safety property:

- changing config must not turn controlled loads off merely because config is rebuilt;
- active timer deadline recalculation continues to use the updated effective delay;
- constraint/interlock changes caused by reconfigure resolve safely.

Add regression tests around the fixes above so later refactors do not reintroduce side effects.

## Acceptance criteria

- Constraint exit resolves current conditions correctly.
- Activate has deterministic behavior from every state and never leaves `enabled` inconsistent with FSM state.
- Stay Mode substate changes do not replay generic active ON/OFF behaviors.
- No startup/reconfigure light flicker regression.
- FSM transition table and docs are updated if allowed edges change.

## Relevant source

- `controller.py`
- `manager.py`
- `actions.py`
- state-machine tests
- `docs/behavior.md`
