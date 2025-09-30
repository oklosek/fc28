// frontend/farmcare.js - dashboard logic
const $ = (selector) => document.querySelector(selector);

const sensorCards = $("#sensorCards");
const configCards = $("#configCards");
const ventList = $("#ventList");
const groupList = $("#groupList");
const allRange = $("#allRange");
const allVal = $("#allVal");
const allActual = $("#allActual");
const openAllBtn = $("#openAllBtn");
const closeAllBtn = $("#closeAllBtn");
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
const updateSection = $("#updateSection");
const updateBadge = $("#updateBadge");
const updateInfo = $("#updateInfo");
const updateNotes = $("#updateNotes");
const updateMeta = $("#updateMeta");
const updateError = $("#updateError");
const runUpdateBtn = $("#runUpdateBtn");
const checkUpdateBtn = $("#checkUpdateBtn");

let mode = "auto";
let vents = [];
let groups = [];
let currentConfig = {};
let formDirty = false;
let messageTimer = null;
let adminToken = "";
let bulkActionInProgress = false;
let updateStatus = null;
let updateNotifiedVersion = null;

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

function normalizePercent(value, fallback = 0) {
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return fallback;
  }
  return Math.round(Math.min(100, Math.max(0, num)));
}

function averagePercent(items, getter) {
  if (!items || !items.length) {
    return 0;
  }
  let sum = 0;
  let count = 0;
  items.forEach((item) => {
    const value = getter(item);
    if (Number.isFinite(value)) {
      sum += value;
      count += 1;
    }
  });
  return count ? sum / count : 0;
}


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

