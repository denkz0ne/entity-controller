# Task 06 — Explicit ON/OFF state mappings

## Goal
Make all configured ON and OFF state mappings actually participate in runtime decisions. RC.3 stores explicit OFF lists but largely treats “not ON” as OFF.

## Current RC.3 gap

Configured fields:

- `trigger_on_states`
- `trigger_off_states`
- `state_on_states`
- `state_off_states`
- `override_on_states`
- `override_off_states`

Manager/runtime currently consult the ON lists, but explicit OFF lists are not used for normal event classification.

That is unsafe for entities with neutral/transitional states. Example: a media player may move through `buffering` or `unknown`; that should not automatically mean OFF unless configured that way.

## Required event classification

For trigger/state/override event listeners, classify the new state as:

1. matches configured ON list -> active/ON handling;
2. matches configured OFF list -> inactive/OFF handling;
3. matches neither -> ignore as unmapped/neutral state.

Do not silently treat every non-ON value as OFF.

## Trigger entities

- ON match -> existing sensor-on semantics.
- OFF match -> existing sensor-off semantics.
- Neither -> leave runtime sensor condition unchanged.
- With multiple triggers, recompute whether another trigger is still explicitly ON.

## State/control entities

- ON match -> monitored state considered ON.
- OFF match -> monitored state considered OFF.
- Neither -> ignore the event for logical ON/OFF purposes.
- Preserve `state_attributes_ignore` behavior.

Be careful with multiple monitored entities: one explicit OFF event must not make `state_entities_on = false` when another monitored entity is explicitly ON.

## Override entities

- ON match -> active override.
- OFF match -> inactive override.
- Neither -> leave override condition unchanged / recompute from mapped states only.
- Multiple overrides use OR semantics.

## Startup/reconcile snapshot

Snapshot calculation must use the same explicit mapping rules. An entity in a neutral state must not be counted as active and must not be guessed OFF in a way that triggers an unwanted transition.

Define a consistent policy for unavailable/unknown entities. Prefer treating them as unmapped/neutral unless explicitly present in a configured mapping.

## Migration/default compatibility

Default mappings remain simple:

```text
ON: on
OFF: off
```

If v9 migration supplies richer mappings, preserve them.

## Acceptance criteria

- Every explicit OFF list is used by runtime code.
- Neutral/unmapped states do not trigger false OFF transitions.
- Multi-entity OR semantics remain correct.
- Startup/reconcile and live event listeners use the same mapping rules.
- Tests include media-player-like states (`playing`, `paused`, `idle`, neutral) and `unknown`/`unavailable` behavior.
- Documentation no longer lists OFF mappings as an RC gap after merge.

## Relevant source

- `manager.py`
- `controller.py`
- `model.py`
- `config_flow.py`
- migration tests
- `docs/configuration.md`
- `docs/behavior.md`
