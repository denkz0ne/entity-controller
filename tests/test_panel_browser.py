"""Browser regressions for wheel/touch scrolling during Home Assistant updates."""

from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

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
              // HA WebSocket history is keyed by entity ID, uses epoch
              // seconds and omits lc when it equals lu (even with minimal=false).
              return {[message.entity_ids[0]]: [{
                s: "active_timer",
                lu: (now - 60 * 60 * 1000) / 1000,
              }]};
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


def test_timeline_restores_compact_history_after_page_reload(page):
    recorded = page.evaluate(
        """() => {
          const now = Date.now() / 1000;
          return {
            "sensor.state_0": [
              {s: "idle", lu: now - 90000},
              {s: "active_timer", lu: now - 3600},
              {s: "blocked", lc: now - 1800, lu: now - 600},
              {s: "idle", lu: now - 60},
            ],
            "sensor.unrelated": [{s: "overridden", lu: now - 90000}],
          };
        }"""
    )
    for reload_page in (False, True):
        if reload_page:
            page.reload()
            mount_panel(page)
        page.evaluate(
            """async (recorded) => {
              panel.controllers = panel.controllers.slice(0, 1);
              panel.hass = {...panel.hass, callWS: async () => recorded};
              await panel._loadHistory();
            }""",
            recorded,
        )
        style = page.locator(".timeline").first.get_attribute("style")
        for color in ("#aab2bd", "#28bd57", "#f04452"):
            assert color in style
        assert "#9b59d0" not in style
        assert "#d6dbe0" not in style
        assert page.evaluate("panel.history.get('controller-0').length") == 4
        assert page.evaluate(
            "Date.parse(panel.history.get('controller-0')[2].last_changed) / 1000"
        ) == pytest.approx(recorded["sensor.state_0"][2]["lc"], abs=0.001)


@pytest.mark.parametrize("failure", ("disconnected", "malformed"))
def test_timeline_keeps_loaded_records_when_history_refresh_fails(page, failure):
    page.evaluate(
        """async (failure) => {
          panel.controllers = panel.controllers.slice(0, 1);
          const recorded = {"sensor.state_0": [
            {s: "active_timer", lu: Date.now() / 1000 - 3600},
          ]};
          panel.hass = {...panel.hass, callWS: async () => recorded};
          await panel._loadHistory();
          panel.hass = {...panel.hass, callWS: async () => {
            if (failure === "disconnected") throw new Error("Spojenie prerušené");
            return {"sensor.state_0": [{s: "active_timer"}]};
          }};
          await panel._loadHistory();
        }""",
        failure,
    )
    assert "#28bd57" in page.locator(".timeline").first.get_attribute("style")
    expect(page.locator(".timeline-error")).to_be_visible()
    assert page.evaluate("panel.history.get('controller-0').length") == 1


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
    assert page.locator(".editor-card").filter(has_text="Čo spúšťa automatiku").is_visible()
    assert page.locator(".editor-card").filter(has_text="Ovládané zariadenia").is_visible()
    assert page.locator('input[type="range"][data-field="delay_seconds"]').get_attribute("type") == "range"
    assert page.locator('[data-duration-manual="basic.delay_seconds"]').get_attribute("type") == "number"
    assert page.locator('[data-picker-toggle="basic.trigger_entities"]').is_visible()

    page.locator('[data-picker-toggle="basic.trigger_entities"]').click()
    search = page.locator('[data-entity-search="basic.trigger_entities"]')
    search.fill("front door")
    expect(page.locator('[data-entity-option="light.room"]')).not_to_be_visible()
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
    expect(page.locator('[data-entity-option="light.room"]')).not_to_be_visible()

    page.evaluate("panel._refresh()")
    page.wait_for_timeout(50)

    assert page.locator('[data-picker-toggle="basic.trigger_entities"]').get_attribute("aria-expanded") == "true"
    assert search.input_value() == "obyvacka poh"
    expect(page.locator('[data-entity-option="light.room"]')).not_to_be_visible()
    search.fill("no matching entity")
    expect(page.locator('.entity-option:visible')).to_have_count(0)
    search.fill("")
    expect(page.locator('[data-entity-option="light.room"]')).to_be_visible()


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
    expect(page.locator('[data-icon-value="mdi:lightbulb"]')).not_to_be_visible()
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


