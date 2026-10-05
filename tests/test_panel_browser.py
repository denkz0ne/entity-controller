"""Browser regressions for wheel/touch scrolling during Home Assistant updates."""

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

PANEL_JS = Path(
    "custom_components/entity_controller/www/entity-controller-panel.js"
)

MOUNT_PANEL = """
() => {
  const panel = document.createElement("entity-controller-panel");
  // Mock transport only: rendering, browser scrolling and gestures remain real.
  panel._start = async () => {};
  panel._watchStates = async () => {};
  panel.controllers = Array.from({length: 24}, (_, index) => ({
    id: "controller-" + index,
    name: "Controller " + index,
    icon: "mdi:lightbulb",
    state: "idle",
    enabled: true,
    enabled_entity_id: "switch.enabled_" + index,
    state_entity_id: "sensor.state_" + index,
    triggers: ["binary_sensor.motion"],
    outputs: ["light.room"],
    overrides: [],
    interlocks: [],
  }));
  window.serviceCalls = [];
  window.moreInfoCalls = [];
  panel.addEventListener("hass-more-info", (event) => {
    window.moreInfoCalls.push(event.detail.entityId);
  });
  document.querySelector("#mount").appendChild(panel);
  panel.hass = {
    connection: {},
    states: {
      "binary_sensor.motion": {
        state: "off", attributes: {friendly_name: "Motion"}
      },
      "light.room": {state: "off", attributes: {friendly_name: "Room"}}
    },
    callService: async (...args) => { window.serviceCalls.push(args); },
  };
  window.panel = panel;
  window.scroller = panel.shadowRoot.querySelector(".wrap");
}
"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch()
        yield instance
        instance.close()


def mount_panel(page):
    page.set_content(
        '<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1">'
        '<style>html,body{margin:0;height:100%;overflow:hidden}'
        '#mount{height:calc(100dvh - 64px)}</style><div id="mount"></div>'
    )
    page.add_script_tag(path=str(PANEL_JS))
    page.evaluate(MOUNT_PANEL)


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1200, "height": 800})
    result = context.new_page()
    mount_panel(result)
    yield result
    context.close()


@pytest.fixture
def mobile_page(browser):
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        is_mobile=True,
        has_touch=True,
        device_scale_factor=2,
    )
    result = context.new_page()
    mount_panel(result)
    yield result
    context.close()


def test_wheel_over_chips_and_live_updates_preserve_scroll(page):
    page.locator(".chip").first.hover()
    page.evaluate(
        "() => { window.updates = setInterval(() => {"
        "panel.hass = {...panel.hass}; }, 40); }"
    )
    try:
        page.mouse.wheel(0, 500)
        page.wait_for_function("scroller.scrollTop > 200")
        before = page.evaluate("scroller.scrollTop")
        page.evaluate(
            "() => {"
            "panel.controllers[0].name = 'Renamed controller';"
            "panel.hass = {...panel.hass};"
            "panel._render();"
            "}"
        )
        assert page.evaluate(
            "scroller === panel.shadowRoot.querySelector('.wrap')"
        )
        assert abs(page.evaluate("scroller.scrollTop") - before) < 2
        page.mouse.wheel(0, -500)
        page.wait_for_function("scroller.scrollTop < 10")
    finally:
        page.evaluate("clearInterval(window.updates)")


def test_wheel_over_heading_reaches_last_controller_and_footer(page):
    page.locator(".heading").hover()
    page.mouse.wheel(0, 10000)
    page.wait_for_function(
        "scroller.scrollTop >= scroller.scrollHeight - scroller.clientHeight - 2"
    )
    assert page.locator(".row").last.is_visible()
    assert page.locator(".legend").is_visible()
    last = page.locator(".row").last.bounding_box()
    bounds = page.locator(".wrap").bounding_box()
    assert last["y"] + last["height"] <= bounds["y"] + bounds["height"]
    assert page.evaluate("document.scrollingElement.scrollTop") == 0


@pytest.mark.parametrize("target", [".chip", ".toggle", ".timeline"])
def test_touch_scroll_from_controls_survives_updates(mobile_page, target):
    page = mobile_page
    control = page.locator(".row").nth(2).locator(target).first
    control.evaluate("(element) => { window.gestureTarget = element; }")
    box = control.bounding_box()
    x = box["x"] + box["width"] / 2
    y = box["y"] + box["height"] / 2
    session = page.context.new_cdp_session(page)
    session.send(
        "Input.dispatchTouchEvent",
        {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]},
    )
    page.wait_for_function("panel._touching")
    page.evaluate(
        "() => {"
        "panel.controllers[2].name = 'Updated during swipe';"
        "panel.hass = {...panel.hass};"
        "}"
    )
    assert page.evaluate("gestureTarget.isConnected")
    for step in range(1, 9):
        session.send(
            "Input.dispatchTouchEvent",
            {
                "type": "touchMove",
                "touchPoints": [{"x": x, "y": y - step * 25}],
            },
        )
        page.evaluate("panel.hass = {...panel.hass}")
        page.wait_for_timeout(30)
    assert page.evaluate("gestureTarget.isConnected")
    session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    page.wait_for_function("scroller.scrollTop > 80")
    page.wait_for_function("!panel._touching && !panel._renderPending")
    assert page.evaluate(
        "scroller === panel.shadowRoot.querySelector('.wrap')"
    )
    assert page.locator(".controller-name").nth(2).inner_text() == (
        "Updated during swipe"
    )
    assert page.evaluate("window.serviceCalls") == []
    assert page.evaluate("window.moreInfoCalls") == []


def test_taps_still_toggle_entities_and_open_more_info(mobile_page):
    page = mobile_page
    page.locator(".chip[data-chip-toggle]").first.tap()
    page.wait_for_function("window.serviceCalls.length === 1")
    assert page.evaluate("window.serviceCalls[0]") == [
        "light", "turn_on", {"entity_id": "light.room"}
    ]
    page.locator(".toggle").first.tap()
    page.wait_for_function("window.serviceCalls.length === 2")
    assert page.evaluate("window.serviceCalls[1]") == [
        "switch", "turn_off", {"entity_id": "switch.enabled_0"}
    ]
    page.locator(".chip").first.tap()
    page.wait_for_function("window.moreInfoCalls.length === 1")
    assert page.evaluate("window.moreInfoCalls") == ["binary_sensor.motion"]


def test_native_scroll_has_finite_height_without_parent_height(page):
    page.evaluate("document.querySelector('#mount').style.height = 'auto'")
    assert page.evaluate("scroller.clientHeight <= window.innerHeight")
    assert page.evaluate("scroller.scrollHeight > scroller.clientHeight")
    page.locator(".chip").first.hover()
    page.mouse.wheel(0, 400)
    page.wait_for_function("scroller.scrollTop > 100")


def test_timeline_loads_recorder_states_on_a_rolling_offset_axis(page):
    page.evaluate(
        """async () => {
          const now = Date.now();
          const calls = [];
          panel.hass = {
            ...panel.hass,
            callWS: async (message) => {
              calls.push(message);
              return [[{
                state: "active_timer",
                last_changed: new Date(now - 60 * 60 * 1000).toISOString(),
              }]];
            },
          };
          panel.history.set("controller-0", []);
          await panel._loadHistory();
          window.timelineCalls = calls;
        }"""
    )
    assert page.locator(".timeline-axis").first.locator("span").all_text_contents() == [
        "-24h", "-22h", "-20h", "-18h", "-16h", "-14h", "-12h",
        "-10h", "-8h", "-6h", "-4h", "-2h", "0",
    ]
    assert page.locator(".timeline").first.get_attribute("style").find(
        "#28bd57"
    ) >= 0
    history_call = page.evaluate("timelineCalls[0]")
    assert history_call["minimal_response"] is False
    assert history_call["end_time"] > history_call["start_time"]


def test_admin_config_panel_switches_modes_and_saves_explicitly(page):
    page.evaluate(
        """() => {
          const controller = panel.controllers[0];
          controller.entry_id = "entry-1";
          controller.form = {
            basic: {
              name: controller.name,
              icon: controller.icon,
              trigger_entities: ["binary_sensor.motion"],
              control_entities: ["light.room"],
              delay_seconds: {days: 0, hours: 0, minutes: 3, seconds: 0},
            },
            timer: {sensor_type: "event", sensor_resets_timer: false},
            advanced: {state_on_states: "on", state_off_states: "off"},
          };
          window.wsCalls = [];
          panel.hass = {
            ...panel.hass,
            user: {is_admin: true},
            callWS: async (message) => {
              wsCalls.push(message);
              if (message.type === "entity_controller/panel/save") return {success: true};
              if (message.type === "entity_controller/panel") return {controllers: panel.controllers};
              return [[]];
            },
          };
        }"""
    )
    page.locator(".edit-toggle").first.click()
    assert page.locator(".editor").is_visible()
    assert page.locator('[data-field="state_on_states"]').count() == 0
    page.locator('button[data-mode="full"]').click()
    page.locator(".editor-section").filter(has_text="Pokročilé stavy").locator("summary").click()
    assert page.locator('[data-field="state_on_states"]').is_visible()
    page.locator('[data-field="name"]').first.fill("Updated room")
    assert page.evaluate(
        'wsCalls.filter((call) => call.type === "entity_controller/panel/save").length'
    ) == 0
    page.locator(".editor-save").click()
    page.wait_for_function(
        'wsCalls.some((call) => call.type === "entity_controller/panel/save")'
    )
    save = page.evaluate(
        'wsCalls.find((call) => call.type === "entity_controller/panel/save")'
    )
    assert save["entry_id"] == "entry-1"
    assert save["form"]["basic"]["name"] == "Updated room"


def test_editor_uses_compact_cards_and_searchable_entity_chips(page):
    page.evaluate(
        """() => {
          const controller = panel.controllers[0];
          controller.entry_id = "entry-1";
          controller.form = {
            basic: {
              name: controller.name,
              icon: controller.icon,
              trigger_entities: ["binary_sensor.motion"],
              control_entities: ["light.room"],
              delay_seconds: {days: 0, hours: 0, minutes: 3, seconds: 0},
            },
            timer: {sensor_type: "event", sensor_resets_timer: true},
            monitoring: {state_entities: [], blocking_enabled: true},
            constraints: {constraint_enabled: true, constraint_start_source: "fixed",
              constraint_start_time: "06:00:00", constraint_end_source: "fixed",
              constraint_end_time: "22:00:00"},
          };
          panel.hass = {
            ...panel.hass,
            user: {is_admin: true},
            states: {
              ...panel.hass.states,
              "binary_sensor.front_door": {
                state: "off", attributes: {friendly_name: "Front door"}
              },
            },
            callWS: async (message) => message.type === "entity_controller/panel/save"
              ? {success: true} : {controllers: panel.controllers},
          };
        }"""
    )

    page.locator(".edit-toggle").first.click()

    assert page.locator(".editor").is_visible()
    assert not page.locator(".row.editing .timeline-line").is_visible()
    assert page.locator(".editor-card").filter(has_text="Spúšťače").is_visible()
    assert page.locator(".editor-card").filter(has_text="Ovládané entity").is_visible()
    assert page.locator('input[type="range"][data-field="delay_seconds"]').get_attribute("type") == "range"
    assert page.locator('[data-duration-manual="basic.delay_seconds"]').get_attribute("type") == "number"
    assert page.locator('[data-picker-toggle="basic.trigger_entities"]').is_visible()

    page.locator('[data-picker-toggle="basic.trigger_entities"]').click()
    search = page.locator('[data-entity-search="basic.trigger_entities"]')
    search.fill("front door")
    page.locator('[data-entity-option="binary_sensor.front_door"]').click()

    assert page.locator(
        '.selected-entity[data-entity-id="binary_sensor.front_door"]'
    ).is_visible()


def test_editor_picker_survives_runtime_refresh_and_normalizes_search(page):
    page.evaluate(
        """() => {
          const controller = panel.controllers[0];
          controller.entry_id = "entry-1";
          controller.form = {
            basic: {name: controller.name, icon: controller.icon,
              trigger_entities: [], control_entities: [], delay_seconds: 180},
          };
          panel.hass = {
            ...panel.hass, user: {is_admin: true},
            states: {...panel.hass.states,
              "binary_sensor.living_room_motion": {
                state: "off", attributes: {friendly_name: "Obývačka pohyb"}
              }},
            callWS: async (message) => message.type === "entity_controller/panel"
              ? {controllers: panel.controllers}
              : message.type === "history/history_during_period" ? [[]] : {success: true},
          };
        }"""
    )
    page.locator(".edit-toggle").first.click()
    page.locator('[data-picker-toggle="basic.trigger_entities"]').click()
    search = page.locator('[data-entity-search="basic.trigger_entities"]')
    search.fill("obyvacka poh")
    assert page.locator('[data-entity-option="binary_sensor.living_room_motion"]').is_visible()

    page.evaluate("panel._refresh()")
    page.wait_for_timeout(50)

    assert page.locator('[data-picker-toggle="basic.trigger_entities"]').get_attribute("aria-expanded") == "true"
    assert search.input_value() == "obyvacka poh"


def test_controller_icon_is_selected_from_searchable_visual_picker(page):
    page.evaluate(
        """() => {
          const controller = panel.controllers[0];
          controller.entry_id = "entry-1";
          controller.form = {basic: {name: controller.name, icon: "mdi:home-automation",
            trigger_entities: [], control_entities: [], delay_seconds: 180}};
          panel.hass = {...panel.hass, user: {is_admin: true},
            callWS: async (message) => message.type === "entity_controller/panel/save"
              ? {success: true, form: message.form} : {controllers: panel.controllers}};
        }"""
    )
    page.locator(".edit-toggle").first.click()
    assert page.locator('[data-field="icon"]').count() == 0
    page.locator("button.controller-avatar").click()
    page.locator(".icon-search").fill("sunset")
    page.locator('[data-icon-value="mdi:weather-sunset"]').click()
    page.wait_for_function(
        'panel.controllers[0].form.basic.icon === "mdi:weather-sunset"'
    )
    assert page.locator("article").first.locator(".controller-icon").get_attribute("icon") == "mdi:weather-sunset"


def test_explicit_save_uses_authoritative_response_without_full_panel_reload(page):
    page.evaluate(
        """() => {
          const controller = panel.controllers[0];
          controller.entry_id = "entry-1";
          controller.form = {basic: {name: controller.name, icon: controller.icon,
            trigger_entities: [], control_entities: [], delay_seconds: 180}};
          window.panelRequests = 0;
          panel.hass = {
            ...panel.hass, user: {is_admin: true},
            callWS: async (message) => {
              if (message.type === "entity_controller/panel") {
                panelRequests += 1;
                return {controllers: panel.controllers};
              }
              if (message.type === "entity_controller/panel/save")
                return {success: true, form: message.form};
              return [[]];
            },
          };
        }"""
    )
    page.locator(".edit-toggle").first.click()
    page.locator('[data-field="name"]').first.fill("Saved room")
    assert page.evaluate(
        'panel._dirtyControllers.has("controller-0") && panelRequests === 0'
    )
    page.locator(".editor-save").click()
    page.wait_for_function('panel.shadowRoot.querySelector(".save-state")?.textContent === "Uložené"')
    assert page.evaluate("panelRequests") == 0
    assert page.locator('[data-field="name"]').first.input_value() == "Saved room"


def test_failed_save_keeps_draft_and_reports_backend_error(page):
    page.evaluate(
        """() => {
          const controller = panel.controllers[0];
          controller.entry_id = "entry-1";
          controller.form = {basic: {name: "Confirmed room", icon: controller.icon,
            trigger_entities: [], control_entities: [], delay_seconds: 180}};
          panel.hass = {...panel.hass, user: {is_admin: true},
            callWS: async (message) => {
              if (message.type === "entity_controller/panel/save")
                throw new Error("Rejected by backend");
              return {controllers: panel.controllers};
            }};
        }"""
    )
    page.locator(".edit-toggle").first.click()
    field = page.locator('[data-field="name"]').first
    field.fill("Rejected room")
    page.locator(".editor-save").click()
    page.wait_for_function('panel._saveErrors.has("controller-0")')
    assert "Rejected by backend" in page.locator(".save-state").inner_text()
    assert page.locator('[data-field="name"]').first.input_value() == "Rejected room"
    assert page.evaluate('panel._dirtyControllers.has("controller-0")')


def test_schedule_range_displays_and_saves_an_overnight_window(page):
    page.evaluate(
        """() => {
          const controller = panel.controllers[0];
          controller.entry_id = "entry-1";
          controller.form = {
            basic: {name: controller.name, trigger_entities: [], control_entities: [], delay_seconds: 180},
            constraints: {constraint_enabled: true, constraint_start_source: "fixed",
              constraint_start_time: "22:00:00", constraint_end_source: "fixed",
              constraint_end_time: "06:00:00"},
          };
          window.wsCalls = [];
          panel.hass = {
            ...panel.hass,
            user: {is_admin: true},
            callWS: async (message) => {
              wsCalls.push(message);
              return message.type === "entity_controller/panel/save"
                ? {success: true} : {controllers: panel.controllers};
            },
          };
        }"""
    )

    page.locator(".edit-toggle").first.click()
    schedule = page.locator(".schedule-card").filter(has_text="Povolený čas")
    assert schedule.locator(".card-heading-copy p").inner_text() == "22:00 – 06:00 každý deň"
    start = page.locator('[data-field="constraint_start_time"]')
    assert start.get_attribute("type") == "range"
    start.focus()
    start.press("ArrowRight")
    assert page.evaluate('wsCalls.filter((call) => call.type === "entity_controller/panel/save").length') == 0
    page.locator(".editor-save").click()
    page.wait_for_function(
        'wsCalls.some((call) => call.type === "entity_controller/panel/save")'
    )
    save = page.evaluate(
        'wsCalls.find((call) => call.type === "entity_controller/panel/save")'
    )
    assert save["form"]["constraints"]["constraint_start_time"] == "22:15:00"


def test_dragging_solar_schedule_endpoint_switches_to_fixed_time(page):
    page.evaluate(
        """() => {
          const controller = panel.controllers[0];
          controller.entry_id = "entry-1";
          controller.form = {
            basic: {name: controller.name, trigger_entities: [], control_entities: [], delay_seconds: 180},
            constraints: {constraint_enabled: true, constraint_start_source: "sunrise",
              constraint_start_time: "06:00:00", constraint_end_source: "fixed",
              constraint_end_time: "22:00:00"},
          };
          window.wsCalls = [];
          panel.hass = {
            ...panel.hass, user: {is_admin: true},
            callWS: async (message) => {
              wsCalls.push(message);
              return message.type === "entity_controller/panel/save"
                ? {success: true, form: message.form, resolved_schedule: {constraint: {start: 375, end: 1320}}}
                : {controllers: panel.controllers};
            },
          };
        }"""
    )
    page.locator(".edit-toggle").first.click()
    start = page.locator('[data-field="constraint_start_time"]')
    assert start.is_enabled()
    start.focus()
    start.press("ArrowRight")
    page.locator(".editor-save").click()
    page.wait_for_function(
        'wsCalls.some((call) => call.type === "entity_controller/panel/save")'
    )
    save = page.evaluate(
        'wsCalls.find((call) => call.type === "entity_controller/panel/save")'
    )
    assert save["form"]["constraints"]["constraint_start_source"] == "fixed"


def test_solar_offset_uses_fifteen_minute_steps_once_in_basic_mode(page):
    page.evaluate(
        """() => {
          const controller = panel.controllers[0];
          controller.entry_id = "entry-1";
          controller.form = {
            basic: {name: controller.name, trigger_entities: [], control_entities: [], delay_seconds: 180},
            constraints: {constraint_enabled: true, constraint_start_source: "sunrise",
              constraint_start_time: "06:00:00", constraint_start_offset_seconds: 0,
              constraint_end_source: "fixed", constraint_end_time: "22:00:00"},
          };
          window.wsCalls = [];
          panel.hass = {...panel.hass, user: {is_admin: true},
            callWS: async (message) => {
              wsCalls.push(message);
              return message.type === "entity_controller/panel/save"
                ? {success: true, form: message.form} : {controllers: panel.controllers};
            }};
        }"""
    )
    page.locator(".edit-toggle").first.click()
    page.locator('[aria-label="Zvýšiť posun o 15 minút"]').click()
    assert page.evaluate(
        'panel.controllers[0].form.constraints.constraint_start_offset_seconds'
    ) == 900
    page.locator(".editor-save").click()
    page.wait_for_function(
        'wsCalls.some((call) => call.type === "entity_controller/panel/save")'
    )
    save = page.evaluate(
        'wsCalls.find((call) => call.type === "entity_controller/panel/save")'
    )
    assert save["form"]["constraints"]["constraint_start_offset_seconds"] == 900
    assert page.locator('.editor-section [data-field="constraint_start_offset_seconds"]').count() == 0


def test_editor_waits_for_explicit_save_and_has_manual_duration_input(page):
    page.evaluate(
        """() => {
          const controller = panel.controllers[0];
          controller.entry_id = "entry-1";
          controller.form = {
            basic: {name: controller.name, trigger_entities: [], control_entities: [], delay_seconds: 240},
          };
          window.wsCalls = [];
          panel.hass = {...panel.hass, user: {is_admin: true},
            callWS: async (message) => {
              wsCalls.push(message);
              return message.type === "entity_controller/panel/save"
                ? {success: true, form: message.form} : {controllers: panel.controllers};
            }};
        }"""
    )

    page.locator(".edit-toggle").first.click()
    duration = page.locator('input[type="range"][data-field="delay_seconds"][data-kind="duration"]')
    assert duration.get_attribute("type") == "range"
    manual = page.locator('[data-duration-manual="basic.delay_seconds"]')
    assert manual.get_attribute("type") == "number"
    manual.fill("301")
    assert page.evaluate(
        'wsCalls.filter((call) => call.type === "entity_controller/panel/save").length'
    ) == 0
    assert page.locator(".editor-save").is_visible()
    assert page.locator(".editor-close").is_visible()

    page.locator(".editor-save").click()
    page.wait_for_function(
        'wsCalls.some((call) => call.type === "entity_controller/panel/save")'
    )
    saved = page.evaluate(
        'wsCalls.find((call) => call.type === "entity_controller/panel/save")'
    )
    assert saved["form"]["basic"]["delay_seconds"] == {
        "days": 0, "hours": 0, "minutes": 5, "seconds": 1
    }


def test_close_reopen_is_single_click_and_preserves_unsaved_draft(page):
    page.evaluate(
        """() => {
          const controller = panel.controllers[0];
          controller.entry_id = "entry-1";
          controller.form = {
            basic: {name: controller.name, trigger_entities: [], control_entities: [], delay_seconds: 240},
          };
          window.wsCalls = [];
          panel.style.setProperty("--secondary-background-color", "rgb(20, 30, 40)");
          panel.hass = {...panel.hass, user: {is_admin: true},
            callWS: async (message) => {
              wsCalls.push(message);
              return message.type === "entity_controller/panel/save"
                ? {success: true, form: message.form} : {controllers: panel.controllers};
            }};
        }"""
    )

    page.locator(".edit-toggle").first.click()
    assert page.locator(".editor").is_visible()
    assert page.locator(".editor").evaluate("element => getComputedStyle(element).backgroundColor") == "rgb(20, 30, 40)"
    assert page.locator(".editor-card").first.evaluate(
        "element => getComputedStyle(element).backgroundColor"
    ) == "rgba(0, 0, 0, 0)"
    page.locator('[data-field="name"]').first.fill("Draft room")
    page.locator(".editor-close").click()
    assert page.locator(".editor").count() == 0
    assert page.evaluate(
        'wsCalls.filter((call) => call.type === "entity_controller/panel/save").length'
    ) == 0

    page.locator(".edit-toggle").first.click()
    assert page.locator(".editor").is_visible()
    assert page.locator('[data-field="name"]').first.input_value() == "Draft room"
    assert page.locator(".save-state").inner_text() == "Neuložené zmeny"

