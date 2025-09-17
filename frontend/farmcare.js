// frontend/farmcare.js - dashboard logic
const $ = (selector) => document.querySelector(selector);

const sensorCards = $("#sensorCards");
const configCards = $("#configCards");
const ventList = $("#ventList");
const groupList = $("#groupList");
const allRange = $("#allRange");
const allVal = $("#allVal");
const modeBtn = $("#modeBtn");
const modeIndicator = $("#modeIndicator");
const tokenInput = $("#tokenInput");
const saveTokenBtn = $("#saveTokenBtn");
const tokenStatus = $("#tokenStatus");
const historyBody = $("#historyBody");
const historyLimitInput = $("#historyLimit");
const refreshHistoryBtn = $("#refreshHistoryBtn");
const controlForm = $("#controlForm");
const controlFieldsBox = $("#controlFields");
const controlStatus = $("#controlStatus");
const messageEl = $("#message");

let mode = "auto";
let vents = [];
let groups = [];
let currentConfig = {};
let formDirty = false;
let messageTimer = null;
let adminToken = "";

const SENSOR_META = {
  internal_temp: { label: "Internal temperature", unit: "C", digits: 1 },
  external_temp: { label: "External temperature", unit: "C", digits: 1 },
  internal_hum: { label: "Internal humidity", unit: "%", digits: 0 },
  external_hum: { label: "External humidity", unit: "%", digits: 0 },
  internal_co2: { label: "CO2", unit: "ppm", digits: 0 },
  external_pressure: { label: "Pressure", unit: "hPa", digits: 1 },
  wind_speed: { label: "Wind average", unit: "m/s", digits: 1 },
  wind_gust: { label: "Wind gust", unit: "m/s", digits: 1 },
  wind_direction: { label: "Wind direction", unit: "", digits: 0 },
  rain: { label: "Rainfall", unit: "mm", digits: 1 },
};

const CONTROL_FIELDS = [
  { key: "target_temp_c", label: "Target temperature (C)", step: "0.5", parser: parseFloat, decimals: 1, unit: "C" },
  { key: "humidity_thr", label: "Maximum humidity (%)", step: "1", parser: parseFloat, decimals: 0, unit: "%" },
  { key: "min_open_hum_percent", label: "Minimum opening at high humidity (%)", step: "1", parser: parseFloat, decimals: 0, unit: "%" },
  { key: "wind_risk_ms", label: "Risk wind speed (m/s)", step: "0.5", parser: parseFloat, decimals: 1, unit: "m/s" },
  { key: "wind_crit_ms", label: "Critical wind speed (m/s)", step: "0.5", parser: parseFloat, decimals: 1, unit: "m/s" },
  { key: "risk_open_limit_percent", label: "Max opening at risk wind (%)", step: "1", parser: parseFloat, decimals: 0, unit: "%" },
  { key: "rain_threshold", label: "Rain threshold (mm)", step: "0.1", parser: parseFloat, decimals: 1, unit: "mm" },
  { key: "step_percent", label: "Stage step size (%)", step: "1", parser: parseFloat, decimals: 0, unit: "%" },
  { key: "step_delay_s", label: "Delay between steps (s)", step: "1", parser: parseFloat, decimals: 0, unit: "s" },
  { key: "group_delay_s", label: "Delay between groups (s)", step: "1", parser: parseFloat, decimals: 0, unit: "s" },
  { key: "allow_humidity_override", label: "Allow crack for high humidity", type: "checkbox" },
  { key: "crit_hum_crack_percent", label: "Crack percent at high humidity (%)", step: "1", parser: parseFloat, decimals: 0, unit: "%" },
];

function showMessage(text, type = "info", timeout = 4000) {
  if (!messageEl) return;
  messageEl.textContent = text;
  messageEl.className = `notice ${type}`;
  messageEl.classList.remove("hidden");
  if (messageTimer) {
    clearTimeout(messageTimer);
  }
  if (timeout) {
    messageTimer = setTimeout(() => {
      messageEl.classList.add("hidden");
    }, timeout);
  }
}