@pytest.mark.parametrize("mode", ["basic", "full"])
@pytest.mark.parametrize("night_enabled", [False, True])
def test_saved_editor_payload_passes_ha_schema_without_changing_other_settings(
    page, mode, night_enabled
):
    from custom_components.entity_controller.config_flow import (
        CONTROLLER_SCHEMA,
        controller_form_values,
        normalize_controller_user_input,
    )

    stored = {
        "name": "Hall", "icon": "mdi:timer",
        "trigger_entities": ["binary_sensor.motion"],
        "control_entities": ["light.room"],
        "delay_seconds": 181, "block_timeout_seconds": None,
        "constraint_window": {
            "start": {"source": "sunrise", "time": "06:07:30", "offset_seconds": 900},
            "end": {"source": "fixed", "time": "22:07:30", "offset_seconds": 0},
        },
        "night_mode": {
            "start": {"source": "sunset", "time": "20:07:30", "offset_seconds": -900},
            "end": {"source": "sunrise", "time": "06:07:30", "offset_seconds": 0},
            "delay_seconds": 61, "service_data_on": {"brightness": 10},
            "service_data_off": {},
        } if night_enabled else None,
        "trigger_on_states": ["on", "playing"],
        "service_data_on": {"brightness": 100},
    }
    baseline = normalize_controller_user_input(CONTROLLER_SCHEMA(controller_form_values(stored)))
    page.evaluate(
        """form => {
          const controller = panel.controllers[0];
          controller.entry_id = "entry-1";
          controller.form = form;
          controller.resolved_schedule = {constraint: {start: 390, end: 1327},
            night: {start: 1185, end: 375}};
          window.wsCalls = [];
          panel.hass = {...panel.hass, user: {is_admin: true}, callWS: async message => {
            wsCalls.push(message);
            return {success: true, form: message.form};
          }};
        }""", controller_form_values(baseline),
    )
    page.locator(".edit-toggle").first.click()
    if mode == "full":
        page.locator('button[data-mode="full"]').click()
    page.locator('[data-field="name"]').first.fill("Renamed room")
    page.locator(".editor-save").click()
    page.wait_for_function('wsCalls.some(call => call.type === "entity_controller/panel/save")')
    saved = page.evaluate('wsCalls.find(call => call.type === "entity_controller/panel/save")')
    normalized = normalize_controller_user_input(CONTROLLER_SCHEMA(saved["form"]))
    assert normalized == {**baseline, "name": "Renamed room"}


def test_invalid_parameter_stops_save_before_websocket_submission(page):
    page.evaluate("""() => {
      const controller = panel.controllers[0];
      controller.entry_id = "entry-1";
      controller.form = {basic: {name: "Hall", delay_seconds: 180, control_entities: ["light.room"]},
        actions: {service_data_on: {brightness: 100}}};
      window.wsCalls = [];
      panel.hass = {...panel.hass, user: {is_admin: true}, callWS: async message => {
        wsCalls.push(message); return {success: true, form: message.form};
      }};
    }""")
    page.locator(".edit-toggle").first.click()
    section = page.locator('.parameter-editor[data-editor-section="actions-service_data_on"]')
    section.locator("summary").click()
    section.locator('input[type="number"][data-service-param="brightness_pct"]').fill("101")
    page.locator('[data-field="name"]').first.fill("Renamed room")
    page.locator(".editor-save").click()
    assert page.evaluate('wsCalls.filter(call => call.type === "entity_controller/panel/save").length') == 0
    assert "Uloženie zlyhalo" in page.locator(".save-state").inner_text()
    assert section.locator('input[type="number"][data-service-param="brightness_pct"]').input_value() == "101"


