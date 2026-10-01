# Native sidebar panel

Entity Controller adds a **Entity Controller** item to the Home Assistant
sidebar while at least one controller config entry is loaded. It lists
controllers dynamically, shows their trigger and controlled entities, and
provides an enable switch backed by each controller's native Entity Controller
switch entity. Clicking an entity chip opens Home Assistant's more-info dialog.

Each controller row includes a 24-hour timeline from Home Assistant recorder
history for its native state sensor. Timeline colors represent active (green),
constrained (blue), blocked (red), and inactive (gray) states. If recorder
history is unavailable, the panel reports that history could not be loaded; it
does not synthesize missing history.

The panel uses the configured controller and entity registry IDs, so controller
names and entity IDs remain dynamic and user-renamed entities continue to work.