function formatValue(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--";
  }
  return Number(value).toFixed(digits);
}

function formatWithUnit(value, unit = "", digits = 1) {
  const formatted = formatValue(value, digits);
  return formatted === "--" ? formatted : `${formatted} ${unit}`.trim();
}

function renderSensors(sensors) {
  if (!sensorCards) return;
  sensorCards.innerHTML = "";
  const seen = new Set();
  Object.entries(SENSOR_META).forEach(([key, meta]) => {
    const val = sensors?.[key];
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <h3>${meta.label}</h3>
      <p>${formatWithUnit(val, meta.unit, meta.digits)}</p>
    `;
    sensorCards.appendChild(card);
    seen.add(key);
  });
  Object.entries(sensors || {}).forEach(([key, value]) => {
    if (seen.has(key)) return;
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <h3>${key}</h3>
      <p>${formatValue(value)}</p>
    `;
    sensorCards.appendChild(card);
  });
}

function renderConfigSummary(config) {
  if (!configCards) return;
  configCards.innerHTML = "";
  const keysOfInterest = [
    "target_temp_c",
    "humidity_thr",
    "min_open_hum_percent",
    "wind_risk_ms",
    "wind_crit_ms",
    "risk_open_limit_percent",
    "rain_threshold",
    "allow_humidity_override",
  ];
  keysOfInterest.forEach((key) => {
    if (!(key in config)) return;
    const field = CONTROL_FIELDS.find((f) => f.key === key);
    const card = document.createElement("div");
    card.className = "card";
    let value = config[key];
    let display;
    if (field?.type === "checkbox") {
      display = value ? "YES" : "NO";
    } else {
      const digits = field?.decimals ?? 1;
      const unit = field?.unit ?? "";
      display = formatWithUnit(value, unit, digits);
    }
    card.innerHTML = `
      <h3>${field?.label || key}</h3>
      <p>${display}</p>
    `;
    configCards.appendChild(card);
  });
}

function renderVentSliders() {
  if (!ventList) return;
  ventList.innerHTML = "";
  vents.forEach((vent) => {
    const row = document.createElement("div");
    row.className = "vent-row";
    const disabled = mode !== "manual" || !vent.available;
    row.innerHTML = `
      <span>#${vent.id} ${vent.name}</span>
      <input type="range" min="0" max="100" value="${Math.round(
        vent.position || 0
      )}" ${disabled ? "disabled" : ""} data-vent="${vent.id}">
      <span>${Math.round(vent.position || 0)}%</span>
      <span class="${vent.available ? "ok" : "err"}">${
      vent.available ? "OK" : "AWARIA"
    }</span>
    `;
    const slider = row.querySelector("input[type=range]");
    slider?.addEventListener("input", () => {
      row.querySelector("span:nth-child(3)").textContent = `${slider.value}%`;
    });
    slider?.addEventListener("change", async () => {
      const pos = parseInt(slider.value, 10);
      await fetch(`/api/vents/${vent.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position: pos }),
      });
    });
    ventList.appendChild(row);
  });
}

function renderGroupSliders() {
  if (!groupList) return;
  groupList.innerHTML = "";
  groups.forEach((group) => {
    const wrapper = document.createElement("div");
    wrapper.className = "group-row";
    const disabled = mode !== "manual";
    const currentAvg = (() => {
      const relevant = vents.filter((v) => group.vents.includes(v.id));
      if (!relevant.length) return 0;
      return (
        relevant.reduce((acc, item) => acc + (item.position || 0), 0) /
        relevant.length
      );
    })();
    wrapper.innerHTML = `
      <div class="group-info">
        <h3>${group.name}</h3>
        <p>Wietrzniki: ${group.vents.join(", ") || "-"}</p>
      </div>
      <div class="group-control">
        <input type="range" min="0" max="100" value="${Math.round(
          currentAvg
        )}" ${disabled ? "disabled" : ""} data-group="${group.id}">
        <span>${Math.round(currentAvg)}%</span>
      </div>
    `;
    const slider = wrapper.querySelector("input[type=range]");
    slider?.addEventListener("input", () => {
      wrapper.querySelector("span").textContent = `${slider.value}%`;
    });
    slider?.addEventListener("change", async () => {
      const pos = parseInt(slider.value, 10);
      await fetch(`/api/vents/group/${group.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position: pos }),
      });
    });
    groupList.appendChild(wrapper);
  });
}

