/**
 * DWARF 3 card: live view, joystick, capture, goto and gallery for the dwarf3 integration.
 *
 *   type: custom:dwarf3-card
 *   device_id: <optional, the first DWARF 3 is used when left out>
 *   theme: auto | light | dark   (auto follows Home Assistant)
 *
 * The card finds its entities through the entity registry (translation keys), so renamed entities keep working.
 */

const VERSION = "0.3.2";
const DOMAIN = "dwarf3";

// Translation key -> role. Battery and connectivity have no key; they are found by device class.
const ROLES = {
  needs_prepare: "needsPrepare",
  tracking: "tracking",
  app_connected: "appConnected",
  busy_elsewhere: "busyElsewhere",
  close_barrel: "closeBarrel",
  stop_capture: "stopCapture",
  prepare: "prepare",
  calibrate: "calibrate",
  point_up: "pointUp",
  wide_camera: "wideCamera",
  tele_camera: "teleCamera",
  capture_finished: "captureFinished",
  latest_stack: "latestStack",
  capture_progress: "progress",
  sd_used: "sdUsed",
  sd_free: "sdFree",
  tele_darks: "teleDarks",
  wide_darks: "wideDarks",
  job_state: "jobState",
  frames_captured: "framesCaptured",
  frames_failed: "framesFailed",
  device_temperature: "bodyTemp",
  tele_sensor_temperature: "teleTemp",
  wide_sensor_temperature: "wideTemp",
  pitch: "pitch",
  rotation: "rotation",
  sessions: "sessions",
  relay_version: "relayVersion",
};

// Barlow (SIL OFL, frontend/fonts/OFL.txt), served by the integration next to this file. @font-face does not work
// inside a shadow root, so it goes in the document once.
const FONT_BASE = import.meta.url.startsWith("data:") ? "/dwarf3_frontend/fonts/" : new URL("fonts/", import.meta.url).href;
if (!document.getElementById("dwarf3-card-fonts")) {
  const style = document.createElement("style");
  style.id = "dwarf3-card-fonts";
  style.textContent = [400, 500, 600, 700]
    .map(
      (w) => `@font-face { font-family: "DWARF3 Barlow"; font-style: normal; font-weight: ${w}; font-display: swap;
        src: url("${FONT_BASE}barlow-${w}.woff2") format("woff2"); }`,
    )
    .join("\n");
  document.head.appendChild(style);
}

const EXPOSURES = ["15", "30", "60"];
const FILTERS = [
  { id: "vis", label: "VIS", hint: "Clear, for galaxies and clusters" },
  { id: "astro", label: "Astro", hint: "Light pollution cut" },
  { id: "duo", label: "Duo-band", hint: "Hα + OIII, for emission nebulae" },
];
const FRAME_PRESETS = [20, 50, 100, 200, 500];

// J2000. ra in hours, dec in degrees. Names match how the scope labels sessions ("M 81", "NGC 1499").
// Checked against OpenNGC: all within 15 arcmin, except two aimed on purpose to frame the whole target.
const CATALOG = [
  ["M 31", "Andromeda Galaxy", "galaxy", 0.7123, 41.2692, 3.4, "NGC 224"],
  ["M 33", "Triangulum Galaxy", "galaxy", 1.5641, 30.6602, 5.7, "NGC 598"],
  ["M 51", "Whirlpool Galaxy", "galaxy", 13.498, 47.1953, 8.4, "NGC 5194"],
  ["M 63", "Sunflower Galaxy", "galaxy", 13.2637, 42.0292, 8.6, "NGC 5055"],
  ["M 64", "Black Eye Galaxy", "galaxy", 12.9455, 21.6828, 8.5, "NGC 4826"],
  ["M 74", "Phantom Galaxy", "galaxy", 1.6116, 15.7836, 9.4, "NGC 628"],
  ["M 77", "Cetus A", "galaxy", 2.7113, -0.0133, 8.9, "NGC 1068"],
  ["M 81", "Bode's Galaxy", "galaxy", 9.9259, 69.0653, 6.9, "NGC 3031"],
  ["M 82", "Cigar Galaxy", "galaxy", 9.9313, 69.6794, 8.4, "NGC 3034"],
  ["M 83", "Southern Pinwheel", "galaxy", 13.6169, -29.8658, 7.5, "NGC 5236"],
  ["M 87", "Virgo A", "galaxy", 12.5137, 12.3911, 8.6, "NGC 4486"],
  ["M 101", "Pinwheel Galaxy", "galaxy", 14.0535, 54.3492, 7.9, "NGC 5457"],
  ["M 104", "Sombrero Galaxy", "galaxy", 12.6665, -11.6231, 8.0, "NGC 4594"],
  ["M 106", "", "galaxy", 12.316, 47.3039, 8.4, "NGC 4258"],
  ["NGC 253", "Sculptor Galaxy", "galaxy", 0.7925, -25.2883, 7.2, ""],
  ["NGC 891", "Outer Limits Galaxy", "galaxy", 2.376, 42.3492, 10.0, ""],
  ["NGC 4565", "Needle Galaxy", "galaxy", 12.6058, 25.9878, 9.6, ""],
  ["NGC 7331", "Deer Lick Galaxy", "galaxy", 22.6178, 34.4156, 9.5, ""],
  ["M 1", "Crab Nebula", "nebula", 5.5755, 22.0145, 8.4, "NGC 1952"],
  ["M 8", "Lagoon Nebula", "nebula", 18.0603, -24.387, 6.0, "NGC 6523"],
  ["M 16", "Eagle Nebula", "nebula", 18.3133, -13.8167, 6.0, "NGC 6611"],
  ["M 17", "Omega Nebula", "nebula", 18.3406, -16.1767, 6.0, "NGC 6618"],
  ["M 20", "Trifid Nebula", "nebula", 18.0397, -23.03, 6.3, "NGC 6514"],
  ["M 42", "Orion Nebula", "nebula", 5.5881, -5.3911, 4.0, "NGC 1976"],
  ["M 78", "", "nebula", 5.7796, 0.0139, 8.3, "NGC 2068"],
  ["NGC 7000", "North America Nebula", "nebula", 20.9797, 44.33, 4.0, ""],
  ["IC 5070", "Pelican Nebula", "nebula", 20.8467, 44.35, 8.0, ""],
  ["IC 1396", "Elephant's Trunk", "nebula", 21.6517, 57.5, 3.5, ""],
  ["NGC 6960", "Western Veil", "nebula", 20.7606, 30.7083, 7.0, "Witch's Broom"],
  ["NGC 6992", "Eastern Veil", "nebula", 20.94, 31.7167, 7.0, ""],
  ["NGC 6888", "Crescent Nebula", "nebula", 20.2019, 38.355, 7.4, ""],
  ["NGC 1499", "California Nebula", "nebula", 4.055, 36.4217, 6.0, ""],
  ["IC 434", "Horsehead Nebula", "nebula", 5.6831, -2.4583, 6.8, "Barnard 33"],
  // The centre of the ring, on the NGC 2244 cluster. OpenNGC puts NGC 2237 on the western lobe.
  ["NGC 2237", "Rosette Nebula", "nebula", 6.5625, 4.9983, 5.5, "NGC 2238 NGC 2244"],
  ["NGC 2264", "Cone Nebula", "nebula", 6.685, 9.8833, 3.9, "Christmas Tree"],
  ["IC 405", "Flaming Star Nebula", "nebula", 5.2681, 34.45, 6.0, ""],
  ["IC 1805", "Heart Nebula", "nebula", 2.5561, 61.4433, 6.5, ""],
  ["IC 1848", "Soul Nebula", "nebula", 2.85, 60.4167, 6.5, ""],
  ["NGC 7635", "Bubble Nebula", "nebula", 23.3467, 61.2017, 10.0, ""],
  ["NGC 281", "Pacman Nebula", "nebula", 0.8831, 56.6219, 7.4, ""],
  ["NGC 7023", "Iris Nebula", "nebula", 21.0269, 68.1633, 6.8, ""],
  ["IC 5146", "Cocoon Nebula", "nebula", 21.89, 47.2667, 7.2, ""],
  ["M 27", "Dumbbell Nebula", "planetary", 19.9934, 22.7211, 7.5, "NGC 6853"],
  ["M 57", "Ring Nebula", "planetary", 18.8931, 33.0292, 8.8, "NGC 6720"],
  ["M 76", "Little Dumbbell", "planetary", 1.7055, 51.5753, 10.1, "NGC 650"],
  ["M 97", "Owl Nebula", "planetary", 11.2466, 55.0192, 9.9, "NGC 3587"],
  ["NGC 7293", "Helix Nebula", "planetary", 22.494, -20.8372, 7.6, ""],
  ["NGC 6543", "Cat's Eye Nebula", "planetary", 17.9759, 66.6331, 8.1, ""],
  ["NGC 2392", "Eskimo Nebula", "planetary", 7.4863, 20.9117, 9.1, ""],
  ["M 3", "", "cluster", 13.7032, 28.3772, 6.2, "NGC 5272"],
  ["M 5", "", "cluster", 15.3092, 2.0811, 5.6, "NGC 5904"],
  ["M 13", "Hercules Cluster", "cluster", 16.6948, 36.4597, 5.8, "NGC 6205"],
  ["M 22", "", "cluster", 18.6066, -23.9047, 5.1, "NGC 6656"],
  ["M 92", "", "cluster", 17.2854, 43.1358, 6.4, "NGC 6341"],
  ["M 35", "", "cluster", 6.1483, 24.3333, 5.3, "NGC 2168"],
  ["M 44", "Beehive Cluster", "cluster", 8.6733, 19.6667, 3.7, "Praesepe NGC 2632"],
  ["M 45", "Pleiades", "cluster", 3.79, 24.1167, 1.6, "Seven Sisters"],
  // Between NGC 869 and NGC 884, so both fit.
  ["NGC 869", "Double Cluster", "cluster", 2.3333, 57.1333, 3.7, "NGC 884"],
].map(([id, name, type, ra, dec, mag, aka]) => ({ id, name, type, ra, dec, mag, aka }));

const TYPES = {
  all: { label: "All", icon: "mdi:star-four-points-outline" },
  galaxy: { label: "Galaxies", one: "Galaxy", icon: "mdi:orbit" },
  nebula: { label: "Nebulae", one: "Nebula", icon: "mdi:weather-hazy" },
  planetary: { label: "Planetary", one: "Planetary nebula", icon: "mdi:circle-double" },
  cluster: { label: "Clusters", one: "Star cluster", icon: "mdi:dots-hexagon" },
};

// ---------- sky math (low precision, plenty for "is it up") ----------

const RAD = Math.PI / 180;

function julian(date) {
  return date.getTime() / 86400000 + 2440587.5;
}

function lstDegrees(date, lon) {
  const d = julian(date) - 2451545.0;
  return (((280.46061837 + 360.98564736629 * d + lon) % 360) + 360) % 360;
}

function altAz(raHours, decDeg, lat, lon, date = new Date()) {
  const ha = (lstDegrees(date, lon) - raHours * 15) * RAD;
  const dec = decDeg * RAD;
  const phi = lat * RAD;
  const sinAlt = Math.sin(dec) * Math.sin(phi) + Math.cos(dec) * Math.cos(phi) * Math.cos(ha);
  const alt = Math.asin(sinAlt);
  const cosAz = (Math.sin(dec) - sinAlt * Math.sin(phi)) / (Math.cos(alt) * Math.cos(phi));
  let az = Math.acos(Math.min(1, Math.max(-1, cosAz))) / RAD;
  if (Math.sin(ha) > 0) az = 360 - az;
  return { alt: alt / RAD, az };
}

