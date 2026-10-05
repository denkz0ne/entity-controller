# Change Log

All notable changes to Entity Controller v10 are documented here.

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
