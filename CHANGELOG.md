# Change Log

All notable changes to Entity Controller v10 are documented here.

<a name="10.5.0"></a>
## 10.5.0 (2026-10-05)

### Sidebar editor

* separate the bordered controller overview from settings on the Home Assistant page background
* arrange inputs and control/timer behavior into two clearly labelled white groups
* pack time profiles below their related settings without leaving gaps between columns
* move helper explanations into keyboard/touch accessible question-mark popovers
* adapt to the actual panel width and provide larger mobile controls
* collapse priority/blocking rules until needed
* use one settings toolbar for mode selection, save status, Save, and Close
* align fields and simplify section headings, entity controls, and mobile layout
* preserve explicit saving, manual timer entry, and drafts during live updates

<a name="10.4.2"></a>
## 10.4.2 (2026-10-05)

### Fixes

* use the valid night profile enable field when saving settings
* preserve solar schedule sources and exact fixed times during unrelated edits
* clear the previous solar offset when a slider selects a fixed clock time
* keep advanced state fields compatible with the Home Assistant form schema
* stop saving on invalid JSON instead of silently retaining an older object
* preserve newer drafts and update the current controller after an asynchronous save
* keep editor buttons attached during live updates so the first click works
* refresh schedule controls after changing their enable switch or time source
* display duration mappings as slider/manual inputs and retain the night timer value

### Validation

* validate real browser save payloads against the Home Assistant controller schema in both editor modes

<a name="10.4.1"></a>
## 10.4.1 (2026-10-05)

### Fixes

* convert disabled optional durations to selector mappings so saving other settings succeeds

<a name="10.4.0"></a>
## 10.4.0 (2026-10-05)

### Features

* replace automatic editor saves with explicit Save and Close actions
* add manual seconds input synchronized with duration sliders

### Fixes

* preserve unsaved drafts after closing settings and while panel data refreshes
* keep unsaved values visible after a failed save and show the backend error
* place transparent setting groups on a shared compact editor background
* avoid treating schedule offset buttons as form values during save

<a name="10.3.0"></a>
## 10.3.0 (2026-10-05)

### Features

* add a searchable visual MDI icon picker and solar-aware interactive schedule ranges
* compact and regroup the inline editor with responsive layouts and 15-minute schedule offsets

### Fixes

* return the confirmed normalized configuration after save and avoid unnecessary panel reloads
* preserve editor, picker, search and open sections during Home Assistant runtime refreshes
* prevent older save responses from overwriting newer edits and restore the last confirmed form on errors
* resolve sunrise and sunset schedule positions using Home Assistant local sun data

<a name="10.2.0"></a>
## 10.2.0 (2026-10-05)

### Features

* redesign the inline configuration editor as compact Home Assistant themed cards with basic and full settings modes
* add searchable entity selection chips, visual time windows, duration controls, and live decision diagnostics

### Fixes

* clarify monitored entities and expose the existing manual-control blocking switch
* version the panel asset URL with the integration release

<a name="10.1.0"></a>
## 10.1.0 (2026-10-05)

### Features

* add a configuration panel for editing controller settings in Home Assistant

### Fixes

* fix the rolling 24-hour controller timeline and Recorder history loading

<a name="10.0.1"></a>
## 10.0.1 (2026-10-05)

### Fixes

* persist controller history on a rolling 24-hour timeline, with the current time at the right edge
* load full Recorder history responses and normalize returned records

<a name="10.0.0"></a>
## 10.0.0 (2026-10-04)

### Features

* deliver v10 as a native Home Assistant integration with independent controllers, native entities, migration support, and a responsive sidebar panel

### Fixes

* correct controller entity naming and config-flow behavior
* improve panel scrolling and duration pickers

### Compatibility

* requires Home Assistant 2026.9.0 or newer
* migration from v9.7.6 uses config entries; Helpers and legacy YAML are left in place for manual validation and cleanup