def test_graphical_light_parameters_preserve_legacy_and_separate_profiles(page):
    page.evaluate("""() => {
      const c=panel.controllers[0]; c.entry_id='entry-1';
      c.form={basic:{name:'Room',control_entities:['light.room'],delay_seconds:{minutes:4}},
        actions:{service_data_on:{brightness:100,custom_key:'keep'},service_data_off:{}},
        night:{night_mode_enabled:true,night_start_source:'fixed',night_end_source:'fixed',
          night_start_time:'22:00',night_end_time:'06:00',night_service_data_on:{brightness:10},night_service_data_off:{}}};
      window.wsCalls=[];panel.hass={...panel.hass,user:{is_admin:true},callWS:async m=>{
        wsCalls.push(m);return {success:true,form:m.form};}};
    }""")
    page.locator('.edit-toggle').first.click()
    day = page.locator('[data-editor-section="actions-service_data_on"]')
    day.locator('summary').click()
    assert page.locator('.editor textarea[data-kind="json"]').count() == 0
    day.locator('input[type="number"][data-service-param="brightness_pct"]').fill('75')
    day.locator('input[type="checkbox"][data-service-param="color_temp_kelvin"]').check()
    day.locator('input[type="number"][data-service-param="color_temp_kelvin"]').fill('2700')
    assert day.locator('input[type="range"][data-service-param="brightness_pct"]').input_value() == '75'
    night = page.locator('[data-editor-section="night-night_service_data_on"]')
    night.locator('summary').click()
    night.locator('input[type="number"][data-service-param="brightness_pct"]').fill('20')
    page.evaluate('panel.hass={...panel.hass};panel._render(true)')
    expect(day).to_have_attribute('open','')
    expect(night).to_have_attribute('open','')
    page.locator('.editor-save').click()
    saved = page.evaluate('wsCalls.find(m=>m.type==="entity_controller/panel/save").form')
    assert saved['actions']['service_data_on'] == {'brightness_pct':75,'color_temp_kelvin':2700,'custom_key':'keep'}
    assert saved['night']['night_service_data_on'] == {'brightness_pct':20}
    assert saved['actions']['service_data_off'] == {}


def test_basic_decision_distinguishes_running_and_draft_settings(page):
    page.evaluate("""() => {
      const c=panel.controllers[0];c.state='active_timer';c.expires_at=new Date(Date.now()+240000).toISOString();
      c.night_active=true;c.form={basic:{name:'Room',delay_seconds:{minutes:4},control_entities:['light.room']},
        actions:{service_data_on:{brightness_pct:80}},night:{night_mode_enabled:true,night_delay_seconds:{minutes:1},
          night_service_data_on:{brightness_pct:20,color_temp_kelvin:2700}}};
      panel.hass={...panel.hass,user:{is_admin:true}};
    }""")
    page.locator('.edit-toggle').first.click()
    decision = page.locator('.live-decision')
    expect(decision).to_contain_text('Nočný profil')
    expect(decision).to_contain_text('Jas 20 % · 2700 K')
    assert decision.locator('[data-decision-countdown]').inner_text() in {'4 min','3 min 59 s'}
    decision.locator('.field-help').click()
    expect(decision.locator('.help-popover:popover-open')).to_be_visible()
    page.evaluate('panel._updateClock()')
    expect(decision.locator('.help-popover:popover-open')).to_be_visible()
    decision.locator('.field-help').click()
    page.locator('[data-duration-manual="basic.delay_seconds"]').fill('600')
    expect(decision.locator('.draft-preview')).to_contain_text('10 min')
    expect(decision.locator('.decision-metrics')).to_contain_text('Jas 20 % · 2700 K')
    page.evaluate('panel.controllers[0].state="overridden";panel.controllers[0].active_overrides=["input_boolean.override"];panel._updateEditorStatus(panel.controllers[0])')
    expect(decision.locator('[data-decision-countdown]')).to_have_text('Odpočet nebeží')
    expect(decision).to_contain_text('Aktívne prednostné riadenie')


