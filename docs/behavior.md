# Entity Controller v10 behavior

Entity Controller v10 keeps the explicit finite-state-machine behavior from v9 while moving runtime ownership into one Config Entry and one controller subentry per controller.

## Runtime states

Controllers expose these states:

- `idle`
- `active_timer`
- `active_stay_on`
- `blocked`
- `overridden`
- `constrained`
- `disabled`

Startup, restore, migration, and reconfiguration use reconcile. Reconcile rebuilds logical state from stored controller-owned flags and current Home Assistant entity state without replaying ON/OFF transition actions.

## Timers

Event sensors start an active timer. Re-triggering while active resets the timer and applies configured backoff when enabled. Duration sensors can keep the controller active until the sensor turns off after the timer has already expired.

## Blocking and overrides

Manual control or interlock entities can move a controller into `blocked`. Override Helpers move only the assigned controller into `overridden`; Entity Controller does not own or globally register those Helpers.

## Helper composition

Any Home Assistant automation may drive a normal Helper such as `input_boolean.navsteva_block`. That Helper can then be selected in one or more Entity Controller rules as an override, interlock, or other rule input.
