# Native Entity Controller panel implementation plan

**Specification:** GitHub issue #12 and its approved screenshot attachment (the screenshot supersedes the repository concept SVG).

**Goal:** Add a native Home Assistant sidebar panel that dynamically presents every configured Entity Controller, its controls and entity chips, and recorded state history for the previous 24 hours.

**Approach:** Register a custom built-in panel and static frontend assets while at least one integration entry is loaded. Expose controller runtime/configuration data through a read-only websocket command, resolve native entity IDs from the entity registry, and render Home Assistant-native controls and recorder history in a responsive custom element. Keep business state in existing runtime and entity platforms.

## Tasks

1. **Controller data API (TDD)**
   - Add tests for a dynamic controller payload, resolved entity IDs, state diagnostics, and empty/unavailable entity cases.
   - Implement payload serialization and an authenticated websocket command.
2. **Panel lifecycle (TDD)**
   - Test setup/unload registration behavior, including multiple entries.
   - Register static assets and one sidebar panel while the integration is loaded; remove the panel when the final entry unloads.
3. **Frontend panel**
   - Build an HA custom panel that renders dynamic controller rows, native enable controls, input/output chips, runtime details, and a 24-hour recorder timeline with the approved colors and shared legend.
   - Subscribe to controller/state entity changes and refresh the panel data; use Home Assistant theme variables and responsive layout.
4. **Docs and release notes**
   - Document the panel and its recorder-history requirement; add the feature to the changelog.
5. **Verification**
   - Run focused tests, full test suite, Ruff, and inspect frontend syntax/build behavior.
