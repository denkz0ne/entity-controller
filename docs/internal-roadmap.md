# Entity Controller v10 — internal roadmap / deferred ideas

Status: internal design notes. These items are **not implementation commitments** unless promoted to a dedicated GitHub issue.

This file records ideas deliberately deferred during the 2026-10-02 feature review so they are not lost and are not repeatedly re-proposed without context.

## Deferred / revisit later

### 1. Resume / re-arm policy after temporary blocking or constraints

Potential future feature: explicitly configure what happens when a temporary suppressing condition ends.

Possible policies:

- resume immediately according to current room reality;
- wait for a fresh activation trigger;
- require the room to become clear/empty before re-arming;
- resume only after a configured state transition.

Applies potentially after:

- interlock release;
- constraint window end;
- manual-control block release;
- controller re-enable.

Keep this deferred until #14 Presence/Hold and #15 Manual Takeover establish the final occupancy/session model. A generic resume-policy selector should not be added before those semantics are stable.

### 2. Minimum ON/OFF time and trigger debounce

Potential reliability controls:

- minimum ON time to prevent very short activations;
- optional minimum OFF time to prevent rapid OFF -> ON oscillation;
- trigger debounce to collapse duplicate/noisy state changes.

Do not implement yet. Only promote if real devices show flicker/chatter that current timer logic cannot handle cleanly.

### 3. Derived room occupancy entity

Potential entity:

`binary_sensor.ec_<controller>_occupied`

Meaning: EC currently considers the room/session occupied based on configured activation and future presence/hold sensors; this is **not** equivalent to "controlled light is on".

Possible reuse:

- heating;
- music;
- other automations;
- dashboard presence overview.

Do not add yet. Revisit after #14 proves the occupancy model is stable enough to expose publicly.

### 4. EC-only event journal

Keep a compact ring buffer of meaningful events generated/handled by Entity Controller itself.

This must **not** become a general Home Assistant event log.

Example entries:

- motion trigger received;
- EC entered ACTIVE;
- timer reset / expired;
- EC called light.turn_on / light.turn_off;
- manual takeover detected;
- interlock engaged/released;
- constraint entered/exited;
- restore action executed/skipped;
- service/action error.

Possible fields:

- timestamp;
- controller state before/after;
- reason/cause;
- source entity;
- action performed;
- result/error.

Use a bounded in-memory/persisted history with a sane cap, e.g. last 20–100 meaningful EC events, not every entity attribute update.

Potential surfaces:

- diagnostics download;
- controller troubleshooting detail;
- optional future sidepanel detail drawer.

Do not implement yet.

### 5. Controller Health / Problem diagnostics

Potential diagnostic health model for one controller.

Goal: answer whether the controller is operational, not merely what FSM state it is in.

Possible health inputs:

- trigger entity missing/unavailable;
- all configured trigger sensors unavailable;
- future presence/hold sensors unavailable;
- controlled entity missing/unavailable;
- invalid explicit ON/OFF mapping;
- failed service/action call;
- failed custom lifecycle action;
- restore failure;
- config/runtime reconcile error;
- unsupported domain capability selected;
- stale/missing referenced entity after rename/removal.

Suggested normalized result:

- `ok`;
- `warning`;
- `error`.

And a bounded list of problem codes, for example:

- `trigger_unavailable`;
- `control_entity_missing`;
- `action_failed`;
- `invalid_mapping`;
- `runtime_error`.

Potential implementation options later:

- default-disabled diagnostic binary/sensor entity;
- diagnostics-only field;
- health indicator in the EC sidepanel.

Avoid one diagnostic entity per problem. Prefer one controller health summary with structured attributes/details.

Do not implement yet; revisit after the runtime/action architecture (#14–#17) settles.

### 6. Multiple profiles beyond Day / Night

Potential future evolution of the current day/night profile model:

- Day;
- Evening;
- Night;
- Sleep;
- custom externally selected profile.

A profile could define:

- delay;
- output/light parameters;
- lifecycle action variants;
- possibly activation constraints.

Risk: this can easily turn EC into another general automation editor. Keep deferred until there is a concrete real-world need that cannot be expressed cleanly by current Day/Night + external helpers/interlocks.

### 7. Dry-run / Explain current decision

Potential troubleshooting tool that evaluates current controller inputs without executing side effects.

Examples:

- "If a trigger arrived now, result would be BLOCKED because input_boolean.navsteva_block is ON.";
- "Would activate ACTIVE_TIMER for 180 s using Night profile.";
- "Would not activate because controller is outside the allowed constraint window.";
- "Timer expiry would be held because presence sensor is still active.".

This should build on the existing side-effect-free reconcile architecture and the normalized diagnostic `decision_reason` tracked in issue #4.

Potential UI surfaces:

- small `Explain / Test decision` action in controller reconfigure flow;
- troubleshooting detail in the future sidepanel.

Do not implement yet.

## Explicitly not planned for now

These ideas were reviewed and intentionally rejected/deferred without a TODO implementation target unless real usage changes the requirement.

### Lux / ambient-light activation gate

Not planned. Current user setup does not use lux sensors.

### Clickable / detailed timeline inspection

Not needed now. The sidepanel timeline remains a visual 24 h state overview; no hover/click forensic timeline requirement at this stage.

### Snooze / temporary pause timer

Not planned. Temporary suppression should be handled externally through automations/helpers connected to EC interlocks.

### Extra permanent quick-action entities / menus

Not planned beyond the controls already required. Avoid entity/UI clutter.

### Activity-adaptive timeout

Not planned. Existing timeout/backoff behavior is sufficient for now.

### Area-assisted automatic setup

Not planned. Do not auto-discover room entities from HA Area at this stage.

## Promoted to dedicated issues

The following ideas from the same review are no longer TODOs and are tracked as implementation candidates:

- #14 — separate activation triggers from Presence/Hold sensors;
- #15 — richer manual control / takeover semantics including brightness/color/temp changes;
- #16 — lifecycle actions, scenes/custom actions and restore-previous-state policy;
- #17 — domain-aware configurator, filtered pickers and smart light controls;
- #4 follow-up — normalized diagnostic decision reason / occasional "why?" explanation.

## Design guardrails

Future ideas should preserve these principles:

1. Primary use case remains room automation: presence/activity -> automatic light control under conditions.
2. Do not hard-wire controllers together. Inter-controller orchestration should use normal HA entities/helpers/automations.
3. Prefer native EC runtime state/diagnostics over creating external helper clutter.
4. Preserve side-effect-free startup/reconfigure reconciliation.
5. Keep the normal configuration simple; advanced behavior belongs behind clear advanced sections.
6. Avoid turning EC into a general-purpose automation editor when Home Assistant already provides scripts/actions/automations for that role.