def test_solar_source_and_offset_preview_changes_without_saving(page):
    page.evaluate("""() => {
      const c=panel.controllers[0];c.form={basic:{name:'Room'},constraints:{constraint_enabled:true,
        constraint_start_source:'fixed',constraint_start_time:'12:00',constraint_end_source:'fixed',constraint_end_time:'22:00'}};
      c.resolved_schedule={solar:{sunrise:375,sunset:1104},constraint:{start:720,end:1320}};
      panel.hass={...panel.hass,user:{is_admin:true}};
    }""")
    page.locator('.edit-toggle').first.click()
    page.locator('[data-field="constraint_start_source"]').select_option('sunrise')
    assert page.locator('[data-field="constraint_start_time"]').input_value() == '375'
    page.locator('[aria-label="Zvýšiť posun o 15 minút"]').click()
    assert page.locator('[data-field="constraint_start_time"]').input_value() == '390'
    page.locator('[data-field="constraint_start_source"]').select_option('sunset')
    assert page.locator('[data-field="constraint_start_time"]').input_value() == '1119'
    assert page.evaluate('panel.controllers[0].form.constraints.constraint_start_time') == '12:00'
    page.evaluate("""async () => {
      panel._loadHistory=async()=>{};
      panel.hass.callWS=async()=>({controllers:[{...panel.controllers[0],
        resolved_schedule:{solar:{sunrise:380,sunset:1110},constraint:{start:720,end:1320}}}]});
      await panel._refresh();
    }""")
    assert page.locator('[data-field="constraint_start_time"]').input_value() == '1125'
    assert page.evaluate('panel.controllers[0].form.constraints.constraint_start_source') == 'sunset'
    assert page.evaluate('panel.controllers[0].form.constraints.constraint_start_offset_seconds') == 900


def test_native_action_editor_updates_draft_and_scene_selector(page):
    page.evaluate("""() => {
      customElements.define('ha-form',class extends HTMLElement {});
      const c=panel.controllers[0];c.entry_id='entry-1';c.form={basic:{name:'Room'},actions:{on_enter_active:'on',on_exit_active:'off'}};
      panel.hass={...panel.hass,user:{is_admin:true},states:{...panel.hass.states,'scene.evening':{attributes:{friendly_name:'Večer'}}}};
    }""")
    page.locator('.edit-toggle').first.click()
    page.locator('[data-field="on_enter_active"]').select_option('custom')
    native = page.locator('ha-form[data-native-action="on_enter_active"]')
    assert native.evaluate('el=>el.schema[0].selector') == {'action':{}}
    page.locator('[data-scene-hook="on_enter_active"]').select_option('scene.evening')
    assert native.evaluate('el=>el.data.sequence') == [{'action':'scene.turn_on','target':{'entity_id':'scene.evening'}}]
    native.evaluate("el=>el.dispatchEvent(new CustomEvent('value-changed',{detail:{value:{sequence:[{action:'script.turn_on',target:{entity_id:'script.test'}}]}}}))")
    assert page.evaluate('panel.controllers[0].form.actions.lifecycle_actions.on_enter_active[0].action') == 'script.turn_on'
    page.locator('[data-field="on_exit_active"]').select_option('restore')
    assert page.evaluate('panel.controllers[0].form.actions.on_enter_idle') == 'ignore'
    page.locator('.editor [data-icon-toggle]').click()
    icon = page.locator('ha-form[data-native-icon]')
    assert icon.evaluate('el=>el.schema[0].selector') == {'icon':{}}
    icon.evaluate("el=>el.dispatchEvent(new CustomEvent('value-changed',{detail:{value:{icon:'mdi:sofa'}}}))")
    assert page.evaluate('panel.controllers[0].form.basic.icon') == 'mdi:sofa'


