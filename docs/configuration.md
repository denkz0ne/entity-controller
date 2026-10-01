# Entity Controller v10 Configuration

Entity Controller v10 uses one root Config Entry and one controller Config Subentry per controller rule.

The UI supports:
- creating the root Entity Controller entry;
- opening the first controller form immediately after setup;
- showing Entity Controller on the Integrations page as one hub;
- showing every controller below it as a device with its native entities;
- adding further controllers from the Entity Controller integration;
- reconfiguring one controller without reloading unrelated controllers;
- selecting trigger and controlled entities with native entity selectors;
- preserving external override and interlock Helper/entity references;
- allowed operating windows using fixed times, sunrise, or sunset with offsets;
- a separate night profile with its own delay and turn-on/turn-off service data;
- timer backoff and optional automatic block timeout;
- configurable actions for each controller state transition;
- custom active/inactive state mappings and ignored state attributes.

Controller changes apply live. A trigger turns on the selected controlled
entities, retriggers reset the timer, and timer expiry turns them off. Enabled
and Stay Mode state is stored in the controller subentry. The allowed window
prevents activation outside its bounds. The night window changes the active
profile without creating another controller. All controller fields can be
edited later from the controller device in the Entity Controller integration.
