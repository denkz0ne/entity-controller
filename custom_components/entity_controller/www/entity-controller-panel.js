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
    this._removeEvent?.();
    this._removeEvent = null;
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
      ...controller.triggers, ...controller.outputs, ...controller.constraints].filter(Boolean);
  }

  async _refresh() {
    if (this._refreshing || !this._hass) return;
    this._refreshing = true;
    try {
      const response = await this._hass.callWS({ type: DATA_COMMAND });
      this.controllers = response.controllers || [];
      this._render();
      await this._loadHistory();
    } catch (error) {
      this.error = error?.message || "Nepodarilo sa načítať ovládače.";
      this._render();
    } finally {
      this._refreshing = false;
    }
  }

  async _loadHistory() {
    if (!this._hass || !this.controllers.length) return;
    const end = new Date();
    const start = new Date(end.getTime() - WINDOW_MS);
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
    const name = state?.attributes?.friendly_name || entityId;
    const icon = state?.attributes?.icon || "mdi:circle-small";
    const value = state ? state.state : "—";
    const active = ["on", "open", "home", "playing", "active"].includes(value);
    return `<button class="chip ${active ? "is-active" : ""}" data-entity="${esc(entityId)}" title="${esc(`${name}: ${value}`)}">
      <ha-icon icon="${esc(icon)}"></ha-icon><span>${esc(name)}</span><b>${esc(value)}</b></button>`;
  }

  _timeline(controller) {
    const history = this.history.get(controller.id);
    if (history === null) return `<div class="timeline-empty">História nie je dostupná</div>`;
    if (!history?.length) return `<div class="timeline-empty">Za posledných 24 hodín bez zaznamenanej zmeny</div>`;
    const end = Date.now();
    const start = end - WINDOW_MS;
    const segments = [];
    const entries = [...history].sort((a, b) => new Date(a.last_changed) - new Date(b.last_changed));
    const firstState = entries[0];
    const firstAt = new Date(firstState.last_changed).getTime();
    if (firstAt > start) segments.push({ start, end: firstAt, state: "unknown" });
    entries.forEach((entry, index) => {
      const from = Math.max(start, new Date(entry.last_changed).getTime());
      const to = Math.min(end, index + 1 < entries.length ? new Date(entries[index + 1].last_changed).getTime() : end);
      if (to > from) segments.push({ start: from, end: to, state: entry.state });
    });
    const gradient = segments.map((segment) => {
      const color = stateColor(segment.state);
      const left = ((segment.start - start) / WINDOW_MS * 100).toFixed(3);
      const right = ((segment.end - start) / WINDOW_MS * 100).toFixed(3);
      return `var(--ec-${color}) ${left}% ${right}%`;
    }).join(", ");
    return `<div class="timeline" role="img" aria-label="Stavový priebeh za posledných 24 hodín" style="background:linear-gradient(90deg,${gradient})"></div>`;
  }

  _row(controller) {
    const stateClass = stateColor(controller.state);
    const stateEntity = this._hass?.states?.[controller.state_entity_id];
    const title = stateEntity?.attributes?.friendly_name || controller.name;
    const details = controller.block_reason || controller.last_transition_cause || controller.state.replaceAll("_", " ");
    return `<article class="row">
      <div class="identity">
        <ha-icon class="controller-icon" icon="${esc(controller.icon || "mdi:home-automation")}"></ha-icon>
        <div class="title"><strong>${esc(title)}</strong><span class="state ${stateClass}">${esc(controller.state.replaceAll("_", " "))}</span></div>
        <button class="toggle ${controller.enabled ? "on" : ""}" data-toggle="${esc(controller.enabled_entity_id || "")}" aria-label="${controller.enabled ? "Vypnúť" : "Zapnúť"} ${esc(title)}"><span></span></button>
      </div>
      <div class="chips">${controller.triggers.map((id) => this._entityChip(id)).join("")}</div>
      <div class="chips outputs">${controller.outputs.map((id) => this._entityChip(id)).join("")}</div>
      <div class="timeline-line">${this._timeline(controller)}</div>
      <div class="details">${esc(details)}${controller.expires_at ? ` · do ${esc(new Date(controller.expires_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}` : ""}</div>
    </article>`;
  }

  _render() {
    if (!this.shadowRoot) return;
    const rows = this.controllers.map((controller) => this._row(controller)).join("");
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;color:var(--primary-text-color);--ec-active:var(--success-color,#43a047);--ec-constrained:var(--info-color,#039be5);--ec-blocked:var(--error-color,#db4437);--ec-inactive:var(--disabled-text-color,#9e9e9e);font-family:var(--paper-font-body1_-_font-family,inherit)}
      .wrap{max-width:1320px;margin:0 auto;padding:24px 24px 40px}.heading{font-size:22px;font-weight:500;margin:0 0 18px}.list{display:grid;gap:12px}.row{background:var(--card-background-color);border-radius:12px;box-shadow:var(--ha-card-box-shadow,0 1px 3px #0002);padding:14px 16px;display:grid;grid-template-columns:minmax(190px, .8fr) minmax(0,1.3fr) minmax(0,1.3fr);gap:10px 16px;align-items:center}.identity{display:flex;align-items:center;gap:12px;min-width:0}.controller-icon{color:var(--primary-color);--mdc-icon-size:24px}.title{display:grid;gap:3px;min-width:0}.title strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:15px}.state{font-size:12px;text-transform:capitalize}.active{color:var(--ec-active)}.constrained{color:var(--ec-constrained)}.blocked{color:var(--ec-blocked)}.inactive{color:var(--ec-inactive)}.toggle{margin-left:auto;border:0;border-radius:16px;width:40px;height:24px;padding:3px;background:var(--disabled-text-color,#999);cursor:pointer;transition:background .15s}.toggle span{display:block;width:18px;height:18px;border-radius:50%;background:#fff;transition:transform .15s}.toggle.on{background:var(--primary-color)}.toggle.on span{transform:translateX(16px)}.chips{display:flex;gap:6px;min-width:0;overflow:hidden}.outputs{grid-column:3}.chip{display:flex;align-items:center;gap:5px;min-width:0;max-width:100%;padding:5px 8px;border:1px solid var(--divider-color);border-radius:8px;background:var(--secondary-background-color);color:var(--primary-text-color);cursor:pointer;white-space:nowrap;font:inherit;font-size:12px}.chip ha-icon{--mdc-icon-size:16px;color:var(--secondary-text-color);flex:none}.chip span{overflow:hidden;text-overflow:ellipsis}.chip b{font-weight:400;color:var(--secondary-text-color)}.chip.is-active ha-icon{color:var(--primary-color)}.timeline-line{grid-column:1/-1;padding-top:2px}.timeline{height:8px;border-radius:5px;min-width:100%;background:var(--ec-inactive)}.timeline-empty{height:8px;border-radius:5px;background:var(--ec-inactive);opacity:.35}.details{grid-column:1/-1;color:var(--secondary-text-color);font-size:12px;margin-top:-5px}.legend{display:flex;justify-content:center;gap:18px;flex-wrap:wrap;color:var(--secondary-text-color);font-size:12px;padding:20px}.legend span{display:flex;align-items:center;gap:6px}.dot{width:9px;height:9px;border-radius:50%;background:var(--ec-inactive)}.dot.active{background:var(--ec-active)}.dot.constrained{background:var(--ec-constrained)}.dot.blocked{background:var(--ec-blocked)}.empty{color:var(--secondary-text-color);text-align:center;padding:48px 16px}.error{color:var(--error-color);padding:16px}
      @media(max-width:850px){.wrap{padding:16px 12px}.row{grid-template-columns:1fr 1fr;gap:10px}.identity{grid-column:1/-1}.outputs{grid-column:2}.chips{overflow-x:auto}.timeline-line,.details{grid-column:1/-1}}
      @media(max-width:520px){.row{grid-template-columns:1fr}.chips,.outputs{grid-column:1}.chip{flex:none}.legend{gap:10px}}
    </style><main class="wrap"><h1 class="heading">Entity Controller</h1>${this.error ? `<div class="error">${esc(this.error)}</div>` : ""}<div class="list">${rows || `<div class="empty">Nie sú nakonfigurované žiadne ovládače.</div>`}</div><footer class="legend"><span><i class="dot active"></i>Aktívny</span><span><i class="dot constrained"></i>Obmedzený</span><span><i class="dot blocked"></i>Blokovaný</span><span><i class="dot"></i>Neaktívny</span></footer></main>`;
    this.shadowRoot.querySelectorAll("[data-entity]").forEach((button) => button.addEventListener("click", () => {
      this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId: button.dataset.entity } }));
    }));
    this.shadowRoot.querySelectorAll("[data-toggle]").forEach((button) => button.addEventListener("click", async () => {
      const entityId = button.dataset.toggle;
      if (!entityId) return;
      const enabled = this.controllers.find((item) => item.enabled_entity_id === entityId)?.enabled;
      await this._hass.callService("switch", enabled ? "turn_off" : "turn_on", { entity_id: entityId });
    }));
  }
}

if (!customElements.get("entity-controller-panel")) {
  customElements.define("entity-controller-panel", EntityControllerPanel);
}
