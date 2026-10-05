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

The first visible section contains only name, icon, trigger entities,
controlled entities, and activity time. The remaining settings are grouped
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