function formatTimestamp(value) {
  if (!value) {
    return 'niedostępne';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString();
}

function renderUpdateBanner(status) {
  if (!updateSection) return;
  if (!status || status.enabled === false) {
    updateSection.classList.add('hidden');
    return;
  }
  updateSection.classList.remove('hidden');
  const { current_version, latest_version, available, last_checked, notes, error, channel } = status;
  if (updateInfo) {
    updateInfo.textContent = available
      ? `Dostępna nowa wersja ${latest_version}. Zainstalowana wersja: ${current_version}.`
      : `Zainstalowana wersja: ${current_version}. System jest aktualny.`;
  }
  if (updateNotes) {
    if (notes) {
      updateNotes.textContent = notes;
      updateNotes.classList.remove('hidden');
    } else {
      updateNotes.textContent = '';
      updateNotes.classList.add('hidden');
    }
  }
  if (updateMeta) {
    const channelText = channel ? `Kanał: ${channel}` : 'Kanał: stable';
    const checkedText = last_checked ? `Ostatnie sprawdzenie: ${formatTimestamp(last_checked)}` : 'Ostatnie sprawdzenie: brak danych';
    updateMeta.textContent = `${checkedText} · ${channelText}`;
  }
  if (updateError) {
    if (error) {
      updateError.textContent = `Błąd: ${error}`;
      updateError.classList.remove('hidden');
    } else {
      updateError.textContent = '';
      updateError.classList.add('hidden');
    }
  }
  if (updateBadge) {
    updateBadge.classList.toggle('hidden', !available);
  }
  if (runUpdateBtn) {
    runUpdateBtn.disabled = !available;
  }
  if (checkUpdateBtn) {
    checkUpdateBtn.disabled = false;
  }
  updateSection.classList.toggle('update-available', Boolean(available));
  if (available && latest_version && latest_version !== updateNotifiedVersion) {
    showMessage(`Nowa wersja ${latest_version} jest dostępna.`, 'info', 6000);
    updateNotifiedVersion = latest_version;
  }
}

async function fetchUpdateStatus() {
  if (!updateSection) {
    return;
  }
  try {
    const response = await fetch('/api/update/status');
    if (!response.ok) {
      if (response.status === 404 || response.status === 503) {
        updateSection.classList.add('hidden');
        return;
      }
      throw new Error(`update status error: ${response.status}`);
    }
    const data = await response.json();
    updateStatus = data;
    renderUpdateBanner(data);
  } catch (err) {
    console.error(err);
    if (updateError) {
      updateError.textContent = 'Nie udało się pobrać statusu aktualizacji';
      updateError.classList.remove('hidden');
    }
  }
}

async function requestUpdateCheck() {
  if (!checkUpdateBtn) return;
  if (!adminToken) {
    showMessage('Podaj token administratora, aby sprawdzić aktualizacje', 'warning');
    return;
  }
  checkUpdateBtn.disabled = true;
  try {
    const response = await fetch('/api/update/check', {
      method: 'POST',
      headers: adminHeaders(),
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      throw new Error(`update check error: ${response.status}`);
    }
    const data = await response.json();
    updateStatus = data.status;
    renderUpdateBanner(updateStatus);
    showMessage('Sprawdzono dostępność aktualizacji', 'info');
  } catch (err) {
    console.error(err);
    showMessage('Nie udało się sprawdzić aktualizacji', 'error');
  } finally {
    checkUpdateBtn.disabled = false;
    fetchUpdateStatus();
  }
}

async function requestRunUpdate() {
  if (!runUpdateBtn) return;
  if (!adminToken) {
    showMessage('Podaj token administratora, aby zainstalować aktualizację', 'warning');
    return;
  }
  runUpdateBtn.disabled = true;
  try {
    const response = await fetch('/api/update/run', {
      method: 'POST',
      headers: adminHeaders(),
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `update run error: ${response.status}`);
    }
    const data = await response.json();
    updateStatus = data.status;
    renderUpdateBanner(updateStatus);
    showMessage('Aktualizacja została zainstalowana', 'success', 5000);
  } catch (err) {
    console.error(err);
    showMessage('Instalacja aktualizacji nie powiodła się', 'error');
  } finally {
    runUpdateBtn.disabled = false;
    fetchUpdateStatus();
  }
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
    const desired = mode === "manual"
      ? (Number.isFinite(vent.user_target) ? vent.user_target : vent.position)
      : vent.position;
    const targetValue = normalizePercent(desired, normalizePercent(vent.position, 0));
    const actualValue = normalizePercent(vent.position, 0);
    row.innerHTML = `
      <span class="vent-name">#${vent.id} ${vent.name}${vent.boneio_device ? ` [${vent.boneio_device}]` : ''}</span>
      <input type="range" min="0" max="100" value="${targetValue}" ${disabled ? "disabled" : ""} data-vent="${vent.id}">
      <span class="target-value">cel: ${targetValue}%</span>
      <span class="actual-value">aktualnie: ${actualValue}%</span>
      <span class="${vent.available ? "ok" : "err"}">${vent.available ? "OK" : "AWARIA"}</span>
    `;
    const slider = row.querySelector("input[type=range]");
    if (slider) {
      slider.addEventListener("input", () => {
        const val = normalizePercent(slider.value);
        const targetLabel = row.querySelector(".target-value");
        if (targetLabel) {
          targetLabel.textContent = `cel: ${val}%`;
        }
      });
      slider.addEventListener("change", async () => {
        const pos = normalizePercent(slider.value);
        await sendVentPosition(vent.id, pos);
      });
    }
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
    const relevant = vents.filter((v) => group.vents.includes(v.id));
    const actualAvg = averagePercent(relevant, (v) => v.position);
    const targetAvgSource = mode === "manual"
      ? averagePercent(relevant, (v) => Number.isFinite(v.user_target) ? v.user_target : v.position)
      : actualAvg;
    const sliderValue = normalizePercent(targetAvgSource, normalizePercent(actualAvg, 0));
    const actualValue = normalizePercent(actualAvg, 0);
    wrapper.innerHTML = `
      <div class="group-info">
        <h3>${group.name}</h3>
        <p>Wietrzniki: ${group.vents.join(", ") || "-"}</p>
      </div>
      <div class="group-control">
        <input type="range" min="0" max="100" value="${sliderValue}" ${disabled ? "disabled" : ""} data-group="${group.id}">
        <span class="group-target">cel: ${sliderValue}%</span>
        <span class="group-actual">aktualnie: ${actualValue}%</span>
      </div>
    `;
    const slider = wrapper.querySelector("input[type=range]");
    if (slider) {
      slider.addEventListener("input", () => {
        const val = normalizePercent(slider.value);
        const label = wrapper.querySelector(".group-target");
        if (label) {
          label.textContent = `cel: ${val}%`;
        }
      });
      slider.addEventListener("change", async () => {
        const pos = normalizePercent(slider.value);
        await sendGroupPosition(group.id, pos);
      });
    }
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

    updateModeUI();

    renderSensors(data.sensors || {});
    renderConfigSummary(currentConfig);
    renderVentSliders();
    renderGroupSliders();

    const actualAvg = averagePercent(vents, (v) => v.position);
    const targetAvgSource = mode === "manual"
      ? averagePercent(vents, (v) => Number.isFinite(v.user_target) ? v.user_target : v.position)
      : actualAvg;
    const sliderValue = normalizePercent(targetAvgSource, normalizePercent(actualAvg, 0));
    const actualValue = normalizePercent(actualAvg, 0);
    if (allRange) {
      allRange.value = String(sliderValue);
    }
    if (allVal) {
      allVal.textContent = `cel: ${sliderValue}%`;
    }
    if (allActual) {
      allActual.textContent = `aktualnie: ${actualValue}%`;
    }

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
  if (tokenInput) {
    tokenInput.value = adminToken;
  }
  if (tokenStatus) {
    tokenStatus.textContent = adminToken ? "Token saved" : "Token optional";
  }
}

function saveToken() {
  adminToken = tokenInput.value.trim();
  localStorage.setItem("farmcare_admin_token", adminToken);
  if (tokenStatus) {
    tokenStatus.textContent = adminToken ? "Token saved" : "Token optional";
  }
  showMessage("Admin token preference saved", "info");
}

function adminHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (adminToken) {
    headers["x-admin-token"] = adminToken;
  }
  return headers;
}

function updateModeUI() {
  if (modeIndicator) {
    modeIndicator.textContent = `Mode: ${mode.toUpperCase()}`;
  }
  if (modeBtn) {
    modeBtn.textContent = mode === "auto" ? "Switch to manual" : "Switch to auto";
  }
  if (allRange) {
    allRange.disabled = mode !== "manual";
  }
}

async function ensureManualMode() {
  if (mode === "manual") {
    return true;
  }
  try {
    const response = await fetch("/api/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "manual" }),
    });
    if (!response.ok) {
      throw new Error(`mode error: ${response.status}`);
    }
    const data = await response.json();
    mode = data.mode || "manual";
    updateModeUI();
    await fetchState();
    showMessage("Przełączono na tryb ręczny", "info", 2500);
    return true;
  } catch (err) {
    console.error(err);
    showMessage("Nie udało się przełączyć na tryb ręczny", "error");
    return false;
  }
}