function buildControlForm(config) {
  if (!controlFieldsBox) return;
  controlFieldsBox.innerHTML = "";
  CONTROL_FIELDS.forEach((field) => {
    const row = document.createElement("div");
    row.className = "form-row";
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.dataset.key = field.key;
    input.id = `ctrl_${field.key}`;
    if (field.type === "checkbox") {
      input.type = "checkbox";
      input.checked = Boolean(config[field.key]);
      label.textContent = field.label;
      label.setAttribute("for", input.id);
      row.appendChild(label);
      row.appendChild(input);
    } else {
      input.type = field.type || "number";
      input.step = field.step || "0.1";
      const value = config[field.key];
      input.value = value !== undefined && value !== null ? value : "";
      label.setAttribute("for", input.id);
      label.textContent = field.label;
      row.appendChild(label);
      row.appendChild(input);
    }
    controlFieldsBox.appendChild(row);
  });
}

function refreshControlInputs(config) {
  CONTROL_FIELDS.forEach((field) => {
    const input = controlFieldsBox.querySelector(
      `[data-key="${field.key}"]`
    );
    if (!input) return;
    if (field.type === "checkbox") {
      input.checked = Boolean(config[field.key]);
    } else {
      const value = config[field.key];
      input.value = value !== undefined && value !== null ? value : "";
    }
  });
}

async function fetchState() {
  try {
    const response = await fetch("/api/state");
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    const data = await response.json();
    mode = data.mode;
    vents = data.vents || [];
    groups = data.groups || [];
    currentConfig = data.config || {};

    modeIndicator.textContent = `Mode: ${mode.toUpperCase()}`;
    modeBtn.textContent = mode === "auto" ? "Switch to manual" : "Switch to auto";

    renderSensors(data.sensors || {});
    renderConfigSummary(currentConfig);
    renderVentSliders();
    renderGroupSliders();

    const avg = vents.length
      ? vents.reduce((sum, v) => sum + (v.position || 0), 0) / vents.length
      : 0;
    allRange.value = Math.round(avg);
    allVal.textContent = `${Math.round(avg)}%`;

    if (!controlFieldsBox.children.length) {
      buildControlForm(currentConfig);
    } else if (!formDirty) {
      refreshControlInputs(currentConfig);
    }
  } catch (err) {
    console.error(err);
    showMessage("Failed to fetch controller state", "error");
  }
}

async function fetchHistory(limit) {
  try {
    const response = await fetch(`/api/history?limit=${limit}`);
    if (!response.ok) {
      throw new Error(`History API error: ${response.status}`);
    }
    const data = await response.json();
    historyBody.innerHTML = "";
    data.forEach((entry) => {
      const row = document.createElement("tr");
      const ts = new Date(entry.ts);
      row.innerHTML = `
        <td>${ts.toLocaleString()}</td>
        <td>${entry.name}</td>
        <td>${formatValue(entry.value, 3)}</td>
      `;
      historyBody.appendChild(row);
    });
  } catch (err) {
    console.error(err);
    showMessage("Failed to fetch sensor history", "error");
  }
}

function loadToken() {
  adminToken = localStorage.getItem("farmcare_admin_token") || "";
  tokenInput.value = adminToken;
  tokenStatus.textContent = adminToken ? "Token saved" : "Token missing";
}

