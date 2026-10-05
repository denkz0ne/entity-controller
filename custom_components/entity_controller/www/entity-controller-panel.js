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
  presence_entities: "Prítomnosť / podržanie", presence_on_states: "Prítomnosť · aktívny stav", presence_off_states: "Prítomnosť · neaktívny stav",
  sensor_type: "Typ spúšťača", sensor_resets_timer: "Opakovaný spúšťač obnoví časovač",
  backoff_enabled: "Postupne predlžovať opakovanie", backoff_factor: "Faktor predĺženia",
  backoff_max_seconds: "Najdlhšie predĺženie", state_entities: "Sledované entity",
  blocking_enabled: "Povoliť blokovanie", block_timeout_seconds: "Automatické odblokovanie po",
  protect_manual_off: "Rešpektovať ručné vypnutie", protect_manual_on: "Rešpektovať zapnutie a úpravy",
  override_entities: "Override entity", interlock_entities: "Interlock entity",
  constraint_enabled: "Povoliť časové okno", night_mode_enabled: "Povoliť nočný režim",
  night_delay_seconds: "Nočný čas aktivity", service_data_on: "Parametre pri zapnutí",
  service_data_off: "Parametre pri vypnutí", night_service_data_on: "Nočné parametre pri zapnutí",
  night_service_data_off: "Nočné parametre pri vypnutí", enabled_default: "Počiatočne povolený",
  stay_mode_default: "Počiatočný trvalý režim", trigger_on_states: "Spúšťacie stavy · aktívny",
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
    this._iconPickerOpen = false;
    this._dirtyControllers = new Set();
    this._savingControllers = new Set();
    this._saveErrors = new Map();
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
    this._helpResizeHandler = () => this._dismissHelp();
    this.shadowRoot.addEventListener("scroll", () => this._dismissHelp(), {capture: true, passive: true});
    this.shadowRoot.addEventListener("click", (event) => this._handleClick(event));
    this.shadowRoot.addEventListener("toggle", (event) => {
      if (!event.target.matches?.(".help-popover")) return;
      const button = [...this.shadowRoot.querySelectorAll("button[data-help]")]
        .find((item) => item.dataset.help === event.target.id);
      button?.setAttribute("aria-expanded", String(event.newState === "open"));
    }, true);
    this.shadowRoot.addEventListener("change", (event) => this._handleEditorChange(event));
    this.shadowRoot.addEventListener("input", (event) => this._handleEditorInput(event));
    this.shadowRoot.addEventListener('keydown', event => this._handlePickerKeydown(event));
    this.shadowRoot.addEventListener("focusout", (event) => {
      if (event.target.matches?.(".editor [data-field]") && this._editorRenderPending) {
        // Keep the clicked button and draft inputs alive across focusout.
        setTimeout(() => this._render(true), 0);
      }
    });
  }

  set hass(hass) {
    const previous = this._hass;
    this._hass = hass;
    if (hass && !previous) this._start();
    if (hass && previous && hass.connection !== previous.connection) this._watchStates();
    this._render(Boolean(this._editing));
  }

  get hass() { return this._hass; }

  connectedCallback() {
    window.addEventListener("resize", this._helpResizeHandler, {passive: true});
    this.addEventListener("touchstart", this._touchStartHandler, { passive: true });
    window.addEventListener("touchend", this._touchEndHandler, { capture: true, passive: true });
    window.addEventListener("touchcancel", this._touchEndHandler, { capture: true, passive: true });
    if (this._hass) this._start();
  }

  disconnectedCallback() {
    window.removeEventListener("resize", this._helpResizeHandler);
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
    if (!this._timer) this._timer = setInterval(() => this._refresh(), REFRESH_MS);
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
    const form = controller.form || {};
    const hasSolarSchedule = [form.constraints, form.night].some((section) =>
      section && Object.entries(section).some(([key, value]) =>
        key.endsWith("_source") && value !== "fixed"));
    return [controller.state_entity_id, controller.enabled_entity_id,
      ...(controller.inputs || controller.triggers || []), ...controller.outputs,
      ...(hasSolarSchedule ? ["sun.sun"] : [])].filter(Boolean);
  }

  async _refresh() {
    if (this._refreshing || !this._hass) return;
    this._refreshing = true;
    try {
      const response = await this._hass.callWS({ type: DATA_COMMAND });
      const previousControllers = new Map(this.controllers.map((item) => [item.id, item]));
      this.controllers = (response.controllers || []).map((item) => {
        const previous = previousControllers.get(item.id);
        if ((this._editing?.id !== item.id && !this._dirtyControllers.has(item.id)) || !previous) return item;
        return { ...item, _liveForm: item.form, form: previous.form, name: previous.name, icon: previous.icon,
          _draftRevision: previous._draftRevision };
      });
      this.error = null;
      this._render(Boolean(this._editing));
      const editing = this.controllers.find(item => item.id === this._editing?.id);
      if (editing) {
        this._updateEditorStatus(editing);
        for (const prefix of ['constraint', 'night']) {
          const section = prefix === 'constraint' ? 'constraints' : 'night';
          for (const side of ['start', 'end']) {
            const source = editing.form?.[section]?.[prefix + '_' + side + '_source'];
            if (source && source !== 'fixed') this._syncScheduleEndpoint(editing, prefix, side);
          }
        }
      }
      await this._loadHistory();
    } catch (error) {
      this.error = error?.message || "Nepodarilo sa načítať ovládače.";
      this._render(Boolean(this._editing));
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
    this._render(Boolean(this._editing));
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
    const editButton = this._hass?.user?.is_admin && this._editing?.id !== controller.id
      ? '<button class="edit-toggle" data-edit="' + esc(controller.id) + '" aria-expanded="' +
        (this._editing?.id === controller.id) + '" title="Upraviť nastavenia">' +
        (this._editing?.id === controller.id ? 'Zavrieť' : '<ha-icon icon="mdi:cog-outline"></ha-icon>') + '</button>' : '';
    const avatar = this._editing?.id === controller.id
      ? '<button type="button" class="controller-avatar" data-icon-toggle="header" aria-label="Vybrať ikonu">'
      : '<div class="controller-avatar">';
    const avatarEnd = this._editing?.id === controller.id ? '</button>' : '</div>';
    return '<article class="row ' + status.color + (this._editing?.id === controller.id ? ' editing' : '') +
      '" data-controller-id="' + esc(controller.id) + '">' +
      '<div class="controller-summary">' +
      '<div class="identity">' +
        '<div class="controller-control">' + avatar + '<ha-icon class="controller-icon" data-controller-icon="' +
          esc(controller.icon || "mdi:home-automation") + '" icon="' +
          esc(controller.icon || "mdi:home-automation") + '"></ha-icon>' + avatarEnd + toggle + '</div>' +
        '<strong class="controller-name">' + esc(title) + '</strong>' + editButton +
        '<div class="status"><div class="status-head"><div class="status-label"><i></i><b>' +
          esc(status.label) + '</b></div>' + (status.countdown
            ? '<span class="status-countdown">' + esc(status.countdown) + '</span>' : '') +
          '</div><div class="status-meta"><span class="status-detail">' + esc(status.detail) +
          '</span><small>' + esc(status.changedAt) + '</small></div></div>' +
      '</div>' +
      '<div class="chips entities">' + groupedChips + '</div>' +
      '<div class="timeline-line">' + this._timeline(controller) + '</div>' +
      '</div>' +
      (this._editing?.id === controller.id ? this._editor(controller) : '') +
      '</article>';
  }

  _editor(controller) {
    controller._liveForm ||= structuredClone(controller.form || {});
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
    let helpIndex = 0;
    const help = (label, text) => {
      const id = "help-" + controller.id + "-" + (++helpIndex);
      return '<button type="button" class="field-help" data-help="' + esc(id) +
        '" aria-label="Pomoc: ' + esc(label) + '" aria-controls="' + esc(id) +
        '" aria-expanded="false">?</button><div id="' + esc(id) +
        '" class="help-popover" popover role="note">' + esc(text) + '</div>';
    };
    const parameters = (section, key, off = false) => {
      const data = form[section]?.[key] || {};
      const lights = (basic.control_entities || controller.outputs || []).filter(id => id.startsWith("light."));
      const fans = (basic.control_entities || controller.outputs || []).some(id => id.startsWith("fan."));
      if (!lights.length && !fans && !Object.keys(data).length) return '';
      const nightProfile = section === "night";
      const attrs = lights.map(id => this._hass?.states?.[id]?.attributes || {});
      const brightnessSupported = attrs.every(a => !a.supported_color_modes || a.supported_color_modes.some(mode => mode !== 'onoff'));
      const temperatureSupported = attrs.every(a => !a.supported_color_modes || a.supported_color_modes.includes('color_temp'));
      const colorSupported = attrs.every(a => !a.supported_color_modes || a.supported_color_modes.some(mode => ['hs','xy','rgb','rgbw','rgbww'].includes(mode)));
      const minimum = Math.max(1500, ...attrs.map(a => Number(a.min_color_temp_kelvin) || 1500));
      const maximum = Math.min(10000, ...attrs.map(a => Number(a.max_color_temp_kelvin) || 10000));
      const attr = name => ' data-service-section="' + section + '" data-service-key="' + key + '" data-service-param="' + name + '"';
      const control = (name, label, value, min, max, step, unit, active, accent = '') =>
        '<div class="parameter-setting"><label class="parameter-label"><input type="checkbox"' + attr(name) +
        ' data-param-enable="true"' + (active ? ' checked' : '') + '><span>' + label + '</span></label>' +
        '<div class="parameter-inputs"><input type="range" min="' + min + '" max="' + max + '" step="' + step +
        '" value="' + esc(value) + '" aria-label="' + label + ' posuvník"' + attr(name) +
        (accent ? ' style="' + accent + '"' : '') + (active ? '' : ' disabled') + '>' +
        '<input type="number" min="' + min + '" max="' + max + '" step="' + step + '" value="' + esc(value) +
        '" aria-label="' + label + ' presná hodnota"' + attr(name) + (active ? '' : ' disabled') + ' required><small>' + unit + '</small></div></div>';
      const brightness = data.brightness_pct ?? Math.round(Number(data.brightness ?? 255) / 255 * 100);
      const kelvin = data.color_temp_kelvin ?? data.kelvin ?? (data.color_temp ? Math.round(1000000 / data.color_temp) : 3000);
      const effects = [...new Set(attrs[0]?.effect_list || [])].filter(effect => attrs.every(a => (a.effect_list || []).includes(effect)));
      const rgb = data.rgb_color || [255, 255, 255];
      const color = '#' + rgb.slice(0, 3).map(v => Number(v).toString(16).padStart(2, '0')).join('');
      return '<details class="parameter-editor" data-editor-section="' + section + '-' + key + '"><summary><span>' +
        (off ? 'Pri vypnutí' : nightProfile ? 'Nočné svetlo' : 'Svetlo pri zapnutí') + '</span><small>' +
        esc(Object.keys(data).length ? this._parameterText(data) : nightProfile ? 'Podľa denného profilu' : 'Pôvodné hodnoty') +
        '</small><ha-icon icon="mdi:chevron-down"></ha-icon></summary><div class="parameter-fields">' +
        '<div class="section-title parameter-help"><span>' + (nightProfile ? 'Nočné parametre' : 'Parametre zariadení') + '</span>' +
        help(key, 'Zaškrtni iba hodnoty, ktoré má automatika meniť. Prázdny nočný profil preberá denné hodnoty. Pôvodné hodnoty sa obnovia pri skončení riadenia; vypnuté svetlo sa kvôli obnove nezapne. Ručne zmenené hodnoty majú prednosť.') + '</div>' +
        (!off && lights.length ? (brightnessSupported ? control('brightness_pct', 'Jas', brightness, 0, 100, 1, '%', data.brightness_pct != null || data.brightness != null) : '') +
          (temperatureSupported && minimum <= maximum ? control('color_temp_kelvin', 'Teplota', kelvin, minimum, maximum, 1, 'K', data.color_temp_kelvin != null || data.kelvin != null || data.color_temp != null,
            'background:linear-gradient(90deg,#ffb35c,#f6f4ee,#9fcaff)') : '') +
          (colorSupported ? '<div class="parameter-setting"><label class="parameter-label"><input type="checkbox"' + attr('rgb_color') +
          ' data-param-enable="true"' + (data.rgb_color ? ' checked' : '') + '><span>Farba</span></label><input type="color" value="' + esc(color) +
          '" aria-label="Farba svetla"' + attr('rgb_color') + (data.rgb_color ? '' : ' disabled') + '></div>' : '') +
          (effects.length || data.effect ? '<label class="parameter-setting"><span>Efekt</span><select aria-label="Efekt svetla"' + attr('effect') +
            '><option value="">Pôvodný efekt</option>' + [...new Set([...effects, ...(data.effect ? [data.effect] : [])])].map(effect =>
              '<option value="' + esc(effect) + '"' + (data.effect === effect ? ' selected' : '') + '>' + esc(effect) + '</option>').join('') + '</select></label>' : '') : '') +
        (!off && fans ? control('percentage', 'Výkon ventilátora', data.percentage ?? 50, 0, 100, 1, '%', data.percentage != null) : '') +
        (lights.length ? control('transition', 'Plynulý prechod', data.transition ?? 1, 0, 3600, 0.1, 's', data.transition != null) : '') +
        '</div></details>';
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
      return '<section class="entity-card"><div class="card-heading"><div class="card-heading-icon"><ha-icon icon="mdi:home-import-outline"></ha-icon></div>' +
        '<div class="card-heading-copy section-title"><h3>' + esc(title) +
        '</h3>' + help(title, hint) + '</div></div>' + chips + extraMarkup +
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
      const enabledKey = prefix === "night" ? "night_mode_enabled" : "constraint_enabled";
      const startKey = prefix + "_start_time";
      const endKey = prefix + "_end_time";
      const startSourceKey = prefix + "_start_source";
      const endSourceKey = prefix + "_end_source";
      const startSource = form[section]?.[startSourceKey] || (prefix === "night" ? "sunset" : "fixed");
      const endSource = form[section]?.[endSourceKey] || (prefix === "night" ? "sunrise" : "fixed");
      const resolved = controller.resolved_schedule?.[prefix] || {};
      const storedStart = timeMinutes(form[section]?.[startKey], startDefault);
      const storedEnd = timeMinutes(form[section]?.[endKey], endDefault);
      const start = this._scheduleMinutes(controller, prefix, "start", startSource, storedStart, resolved.start);
      const end = this._scheduleMinutes(controller, prefix, "end", endSource, storedEnd, resolved.end);
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
        (source !== "fixed"
          ? (() => {
            const offsetKey = prefix + "_" + side + "_offset_seconds";
            const offset = Number(form[section]?.[offsetKey] || 0) / 60;
            const abs = Math.abs(offset);
            const label = offset === 0 ? "0 min" : (offset > 0 ? "+" : "−") +
              (Math.floor(abs / 60) ? Math.floor(abs / 60) + " h" + (abs % 60 ? " " + abs % 60 + " min" : "") : abs + " min");
            return '<div class="offset-control"><button type="button" data-offset-step="-15" data-section="' + esc(section) +
              '" data-field="' + esc(offsetKey) + '" aria-label="Znížiť posun o 15 minút">−</button><output>' + esc(label) +
              '</output><button type="button" data-offset-step="15" data-section="' + esc(section) + '" data-field="' +
              esc(offsetKey) + '" aria-label="Zvýšiť posun o 15 minút">+</button></div>';
          })() : '') + '</label>';
      return '<section class="editor-card schedule-card schedule-card-' + prefix + ' ' + (enabled ? 'enabled' : '') + '"><div class="card-heading schedule-heading">' +
        '<div class="card-heading-icon"><ha-icon icon="mdi:clock-time-four-outline"></ha-icon></div>' +
        '<div class="card-heading-copy"><h3>' + esc(title) + '</h3><p>' +
        esc(enabled ? timeText(start) + ' – ' + timeText(end) + ' každý deň' : 'Neaktívne') + '</p></div>' +
        '<label class="switch-setting"><span>' + (enabled ? 'Zapnuté' : 'Vypnuté') + '</span><input type="checkbox"' +
        ' data-section="' + esc(section) + '" data-field="' + esc(enabledKey) + '"' +
        (enabled ? ' checked' : '') + '><i></i></label></div>' +
        (enabled ? '<div class="schedule-content"><div class="schedule-track" aria-label="' + esc(title) + '">' +
          '<div class="schedule-fill" style="background:' + esc(scheduleStyle) + '"></div>' +
          '<input class="schedule-range start" type="range" min="0" max="1439" step="1" value="' + start + '"' +
          ' aria-label="Začiatok intervalu" data-kind="schedule-time" data-section="' + esc(section) + '" data-field="' +
          esc(startKey) + '">' +
          '<input class="schedule-range end" type="range" min="0" max="1439" step="1" value="' + end + '"' +
          ' aria-label="Koniec intervalu" data-kind="schedule-time" data-section="' + esc(section) + '" data-field="' +
          esc(endKey) + '"></div>' +
          '<div class="schedule-labels"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span></div>' +
          '<div class="schedule-endpoints">' + endpoint("start", "Od", start, startSource, startKey, startSourceKey) +
          endpoint("end", "Do", end, endSource, endKey, endSourceKey) + '</div>' +
          (prefix === "night" ? '<div class="schedule-extra">' + this._durationField(section, "night_delay_seconds", form[section]?.night_delay_seconds || 0, "Nočný časovač") + '</div>' + parameters('night', 'night_service_data_on') + parameters('night', 'night_service_data_off', true) : '') +
          '</div>' : '') + '</section>';
    };
    const behaviorField = (section, key, value, label, options) =>
      '<label class="field"><span>' + esc(label) + '</span><select data-section="' + esc(section) + '" data-field="' +
      esc(key) + '" data-kind="select">' + options.map(([option, text]) => '<option value="' + esc(option) + '"' +
        (value === option ? ' selected' : '') + '>' + esc(text) + '</option>').join("") + '</select></label>' +
        (value === 'custom' ? '<div class="lifecycle-editor"><label class="field"><span>Scéna</span><select data-scene-hook="' + esc(key) + '">' +
          '<option value="">Vlastné akcie</option>' + Object.entries(this._hass?.states || {}).filter(([id]) => id.startsWith('scene.')).map(([id,state]) =>
            '<option value="' + esc(id) + '"' + ((actions.lifecycle_actions?.[key]?.[0]?.target?.entity_id === id) ? ' selected' : '') + '>' +
              esc(state.attributes?.friendly_name || id) + '</option>').join('') + '</select></label><ha-form data-native-action="' + esc(key) +
          '"></ha-form><p class="native-loading">Načítavam grafický editor Home Assistant…</p></div>' : '');
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
      if (key.startsWith('on_')) return behaviorField(section, key, value, label,
        [["on", "Zapnúť entity"], ["off", "Vypnúť entity"], ["ignore", "Nič nerobiť"], ["restore", "Obnoviť pôvodný stav"], ["custom", "Scéna / vlastné akcie"]]);
      if (booleanField) return '<label class="switch-setting"><span>' + esc(label) + '</span><input type="checkbox" data-section="' + esc(section) +
        '" data-field="' + esc(key) + '"' + (Boolean(value) ? ' checked' : '') + '><i></i></label>';
      if (key.endsWith("_offset_seconds")) return '<label class="field"><span>' + esc(label) + '</span><div class="offset-control"><input type="number" step="5" data-kind="offset-minutes" data-section="' +
        esc(section) + '" data-field="' + esc(key) + '" value="' + esc(Number(value || 0) / 60) + '"><small>minút</small></div></label>';
      if (["delay_seconds", "block_timeout_seconds", "backoff_max_seconds", "night_delay_seconds"].includes(key)) {
        return this._durationField(section, key, value, label);
      }
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
      ["initial_state", "Predvolené správanie", null],
      ["actions", "Akcie pri ďalších stavoch", ["on_enter_idle", "on_exit_idle", "on_enter_overridden", "on_exit_overridden", "on_enter_constrained", "on_exit_constrained", "on_enter_blocked", "on_exit_blocked"]],
      ["advanced", "Pokročilé stavy a kompatibilita", null],
    ];
    const advancedMarkup = mode === "full" ? advanced.map(([section, title, fields]) => {
      const values = form[section] || {};
      const entries = Object.entries(values).filter(([key]) => fields === null || fields.includes(key));
      const hints = {
        sensor_type: 'Udalosť reaguje na nový pohyb. Trvanie drží aktivitu, kým je spúšťač zapnutý.',
        backoff_enabled: 'Pri opakovanej aktivite môže automatika postupne predlžovať čas do vypnutia.',
        backoff_factor: 'Násobok času pri ďalšom predĺžení. Napríklad 2 znamená dvojnásobok.',
        backoff_max_seconds: 'Horná hranica postupne predlžovaného časovača.',
        block_timeout_seconds: 'Po tomto čase sa zruší dočasné blokovanie. Nula vypne automatické odblokovanie.',
        enabled_default: 'Počiatočná hodnota pri vytvorení controllera; aktuálne zapnutie ovláda hlavný prepínač.',
        stay_mode_default: 'Počiatočný trvalý režim bez bežného odpočtu.',
        state_attributes_ignore: 'Atribúty, ktorých zmenu automatika nepovažuje za ručný zásah. Oddeľ ich čiarkami.',
      };
      const contents = entries.map(([key, value]) => '<div class="advanced-setting">' + renderField(section, key, value) +
        help(FIELD_LABELS[key] || key, hints[key] || (key.startsWith('on_') ? 'Akcia pri tomto prechode stavu. Nič nerobiť zachová stav zariadení.' :
          'Hodnoty stavu entity oddeľ čiarkami. Aktívny a neaktívny stav majú samostatné mapovanie.')) + '</div>').join("");
      return contents ? '<details class="editor-section editor-card" data-editor-section="' + esc(section) + '"><summary><span>' + esc(title) +
        '</span><ha-icon icon="mdi:chevron-down"></ha-icon></summary><div class="advanced-fields">' + contents + '</div></details>' : '';
    }).join("") : '';
    const diagnosticReason = controller.block_reason === "interlock" ? "Zastavené pravidlom Interlock" :
      controller.block_reason === "controlled_entity_on" ? "Zapnuté ovládané zariadenie bráni automatickému zásahu" :
        controller.last_transition_cause === "manual_control" ? "Poslednú zmenu spôsobil ručný zásah" :
          controller.block_reason || controller.next_transition_label || "Bez aktívneho blokovania";
    const diagnosticEntities = [...new Set([
      ...(controller.active_triggers || []), ...(controller.active_state_entities || []),
      ...(controller.active_overrides || []), ...(controller.active_interlocks || []),
      ...(Array.isArray(controller.blocked_by) ? controller.blocked_by : controller.blocked_by ? [controller.blocked_by] : []),
    ])];
    const diagnosticMarkup = mode === "full"
      ? '<details class="editor-section editor-card" data-editor-section="decision"><summary><span>Rozhodnutie teraz</span><ha-icon icon="mdi:chevron-down"></ha-icon></summary>' +
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
    const behaviorOptions = [["on", "Zapnúť entity"], ["off", "Vypnúť entity"], ["ignore", "Nič nerobiť"], ["restore", "Obnoviť pôvodný stav"], ["custom", "Scéna / vlastné akcie"]];
    return '<section class="editor"><header class="editor-header"><div class="editor-heading"><h2>Nastavenia controllera</h2>' +
      '<span class="save-state" role="status">' + esc(this._savingControllers.has(controller.id)
        ? "Ukladám…" : this._saveErrors.get(controller.id) ||
          (this._dirtyControllers.has(controller.id) ? "Neuložené zmeny" : "Uložené")) +
      '</span></div><div class="editor-toolbar"><div class="edit-modes" role="group" aria-label="Rozsah nastavení">' +
      '<button type="button" data-mode="basic" class="' + (mode === "basic" ? "selected" : "") + '">Základné</button>' +
      '<button type="button" data-mode="full" class="' + (mode === "full" ? "selected" : "") + '">Všetky nastavenia</button></div>' +
      '<div class="editor-buttons"><button type="button" class="editor-save" data-save="' + esc(controller.id) + '"' +
      (this._dirtyControllers.has(controller.id) && !this._savingControllers.has(controller.id) ? '' : ' disabled') +
      '>Uložiť</button><button type="button" class="editor-close" data-close="' + esc(controller.id) + '">Zavrieť</button></div></div></header>' +
      '<div class="editor-grid"><section class="editor-card identity-card"><div class="card-heading"><div class="card-heading-icon"><ha-icon icon="mdi:tune-variant"></ha-icon></div>' +
      '<div class="card-heading-copy"><h3>Názov a ikona</h3></div></div>' +
      '<div class="card-fields">' + renderField("basic", "name", basic.name || controller.name) +
      '<div class="icon-picker"><button type="button" class="add-entity" data-icon-toggle="editor"><ha-icon icon="' +
      esc(basic.icon || controller.icon || "mdi:home-automation") + '"></ha-icon> Vybrať ikonu</button>' +
      (this._iconPickerOpen ? '<ha-form data-native-icon="true"></ha-form><div class="icon-fallback"><input class="entity-search icon-search" type="search" placeholder="Hľadať ikonu" aria-label="Hľadať ikonu">' +
        '<div class="icon-options">' + ["home-automation", "lightbulb", "motion-sensor", "door", "door-open", "window-open", "weather-sunset", "weather-sunset-up", "clock-outline", "timer-outline", "account", "account-group", "shield-check", "shield-lock", "gesture-tap-button", "power", "toggle-switch", "fan", "air-conditioner", "thermostat", "water", "smoke-detector", "bell", "robot", "tune-variant"].map((name) =>
          '<button type="button" class="icon-option" data-icon-value="mdi:' + name + '" aria-label="mdi:' + name + '"><ha-icon icon="mdi:' + name + '"></ha-icon><span>' + name.replaceAll("-", " ") + '</span></button>').join("") + '</div></div>' : '') + '</div></div>' +
      '</section>' +
      '<section class="editor-card live-decision" aria-label="Čo sa stane teraz">' + this._decisionSummary(controller) + '</section>' +
      '<div class="editor-column inputs-column"><section class="editor-card inputs-card"><h3 class="group-title">Vstupy</h3>' +
      '<div class="activation-inputs">' + entityPicker("basic", "trigger_entities", "Spúšťače", "Čo aktivuje miestnosť?", ["binary_sensor", "sensor", "input_boolean", "switch", "light", "fan", "event", "device_tracker"]) +
      '<details class="presence-editor" data-editor-section="presence"' + (basic.presence_entities?.length ? ' open' : '') + '><summary>Prítomnosť / podržanie<ha-icon icon="mdi:chevron-down"></ha-icon></summary>' +
      entityPicker("basic", "presence_entities", "Senzory prítomnosti", "Samy nezapínajú svetlo. Držia aktívnu miestnosť, kým niekto zostáva vnútri. Po odchode sa spustí bežný časovač.", ["binary_sensor", "sensor", "input_boolean", "device_tracker"]) + '</details></div>' +
      entityPicker("monitoring", "state_entities", "Sledované entity", "Ich zapnutý stav môže pozastaviť automatiku.",
        ["binary_sensor", "sensor", "input_boolean", "device_tracker"],
        '<label class="switch-setting"><span>Povoliť blokovanie</span><input type="checkbox" data-section="monitoring" data-field="blocking_enabled"' +
        (monitoring.blocking_enabled !== false ? ' checked' : '') + '><i></i></label>') + '</section>' +
      schedule("constraints", "Povolený čas", "constraint", Boolean(constraints.constraint_enabled), "06:00", "23:00") + '</div>' +
      '<div class="editor-column behavior-column"><section class="editor-card behavior-card"><h3 class="group-title">Ovládanie a časovanie</h3>' +
      entityPicker("basic", "control_entities", "Ovládané entity", "Zariadenia, ktoré sa zapnú alebo vypnú pri zmene stavu.", ["light", "switch", "fan"]) +
      '<section class="settings-group timing-card"><div class="card-heading"><div class="card-heading-icon"><ha-icon icon="mdi:timer-outline"></ha-icon></div>' +
      '<div class="card-heading-copy section-title"><h3>Časovanie</h3>' + help("Časovanie", "Po poslednej aktivite sa spustí odpočet. Čas môžeš nastaviť posuvníkom alebo vpísať v sekundách.") + '</div></div>' +
      '<div class="duration-setting">' + duration + '</div>' + resetTimer + '</section>' +
      '<section class="settings-group editor-actions"><div class="card-heading"><div class="card-heading-icon"><ha-icon icon="mdi:gesture-tap-button"></ha-icon></div>' +
      '<div class="card-heading-copy section-title"><h3>Akcia controllera</h3>' + help("Akcia controllera", "Vyber, čo sa má stať pri aktivácii a po skončení aktivity.") + '</div></div><div class="card-fields">' +
      behaviorField("actions", "on_enter_active", actions.on_enter_active || "on", "Pri aktivácii", behaviorOptions) +
      behaviorField("actions", "on_exit_active", actions.on_exit_active || "off", "Po skončení aktivity", behaviorOptions) + '</div>' +
      '<div class="parameter-pair">' + parameters('actions', 'service_data_on') + parameters('actions', 'service_data_off', true) + '</div></section></section>' +
      schedule("night", "Nočný profil", "night", Boolean(night.night_mode_enabled), "20:00", "06:00") + '</div>' +
      '<details class="editor-card rules-card" data-editor-section="rules"><summary>Priorita a blokovanie<ha-icon icon="mdi:chevron-down"></ha-icon></summary><div class="rule-groups">' +
      entityPicker("rules", "override_entities", "Override", "Prevezme prioritu podľa vstupného stavu.", ["binary_sensor", "sensor", "input_boolean", "switch", "light", "device_tracker"]) +
      entityPicker("rules", "interlock_entities", "Interlock", "Blokuje automatické riadenie, kým je vstup aktívny.", ["binary_sensor", "sensor", "input_boolean", "switch", "light", "device_tracker"]) +
      '<div class="manual-controls"><div class="section-title"><h3>Ručné riadenie</h3>' + help('Ručné riadenie','Ručné vypnutie, zapnutie alebo úprava svetla dostane prednosť počas obsadenia miestnosti. Automatika sa pripraví na nový pohyb až po uvoľnení spúšťačov a prítomnosti.') + '</div>' +
      renderField('monitoring','protect_manual_off',monitoring.protect_manual_off !== false) +
      renderField('monitoring','protect_manual_on',monitoring.protect_manual_on !== false) + '</div>' +
      '</div></details>' + advancedMarkup + diagnosticMarkup + '</div></section>';
  }

  _formatDuration(seconds) {
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    const minutes = Math.floor(total / 60);
    const remainder = total % 60;
    if (minutes && remainder) return minutes + ' min ' + String(remainder).padStart(2, '0') + ' s';
    if (minutes) return minutes + (minutes === 1 ? ' min' : ' min');
    return remainder + ' s';
  }

  _parameterText(data) {
    const parts = [];
    if (data.brightness_pct != null || data.brightness != null) parts.push('Jas ' +
      (data.brightness_pct ?? Math.round(data.brightness / 255 * 100)) + ' %');
    if (data.color_temp_kelvin != null || data.kelvin != null || data.color_temp != null) parts.push(
      (data.color_temp_kelvin ?? data.kelvin ?? Math.round(1000000 / data.color_temp)) + ' K');
    if (data.rgb_color) parts.push('Vlastná farba');
    if (data.effect) parts.push(data.effect);
    if (data.percentage != null) parts.push('Výkon ' + data.percentage + ' %');
    if (data.transition != null) parts.push('Prechod ' + data.transition + ' s');
    return parts.join(' · ') || (Object.keys(data).length ? 'Vlastné parametre' : 'Pôvodné hodnoty');
  }

  async _ensureNativeEditors() {
    if (customElements.get('ha-form')) {this._bindNativeEditors(); return;}
    if (this._nativeLoadFailed) {this._showNativeLoadFailure(); return;}
    if (this._nativeLoading) return;
    this._nativeLoading = true;
    try {
      if (!window.loadCardHelpers) {
        // A direct sidebar visit may precede Lovelace. Load its registered HA
        // route module without navigation, dashboard rendering or guessed URLs.
        const roots = [document];
        let resolver;
        while (roots.length && !resolver) {
          const root = roots.shift();
          resolver = root.querySelector('partial-panel-resolver');
          if (!resolver) root.querySelectorAll('*').forEach(el => {if (el.shadowRoot) roots.push(el.shadowRoot);});
        }
        const route = Object.values(resolver?.routerOptions?.routes || {}).find(item => item.tag === 'ha-panel-lovelace');
        if (!route?.load) throw new Error('HA neposkytol načítanie editora');
        await route.load();
      }
      const helpers = await window.loadCardHelpers();
      const card = helpers.createCardElement({type: 'entities', entities: []});
      await card.constructor.getConfigElement?.();
      if (!customElements.get('ha-form')) throw new Error('Editor HA sa nenačítal');
      this._bindNativeEditors();
    } catch (error) {
      this._nativeLoadFailed = true;
      this._showNativeLoadFailure();
    } finally {this._nativeLoading = false;}
  }

  _showNativeLoadFailure() {
    this.shadowRoot.querySelectorAll('.native-loading').forEach(el => {
      el.innerHTML = 'Grafický editor sa nepodarilo načítať. <button type="button" data-native-retry>Skúsiť znova</button>';
    });
  }

  _bindNativeEditors() {
    if (!customElements.get('ha-form')) return;
    const controller = this.controllers.find(item => item.id === this._editing?.id);
    if (!controller) return;
    this.shadowRoot.querySelectorAll('ha-form[data-native-action],ha-form[data-native-icon]').forEach(form => {
      const icon = Boolean(form.dataset.nativeIcon);
      const key = form.dataset.nativeAction;
      form.hass = this._hass;
      form.narrow = this.shadowRoot.querySelector('.wrap').clientWidth < 620;
      form.schema = [{name: icon ? 'icon' : 'sequence', selector: icon ? {icon: {}} : {action: {}}}];
      form.computeLabel = () => icon ? 'Ikona' : 'Akcie';
      const data = icon ? {icon: controller.form?.basic?.icon || controller.icon} :
        {sequence: controller.form?.actions?.lifecycle_actions?.[key] || []};
      if (JSON.stringify(form.data) !== JSON.stringify(data)) form.data = data;
      form.setAttribute('data-native-ready', 'true');
      form.parentElement.querySelector('.native-loading')?.setAttribute('hidden', '');
      if (icon) form.parentElement.querySelector('.icon-fallback')?.setAttribute('hidden', '');
      if (form._ecBound) return;
      form._ecBound = true;
      form.addEventListener('value-changed', event => {
        event.stopPropagation();
        const current = this.controllers.find(item => item.id === this._editing?.id);
        if (!current || !form.isConnected) return;
        const next = structuredClone(current.form || {});
        if (icon) {next.basic ||= {}; next.basic.icon = event.detail.value.icon;}
        else {next.actions ||= {}; next.actions.lifecycle_actions ||= {}; next.actions.lifecycle_actions[key] = event.detail.value.sequence || [];}
        current.form = next;
        this._markControllerDirty(current);
        if (icon) {this._rowMarkup.clear(); this._render(true); this._refreshControllerIcons();}
      });
    });
  }

  _scheduleMinutes(controller, prefix, side, source, stored, fallback) {
    if (source === 'fixed') return stored;
    const solar = controller.resolved_schedule?.solar?.[source];
    const section = prefix === 'night' ? 'night' : 'constraints';
    if (solar == null) return fallback ?? stored;
    const offset = Number(controller.form?.[section]?.[prefix + '_' + side + '_offset_seconds'] || 0) / 60;
    return ((solar + offset) % 1440 + 1440) % 1440;
  }

  _decisionSummary(controller) {
    const state = stateKey(controller.state);
    const liveForm = controller._liveForm || controller.form || {};
    const profile = controller.night_active ? 'Nočný' : 'Denný';
    const params = controller.night_active && Object.keys(liveForm.night?.night_service_data_on || {}).length
      ? liveForm.night.night_service_data_on : liveForm.actions?.service_data_on || {};
    const remaining = controller.expires_at ? Math.max(0, (new Date(controller.expires_at) - Date.now()) / 1000) : null;
    const reason = controller.active_interlocks?.length ? 'Aktívne blokovacie pravidlo' :
      controller.active_overrides?.length ? 'Riadenie prevzal Override' :
      controller.block_reason?.startsWith('manual') || controller.last_transition_cause === 'manual_control' ? 'Ručné riadenie má prednosť' :
      state === 'constrained' ? 'Mimo povoleného času' : state === 'disabled' ? 'Automatika je vypnutá' :
      state === 'active_stay_on' ? 'Trvalý režim bez odpočtu' : state === 'active_timer' ?
        (controller.timer_expired_pending_sensor ? 'Čaká na uvoľnenie spúšťača' : 'Nová aktivita môže predĺžiť čas') : 'Čaká na aktivitu';
    const countdown = controller.presence_active && state === 'active_timer' ? 'Drží prítomnosť' : state === 'active_timer' && remaining != null ? this._formatDuration(remaining) :
      state === 'active_stay_on' ? 'Bez časového limitu' : 'Odpočet nebeží';
    const next = controller.next_transition_at ? (controller.next_transition_label || 'Plánovaná zmena') + ' · ' +
      new Date(controller.next_transition_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : 'Žiadna naplánovaná zmena';
    const draft = controller.form || {};
    const dirty = this._dirtyControllers.has(controller.id);
    const helpId = 'decision-help-' + controller.id;
    const help = '<button type="button" class="field-help" data-help="' + esc(helpId) +
      '" aria-label="Pomoc: aktuálne rozhodnutie" aria-controls="' + esc(helpId) +
      '" aria-expanded="false">?</button><div id="' + esc(helpId) +
      '" class="help-popover" popover role="note">' + esc(reason + '. ' + next +
      '. Odpočet neznamená automatické vypnutie pri ručnom riadení alebo Override. Neuložený návrh ešte neovplyvňuje bežiaci profil.') + '</div>';
    return '<div class="decision-heading"><h3>Čo sa stane teraz ' + help + '</h3><span class="live-badge">Bežiace nastavenie</span></div>' +
      '<div class="decision-metrics"><div title="' + esc(reason) + '"><span>Stav</span><strong>' + esc(STATES[state].label) + '</strong><small>' + esc(reason) + '</small></div>' +
      '<div><span>Zostáva do konca aktivity</span><strong data-decision-countdown title="Čas aktivity nie je zárukou vypnutia pri Override alebo ručnom riadení.">' + esc(countdown) + '</strong></div>' +
      '<div title="' + esc(next) + '"><span>' + profile + ' profil</span><strong>' + esc(this._parameterText(params)) + '</strong><small>' +
      esc(next) + '</small></div></div>' + (dirty ? '<div class="draft-preview"><b>Neuložený návrh</b><span>Po poslednej aktivite ' +
        esc(this._formatDuration(durationSeconds(draft.basic?.delay_seconds))) + ' · ' + esc(this._parameterText(draft.actions?.service_data_on || {})) +
        (draft.night?.night_mode_enabled ? ' · Noc: ' + esc(this._formatDuration(durationSeconds(draft.night.night_delay_seconds))) + ' / ' +
          esc(this._parameterText(Object.keys(draft.night.night_service_data_on || {}).length ? draft.night.night_service_data_on : draft.actions?.service_data_on || {})) : '') + '</span></div>' : '');
  }

  _updateServiceParameter(field) {
    const controller = this.controllers.find(item => item.id === this._editing?.id);
    if (!controller || !field.isConnected) return;
    const section = field.dataset.serviceSection;
    const key = field.dataset.serviceKey;
    const param = field.dataset.serviceParam;
    const form = structuredClone(controller.form || {});
    form[section] ||= {};
    const data = {...form[section][key]};
    const group = field.closest('.parameter-editor');
    const controls = [...group.querySelectorAll('[data-service-param]')].filter(el => el.dataset.serviceParam === param);
    const enabling = field.dataset.paramEnable;
    const valueField = enabling ? controls.find(el => el.type !== 'checkbox' && el.type !== 'range') : field;
    if (!enabling && !field.checkValidity()) {
      this._markControllerDirty(controller);
      this._saveErrors.set(controller.id, 'Skontroluj zvýraznenú hodnotu.');
      this._updateEditorStatus(controller);
      return;
    }
    const aliases = param === 'brightness_pct' ? ['brightness', 'brightness_pct'] :
      ['color_temp_kelvin', 'rgb_color'].includes(param) ? ['kelvin','color_temp','color_temp_kelvin','rgb_color','rgbw_color','rgbww_color','hs_color','xy_color'] : [param];
    aliases.forEach(alias => delete data[alias]);
    if (!(enabling && !field.checked) && valueField.value !== '') {
      data[param] = param === 'rgb_color' ? valueField.value.slice(1).match(/../g).map(hex => parseInt(hex,16)) :
        param === 'effect' ? valueField.value : Number(valueField.value);
    }
    form[section][key] = data;
    controller._liveForm ||= structuredClone(controller.form || {});
    controller.form = form;
    controls.forEach(el => {
      if (el.type !== 'checkbox') {
        el.disabled = Boolean(enabling && !field.checked);
        if (!enabling && el !== field) el.value = field.value;
      }
    });
    this._markControllerDirty(controller);
    // Colour and white temperature are exclusive; rebuild only after enabling.
    if (enabling) {field.blur(); this._rowMarkup.clear(); this._render();}
    else {
      const summary = group.querySelector('summary small');
      if (summary) summary.textContent = this._parameterText(data);
    }
  }

  _durationField(section, key, value, label) {
    const seconds = durationSeconds(value);
    const maximum = Math.max(7200, Math.ceil(seconds / 3600) * 3600);
    return '<label class="duration-control"><span>' + esc(label) + '</span><div class="duration-input"><input type="range" min="0" max="' + maximum +
      '" step="30" value="' + seconds + '" data-kind="duration" data-section="' + esc(section) + '" data-field="' + esc(key) + '">' +
      '<div class="duration-manual"><input type="number" min="0" max="31536000" step="1" value="' + seconds +
      '" data-kind="duration" data-duration-manual="' + esc(section + "." + key) + '" data-section="' + esc(section) +
      '" data-field="' + esc(key) + '" aria-label="' + esc(label + " v sekundách") + '"><span>s</span></div></div>' +
      '<output class="duration-value" data-duration-for="' + esc(section + "." + key) + '">' +
      esc(this._formatDuration(seconds)) + '</output></label>';
  }

  _render(preserveEditor = false) {
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
        '.controller-control{grid-column:1;grid-row:1/3;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;gap:4px}.controller-avatar{width:36px;height:36px;flex:none;border:0;padding:0;border-radius:50%;display:flex;align-items:center;justify-content:center;background:color-mix(in srgb,var(--ec-row-color) 18%,var(--ha-card-background,var(--card-background-color)));color:var(--ec-row-color)}button.controller-avatar{cursor:pointer}.controller-icon{color:var(--ec-row-color);--mdc-icon-size:24px}.controller-name{grid-column:2;grid-row:1;align-self:center;min-width:0;font-size:16px;line-height:20px;font-weight:var(--mush-card-primary-font-weight,500);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
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
      const interactionStyles = '.duration-input{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:10px}.duration-value{min-width:56px;color:var(--primary-text-color);font-size:12px;font-weight:600;text-align:right;font-variant-numeric:tabular-nums}.duration-setting{display:block}.duration-setting .duration-control{display:flex;flex-direction:column;gap:6px}.duration-setting .duration-control>span{color:var(--secondary-text-color);font-size:11px}.duration-setting .duration-control input{width:100%;accent-color:var(--primary-color)}.editor-grid{grid-template-columns:repeat(12,minmax(0,1fr));gap:10px}.editor-card{padding:10px;border-color:color-mix(in srgb,var(--divider-color) 65%,transparent);background:color-mix(in srgb,var(--secondary-background-color,var(--card-background-color)) 72%,transparent);box-shadow:none}.editor-grid>.identity-card{grid-column:span 4}.editor-grid>.entity-card:nth-child(2),.editor-grid>.entity-card:nth-child(4){grid-column:span 6}.editor-grid>.entity-card:nth-child(3),.editor-grid>.timing-card{grid-column:span 3}.editor-grid>.schedule-card,.editor-grid>.editor-actions{grid-column:span 6}.editor-grid>.rules-card,.editor-grid>.editor-section{grid-column:1/-1}.icon-options{display:grid;grid-template-columns:repeat(auto-fill,minmax(105px,1fr));gap:4px;max-height:190px;overflow:auto;margin-top:6px}.icon-option{display:flex;align-items:center;gap:6px;min-height:34px;padding:4px 7px;border:0;border-radius:7px;background:var(--primary-background-color,var(--card-background-color));color:var(--primary-text-color);text-align:left;cursor:pointer}.icon-option ha-icon{--mdc-icon-size:18px;color:var(--primary-color)}.icon-option span{font-size:11px;text-transform:capitalize}.icon-picker{min-width:0}@media(max-width:1000px){.editor-grid{grid-template-columns:repeat(6,minmax(0,1fr))}.editor-grid>.identity-card{grid-column:span 3}.editor-grid>.entity-card:nth-child(2),.editor-grid>.entity-card:nth-child(4),.editor-grid>.schedule-card,.editor-grid>.editor-actions{grid-column:span 3}.editor-grid>.entity-card:nth-child(3),.editor-grid>.timing-card{grid-column:span 3}}@media(max-width:760px){.editor-grid{grid-template-columns:minmax(0,1fr)}.editor-grid>.identity-card,.editor-grid>.entity-card,.editor-grid>.timing-card,.editor-grid>.schedule-card,.editor-grid>.editor-actions,.editor-grid>.rules-card,.editor-grid>.editor-section{grid-column:1}}';
      const scheduleStyles = '.offset-control{justify-content:flex-start}.offset-control button{width:27px;height:27px;padding:0;border:1px solid var(--divider-color);border-radius:7px;background:var(--primary-background-color,var(--card-background-color));color:var(--primary-color);font-size:17px;cursor:pointer}.offset-control output{min-width:70px;text-align:center;font-size:11px;font-weight:600;font-variant-numeric:tabular-nums}';
      const manualSaveStyles = '.editor{padding:12px;border:0;border-radius:12px;background:var(--secondary-background-color,var(--card-background-color))}.editor-grid{padding:8px;border-radius:10px;background:var(--secondary-background-color,var(--card-background-color))}.editor-card{border:0;border-radius:0;background:transparent;box-shadow:none}.editor-section{background:transparent}.editor-status{justify-content:space-between;flex-wrap:wrap}.editor-buttons{display:flex;align-items:center;gap:7px}.editor-buttons button{min-height:32px;padding:5px 12px;border:1px solid var(--divider-color);border-radius:8px;background:transparent;color:var(--primary-text-color);font:inherit;font-size:12px;cursor:pointer}.editor-buttons .editor-save{border-color:var(--primary-color);background:var(--primary-color);color:var(--text-primary-color,#fff);font-weight:600}.editor-buttons button:disabled{opacity:.45;cursor:not-allowed}.duration-manual{display:flex;align-items:center;gap:5px}.duration-setting .duration-control .duration-manual input{box-sizing:border-box;width:76px;min-height:30px;padding:4px 6px;border:1px solid var(--divider-color);border-radius:7px;background:var(--primary-background-color,var(--card-background-color));color:var(--primary-text-color);font:inherit;font-size:12px}.duration-manual span{color:var(--secondary-text-color);font-size:11px}';
      const layoutStyles = `
        .wrap{container-type:inline-size;container-name:ec-panel}
        .row{display:block;padding:0;border:0;border-radius:0;background:transparent;box-shadow:none}
        .controller-summary{position:relative;box-sizing:border-box;display:grid;grid-template-columns:minmax(320px,34%) minmax(0,1fr);gap:6px 12px;padding:12px;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#e0e0e0);border-radius:14px}
        .row.editing .controller-summary{grid-template-columns:minmax(0,1fr);gap:6px}
        .row.editing .controller-summary .identity{grid-row:1}
        .row.editing .controller-summary .chips{grid-row:2}
        .editor{margin-top:12px;padding:0;border:0;border-radius:0;background:transparent}
        .editor-header{margin:0 0 10px;align-items:center;gap:12px}
        .editor-heading{min-width:0;display:flex;align-items:center;flex-wrap:wrap;gap:4px}.editor-heading h2{margin:0;font-size:16px;font-weight:600}
        .save-state{display:inline;margin:0 0 0 12px;font-size:12px}
        .editor-toolbar{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
        .edit-modes{background:transparent;padding:0;gap:4px}
        .edit-modes button{min-height:32px;padding:6px 10px;font-size:12px}
        .edit-modes button.selected{background:var(--card-background-color,#fff);box-shadow:none}
        .editor-buttons{gap:8px}.editor-buttons button{min-height:32px;padding:6px 12px}
        .editor-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;padding:0;border-radius:0;background:transparent;align-items:start}
        .editor-grid>.editor-card,.editor-column>.editor-card{box-sizing:border-box;min-width:0;grid-column:auto;padding:12px;border:0;border-radius:12px;background:var(--card-background-color,#fff);box-shadow:none;margin:0}
        .editor-grid>.identity-card{grid-column:1/-1;display:grid;grid-template-columns:110px minmax(0,1fr);align-items:center;gap:12px}
        .identity-card .card-heading{margin:0}.identity-card .card-heading-icon{display:none}
        .identity-card .card-fields{display:grid;grid-template-columns:minmax(0,480px) auto;justify-content:start;align-items:center;gap:10px}.identity-card .field{flex-direction:row;align-items:center}.identity-card .field>span{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
        .identity-card .icon-picker{min-width:140px}.identity-card .icon-picker>.add-entity{min-height:32px;margin:0}
        .entity-option[hidden],.icon-option[hidden]{display:none}
        .entity-option{grid-template-columns:20px minmax(0,1fr);gap:2px 7px;min-width:0}
        .entity-option ha-state-icon{grid-column:1;grid-row:1/3}.entity-option span{grid-column:2;grid-row:1}.entity-option small{grid-column:2;grid-row:2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .section-title{display:flex;align-items:center;gap:6px;min-width:0}.section-title h3{min-width:0}
        .field-help{flex:none;display:inline-grid;place-items:center;width:24px;height:24px;padding:0;border:1px solid var(--divider-color,#ddd);border-radius:50%;background:transparent;color:var(--secondary-text-color,#666);font:inherit;font-size:12px;cursor:pointer}
        .help-popover{box-sizing:border-box;position:fixed;inset:auto;margin:0;width:max-content;max-width:min(300px,calc(100vw - 24px));padding:12px;border:1px solid var(--divider-color,#ddd);border-radius:10px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#222);font:inherit;font-size:13px;line-height:1.5;box-shadow:0 4px 16px #0002;overflow-wrap:anywhere}
        .editor-column{display:flex;flex-direction:column;gap:10px;min-width:0}
        .group-title{grid-column:1/-1;margin:0;font-size:16px;font-weight:600;color:var(--primary-text-color)}
        .inputs-card,.behavior-card{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.inputs-card>.entity-card+.entity-card,.behavior-card>.settings-group{margin-top:0}.behavior-card>.editor-actions{grid-column:1/-1}
        .entity-card,.settings-group,.rules-card .entity-card{min-width:0;padding:0;background:transparent;border:0}
        .inputs-card .card-heading-icon,.behavior-card .card-heading-icon{display:none}
        .card-heading{margin-bottom:12px;gap:6px}.card-heading-copy h3{font-size:14px;line-height:20px}
        .card-heading-copy p{font-size:12px;line-height:16px;margin-top:2px}
        .card-heading-icon{width:32px;height:32px;border-radius:9px}
        .selected-entities{gap:4px;margin:0 0 6px}.selected-entity{min-height:30px}
        .add-entity{border:0;border-radius:8px;padding:5px 8px;background:color-mix(in srgb,var(--primary-color) 8%,var(--card-background-color,#fff));color:var(--primary-color)}
        .switch-setting{justify-content:space-between;gap:10px;margin-top:6px;font-size:12px;line-height:18px}
        .card-fields{gap:8px}.field{gap:4px;font-size:12px}
        .field input:not([type=checkbox]),.field select,.field textarea,.schedule-endpoint select{min-height:32px;padding:5px 8px;border:1px solid transparent;background:var(--primary-background-color);border-radius:8px}
        .field input:focus-visible,.field select:focus-visible,.field textarea:focus-visible,.editor button:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}
        .duration-setting .duration-control{gap:6px}.duration-input{gap:12px}
        .duration-setting .duration-control .duration-manual input{width:72px;min-height:32px;background:var(--primary-background-color);border-color:transparent}
        .duration-value{margin-top:0}.schedule-heading{align-items:center}.schedule-heading .switch-setting{margin:0}
        .schedule-content{margin-top:2px;padding-top:0}.schedule-track{margin:2px 0 0}.schedule-labels{margin-bottom:3px}.schedule-endpoints{gap:10px;margin-top:6px}
        .schedule-endpoint{gap:7px}.schedule-endpoint select{width:100%;min-width:0;font-size:12px}
        .editor-grid>.rules-card,.editor-grid>.editor-section{grid-column:1/-1;padding:0;display:block}
        .rules-card summary,.editor-section summary{display:flex;justify-content:space-between;align-items:center;padding:10px 12px;font-size:14px;font-weight:500;cursor:pointer;list-style:none}
        .rules-card summary::-webkit-details-marker,.editor-section summary::-webkit-details-marker{display:none}
        .rules-card summary ha-icon{--mdc-icon-size:20px;color:var(--secondary-text-color)}
        .rule-groups{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:2px 12px 12px}
        .advanced-fields,.decision-summary{padding:2px 12px 12px}
        .advanced-setting{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:6px;min-width:0}.advanced-setting>.field-help{margin-top:0}.advanced-setting .switch-setting{margin:0}.advanced-setting .field,.advanced-setting .duration-control{min-width:0}
        .advanced-fields{grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr));gap:12px}.editor-grid>.editor-section[data-editor-section=timer],.editor-grid>.editor-section[data-editor-section=monitoring],.editor-grid>.editor-section[data-editor-section=initial_state]{grid-column:span 1}
        .parameter-editor{margin-top:8px;border:0;min-width:0}.parameter-editor>summary{display:flex;align-items:center;gap:8px;min-height:32px;cursor:pointer;font-size:12px;list-style:none}.parameter-editor>summary::-webkit-details-marker{display:none}.parameter-editor>summary small{flex:1;color:var(--secondary-text-color);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:right}.parameter-editor ha-icon{--mdc-icon-size:16px}.parameter-fields{display:grid;gap:8px;padding:4px 0}.parameter-help{font-size:12px}.parameter-setting{display:grid;grid-template-columns:115px minmax(0,1fr);gap:8px;align-items:center;font-size:12px;min-width:0}.parameter-label{display:flex;gap:6px;align-items:center}.parameter-label input{accent-color:var(--primary-color);width:18px;height:18px;margin:0}.parameter-inputs{display:grid;grid-template-columns:minmax(0,1fr) 66px auto;gap:6px;align-items:center;min-width:0}.parameter-inputs input[type=range]{width:100%;min-width:0;accent-color:var(--primary-color);border-radius:8px}.parameter-inputs input[type=number],.parameter-setting select{box-sizing:border-box;width:100%;min-width:0;min-height:32px;padding:5px;border:1px solid transparent;border-radius:8px;background:var(--primary-background-color);color:var(--primary-text-color);font:inherit}.parameter-setting input[type=color]{width:100%;height:32px;border:0;padding:0;background:transparent;cursor:pointer}.parameter-setting input:disabled{opacity:.4}.parameter-editor[open]>summary ha-icon{transform:rotate(180deg)}
        .editor-grid>.live-decision{grid-column:1/-1;padding:8px 12px}.decision-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}.decision-heading h3{margin:0;font-size:14px}.live-badge{font-size:10px;color:var(--secondary-text-color)}.decision-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.decision-metrics>div{display:flex;flex-direction:column;gap:3px;min-width:0}.decision-metrics span,.decision-metrics small{font-size:11px;color:var(--secondary-text-color);line-height:1.35}.decision-metrics strong{font-size:13px;line-height:1.4;overflow-wrap:anywhere}.draft-preview{display:flex;flex-wrap:wrap;gap:4px 10px;padding-top:8px;margin-top:8px;border-top:1px solid var(--divider-color);font-size:11px}.draft-preview b{color:var(--primary-color)}
        @container ec-panel (max-width:950px){.editor-grid>.live-decision{grid-row:2}.inputs-card{grid-row:3}.behavior-card{grid-row:4}.schedule-card-constraint{grid-row:5}.schedule-card-night{grid-row:6}.editor-grid>.editor-section[data-editor-section]{grid-column:1}}
        @container ec-panel (max-width:620px){.decision-metrics{grid-template-columns:minmax(0,1fr);gap:8px}.decision-metrics>div{display:grid;grid-template-columns:1fr 1fr;gap:2px 8px}.decision-metrics small{grid-column:1/-1}.parameter-setting{grid-template-columns:1fr;gap:4px}.parameter-inputs input[type=number],.parameter-setting select{min-height:44px;font-size:16px}.parameter-label{min-height:36px}.parameter-editor>summary{min-height:44px}.parameter-inputs input[type=range]{height:32px}.advanced-fields{grid-template-columns:1fr}.parameter-editor>summary small{white-space:normal}}
        @container ec-panel (max-width:950px){.controller-summary{grid-template-columns:minmax(0,1fr)}.controller-summary .identity{grid-row:1}.controller-summary .chips{grid-column:1;grid-row:2}.controller-summary .timeline-line{grid-row:3}.editor-header{align-items:flex-start}.editor-toolbar{gap:10px}.editor-grid{grid-template-columns:minmax(0,1fr)}.editor-grid>.editor-card{grid-column:1}.editor-column{display:contents}.inputs-card{grid-row:2}.behavior-card{grid-row:3}.schedule-card-constraint{grid-row:4}.schedule-card-night{grid-row:5}.editor-grid>.identity-card{grid-template-columns:110px minmax(0,1fr)}.rule-groups{grid-template-columns:1fr}}
        @container ec-panel (max-width:620px){.editor-grid>.editor-card,.editor-column>.editor-card{padding:14px}.editor-grid>.rules-card,.editor-grid>.editor-section{padding:0}.editor-header{flex-direction:column;align-items:stretch;gap:10px}.editor-toolbar{width:100%;justify-content:space-between;gap:8px}.edit-modes{width:auto}.field-help{width:36px;height:36px}.edit-modes button,.editor-buttons button{min-height:44px;padding:8px 10px}.editor-grid>.identity-card{grid-template-columns:minmax(0,1fr);gap:8px}.identity-card .card-fields{grid-template-columns:minmax(0,1fr) auto}.identity-card .icon-picker{min-width:0}.identity-card .icon-picker>.add-entity{min-height:44px}.inputs-card,.behavior-card{grid-template-columns:minmax(0,1fr);gap:16px}.schedule-endpoints{grid-template-columns:1fr}.rule-groups{padding:4px 14px 14px}.field input:not([type=checkbox]),.field select,.field textarea,.schedule-endpoint select,.entity-search{min-height:44px;font-size:16px}.add-entity,.entity-option,.icon-option{min-height:44px}.selected-entity{min-height:36px}.remove-entity{width:36px;height:36px}.switch-setting{min-height:44px}.schedule-heading .switch-setting{min-height:44px}.offset-control button{min-width:44px;min-height:44px}.schedule-track{height:40px}.duration-setting .duration-control .duration-manual input{min-height:44px;font-size:16px}.rules-card summary,.editor-section summary{min-height:44px}.editor-actions .card-fields{grid-template-columns:minmax(0,1fr)}}
        .parameter-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.parameter-pair:has(details[open]){display:block}.parameter-pair .parameter-editor>summary{font-size:11px}
        .editor-grid>.live-decision{display:grid;grid-template-columns:180px minmax(0,1fr);gap:12px;align-items:center}.live-decision .decision-heading{flex-direction:column;align-items:flex-start;margin:0;gap:4px}.live-decision .decision-metrics small{display:none}.draft-preview{grid-column:1/-1}
        .editor-grid>.identity-card{padding-top:8px;padding-bottom:8px}.schedule-card:not(.enabled){padding-top:8px;padding-bottom:8px}.schedule-card:not(.enabled) .card-heading{margin-bottom:0}.inputs-card .card-heading,.behavior-card .card-heading{margin-bottom:6px}.inputs-card,.behavior-card{gap:8px}
        @container ec-panel (max-width:950px){.editor-grid>.live-decision{grid-row:2}.inputs-card{grid-row:3}.behavior-card{grid-row:4}.schedule-card-constraint{grid-row:5}.schedule-card-night{grid-row:6}.editor-grid>.editor-section[data-editor-section]{grid-column:1}}
        @container ec-panel (max-width:620px){.editor-grid>.live-decision{display:block}.live-decision .decision-heading{flex-direction:row;margin-bottom:8px}.live-decision .decision-metrics small{display:block}.parameter-pair{display:block}}
        .presence-editor{margin-top:6px}.presence-editor>summary{display:flex;align-items:center;justify-content:space-between;gap:6px;min-height:28px;font-size:11px;cursor:pointer;list-style:none;color:var(--secondary-text-color)}.presence-editor>summary::-webkit-details-marker{display:none}.presence-editor>summary ha-icon{--mdc-icon-size:16px}.presence-editor .entity-card{margin-top:6px}.activation-inputs{min-width:0}
        ha-form[data-native-action],ha-form[data-native-icon]{display:none}ha-form[data-native-ready]{display:block;min-width:0}.icon-fallback[hidden],.native-loading[hidden],.search-empty[hidden]{display:none}.lifecycle-editor{min-width:0;grid-column:1/-1;margin-top:8px}.native-loading{font-size:11px;color:var(--secondary-text-color)}
        .manual-controls{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr 1fr;align-items:center;gap:12px}.manual-controls h3{margin:0;font-size:13px}.manual-controls .switch-setting{margin:0}@container ec-panel (max-width:620px){.manual-controls{grid-template-columns:1fr}}
      `;
      this.shadowRoot.innerHTML = '<style>' + styles + editorStyles + interactionStyles + scheduleStyles + manualSaveStyles + layoutStyles + '</style>' +
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
          const editor = preserveEditor && this._editing?.id === controller.id
            ? row.querySelector(".editor") : null;
          row.className = updated.className;
          if (editor) {
            // Detaching and reattaching the editor cancels a button click that
            // is between pointerdown and pointerup during a live HA update.
            for (const child of [...row.children]) if (child !== editor) child.remove();
            for (const child of [...updated.children]) {
              if (!child.matches(".editor")) row.insertBefore(child, editor);
            }
          } else {
            const sections = new Map([...row.querySelectorAll(".editor details[data-editor-section]")]
              .map((section) => [section.dataset.editorSection, section.open]));
            row.innerHTML = updated.innerHTML;
            row.querySelectorAll(".editor details[data-editor-section]").forEach((section) => {
              if (sections.has(section.dataset.editorSection)) section.open = sections.get(section.dataset.editorSection);
            });
          }
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
    if (this._editing) this._ensureNativeEditors();
    requestAnimationFrame(() => this._updateVisibleCount());
  }

  _dismissHelp() {
    this.shadowRoot.querySelectorAll(".help-popover:popover-open").forEach((item) => item.hidePopover());
  }

  async _handleClick(event) {
    const button = event.composedPath().find((element) =>
      element.matches?.(".chip[data-entity], button[data-toggle], button[data-edit], button[data-mode], " +
        "button[data-picker-toggle], button[data-entity-option], button[data-remove-entity], button[data-save], button[data-close], " +
        "button[data-icon-toggle], button[data-icon-value], button[data-offset-step], button[data-help], button[data-native-retry]"));
    if (!button) return;
    if (button.hasAttribute('data-native-retry')) {this._nativeLoadFailed = false; this._ensureNativeEditors(); return;}
    if (button.dataset.help) {
      const popover = this.shadowRoot.getElementById(button.dataset.help);
      if (!popover) return;
      const wasOpen = popover.matches(":popover-open");
      this._dismissHelp();
      if (!wasOpen) {
        popover.showPopover();
        const anchor = button.getBoundingClientRect();
        const box = popover.getBoundingClientRect();
        popover.style.left = Math.max(12, Math.min(window.innerWidth - box.width - 12, anchor.left)) + "px";
        const top = anchor.bottom + 6;
        popover.style.top = Math.max(12, top + box.height <= window.innerHeight - 12
          ? top : anchor.top - box.height - 6) + "px";
      }
      return;
    }
    if (button.dataset.save) {
      const controller = this.controllers.find((item) => item.id === button.dataset.save);
      if (controller) await this._saveController(controller);
      return;
    }
    if (button.dataset.close) {
      this._editing = null;
      this._pickerOpen = null;
      this._iconPickerOpen = false;
      this._rowMarkup.clear();
      this._render();
      return;
    }
    if (button.dataset.iconToggle) {
      this._iconPickerOpen = !this._iconPickerOpen;
      this._rowMarkup.clear();
      this._render();
      this.shadowRoot.querySelector(".icon-search")?.focus();
      return;
    }
    if (button.dataset.iconValue) {
      const controller = this.controllers.find((item) => item.id === this._editing?.id);
      if (!controller) return;
      const nextForm = structuredClone(controller.form || {});
      nextForm.basic = { ...(nextForm.basic || {}), icon: button.dataset.iconValue };
      controller.form = nextForm;
      controller.icon = button.dataset.iconValue;
      this._iconPickerOpen = false;
      this._markControllerDirty(controller);
      this._rowMarkup.clear();
      this._render();
      return;
    }
    if (button.dataset.offsetStep) {
      const controller = this.controllers.find((item) => item.id === this._editing?.id);
      if (!controller) return;
      const section = button.dataset.section;
      const key = button.dataset.field;
      const nextForm = structuredClone(controller.form || {});
      if (!nextForm[section]) nextForm[section] = {};
      const currentMinutes = Number(nextForm[section][key] || 0) / 60;
      nextForm[section][key] = Math.max(-720, Math.min(720, currentMinutes + Number(button.dataset.offsetStep))) * 60;
      controller.form = nextForm;
      this._markControllerDirty(controller);
      this._rowMarkup.clear();
      this._render();
      return;
    }
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
      controller.form = nextForm;
      if (button.dataset.entityOption) this._pickerOpen = section + "." + key;
      this._markControllerDirty(controller);
      this._rowMarkup.clear();
      this._render();
      return;
    }
    if (button.dataset.edit) {
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
    if (kind === "offset-minutes") return Math.max(-720, Math.min(720, Number(element.value) || 0)) * 60;
    if (kind === "states") return element.value;
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

  _handlePickerKeydown(event) {
    if (event.target.matches?.('.schedule-range') && ['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) {
      event.preventDefault();
      const direction = ['ArrowRight','ArrowUp'].includes(event.key) ? 1 : -1;
      event.target.value = String(Math.max(0,Math.min(1439,Number(event.target.value) + direction * 15)));
      event.target.dispatchEvent(new Event('input',{bubbles:true}));
      event.target.dispatchEvent(new Event('change',{bubbles:true}));
      return;
    }
    const picker = event.target.closest?.('.entity-picker,.icon-picker');
    if (!picker) return;
    const options = [...picker.querySelectorAll('.entity-option,.icon-option')].filter(el => !el.hidden);
    if (event.key === 'Escape') {
      event.preventDefault();
      const key = this._pickerOpen;
      event.target.blur();
      this._pickerOpen = null; this._iconPickerOpen = false;
      this._rowMarkup.clear(); this._render();
      const toggle = [...this.shadowRoot.querySelectorAll('[data-picker-toggle]')].find(el => el.dataset.pickerToggle === key);
      (toggle || this.shadowRoot.querySelector('.editor [data-icon-toggle]'))?.focus(); return;
    }
    if (['ArrowDown','ArrowUp'].includes(event.key) && options.length) {
      event.preventDefault();
      const index = options.indexOf(event.target);
      options[(index + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length].focus();
    } else if (event.key === 'Enter' && event.target.type === 'search' && options.length) {
      event.preventDefault(); options[0].click();
    }
  }

  _handleEditorInput(event) {
    const field = event.target;
    if (field.matches?.('[data-service-param]') && field.type !== 'checkbox') {
      this._updateServiceParameter(field); return;
    }
    if (field.matches?.(".icon-search")) {
      const query = field.value.toLocaleLowerCase();
      field.closest(".icon-picker")?.querySelectorAll(".icon-option").forEach((option) => {
        option.hidden = !option.textContent.toLocaleLowerCase().includes(query);
      });
      return;
    }
    if (field.matches?.(".entity-search")) {
      const normalize = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
        .toLocaleLowerCase().trim();
      const query = normalize(field.value);
      field.closest(".entity-picker")?.querySelectorAll(".entity-option").forEach((option) => {
        const text = normalize(option.textContent);
        option.hidden = !query.split(/\s+/).every((token) => text.includes(token));
      });
      const picker = field.closest('.entity-picker');
      let message = picker.querySelector('.search-empty');
      if (!message) {message = document.createElement('p'); message.className = 'empty-selection search-empty'; message.setAttribute('role','status'); picker.appendChild(message);}
      message.textContent = 'Žiadna entita nezodpovedá vyhľadávaniu.';
      message.hidden = [...picker.querySelectorAll('.entity-option')].some(el => !el.hidden);
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
      this._updateDraftField(field);
      return;
    }
    if (field.dataset.kind === "duration") {
      const selector = '[data-duration-manual="' + field.dataset.section + "." + field.dataset.field + '"]';
      const manual = this.shadowRoot.querySelector(selector);
      const range = field.type === "range" ? field :
        this.shadowRoot.querySelector('.editor input[type="range"][data-section="' + field.dataset.section + '"][data-field="' + field.dataset.field + '"]');
      if (field.type === "range" && manual) manual.value = field.value;
      if (field.type === "number" && range) {
        const seconds = Math.max(0, Number(field.value) || 0);
        range.max = String(Math.max(Number(range.max), Math.ceil(seconds / 3600) * 3600));
        range.value = String(seconds);
      }
      const output = this.shadowRoot.querySelector('[data-duration-for="' + field.dataset.section + "." + field.dataset.field + '"]');
      if (output) output.textContent = this._formatDuration(Number(field.value));
      this._updateDraftField(field);
      return;
    }
    this._updateDraftField(field);
  }

  _handleEditorChange(event) {
    const field = event.target;
    if (field.matches?.('[data-scene-hook]')) {
      const controller = this.controllers.find(item => item.id === this._editing?.id);
      if (!controller) return;
      const form = structuredClone(controller.form || {});
      form.actions ||= {}; form.actions.lifecycle_actions ||= {};
      form.actions.lifecycle_actions[field.dataset.sceneHook] = field.value ? [{action:'scene.turn_on', target:{entity_id:field.value}}] : [];
      controller.form = form; this._markControllerDirty(controller); this._bindNativeEditors(); return;
    }
    if (field.matches?.('[data-service-param]')) {this._updateServiceParameter(field); return;}
    if (!field.matches?.(".editor [data-field]")) return;
    if (this._updateDraftField(field) &&
        (["constraint_enabled", "night_mode_enabled"].includes(field.dataset.field) || field.dataset.kind === "schedule-source" || field.dataset.field.startsWith('on_'))) {
      field.blur();
      this._rowMarkup.clear();
      this._render();
    }
  }

  _updateDraftField(field, strict = false) {
    const controller = this.controllers.find((item) => item.id === this._editing?.id);
    if (!controller || !field.isConnected) return;
    const section = field.dataset.section;
    const key = field.dataset.field;
    const nextForm = structuredClone(controller.form || {});
    if (!nextForm[section]) nextForm[section] = {};
    try {
      nextForm[section][key] = this._readEditorValue(field);
      if (!strict && section === 'actions' && key === 'on_exit_active') nextForm.actions.on_enter_idle = 'ignore';
      if (field.dataset.kind === "schedule-time") {
        const prefix = section === "constraints" ? "constraint" : "night";
        const side = key.includes("_start_") ? "start" : "end";
        nextForm[section][prefix + "_" + side + "_source"] = "fixed";
        nextForm[section][prefix + "_" + side + "_offset_seconds"] = 0;
        const source = this.shadowRoot.querySelector(
          '.schedule-card-' + prefix + ' [data-field="' + prefix + '_' + side + '_source"]'
        );
        if (source) source.value = "fixed";
      }
    } catch (error) {
      if (strict) throw error;
      this._markControllerDirty(controller);
      this._saveErrors.set(controller.id, "Neplatná hodnota: " + (error?.message || "skontroluj JSON."));
      this._updateEditorStatus(controller);
      return;
    }
    controller.form = nextForm;
    this._markControllerDirty(controller);
    return true;
  }

  _markControllerDirty(controller) {
    controller._draftRevision = (controller._draftRevision || 0) + 1;
    this._dirtyControllers.add(controller.id);
    this._saveErrors.delete(controller.id);
    this._updateEditorStatus(controller);
  }

  _updateEditorStatus(controller) {
    if (this._editing?.id !== controller.id) return;
    const status = this.shadowRoot.querySelector(".editor .save-state");
    const save = this.shadowRoot.querySelector(".editor-save");
    if (status) status.textContent = this._savingControllers.has(controller.id) ? "Ukladám…" :
      this._saveErrors.get(controller.id) || (this._dirtyControllers.has(controller.id) ? "Neuložené zmeny" : "Uložené");
    if (save) save.disabled = !this._dirtyControllers.has(controller.id) || this._savingControllers.has(controller.id);
    const decision = this.shadowRoot.querySelector('.live-decision');
    if (decision) decision.innerHTML = this._decisionSummary(controller);
  }

  async _saveController(controller) {
    if (this._savingControllers.has(controller.id) || !this._dirtyControllers.has(controller.id)) return;
    this._savingControllers.add(controller.id);
    this._saveErrors.delete(controller.id);
    this._updateEditorStatus(controller);
    let preserveDraft = true;
    try {
      for (const field of this.shadowRoot.querySelectorAll('.editor [data-service-param]')) {
        if (!field.checkValidity()) {field.reportValidity(); throw new Error('Skontroluj zvýraznenú hodnotu.');}
      }
      for (const field of this.shadowRoot.querySelectorAll(".editor input[data-field], .editor select[data-field], .editor textarea[data-field]")) {
        // Schedule sliders display resolved/snap-rounded times. Only an actual
        // input/change event may replace the persisted time or solar source.
        if (field.dataset.kind === "schedule-time") continue;
        if (!field.checkValidity()) {
          field.reportValidity();
          throw new Error("Skontroluj zvýraznenú hodnotu.");
        }
        this._updateDraftField(field, true);
      }
      const revision = controller._draftRevision || 0;
      const response = await this._hass.callWS({
        type: SAVE_COMMAND,
        entry_id: controller.entry_id,
        controller_id: controller.id,
        form: structuredClone(controller.form || {}),
      });
      const current = this.controllers.find((item) => item.id === controller.id);
      if (current && (current._draftRevision || 0) === revision) {
        if (response?.form) current.form = response.form;
        current._liveForm = structuredClone(current.form || {});
        if (response?.name) current.name = response.name;
        if (response?.icon !== undefined) current.icon = response.icon;
        if (response?.resolved_schedule) current.resolved_schedule = response.resolved_schedule;
        this._dirtyControllers.delete(controller.id);
        this._saveErrors.delete(controller.id);
        preserveDraft = false;
      }
    } catch (error) {
      this._saveErrors.set(controller.id, "Uloženie zlyhalo: " + (error?.message || "skús to znova."));
    } finally {
      this._savingControllers.delete(controller.id);
      this._updateEditorStatus(controller);
      this._rowMarkup.clear();
      this._render(preserveDraft);
    }
  }

  _syncScheduleEndpoint(controller, prefix, side) {
    const section = prefix === "constraint" ? "constraints" : "night";
    const key = prefix + "_" + side + "_time";
    const sourceKey = prefix + "_" + side + "_source";
    const source = controller.form?.[section]?.[sourceKey] || "fixed";
    const rawTime = String(controller.form?.[section]?.[key] || "00:00").split(":");
    const stored = (Number(rawTime[0]) || 0) * 60 + (Number(rawTime[1]) || 0);
    const minutes = this._scheduleMinutes(controller, prefix, side, source, stored, controller.resolved_schedule?.[prefix]?.[side]);
    const card = this.shadowRoot.querySelector(".schedule-card-" + prefix);
    const range = card?.querySelector(".schedule-range." + side);
    if (range) range.value = String(minutes);
    const output = card?.querySelector('[data-time-label="' + key + '"]');
    if (output) output.textContent = String(Math.floor(minutes / 60)).padStart(2, "0") + ":" +
      String(minutes % 60).padStart(2, "0");
    const values = [...(card?.querySelectorAll(".schedule-range") || [])].map((item) => Number(item.value) / 1439 * 100);
    const fill = card?.querySelector(".schedule-fill");
    if (fill && values.length === 2) {
      const left = Math.min(...values);
      const right = Math.max(...values);
      fill.style.background = values[0] <= values[1]
        ? "linear-gradient(to right, transparent " + left + "%, var(--primary-color) " + left + "%, var(--primary-color) " + right + "%, transparent " + right + "%)"
        : "linear-gradient(to right, var(--primary-color) 0%, var(--primary-color) " + right + "%, transparent " + right + "%, transparent " + left + "%, var(--primary-color) " + left + "%, var(--primary-color) 100%)";
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
      if (this._editing?.id === controller.id) {
        const countdown = row?.querySelector('[data-decision-countdown]');
        if (countdown && controller.state === 'active_timer') {
          const remaining = Math.max(0, (new Date(controller.expires_at) - Date.now()) / 1000);
          countdown.textContent = controller.presence_active ? 'Drží prítomnosť' :
            controller.expires_at ? this._formatDuration(remaining) : 'Odpočet nebeží';
        }
      }
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