def test_native_editor_bootstraps_registered_route_without_navigation(page):
    page.evaluate("""() => {
      const host=document.createElement('div');const shadow=host.attachShadow({mode:'open'});
      const resolver=document.createElement('partial-panel-resolver');window.nativeLoads=0;
      resolver.routerOptions={routes:{dashboard:{tag:'ha-panel-lovelace',load:async()=>{
        nativeLoads++;window.loadCardHelpers=async()=>({createCardElement:()=>new(class{
          static async getConfigElement(){customElements.define('ha-form',class extends HTMLElement {});}
        })()});}}}};shadow.append(resolver);document.body.append(host);
      panel.controllers[0].form={basic:{name:'Room'},actions:{on_enter_active:'custom'}};
      panel.hass={...panel.hass,user:{is_admin:true}};
    }""")
    page.locator('.edit-toggle').first.click()
    expect(page.locator('ha-form[data-native-action]')).to_have_attribute('data-native-ready','true')
    assert page.evaluate('nativeLoads') == 1
    assert page.url == 'about:blank'
    expect(page.locator('.native-loading')).not_to_be_visible()


def test_native_editor_failure_has_retry_and_recovers(page):
    page.evaluate("""() => {
      panel.controllers[0].form={basic:{name:'Room'},actions:{on_enter_active:'custom'}};
      panel.hass={...panel.hass,user:{is_admin:true}};
    }""")
    page.locator('.edit-toggle').first.click()
    expect(page.locator('[data-native-retry]')).to_be_visible()
    page.evaluate("""() => {window.loadCardHelpers=async()=>({createCardElement:()=>new(class{
      static async getConfigElement(){customElements.define('ha-form',class extends HTMLElement {});}
    })()});}""")
    page.locator('[data-native-retry]').click()
    expect(page.locator('ha-form[data-native-action]')).to_have_attribute('data-native-ready','true')


def test_light_capabilities_intersection_and_kelvin_alias(page):
    page.evaluate("""() => {
      const c=panel.controllers[0];c.form={basic:{name:'Room',control_entities:['light.room','light.second']},
        actions:{service_data_on:{kelvin:2700,brightness:100,keep:'yes'}}};
      panel.hass={...panel.hass,user:{is_admin:true},states:{...panel.hass.states,
        'light.room':{state:'on',attributes:{supported_color_modes:['color_temp'],min_color_temp_kelvin:2000,max_color_temp_kelvin:6500,effect_list:['a','b']}},
        'light.second':{state:'off',attributes:{supported_color_modes:['color_temp'],min_color_temp_kelvin:2500,max_color_temp_kelvin:5000,effect_list:['b','c']}}}};
    }""")
    page.locator('.edit-toggle').first.click()
    params=page.locator('[data-editor-section="actions-service_data_on"]')
    params.locator('summary').click()
    temp=params.locator('input[type="number"][data-service-param="color_temp_kelvin"]')
    assert temp.input_value() == '2700'
    assert temp.get_attribute('min') == '2500'
    assert temp.get_attribute('max') == '5000'
    assert params.locator('[data-service-param="rgb_color"]').count() == 0
    assert params.locator('select[data-service-param="effect"] option').all_text_contents() == ['Pôvodný efekt','b']
    temp.fill('3000')
    assert page.evaluate('panel.controllers[0].form.actions.service_data_on') == {'brightness':100,'color_temp_kelvin':3000,'keep':'yes'}


