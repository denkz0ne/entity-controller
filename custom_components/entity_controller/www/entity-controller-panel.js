const DATA_COMMAND = "entity_controller/panel";
const HISTORY_COMMAND = "history/history_during_period";
const WINDOW_MS = 24 * 60 * 60 * 1000;
const REFRESH_MS = 5 * 60 * 1000;

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

const stateColor = (state) => {
  if (["active_timer", "active_stay_on", "active"].includes(state)) return "active";
  if (state === "constrained") return "constrained";
  if (state === "blocked") return "blocked";
  return "inactive";
};

class EntityControllerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.controllers = [];
    this.history = new Map();
    this._refreshing = false;
    this._removeEvents = [];
    this._timer = null;
  }

  set hass(hass) {
    const previous = this._hass;
    this._hass = hass;
    if (hass && !previous) this._start();
    if (hass && previous && hass.connection !== previous.connection) this._watchStates();
    this._render();
  }

  get hass() { return this._hass; }

  connectedCallback() {
    if (this._hass) this._start();
  }

  disconnectedCallback() {
    this._removeEvents.forEach((remove) => remove());
    this._removeEvents = [];
    clearInterval(this._timer);
    this._timer = null;
  }

  async _start() {
    await this._refresh();
    this._watchStates();
    if (!this._timer) this._timer = setInterval(() => this._loadHistory(), REFRESH_MS);
  }

  async _watchStates() {
    this._removeEvents.forEach((remove) => remove());
    this._removeEvents = [];
    if (!this._hass?.connection?.subscribeEvents) return;
    const connection = this._hass.connection;
    const removeStateEvents = await connection.subscribeEvents((event) => {
      const changed = event.data?.entity_id;
      if (!changed) return;
      if (this.controllers.some((item) => this._allEntities(item).includes(changed))) {
        this._refresh();
      }
    }, "state_changed");
    const removeRegistryEvents = await connection.subscribeEvents(() => this._refresh(), "entity_registry_updated");
    if (!this.isConnected || this._hass?.connection !== connection) {
      removeStateEvents();
      removeRegistryEvents();
    } else this._removeEvents = [removeStateEvents, removeRegistryEvents];
  }

  _allEntities(controller) {
    return [controller.state_entity_id, controller.enabled_entity_id,
      ...(controller.inputs || controller.triggers || []), ...controller.outputs].filter(Boolean);
  }

  async _refresh() {
    if (this._refreshing || !this._hass) return;
    this._refreshing = true;
    try {
      const response = await this._hass.callWS({ type: DATA_COMMAND });
      this.controllers = response.controllers || [];
      this.error = null;
      this._render();
      await this._loadHistory();
    } catch (error) {
      this.error = error?.message || "Nepodarilo sa načítať ovládače.";
      this._render();
    } finally {
      this._refreshing = false;
    }
  }

  _dayRange() {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    return { start, end: new Date(start.getTime() + WINDOW_MS) };
  }

  async _loadHistory() {
    if (!this._hass || !this.controllers.length) return;
    const { start, end } = this._dayRange();
    await Promise.all(this.controllers.map(async (controller) => {
      if (!controller.state_entity_id) return;
      try {
        const result = await this._hass.callWS({
          type: HISTORY_COMMAND,
          start_time: start.toISOString(),
          end_time: end.toISOString(),
          entity_ids: [controller.state_entity_id],
          minimal_response: true,
          no_attributes: true,
        });
        this.history.set(controller.id, result?.[0] || []);
      } catch (_error) {
        this.history.set(controller.id, null);
      }
    }));
    this._render();
  }

  _entityChip(entityId) {
    const state = this._hass?.states?.[entityId];
    const name = state?.attributes?.friendly_name || entityId.split(".").pop().replaceAll("_", " ");
    return '<button class="chip" data-entity="' + esc(entityId) + '" title="' + esc(name) + '">' +
      '<ha-state-icon class="chip-icon" data-entity="' + esc(entityId) + '"></ha-state-icon>' +
      '<span>' + esc(name) + '</span></button>';
  }

  _timeline(controller) {
    const history = this.history.get(controller.id);
    const { start, end } = this._dayRange();
    const now = Date.now();
    const chartEnd = Math.min(now, end.getTime());
    const entries = [...(history || [])].sort((a, b) =>
      new Date(a.last_changed) - new Date(b.last_changed));
    const segments = [];
    if (!history?.length) {
      segments.push({ start: start.getTime(), end: end.getTime(), state: "unknown" });
    } else {
      const firstAt = new Date(entries[0].last_changed).getTime();
      if (firstAt > start.getTime()) {
        segments.push({ start: start.getTime(), end: Math.min(firstAt, chartEnd), state: "unknown" });
      }
      entries.forEach((entry, index) => {
        const from = Math.max(start.getTime(), new Date(entry.last_changed).getTime());
        const nextAt = index + 1 < entries.length
          ? new Date(entries[index + 1].last_changed).getTime()
          : chartEnd;
        const to = Math.min(chartEnd, nextAt);
        if (to > from) segments.push({ start: from, end: to, state: entry.state });
      });
      if (chartEnd < end.getTime()) {
        segments.push({ start: chartEnd, end: end.getTime(), state: "unknown" });
      }
    }
    const colors = { active: "#28bd57", constrained: "#1686f5", blocked: "#ff3030", inactive: "#d6dbe0" };
    const gradient = segments.map((segment) => {
      const color = colors[stateColor(segment.state)] || colors.inactive;
      const left = ((segment.start - start.getTime()) / WINDOW_MS * 100).toFixed(3);
      const right = ((segment.end - start.getTime()) / WINDOW_MS * 100).toFixed(3);
      return color + " " + left + "% " + right + "%";
    }).join(", ");
    const ticks = Array.from({ length: 13 }, (_, index) => {
      const position = index * 100 / 12;
      return '<i class="tick" style="left:' + position + '%"></i>';
    }).join("");
    const labels = Array.from({ length: 13 }, (_, index) => {
      const label = String(index * 2).padStart(2, "0") + ":00";
      return '<span>' + label + '</span>';
    }).join("");
    return '<div class="timeline-wrap"><div class="timeline" role="img" aria-label="Stavový priebeh počas dňa" ' +
      'style="background:linear-gradient(90deg,' + (gradient || colors.inactive + ' 0% 100%') + ')">' +
      ticks + '</div><div class="timeline-axis">' + labels + '</div></div>';
  }

  _status(controller) {
    const state = controller.state;
    const active = ["active_timer", "active_stay_on"].includes(state);
    let label = "Neaktívny";
    let detail = controller.last_transition_cause || "Čaká na spúšťač";
    if (active) {
      label = "Aktívny";
      const started = controller.last_triggered_at || controller.last_transition_at;
      if (started) {
        const seconds = Math.max(0, Math.floor((Date.now() - new Date(started).getTime()) / 1000));
        label += " · " + String(Math.floor(seconds / 60)).padStart(2, "0") +
          ":" + String(seconds % 60).padStart(2, "0");
      }
      detail = controller.last_transition_cause === "trigger_on"
        ? "Spustený pohybom" : "Ovládač je aktívny";
    } else if (state === "constrained") {
      label = "Obmedzený";
      if (controller.expires_at) {
        label += " · do " + new Date(controller.expires_at).toLocaleTimeString([], {
          hour: "2-digit", minute: "2-digit",
        });
      }
      detail = "Časové obmedzenie";
    } else if (state === "blocked") {
      label = "Blokovaný";
      detail = controller.block_reason || "Podmienky nie sú splnené";
    } else if (state === "disabled" || !controller.enabled) {
      label = "Vypnutý";
      detail = "Manuálne vypnutý";
    }
    return { label, detail, color: stateColor(state) };
  }

  _row(controller) {
    const status = this._status(controller);
    const title = controller.name;
    const inputs = controller.inputs || controller.triggers || [];
    return '<article class="row ' + status.color + '">' +
      '<div class="identity">' +
        '<button class="toggle ' + (controller.enabled ? "on" : "") + '" data-toggle="' +
          esc(controller.enabled_entity_id || "") + '" aria-label="' +
          (controller.enabled ? "Vypnúť " : "Zapnúť ") + esc(title) + '"><span></span></button>' +
        '<ha-icon class="controller-icon" icon="' + esc(controller.icon || "mdi:home-automation") + '"></ha-icon>' +
        '<strong class="controller-name">' + esc(title) + '</strong>' +
        '<div class="status"><div class="status-label"><i></i><b>' + esc(status.label) +
          '</b></div><span>' + esc(status.detail) + '</span></div>' +
      '</div>' +
      '<div class="chips inputs">' + inputs.map((id) => this._entityChip(id)).join("") + '</div>' +
      '<div class="chips outputs">' + controller.outputs.map((id) => this._entityChip(id)).join("") + '</div>' +
      '<div class="timeline-line">' + this._timeline(controller) + '</div>' +
      '</article>';
  }

  _render() {
    if (!this.shadowRoot) return;
    const styles = [
      ':host{display:block;height:100%;min-height:0;color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,inherit);--ec-active:#28bd57;--ec-constrained:#1686f5;--ec-blocked:#ff3030;--ec-inactive:#d6dbe0}',
      '.wrap{box-sizing:border-box;height:100%;min-height:calc(100vh - 64px);display:flex;flex-direction:column;padding:12px 16px 8px;gap:8px}',
      '.heading{flex:none;padding:0 4px 2px}.heading h1{font-size:30px;line-height:1.05;font-weight:700;margin:0}.heading p{font-size:16px;color:var(--secondary-text-color);margin:2px 0 0}',
      '.list{flex:1;min-height:0;overflow:auto;display:flex;flex-direction:column;gap:8px;scrollbar-width:thin}',
      '.row{position:relative;flex:none;box-sizing:border-box;display:grid;grid-template-columns:minmax(400px,34%) minmax(0,1fr);grid-template-rows:auto auto auto;align-items:center;gap:5px 10px;padding:7px 18px 5px 20px;background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:15px;min-height:88px}',
      '.row:before{content:"";position:absolute;left:-1px;top:-1px;bottom:-1px;width:4px;background:var(--ec-row-color);border-radius:15px 0 0 15px}.row.active{--ec-row-color:var(--ec-active)}.row.constrained{--ec-row-color:var(--ec-constrained)}.row.blocked{--ec-row-color:var(--ec-blocked)}.row.inactive{--ec-row-color:#8b949e}',
      '.identity{grid-column:1;grid-row:1/3;min-width:0;display:grid;grid-template-columns:48px 42px minmax(78px,1fr) minmax(145px,1.25fr);gap:11px;align-items:center}',
      '.toggle{box-sizing:border-box;border:0;border-radius:14px;width:46px;height:24px;padding:3px;background:#b9bec4;cursor:pointer}.toggle span{display:block;width:18px;height:18px;border-radius:50%;background:#fff;transition:transform .15s}.toggle.on{background:#1686f5}.toggle.on span{transform:translateX(22px)}',
      '.controller-icon{color:var(--secondary-text-color);--mdc-icon-size:38px}.controller-name{font-size:19px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
      '.status{min-width:0;display:flex;flex-direction:column;gap:5px;font-size:13px;color:var(--secondary-text-color)}.status-label{display:flex;align-items:center;gap:9px;color:var(--primary-text-color);white-space:nowrap}.status-label b{font-size:14px}.status-label i{flex:none;width:12px;height:12px;border-radius:50%;background:var(--ec-row-color)}.status>span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-left:21px}',
      '.chips{grid-column:2;min-width:0;display:flex;flex-wrap:nowrap;align-items:center;gap:7px;overflow-x:auto;overflow-y:hidden;scrollbar-width:none;padding:1px 0}.chips::-webkit-scrollbar{display:none}.inputs{grid-row:1}.outputs{grid-row:2}',
      '.chip{height:32px;box-sizing:border-box;flex:0 1 auto;min-width:95px;max-width:190px;display:flex;align-items:center;justify-content:flex-start;gap:9px;padding:0 13px;border:0;border-radius:18px;background:#f0f2f4;color:var(--primary-text-color);cursor:pointer;white-space:nowrap;font:inherit;font-size:13px}.chip span{min-width:0;overflow:hidden;text-overflow:ellipsis}.chip-icon{--mdc-icon-size:18px;flex:none;color:var(--secondary-text-color)}',
      '.timeline-line{grid-column:1/-1;grid-row:3;padding-top:1px;min-width:0}.timeline-wrap{width:100%}.timeline{height:14px;position:relative;overflow:hidden;border-radius:4px;background:#d6dbe0}.tick{position:absolute;top:0;bottom:0;width:1px;background:#fff;opacity:.72}.timeline-axis{height:16px;display:flex;justify-content:space-between;align-items:flex-start;color:#66717d;font-size:11px;line-height:14px;padding-top:3px}.timeline-axis span{white-space:nowrap}.timeline-axis span:first-child{transform:none}.timeline-axis span:last-child{transform:translateX(0)}',
      '.legend{flex:none;box-sizing:border-box;min-height:48px;padding:8px 18px;display:flex;align-items:center;justify-content:space-between;gap:15px;border:1px solid #cce8f4;border-radius:12px;background:#eaf7fc;color:var(--primary-text-color);font-size:13px}.legend-items{display:flex;align-items:center;gap:28px;flex-wrap:wrap}.legend-title{font-weight:700}.legend-items span{display:flex;align-items:center;gap:9px;white-space:nowrap}.swatch{width:29px;height:13px;border-radius:3px;background:var(--ec-inactive)}.swatch.active{background:var(--ec-active)}.swatch.constrained{background:var(--ec-constrained)}.swatch.blocked{background:var(--ec-blocked)}.count{color:var(--secondary-text-color);white-space:nowrap}',
      '.empty{color:var(--secondary-text-color);text-align:center;padding:48px 16px}.error{color:var(--error-color);padding:10px 14px}',
      '@media(max-width:1100px){.row{grid-template-columns:minmax(310px,38%) minmax(0,1fr)}.identity{grid-template-columns:44px 36px minmax(72px,1fr) minmax(115px,1.15fr);gap:7px}.controller-icon{--mdc-icon-size:32px}.chip{min-width:82px;padding:0 9px}.legend-items{gap:14px}}',
      '@media(max-width:760px){.wrap{padding:10px}.row{grid-template-columns:1fr;grid-template-rows:auto auto auto auto;gap:5px}.identity{grid-column:1;grid-row:1;grid-template-columns:44px 38px minmax(80px,1fr) minmax(120px,1.2fr)}.chips{grid-column:1}.inputs{grid-row:2}.outputs{grid-row:3}.timeline-line{grid-column:1;grid-row:4}.legend{align-items:flex-start;flex-direction:column}.legend-items{gap:10px 16px}}',
      '@media(max-width:480px){.heading h1{font-size:25px}.row{padding:8px 10px 5px 15px}.identity{grid-template-columns:38px 30px minmax(60px,.8fr) minmax(105px,1.2fr);gap:5px}.toggle{width:36px}.toggle.on span{transform:translateX(12px)}.controller-icon{--mdc-icon-size:27px}.controller-name{font-size:16px}.status-label b{font-size:12px}.status{font-size:11px}.status-label i{width:9px;height:9px}.chip{font-size:12px;height:29px}.legend-items{font-size:11px;gap:9px 12px}.swatch{width:22px;height:11px}}',
    ].join("");
    const rows = this.controllers.map((controller) => this._row(controller)).join("");
    const error = this.error ? '<div class="error">' + esc(this.error) + '</div>' : "";
    this.shadowRoot.innerHTML = '<style>' + styles + '</style>' +
      '<main class="wrap"><header class="heading"><h1>Entity Controller</h1>' +
      '<p>Rýchly prehľad controllerov</p></header>' + error +
      '<section class="list">' + (rows || '<div class="empty">Nie sú nakonfigurované žiadne ovládače.</div>') +
      '</section><footer class="legend"><div class="legend-items"><span class="legend-title">Legenda časovej osi:</span>' +
      '<span><i class="swatch active"></i>Aktívny</span><span><i class="swatch constrained"></i>Obmedzený (čas)</span>' +
      '<span><i class="swatch blocked"></i>Blokovaný (podmienky)</span><span><i class="swatch"></i>Neaktívny</span>' +
      '</div><span class="count"></span></footer></main>';

    this.shadowRoot.querySelectorAll("ha-state-icon[data-entity]").forEach((icon) => {
      icon.hass = this._hass;
      icon.stateObj = this._hass?.states?.[icon.dataset.entity];
    });
    this.shadowRoot.querySelectorAll("[data-entity]").forEach((button) => button.addEventListener("click", () => {
      this.dispatchEvent(new CustomEvent("hass-more-info", {
        bubbles: true, composed: true, detail: { entityId: button.dataset.entity },
      }));
    }));
    this.shadowRoot.querySelectorAll("[data-toggle]").forEach((button) => button.addEventListener("click", async () => {
      const entityId = button.dataset.toggle;
      if (!entityId) return;
      const enabled = this.controllers.find((item) => item.enabled_entity_id === entityId)?.enabled;
      await this._hass.callService("switch", enabled ? "turn_off" : "turn_on", { entity_id: entityId });
    }));
    const list = this.shadowRoot.querySelector(".list");
    list.addEventListener("scroll", () => this._updateVisibleCount(), { passive: true });
    requestAnimationFrame(() => this._updateVisibleCount());
  }

  _updateVisibleCount() {
    const list = this.shadowRoot?.querySelector(".list");
    const counter = this.shadowRoot?.querySelector(".count");
    if (!list || !counter) return;
    const bounds = list.getBoundingClientRect();
    const visible = [...list.querySelectorAll(".row")].filter((row) => {
      const rect = row.getBoundingClientRect();
      return rect.bottom > bounds.top && rect.top < bounds.bottom;
    }).length;
    counter.textContent = "Zobrazených " + visible + " z " +
      this.controllers.length + " controllerov";
  }
}

if (!customElements.get("entity-controller-panel")) {
  customElements.define("entity-controller-panel", EntityControllerPanel);
}