function sunRaDec(date = new Date()) {
  const n = julian(date) - 2451545.0;
  const L = (280.46 + 0.9856474 * n) % 360;
  const g = ((357.528 + 0.9856003 * n) % 360) * RAD;
  const lambda = (L + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * RAD;
  const eps = (23.439 - 0.0000004 * n) * RAD;
  const ra = Math.atan2(Math.cos(eps) * Math.sin(lambda), Math.cos(lambda)) / RAD;
  const dec = Math.asin(Math.sin(eps) * Math.sin(lambda)) / RAD;
  return { ra: (((ra % 360) + 360) % 360) / 15, dec };
}

function skyPhase(sunAlt) {
  if (sunAlt > 0) return { label: "Daylight", cls: "day" };
  if (sunAlt > -6) return { label: "Civil twilight", cls: "twilight" };
  if (sunAlt > -12) return { label: "Nautical twilight", cls: "twilight" };
  if (sunAlt > -18) return { label: "Astro twilight", cls: "dusk" };
  return { label: "Dark sky", cls: "dark" };
}

function compass(az) {
  return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(az / 45) % 8];
}

function fmtRa(h) {
  const hh = Math.floor(h);
  const m = (h - hh) * 60;
  return `${hh}h ${Math.floor(m).toString().padStart(2, "0")}m`;
}

function fmtDec(d) {
  const sign = d < 0 ? "−" : "+";
  const a = Math.abs(d);
  return `${sign}${Math.floor(a)}° ${Math.round((a % 1) * 60).toString().padStart(2, "0")}′`;
}

function fmtDuration(seconds) {
  if (!isFinite(seconds) || seconds <= 0) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h ? `${h} h ${m.toString().padStart(2, "0")} m` : `${m} min`;
}

// "DWARF_RAW_TELE_M 81_EXP_30_GAIN_60_2026-11-18-03-11-46-101" -> parts
function parseSession(name) {
  const m = /^DWARF_RAW_(TELE|WIDE)_(.+?)_EXP_([\d.]+)_GAIN_(\d+)_(\d{4})-(\d\d)-(\d\d)-(\d\d)-(\d\d)/.exec(name || "");
  if (!m) return { target: name };
  return {
    camera: m[1].toLowerCase(),
    target: m[2],
    exposure: Number(m[3]),
    gain: Number(m[4]),
    date: new Date(+m[5], +m[6] - 1, +m[7], +m[8], +m[9]),
  };
}

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const icon = (name, cls = "") => `<ha-icon class="${cls}" icon="${name}"></ha-icon>`;

// Line icons for the status bar and HUD, drawn to one grid so they sit together.
const GLYPHS = {
  thermo: `<path d="M10 13.6V5a2 2 0 1 1 4 0v8.6a4 4 0 1 1-4 0Z"/><path d="M12 9v6.5"/><circle cx="12" cy="17" r="1.6" fill="currentColor" stroke="none"/>`,
  sd: `<path d="M8.5 3H17a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V8.5Z"/><path d="M10 3v3.5M12.5 3v3.5M15 3v3.5"/>`,
  moon: `<path d="M19.5 14.6A7.5 7.5 0 0 1 9.4 4.5a7.5 7.5 0 1 0 10.1 10.1Z"/><path d="M16.5 3.5v3M15 5h3" stroke-width="1.4"/>`,
  dusk: `<path d="M3 17h18M7 17a5 5 0 0 1 10 0"/><path d="M12 6.5v2.5M5.4 9.9l1.7 1.7M18.6 9.9l-1.7 1.7M8 21h8"/>`,
  sun: `<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>`,
  eye: `<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/>`,
  pitch: `<path d="M4 19h16M4 19 15.5 7.5"/><path d="M10 19a6 6 0 0 0-1.8-4.3"/>`,
  rotate: `<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v4.5h-4.5"/>`,
};
const glyph = (name) =>
  `<svg class="glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${GLYPHS[name]}</svg>`;
// A battery that fills to the charge level.
const batteryGlyph = () =>
  `<svg class="glyph battery" viewBox="0 0 28 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">
    <rect x="2" y="6.5" width="21" height="11" rx="3"/><path d="M25.5 10.2v3.6" stroke-linecap="round" stroke-width="2.2"/>
    <rect class="level" x="4.4" y="8.9" height="6.2" rx="1.4" width="0" fill="currentColor" stroke="none"/></svg>`;

// ---------- the card ----------