def test_transition_uses_shared_capabilities_and_unavailable_preserves_parameters(page):
    page.evaluate("""() => {
      panel.controllers[0].form={basic:{name:'Room',control_entities:['light.room','light.second']},
        actions:{service_data_on:{transition:2,brightness_pct:40}}};
      panel.hass={...panel.hass,user:{is_admin:true},states:{...panel.hass.states,
        'light.room':{state:'on',attributes:{supported_color_modes:['brightness'],supported_features:32}},
        'light.second':{state:'off',attributes:{supported_color_modes:['onoff'],supported_features:0}}}};
    }""")
    page.locator('.edit-toggle').first.click()
    params=page.locator('[data-editor-section="actions-service_data_on"]')
    params.locator('summary').click()
    assert params.locator('[data-service-param="transition"]').count() == 0
    assert params.locator('[data-service-param="brightness_pct"]').count() == 0
    page.evaluate("""() => {
      panel.hass.states['light.second']={state:'on',attributes:{supported_color_modes:['brightness'],supported_features:32}};
      panel._rowMarkup.clear();panel._render();
    }""")
    assert params.locator('input[type="number"][data-service-param="transition"]').input_value() == '2'
    page.evaluate("""() => {
      panel.hass.states['light.second']={state:'unavailable',attributes:{}};
      panel._rowMarkup.clear();panel._render();
    }""")
    expect(params.locator('.capability-warning')).to_contain_text('Možnosti svetla nie sú overené')
    params.locator('.capability-warning .field-help').click()
    expect(params.locator('.capability-warning .help-popover:popover-open')).to_be_visible()
    assert params.locator('[data-service-param="transition"]').count() == 0
    assert page.evaluate('panel.controllers[0].form.actions.service_data_on') == {'transition':2,'brightness_pct':40}
    assert page.locator('.editor-save').is_disabled()


def test_entity_picker_keyboard_empty_result_and_presence(page):
    page.evaluate("""() => {
      panel.controllers[0].form={basic:{name:'Room',trigger_entities:[],presence_entities:[]}};
      panel.hass={...panel.hass,user:{is_admin:true}};
    }""")
    page.locator('.edit-toggle').first.click()
    page.locator('.presence-editor>summary').click()
    page.locator('[data-picker-toggle="basic.presence_entities"]').click()
    search=page.locator('[data-entity-search="basic.presence_entities"]')
    search.fill('nobody')
    expect(page.locator('.search-empty')).to_be_visible()
    search.fill('motion')
    search.press('ArrowDown')
    expect(page.locator('.entity-option:not([hidden])')).to_be_focused()
    page.locator('.entity-option:not([hidden])').press('Enter')
    assert page.evaluate('panel.controllers[0].form.basic.presence_entities') == ['binary_sensor.motion']
    expect(page.locator('.presence-editor')).to_have_attribute('open','')
    page.locator('.entity-search').press('Escape')
    expect(page.locator('.entity-picker')).to_have_count(0)
    expect(page.locator('[data-picker-toggle="basic.presence_entities"]')).to_be_focused()


@pytest.mark.parametrize("edit_while_saving", [False, True])
def test_save_response_preserves_new_edits_and_updates_current_controller(page, edit_while_saving):
    page.evaluate("""() => {
      const controller = panel.controllers[0];
      controller.entry_id = "entry-1";
      controller.form = {basic: {name: "Hall", delay_seconds: 180}};
      panel._loadHistory = async () => {};
      panel.hass = {...panel.hass, user: {is_admin: true}, callWS: message => {
        if (message.type === "entity_controller/panel") return Promise.resolve({controllers:
          panel.controllers.map(item => {const fresh = {...item}; delete fresh._draftRevision; return fresh;})});
        return new Promise(resolve => {window.resolveSave = () => resolve({success: true,
          form: {...message.form, basic: {...message.form.basic, name: "Saved name"}}, name: "Saved name"});});
      }};
    }""")
    page.locator(".edit-toggle").first.click()
    page.locator('[data-field="name"]').first.fill("First name")
    page.locator(".editor-save").click()
    page.wait_for_function('typeof resolveSave === "function"')
    page.evaluate('panel._refresh()')
    if edit_while_saving:
        page.locator('[data-field="name"]').first.fill("Newer name")
    page.evaluate('resolveSave()')
    page.wait_for_function('!panel._savingControllers.has("controller-0")')
    assert page.evaluate('panel.controllers[0].form.basic.name') == ("Newer name" if edit_while_saving else "Saved name")
    assert page.evaluate('panel._dirtyControllers.has("controller-0")') == edit_while_saving


