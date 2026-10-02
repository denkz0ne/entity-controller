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