class Dwarf3Card extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "shoot";
    this._view = "tele";
    this._typeFilter = "all";
    this._upOnly = true;
    this._query = "";
    this._gallery = null;
    this._galleryError = null;
    this._settings = Object.assign(
      { exposure: "30", gain: 60, filter: "duo", frames: 100, darkFrames: 20, darkExposure: "30", darkWide: false },
      JSON.parse(localStorage.getItem("dwarf3-card-settings") || "{}"),
    );
    this._night = localStorage.getItem("dwarf3-card-night") === "1";
    this._busy = new Set();
  }

  static getStubConfig() {
    return {};
  }

  static getConfigElement() {
    return document.createElement("dwarf3-card-editor");
  }

  setConfig(config) {
    this._config = config || {};
  }

  getCardSize() {
    return 12;
  }

  getGridOptions() {
    return { columns: "full", rows: "auto" };
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first || !this._ents) this._resolve();
    if (!this._built) this._build();
    this._update();
  }

  connectedCallback() {
    this._clock = setInterval(() => this._tick(), 60000);
    this._pipTimer = setInterval(() => this._refreshPip(), 10000);
    this._onResize = () => this._layout();
    window.addEventListener("resize", this._onResize);
    this._resizeObserver = new ResizeObserver(this._onResize);
    this._resizeObserver.observe(this);
  }

  disconnectedCallback() {
    clearInterval(this._clock);
    clearInterval(this._pipTimer);
    window.removeEventListener("resize", this._onResize);
    this._resizeObserver?.disconnect();
    this._stopJoystick();
  }

  // Three layouts. Wide: stage and a side dock, filling the screen (desktop, landscape tablet). Tall: stage over the
  // dock, filling the screen (portrait tablet). Phone: stage over the dock, scrolling with the page.
  _layout() {
    const card = this.$("card");
    if (!card) return;
    const width = this.clientWidth;
    if (!width) return;
    // The card sits under the dashboard header; fill from there to the bottom of the window.
    const top = Math.max(0, Math.min(this.getBoundingClientRect().top, 200));
    const avail = Math.max(520, window.innerHeight - top - 8);
    const mode = width < 600 ? "phone" : width >= 900 || (width >= 700 && width / avail >= 1.15) ? "wide" : "tall";
    for (const m of ["wide", "tall", "phone"]) card.classList.toggle(`layout-${m}`, m === mode);
    card.style.height = mode === "phone" ? "" : `${avail}px`;
  }

  // ----- entity discovery -----

  _resolve() {
    const hass = this._hass;
    const regs = Object.values(hass.entities || {}).filter((e) => e.platform === DOMAIN);
    if (!regs.length) {
      this._ents = null;
      return;
    }
    const deviceId = this._config.device_id || regs[0].device_id;
    const mine = regs.filter((e) => e.device_id === deviceId);
    const ents = {};
    for (const e of mine) {
      const role = ROLES[e.translation_key];
      if (role) ents[role] = e.entity_id;
      const st = hass.states[e.entity_id];
      const dc = st?.attributes?.device_class;
      if (!e.translation_key && e.entity_id.startsWith("sensor.") && dc === "battery") ents.battery = e.entity_id;
      if (!e.translation_key && e.entity_id.startsWith("binary_sensor.") && dc === "connectivity")
        ents.online = e.entity_id;
    }
    Object.assign(ents, this._config.entities || {});
    this._ents = ents;
    this._deviceId = deviceId;
    this._deviceName = hass.devices?.[deviceId]?.name_by_user || hass.devices?.[deviceId]?.name || "DWARF 3";
    // Any entity of the device works as a service target.
    this._target = { entity_id: ents.battery || ents.prepare || mine[0].entity_id };
  }

  _st(role) {
    const id = this._ents?.[role];
    return id ? this._hass.states[id] : undefined;
  }

  _val(role) {
    const s = this._st(role)?.state;
    return s === undefined || s === "unknown" || s === "unavailable" ? null : s;
  }

  _num(role) {
    const v = this._val(role);
    return v === null ? null : Number(v);
  }

  _fmt(role, digits = 0) {
    const st = this._st(role);
    const n = this._num(role);
    if (n === null || isNaN(n)) return "—";
    const unit = st.attributes.unit_of_measurement || "";
    return `${n.toFixed(digits)}${unit === "%" || unit.startsWith("°") ? "" : " "}${unit}`;
  }

  // ----- actions -----

  async _call(service, data = {}, label) {
    const key = label || service;
    if (this._busy.has(key)) return;
    this._busy.add(key);
    this._update();
    try {
      await this._hass.callService(DOMAIN, service, data, this._target);
      return true;
    } catch (err) {
      this._toast(err?.message || String(err), "error");
      return false;
    } finally {
      this._busy.delete(key);
      this._update();
    }
  }

  async _press(role, label) {
    const id = this._ents?.[role];
    if (!id || this._busy.has(role)) return;
    this._busy.add(role);
    this._update();
    try {
      await this._hass.callService("button", "press", {}, { entity_id: id });
      if (label) this._toast(label);
    } catch (err) {
      this._toast(err?.message || String(err), "error");
    } finally {
      this._busy.delete(role);
      this._update();
    }
  }

  _saveSettings() {
    localStorage.setItem("dwarf3-card-settings", JSON.stringify(this._settings));
  }

  _toast(message, kind = "info") {
    const el = this.$("toast");
    el.textContent = message;
    el.className = `toast show ${kind}`;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => (el.className = "toast"), kind === "error" ? 6000 : 3000);
  }

  _confirm(message, action) {
    const el = this.$("confirm");
    el.querySelector(".confirm-text").textContent = message;
    el.classList.add("show");
    this._confirmAction = action;
  }

  // ----- skeleton -----

  $(id) {
    return this.shadowRoot.getElementById(id);
  }

  _build() {
    if (!this._ents) {
      this.shadowRoot.innerHTML = `<style>${STYLES}</style><ha-card class="empty">
        ${icon("mdi:telescope")}<div>No DWARF 3 found. Add the DWARF 3 integration first.</div></ha-card>`;
      return;
    }
    this._built = true;
    this.shadowRoot.innerHTML = `<style>${STYLES}</style>
      <ha-card id="card" class="${this._night ? "night" : ""}">
        <div class="shell">
          <header class="topbar">
            <div class="brand">
              <span class="dot" id="online-dot"></span>
              <button class="name" id="device-btn" title="Device details">${esc(this._deviceName)}</button>
              <span class="pill" id="state-pill"></span>
            </div>
            <div class="stats">
              <span class="stat" id="stat-sky" title="Sun altitude"></span>
              <span class="stat" id="stat-temp" title="Body temperature">${glyph("thermo")}<b></b></span>
              <span class="stat" id="stat-sd" title="SD card free">${glyph("sd")}<b></b></span>
              <span class="stat" id="stat-batt" title="Battery">${batteryGlyph()}<b></b></span>
              <button class="icon-btn" id="night-btn" title="Night vision">${glyph("eye")}</button>
            </div>
          </header>

          <section class="stage" id="stage">
            <div class="viewport" id="viewport"></div>
            <div class="reticle" id="reticle"><span></span><span></span></div>

            <div class="view-switch" id="view-switch">
              <button data-view="tele">Tele</button>
              <button data-view="wide">Wide</button>
              <button data-view="stack">Stack</button>
            </div>

            <button class="pip" id="pip" title="Swap cameras"><img id="pip-img" alt=""><span id="pip-label"></span></button>

            <div class="hud" id="hud">
              <div class="hud-target" id="hud-target"></div>
              <div class="hud-row">
                <span title="Pitch">${glyph("pitch")}<b id="hud-pitch">—</b></span>
                <span title="Rotation">${glyph("rotate")}<b id="hud-rot">—</b></span>
                <span id="hud-track"></span>
              </div>
            </div>

            <div class="banner" id="prepare-banner">
              ${icon("mdi:power-sleep")}
              <div><b>Scope needs Prepare</b><span>The camera, Calibrate, goto and capture work after it.</span></div>
              <button class="btn primary" id="banner-prepare">Prepare</button>
            </div>

            <div class="joystick" id="joystick" title="Drag to slew">
              <div class="ring"></div>
              <div class="knob" id="knob"></div>
              <span class="j-n">▲</span><span class="j-s">▼</span><span class="j-w">◀</span><span class="j-e">▶</span>
            </div>

            <div class="rail">
              <button class="shutter" id="shutter" title="Start capture">
                <svg viewBox="0 0 100 100"><circle class="track" cx="50" cy="50" r="45"/><circle class="bar" id="ring" cx="50" cy="50" r="45"/></svg>
                <span class="core" id="shutter-core"></span>
              </button>
              <div class="rail-summary" id="rail-summary"></div>
            </div>

            <div class="capture-strip" id="capture-strip">
              <div class="strip-bar"><div id="strip-fill"></div></div>
              <div class="strip-text" id="strip-text"></div>
            </div>
          </section>

          <aside class="dock">
            <nav class="tabs" id="tabs">
              <button data-tab="shoot">${icon("mdi:camera-iris")}<span>Shoot</span></button>
              <button data-tab="goto">${icon("mdi:crosshairs-gps")}<span>Go to</span></button>
              <button data-tab="gallery">${icon("mdi:image-multiple")}<span>Gallery</span></button>
              <button data-tab="device">${icon("mdi:tune-variant")}<span>Device</span></button>
            </nav>
            <div class="panel" id="panel"></div>
          </aside>
        </div>

        <div class="lightbox" id="lightbox">
          <div class="lb-inner">
            <img id="lb-img" alt="">
            <div class="lb-bar">
              <div class="lb-title" id="lb-title"></div>
              <div class="lb-actions">
                <a class="btn" id="lb-open" target="_blank" rel="noopener">${icon("mdi:open-in-new")}Full size</a>
                <button class="btn danger" id="lb-delete">${icon("mdi:delete-outline")}Delete</button>
                <button class="btn" id="lb-close">${icon("mdi:close")}</button>
              </div>
            </div>
          </div>
        </div>

        <div class="confirm" id="confirm">
          <div class="confirm-box">
            <div class="confirm-text"></div>
            <div class="confirm-actions">
              <button class="btn" id="confirm-no">Cancel</button>
              <button class="btn primary" id="confirm-yes">Confirm</button>
            </div>
          </div>
        </div>

        <div class="toast" id="toast"></div>
      </ha-card>`;

    this._wire();
    this._renderViewport();
    this._renderPanel();
    this._layout();
    requestAnimationFrame(() => this._layout());
  }

  _wire() {
    const root = this.shadowRoot;
    this.$("view-switch").addEventListener("click", (ev) => {
      const v = ev.target.closest("button")?.dataset.view;
      if (v) this._setView(v);
    });
    this.$("pip").addEventListener("click", () => this._setView(this._view === "tele" ? "wide" : "tele"));
    this.$("device-btn").addEventListener("click", () => {
      // HA has no device dialog; the more-info dialog names the device and links to its page.
      const entityId = this._ents.online || this._target.entity_id;
      this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }));
    });
    this.$("tabs").addEventListener("click", (ev) => {
      const t = ev.target.closest("button")?.dataset.tab;
      if (t && t !== this._tab) {
        this._tab = t;
        this._renderPanel();
        this._update();
      }
    });
    this.$("night-btn").addEventListener("click", () => {
      this._night = !this._night;
      localStorage.setItem("dwarf3-card-night", this._night ? "1" : "0");
      this.$("card").classList.toggle("night", this._night);
    });
    this.$("banner-prepare").addEventListener("click", () => this._press("prepare", "Preparing the scope…"));
    this.$("shutter").addEventListener("click", () => this._shutter());
    this.$("lb-close").addEventListener("click", () => this.$("lightbox").classList.remove("show"));
    this.$("lightbox").addEventListener("click", (ev) => {
      if (ev.target.id === "lightbox") this.$("lightbox").classList.remove("show");
    });
    this.$("lb-delete").addEventListener("click", () => {
      const session = this._lbSession;
      this._confirm(`Delete ${parseSession(session).target} from the SD card? This cannot be undone.`, async () => {
        if (await this._call("delete_session", { session }, "delete")) {
          this.$("lightbox").classList.remove("show");
          this._toast("Session deleted");
          this._gallery = null;
          this._loadGallery();
        }
      });
    });
    this.$("confirm-no").addEventListener("click", () => this.$("confirm").classList.remove("show"));
    this.$("confirm-yes").addEventListener("click", () => {
      this.$("confirm").classList.remove("show");
      this._confirmAction?.();
    });
    this._wireJoystick();
    root.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") {
        this.$("lightbox").classList.remove("show");
        this.$("confirm").classList.remove("show");
      }
    });
  }

  // ----- viewport -----

  async _renderViewport() {
    const vp = this.$("viewport");
    vp.innerHTML = "";
    if (this._view === "stack") {
      const img = document.createElement("img");
      img.className = "stack-img";
      vp.appendChild(img);
      this._stackImg = img;
      this._streamEl = null;
      return;
    }
    const entity = this._ents[this._view === "tele" ? "teleCamera" : "wideCamera"];
    const stateObj = this._hass.states[entity];
    if (!stateObj) {
      vp.innerHTML = `<div class="no-signal">${icon("mdi:video-off-outline")}<span>No camera</span></div>`;
      return;
    }
    await this._ensureStreamElement();
    if (!customElements.get("ha-camera-stream")) {
      const img = document.createElement("img");
      img.className = "still";
      img.src = stateObj.attributes.entity_picture;
      vp.appendChild(img);
      this._streamEl = null;
      return;
    }
    const el = document.createElement("ha-camera-stream");
    el.hass = this._hass;
    el.stateObj = stateObj;
    el.muted = true;
    el.controls = false;
    el.allowExoPlayer = true;
    el.className = "stream";
    vp.appendChild(el);
    this._streamEl = el;
    this._streamEntity = entity;
  }

  // ha-camera-stream is lazy-loaded by the frontend. Building a picture-entity card pulls it in.
  async _ensureStreamElement() {
    if (customElements.get("ha-camera-stream") || this._noStreamElement) return;
    try {
      const helpers = await window.loadCardHelpers?.();
      const card = helpers?.createCardElement({ type: "picture-entity", entity: this._ents.teleCamera, camera_view: "live" });
      if (card) {
        card.hass = this._hass;
        card.style.display = "none";
        this.shadowRoot.appendChild(card);
        setTimeout(() => card.remove(), 3000);
      }
      await Promise.race([customElements.whenDefined("ha-camera-stream"), new Promise((r) => setTimeout(r, 2500))]);
      this._noStreamElement = !customElements.get("ha-camera-stream"); // wait once, not on every switch
    } catch (_) {
      /* fall back to stills */
    }
  }

  _setView(view) {
    if (view === this._view) return;
    // The camera leaving the main view goes to the PiP: show its last live frame at once, since a still from the
    // scope takes seconds (the tele waits for a keyframe).
    const frame = this._view !== "stack" && view !== "stack" ? this._captureMain() : null;
    this._view = view;
    this._renderViewport();
    this._pipToken = (this._pipToken || 0) + 1;
    this._pipLoading = false;
    const img = this.$("pip-img");
    if (frame) img.src = frame;
    else img.removeAttribute("src");
    this.$("pip").classList.toggle("pending", !frame);
    this._refreshPip();
    this._update();
  }

  // The current frame of the main view as a small JPEG, or null when nothing is playing yet.
  _captureMain() {
    const find = (node) => {
      if (!node) return null;
      if (node.tagName === "VIDEO" && node.videoWidth) return node;
      if (node.tagName === "IMG" && node.complete && node.naturalWidth) return node;
      for (const child of [...(node.shadowRoot?.children || []), ...node.children]) {
        const found = find(child);
        if (found) return found;
      }
      return null;
    };
    const media = find(this.$("viewport"));
    if (!media) return null;
    const w = media.videoWidth || media.naturalWidth;
    const h = media.videoHeight || media.naturalHeight;
    const scale = Math.min(1, 480 / w);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    try {
      canvas.getContext("2d").drawImage(media, 0, 0, canvas.width, canvas.height);
      return canvas.toDataURL("image/jpeg", 0.8);
    } catch (_) {
      return null; // a cross-origin frame cannot be read back
    }
  }

  // Load a fresh still for the PiP off-screen and show it once it has arrived, unless the cameras were swapped
  // in the meantime.
  _refreshPip() {
    if (!this._built || this._view === "stack" || this._pipLoading) return;
    const other = this._st(this._view === "tele" ? "wideCamera" : "teleCamera");
    const url = other?.attributes.entity_picture;
    if (!url) return;
    const token = this._pipToken;
    const next = new Image();
    this._pipLoading = true;
    next.onload = () => {
      if (token !== this._pipToken) return;
      this._pipLoading = false;
      this.$("pip-img").src = next.src;
      this.$("pip").classList.remove("pending");
    };
    next.onerror = () => {
      if (token === this._pipToken) this._pipLoading = false;
    };
    next.src = `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
  }

  // ----- joystick -----

  _wireJoystick() {
    const pad = this.$("joystick");
    const knob = this.$("knob");
    const move = (ev) => {
      const r = pad.getBoundingClientRect();
      const radius = r.width / 2;
      let dx = ev.clientX - (r.left + radius);
      let dy = ev.clientY - (r.top + radius);
      const dist = Math.min(Math.hypot(dx, dy), radius);
      const ang = Math.atan2(dy, dx);
      dx = Math.cos(ang) * dist;
      dy = Math.sin(ang) * dist;
      knob.style.transform = `translate(${dx}px, ${dy}px)`;
      const mag = dist / radius;
      // The scope's joystick: 0 lowers rotation (right), 90 raises pitch (up).
      this._joy = mag < 0.15 ? null : { angle: ((Math.atan2(-dy, dx) / RAD) + 360) % 360, length: Math.min(1, mag) };
    };
    pad.addEventListener("pointerdown", (ev) => {
      pad.setPointerCapture(ev.pointerId);
      pad.classList.add("active");
      move(ev);
      this._startJoystick();
    });
    pad.addEventListener("pointermove", (ev) => pad.classList.contains("active") && move(ev));
    const end = () => {
      if (!pad.classList.contains("active")) return;
      pad.classList.remove("active");
      knob.style.transform = "";
      this._joy = null;
      this._stopJoystick(true);
    };
    pad.addEventListener("pointerup", end);
    pad.addEventListener("pointercancel", end);
  }

  _startJoystick() {
    if (this._joyTimer) return;
    const send = async () => {
      if (!this._joy || this._joyInflight) return;
      this._joyInflight = true;
      try {
        await this._hass.callService(DOMAIN, "move", { ...this._joy, seconds: 1.2 }, this._target);
      } catch (err) {
        this._toast(err?.message || String(err), "error");
        this._stopJoystick();
      } finally {
        this._joyInflight = false;
      }
    };
    send();
    this._joyTimer = setInterval(send, 800);
  }

  _stopJoystick(sendStop = false) {
    clearInterval(this._joyTimer);
    this._joyTimer = null;
    if (sendStop && this._hass) {
      this._hass.callService(DOMAIN, "move", { angle: 0, length: 0, seconds: 0.1 }, this._target).catch(() => {});
    }
  }

  // ----- capture -----

  _capturing() {
    return this._val("jobState") === "running";
  }

  _shutter() {
    if (this._capturing()) {
      this._confirm("Stop the capture? Frames taken so far stay on the SD card.", () =>
        this._press("stopCapture", "Stopping capture…"),
      );
      return;
    }
    const s = this._settings;
    this._call("start_capture", {
      frames: Number(s.frames),
      exposure: s.exposure,
      gain: Number(s.gain),
      filter: s.filter,
    }).then((ok) => ok && this._toast(`Capturing ${s.frames} × ${s.exposure} s`));
  }

  // ----- panels -----

  _renderPanel() {
    const panel = this.$("panel");
    const render = { shoot: this._panelShoot, goto: this._panelGoto, gallery: this._panelGallery, device: this._panelDevice }[
      this._tab
    ];
    panel.innerHTML = render.call(this);
    panel.scrollTop = 0;
    this.shadowRoot.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === this._tab));
    this[`_wire_${this._tab}`]?.(panel);
    if (this._tab === "gallery" && !this._gallery && !this._galleryLoading) this._loadGallery();
  }

  _seg(name, options, current) {
    return `<div class="seg" data-name="${name}">${options
      .map((o) => {
        const id = typeof o === "object" ? o.id : o;
        const label = typeof o === "object" ? o.label : o;
        return `<button data-value="${esc(id)}" class="${String(current) === String(id) ? "on" : ""}">${esc(label)}</button>`;
      })
      .join("")}</div>`;
  }

  _panelShoot() {
    const s = this._settings;
    const filt = FILTERS.find((f) => f.id === s.filter);
    return `
      <div class="group">
        <label>Exposure</label>
        ${this._seg("exposure", EXPOSURES.map((e) => ({ id: e, label: `${e} s` })), s.exposure)}
      </div>
      <div class="group">
        <label>Filter <small>${esc(filt?.hint || "")}</small></label>
        ${this._seg("filter", FILTERS, s.filter)}
      </div>
      <div class="group">
        <label>Gain <small id="gain-val">${s.gain}</small></label>
        <input type="range" min="0" max="200" step="5" value="${s.gain}" data-name="gain" class="slider">
        <div class="ticks"><span>0</span><span>60</span><span>120</span><span>200</span></div>
      </div>
      <div class="group">
        <label>Frames</label>
        <div class="frames">
          <button class="step" data-step="-10">−</button>
          <input type="number" min="1" max="500" value="${s.frames}" data-name="frames" class="num">
          <button class="step" data-step="10">+</button>
        </div>
        <div class="chips">${FRAME_PRESETS.map((n) => `<button class="chip ${Number(s.frames) === n ? "on" : ""}" data-frames="${n}">${n}</button>`).join("")}</div>
      </div>
      <div class="total" id="shoot-total"></div>
      <div class="darks-note" id="darks-note"></div>
      <button class="btn big primary" id="go-capture"></button>`;
  }

  _wire_shoot(panel) {
    const sync = () => {
      this._saveSettings();
      this._updateShoot();
      this._update();
    };
    panel.querySelectorAll(".seg").forEach((seg) =>
      seg.addEventListener("click", (ev) => {
        const b = ev.target.closest("button");
        if (!b) return;
        this._settings[seg.dataset.name] = b.dataset.value;
        seg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
        if (seg.dataset.name === "filter") this._renderPanel();
        sync();
      }),
    );
    const gain = panel.querySelector('[data-name="gain"]');
    gain.addEventListener("input", () => {
      this._settings.gain = Number(gain.value);
      panel.querySelector("#gain-val").textContent = gain.value;
      sync();
    });
    const frames = panel.querySelector('[data-name="frames"]');
    const setFrames = (n) => {
      n = Math.max(1, Math.min(500, Math.round(n) || 1));
      this._settings.frames = n;
      frames.value = n;
      panel.querySelectorAll(".chip").forEach((c) => c.classList.toggle("on", Number(c.dataset.frames) === n));
      sync();
    };
    frames.addEventListener("change", () => setFrames(Number(frames.value)));
    panel.querySelectorAll(".step").forEach((b) =>
      b.addEventListener("click", () => setFrames(Number(this._settings.frames) + Number(b.dataset.step))),
    );
    panel.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => setFrames(Number(c.dataset.frames))));
    panel.querySelector("#go-capture").addEventListener("click", () => this._shutter());
    this._updateShoot();
  }

  _updateShoot() {
    if (this._tab !== "shoot") return;
    const s = this._settings;
    const total = this.$("shoot-total");
    if (!total) return;
    total.innerHTML = `<span>Total integration</span><b>${fmtDuration(s.frames * s.exposure)}</b>`;
    const darks = this._num("teleDarks");
    const note = this.$("darks-note");
    note.innerHTML =
      darks === null
        ? ""
        : darks > 0
          ? `${icon("mdi:check-circle-outline")} ${darks} tele darks in the library`
          : `${icon("mdi:alert-outline")} No tele darks yet. Take some from Device.`;
    note.className = `darks-note ${darks ? "ok" : "warn"}`;
    const btn = this.$("go-capture");
    const running = this._capturing();
    btn.innerHTML = running ? `${icon("mdi:stop")}Stop capture` : `${icon("mdi:record-circle-outline")}Start capture`;
    btn.classList.toggle("danger", running);
    btn.classList.toggle("primary", !running);
    btn.disabled =
      this._busy.has("start_capture") || this._busy.has("stopCapture") || (!running && this._val("busyElsewhere") === "on");
  }

  _panelGoto() {
    return `
      <div class="search">
        ${icon("mdi:magnify")}
        <input type="search" id="q" placeholder="Search M 42, Orion, NGC 7000…" value="${esc(this._query)}">
      </div>
      <div class="filters">
        <div class="chips" id="type-chips">${Object.entries(TYPES)
          .map(([k, t]) => `<button class="chip ${this._typeFilter === k ? "on" : ""}" data-type="${k}">${t.label}</button>`)
          .join("")}</div>
        <label class="toggle"><input type="checkbox" id="up-only" ${this._upOnly ? "checked" : ""}><span></span>Above 20°</label>
      </div>
      <div class="quick">
        <button class="btn" data-press="calibrate">${icon("mdi:star-shooting-outline")}Calibrate</button>
        <button class="btn" data-press="pointUp">${icon("mdi:arrow-up-bold-circle-outline")}Point up</button>
      </div>
      <div class="targets" id="targets"></div>
      <details class="custom">
        <summary>${icon("mdi:map-marker-plus-outline")}Custom coordinates</summary>
        <div class="custom-grid">
          <input id="c-name" placeholder="Name" value="Custom">
          <input id="c-ra" type="number" step="any" min="0" max="24" placeholder="RA (hours)">
          <input id="c-dec" type="number" step="any" min="-90" max="90" placeholder="Dec (degrees)">
          <button class="btn primary" id="c-go">Go to</button>
        </div>
      </details>`;
  }

  _wire_goto(panel) {
    const q = panel.querySelector("#q");
    q.addEventListener("input", () => {
      this._query = q.value;
      this._renderTargets();
    });
    panel.querySelector("#type-chips").addEventListener("click", (ev) => {
      const t = ev.target.closest("button")?.dataset.type;
      if (!t) return;
      this._typeFilter = t;
      panel.querySelectorAll("#type-chips .chip").forEach((c) => c.classList.toggle("on", c.dataset.type === t));
      this._renderTargets();
    });
    panel.querySelector("#up-only").addEventListener("change", (ev) => {
      this._upOnly = ev.target.checked;
      this._renderTargets();
    });
    panel.querySelectorAll("[data-press]").forEach((b) =>
      b.addEventListener("click", () =>
        this._press(b.dataset.press, b.dataset.press === "calibrate" ? "Calibrating… this needs stars" : "Pointing straight up"),
      ),
    );
    panel.querySelector("#targets").addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-goto]");
      if (b) this._goto(CATALOG.find((o) => o.id === b.dataset.goto));
    });
    panel.querySelector("#c-go").addEventListener("click", () => {
      const ra = parseFloat(panel.querySelector("#c-ra").value);
      const dec = parseFloat(panel.querySelector("#c-dec").value);
      if (!(ra >= 0 && ra <= 24 && dec >= -90 && dec <= 90)) {
        this._toast("RA is 0–24 hours, Dec is −90–90 degrees", "error");
        return;
      }
      this._goto({ id: panel.querySelector("#c-name").value || "Custom", ra, dec });
    });
    this._renderTargets();
  }

  _renderTargets() {
    const box = this.$("targets");
    if (!box) return;
    const { latitude: lat, longitude: lon } = this._hass.config;
    const now = new Date();
    const q = this._query.trim().toLowerCase().replace(/\s+/g, "");
    let rows = CATALOG.map((o) => ({ ...o, ...altAz(o.ra, o.dec, lat, lon, now) }))
      .filter((o) => this._typeFilter === "all" || o.type === this._typeFilter)
      .filter((o) => !q || `${o.id}${o.name}${o.aka}`.toLowerCase().replace(/\s+/g, "").includes(q))
      .filter((o) => !this._upOnly || q || o.alt >= 20)
      .sort((a, b) => b.alt - a.alt);
    if (!rows.length) {
      box.innerHTML = `<div class="empty-list">${icon("mdi:weather-night")}<span>Nothing ${this._upOnly ? "above 20° " : ""}matches right now.</span></div>`;
      return;
    }
    const current = this._lastGoto?.id;
    box.innerHTML = rows
      .map(
        (o) => `
        <div class="target ${o.alt < 0 ? "below" : ""} ${current === o.id ? "current" : ""}">
          <div class="t-icon t-${o.type}">${icon(TYPES[o.type].icon)}</div>
          <div class="t-main">
            <div class="t-name">${esc(o.id)}${o.name ? ` <span>${esc(o.name)}</span>` : ""}</div>
            <div class="t-meta">${TYPES[o.type].one} · mag ${o.mag.toFixed(1)} · ${fmtRa(o.ra)} ${fmtDec(o.dec)}</div>
          </div>
          <div class="t-alt" title="Altitude, azimuth">
            <b>${o.alt.toFixed(0)}°</b><small>${compass(o.az)}</small>
            <div class="altbar"><i style="width:${Math.max(0, Math.min(100, (o.alt / 90) * 100))}%"></i></div>
          </div>
          <button class="btn goto-btn" data-goto="${esc(o.id)}" ${o.alt < 0 || this._busy.has("goto") ? "disabled" : ""}>
            ${this._busy.has("goto") && this._pendingGoto === o.id ? '<span class="spin"></span>' : icon("mdi:crosshairs-gps")}
          </button>
        </div>`,
      )
      .join("");
  }

  async _goto(o) {
    this._pendingGoto = o.id;
    this._toast(`Slewing to ${o.id}…`);
    this._renderTargets();
    const ok = await this._call("goto", { name: o.id, ra_hours: o.ra, dec_degrees: o.dec }, "goto");
    this._pendingGoto = null;
    if (ok) {
      this._lastGoto = { id: o.id, name: o.name || "", at: Date.now() };
      localStorage.setItem("dwarf3-card-last-goto", JSON.stringify(this._lastGoto));
      this._toast(`Tracking ${o.id}`);
    }
    this._renderTargets();
    this._update();
  }

  _panelGallery() {
    const stack = this._st("latestStack");
    const a = stack?.attributes || {};
    const hero = stack?.attributes.entity_picture
      ? `<div class="hero" id="hero">
          <img src="${esc(a.entity_picture)}" alt="">
          <div class="hero-meta">
            <span class="kicker">Latest stack</span>
            <b>${esc(a.target || "Capture")}</b>
            <span>${[a.camera && a.camera.toUpperCase(), a.exposure_s && `${a.exposure_s} s`, a.gain !== undefined && `gain ${a.gain}`, a.started]
              .filter(Boolean)
              .map(esc)
              .join(" · ")}</span>
          </div>
        </div>`
      : "";
    let grid;
    if (this._galleryError) grid = `<div class="empty-list">${icon("mdi:sd")}<span>${esc(this._galleryError)}</span></div>`;
    else if (!this._gallery) grid = `<div class="empty-list"><span class="spin"></span><span>Reading the SD card…</span></div>`;
    else if (!this._gallery.length) grid = `<div class="empty-list">${icon("mdi:image-off-outline")}<span>No sessions on the card yet.</span></div>`;
    else
      grid = `<div class="grid">${this._gallery
        .map((item, i) => {
          const p = parseSession(item.session);
          return `<button class="thumb" data-i="${i}">
            ${item.thumbnail ? `<img loading="lazy" src="${esc(item.thumbnail)}" alt="">` : `<div class="no-thumb">${icon("mdi:image-filter-hdr")}</div>`}
            <span class="thumb-cap"><b>${esc(p.target)}</b><small>${p.date ? p.date.toLocaleDateString(undefined, { month: "short", day: "numeric" }) : ""}${p.exposure ? ` · ${p.exposure} s` : ""}</small></span>
          </button>`;
        })
        .join("")}</div>`;
    const count = this._val("sessions");
    return `${hero}
      <div class="section-head"><span>On the SD card${count ? ` · ${count}` : ""}</span>
        <button class="icon-btn" id="g-refresh" title="Refresh">${icon("mdi:refresh")}</button></div>
      ${grid}`;
  }

  _wire_gallery(panel) {
    panel.querySelector("#g-refresh").addEventListener("click", () => {
      this._gallery = null;
      this._galleryError = null;
      this._renderPanel();
    });
    panel.querySelector("#hero")?.addEventListener("click", () => {
      const a = this._st("latestStack").attributes;
      this._openLightbox({ session: a.session, title: a.target }, a.entity_picture);
    });
    panel.querySelector(".grid")?.addEventListener("click", (ev) => {
      const b = ev.target.closest(".thumb");
      if (b) this._openLightbox(this._gallery[Number(b.dataset.i)]);
    });
  }

  async _loadGallery() {
    this._galleryLoading = true;
    try {
      const res = await this._hass.callWS({ type: "media_source/browse_media", media_content_id: `media-source://${DOMAIN}` });
      let children = res.children || [];
      // More than one scope: the root is one folder per scope.
      if (children.length && children[0].can_expand) {
        const entryId = this._hass.entities?.[this._target.entity_id]?.config_entry_id;
        const folder = children.find((c) => c.media_content_id.endsWith(`/${entryId}`)) || children[0];
        children = (await this._hass.callWS({ type: "media_source/browse_media", media_content_id: folder.media_content_id })).children || [];
      }
      this._gallery = children
        .map((c) => ({
          id: c.media_content_id,
          session: decodeURIComponent(c.media_content_id.split("/").pop()),
          title: c.title,
          thumbnail: c.thumbnail,
        }))
        .sort((a, b) => (parseSession(b.session).date || 0) - (parseSession(a.session).date || 0));
      this._galleryError = null;
    } catch (err) {
      this._galleryError = err?.message || "Could not read the SD card.";
    } finally {
      this._galleryLoading = false;
      if (this._tab === "gallery") this._renderPanel();
    }
  }

  async _openLightbox(item, url) {
    const lb = this.$("lightbox");
    const img = this.$("lb-img");
    this._lbSession = item.session;
    img.src = item.thumbnail || url || "";
    const p = parseSession(item.session);
    this.$("lb-title").innerHTML = `<b>${esc(p.target || item.title)}</b><span>${[
      p.camera && p.camera.toUpperCase(),
      p.exposure && `${p.exposure} s`,
      p.gain !== undefined && `gain ${p.gain}`,
      p.date && p.date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }),
    ]
      .filter(Boolean)
      .map(esc)
      .join(" · ")}</span>`;
    this.$("lb-delete").style.display = item.session ? "" : "none";
    lb.classList.add("show");
    try {
      if (!url && item.id) url = (await this._hass.callWS({ type: "media_source/resolve_media", media_content_id: item.id })).url;
      if (url) {
        img.src = url;
        this.$("lb-open").href = url;
      }
    } catch (err) {
      this._toast(err?.message || "Could not load the full image", "error");
    }
  }

  _panelDevice() {
    const action = (role, ic, label, sub) =>
      `<button class="action" data-press="${role}" ${this._ents[role] ? "" : "disabled"}>
        ${icon(ic)}<b>${label}</b><small>${sub}</small></button>`;
    return `
      <div class="actions">
        ${action("prepare", "mdi:power", "Prepare", "Wake after power on")}
        ${action("calibrate", "mdi:star-shooting-outline", "Calibrate", "Plate solve on stars")}
        ${action("pointUp", "mdi:arrow-up-bold-circle-outline", "Point up", "Straight to zenith")}
        ${action("closeBarrel", "mdi:archive-arrow-down-outline", "Close barrel", "Turn it to stow")}
      </div>

      <div class="section-head"><span>Nudge</span></div>
      <div class="dpad">
        <button data-nudge="90" class="up">${icon("mdi:chevron-up")}</button>
        <button data-nudge="180" class="left">${icon("mdi:chevron-left")}</button>
        <button data-nudge="0" class="right">${icon("mdi:chevron-right")}</button>
        <button data-nudge="270" class="down">${icon("mdi:chevron-down")}</button>
        <div class="dpad-mid">${icon("mdi:crosshairs")}</div>
      </div>

      <div class="section-head"><span>Dark frames</span><small id="dark-counts"></small></div>
      <div class="group">
        ${this._seg("darkExposure", EXPOSURES.map((e) => ({ id: e, label: `${e} s` })), this._settings.darkExposure)}
        <div class="row">
          ${this._seg("darkWide", [{ id: "false", label: "Tele" }, { id: "true", label: "Wide" }], String(this._settings.darkWide))}
          <input type="number" class="num small" min="1" max="500" value="${this._settings.darkFrames}" id="dark-frames">
          <button class="btn" id="dark-go">${icon("mdi:circle-half-full")}Take</button>
        </div>
        <small class="hint">Close the barrel first. Darks match on exposure, gain and temperature.</small>
      </div>

      <div class="section-head"><span>Status</span></div>
      <div class="kv" id="kv"></div>`;
  }

  _wire_device(panel) {
    panel.querySelectorAll("[data-press]").forEach((b) =>
      b.addEventListener("click", () => {
        const role = b.dataset.press;
        if (role === "closeBarrel")
          this._confirm("Close the barrel? It turns to its stowed position and any capture stops.", () =>
            this._press(role, "Closing the barrel"),
          );
        else this._press(role, `${b.querySelector("b").textContent}…`);
      }),
    );
    panel.querySelectorAll("[data-nudge]").forEach((b) =>
      b.addEventListener("click", () =>
        this._call("move", { angle: Number(b.dataset.nudge), length: 0.3, seconds: 1 }, `nudge${b.dataset.nudge}`),
      ),
    );
    panel.querySelectorAll(".seg").forEach((seg) =>
      seg.addEventListener("click", (ev) => {
        const b = ev.target.closest("button");
        if (!b) return;
        const v = b.dataset.value;
        this._settings[seg.dataset.name] = seg.dataset.name === "darkWide" ? v === "true" : v;
        seg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
        this._saveSettings();
      }),
    );
    const frames = panel.querySelector("#dark-frames");
    frames.addEventListener("change", () => {
      this._settings.darkFrames = Math.max(1, Math.min(500, Number(frames.value) || 20));
      frames.value = this._settings.darkFrames;
      this._saveSettings();
    });
    panel.querySelector("#dark-go").addEventListener("click", () => {
      const s = this._settings;
      this._call("start_dark", { frames: Number(s.darkFrames), exposure: s.darkExposure, wide: !!s.darkWide }).then(
        (ok) => ok && this._toast(`Taking ${s.darkFrames} darks`),
      );
    });
    this._updateDevice();
  }

  _updateDevice() {
    if (this._tab !== "device") return;
    const kv = this.$("kv");
    if (!kv) return;
    const onOff = (role, on, off) => (this._val(role) === null ? "—" : this._val(role) === "on" ? on : off);
    const rows = [
      ["Scope", onOff("online", "Online", "Offline")],
      ["DWARFLAB app", onOff("appConnected", "Connected", "Not connected")],
      ["Tracking", onOff("tracking", "On", "Off")],
      ["Battery", this._fmt("battery")],
      ["Body", this._fmt("bodyTemp", 1)],
      ["Tele sensor", this._fmt("teleTemp", 1)],
      ["Wide sensor", this._fmt("wideTemp", 1)],
      ["SD free", `${this._fmt("sdFree", 1)}${this._num("sdUsed") !== null ? ` · ${this._num("sdUsed").toFixed(0)}% used` : ""}`],
      ["Sessions", this._val("sessions") ?? "—"],
      ["Relay", this._val("relayVersion") ?? "—"],
    ];
    kv.innerHTML = rows.map(([k, v]) => `<div><span>${k}</span><b>${esc(v)}</b></div>`).join("");
    const counts = this.$("dark-counts");
    if (counts) counts.textContent = `${this._val("teleDarks") ?? "—"} tele · ${this._val("wideDarks") ?? "—"} wide`;
    this.shadowRoot.querySelectorAll("#panel [data-press]").forEach((b) => b.classList.toggle("busy", this._busy.has(b.dataset.press)));
  }

  // ----- state -> DOM -----

  _tick() {
    if (!this._built) return;
    this._update();
    if (this._tab === "goto") this._renderTargets();
  }

  _update() {
    if (!this._built || !this._hass) return;
    const $ = (id) => this.$(id);
    const online = this._val("online") === "on";
    const needsPrepare = this._val("needsPrepare") === "on";
    const running = this._capturing();
    const elsewhere = this._val("busyElsewhere") === "on";

    const theme = this._config.theme || "auto";
    const dark = theme === "dark" || (theme !== "light" && this._hass.themes?.darkMode !== false);
    $("card").classList.toggle("light", !dark);

    $("online-dot").className = `dot ${online ? "on" : "off"}`;
    const pill = $("state-pill");
    const [pillText, pillCls] = !online
      ? ["Offline", "off"]
      : running
        ? [elsewhere ? "Capturing (app)" : "Capturing", "rec"]
        : needsPrepare
          ? ["Needs prepare", "warn"]
          : this._val("tracking") === "on"
            ? ["Tracking", "ok"]
            : ["Ready", "ok"];
    pill.textContent = pillText;
    pill.className = `pill ${pillCls}`;

    // Sky
    const { latitude: lat, longitude: lon } = this._hass.config;
    const sun = sunRaDec();
    const sunAlt = altAz(sun.ra, sun.dec, lat, lon).alt;
    const phase = skyPhase(sunAlt);
    $("stat-sky").className = `stat sky ${phase.cls}`;
    $("stat-sky").innerHTML = `${glyph(sunAlt > 0 ? "sun" : sunAlt > -12 ? "dusk" : "moon")}<b>${phase.label}</b>`;

    const batt = this._num("battery");
    $("stat-batt").querySelector("b").textContent = batt === null ? "—" : `${batt.toFixed(0)}%`;
    $("stat-batt").querySelector(".level").setAttribute("width", batt === null ? 0 : (16.2 * Math.max(4, Math.min(100, batt))) / 100);
    $("stat-batt").classList.toggle("low", batt !== null && batt < 20);
    $("stat-batt").classList.toggle("mid", batt !== null && batt >= 20 && batt < 40);
    $("stat-temp").querySelector("b").textContent = this._fmt("bodyTemp");
    $("stat-sd").querySelector("b").textContent = this._fmt("sdFree", 0);

    // View switch + viewport
    this.shadowRoot.querySelectorAll("#view-switch button").forEach((b) => b.classList.toggle("on", b.dataset.view === this._view));
    if (this._streamEl) {
      this._streamEl.hass = this._hass;
      const st = this._hass.states[this._streamEntity];
      if (st && st !== this._streamEl.stateObj) this._streamEl.stateObj = st;
    }
    if (this._view === "stack" && this._stackImg) {
      const pic = this._st("latestStack")?.attributes.entity_picture;
      if (pic && this._stackImg.getAttribute("src") !== pic) this._stackImg.src = pic;
    }
    $("pip").style.display = this._view === "stack" ? "none" : "";
    $("pip-label").textContent = this._view === "tele" ? "Wide" : "Tele";
    if (!$("pip-img").getAttribute("src")) this._refreshPip();
    $("reticle").style.display = this._view === "stack" ? "none" : "";

    // HUD
    const pitch = this._num("pitch");
    const rot = this._num("rotation");
    $("hud-pitch").textContent = pitch === null ? "—" : `${pitch.toFixed(1)}°`;
    $("hud-rot").textContent = rot === null ? "—" : `${rot.toFixed(1)}°`;
    const tracking = this._val("tracking") === "on";
    $("hud-track").innerHTML = tracking ? `<i class="live"></i>Tracking` : "";
    if (!this._lastGoto) this._lastGoto = JSON.parse(localStorage.getItem("dwarf3-card-last-goto") || "null");
    const job = this._st("jobState")?.attributes || {};
    const jobTarget = job.session ? parseSession(job.session).target : null;
    const stackAttrs = this._st("latestStack")?.attributes || {};
    let target = running ? jobTarget || this._lastGoto?.id : this._lastGoto?.id;
    let sub = "";
    if (this._view === "stack") {
      target = stackAttrs.target;
      sub = "Latest stack";
    } else if (target) {
      const cat = CATALOG.find((o) => o.id === target);
      sub = cat?.name || this._lastGoto?.name || "";
    }
    $("hud-target").innerHTML = target ? `<b>${esc(target)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}` : "";

    $("prepare-banner").classList.toggle("show", online && needsPrepare);
    $("banner-prepare").disabled = this._busy.has("prepare");
    $("joystick").classList.toggle("disabled", !online || needsPrepare || this._view === "stack");

    // Shutter
    const progress = this._num("progress");
    const shutter = $("shutter");
    shutter.classList.toggle("rec", running);
    shutter.classList.toggle("busy", this._busy.has("start_capture") || this._busy.has("stopCapture"));
    shutter.disabled = !online || needsPrepare || (elsewhere && !running);
    shutter.title = running ? "Stop capture" : "Start capture";
    const C = 2 * Math.PI * 45;
    $("ring").style.strokeDasharray = `${C}`;
    $("ring").style.strokeDashoffset = `${C * (1 - (running && progress !== null ? progress / 100 : 0))}`;
    const s = this._settings;
    $("rail-summary").innerHTML = running
      ? `<b>${progress === null ? "…" : `${progress.toFixed(0)}%`}</b>`
      : `<b>${s.exposure}s</b><span>G${s.gain}</span><span>${FILTERS.find((f) => f.id === s.filter)?.label}</span><span>×${s.frames}</span>`;

    const strip = $("capture-strip");
    strip.classList.toggle("show", running);
    $("stage").classList.toggle("capturing", running);
    if (running) {
      const frames = Number(job.frames) || null;
      const captured = this._num("framesCaptured") ?? Number(job.captured) ?? 0;
      const exp = jobTarget ? parseSession(job.session).exposure : Number(s.exposure);
      const left = frames ? (frames - captured) * (exp || 0) : null;
      $("strip-fill").style.width = `${progress ?? 0}%`;
      $("strip-text").innerHTML = `<span><i class="live rec"></i>${esc(jobTarget || "Capturing")}</span><span>${captured}${
        frames ? ` / ${frames}` : ""
      } frames${left ? ` · ${fmtDuration(left)} left` : ""}</span>`;
    }

    // Capture finished -> refresh the gallery next time it opens
    const finished = this._st("captureFinished")?.state;
    if (this._lastFinished !== undefined && finished !== this._lastFinished) {
      const type = this._st("captureFinished").attributes.event_type;
      this._toast(type === "capture_failed" ? "Capture failed" : "Capture finished", type === "capture_failed" ? "error" : "info");
      this._gallery = null;
    }
    this._lastFinished = finished;

    this._updateShoot();
    this._updateDevice();
  }
}