def test_first_save_click_survives_pending_render_from_live_update(page):
    page.evaluate("""() => {
      panel.controllers[0].entry_id = "entry-1";
      panel.controllers[0].form = {basic: {name: "Hall", delay_seconds: 180}};
      window.wsCalls = [];
      panel.hass = {...panel.hass, user: {is_admin: true}, callWS: async message => {
        wsCalls.push(message); return {success: true, form: message.form};
      }};
    }""")
    page.locator(".edit-toggle").first.click()
    page.locator('[data-field="name"]').first.fill("Renamed room")
    page.evaluate('panel.hass = {...panel.hass}')
    button = page.locator(".editor-save").bounding_box()
    page.mouse.move(button["x"] + button["width"] / 2, button["y"] + button["height"] / 2)
    page.mouse.down()
    page.wait_for_timeout(50)
    page.mouse.up()
    assert page.evaluate('wsCalls.filter(call => call.type === "entity_controller/panel/save").length') == 1


def test_enabling_night_profile_reveals_valid_controls_and_keeps_duration(page):
    page.evaluate("""() => {
      panel.controllers[0].form = {basic: {name: "Hall"},
        night: {night_mode_enabled: false, night_delay_seconds: {minutes: 2, seconds: 1}}};
      panel.hass = {...panel.hass, user: {is_admin: true}};
    }""")
    page.locator(".edit-toggle").first.click()
    assert page.locator('[data-field="night_enabled"]').count() == 0
    page.locator('[data-field="night_mode_enabled"]').check()
    manual = page.locator('[data-duration-manual="night.night_delay_seconds"]')
    assert manual.input_value() == "121"
    assert page.locator('.schedule-extra .duration-control > span').inner_text() == "Nočný časovač"


