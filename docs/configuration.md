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
