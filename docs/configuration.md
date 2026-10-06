# Entity Controller v10 Configuration

Entity Controller v10 uses one Home Assistant config entry and one device per controller.

Add another controller with the top-right `+` on the Entity Controller
integration page. Open a controller's settings to edit only that controller.

The UI supports:
- creating a controller directly from the integration page;
- showing every controller directly as one device with its native entities;
- adding controllers as separate config entries of the same integration;
- reconfiguring one controller without changing other controllers;
- selecting trigger and controlled entities with native entity selectors;
- preserving external override and interlock Helper/entity references;
- allowed operating windows using fixed times, sunrise, or sunset with offsets;
- a separate night profile with its own delay and turn-on/turn-off service data;
- timer backoff and optional automatic block timeout;
- configurable actions for each controller state transition;
- custom active/inactive state mappings and ignored state attributes.

The first visible section contains name, icon, activation triggers, optional
presence/hold sensors, controlled entities, and activity time. The remaining settings are grouped
into collapsed sections for timer behavior, manual intervention, override and
interlock, allowed time, night profile, transition actions, and advanced state
mapping. The initial Enabled and Stay Mode defaults are shown only while a
controller is created; live values are managed by their native switches.

Controller changes apply live. A trigger turns on the selected controlled
entities, retriggers reset the timer, and timer expiry turns them off. Enabled
and Stay Mode state is stored in the controller config entry. The allowed window
prevents activation outside its bounds. The night window changes the active
profile without creating another controller. All controller fields can be
edited later from the controller device in the Entity Controller integration.

## Presence / hold sensors

Activation triggers (for example PIR motion) start room activity. Optional
presence sensors (for example mmWave occupancy) only hold an already active
room; they do not switch an idle room on. While any configured presence sensor
matches its active mapping, the inactivity timer cannot turn the room off.
After the last presence sensor matches its inactive mapping, the normal
configured vacancy delay begins again. A zero delay ends activity immediately.

Presence is independent of the trigger event/duration mode. Leave the presence
list empty to retain the existing PIR-only setup. Existing triggers are never
silently reassigned. Advanced settings include separate presence ON/OFF
mappings; neutral states such as unknown/unavailable do not count as explicit
OFF events. Presence does not bypass Disabled, allowed time, Override,
Interlock or manual-control protection.

The State sensor and diagnostics expose `presence_active`,
`active_presence_entities`, `presence_hold_started_at` and
`last_presence_changed_at` so the hold source can be inspected.

## Manual control

Manual-control settings separately protect external OFF and external ON or
significant adjustments, both enabled by default. External means outside this
EC instance; Home Assistant cannot always identify a physical person. Protected
changes release ownership until the trigger/presence room session clears.
Disable only the corresponding protection when that external change should
remain subject to EC's ordinary activity policy.

## Custom lifecycle actions

Advanced `lifecycle_actions` maps an enter/exit hook (for example
`on_enter_active`) to a native Home Assistant action sequence. A scene can be
applied with a sequence item such as `action: scene.turn_on` and its scene
target. Choose Custom for that hook; its sequence runs through the shared
lifecycle executor. Invalid sequences must be rejected before configuration
is saved. Startup and reconfigure reconciliation do not replay actions.

Normal shutdown now belongs to `on_exit_active`, whose default is Off;
`on_enter_idle` defaults to Ignore. The old default pair (idle Off, active exit
Ignore) converts deterministically to this equivalent room shutdown policy.
Other explicit advanced hook combinations are retained. The conversion is
idempotent and is applied to the editor's canonical form before an ordinary
name-only save, so renaming does not select a new exit policy.

## Sidebar editor

The sidebar panel shows a bordered controller overview above the settings.
The settings use the Home Assistant page background with separate cards for:

- name and icon;
- inputs (triggers and monitored entities);
- controlled entities, timer, and activation/end actions;
- allowed operating time and the night profile.

Priority and blocking rules are collapsed until opened. Full settings also
expose advanced options. On narrow screens the cards stack in reading order with larger touch controls.
Question-mark buttons open helper explanations by click, tap, or keyboard;
Escape or a click outside closes the explanation. Layout follows the available
panel width, including the space taken by the Home Assistant sidebar.
Changes remain a draft until **Save** is pressed. **Close** hides the editor
while retaining the draft for the current panel session. Timer values can be
entered manually as well as adjusted with the slider.