def test_dragging_solar_schedule_endpoint_switches_to_fixed_time(page):
    page.evaluate(
        """() => {
          const controller = panel.controllers[0];
          controller.entry_id = "entry-1";
          controller.form = {
            basic: {name: controller.name, trigger_entities: [], control_entities: [], delay_seconds: 180},
            constraints: {constraint_enabled: true, constraint_start_source: "sunrise",
              constraint_start_offset_seconds: 900,
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
    assert save["form"]["constraints"]["constraint_start_offset_seconds"] == 0


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
          panel.style.setProperty("--card-background-color", "white");
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
    assert page.locator(".editor").evaluate("element => getComputedStyle(element).backgroundColor") == "rgba(0, 0, 0, 0)"
    assert page.locator(".editor-card").first.evaluate(
        "element => getComputedStyle(element).backgroundColor"
    ) == "rgb(255, 255, 255)"
    assert page.locator(".controller-summary").first.evaluate(
        "element => getComputedStyle(element).borderTopWidth"
    ) == "1px"
    assert page.locator(".row.editing").evaluate(
        "element => getComputedStyle(element).borderTopWidth"
    ) == "0px"
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



@pytest.mark.parametrize("width", [320, 390, 768, 1600])
def test_compact_editor_and_help_fit_panel_width(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.evaluate("""() => {
      const c = panel.controllers[0];
      c.entry_id = "entry-1";
      c.form = {
        basic: {name: c.name, trigger_entities: ["binary_sensor.motion"],
          control_entities: ["light.room"], delay_seconds: {minutes: 4}},
        timer: {sensor_resets_timer: true},
        monitoring: {state_entities: [], blocking_enabled: true},
        constraints: {constraint_enabled: true, constraint_start_source: "sunset",
          constraint_end_source: "sunrise", constraint_start_time: "18:24:00",
          constraint_end_time: "06:53:00"},
        night: {night_mode_enabled: false},
        actions: {on_enter_active: "on", on_exit_active: "off"},
        rules: {override_entities: [], interlock_entities: []},
      };
      panel.hass = {...panel.hass, user: {is_admin: true}};
    }""")
    page.locator(".edit-toggle").first.click()
    if width < 620:
        assert page.locator(".inputs-card").evaluate("""el => {
          const groups = el.querySelectorAll('.entity-card');
          const a = groups[0].getBoundingClientRect(), b = groups[1].getBoundingClientRect();
          return Math.abs(a.left - b.left) < 1 && b.top > a.bottom;
        }""")
    if width == 1600:
        assert page.locator(".editor-grid").evaluate("el => el.getBoundingClientRect().height") <= 550
    page.locator('.edit-modes button[data-mode="full"]').click()
    page.locator(".rules-card summary").click()
    page.locator(".inputs-card .add-entity").first.click()
    assert page.locator(".editor").evaluate("""el => [...el.querySelectorAll('input,select,button,section,details')]
      .filter(n => n.getBoundingClientRect().width > 0)
      .every(n => n.getBoundingClientRect().left >= 0 && n.getBoundingClientRect().right <= innerWidth + 1)""")
    help_button = page.locator(".inputs-card .field-help").first
    help_button.click()
    expect(help_button).to_have_attribute("aria-expanded", "true")
    popover = page.locator(".help-popover:popover-open")
    assert popover.is_visible()
    assert popover.evaluate("""el => {
      const r = el.getBoundingClientRect();
      return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight;
    }""")
    page.keyboard.press("Escape")
    assert page.locator(".help-popover:popover-open").count() == 0
    expect(help_button).to_have_attribute("aria-expanded", "false")
    help_button.click()
    page.evaluate("scroller.scrollTop += 100")
    expect(page.locator(".help-popover:popover-open")).to_have_count(0)
    help_button.click()
    page.set_viewport_size({"width": width + 10, "height": 900})
    expect(page.locator(".help-popover:popover-open")).to_have_count(0)


def test_mobile_help_opens_by_tap_without_changing_draft(mobile_page):
    mobile_page.evaluate("""() => {
      const c = panel.controllers[0];
      c.entry_id = "entry-1";
      c.form = {basic: {name: c.name, trigger_entities: [], control_entities: [], delay_seconds: 240}};
      panel.hass = {...panel.hass, user: {is_admin: true}};
    }""")
    mobile_page.locator(".edit-toggle").first.tap()
    mobile_page.locator(".field-help").first.tap()
    assert mobile_page.locator(".help-popover:popover-open").is_visible()
    assert mobile_page.locator(".editor-save").is_disabled()
    mobile_page.locator(".editor-heading").tap()
    assert mobile_page.locator(".help-popover:popover-open").count() == 0


def test_removing_rule_entity_keeps_rules_and_other_sections_open(page):
    page.evaluate("""() => {
      const c = panel.controllers[0];
      c.entry_id = "entry-1";
      c.form = {
        basic: {name: c.name, trigger_entities: [], control_entities: [], delay_seconds: 240},
        timer: {backoff_enabled: false, backoff_factor: 2},
        rules: {override_entities: ["light.room", "binary_sensor.motion"], interlock_entities: []},
      };
      panel.hass = {...panel.hass, user: {is_admin: true}};
    }""")
    page.locator(".edit-toggle").first.click()
    page.locator('[data-mode="full"]').click()
    page.locator(".rules-card summary").click()
    advanced = page.locator(".editor-section").filter(has_text="Adaptívne časovanie")
    advanced.locator("summary").click()
    page.locator('.rules-card [data-remove-entity][data-value="light.room"]').click()
    expect(page.locator(".rules-card")).to_have_attribute("open", "")
    expect(advanced).to_have_attribute("open", "")
    expect(page.locator('.rules-card [data-entity-id="light.room"]')).to_have_count(0)
    page.locator('.rules-card [data-remove-entity][data-value="binary_sensor.motion"]').click()
    expect(page.locator(".rules-card")).to_have_attribute("open", "")
    page.locator('[data-picker-toggle="rules.override_entities"]').click()
    page.locator('[data-entity-option="light.room"]').click()
    expect(page.locator(".rules-card")).to_have_attribute("open", "")
    expect(advanced).to_have_attribute("open", "")
    assert page.locator(".editor-save").is_enabled()