const STYLES = `
:host {
  --d-bg: #07080b;
  --d-panel: #0f1116;
  --d-raise: #171a21;
  --d-line: rgba(255,255,255,.08);
  --d-text: #eef0f4;
  --d-mute: #8b919e;
  --d-accent: #ff6b35;
  --d-accent-2: #ffb347;
  --d-ok: #3ddc97;
  --d-warn: #ffc24b;
  --d-bad: #ff4d5e;
  --d-radius: 18px;
  --d-top: linear-gradient(180deg, #0d0f14, #0a0b0f);
  --d-seg-on: #171a21;
  --d-seg-shadow: inset 0 0 0 1px rgba(255,107,53,.5);
  --d-shadow: none;
  --d-scroll: #333;
  --d-toast: #20242d;
  --d-danger-text: #ff8b96;
  --d-on-accent: #160a03;
  display: block;
  container-type: inline-size;
}
* { box-sizing: border-box; }
ha-card {
  display: block;
  background: var(--d-bg);
  color: var(--d-text);
  border-radius: var(--ha-card-border-radius, 20px);
  overflow: hidden;
  position: relative;
  border: 1px solid var(--d-line);
  font-family: "DWARF3 Barlow", Barlow, Bahnschrift, "DIN Alternate", "Avenir Next", system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}
/* Light: the dock and top bar go light. The stage and the photo overlays stay dark, like a camera app. */
ha-card.light {
  --d-bg: #f3f4f7;
  --d-panel: #ffffff;
  --d-raise: #eceef2;
  --d-line: rgba(15,20,30,.09);
  --d-text: #141720;
  --d-mute: #5f6675;
  --d-accent: #ec5a1f;
  --d-accent-2: #ff9a3c;
  --d-ok: #0f9b67;
  --d-warn: #b07800;
  --d-bad: #dc3545;
  --d-top: #ffffff;
  --d-seg-on: #ffffff;
  --d-seg-shadow: 0 1px 3px rgba(15,20,30,.14), inset 0 0 0 1px rgba(236,90,31,.55);
  --d-shadow: 0 1px 2px rgba(15,20,30,.05);
  --d-scroll: #c8ccd4;
  --d-toast: #ffffff;
  --d-danger-text: #c82333;
}
.stage, .lightbox {
  --d-bg: #07080b; --d-panel: #0f1116; --d-raise: #171a21; --d-line: rgba(255,255,255,.08);
  --d-text: #eef0f4; --d-mute: #a3a9b5; --d-ok: #3ddc97; --d-warn: #ffc24b; --d-bad: #ff4d5e;
  --d-accent: #ff6b35; --d-accent-2: #ffb347; --d-danger-text: #ff8b96;
  color: var(--d-text);
}
ha-card.light .stage .banner { box-shadow: 0 12px 40px rgba(0,0,0,.4); }
ha-card.night { filter: grayscale(1) sepia(1) saturate(6) hue-rotate(-40deg) brightness(.75); }
ha-card.empty { display:flex; gap:12px; align-items:center; padding:24px; color: var(--d-mute); }
ha-icon { --mdc-icon-size: 18px; display:inline-flex; }
button { font: inherit; color: inherit; cursor: pointer; border: 0; background: none; -webkit-tap-highlight-color: transparent; }
button:disabled { opacity: .4; cursor: not-allowed; }

.shell { display: grid; grid-template-columns: minmax(0, 1fr); grid-template-areas: "top" "stage" "dock"; height: 100%; }
.layout-wide .shell { grid-template-columns: minmax(0, 1fr) clamp(360px, 30%, 440px); grid-template-areas: "top top" "stage dock"; grid-template-rows: auto minmax(0, 1fr); }
.layout-wide .stage, .layout-tall .stage { aspect-ratio: auto; height: 100%; min-height: 0; }
.layout-wide .dock { border-left: 1px solid var(--d-line); border-top: 0; min-height: 0; }
.layout-tall .shell { grid-template-rows: auto minmax(0, 1.15fr) minmax(0, 1fr); }
.layout-tall .dock { min-height: 0; }
.layout-wide .panel, .layout-tall .panel { max-height: none; min-height: 0; }
.layout-tall .panel { padding: 16px 20px; }
.layout-tall .tabs { padding: 8px 14px; }
.layout-phone .panel { max-height: none; overflow: visible; }

/* top bar */
.topbar { grid-area: top; display:flex; align-items:center; justify-content:space-between; gap:12px;
  padding: 10px 14px; background: var(--d-top); border-bottom: 1px solid var(--d-line); }
.brand { display:flex; align-items:center; gap:10px; min-width:0; }
.brand .name { font-weight: 650; font-size: 16px; letter-spacing: .02em; white-space: nowrap; padding: 4px 6px; margin: -4px -6px; border-radius: 8px; }
.brand .name:hover { background: var(--d-raise); }
.dot { width:8px; height:8px; border-radius:50%; background: var(--d-mute); flex: none; }
.dot.on { background: var(--d-ok); box-shadow: 0 0 10px var(--d-ok); }
.dot.off { background: var(--d-bad); }
.pill { font-size: 11px; font-weight: 600; letter-spacing:.04em; text-transform: uppercase; padding: 3px 9px; border-radius: 99px;
  background: var(--d-raise); color: var(--d-mute); white-space: nowrap; }
.pill.ok { color: var(--d-ok); background: rgba(61,220,151,.1); }
.pill.warn { color: var(--d-warn); background: rgba(255,194,75,.12); }
.pill.rec { color: #fff; background: var(--d-bad); animation: pulse 1.6s infinite; }
.pill.off { color: var(--d-bad); background: rgba(255,77,94,.1); }
.stats { display:flex; align-items:center; gap: 6px; flex-wrap: nowrap; overflow: hidden; }
.stat { display:inline-flex; align-items:center; gap:5px; font-size: 13px; color: var(--d-mute); padding: 4px 8px; border-radius: 10px; background: var(--d-raise); white-space: nowrap; }
.stat b { color: var(--d-text); font-weight: 600; font-variant-numeric: tabular-nums; }
.glyph { width: 18px; height: 18px; flex: none; }
.glyph.battery { width: 23px; }
.stat .glyph { color: var(--d-mute); }
.stat#stat-batt .glyph { color: var(--d-ok); }
.stat.mid#stat-batt .glyph { color: var(--d-warn); }
.stat.low .glyph, .stat.low b { color: var(--d-bad); }
.stat.sky.dark .glyph { color: #7d95ff; } .stat.sky.dusk .glyph { color: #a17bff; }
.stat.sky.twilight .glyph { color: var(--d-accent); } .stat.sky.day .glyph { color: var(--d-warn); }
ha-card.night #night-btn { color: var(--d-bad); }
@container (max-width: 560px) { .stat.sky, .stat#stat-temp { display:none; } }
@container (max-width: 440px) { .stat#stat-sd { display:none; } .topbar { padding: 10px; } }
.icon-btn { width: 32px; height: 32px; border-radius: 10px; display:inline-grid; place-items:center; color: var(--d-mute); }
.icon-btn:hover { background: var(--d-raise); color: var(--d-text); }

/* stage */
.stage { grid-area: stage; position: relative; aspect-ratio: 16 / 10; background: radial-gradient(ellipse at center, #10131b 0%, #040507 70%); overflow: hidden; user-select: none; }
.viewport, .viewport > * { position:absolute; inset:0; width:100%; height:100%; }
.viewport img, .viewport ha-camera-stream { object-fit: contain; }
.viewport ha-camera-stream { --video-max-height: 100%; display:flex; align-items:center; justify-content:center; }
.stack-img { object-fit: contain; background: #000; }
.no-signal { display:flex !important; flex-direction:column; align-items:center; justify-content:center; gap:8px; color: var(--d-mute); }
.no-signal ha-icon { --mdc-icon-size: 40px; }
.reticle { position:absolute; left:50%; top:50%; width: 64px; height: 64px; transform: translate(-50%,-50%); pointer-events:none; opacity:.55; }
.reticle span { position:absolute; background: rgba(255,255,255,.7); }
.reticle span:first-child { left: 50%; top:0; bottom:0; width:1px; -webkit-mask: linear-gradient(#000 35%, transparent 35% 65%, #000 65%); mask: linear-gradient(#000 35%, transparent 35% 65%, #000 65%); }
.reticle span:last-child { top:50%; left:0; right:0; height:1px; -webkit-mask: linear-gradient(90deg,#000 35%, transparent 35% 65%, #000 65%); mask: linear-gradient(90deg,#000 35%, transparent 35% 65%, #000 65%); }

.view-switch { position:absolute; top:12px; left:12px; display:flex; padding:3px; gap:2px; border-radius: 12px; background: rgba(10,11,15,.7); backdrop-filter: blur(10px); border: 1px solid var(--d-line); }
.view-switch button { padding: 6px 12px; border-radius: 9px; font-size: 13px; font-weight: 600; color: var(--d-mute); }
.view-switch button.on { background: var(--d-text); color: #000; }

.pip { position:absolute; top:12px; right:12px; width: 22%; max-width: 200px; min-width: 110px; aspect-ratio: 16/9; border-radius: 12px; overflow:hidden; border: 1px solid rgba(255,255,255,.18); background:#000; box-shadow: 0 6px 24px rgba(0,0,0,.5); padding:0; }
.pip img { width:100%; height:100%; object-fit: cover; display:block; }
.pip img:not([src]) { visibility: hidden; }
.pip.pending::after { content: ""; position: absolute; left: 50%; top: 50%; width: 18px; height: 18px; margin: -9px 0 0 -9px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.2); border-top-color: var(--d-accent); animation: spin .8s linear infinite; }
.pip span { position:absolute; left:6px; bottom:5px; font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; background: rgba(0,0,0,.6); padding: 2px 6px; border-radius: 6px; }

.hud { position:absolute; left: 14px; top: 58px; pointer-events:none; text-shadow: 0 1px 6px rgba(0,0,0,.8); }
.hud-target b { display:block; font-size: 22px; font-weight: 700; letter-spacing: -.01em; }
.hud-target span { font-size: 13px; color: rgba(255,255,255,.7); }
.hud-row { display:flex; gap: 12px; margin-top: 6px; font-size: 12px; color: rgba(255,255,255,.8); }
.hud-row span { display:inline-flex; align-items:center; gap:4px; }
.hud-row .glyph { width: 15px; height: 15px; opacity: .75; }
.hud-row b { font-variant-numeric: tabular-nums; font-weight: 600; }
i.live { display:inline-block; width:7px; height:7px; border-radius: 50%; background: var(--d-ok); margin-right: 5px; animation: pulse 1.6s infinite; }
i.live.rec { background: var(--d-bad); }

.banner { position:absolute; left:50%; top: 50%; transform: translate(-50%,-50%) scale(.96); opacity:0; pointer-events:none; transition: .25s;
  display:flex; align-items:center; gap: 14px; padding: 14px 16px; border-radius: 16px; background: rgba(15,17,22,.92); backdrop-filter: blur(14px);
  border: 1px solid rgba(255,194,75,.35); max-width: calc(100% - 40px); }
.banner.show { opacity:1; pointer-events:auto; transform: translate(-50%,-50%) scale(1); }
.banner > ha-icon { --mdc-icon-size: 28px; color: var(--d-warn); }
.banner b { display:block; } .banner span { font-size: 13px; color: var(--d-mute); }

.joystick { position:absolute; left: 22px; bottom: 22px; width: 128px; height: 128px; border-radius:50%; touch-action:none; cursor: grab; }
.joystick .ring { position:absolute; inset:0; border-radius:50%; background: radial-gradient(circle, rgba(255,255,255,.04) 0 40%, rgba(255,255,255,.08) 70%, rgba(255,255,255,.02));
  border: 1px solid rgba(255,255,255,.16); backdrop-filter: blur(6px); }
.joystick .knob { position:absolute; left: 50%; top: 50%; width: 52px; height: 52px; margin: -26px 0 0 -26px; border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #fff, #c9ced8 60%, #9aa1ad); box-shadow: 0 4px 16px rgba(0,0,0,.5); transition: transform .18s cubic-bezier(.2,.9,.3,1.3); }
.joystick.active { cursor: grabbing; } .joystick.active .knob { transition: none; }
.joystick.active .ring { border-color: var(--d-accent); box-shadow: 0 0 0 4px rgba(255,107,53,.15); }
.joystick span { position:absolute; font-size: 9px; color: rgba(255,255,255,.4); pointer-events:none; }
.j-n { top: 6px; left: 50%; transform: translateX(-50%); } .j-s { bottom: 6px; left: 50%; transform: translateX(-50%); }
.j-w { left: 7px; top: 50%; transform: translateY(-50%); } .j-e { right: 7px; top: 50%; transform: translateY(-50%); }
.joystick.disabled { opacity: .3; pointer-events: none; }

.rail { position:absolute; right: 18px; top: 50%; transform: translateY(-50%); display:flex; flex-direction:column; align-items:center; gap: 10px; }
.shutter { position:relative; width: 84px; height: 84px; border-radius: 50%; padding:0; display:grid; place-items:center; }
.shutter svg { position:absolute; inset:0; transform: rotate(-90deg); }
.shutter .track { fill: rgba(10,11,15,.55); stroke: rgba(255,255,255,.85); stroke-width: 4; }
.shutter .bar { fill: none; stroke: var(--d-accent); stroke-width: 6; stroke-linecap: round; transition: stroke-dashoffset .6s; }
.shutter .core { position:relative; width: 62px; height: 62px; border-radius: 50%; background: linear-gradient(145deg, var(--d-accent-2), var(--d-accent)); box-shadow: 0 0 24px rgba(255,107,53,.45); transition: .25s; }
.shutter:hover .core { transform: scale(1.04); }
.shutter.rec .track { stroke: rgba(255,255,255,.25); }
.shutter.rec .core { width: 30px; height: 30px; border-radius: 8px; background: var(--d-bad); box-shadow: 0 0 24px rgba(255,77,94,.6); }
.shutter.busy .core { animation: pulse 1s infinite; }
.rail-summary { display:flex; flex-direction:column; align-items:center; gap: 2px; padding: 6px 8px; border-radius: 12px; background: rgba(10,11,15,.6); backdrop-filter: blur(8px); font-size: 11px; color: var(--d-mute); border: 1px solid var(--d-line); font-variant-numeric: tabular-nums; }
.rail-summary b { color: var(--d-text); font-size: 13px; }

.capture-strip { position:absolute; left: 170px; right: 130px; bottom: 26px; padding: 10px 14px; border-radius: 14px; background: rgba(10,11,15,.75); backdrop-filter: blur(10px); border: 1px solid var(--d-line);
  opacity:0; transform: translateY(10px); transition: .3s; pointer-events:none; }
.capture-strip.show { opacity:1; transform:none; }
.strip-bar { height: 4px; border-radius: 2px; background: rgba(255,255,255,.1); overflow:hidden; }
.strip-bar div { height:100%; background: linear-gradient(90deg, var(--d-accent), var(--d-accent-2)); transition: width .6s; }
.strip-text { display:flex; justify-content:space-between; margin-top: 7px; font-size: 13px; gap: 10px; }
.strip-text span:last-child { color: var(--d-mute); font-variant-numeric: tabular-nums; }
@container (max-width: 640px) {
  .capture-strip { left: 12px; right: 12px; bottom: 12px; }
  .joystick { width: 104px; height: 104px; left: 14px; bottom: 14px; transition: bottom .3s; }
  .stage.capturing .joystick { bottom: 82px; }
  .joystick .knob { width: 42px; height: 42px; margin: -21px 0 0 -21px; }
  .shutter { width: 70px; height: 70px; } .shutter .core { width: 50px; height: 50px; }
  .rail { right: 12px; } .rail-summary { display:none; }
  .pip { min-width: 92px; }
  .stage { aspect-ratio: 4 / 3.4; }
}

/* dock */
.dock { grid-area: dock; display:flex; flex-direction:column; background: var(--d-panel); border-top: 1px solid var(--d-line); }
.tabs { display:grid; grid-template-columns: repeat(4,1fr); padding: 8px; gap: 4px; border-bottom: 1px solid var(--d-line); }
.tabs button { display:flex; flex-direction:column; align-items:center; gap: 3px; padding: 8px 4px; border-radius: 12px; font-size: 12px; font-weight: 600; color: var(--d-mute); }
.tabs button ha-icon { --mdc-icon-size: 20px; }
.tabs button:hover { color: var(--d-text); }
.tabs button.on { color: var(--d-text); background: var(--d-raise); }
.tabs button.on ha-icon { color: var(--d-accent); }
.panel { padding: 14px; overflow-y: auto; flex: 1; max-height: 560px; scrollbar-width: thin; scrollbar-color: var(--d-scroll) transparent; }

.group { margin-bottom: 16px; }
.group > label { display:flex; justify-content:space-between; align-items:baseline; font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--d-mute); margin-bottom: 8px; }
.group > label small { text-transform:none; letter-spacing:0; font-weight: 500; color: var(--d-text); font-size: 12px; }
.seg { display:flex; padding: 3px; gap: 3px; border-radius: 12px; background: var(--d-bg); border: 1px solid var(--d-line); }
.seg button { flex:1; padding: 9px 6px; border-radius: 9px; font-size: 14px; font-weight: 600; color: var(--d-mute); transition: .15s; }
.seg button.on { background: var(--d-seg-on); color: var(--d-text); box-shadow: var(--d-seg-shadow); }
.slider { width: 100%; accent-color: var(--d-accent); height: 24px; }
.ticks { display:flex; justify-content:space-between; font-size: 11px; color: var(--d-mute); padding: 0 2px; }
.frames { display:flex; gap: 6px; }
.step { width: 44px; border-radius: 12px; background: var(--d-raise); font-size: 20px; }
.num { flex:1; min-width: 0; text-align:center; padding: 10px; border-radius: 12px; border: 1px solid var(--d-line); background: var(--d-bg); color: var(--d-text); font: inherit; font-size: 18px; font-weight: 650; font-variant-numeric: tabular-nums; }
.num.small { flex: 0 0 72px; font-size: 15px; padding: 8px; }
.chips { display:flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.chip { padding: 6px 12px; border-radius: 99px; font-size: 13px; font-weight: 600; background: var(--d-bg); border: 1px solid var(--d-line); color: var(--d-mute); }
.chip.on { color: var(--d-text); border-color: rgba(255,107,53,.6); background: rgba(255,107,53,.12); }
.total { display:flex; justify-content:space-between; align-items:center; padding: 12px 14px; border-radius: 14px; background: var(--d-bg); border: 1px solid var(--d-line); margin-bottom: 10px; }
.total span { color: var(--d-mute); font-size: 13px; } .total b { font-size: 18px; }
.darks-note { display:flex; align-items:center; gap: 6px; font-size: 13px; margin-bottom: 12px; color: var(--d-mute); }
.darks-note.ok ha-icon { color: var(--d-ok); } .darks-note.warn ha-icon { color: var(--d-warn); }

.btn { display:inline-flex; align-items:center; justify-content:center; gap: 6px; padding: 9px 14px; border-radius: 12px; background: var(--d-raise); font-weight: 600; font-size: 14px; border: 1px solid var(--d-line); text-decoration:none; color: var(--d-text); }
.btn:hover:not(:disabled) { border-color: rgba(255,255,255,.2); }
.btn.primary { background: linear-gradient(145deg, var(--d-accent-2), var(--d-accent)); color: var(--d-on-accent); border: 0; }
.btn.danger { background: rgba(255,77,94,.14); color: var(--d-danger-text); border-color: rgba(255,77,94,.3); }
.btn.big { width:100%; padding: 14px; font-size: 16px; border-radius: 14px; }
.btn.big ha-icon { --mdc-icon-size: 22px; }

/* goto */
.search { display:flex; align-items:center; gap: 8px; padding: 0 12px; border-radius: 12px; background: var(--d-bg); border: 1px solid var(--d-line); color: var(--d-mute); }
.search input { flex:1; padding: 11px 0; background: none; border: 0; outline: 0; color: var(--d-text); font: inherit; font-size: 15px; }
.filters { display:flex; align-items:center; justify-content:space-between; gap: 8px; flex-wrap: wrap; margin: 4px 0 10px; }
.toggle { display:inline-flex; align-items:center; gap: 8px; font-size: 13px; color: var(--d-mute); cursor:pointer; margin-top: 8px; }
.toggle input { display:none; }
.toggle span { width: 34px; height: 20px; border-radius: 99px; background: var(--d-raise); position: relative; transition: .2s; border: 1px solid var(--d-line); }
.toggle span::after { content:""; position:absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius:50%; background: var(--d-mute); transition: .2s; }
.toggle input:checked + span { background: rgba(255,107,53,.35); }
.toggle input:checked + span::after { left: 16px; background: var(--d-accent); }
.quick { display:grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; }
.targets { display:flex; flex-direction:column; gap: 6px; }
.target { display:grid; grid-template-columns: 36px 1fr auto 40px; align-items:center; gap: 10px; padding: 8px 8px 8px 10px; border-radius: 14px; background: var(--d-bg); border: 1px solid transparent; }
.target:hover { border-color: var(--d-line); }
ha-card.light .target, ha-card.light .action, ha-card.light .kv div, ha-card.light .total, ha-card.light .custom { box-shadow: var(--d-shadow); border-color: var(--d-line); }
ha-card.light .t-galaxy { color: #3d63e0; } ha-card.light .t-nebula { color: #d63a73; }
ha-card.light .t-planetary { color: #0e9a8a; } ha-card.light .t-cluster { color: #b98300; }
.target.current { border-color: rgba(61,220,151,.4); background: rgba(61,220,151,.05); }
.target.below { opacity: .45; }
.t-icon { width: 36px; height: 36px; border-radius: 10px; display:grid; place-items:center; background: var(--d-raise); }
.t-galaxy { color: #9db4ff; } .t-nebula { color: #ff8fb1; } .t-planetary { color: #6fe3d4; } .t-cluster { color: #ffd479; }
.t-name { font-weight: 650; font-size: 15px; white-space: nowrap; overflow:hidden; text-overflow: ellipsis; }
.t-name span { font-weight: 500; color: var(--d-mute); font-size: 13px; }
.t-meta { font-size: 11.5px; color: var(--d-mute); margin-top: 2px; white-space: nowrap; overflow:hidden; text-overflow: ellipsis; }
.t-main { min-width: 0; }
.t-alt { text-align:right; font-variant-numeric: tabular-nums; min-width: 46px; }
.t-alt b { font-size: 15px; } .t-alt small { color: var(--d-mute); font-size: 11px; margin-left: 3px; }
.altbar { height: 3px; border-radius: 2px; background: var(--d-raise); margin-top: 4px; overflow:hidden; }
.altbar i { display:block; height: 100%; background: linear-gradient(90deg, var(--d-accent), var(--d-ok)); }
.goto-btn { width: 40px; height: 40px; padding:0; border-radius: 12px; }
.goto-btn:hover:not(:disabled) { background: var(--d-accent); color: var(--d-on-accent); border-color: transparent; }
.custom { margin-top: 14px; border-radius: 14px; background: var(--d-bg); border: 1px solid var(--d-line); }
.custom summary { display:flex; gap: 8px; align-items:center; padding: 12px; cursor:pointer; font-weight: 600; font-size: 14px; color: var(--d-mute); list-style: none; }
.custom-grid { display:grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 0 12px 12px; }
.custom-grid input { padding: 10px; border-radius: 10px; border: 1px solid var(--d-line); background: var(--d-panel); color: var(--d-text); font: inherit; min-width: 0; }
.custom-grid #c-name { grid-column: 1 / -1; }
.custom-grid .btn { grid-column: 1 / -1; }
.empty-list { display:flex; flex-direction:column; align-items:center; gap: 10px; padding: 34px 10px; color: var(--d-mute); text-align:center; font-size: 14px; }
.empty-list ha-icon { --mdc-icon-size: 32px; }

/* gallery */
.hero { position:relative; border-radius: 16px; overflow:hidden; cursor:pointer; margin-bottom: 14px; background:#000; aspect-ratio: 16/10; }
.hero img { width:100%; height:100%; object-fit: cover; display:block; transition: transform .5s; }
.hero:hover img { transform: scale(1.03); }
.hero-meta, .thumb-cap { color: #fff; }
.hero-meta { position:absolute; left:0; right:0; bottom:0; padding: 30px 14px 12px; background: linear-gradient(transparent, rgba(0,0,0,.85)); display:flex; flex-direction:column; }
.hero-meta .kicker { font-size: 10.5px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--d-accent-2); }
.hero-meta b { font-size: 20px; } .hero-meta span:last-child { font-size: 12px; color: rgba(255,255,255,.7); }
.section-head { display:flex; justify-content:space-between; align-items:center; margin: 6px 0 8px; font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--d-mute); }
.section-head small { text-transform:none; letter-spacing:0; font-weight: 500; }
.grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); gap: 8px; }
.thumb { position:relative; aspect-ratio: 1; border-radius: 12px; overflow:hidden; background: var(--d-bg); padding:0; border: 1px solid var(--d-line); }
.thumb img { width:100%; height:100%; object-fit: cover; display:block; transition: transform .3s; }
.thumb:hover img { transform: scale(1.06); }
.no-thumb { width:100%; height:100%; display:grid; place-items:center; color: var(--d-mute); }
.thumb-cap { position:absolute; left:0; right:0; bottom:0; padding: 18px 7px 6px; background: linear-gradient(transparent, rgba(0,0,0,.85)); text-align:left; display:flex; flex-direction:column; }
.thumb-cap b { font-size: 12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; } .thumb-cap small { font-size: 10.5px; color: rgba(255,255,255,.65); }

/* device */
.actions { display:grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; }
.action { display:flex; flex-direction:column; align-items:flex-start; gap: 3px; padding: 12px; border-radius: 14px; background: var(--d-bg); border: 1px solid var(--d-line); text-align:left; transition: .15s; }
.action:hover:not(:disabled) { border-color: rgba(255,107,53,.5); }
.action ha-icon { --mdc-icon-size: 22px; color: var(--d-accent); margin-bottom: 4px; }
.action b { font-size: 14px; } .action small { font-size: 11.5px; color: var(--d-mute); }
.action.busy { animation: pulse 1s infinite; }
.dpad { position:relative; width: 156px; height: 156px; margin: 0 auto 18px; display:grid; grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(3, 1fr); gap: 4px; }
.dpad button { border-radius: 14px; background: var(--d-raise); border: 1px solid var(--d-line); display:grid; place-items:center; }
.dpad button:active { background: var(--d-accent); color: var(--d-on-accent); }
.dpad ha-icon { --mdc-icon-size: 26px; }
.dpad .up { grid-area: 1 / 2; } .dpad .left { grid-area: 2 / 1; } .dpad .right { grid-area: 2 / 3; } .dpad .down { grid-area: 3 / 2; }
.dpad-mid { grid-area: 2 / 2; display:grid; place-items:center; color: var(--d-mute); }
.row { display:flex; gap: 8px; margin-top: 8px; align-items: stretch; }
.row .seg { flex: 1; }
.hint { display:block; margin-top: 8px; color: var(--d-mute); font-size: 12px; }
.kv { display:grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.kv div { display:flex; flex-direction:column; padding: 9px 11px; border-radius: 12px; background: var(--d-bg); }
.kv span { font-size: 11px; color: var(--d-mute); text-transform: uppercase; letter-spacing: .05em; }
.kv b { font-size: 14px; margin-top: 2px; font-variant-numeric: tabular-nums; }

/* overlays */
.lightbox { position:absolute; inset:0; background: rgba(0,0,0,.92); display:flex; align-items:center; justify-content:center; z-index: 10; opacity:0; pointer-events:none; transition: .2s; padding: 16px; }
.lightbox.show { opacity:1; pointer-events:auto; }
.lb-inner { display:flex; flex-direction:column; max-width: 100%; max-height: 100%; gap: 10px; }
.lb-inner img { max-width: 100%; max-height: calc(82vh - 80px); object-fit: contain; border-radius: 10px; min-height: 0; }
.lb-bar { display:flex; justify-content:space-between; align-items:center; gap: 12px; flex-wrap: wrap; }
.lb-title { display:flex; flex-direction:column; } .lb-title b { font-size: 18px; } .lb-title span { font-size: 12px; color: var(--d-mute); }
.lb-actions { display:flex; gap: 6px; }
.confirm { position:absolute; inset:0; background: rgba(0,0,0,.6); backdrop-filter: blur(4px); display:flex; align-items:center; justify-content:center; z-index: 20; opacity:0; pointer-events:none; transition: .15s; padding: 20px; }
.confirm.show { opacity:1; pointer-events:auto; }
.confirm-box { background: var(--d-panel); color: var(--d-text); border: 1px solid var(--d-line); border-radius: 18px; padding: 18px; max-width: 360px; box-shadow: 0 20px 60px rgba(0,0,0,.35); }
.confirm-text { font-size: 15px; line-height: 1.45; margin-bottom: 16px; }
.confirm-actions { display:flex; justify-content:flex-end; gap: 8px; }
.toast { position:absolute; left: 50%; bottom: 18px; transform: translate(-50%, 20px); padding: 10px 16px; border-radius: 12px; background: var(--d-toast); color: var(--d-text); border: 1px solid var(--d-line); font-size: 14px; opacity:0; pointer-events:none; transition: .25s; z-index: 30; max-width: calc(100% - 32px); box-shadow: 0 10px 30px rgba(0,0,0,.5); }
.toast.show { opacity:1; transform: translate(-50%, 0); }
.toast.error { border-color: rgba(255,77,94,.5); color: var(--d-danger-text); }
.spin { width: 16px; height: 16px; border-radius: 50%; border: 2px solid rgba(255,255,255,.2); border-top-color: var(--d-accent); animation: spin .8s linear infinite; display:inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse { 50% { opacity: .55; } }
`;

