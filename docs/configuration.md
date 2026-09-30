# Entity Controller v10 Configuration

Entity Controller v10 uses one root Config Entry and one controller Config Subentry per controller rule.

The UI supports:
- creating the root Entity Controller entry;
- opening the first controller form immediately after setup;
- adding further controllers from the existing Helper settings;
- reconfiguring one controller without reloading unrelated controllers;
- selecting trigger and controlled entities with native entity selectors;
- preserving external override and interlock Helper/entity references.

Controller changes apply live. A trigger turns on the selected controlled
entities, retriggers reset the timer, and timer expiry turns them off. Enabled
and Stay Mode state is stored in the controller subentry.
