const DATA_COMMAND = "entity_controller/panel";
const SAVE_COMMAND = "entity_controller/panel/save";
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
const durationSeconds = (value) => {
  if (typeof value === "number") return value;
  if (!value || typeof value !== "object") return Number(value) || 0;
  return (Number(value.days || 0) * 86400) + (Number(value.hours || 0) * 3600) +
    (Number(value.minutes || 0) * 60) + Number(value.seconds || 0);
};
const FIELD_LABELS = {
  name: "Názov", icon: "Ikona", trigger_entities: "Spúšťacie entity",
  control_entities: "Ovládané entity", delay_seconds: "Doba aktivity",
  sensor_type: "Typ spúšťača", sensor_resets_timer: "Opakovaný spúšťač obnoví časovač",
  backoff_enabled: "Postupne predlžovať opakovanie", backoff_factor: "Faktor predĺženia",
  backoff_max_seconds: "Najdlhšie predĺženie", state_entities: "Sledované entity",
  blocking_enabled: "Povoliť blokovanie", block_timeout_seconds: "Automatické odblokovanie po",
  override_entities: "Override entity", interlock_entities: "Interlock entity",
  constraint_enabled: "Povoliť časové okno", night_mode_enabled: "Povoliť nočný režim",
  night_delay_seconds: "Nočný čas aktivity", service_data_on: "Parametre pri zapnutí",
  service_data_off: "Parametre pri vypnutí", night_service_data_on: "Nočné parametre pri zapnutí",
  night_service_data_off: "Nočné parametre pri vypnutí", enabled_default: "Počiatočne povolený",
  stay_mode_default: "Počiatočný trvalý režim", trigger_on_states: "Spúšťací stavy · aktívny",
  trigger_off_states: "Spúšťacie stavy · neaktívny", state_on_states: "Sledované stavy · aktívny",
  state_off_states: "Sledované stavy · neaktívny", override_on_states: "Override stavy · aktívny",
  override_off_states: "Override stavy · neaktívny", state_attributes_ignore: "Ignorované atribúty",
  constraint_start_source: "Začiatok podľa", constraint_end_source: "Koniec podľa",
  night_start_source: "Začiatok noci podľa", night_end_source: "Koniec noci podľa",
  constraint_start_time: "Začiatok okna", constraint_end_time: "Koniec okna",
  night_start_time: "Začiatok noci", night_end_time: "Koniec noci",
  constraint_start_offset_seconds: "Posun začiatku v sekundách",
  constraint_end_offset_seconds: "Posun konca v sekundách",
  night_start_offset_seconds: "Posun začiatku v sekundách",
  night_end_offset_seconds: "Posun konca v sekundách",
  on_enter_idle: "Pri skončení aktivity", on_exit_idle: "Pri obnovení z neaktivity",
  on_enter_active: "Pri aktivácii", on_exit_active: "Po skončení aktivity",
  on_enter_overridden: "Pri prevzatí override", on_exit_overridden: "Po skončení override",
  on_enter_constrained: "Pri zatvorení časového okna", on_exit_constrained: "Pri otvorení časového okna",
  on_enter_blocked: "Pri zablokovaní", on_exit_blocked: "Po odblokovaní",
};

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
    this._rowMarkup = new Map();
    this._touching = false;
    this._renderPending = false;
    this._editing = null;
    this._pickerOpen = null;
    this._saveTimers = new Map();
    this._saveQueues = new Map();
    this._failedSaves = new Map();
    this._editorRenderPending = false;
    this._touchStartHandler = () => { this._touching = true; };
    this._touchEndHandler = (event) => {
      if (!this._touching || event.touches.length) return;
      this._touching = false;
      if (this._renderPending) {
        this._renderPending = false;
        requestAnimationFrame(() => this._render());
      }
    };
    this.shadowRoot.addEventListener("click", (event) => this._handleClick(event));
    this.shadowRoot.addEventListener("change", (event) => this._handleEditorChange(event));
    this.shadowRoot.addEventListener("input", (event) => this._handleEditorInput(event));
    this.shadowRoot.addEventListener("focusout", (event) => {
      if (event.target.matches?.(".editor [data-field]") && this._editorRenderPending) {
        setTimeout(() => this._render(), 0);
      }
    });
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
    this.addEventListener("touchstart", this._touchStartHandler, { passive: true });
    window.addEventListener("touchend", this._touchEndHandler, { capture: true, passive: true });
    window.addEventListener("touchcancel", this._touchEndHandler, { capture: true, passive: true });
    if (this._hass) this._start();
  }

  disconnectedCallback() {
    this.removeEventListener("touchstart", this._touchStartHandler);
    window.removeEventListener("touchend", this._touchEndHandler, { capture: true });
    window.removeEventListener("touchcancel", this._touchEndHandler, { capture: true });
    this._touching = false;
    this._renderPending = false;
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
    const end = new Date();
    return { start: new Date(end.getTime() - WINDOW_MS), end };
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
          minimal_response: false,
          no_attributes: true,
        });
        const records = Array.isArray(result) ? result[0] : result?.states;
        this.history.set(controller.id, Array.isArray(records) ? records : []);
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
    const available = Boolean(value && !["unknown", "unavailable", "none"].includes(value));
    const triggerActive = kind === "trigger" &&
      ["on", "detected", "occupied", "motion", "present"].includes(value);
    const outputActive = kind === "output" &&
      ["on", "open", "playing", "active", "heat", "cool", "dry", "fan_only"].includes(value);
    const activeClass = triggerActive ? " active-trigger" : outputActive ? " active-output" :
      kind === "override" && value === "on" ? " active-override" :
      kind === "interlock" && value === "on" ? " active-interlock" : "";
    const invalidClass = available ? "" : " unavailable";
    const domain = entityId.split(".", 1)[0];
    const toggleDomain = available && ["switch", "input_boolean", "light"].includes(domain) ? domain : "";
    const switchToggle = Boolean(toggleDomain);
    const stateTitle = state ? " · " + value : " · nedostupná";
    return '<button class="chip' + activeClass + invalidClass + '" data-entity="' + esc(entityId) +
      (switchToggle ? '" data-chip-toggle="' + esc(toggleDomain) : '') +
      '" title="' + esc(name + stateTitle) + '" aria-label="' +
      esc(name + stateTitle + (switchToggle ? ", prepínač" : "")) + '">' +
      '<ha-state-icon class="chip-icon" data-entity="' + esc(entityId) + '"></ha-state-icon>' +
      '<span class="chip-label">' + esc(name) + '</span>' +
      (switchToggle ? '<span class="chip-switch' + (value === "on" ? " is-on" : "") +
        '" aria-hidden="true"><i></i></span>' : '') +
      (available && (triggerActive || outputActive) ? '<i class="chip-active-dot" aria-hidden="true"></i>' : '') +
      '</button>';
  }

  _refreshControllerIcons(root = this.shadowRoot) {
    root.querySelectorAll("[data-controller-icon]").forEach((icon) => {
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
    const chartEnd = end.getTime();
    const entries = [...(history || [])]
      .filter((entry) => entry?.last_changed && Number.isFinite(new Date(entry.last_changed).getTime()))
      .map((entry) => ({ state: String(entry.state), last_changed: entry.last_changed }));
    // The timeline is built only from Recorder history so an HA restart does
    // not invent a segment from the current live state.
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
      const offset = (index - 12) * 2;
      const label = offset === 0 ? "0" : offset + "h";
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
    if (key === "active_timer") {
      const derivedExpiry = controller.last_triggered_at &&
        Number.isFinite(Number(controller.effective_delay_seconds))
        ? new Date(new Date(controller.last_triggered_at).getTime() +
          Number(controller.effective_delay_seconds) * 1000).toISOString()
        : null;
      countdownAt = controller.expires_at || derivedExpiry;
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
    const chipDivider = '<span class="chip-separator" aria-hidden="true">·</span>';
    const groupedChips = [triggerChips, outputChips, blockingChips].filter(Boolean).join(chipDivider);
    const toggle = '<button class="toggle ' + (controller.enabled ? "on" : "") +
      '" data-toggle="' + esc(controller.enabled_entity_id || "") + '" aria-label="' +
      (controller.enabled ? "Vypnúť " : "Zapnúť ") + esc(title) + '"><span></span></button>';
    const editButton = this._hass?.user?.is_admin
      ? '<button class="edit-toggle" data-edit="' + esc(controller.id) + '" aria-expanded="' +
        (this._editing?.id === controller.id) + '" title="Upraviť nastavenia">' +
        (this._editing?.id === controller.id ? 'Zavrieť' : '<ha-icon icon="mdi:cog-outline"></ha-icon>') + '</button>' : '';
    return '<article class="row ' + status.color + (this._editing?.id === controller.id ? ' editing' : '') +
      '" data-controller-id="' + esc(controller.id) + '">' +
      '<div class="identity">' +
        '<div class="controller-control"><div class="controller-avatar"><ha-icon class="controller-icon" data-controller-icon="' +
          esc(controller.icon || "mdi:home-automation") + '" icon="' +
          esc(controller.icon || "mdi:home-automation") + '"></ha-icon></div>' + toggle + '</div>' +
        '<strong class="controller-name">' + esc(title) + '</strong>' + editButton +
        '<div class="status"><div class="status-head"><div class="status-label"><i></i><b>' +
          esc(status.label) + '</b></div>' + (status.countdown
            ? '<span class="status-countdown">' + esc(status.countdown) + '</span>' : '') +
          '</div><div class="status-meta"><span class="status-detail">' + esc(status.detail) +
          '</span><small>' + esc(status.changedAt) + '</small></div></div>' +
      '</div>' +
      '<div class="chips entities">' + groupedChips + '</div>' +
      '<div class="timeline-line">' + this._timeline(controller) + '</div>' +
      (this._editing?.id === controller.id ? this._editor(controller) : '') +
      '</article>';
  }

  _editor(controller) {
    const form = structuredClone(controller.form || {});
    const mode = this._editing?.mode || "basic";
    const basic = form.basic || {};
    const timer = form.timer || {};
    const monitoring = form.monitoring || {};
    const rules = form.rules || {};
    const constraints = form.constraints || {};
    const night = form.night || {};
    const actions = form.actions || {};
    const selectedEntity = (entityId, key) => {
      const state = this._hass?.states?.[entityId];
      const name = state?.attributes?.friendly_name || entityId;
      return '<span class="selected-entity" data-entity-id="' + esc(entityId) + '">' +
        '<ha-state-icon data-entity="' + esc(entityId) + '"></ha-state-icon>' +
        '<span class="selected-entity-name" title="' + esc(entityId) + '">' + esc(name) + '</span>' +
        '<button type="button" class="remove-entity" data-remove-entity="' + esc(key) + '"' +
        ' data-section="' + esc(key.split(".")[0]) + '" data-field="' + esc(key.split(".")[1]) + '"' +
        ' data-value="' + esc(entityId) + '" aria-label="Odstrániť ' + esc(name) + '">×</button></span>';
    };
    const entityPicker = (section, key, title, hint, domains, extraMarkup = "") => {
      const pickerKey = section + "." + key;
      const entities = Array.isArray(form[section]?.[key]) ? form[section][key] : [];
      const isOpen = this._pickerOpen === pickerKey;
      const states = this._hass?.states || {};
      const options = Object.keys(states).filter((entityId) => {
        const domain = entityId.split(".")[0];
        return !domains?.length || domains.includes(domain);
      }).filter((entityId) => !entities.includes(entityId)).sort((left, right) => {
        const leftName = states[left]?.attributes?.friendly_name || left;
        const rightName = states[right]?.attributes?.friendly_name || right;
        return leftName.localeCompare(rightName);
      });
      const chips = entities.length
        ? '<div class="selected-entities">' + entities.map((id) => selectedEntity(id, pickerKey)).join("") + '</div>'
        : '<p class="empty-selection">Zatiaľ nie je vybraná žiadna entita.</p>';
      const picker = isOpen
        ? '<div class="entity-picker"><input class="entity-search" type="search" autocomplete="off"' +
          ' data-entity-search="' + esc(pickerKey) + '" placeholder="Hľadať podľa názvu alebo entity ID"' +
          ' aria-label="Hľadať entity pre ' + esc(title) + '">' +
          '<div class="entity-options" role="listbox">' + (options.length ? options.map((id) => {
            const name = states[id]?.attributes?.friendly_name || id;
            return '<button type="button" class="entity-option" data-entity-option="' + esc(id) + '"' +
              ' data-picker="' + esc(pickerKey) + '" data-section="' + esc(section) + '"' +
              ' data-field="' + esc(key) + '" data-value="' + esc(id) + '" role="option">' +
              '<ha-state-icon data-entity="' + esc(id) + '"></ha-state-icon><span>' + esc(name) +
              '</span><small>' + esc(id) + '</small></button>';
          }).join("") : '<p class="empty-selection">Nenašli sa žiadne dostupné entity.</p>') + '</div></div>' : '';
      return '<section class="editor-card entity-card"><div class="card-heading"><div class="card-heading-icon"><ha-icon icon="mdi:home-import-outline"></ha-icon></div>' +
        '<div class="card-heading-copy"><h3>' + esc(title) +
        '</h3><p>' + esc(hint) + '</p></div></div>' + chips + extraMarkup +
        '<button type="button" class="add-entity" data-picker-toggle="' + esc(pickerKey) + '" aria-expanded="' +
        Boolean(isOpen) + '"><ha-icon icon="mdi:plus"></ha-icon> Pridať entitu</button>' + picker + '</section>';
    };
    const timeMinutes = (value, fallback) => {
      const [hours, minutes] = String(value || fallback).split(":").map(Number);
      return Math.max(0, Math.min(1439, (hours || 0) * 60 + (minutes || 0)));
    };
    const timeText = (minutes) => String(Math.floor(minutes / 60)).padStart(2, "0") + ":" +
      String(minutes % 60).padStart(2, "0");
    const schedule = (section, title, prefix, enabled, startDefault, endDefault) => {
      const startKey = prefix + "_start_time";
      const endKey = prefix + "_end_time";
      const startSourceKey = prefix + "_start_source";
      const endSourceKey = prefix + "_end_source";
      const start = timeMinutes(form[section]?.[startKey], startDefault);
      const end = timeMinutes(form[section]?.[endKey], endDefault);
      const startSource = form[section]?.[startSourceKey] || (prefix === "night" ? "sunset" : "fixed");
      const endSource = form[section]?.[endSourceKey] || (prefix === "night" ? "sunrise" : "fixed");
      const left = Math.min(start, end) / 1439 * 100;
      const right = Math.max(start, end) / 1439 * 100;
      const scheduleStyle = start <= end
        ? 'linear-gradient(to right, transparent 0%, transparent ' + left + '%, var(--primary-color) ' + left +
          '%, var(--primary-color) ' + right + '%, transparent ' + right + '%, transparent 100%)'
        : 'linear-gradient(to right, var(--primary-color) 0%, var(--primary-color) ' + right +
          '%, transparent ' + right + '%, transparent ' + left + '%, var(--primary-color) ' + left + '%, var(--primary-color) 100%)';
      const endpoint = (side, sideLabel, value, source, fieldKey, sourceKey) =>
        '<label class="schedule-endpoint"><span>' + esc(sideLabel) + '</span><select data-kind="schedule-source"' +
        ' data-section="' + esc(section) + '" data-field="' + esc(sourceKey) + '">' +
        [["fixed", "Konkrétny čas"], ["sunrise", "Východ slnka"], ["sunset", "Západ slnka"]].map(([key, label]) =>
          '<option value="' + key + '"' + (source === key ? ' selected' : '') + '>' + label + '</option>').join("") +
        '</select><output data-time-label="' + esc(fieldKey) + '">' + esc(timeText(value)) + '</output>' +
        (source !== "fixed" && mode === "full"
          ? '<div class="offset-control">Posun v min<input type="number" step="5" data-kind="offset-minutes"' +
            ' data-section="' + esc(section) + '" data-field="' + esc(prefix + "_" + side + "_offset_seconds") + '" value="' +
            esc(Number(form[section]?.[prefix + "_" + side + "_offset_seconds"] || 0) / 60) + '"></div>' : '') + '</label>';
      return '<section class="editor-card schedule-card ' + (enabled ? 'enabled' : '') + '"><div class="card-heading schedule-heading">' +
        '<div class="card-heading-icon"><ha-icon icon="mdi:clock-time-four-outline"></ha-icon></div>' +
        '<div class="card-heading-copy"><h3>' + esc(title) + '</h3><p>' +
        esc(enabled ? timeText(start) + ' – ' + timeText(end) + ' každý deň' : 'Neaktívne') + '</p></div>' +
        '<label class="switch-setting"><span>' + (enabled ? 'Zapnuté' : 'Vypnuté') + '</span><input type="checkbox"' +
        ' data-section="' + esc(section) + '" data-field="' + esc(prefix + "_enabled") + '"' +
        (enabled ? ' checked' : '') + '><i></i></label></div>' +
        (enabled ? '<div class="schedule-content"><div class="schedule-track" aria-label="' + esc(title) + '">' +
          '<div class="schedule-fill" style="background:' + esc(scheduleStyle) + '"></div>' +
          '<input class="schedule-range start" type="range" min="0" max="1439" step="15" value="' + start + '"' +
          ' aria-label="Začiatok intervalu" data-kind="schedule-time" data-section="' + esc(section) + '" data-field="' +
          esc(startKey) + '"' + (startSource !== 'fixed' ? ' disabled' : '') + '>' +
          '<input class="schedule-range end" type="range" min="0" max="1439" step="15" value="' + end + '"' +
          ' aria-label="Koniec intervalu" data-kind="schedule-time" data-section="' + esc(section) + '" data-field="' +
          esc(endKey) + '"' + (endSource !== 'fixed' ? ' disabled' : '') + '></div>' +
          '<div class="schedule-labels"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span></div>' +
          '<div class="schedule-endpoints">' + endpoint("start", "Od", start, startSource, startKey, startSourceKey) +
          endpoint("end", "Do", end, endSource, endKey, endSourceKey) + '</div>' +
          (prefix === "night" ? '<div class="schedule-extra">' + this._durationField(section, "night_delay_seconds",'Nočný časovač', form[section]?.night_delay_seconds || 0) + '</div>' : '') +
          '</div>' : '') + '</section>';
    };
    const behaviorField = (section, key, value, label, options) =>
      '<label class="field"><span>' + esc(label) + '</span><select data-section="' + esc(section) + '" data-field="' +
      esc(key) + '" data-kind="select">' + options.map(([option, text]) => '<option value="' + esc(option) + '"' +
        (value === option ? ' selected' : '') + '>' + esc(text) + '</option>').join("") + '</select></label>';
    const renderField = (section, key, value) => {
      const entityField = key.endsWith("_entities");
      const booleanField = typeof value === "boolean" || key.endsWith("_enabled") || key.endsWith("_resets_timer") || key.endsWith("_default");
      const isArray = Array.isArray(value) || entityField;
      const isObject = value && typeof value === "object" && !Array.isArray(value);
      const label = FIELD_LABELS[key] || key.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
      if (entityField) {
        const domains = key === "control_entities" ? ["light", "switch", "fan"] :
          ["binary_sensor", "sensor", "input_boolean", "switch", "light", "fan", "cover", "device_tracker", "event"];
        return entityPicker(section, key, label, "Vybrané entity zobrazíme ako štítky.", domains);
      }
      if (booleanField) return '<label class="field check"><input type="checkbox" data-section="' + esc(section) +
        '" data-field="' + esc(key) + '"' + (Boolean(value) ? ' checked' : '') + '><span>' + esc(label) + '</span></label>';
      if (key.endsWith("_offset_seconds")) return '<label class="field"><span>' + esc(label) + '</span><div class="offset-control"><input type="number" step="5" data-kind="offset-minutes" data-section="' +
        esc(section) + '" data-field="' + esc(key) + '" value="' + esc(Number(value || 0) / 60) + '"><small>minút</small></div></label>';
      if (isObject) return '<label class="field"><span>' + esc(label) + '</span><textarea rows="3" data-kind="json" data-section="' +
        esc(section) + '" data-field="' + esc(key) + '">' + esc(JSON.stringify(value, null, 2)) + '</textarea></label>';
      if (isArray) value = value.join(", ");
      const kind = key.endsWith("_time") ? "time" : key === "sensor_type" ? "select" :
        key.startsWith("on_") ? "behavior" : key.endsWith("_source") ? "schedule-source" :
        ["delay_seconds", "block_timeout_seconds", "backoff_max_seconds", "night_delay_seconds"].includes(key) ? "duration" :
        ["backoff_factor", "constraint_start_offset_seconds", "constraint_end_offset_seconds", "night_start_offset_seconds", "night_end_offset_seconds"].includes(key) ? "number" :
        ["trigger_on_states", "trigger_off_states", "state_on_states", "state_off_states", "override_on_states", "override_off_states", "state_attributes_ignore"].includes(key) ? "states" : "text";
      const input = kind === "duration" ? this._durationField(section, key, value, label) :
        kind === "select" || kind === "behavior" || kind === "schedule-source"
          ? '<select data-kind="' + kind + '" data-section="' + esc(section) + '" data-field="' + esc(key) + '">' +
            (kind === "behavior" ? [["on", "Zapnúť"], ["off", "Vypnúť"], ["ignore", "Nič nerobiť"]] :
              kind === "schedule-source" ? [["fixed", "Konkrétny čas"], ["sunrise", "Východ slnka"], ["sunset", "Západ slnka"]] :
                [["event", "Udalosť"], ["duration", "Trvanie"]]).map(([option, text]) => '<option value="' + option + '"' +
                  (value === option ? ' selected' : '') + '>' + text + '</option>').join("") + '</select>'
          : '<input type="' + (kind === "time" ? "time" : kind === "number" ? "number" : "text") + '" data-kind="' + kind +
            '" data-section="' + esc(section) + '" data-field="' + esc(key) + '" value="' + esc(value ?? "") + '"' +
            (kind === "number" ? ' step="any"' : '') + '>';
      return '<label class="field"><span>' + esc(label) + '</span>' + input + '</label>';
    };
    const advanced = [
      ["timer", "Adaptívne časovanie", ["sensor_type", "backoff_enabled", "backoff_factor", "backoff_max_seconds"]],
      ["monitoring", "Automatické odblokovanie", ["block_timeout_seconds"]],
      ["constraints", "Posuny časového okna", ["constraint_start_offset_seconds", "constraint_end_offset_seconds"]],
      ["night", "Podrobnosti nočného profilu", ["night_start_offset_seconds", "night_end_offset_seconds", "night_service_data_on", "night_service_data_off"]],
      ["initial_state", "Predvolené správanie", null],
      ["actions", "Akcie pri ďalších stavoch", ["service_data_on", "service_data_off", "on_enter_idle", "on_exit_idle", "on_enter_overridden", "on_exit_overridden", "on_enter_constrained", "on_exit_constrained", "on_enter_blocked", "on_exit_blocked"]],
      ["advanced", "Pokročilé stavy a kompatibilita", null],
    ];
    const advancedMarkup = mode === "full" ? advanced.map(([section, title, fields]) => {
      const values = form[section] || {};
      const entries = Object.entries(values).filter(([key]) => fields === null || fields.includes(key));
      const contents = entries.map(([key, value]) => renderField(section, key, value)).join("");
      return contents ? '<details class="editor-section editor-card"><summary><span>' + esc(title) +
        '</span><ha-icon icon="mdi:chevron-down"></ha-icon></summary><div class="advanced-fields">' + contents + '</div></details>' : '';
    }).join("") : '';
    const diagnosticReason = controller.block_reason === "interlock" ? "Zastavené pravidlom Interlock" :
      controller.block_reason === "controlled_entity_on" ? "Zapnuté ovládané zariadenie bráni automatickému zásahu" :
        controller.last_transition_cause === "manual_control" ? "Poslednú zmenu spôsobil ručný zásah" :
          controller.block_reason || controller.next_transition_label || "Bez aktívneho blokovania";
    const diagnosticEntities = [...new Set([
      ...(controller.active_triggers || []), ...(controller.active_state_entities || []),
      ...(controller.active_overrides || []), ...(controller.active_interlocks || []),
      ...(controller.blocked_by ? [controller.blocked_by] : []),
    ])];
    const diagnosticMarkup = mode === "full"
      ? '<details class="editor-section editor-card"><summary><span>Rozhodnutie teraz</span><ha-icon icon="mdi:chevron-down"></ha-icon></summary>' +
        '<div class="decision-summary"><div class="decision-state"><span>Stav</span><strong>' +
        esc(STATES[stateKey(controller.state)].label) + '</strong></div><div class="decision-reason"><span>Dôvod</span><strong>' +
        esc(diagnosticReason) + '</strong></div>' + (controller.next_transition_at
          ? '<div class="decision-deadline"><span>Ďalšia zmena</span><strong>' +
            esc(controller.next_transition_label || "Naplánovaná zmena") + ' · ' +
            esc(new Date(controller.next_transition_at).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})) + '</strong></div>' : '') +
        (diagnosticEntities.length ? '<div class="decision-entities"><span>Aktívne entity</span><div class="selected-entities">' +
          diagnosticEntities.map((id) => '<span class="selected-entity"><ha-state-icon data-entity="' + esc(id) + '"></ha-state-icon>' +
            '<span class="selected-entity-name">' + esc(this._hass?.states?.[id]?.attributes?.friendly_name || id) + '</span></span>').join("") +
          '</div></div>' : '') + '</div></details>' : '';
    const duration = this._durationField("basic", "delay_seconds", basic.delay_seconds || 180, "Po poslednej aktivite vypnúť po");
    const resetTimer = '<label class="switch-setting"><span>Nový pohyb vynuluje odpočet</span><input type="checkbox" data-section="timer"' +
      ' data-field="sensor_resets_timer"' + (timer.sensor_resets_timer ? ' checked' : '') + '><i></i></label>';
    const behaviorOptions = [["on", "Zapnúť entity"], ["off", "Vypnúť entity"], ["ignore", "Nič nerobiť"]];
    return '<section class="editor"><header class="editor-header"><div><h2>Nastavenia controllera</h2>' +
      '<p>Úpravy sa ukladajú priebežne.</p></div><div class="edit-modes" role="group" aria-label="Rozsah nastavení">' +
      '<button type="button" data-mode="basic" class="' + (mode === "basic" ? "selected" : "") + '">Základné</button>' +
      '<button type="button" data-mode="full" class="' + (mode === "full" ? "selected" : "") + '">Všetky nastavenia</button></div></header>' +
      '<div class="editor-status" role="status"><span class="save-state">' + esc(this._saveMessage || "Ukladanie automaticky") +
      '</span>' + (this._failedSaves?.has(controller.id) ? '<button type="button" data-retry-save="' + esc(controller.id) + '">Opakovať</button>' : '') + '</div>' +
      '<div class="editor-grid"><section class="editor-card identity-card"><div class="card-heading"><div class="card-heading-icon"><ha-icon icon="mdi:tune-variant"></ha-icon></div>' +
      '<div class="card-heading-copy"><h3>Základné nastavenia</h3><p>Rozpoznateľný názov a riadenie controllera.</p></div></div>' +
      '<div class="card-fields">' + renderField("basic", "name", basic.name || controller.name) + renderField("basic", "icon", basic.icon || controller.icon || "") + '</div>' +
      '</section>' +
      entityPicker("basic", "trigger_entities", "Spúšťače", "Čo aktivuje miestnosť?", ["binary_sensor", "sensor", "input_boolean", "switch", "light", "fan", "event", "device_tracker"]) +
      entityPicker("monitoring", "state_entities", "Sledované entity", "Ručne zapnutý stav sa rešpektuje a môže zablokovať automatiku.",
        ["binary_sensor", "sensor", "input_boolean", "device_tracker"],
        '<label class="switch-setting"><span>Povoliť blokovanie</span><input type="checkbox" data-section="monitoring" data-field="blocking_enabled"' +
        (monitoring.blocking_enabled !== false ? ' checked' : '') + '><i></i></label>') +
      entityPicker("basic", "control_entities", "Ovládané entity", "Zariadenia, ktoré sa zapnú alebo vypnú pri zmene stavu.", ["light", "switch", "fan"]) +
      '<section class="editor-card timing-card"><div class="card-heading"><div class="card-heading-icon"><ha-icon icon="mdi:timer-outline"></ha-icon></div>' +
      '<div class="card-heading-copy"><h3>Časovanie</h3><p>Po poslednej aktivite sa spustí odpočet.</p></div></div>' +
      '<div class="duration-setting">' + duration + '</div>' + resetTimer + '</section>' +
      schedule("constraints", "Povolený čas", "constraint", Boolean(constraints.constraint_enabled), "06:00", "23:00") +
      schedule("night", "Nočný profil", "night", Boolean(night.night_mode_enabled), "20:00", "06:00") +
      '<section class="editor-card editor-actions"><div class="card-heading"><div class="card-heading-icon"><ha-icon icon="mdi:gesture-tap-button"></ha-icon></div>' +
      '<div class="card-heading-copy"><h3>Akcia controllera</h3><p>Čo sa stane pri aktivite a po nej?</p></div></div><div class="card-fields">' +
      behaviorField("actions", "on_enter_active", actions.on_enter_active || "on", "Pri aktivácii", behaviorOptions) +
      behaviorField("actions", "on_exit_active", actions.on_exit_active || "ignore", "Po skončení aktivity", behaviorOptions) + '</div></section>' +
      '<section class="editor-card rules-card"><div class="card-heading"><div class="card-heading-icon"><ha-icon icon="mdi:shield-outline"></ha-icon></div>' +
      '<div class="card-heading-copy"><h3>Pravidlá riadenia</h3><p>Vstupy, ktoré menia prioritu alebo pozastavia automatiku.</p></div></div>' +
      entityPicker("rules", "override_entities", "Override", "Prevezme prioritu podľa vstupného stavu.", ["binary_sensor", "sensor", "input_boolean", "switch", "light", "device_tracker"]) +
      entityPicker("rules", "interlock_entities", "Interlock", "Blokuje automatické riadenie, kým je vstup aktívny.", ["binary_sensor", "sensor", "input_boolean", "switch", "light", "device_tracker"]) +
      '</section>' + advancedMarkup + diagnosticMarkup + '</div></section>';
  }

  _formatDuration(seconds) {
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    const minutes = Math.floor(total / 60);
    const remainder = total % 60;
    if (minutes && remainder) return minutes + ' min ' + String(remainder).padStart(2, '0') + ' s';
    if (minutes) return minutes + (minutes === 1 ? ' min' : ' min');
    return remainder + ' s';
  }

  _durationField(section, key, value, label) {
    const seconds = durationSeconds(value);
    const maximum = Math.max(7200, Math.ceil(seconds / 3600) * 3600);
    return '<label class="duration-control"><span>' + esc(label) + '</span><div class="duration-input"><input type="range" min="0" max="' + maximum +
      '" step="30" value="' + seconds + '" data-kind="duration" data-section="' + esc(section) + '" data-field="' + esc(key) + '">' +
      '<output class="duration-value" data-duration-for="' + esc(section + "." + key) + '">' +
      esc(this._formatDuration(seconds)) + '</output></div></label>';
  }

  _render() {
    if (!this.shadowRoot) return;
    if (this.shadowRoot.activeElement?.matches?.(".editor input, .editor select, .editor textarea")) {
      this._editorRenderPending = true;
      return;
    }
    this._editorRenderPending = false;
    // Keep the gesture target alive until touchend; native scrolling owns the gesture.
    if (this._touching) {
      this._renderPending = true;
      return;
    }
    if (!this.shadowRoot.querySelector(".wrap")) {
      const styles = [
        ':host{display:block;height:100vh;height:100dvh;max-height:100%;min-height:0;overflow:hidden;color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,inherit);touch-action:pan-y pinch-zoom;--ec-active:#28bd57;--ec-constrained:#1686f5;--ec-blocked:#f04452;--ec-overridden:#9b59d0;--ec-disabled:#667085;--ec-inactive:#aab2bd}',
        '.wrap{box-sizing:border-box;height:100%;min-height:0;overflow-y:auto;overflow-x:hidden;display:flex;flex-direction:column;padding:12px 16px 8px;gap:8px;scrollbar-width:thin;-webkit-overflow-scrolling:touch;touch-action:pan-y pinch-zoom;}',
        '.heading{flex:none;padding:0 4px 2px}.heading h1{font-size:var(--mush-title-font-size,24px);line-height:var(--mush-title-line-height,32px);font-weight:var(--mush-title-font-weight,400);letter-spacing:var(--mush-title-letter-spacing,-.288px);color:var(--mush-title-color,var(--primary-text-color));margin:0}.heading p{font-size:var(--mush-subtitle-font-size,16px);line-height:var(--mush-subtitle-line-height,24px);font-weight:var(--mush-subtitle-font-weight,400);color:var(--mush-subtitle-color,var(--secondary-text-color));margin:0}',
        '.list{flex:none;min-height:0;display:flex;flex-direction:column;gap:8px}',
        '.row{position:relative;flex:none;box-sizing:border-box;display:grid;grid-template-columns:minmax(400px,34%) minmax(0,1fr);grid-template-rows:auto auto;align-items:start;gap:8px 10px;padding:12px 16px;background:var(--ha-card-background,var(--card-background-color));box-shadow:var(--ha-card-box-shadow,none);border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--divider-color));border-radius:var(--ha-card-border-radius,12px);min-height:88px}',
        '.row.idle{--ec-row-color:#aab2bd}.row.active_timer{--ec-row-color:#28bd57}.row.active_stay_on{--ec-row-color:#00a896}.row.constrained{--ec-row-color:#1686f5}.row.blocked{--ec-row-color:#f04452}.row.overridden{--ec-row-color:#9b59d0}.row.disabled{--ec-row-color:#667085}.row.unknown{--ec-row-color:#d6dbe0}',
        '.identity{grid-column:1;grid-row:1;min-width:0;display:grid;grid-template-columns:52px minmax(0,1fr);grid-template-rows:36px auto;gap:4px 12px;align-items:start;align-self:start}',
        '.toggle{box-sizing:border-box;border:0;border-radius:14px;width:46px;height:24px;padding:3px;background:#b9bec4;cursor:pointer;touch-action:pan-y pinch-zoom;user-select:none;-webkit-user-select:none}.toggle span{display:block;width:18px;height:18px;border-radius:50%;background:#fff;transition:transform .15s;pointer-events:none}.toggle.on{background:#1686f5}.toggle.on span{transform:translateX(22px)}',
        '.controller-control{grid-column:1;grid-row:1/3;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;gap:4px}.controller-avatar{width:36px;height:36px;flex:none;border-radius:50%;display:flex;align-items:center;justify-content:center;background:color-mix(in srgb,var(--ec-row-color) 18%,var(--ha-card-background,var(--card-background-color)));color:var(--ec-row-color)}.controller-icon{color:var(--ec-row-color);--mdc-icon-size:24px}.controller-name{grid-column:2;grid-row:1;align-self:center;min-width:0;font-size:16px;line-height:20px;font-weight:var(--mush-card-primary-font-weight,500);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
        '.status{grid-column:2;grid-row:2;min-width:0;display:flex;flex-direction:column;gap:3px;font-size:var(--mush-card-secondary-font-size,12px);color:var(--mush-card-secondary-color,var(--secondary-text-color))}.status-head{display:flex;align-items:center;gap:9px;min-width:0}.status-label{display:flex;align-items:center;gap:7px;color:var(--mush-card-primary-color,var(--primary-text-color));white-space:nowrap}.status-label b{font-size:var(--mush-card-primary-font-size,14px);font-weight:var(--mush-card-primary-font-weight,500)}.status-label i{flex:none;width:10px;height:10px;border-radius:50%;background:var(--ec-row-color)}.status-countdown{white-space:nowrap;font-variant-numeric:tabular-nums;color:var(--mush-card-primary-color,var(--primary-text-color));font-size:var(--mush-card-primary-font-size,14px);font-weight:var(--mush-card-primary-font-weight,500)}.status-meta{display:flex;align-items:baseline;justify-content:space-between;gap:8px;min-width:0}.status-detail{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.status-meta small{flex:none;white-space:nowrap;font-size:var(--mush-card-secondary-font-size,12px);color:var(--mush-card-secondary-color,var(--secondary-text-color))}',
        '.chips{grid-column:2;grid-row:1;min-width:0;display:flex;flex-wrap:wrap;align-items:flex-start;align-content:flex-start;align-self:start;gap:4px;overflow:visible;padding:0}',
        '.chip-separator{flex:none;padding:0;margin:0 -1px;align-self:center;color:var(--secondary-text-color);font-size:13px;line-height:1;opacity:.7}.chip{height:28px;box-sizing:border-box;flex:0 1 auto;min-width:70px;max-width:175px;display:flex;align-items:center;justify-content:flex-start;gap:7px;padding:0 9px;border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--divider-color));border-radius:18px;background:var(--chip-background,var(--ha-card-background,var(--card-background-color)));box-shadow:var(--chip-box-shadow,var(--ha-card-box-shadow,none));color:var(--primary-text-color);cursor:pointer;white-space:nowrap;font:inherit;font-size:12px;touch-action:pan-y pinch-zoom;user-select:none;-webkit-user-select:none} .chip span{min-width:0;overflow:hidden;text-overflow:ellipsis;pointer-events:none}.chip.unavailable{color:var(--disabled-text-color,var(--secondary-text-color));border-color:var(--disabled-text-color,var(--divider-color));background:color-mix(in srgb,var(--ha-card-background,var(--card-background-color)) 78%,var(--secondary-text-color));box-shadow:none;opacity:.62;filter:grayscale(1)}.chip.unavailable .chip-label{text-decoration:line-through;text-decoration-thickness:1px}.chip.unavailable .chip-icon{color:var(--disabled-text-color,var(--secondary-text-color))}.chip-switch{position:relative;width:22px;height:13px;flex:none;box-sizing:border-box;border-radius:8px;background:var(--disabled-text-color,#9e9e9e);opacity:.75;transition:background .15s}.chip-switch i{position:absolute;top:2px;left:2px;width:9px;height:9px;border-radius:50%;background:#fff;transition:transform .15s}.chip-switch.is-on{background:var(--success-color,#43a047);opacity:1}.chip-switch.is-on i{transform:translateX(9px)}.chip-icon{--mdc-icon-size:16px;flex:none;color:var(--secondary-text-color);pointer-events:none}.chip.active-trigger{background:rgba(76,175,80,.18);border-color:#43a047;box-shadow:0 0 0 1px rgba(67,160,71,.14)}.chip.active-output{background:rgba(255,213,79,.22);border-color:#d2a500;box-shadow:0 0 0 1px rgba(210,165,0,.14)}.chip.active-override{background:rgba(156,39,176,.14);border-color:#9c27b0;box-shadow:0 0 0 1px rgba(156,39,176,.12)}.chip.active-interlock{background:rgba(3,169,244,.14);border-color:#039be5;box-shadow:0 0 0 1px rgba(3,155,229,.12)}.chip[data-chip-toggle]{cursor:pointer}.chip-active-dot{width:7px;height:7px;flex:none;border-radius:50%;background:#2e8b3c}.chip.active-output .chip-active-dot{background:#b38b00}',
        '.timeline-line{grid-column:1/-1;grid-row:2;padding-top:2px;min-width:0}.timeline-wrap{width:100%}.timeline{height:16px;position:relative;overflow:hidden;border-radius:5px;background:#d6dbe0;direction:ltr}.tick{position:absolute;top:0;bottom:0;width:1px;background:rgba(255,255,255,.9);opacity:.8;pointer-events:none}.timeline-axis{height:16px;display:flex;justify-content:space-between;align-items:flex-start;color:var(--secondary-text-color);font-size:10px;line-height:14px;padding-top:3px;direction:ltr}.timeline-axis span{white-space:nowrap;flex:none}.timeline-error{font-size:11px;color:var(--error-color);padding-top:3px}',
        '.edit-toggle{position:absolute;right:12px;top:12px;z-index:1;display:flex;align-items:center;gap:5px;min-height:32px;padding:4px 8px;border:1px solid var(--divider-color);border-radius:8px;color:var(--primary-text-color);background:var(--ha-card-background,var(--card-background-color));cursor:pointer}.edit-toggle ha-icon{--mdc-icon-size:20px}.controller-name{padding-right:52px}.row.editing{grid-template-columns:minmax(0,1fr);gap:0}.row.editing .identity{grid-column:1;grid-row:1;grid-template-columns:48px minmax(0,1fr);grid-template-rows:36px auto}.row.editing .controller-name{grid-column:2;grid-row:1}.row.editing .chips{grid-column:1;grid-row:2}.row.editing .timeline-line{grid-column:1;grid-row:3}.editor{grid-column:1;grid-row:4;min-width:0;margin-top:10px;padding-top:12px;border-top:1px solid var(--divider-color)}.editor>header{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.edit-modes{display:flex;padding:3px;background:var(--secondary-background-color,var(--divider-color));border-radius:10px}.edit-modes button{border:0;border-radius:8px;padding:7px 12px;color:var(--primary-text-color);background:transparent;cursor:pointer}.edit-modes button.selected{background:var(--ha-card-background,var(--card-background-color));box-shadow:var(--ha-card-box-shadow,0 1px 3px #0002)}.save-state{margin:8px 0;color:var(--secondary-text-color);font-size:12px}.editor-section{margin:8px 0;border:1px solid var(--divider-color);border-radius:10px;background:var(--card-background-color)}.editor-section summary{padding:11px 13px;cursor:pointer;font-weight:500}.editor-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;padding:0 12px 12px}.field{display:flex;flex-direction:column;gap:5px;min-width:0;color:var(--primary-text-color);font-size:13px}.field input:not([type=checkbox]),.field select,.field textarea{box-sizing:border-box;width:100%;min-height:38px;padding:7px 9px;border:1px solid var(--input-fill-color,var(--divider-color));border-radius:7px;color:var(--primary-text-color);background:var(--input-background-color,var(--primary-background-color));font:inherit}.field select[multiple]{height:118px}.field textarea{resize:vertical;font-family:monospace}.field small{color:var(--secondary-text-color);font-size:11px}.field.check{flex-direction:row;align-items:center;min-height:38px}.field.check input{width:18px;height:18px;accent-color:var(--primary-color)}@media(max-width:620px){.editor-fields{grid-template-columns:1fr}.row.editing .identity{grid-template-columns:42px minmax(0,1fr);gap:4px 8px}.edit-toggle{padding:3px 7px}}',
        '.legend{flex:none;box-sizing:border-box;min-height:48px;padding:8px 18px;display:flex;align-items:center;justify-content:space-between;gap:15px;border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--divider-color));border-radius:var(--ha-card-border-radius,12px);background:var(--ha-card-background,var(--card-background-color));box-shadow:var(--ha-card-box-shadow,none);color:var(--primary-text-color);font-size:13px}.legend-items{display:flex;align-items:center;gap:10px 14px;flex-wrap:wrap}.legend-title{font-weight:700}.legend-items span{display:flex;align-items:center;gap:9px;white-space:nowrap}.swatch{width:22px;height:12px;flex:none;border-radius:4px;background:var(--ec-inactive)}.swatch.idle{background:#aab2bd}.swatch.active_timer{background:#28bd57}.swatch.active_stay_on{background:#00a896}.swatch.constrained{background:#1686f5}.swatch.blocked{background:#f04452}.swatch.overridden{background:#9b59d0}.swatch.disabled{background:#667085}.swatch.unknown{background:repeating-linear-gradient(135deg,#d6dbe0 0 3px,#aab2bd 3px 5px)}.count{color:var(--secondary-text-color);white-space:nowrap}',
        '.empty{color:var(--secondary-text-color);text-align:center;padding:48px 16px}.error{color:var(--error-color);padding:10px 14px}',
        '@media(max-width:1100px){.row{grid-template-columns:minmax(330px,38%) minmax(0,1fr)}.identity{grid-template-columns:48px minmax(0,1fr);grid-template-rows:34px auto;gap:4px 8px}.controller-avatar{width:32px;height:32px}.controller-icon{--mdc-icon-size:22px}.chip{min-width:66px;padding:0 8px}.legend-items{gap:14px}}',
        '@media(max-width:760px){.wrap{padding:10px}.row{grid-template-columns:1fr;grid-template-rows:auto auto;gap:7px}.identity{grid-column:1;grid-row:1;grid-template-columns:48px minmax(0,1fr);grid-template-rows:34px auto}.chips{grid-column:1;grid-row:2}.timeline-line{grid-column:1;grid-row:3}.legend{align-items:flex-start;flex-direction:column}.legend-items{gap:10px 16px}}',
        '@media(max-width:480px){.timeline-axis{font-size:9px}.timeline-axis span:nth-child(even){display:none}.heading h1{font-size:25px}.row{padding:8px 10px 5px 15px}.identity{grid-template-columns:38px minmax(0,1fr);grid-template-rows:32px auto;gap:4px 6px}.toggle{width:36px}.toggle.on span{transform:translateX(12px)}.controller-avatar{width:30px;height:30px}.controller-icon{--mdc-icon-size:20px}.controller-name{font-size:16px}.status-label b,.status-countdown{font-size:12px}.status{font-size:11px}.status-label i{width:9px;height:9px}.status-meta small{font-size:10px}.chip{font-size:11px;height:27px;min-width:58px;padding:0 7px}.legend-items{font-size:11px;gap:9px 12px}.swatch{width:22px;height:11px}}@media(max-width:360px){.timeline-axis span{display:none}.timeline-axis span:nth-child(3n + 1){display:inline}}',
      ].join("");
      const editorStyles = '.row.editing{grid-template-columns:minmax(0,1fr);gap:6px}.row.editing .identity{grid-row:1}.row.editing .chips{grid-row:2}.row.editing .timeline-line{display:none}.editor{grid-row:3;margin-top:3px;padding-top:10px;border-top:1px solid var(--divider-color)}.editor-header{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:0 1px 3px}.editor-header h2{margin:0;font-size:17px;font-weight:600;line-height:1.3}.editor-header p{margin:3px 0 0;color:var(--secondary-text-color);font-size:12px}.edit-modes button{font-size:12px;font-weight:500;white-space:nowrap}.editor-status{display:flex;align-items:center;gap:8px;min-height:26px;margin:0 1px 4px;color:var(--secondary-text-color);font-size:12px}.editor-status button{border:0;border-radius:14px;background:var(--secondary-background-color);color:var(--primary-color);padding:4px 9px;cursor:pointer}.save-state{margin:0}.editor-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:start;gap:8px}.editor-card{box-sizing:border-box;min-width:0;margin:0;padding:12px;border:1px solid var(--ha-card-border-color,var(--divider-color));border-radius:var(--ha-card-border-radius,12px);background:var(--ha-card-background,var(--card-background-color));box-shadow:var(--ha-card-box-shadow,none)}.card-heading{display:flex;align-items:center;gap:10px;min-width:0;margin-bottom:10px}.card-heading-icon{width:30px;height:30px;flex:none;display:grid;place-items:center;border-radius:9px;background:color-mix(in srgb,var(--primary-color) 12%,transparent);color:var(--primary-color)}.card-heading-icon ha-icon{--mdc-icon-size:19px}.card-heading-copy{min-width:0;flex:1}.card-heading-copy h3{margin:0;font-size:14px;font-weight:600;line-height:1.3}.card-heading-copy p{margin:2px 0 0;color:var(--secondary-text-color);font-size:11px;line-height:1.35}.card-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.identity-card .card-fields{grid-template-columns:minmax(0,1.4fr) minmax(130px,.8fr)}.field{font-size:12px}.field input:not([type=checkbox]),.field select,.field textarea{min-height:34px;padding:6px 8px;border-radius:8px}.field select[multiple]{height:auto}.field.check{flex-direction:row;align-items:center;min-height:32px}.card-switches{display:flex;flex-wrap:wrap;gap:4px 14px;margin-top:9px}.switch-setting{position:relative;display:flex;align-items:center;gap:8px;min-height:29px;color:var(--primary-text-color);font-size:12px;cursor:pointer}.switch-setting input{position:absolute;width:1px;height:1px;opacity:0}.switch-setting i{position:relative;width:32px;height:18px;order:2;flex:none;border-radius:12px;background:var(--disabled-text-color,var(--divider-color));transition:background .15s}.switch-setting i:after{content:"";position:absolute;top:3px;left:3px;width:12px;height:12px;border-radius:50%;background:var(--card-background-color);transition:transform .15s}.switch-setting input:checked+i{background:var(--primary-color)}.switch-setting input:checked+i:after{transform:translateX(14px)}.selected-entities{display:flex;flex-wrap:wrap;gap:5px;margin:2px 0 8px}.selected-entity{display:inline-flex;align-items:center;gap:6px;max-width:100%;min-height:28px;padding:0 5px 0 8px;border:1px solid var(--divider-color);border-radius:16px;background:var(--secondary-background-color,var(--card-background-color));font-size:11px}.selected-entity ha-state-icon{--mdc-icon-size:16px;flex:none}.selected-entity-name{max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.remove-entity{width:20px;height:20px;padding:0;border:0;border-radius:50%;background:transparent;color:var(--secondary-text-color);font-size:17px;line-height:18px;cursor:pointer}.remove-entity:hover{background:var(--divider-color)}.empty-selection{margin:2px 0 8px;color:var(--secondary-text-color);font-size:11px}.add-entity{display:inline-flex;align-items:center;gap:5px;min-height:28px;padding:0 9px;border:1px dashed var(--divider-color);border-radius:16px;background:transparent;color:var(--primary-color);font:inherit;font-size:11px;font-weight:500;cursor:pointer}.add-entity ha-icon{--mdc-icon-size:15px}.entity-picker{margin-top:8px;padding:8px;border-radius:9px;background:var(--secondary-background-color,var(--primary-background-color))}.entity-search{box-sizing:border-box;width:100%;height:34px;padding:6px 9px;border:1px solid var(--divider-color);border-radius:8px;background:var(--ha-card-background,var(--card-background-color));color:var(--primary-text-color);font:inherit;font-size:12px}.entity-options{display:flex;flex-direction:column;max-height:190px;overflow:auto;margin-top:5px}.entity-option{display:grid;grid-template-columns:20px minmax(0,1fr) auto;align-items:center;gap:7px;min-height:34px;padding:5px 6px;border:0;border-radius:7px;background:transparent;color:var(--primary-text-color);text-align:left;font:inherit;font-size:12px;cursor:pointer}.entity-option:hover,.entity-option:focus-visible{background:var(--primary-background-color,var(--card-background-color));outline:none}.entity-option ha-state-icon{--mdc-icon-size:17px}.entity-option span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.entity-option small{color:var(--secondary-text-color);font-size:10px}.duration-setting{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px}.duration-control{display:flex;flex-direction:column;gap:8px;min-width:0;color:var(--primary-text-color);font-size:12px}.duration-control input{width:100%;accent-color:var(--primary-color)}.duration-value{min-width:62px;color:var(--primary-text-color);font-size:13px;font-weight:600;text-align:right;font-variant-numeric:tabular-nums}.timing-card>.switch-setting{margin-top:5px}.schedule-heading{margin-bottom:8px}.schedule-heading .card-heading-copy p{font-variant-numeric:tabular-nums}.schedule-content{padding-top:4px}.schedule-track{position:relative;height:22px;display:flex;align-items:center;margin:0 5px}.schedule-track:before{content:"";position:absolute;left:0;right:0;height:5px;border-radius:4px;background:var(--divider-color)}.schedule-fill{position:absolute;left:0;right:0;height:5px;border-radius:4px;opacity:.75;pointer-events:none}.schedule-range{position:absolute;inset:0;width:100%;height:22px;margin:0;background:transparent;appearance:none;-webkit-appearance:none;pointer-events:none}.schedule-range::-webkit-slider-runnable-track{height:5px;background:transparent}.schedule-range::-moz-range-track{height:5px;background:transparent}.schedule-range::-webkit-slider-thumb{width:15px;height:15px;margin-top:-5px;border:2px solid var(--card-background-color);border-radius:50%;appearance:none;-webkit-appearance:none;background:var(--primary-color);box-shadow:0 1px 3px #0003;pointer-events:auto;cursor:grab}.schedule-range::-moz-range-thumb{width:11px;height:11px;border:2px solid var(--card-background-color);border-radius:50%;background:var(--primary-color);box-shadow:0 1px 3px #0003;pointer-events:auto;cursor:grab}.schedule-range:disabled::-webkit-slider-thumb{background:var(--disabled-text-color);cursor:not-allowed}.schedule-labels{display:flex;justify-content:space-between;margin:1px 0 9px;color:var(--secondary-text-color);font-size:9px;font-variant-numeric:tabular-nums}.schedule-endpoints{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.schedule-endpoint{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:6px;min-width:0;color:var(--secondary-text-color);font-size:11px}.schedule-endpoint select{min-width:0;width:100%;height:30px;padding:4px;border:1px solid var(--divider-color);border-radius:7px;background:var(--primary-background-color,var(--card-background-color));color:var(--primary-text-color);font:inherit;font-size:11px}.schedule-endpoint output{min-width:40px;color:var(--primary-text-color);font-size:12px;font-weight:600;font-variant-numeric:tabular-nums}.schedule-extra{margin-top:10px}.offset-control{grid-column:1/-1;display:flex;justify-content:space-between;align-items:center;gap:8px}.offset-control input{width:62px;min-height:28px;padding:3px 5px;border:1px solid var(--divider-color);border-radius:7px;background:var(--primary-background-color,var(--card-background-color));color:var(--primary-text-color)}.editor-actions .card-fields{grid-template-columns:repeat(2,minmax(0,1fr))}.rules-card{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr;gap:8px}.rules-card>.card-heading{grid-column:1/-1;margin-bottom:0}.rules-card .entity-card{padding:8px;background:var(--secondary-background-color,var(--card-background-color))}.editor-section{grid-column:1/-1;margin:0;padding:0}.editor-section summary{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px;list-style:none;font-size:12px}.editor-section summary::-webkit-details-marker{display:none}.editor-section summary ha-icon{--mdc-icon-size:18px;color:var(--secondary-text-color);transition:transform .15s}.editor-section[open] summary ha-icon{transform:rotate(180deg)}.advanced-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:0 12px 12px}.advanced-fields>.entity-card{grid-column:1/-1}.advanced-fields>.field{align-self:start}.advanced-fields .duration-control{grid-column:span 1}.advanced-fields textarea{min-height:66px}.schedule-card{grid-column:span 1}.identity-card,.timing-card,.editor-actions{grid-column:span 1}@media(max-width:760px){.editor-grid{grid-template-columns:1fr}.rules-card{grid-column:1;grid-template-columns:1fr}.rules-card>.card-heading{grid-column:1}.row.editing .timeline-line{display:none}.schedule-card,.identity-card,.timing-card,.editor-actions{grid-column:1}.advanced-fields{grid-template-columns:1fr}}@media(max-width:620px){.editor-header{align-items:flex-start;flex-direction:column}.edit-modes{width:100%}.edit-modes button{flex:1}.card-fields,.identity-card .card-fields,.editor-actions .card-fields{grid-template-columns:1fr}.schedule-endpoints{grid-template-columns:1fr}.rules-card{grid-template-columns:1fr}.editor-card{padding:10px}}';
      const interactionStyles = '.duration-input{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:10px}.duration-value{min-width:56px;color:var(--primary-text-color);font-size:12px;font-weight:600;text-align:right;font-variant-numeric:tabular-nums}.duration-setting{display:block}.duration-setting .duration-control{display:flex;flex-direction:column;gap:6px}.duration-setting .duration-control>span{color:var(--secondary-text-color);font-size:11px}.duration-setting .duration-control input{width:100%;accent-color:var(--primary-color)}';
      this.shadowRoot.innerHTML = '<style>' + styles + editorStyles + interactionStyles + '</style>' +
        '<main class="wrap"><header class="heading"><h1>Entity Controller</h1>' +
        '<p>Rýchly prehľad controllerov</p></header><div class="error" hidden></div>' +
        '<section class="list"></section><footer class="legend"><div class="legend-items"><span class="legend-title">Legenda časovej osi:</span>' +
        '<span><i class="swatch idle"></i>Neaktívny</span><span><i class="swatch active_timer"></i>Aktívny · časovač</span>' +
        '<span><i class="swatch active_stay_on"></i>Aktívny · trvalý režim</span><span><i class="swatch blocked"></i>Blokovaný</span>' +
        '<span><i class="swatch overridden"></i>Override</span><span><i class="swatch constrained"></i>Časovo obmedzený</span>' +
        '<span><i class="swatch disabled"></i>Vypnutý</span><span><i class="swatch unknown"></i>Neznámy</span>' +
        '</div><span class="count"></span></footer></main>';
      this.shadowRoot.querySelector(".wrap").addEventListener(
        "scroll", () => this._updateVisibleCount(), { passive: true }
      );
    }
    // Update individual rows without replacing the scroll container. HA supplies
    // a new hass object for unrelated state updates as well as EC transitions.
    const list = this.shadowRoot.querySelector(".list");
    const error = this.shadowRoot.querySelector(".error");
    error.hidden = !this.error;
    error.textContent = this.error || "";
    const ids = new Set(this.controllers.map((controller) => controller.id));
    const rows = new Map([...list.querySelectorAll(".row")]
      .map((row) => [row.dataset.controllerId, row]));
    for (const [id, row] of rows) {
      if (!ids.has(id)) {
        row.remove();
        this._rowMarkup.delete(id);
      }
    }
    if (this.controllers.length) list.querySelector(".empty")?.remove();
    this.controllers.forEach((controller, index) => {
      const markup = this._row(controller);
      let row = rows.get(controller.id);
      if (!row || this._rowMarkup.get(controller.id) !== markup) {
        const template = document.createElement("template");
        template.innerHTML = markup;
        const updated = template.content.firstElementChild;
        if (row) {
          row.className = updated.className;
          row.innerHTML = updated.innerHTML;
        } else row = updated;
        this._rowMarkup.set(controller.id, markup);
        this._refreshControllerIcons(row);
      }
      if (list.children[index] !== row) list.insertBefore(row, list.children[index] || null);
    });
    if (!this.controllers.length && !list.querySelector(".empty")) {
      list.innerHTML = '<div class="empty">Nie sú nakonfigurované žiadne ovládače.</div>';
    }
    this.shadowRoot.querySelectorAll("ha-state-icon[data-entity]").forEach((icon) => {
      icon.hass = this._hass;
      icon.stateObj = this._hass?.states?.[icon.dataset.entity];
    });
    requestAnimationFrame(() => this._updateVisibleCount());
  }

  async _handleClick(event) {
    const button = event.composedPath().find((element) =>
      element.matches?.(".chip[data-entity], button[data-toggle], button[data-edit], button[data-mode], " +
        "button[data-picker-toggle], button[data-entity-option], button[data-remove-entity], button[data-retry-save]"));
    if (!button) return;
    if (button.dataset.pickerToggle) {
      this._pickerOpen = this._pickerOpen === button.dataset.pickerToggle ? null : button.dataset.pickerToggle;
      this._rowMarkup.clear();
      this._render();
      this.shadowRoot.querySelector(".entity-search")?.focus();
      return;
    }
    if (button.dataset.entityOption || button.dataset.removeEntity) {
      const controller = this.controllers.find((item) => item.id === this._editing?.id);
      if (!controller) return;
      const section = button.dataset.section;
      const key = button.dataset.field;
      const nextForm = structuredClone(controller.form || {});
      if (!nextForm[section]) nextForm[section] = {};
      const selected = Array.isArray(nextForm[section][key]) ? nextForm[section][key] : [];
      nextForm[section][key] = button.dataset.entityOption
        ? [...new Set([...selected, button.dataset.value])]
        : selected.filter((entity) => entity !== button.dataset.value);
      const previousForm = structuredClone(controller.form || {});
      controller.form = nextForm;
      if (button.dataset.entityOption) this._pickerOpen = section + "." + key;
      this._rowMarkup.clear();
      this._render();
      await this._persistControllerForm(controller, nextForm, previousForm);
      return;
    }
    if (button.dataset.retrySave) {
      const controller = this.controllers.find((item) => item.id === button.dataset.retrySave);
      const failed = this._failedSaves.get(button.dataset.retrySave);
      if (controller && failed) {
        controller.form = failed.form;
        await this._persistControllerForm(controller, failed.form, failed.previous);
      }
      return;
    }
    if (button.dataset.edit) {
      this._saveMessage = "Zmeny sa ukladajú automaticky.";
      this._editing = this._editing?.id === button.dataset.edit
        ? null : { id: button.dataset.edit, mode: "basic" };
      this._pickerOpen = null;
      this._rowMarkup.clear();
      this._render();
      return;
    }
    if (button.dataset.mode) {
      if (this._editing) this._editing.mode = button.dataset.mode;
      this._rowMarkup.clear();
      this._render();
      return;
    }
    if (button.dataset.toggle) {
      const entityId = button.dataset.toggle;
      const enabled = this.controllers.find((item) => item.enabled_entity_id === entityId)?.enabled;
      await this._hass.callService("switch", enabled ? "turn_off" : "turn_on", { entity_id: entityId });
      return;
    }
    const entityId = button.dataset.entity;
    if (!entityId) return;
    if (button.dataset.chipToggle) {
      const value = String(this._hass?.states?.[entityId]?.state || "").toLowerCase();
      await this._hass.callService(button.dataset.chipToggle,
        value === "on" ? "turn_off" : "turn_on", { entity_id: entityId });
      return;
    }
    this.dispatchEvent(new CustomEvent("hass-more-info", {
      bubbles: true, composed: true, detail: { entityId },
    }));
  }

  _readEditorValue(element) {
    const kind = element.dataset.kind;
    if (element.type === "checkbox") return element.checked;
    if (element.multiple) return [...element.selectedOptions].map((option) => option.value);
    if (kind === "json") return JSON.parse(element.value || "{}");
    if (kind === "schedule-time") {
      const minutes = Math.max(0, Math.min(1439, Number(element.value) || 0));
      return String(Math.floor(minutes / 60)).padStart(2, "0") + ":" +
        String(minutes % 60).padStart(2, "0") + ":00";
    }
    if (kind === "offset-minutes") return (Number(element.value) || 0) * 60;
    if (kind === "states") return element.value.split(",").map((item) => item.trim()).filter(Boolean);
    if (kind === "duration") {
      const seconds = Math.max(0, Number(element.value) || 0);
      const days = Math.floor(seconds / 86400);
      const hours = Math.floor((seconds % 86400) / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      return { days, hours, minutes, seconds: Math.round(seconds % 60) };
    }
    if (kind === "number") return Number(element.value);
    return element.value;
  }

  _handleEditorInput(event) {
    const field = event.target;
    if (field.matches?.(".entity-search")) {
      const query = field.value.trim().toLocaleLowerCase();
      field.closest(".entity-picker")?.querySelectorAll(".entity-option").forEach((option) => {
        option.hidden = !option.textContent.toLocaleLowerCase().includes(query);
      });
      return;
    }
    if (!field.matches?.(".editor [data-field]") || ["checkbox", "select-multiple"].includes(field.type)) return;
    if (field.dataset.kind === "schedule-time") {
      const minutes = Number(field.value) || 0;
      const display = String(Math.floor(minutes / 60)).padStart(2, "0") + ":" + String(minutes % 60).padStart(2, "0");
      const key = field.dataset.field;
      const timeOutput = field.closest(".schedule-content")?.querySelector('[data-time-label="' + key + '"]');
      if (timeOutput) timeOutput.textContent = display;
      const controls = [...(field.closest(".schedule-track")?.querySelectorAll(".schedule-range") || [])];
      const values = controls.map((control) => Number(control.value) / 1439 * 100);
      const left = Math.min(...values);
      const right = Math.max(...values);
      const fill = field.closest(".schedule-track")?.querySelector(".schedule-fill");
      if (fill) fill.style.background = values[0] <= values[1]
        ? "linear-gradient(to right, transparent 0%, transparent " + left + "%, var(--primary-color) " + left +
          "%, var(--primary-color) " + right + "%, transparent " + right + "%, transparent 100%)"
        : "linear-gradient(to right, var(--primary-color) 0%, var(--primary-color) " + right + "%, transparent " + right +
          "%, transparent " + left + "%, var(--primary-color) " + left + "%, var(--primary-color) 100%)";
      return;
    }
    if (field.dataset.kind === "duration") {
      const basicOutput = this.shadowRoot.querySelector('[data-duration-for="' + field.dataset.section + "." + field.dataset.field + '"]');
      if (basicOutput) basicOutput.textContent = this._formatDuration(Number(field.value));
      return;
    }
    clearTimeout(this._saveTimers.get(field));
    this._saveTimers.set(field, setTimeout(() => this._persistEditorField(field), 650));
  }

  _handleEditorChange(event) {
    const field = event.target;
    if (!field.matches?.(".editor [data-field]")) return;
    clearTimeout(this._saveTimers.get(field));
    this._persistEditorField(field);
  }

  async _persistEditorField(field) {
    const controller = this.controllers.find((item) => item.id === this._editing?.id);
    if (!controller || !field.isConnected) return;
    const section = field.dataset.section;
    const key = field.dataset.field;
    const previousForm = structuredClone(controller.form || {});
    const nextForm = structuredClone(controller.form || {});
    if (!nextForm[section]) nextForm[section] = {};
    try {
      nextForm[section][key] = this._readEditorValue(field);
    } catch (error) {
      const status = field.closest(".editor")?.querySelector(".save-state");
      if (status) status.textContent = "Neplatná hodnota: " + (error?.message || "skontroluj JSON.");
      return;
    }
    const snapshot = JSON.stringify(nextForm[section][key]);
    if (field.dataset.savedSnapshot === snapshot) return;
    controller.form = nextForm;
    return this._persistControllerForm(controller, nextForm, previousForm, field, snapshot);
  }

  async _persistControllerForm(controller, nextForm, previousForm, field = null, snapshot = JSON.stringify(nextForm)) {
    this._saveMessage = "Ukladám…";
    this._failedSaves.delete(controller.id);
    const status = field?.closest(".editor")?.querySelector(".save-state") ||
      this.shadowRoot.querySelector(".editor .save-state");
    if (status) status.textContent = this._saveMessage;
    try {
      const previousSave = this._saveQueues.get(controller.id) || Promise.resolve();
      const save = previousSave.catch(() => {}).then(() => this._hass.callWS({
        type: SAVE_COMMAND,
        entry_id: controller.entry_id,
        controller_id: controller.id,
        form: nextForm,
      }));
      this._saveQueues.set(controller.id, save);
      await save;
      if (field) field.dataset.savedSnapshot = snapshot;
      this._saveMessage = "Uložené";
      if (status?.isConnected) status.textContent = this._saveMessage;
      if (this._saveQueues.get(controller.id) === save) await this._refresh();
    } catch (error) {
      controller.form = previousForm;
      this._failedSaves.set(controller.id, { form: nextForm, previous: previousForm });
      this._saveMessage = "Chyba pri ukladaní; pôvodná hodnota zostala zachovaná.";
      this._rowMarkup.clear();
      this._render();
    }
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
    const bounds = this.shadowRoot.querySelector(".wrap").getBoundingClientRect();
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

