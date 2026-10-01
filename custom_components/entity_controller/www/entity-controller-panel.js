const DATA_COMMAND = "entity_controller/panel";
const HISTORY_COMMAND = "history/history_during_period";
const WINDOW_MS = 24 * 60 * 60 * 1000;
const REFRESH_MS = 5 * 60 * 1000;

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

const STATES = {
  idle: { label: "Neaktívny", color: "#aab2bd" },
  active_timer: { label: "Aktívny · časovač", color: "#28bd57" },
  active_stay_on: { label: "Aktívny · trvalý režim", color: "#00a896" },
  blocked: { label: "Blokovaný", color: "#f04452" },
  overridden: { label: "Override", color: "#9b59d0" },
  constrained: { label: "Časovo obmedzený", color: "#1686f5" },
  disabled: { label: "Vypnutý", color: "#667085" },
  unknown: { label: "Neznámy", color: "#d6dbe0" },
};

const stateKey = (state) => {
  if (["active", "active_timer"].includes(state)) return "active_timer";
  return Object.hasOwn(STATES, state) ? state : "unknown";
};

const stateColor = (state) => stateKey(state);

class EntityControllerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.controllers = [];
    this.history = new Map();
    this.historyErrors = new Map();
    this._refreshing = false;
    this._removeEvents = [];
    this._timer = null;
    this._clockTimer = null;
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
    clearInterval(this._clockTimer);
    this._timer = null;
    this._clockTimer = null;
  }

  async _start() {
    await this._refresh();
    this._watchStates();
    if (!this._timer) this._timer = setInterval(() => this._loadHistory(), REFRESH_MS);
    if (!this._clockTimer) this._clockTimer = setInterval(() => this._updateClock(), 1000);
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
        this.historyErrors.delete(controller.id);
      } catch (error) {
        this.history.set(controller.id, null);
        this.historyErrors.set(controller.id, error?.message || "História nie je dostupná.");
      }
    }));
    this._render();
  }

  _entityChip(entityId, kind) {
    const state = this._hass?.states?.[entityId];
    const name = state?.attributes?.friendly_name || entityId.split(".").pop().replaceAll("_", " ");
    const value = String(state?.state || "").toLowerCase();
    const available = value && !["unknown", "unavailable", "none"].includes(value);
    const triggerActive = kind === "trigger" &&
      ["on", "detected", "occupied", "motion", "present"].includes(value);
    const outputActive = kind === "output" &&
      ["on", "open", "playing", "active", "heat", "cool", "dry", "fan_only"].includes(value);
    const activeClass = triggerActive ? " active-trigger" : outputActive ? " active-output" :
      kind === "override" && value === "on" ? " active-override" :
      kind === "interlock" && value === "on" ? " active-interlock" : "";
    const switchToggle = entityId.startsWith("switch.");
    const stateTitle = state ? " · " + value : "";
    return '<button class="chip' + activeClass + '" data-entity="' + esc(entityId) +
      (switchToggle ? '" data-chip-toggle="' + esc(entityId) : '') +
      '" title="' + esc(name + stateTitle) + '" aria-label="' +
      esc(name + stateTitle + (switchToggle ? ", prepínač" : "")) + '">' +
      '<ha-state-icon class="chip-icon" data-entity="' + esc(entityId) + '"></ha-state-icon>' +
      '<span>' + esc(name) + '</span>' +
      (available && (triggerActive || outputActive) ? '<i class="chip-active-dot" aria-hidden="true"></i>' : '') +
      '</button>';
  }

  _refreshControllerIcons() {
    this.shadowRoot.querySelectorAll("[data-controller-icon]").forEach((icon) => {
      const iconName = icon.dataset.controllerIcon;
      if (!iconName) return;
      icon.icon = iconName;
      icon.hass = this._hass;
      const [prefix] = iconName.split(":", 2);
      if (!prefix || prefix === "mdi") return;

      let attempts = 0;
      const retryWhenPackLoads = () => {
        if (!icon.isConnected) return;
        const registered = window.customIcons?.[prefix]?.getIcon ||
          window.customIconsets?.[prefix];
        if (registered) {
          // ha-icon falls back to the legacy icon element if a custom pack
          // has not registered yet. Reassign after registration to retry it.
          icon.icon = "";
          requestAnimationFrame(() => {
            if (icon.isConnected) icon.icon = iconName;
          });
        } else if (++attempts < 60) {
          setTimeout(retryWhenPackLoads, 500);
        }
      };
      setTimeout(retryWhenPackLoads, 250);
    });
  }

  _timeline(controller) {
    const history = this.history.get(controller.id);
    const { start, end } = this._dayRange();
    const now = Date.now();
    const chartEnd = Math.min(now, end.getTime());
    const entries = [...(history || [])]
      .filter((entry) => entry?.last_changed && Number.isFinite(new Date(entry.last_changed).getTime()))
      .map((entry) => ({ state: String(entry.state), last_changed: entry.last_changed }));
    // Recorder can be disabled or return no rows. The live HA state still gives
    // us a trustworthy segment from the entity's latest state change onward.
    const live = this._hass?.states?.[controller.state_entity_id];
    if (live?.last_changed && Number.isFinite(new Date(live.last_changed).getTime()) &&
        !entries.some((entry) => entry.last_changed === live.last_changed)) {
      entries.push({ state: live.state, last_changed: live.last_changed });
    }
    entries.sort((a, b) => new Date(a.last_changed) - new Date(b.last_changed));
    const segments = [];
    if (!entries.length) {
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
    const gradient = segments.map((segment) => {
      const color = STATES[stateColor(segment.state)].color;
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
      'style="background:linear-gradient(90deg,' + (gradient || STATES.unknown.color + ' 0% 100%') + ')">' +
      ticks + '</div><div class="timeline-axis">' + labels + '</div>' +
      (this.historyErrors.has(controller.id)
        ? '<div class="timeline-error" title="' + esc(this.historyErrors.get(controller.id)) + '">História nie je dostupná</div>'
        : '') + '</div>';
  }

  _status(controller) {
    const key = stateKey(controller.state);
    const meta = STATES[key];
    const state = this._hass?.states?.[controller.state_entity_id];
    const attributes = state?.attributes || {};
    const causeLabels = {
      sensor_trigger: "Spustený pohybom",
      sensor_release: "Pohyb skončil",
      timer_expired: "Časovač skončil",
      manual_control: "Ručné ovládanie",
      override: "Override aktívny",
      constraint: "Časové okno",
      stay_mode: "Trvalý režim",
      service: "Zmena cez službu",
      configuration: "Zmena nastavení",
    };
    let detail = causeLabels[controller.last_transition_cause] || "Čaká na podmienku";
    if (key === "blocked") {
      detail = controller.block_reason || attributes.block_reason || "Blokujúca podmienka aktívna";
    } else if (key === "overridden") {
      detail = controller.overridden_by || (controller.active_overrides || []).join(", ") || "Override aktívny";
    } else if (key === "constrained") {
      detail = controller.next_transition_label || "Čaká na otvorenie časového okna";
    } else if (key === "disabled") {
      detail = "Rozhodovanie controlleru je vypnuté";
    } else if (key === "idle") {
      detail = "Čaká na spúšťač";
    }

    let label = meta.label;
    let countdownAt = null;
    if (key === "active_timer" && controller.expires_at) {
      countdownAt = controller.expires_at;
    } else if (key === "blocked" && controller.block_expires_at) {
      countdownAt = controller.block_expires_at;
    } else if (key !== "disabled") {
      countdownAt = controller.next_transition_at || null;
    }

    let countdown = "";
    if (countdownAt && key !== "disabled") {
      const seconds = Math.max(0, Math.ceil((new Date(countdownAt).getTime() - Date.now()) / 1000));
      countdown = this._formatDuration(seconds);
    }

    const changedAt = controller.last_transition_at || attributes.last_transition_at;
    return {
      label,
      countdown,
      detail,
      changedAt: changedAt
        ? new Date(changedAt).toLocaleString("sk-SK", { dateStyle: "short", timeStyle: "medium" })
        : "Zatiaľ bez zaznamenanej zmeny",
      color: key,
    };
  }

  _formatDuration(seconds) {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainder = seconds % 60;
    if (days) return days + " d " + String(hours).padStart(2, "0") + ":" +
      String(minutes).padStart(2, "0") + ":" + String(remainder).padStart(2, "0");
    if (hours) return String(hours).padStart(2, "0") + ":" +
      String(minutes).padStart(2, "0") + ":" + String(remainder).padStart(2, "0");
    return String(minutes).padStart(2, "0") + ":" + String(remainder).padStart(2, "0");
  }
  _row(controller) {
    const status = this._status(controller);
    const title = controller.name;
    const triggers = controller.triggers || [];
    const outputs = controller.outputs || [];
    const overrides = controller.overrides || [];
    const interlocks = controller.interlocks || [];
    const triggerChips = triggers.map((id) => this._entityChip(id, "trigger")).join("");
    const outputChips = outputs.map((id) => this._entityChip(id, "output")).join("");
    const blockingChips = overrides.map((id) => this._entityChip(id, "override")).join("") +
      interlocks.map((id) => this._entityChip(id, "interlock")).join("");
    const toggle = '<button class="toggle ' + (controller.enabled ? "on" : "") +
      '" data-toggle="' + esc(controller.enabled_entity_id || "") + '" aria-label="' +
      (controller.enabled ? "Vypnúť " : "Zapnúť ") + esc(title) + '"><span></span></button>';
    return '<article class="row ' + status.color + '" data-controller-id="' + esc(controller.id) + '">' +
      '<div class="identity">' +
        '<div class="controller-control"><div class="controller-avatar"><ha-icon class="controller-icon" data-controller-icon="' +
          esc(controller.icon || "mdi:home-automation") + '" icon="' +
          esc(controller.icon || "mdi:home-automation") + '"></ha-icon></div>' + toggle + '</div>' +
        '<strong class="controller-name">' + esc(title) + '</strong>' +
        '<div class="status"><div class="status-head"><div class="status-label"><i></i><b>' +
          esc(status.label) + '</b></div>' + (status.countdown
            ? '<span class="status-countdown">' + esc(status.countdown) + '</span>' : '') +
          '</div><div class="status-meta"><span class="status-detail">' + esc(status.detail) +
          '</span><small>' + esc(status.changedAt) + '</small></div></div>' +
      '</div>' +
      '<div class="chips entities">' +
        (triggerChips ? '<span class="chip-divider" role="separator" aria-label="Pohybové senzory" title="Pohybové senzory"></span>' + triggerChips : '') +
        (outputChips ? '<span class="chip-divider" role="separator" aria-label="Ovládané entity" title="Ovládané entity"></span>' + outputChips : '') +
        (blockingChips ? '<span class="chip-divider" role="separator" aria-label="Blokovacie entity" title="Blokovacie entity"></span>' + blockingChips : '') +
      '</div>' +
      '<div class="timeline-line">' + this._timeline(controller) + '</div>' +
      '</article>';
  }

  _render() {
    if (!this.shadowRoot) return;
    const styles = [
      ':host{display:block;height:100%;min-height:0;color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,inherit);touch-action:pan-y;--ec-active:#28bd57;--ec-constrained:#1686f5;--ec-blocked:#f04452;--ec-overridden:#9b59d0;--ec-disabled:#667085;--ec-inactive:#aab2bd}',
      '.wrap{box-sizing:border-box;height:100%;min-height:calc(100vh - 64px);display:flex;flex-direction:column;padding:12px 16px 8px;gap:8px}',
      '.heading{flex:none;padding:0 4px 2px}.heading h1{font-size:var(--mush-title-font-size,24px);line-height:var(--mush-title-line-height,32px);font-weight:var(--mush-title-font-weight,400);letter-spacing:var(--mush-title-letter-spacing,-.288px);color:var(--mush-title-color,var(--primary-text-color));margin:0}.heading p{font-size:var(--mush-subtitle-font-size,16px);line-height:var(--mush-subtitle-line-height,24px);font-weight:var(--mush-subtitle-font-weight,400);color:var(--mush-subtitle-color,var(--secondary-text-color));margin:0}',
      '.list{flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;display:flex;flex-direction:column;gap:8px;scrollbar-width:thin;-webkit-overflow-scrolling:touch;touch-action:pan-y;overscroll-behavior-y:contain}',
      '.row{position:relative;flex:none;box-sizing:border-box;display:grid;grid-template-columns:minmax(400px,34%) minmax(0,1fr);grid-template-rows:auto auto;align-items:start;gap:8px 10px;padding:12px 16px;background:var(--ha-card-background,var(--card-background-color));box-shadow:var(--ha-card-box-shadow,none);border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--divider-color));border-radius:var(--ha-card-border-radius,12px);min-height:88px}',
      '.row:before{content:"";position:absolute;left:-1px;top:-1px;bottom:-1px;width:4px;background:var(--ec-row-color);border-radius:15px 0 0 15px}.row.idle{--ec-row-color:#aab2bd}.row.active_timer{--ec-row-color:#28bd57}.row.active_stay_on{--ec-row-color:#00a896}.row.constrained{--ec-row-color:#1686f5}.row.blocked{--ec-row-color:#f04452}.row.overridden{--ec-row-color:#9b59d0}.row.disabled{--ec-row-color:#667085}.row.unknown{--ec-row-color:#d6dbe0}',
      '.identity{grid-column:1;grid-row:1;min-width:0;display:grid;grid-template-columns:52px minmax(0,1fr);grid-template-rows:36px auto;gap:4px 12px;align-items:start;align-self:start}',
      '.toggle{box-sizing:border-box;border:0;border-radius:14px;width:46px;height:24px;padding:3px;background:#b9bec4;cursor:pointer;touch-action:pan-y;user-select:none;-webkit-user-select:none}.toggle span{display:block;width:18px;height:18px;border-radius:50%;background:#fff;transition:transform .15s;pointer-events:none}.toggle.on{background:#1686f5}.toggle.on span{transform:translateX(22px)}',
      '.controller-control{grid-column:1;grid-row:1/3;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;gap:4px}.controller-avatar{width:36px;height:36px;flex:none;border-radius:50%;display:flex;align-items:center;justify-content:center;background:color-mix(in srgb,var(--ec-row-color) 18%,var(--ha-card-background,var(--card-background-color)));color:var(--ec-row-color)}.controller-icon{color:var(--ec-row-color);--mdc-icon-size:24px}.controller-name{grid-column:2;grid-row:1;align-self:center;min-width:0;font-size:16px;line-height:20px;font-weight:var(--mush-card-primary-font-weight,500);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
      '.status{grid-column:2;grid-row:2;min-width:0;display:flex;flex-direction:column;gap:3px;font-size:var(--mush-card-secondary-font-size,12px);color:var(--mush-card-secondary-color,var(--secondary-text-color))}.status-head{display:flex;align-items:center;gap:9px;min-width:0}.status-label{display:flex;align-items:center;gap:7px;color:var(--mush-card-primary-color,var(--primary-text-color));white-space:nowrap}.status-label b{font-size:var(--mush-card-primary-font-size,14px);font-weight:var(--mush-card-primary-font-weight,500)}.status-label i{flex:none;width:10px;height:10px;border-radius:50%;background:var(--ec-row-color)}.status-countdown{white-space:nowrap;font-variant-numeric:tabular-nums;color:var(--mush-card-primary-color,var(--primary-text-color));font-size:var(--mush-card-primary-font-size,14px);font-weight:var(--mush-card-primary-font-weight,500)}.status-meta{display:flex;align-items:baseline;justify-content:space-between;gap:8px;min-width:0}.status-detail{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.status-meta small{flex:none;white-space:nowrap;font-size:var(--mush-card-secondary-font-size,12px);color:var(--mush-card-secondary-color,var(--secondary-text-color))}',
      '.chips{grid-column:2;grid-row:1;min-width:0;display:flex;flex-wrap:wrap;align-items:flex-start;align-content:flex-start;align-self:start;gap:6px;overflow:visible;padding:0}',
      '.chip-divider{width:2px;height:20px;flex:0 0 2px;align-self:center;margin:0 3px;border-radius:2px;background:linear-gradient(180deg,transparent,var(--divider-color),transparent);opacity:.85}.chip{height:28px;box-sizing:border-box;flex:0 1 auto;min-width:70px;max-width:175px;display:flex;align-items:center;justify-content:flex-start;gap:7px;padding:0 9px;border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--divider-color));border-radius:18px;background:var(--chip-background,var(--ha-card-background,var(--card-background-color)));box-shadow:var(--chip-box-shadow,var(--ha-card-box-shadow,none));color:var(--primary-text-color);cursor:pointer;white-space:nowrap;font:inherit;font-size:12px;touch-action:pan-y;user-select:none;-webkit-user-select:none} .chip span{min-width:0;overflow:hidden;text-overflow:ellipsis;pointer-events:none}.chip-icon{--mdc-icon-size:16px;flex:none;color:var(--secondary-text-color);pointer-events:none}.chip.active-trigger{background:rgba(76,175,80,.18);border-color:#43a047;box-shadow:0 0 0 1px rgba(67,160,71,.14)}.chip.active-output{background:rgba(255,213,79,.22);border-color:#d2a500;box-shadow:0 0 0 1px rgba(210,165,0,.14)}.chip.active-override{background:rgba(156,39,176,.14);border-color:#9c27b0;box-shadow:0 0 0 1px rgba(156,39,176,.12)}.chip.active-interlock{background:rgba(3,169,244,.14);border-color:#039be5;box-shadow:0 0 0 1px rgba(3,155,229,.12)}.chip[data-chip-toggle]{cursor:pointer}.chip-active-dot{width:7px;height:7px;flex:none;border-radius:50%;background:#2e8b3c}.chip.active-output .chip-active-dot{background:#b38b00}',
      '.timeline-line{grid-column:1/-1;grid-row:2;padding-top:2px;min-width:0}.timeline-wrap{width:100%}.timeline{height:16px;position:relative;overflow:hidden;border-radius:5px;background:#d6dbe0}.tick{position:absolute;top:0;bottom:0;width:1px;background:rgba(255,255,255,.9);opacity:.8;pointer-events:none}.timeline-axis{height:16px;display:flex;justify-content:space-between;align-items:flex-start;color:var(--secondary-text-color);font-size:10px;line-height:14px;padding-top:3px}.timeline-axis span{white-space:nowrap}.timeline-error{font-size:11px;color:var(--error-color);padding-top:3px}',
      '.legend{flex:none;box-sizing:border-box;min-height:48px;padding:8px 18px;display:flex;align-items:center;justify-content:space-between;gap:15px;border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--divider-color));border-radius:var(--ha-card-border-radius,12px);background:var(--ha-card-background,var(--card-background-color));box-shadow:var(--ha-card-box-shadow,none);color:var(--primary-text-color);font-size:13px}.legend-items{display:flex;align-items:center;gap:10px 14px;flex-wrap:wrap}.legend-title{font-weight:700}.legend-items span{display:flex;align-items:center;gap:9px;white-space:nowrap}.swatch{width:22px;height:12px;flex:none;border-radius:4px;background:var(--ec-inactive)}.swatch.idle{background:#aab2bd}.swatch.active_timer{background:#28bd57}.swatch.active_stay_on{background:#00a896}.swatch.constrained{background:#1686f5}.swatch.blocked{background:#f04452}.swatch.overridden{background:#9b59d0}.swatch.disabled{background:#667085}.swatch.unknown{background:repeating-linear-gradient(135deg,#d6dbe0 0 3px,#aab2bd 3px 5px)}.count{color:var(--secondary-text-color);white-space:nowrap}',
      '.empty{color:var(--secondary-text-color);text-align:center;padding:48px 16px}.error{color:var(--error-color);padding:10px 14px}',
      '@media(max-width:1100px){.row{grid-template-columns:minmax(330px,38%) minmax(0,1fr)}.identity{grid-template-columns:48px minmax(0,1fr);grid-template-rows:34px auto;gap:4px 8px}.controller-avatar{width:32px;height:32px}.controller-icon{--mdc-icon-size:22px}.chip{min-width:66px;padding:0 8px}.legend-items{gap:14px}}',
      '@media(max-width:760px){.wrap{padding:10px}.row{grid-template-columns:1fr;grid-template-rows:auto auto;gap:7px}.identity{grid-column:1;grid-row:1;grid-template-columns:48px minmax(0,1fr);grid-template-rows:34px auto}.chips{grid-column:1;grid-row:2}.timeline-line{grid-column:1;grid-row:3}.legend{align-items:flex-start;flex-direction:column}.legend-items{gap:10px 16px}}',
      '@media(max-width:480px){.heading h1{font-size:25px}.row{padding:8px 10px 5px 15px}.identity{grid-template-columns:38px minmax(0,1fr);grid-template-rows:32px auto;gap:4px 6px}.toggle{width:36px}.toggle.on span{transform:translateX(12px)}.controller-avatar{width:30px;height:30px}.controller-icon{--mdc-icon-size:20px}.controller-name{font-size:16px}.status-label b,.status-countdown{font-size:12px}.status{font-size:11px}.status-label i{width:9px;height:9px}.status-meta small{font-size:10px}.chip{font-size:11px;height:27px;min-width:58px;padding:0 7px}.legend-items{font-size:11px;gap:9px 12px}.swatch{width:22px;height:11px}}',
    ].join("");
    const rows = this.controllers.map((controller) => this._row(controller)).join("");
    const error = this.error ? '<div class="error">' + esc(this.error) + '</div>' : "";
    this.shadowRoot.innerHTML = '<style>' + styles + '</style>' +
      '<main class="wrap"><header class="heading"><h1>Entity Controller</h1>' +
      '<p>Rýchly prehľad controllerov</p></header>' + error +
      '<section class="list">' + (rows || '<div class="empty">Nie sú nakonfigurované žiadne ovládače.</div>') +
      '</section><footer class="legend"><div class="legend-items"><span class="legend-title">Legenda časovej osi:</span>' +
      '<span><i class="swatch idle"></i>Neaktívny</span><span><i class="swatch active_timer"></i>Aktívny · časovač</span>' +
      '<span><i class="swatch active_stay_on"></i>Aktívny · trvalý režim</span><span><i class="swatch blocked"></i>Blokovaný</span>' +
      '<span><i class="swatch overridden"></i>Override</span><span><i class="swatch constrained"></i>Časovo obmedzený</span>' +
      '<span><i class="swatch disabled"></i>Vypnutý</span><span><i class="swatch unknown"></i>Neznámy</span>' +
      '</div><span class="count"></span></footer></main>';

    this._refreshControllerIcons();
    this.shadowRoot.querySelectorAll("ha-state-icon[data-entity]").forEach((icon) => {
      icon.hass = this._hass;
      icon.stateObj = this._hass?.states?.[icon.dataset.entity];
    });
    this.shadowRoot.querySelectorAll(".chip[data-entity]").forEach((button) => button.addEventListener("click", async () => {
      const entityId = button.dataset.entity;
      if (button.dataset.chipToggle) {
        const value = String(this._hass?.states?.[entityId]?.state || "").toLowerCase();
        await this._hass.callService("switch", value === "on" ? "turn_off" : "turn_on", { entity_id: entityId });
        return;
      }
      this.dispatchEvent(new CustomEvent("hass-more-info", {
        bubbles: true, composed: true, detail: { entityId },
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

  _updateClock() {
    this.controllers.forEach((controller) => {
      if (!["active_timer", "active_stay_on", "blocked"].includes(controller.state) && !controller.next_transition_at) return;
      const row = [...(this.shadowRoot?.querySelectorAll(".row") || [])]
        .find((item) => item.dataset.controllerId === controller.id);
      const status = this._status(controller);
      const label = row?.querySelector(".status-label b");
      const countdown = row?.querySelector(".status-countdown");
      if (label) label.textContent = status.label;
      if (countdown) countdown.textContent = status.countdown;
    });
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
