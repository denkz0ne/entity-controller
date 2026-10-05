# Editor save review — 10.4.2

Reviewed the rendered inputs, draft updates, save collection, asynchronous responses,
panel refresh, controller form conversion, and backend schema validation. An
independent read-only reviewer examined the original code and the corrective diff.
The installed 10.4.1 panel on HAOS was compared through SMB and matched the repository
file byte for byte.

| Priority | Defect and trigger | Correction |
| --- | --- | --- |
| P1 | Every save collected the generated `night_enabled` checkbox, which the HA schema rejects. | Emit `night_mode_enabled`. |
| P1 | Save collection converted untouched solar schedule sliders to fixed times. | Collect schedule times only from actual input/change events. |
| P1 | Full editor emitted arrays for advanced state fields whose schema requires text. | Keep comma-separated text until backend normalization. |
| P1 | Invalid JSON was caught during collection and the old object was submitted as if successful. | Abort collection before sending a request. |
| P1 | A refresh replaced the controller object while a save was awaiting a response; newer edits could also be overwritten. | Preserve draft revisions across refresh and update the current controller only for the submitted revision. |
| P1 | A pending focusout render detached the save button between pointerdown and pointerup. | Preserve the attached editor while updating the surrounding row. |
| P2 | Untouched fixed schedule times lost their seconds or were snapped to 15-minute slider values. | Preserve the stored time unless the user moves the slider. |
| P2 | Changing a schedule enable switch/source did not reveal the matching controls. | Rerender after the deliberate change. |
| P2 | Native duration mappings appeared as JSON; the night timer value and label arguments were reversed. | Render duration controls before generic objects and pass the correct arguments. |
| P2 | Failed JSON validation replaced the user's invalid text with the previous valid object. | Preserve draft controls on failure. |

Regression coverage exercises real browser clicks, malformed JSON, refresh during a
pending save, newer edits, night controls, and both editor modes with night enabled
and disabled. The save contract tests pass the actual emitted WebSocket form through
`CONTROLLER_SCHEMA`, normalize it, and compare every setting against the baseline
after changing only the controller name. This catches unexpected fields, rejected
types, and unintended schedule/timer changes together.

GitHub Actions installs Home Assistant in the panel browser job so schema validation
is mandatory. Python 3.12 resolves the supported HA test dependency; these checks do
not substitute for a save on the user's HA 2026.9.4 instance. No HA configuration was
modified during review or testing.