// Picks the scope in the card editor. With one DWARF 3 there is nothing to pick: the card finds it.
class Dwarf3CardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.schema = [
        { name: "device_id", selector: { device: { integration: DOMAIN } } },
        {
          name: "theme",
          selector: {
            select: {
              mode: "dropdown",
              options: [
                { value: "auto", label: "Follow Home Assistant" },
                { value: "dark", label: "Dark" },
                { value: "light", label: "Light" },
              ],
            },
          },
        },
      ];
      this._form.computeLabel = (field) =>
        field.name === "theme" ? "Theme" : "DWARF 3 (leave empty to use the first one)";
      this._form.addEventListener("value-changed", (ev) => {
        const config = { ...this._config, ...ev.detail.value };
        if (!config.device_id) delete config.device_id;
        if (!config.theme || config.theme === "auto") delete config.theme;
        this._config = config;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = this._config;
  }
}

if (!customElements.get("dwarf3-card")) {
  customElements.define("dwarf3-card", Dwarf3Card);
  customElements.define("dwarf3-card-editor", Dwarf3CardEditor);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "dwarf3-card")) window.customCards.push({
  type: "dwarf3-card",
  name: "DWARF 3",
  description: "Live view, joystick, capture, goto and gallery for a DWARF 3 smart telescope.",
  preview: false,
  documentationURL: "https://github.com/bscholer/home-assistant-dwarf3",
});
console.info(`%c DWARF3-CARD %c ${VERSION} `, "background:#ff6b35;color:#000;font-weight:700", "background:#222;color:#fff");