async function sendAllPosition(pos, { notify = false } = {}) {
  try {
    const response = await fetch("/api/vents/all", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ position: pos }),
    });
    const data = await response.json().catch(() => ({ ok: false }));
    if (!response.ok || data?.ok === false) {
      throw new Error(`all command error: ${response.status}`);
    }
    if (notify) {
      const msg = pos > 0 ? "Polecenie otwarcia wysłane" : "Polecenie zamknięcia wysłane";
      showMessage(msg, "success", 2500);
    }
    setTimeout(fetchState, 1000);
    return true;
  } catch (err) {
    console.error(err);
    showMessage("Nie udało się wysłać polecenia do wszystkich wietrzników", "error");
    return false;
  }
}

async function sendGroupPosition(groupId, pos) {
  try {
    const response = await fetch(`/api/vents/group/${groupId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ position: pos }),
    });
    const data = await response.json().catch(() => ({ ok: false }));
    if (!response.ok || data?.ok === false) {
      throw new Error(`group command error: ${response.status}`);
    }
    setTimeout(fetchState, 1000);
    return true;
  } catch (err) {
    console.error(err);
    showMessage("Nie udało się wysłać polecenia do grupy", "error");
    return false;
  }
}

async function sendVentPosition(ventId, pos) {
  try {
    const response = await fetch(`/api/vents/${ventId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ position: pos }),
    });
    const data = await response.json().catch(() => ({ ok: false }));
    if (!response.ok || data?.ok === false) {
      throw new Error(`vent command error: ${response.status}`);
    }
    setTimeout(fetchState, 1000);
    return true;
  } catch (err) {
    console.error(err);
    showMessage("Nie udało się wysłać polecenia do wietrznika", "error");
    return false;
  }
}

async function handleBulkAction(target) {
  if (bulkActionInProgress) {
    return;
  }
  bulkActionInProgress = true;
  if (openAllBtn) openAllBtn.disabled = true;
  if (closeAllBtn) closeAllBtn.disabled = true;
  try {
    const ok = await ensureManualMode();
    if (!ok) {
      return;
    }
    if (allRange) {
      allRange.value = String(normalizePercent(target));
    }
    if (allVal) {
      allVal.textContent = `cel: ${normalizePercent(target)}%`;
    }
    await sendAllPosition(target, { notify: true });
  } finally {
    bulkActionInProgress = false;
    if (openAllBtn) openAllBtn.disabled = false;
    if (closeAllBtn) closeAllBtn.disabled = false;
  }
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
    updateModeUI();
    renderVentSliders();
    renderGroupSliders();
    showMessage("Controller mode updated", "success");
    await fetchState();
  } catch (err) {
    console.error(err);
    showMessage("Failed to change mode", "error");
  }
}


async function submitControlForm(event) {
  event.preventDefault();
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
    const val = normalizePercent(allRange.value);
    if (allVal) {
      allVal.textContent = `cel: ${val}%`;
    }
  });
  allRange.addEventListener("change", async () => {
    if (mode !== "manual") {
      showMessage("Switch to manual mode to control position", "warning");
      return;
    }
    const pos = normalizePercent(allRange.value);
    if (allVal) {
      allVal.textContent = `cel: ${pos}%`;
    }
    await sendAllPosition(pos);
  });
}

if (openAllBtn) {
  openAllBtn.addEventListener("click", () => handleBulkAction(100));
}

if (closeAllBtn) {
  closeAllBtn.addEventListener("click", () => handleBulkAction(0));
}

if (modeBtn) {
  modeBtn.addEventListener("click", toggleMode);
}

if (saveTokenBtn) {
  saveTokenBtn.addEventListener("click", saveToken);
}

if (checkUpdateBtn) {
  checkUpdateBtn.addEventListener("click", requestUpdateCheck);
}

if (runUpdateBtn) {
  runUpdateBtn.addEventListener("click", requestRunUpdate);
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
updateModeUI();
fetchUpdateStatus();
fetchState();
fetchHistory(parseInt(historyLimitInput.value, 10) || 100);
setInterval(fetchState, 3000);
setInterval(fetchUpdateStatus, 15 * 60 * 1000);
setInterval(() => {
  const limit = Math.min(
    Math.max(parseInt(historyLimitInput.value, 10) || 100, 10),
    500
  );
  fetchHistory(limit);
}, 30000);