function saveToken() {
  adminToken = tokenInput.value.trim();
  localStorage.setItem("farmcare_admin_token", adminToken);
  tokenStatus.textContent = adminToken ? "Token saved" : "Token missing";
  showMessage("Admin token saved", "info");
}

function adminHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (adminToken) {
    headers["x-admin-token"] = adminToken;
  }
  return headers;
}

async function toggleMode() {
  const next = mode === "auto" ? "manual" : "auto";
  try {
    const response = await fetch("/api/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: next }),
    });
    if (!response.ok) {
      throw new Error(`Mode change error: ${response.status}`);
    }
    const data = await response.json();
    mode = data.mode;
    modeIndicator.textContent = `Mode: ${mode.toUpperCase()}`;
    modeBtn.textContent = mode === "auto" ? "Switch to manual" : "Switch to auto";
    renderVentSliders();
    renderGroupSliders();
    showMessage("Controller mode updated", "success");
  } catch (err) {
    console.error(err);
    showMessage("Failed to change mode", "error");
  }
}

async function submitControlForm(event) {
  event.preventDefault();
  if (!adminToken) {
    showMessage("Provide admin token to save settings", "warning");
    return;
  }
  const payload = {};
  let hasError = false;
  CONTROL_FIELDS.forEach((field) => {
    const input = controlFieldsBox.querySelector(`[data-key="${field.key}"]`);
    if (!input) return;
    if (field.type === "checkbox") {
      payload[field.key] = input.checked;
    } else {
      const raw = input.value;
      if (raw === "") return;
      const parser = field.parser || parseFloat;
      const value = parser(raw);
      if (Number.isNaN(value)) {
        hasError = true;
        input.classList.add("error");
      } else {
        input.classList.remove("error");
        payload[field.key] = value;
      }
    }
  });
  if (hasError) {
    controlStatus.textContent = "Check the entered values";
    controlStatus.className = "error";
    return;
  }
  try {
    const response = await fetch("/api/control", {
      method: "POST",
      headers: adminHeaders(),
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(`Save error: ${response.status}`);
    }
    const data = await response.json();
    currentConfig = data.control || currentConfig;
    controlStatus.textContent = "Saved";
    controlStatus.className = "success";
    formDirty = false;
    showMessage("Controller settings updated", "success");
  } catch (err) {
    console.error(err);
    controlStatus.textContent = "Save failed";
    controlStatus.className = "error";
    showMessage("Failed to save controller settings", "error");
  }
}

if (allRange) {
  allRange.addEventListener("input", () => {
    allVal.textContent = `${allRange.value}%`;
  });
  allRange.addEventListener("change", async () => {
    if (mode !== "manual") {
      showMessage("Switch to manual mode to control position", "warning");
      return;
    }
    const pos = parseInt(allRange.value, 10);
    allVal.textContent = `${pos}%`;
    await fetch("/api/vents/all", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ position: pos }),
    });
  });
}

if (modeBtn) {
  modeBtn.addEventListener("click", toggleMode);
}

if (saveTokenBtn) {
  saveTokenBtn.addEventListener("click", saveToken);
}

if (controlForm) {
  controlForm.addEventListener("submit", submitControlForm);
  controlForm.addEventListener("input", () => {
    formDirty = true;
    controlStatus.textContent = "";
    controlStatus.className = "info";
  });
}

if (refreshHistoryBtn) {
  refreshHistoryBtn.addEventListener("click", () => {
    const limit = Math.min(
      Math.max(parseInt(historyLimitInput.value, 10) || 100, 10),
      500
    );
    fetchHistory(limit);
  });
}

loadToken();
buildControlForm({});
fetchState();
fetchHistory(parseInt(historyLimitInput.value, 10) || 100);
setInterval(fetchState, 3000);
setInterval(() => {
  const limit = Math.min(
    Math.max(parseInt(historyLimitInput.value, 10) || 100, 10),
    500
  );
  fetchHistory(limit);
}, 30000);





