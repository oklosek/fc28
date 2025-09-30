
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const elements = {
  token: document.querySelector('#tokenInput'),
  loadBtn: document.querySelector('#loadConfig'),
  status: document.querySelector('#status'),
  panelTabs: Array.from(document.querySelectorAll('.panel-tab')),
  panels: Array.from(document.querySelectorAll('.panel')),
  requiresConfig: Array.from(document.querySelectorAll('.requires-config')),
  loadingOverlay: document.querySelector('#loadingOverlay'),
  loadingMessage: document.querySelector('#loadingMessage'),
  refreshSensors: document.querySelector('#refreshSensors'),
  sensorMetrics: document.querySelector('#sensorMetrics'),
  rs485Status: document.querySelector('#rs485Status'),
  networkStatus: document.querySelector('#networkStatus'),
  controlDashboard: document.querySelector('#controlDashboard'),
  controlAdvanced: document.querySelector('#controlAdvanced'),
  saveControl: document.querySelector('#saveControl'),
  heatingEnabled: document.querySelector('#heatingEnabled'),
  heatingTopic: document.querySelector('#heatingTopic'),
  heatingPayloadOn: document.querySelector('#heatingPayloadOn'),
  heatingPayloadOff: document.querySelector('#heatingPayloadOff'),
  heatingDayTarget: document.querySelector('#heatingDayTarget'),
  heatingNightTarget: document.querySelector('#heatingNightTarget'),
  heatingHysteresis: document.querySelector('#heatingHysteresis'),
  heatingDayStart: document.querySelector('#heatingDayStart'),
  heatingNightStart: document.querySelector('#heatingNightStart'),
  saveHeating: document.querySelector('#saveHeating'),
  boneioList: document.querySelector('#boneioList'),
  addBoneio: document.querySelector('#addBoneio'),
  saveBoneio: document.querySelector('#saveBoneio'),
  ventList: document.querySelector('#ventList'),
  addVent: document.querySelector('#addVent'),
  saveVents: document.querySelector('#saveVents'),
  groupList: document.querySelector('#groupList'),
  addGroup: document.querySelector('#addGroup'),
  saveGroups: document.querySelector('#saveGroups'),
  planCloseStrategy: document.querySelector('#planCloseStrategy'),
  stageList: document.querySelector('#stageList'),
  addStage: document.querySelector('#addStage'),
  savePlan: document.querySelector('#savePlan'),
  externalEnabled: document.querySelector('#externalEnabled'),
  externalProtocol: document.querySelector('#externalProtocol'),
  externalHost: document.querySelector('#externalHost'),
  externalPort: document.querySelector('#externalPort'),
  externalPath: document.querySelector('#externalPath'),
  externalToken: document.querySelector('#externalToken'),
  saveExternal: document.querySelector('#saveExternal'),
  calibrateAll: document.querySelector('#calibrateAll'),
  rawConfig: document.querySelector('#rawConfig'),
  refreshRaw: document.querySelector('#refreshRaw'),
  testModeToggle: document.querySelector('#testModeToggle'),
  refreshTestStatus: document.querySelector('#refreshTestStatus'),
  testBoneio: document.querySelector('#testBoneio'),
  testVents: document.querySelector('#testVents'),
  testOverrides: document.querySelector('#testOverrides'),
  manualScope: document.querySelector('#manualScope'),
  manualTargetLabel: document.querySelector('#manualTargetLabel'),
  manualTarget: document.querySelector('#manualTarget'),
  manualValue: document.querySelector('#manualValue'),
  manualSend: document.querySelector('#manualSend'),
  simulationList: document.querySelector('#simulationList'),
  applySim: document.querySelector('#applySim'),
  resetSim: document.querySelector('#resetSim'),
  addSimRow: document.querySelector('#addSimRow'),
  logsOutput: document.querySelector('#logsOutput'),
  logButtons: Array.from(document.querySelectorAll('.log-btn')),
  pingButtons: Array.from(document.querySelectorAll('.ping-btn')),
  pingResults: document.querySelector('#pingResults'),
};

const state = {
  snapshot: null,
  controlMeta: null,
  sensors: null,
  testStatus: null,
  boneio: [],
  groups: [],
  vents: [],
  plan: null,
  spinnerDepth: 0,
};
function showLoading(message = 'Przetwarzanie...') {
  state.spinnerDepth += 1;
  elements.loadingMessage.textContent = message;
  elements.loadingOverlay.classList.remove('hidden');
}

function hideLoading(force = false) {
  if (force) {
    state.spinnerDepth = 0;
  } else if (state.spinnerDepth > 0) {
    state.spinnerDepth -= 1;
  }
  if (state.spinnerDepth <= 0) {
    elements.loadingOverlay.classList.add('hidden');
  }
}

function setStatus(message, type = 'info') {
  elements.status.textContent = message;
  elements.status.className = type;
  if (message) {
    setTimeout(() => {
      if (elements.status.textContent === message) {
        elements.status.textContent = '';
        elements.status.className = '';
      }
    }, 5000);
  }
}

function requireToken() {
  const token = elements.token.value.trim();
  if (!token) {
    setStatus('Wpisz token administracyjny', 'err');
    throw new Error('missing-token');
  }
  return token;
}

async function apiRequest(path, { method = 'GET', body = undefined, spinner, skipSpinner = false } = {}) {
  const token = requireToken();
  const headers = { 'x-admin-token': token };
  const options = { method, headers };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  if (!skipSpinner) {
    showLoading(spinner || 'Ladowanie...');
  }
  try {
    const response = await fetch(path, options);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || response.statusText || 'Request failed');
    }
    if (response.status === 204) {
      return null;
    }
    const contentType = response.headers.get('Content-Type') || '';
    if (contentType.includes('application/json')) {
      return await response.json();
    }
    return await response.text();
  } finally {
    if (!skipSpinner) {
      hideLoading();
    }
  }
}

function togglePanels(targetId) {
  elements.panelTabs.forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.panel === targetId);
  });
  elements.panels.forEach((panel) => {
    panel.classList.toggle('active', panel.id === targetId);
  });
}

function setConfigVisibility(visible) {
  elements.requiresConfig.forEach((el) => {
    el.classList.toggle('hidden', !visible);
  });
}

function clearContainer(node) {
  if (node) {
    node.innerHTML = '';
  }
}
function renderSensors() {
  clearContainer(elements.sensorMetrics);
  clearContainer(elements.rs485Status);
  clearContainer(elements.networkStatus);
  const sensors = state.sensors || {};
  const metrics = sensors.metrics || {};
  const sortedKeys = Object.keys(metrics).sort();
  sortedKeys.forEach((key) => {
    const metric = metrics[key] || {};
    const item = document.createElement('div');
    item.className = 'metric';
    const value = metric.value !== null && metric.value !== undefined ? metric.value : '–';
    const unit = metric.unit ? ` ${metric.unit}` : '';
    item.innerHTML = `<span class="metric-name">${key}</span><span class="metric-value">${value}${unit}</span><span class="metric-source">${metric.source || ''}</span>`;
    elements.sensorMetrics.appendChild(item);
  });
  const loops = sensors.loops || {};
  if (Object.keys(loops).length) {
    const loopsBlock = document.createElement('div');
    loopsBlock.className = 'metric loops';
    loopsBlock.innerHTML = `<span class="metric-name">Petle</span><span class="metric-value">kontroler: ${loops.controller ?? '–'} s / scheduler: ${loops.scheduler ?? '–'} s</span>`;
    elements.sensorMetrics.appendChild(loopsBlock);
  }
  const buses = sensors.rs485 || [];
  if (buses.length === 0) {
    const info = document.createElement('p');
    info.textContent = 'Brak danych RS485';
    elements.rs485Status.appendChild(info);
  } else {
    buses.forEach((bus) => {
      const row = document.createElement('div');
      row.className = 'list-item';
      row.innerHTML = `
        <div><strong>${bus.name || bus.port || 'Magistrala'}</strong></div>
        <div class="muted">${bus.port || ''}</div>
        <div>Status: ${bus.online === false ? 'offline' : 'online'}</div>
      `;
      elements.rs485Status.appendChild(row);
    });
  }
  const networks = sensors.network || [];
  if (networks.length === 0) {
    const info = document.createElement('p');
    info.textContent = 'Brak danych sieciowych';
    elements.networkStatus.appendChild(info);
  } else {
    networks.forEach((iface) => {
      const row = document.createElement('div');
      row.className = 'list-item';
      const status = iface.is_up === true ? 'online' : iface.is_up === false ? 'offline' : 'brak danych';
      const addresses = (iface.addresses || []).join(', ');
      row.innerHTML = `
        <div><strong>${iface.role || 'interfejs'}</strong> (${iface.name || 'brak nazwy'})</div>
        <div>Status: ${status}</div>
        <div>Adresy: ${addresses || '–'}</div>
      `;
      elements.networkStatus.appendChild(row);
    });
  }
}

function createControlInput(field) {
  const wrapper = document.createElement('div');
  wrapper.className = 'form-row';
  wrapper.dataset.key = field.key;
  wrapper.dataset.type = field.type;
  const label = document.createElement('label');
  label.textContent = field.key;
  let input;
  if (field.type === 'bool') {
    input = document.createElement('input');
    input.type = 'checkbox';
    input.checked = Boolean(field.value);
  } else {
    input = document.createElement('input');
    input.type = field.type === 'str' ? 'text' : 'number';
    if (field.type === 'int') {
      input.step = '1';
    } else if (field.type === 'float') {
      input.step = 'any';
    }
    if (field.value !== undefined && field.value !== null) {
      input.value = field.value;
    }
    if (field.min !== undefined) {
      input.min = field.min;
    }
    if (field.max !== undefined) {
      input.max = field.max;
    }
  }
  label.appendChild(input);
  wrapper.appendChild(label);
  return wrapper;
}

function renderControl() {
  clearContainer(elements.controlDashboard);
  clearContainer(elements.controlAdvanced);
  if (!state.controlMeta) {
    return;
  }
  const dashFields = state.controlMeta.dashboard || [];
  dashFields.forEach((field) => {
    elements.controlDashboard.appendChild(createControlInput(field));
  });
  const advFields = state.controlMeta.advanced || [];
  advFields.forEach((field) => {
    elements.controlAdvanced.appendChild(createControlInput(field));
  });
}

function renderHeating() {
  const heating = state.snapshot?.heating || {};
  elements.heatingEnabled.checked = Boolean(heating.enabled);
  elements.heatingTopic.value = heating.topic || '';
  elements.heatingPayloadOn.value = heating.payload_on || '';
  elements.heatingPayloadOff.value = heating.payload_off || '';
  elements.heatingDayTarget.value = heating.day_target_c ?? '';
  elements.heatingNightTarget.value = heating.night_target_c ?? '';
  elements.heatingHysteresis.value = heating.hysteresis_c ?? '';
  elements.heatingDayStart.value = heating.day_start || '';
  elements.heatingNightStart.value = heating.night_start || '';
}

function createBoneioRow(device = {}, idx = 0) {
  const row = document.createElement('details');
  row.className = 'boneio-row list-item';
  row.dataset.index = idx;
  row.open = false;
  const summaryLabel = `${device.id || 'BoneIO'}${device.base_topic ? ` - ${device.base_topic}` : ''}`;
  row.innerHTML = `
    <summary>
      <span>${summaryLabel}</span>
      <button type="button" class="inline danger" data-action="remove-boneio">Usun</button>
    </summary>
    <div class="form-grid">
      <div class="form-row"><label>ID<input type="text" class="boneio-id" value="${device.id || ''}" /></label></div>
      <div class="form-row"><label>Topic bazowy<input type="text" class="boneio-topic" value="${device.base_topic || ''}" /></label></div>
      <div class="form-row"><label>Opis<input type="text" class="boneio-description" value="${device.description || ''}" /></label></div>
      <div class="form-row"><label>Topic dostepnosci<input type="text" class="boneio-availability" value="${device.availability_topic || ''}" /></label></div>
    </div>
  `;
  return row;
}

function renderBoneio() {
  clearContainer(elements.boneioList);
  (state.boneio || []).forEach((device, idx) => {
    elements.boneioList.appendChild(createBoneioRow(device, idx));
  });
}

function createVentRow(vent) {
  const block = document.createElement('details');
  block.className = 'vent-row list-item';
  block.open = false;
  block.dataset.id = vent.id ?? '';
  block.innerHTML = `
    <summary>
      <span>ID ${vent.id ?? 'nowy'} - ${vent.name || 'bez nazwy'}${vent.boneio_device ? ` [${vent.boneio_device}]` : ''}</span>
      <button type="button" class="inline danger" data-action="remove-vent">Usun</button>
    </summary>
  `;
  const container = document.createElement('div');
  container.className = 'form-grid';
  const devices = Array.isArray(state.boneio) ? state.boneio : [];
  let options = '<option value="">(wybierz)</option>';
  let hasCurrentDevice = false;
  devices.forEach((device) => {
    const value = device.id || '';
    if (!value) {
      return;
    }
    const label = device.base_topic ? `${device.id} (${device.base_topic})` : device.id;
    const selected = vent.boneio_device === value;
    if (selected) {
      hasCurrentDevice = true;
    }
    options += `<option value="${value}"${selected ? ' selected' : ''}>${label}</option>`;
  });
  if (vent.boneio_device && !hasCurrentDevice) {
    const fallback = vent.boneio_device;
    options = `<option value="${fallback}" selected>${fallback}</option>` + options;
  }
  const deviceField = devices.length
    ? `<select class="vent-device">${options}</select>`
    : `<input type="text" class="vent-device" value="${vent.boneio_device || ''}" />`;
  container.innerHTML = `
    <div class="form-row"><label>ID<input type="number" class="vent-id" value="${vent.id ?? ''}" /></label></div>
    <div class="form-row"><label>Nazwa<input type="text" class="vent-name" value="${vent.name || ''}" /></label></div>
    <div class="form-row"><label>Urzadzenie BoneIO${deviceField}</label></div>
    <div class="form-row"><label>Czas ruchu [s]<input type="number" step="any" class="vent-travel" value="${vent.travel_time_s ?? ''}" /></label></div>
    <div class="form-row"><label>Topic UP<input type="text" class="vent-up" value="${vent.topics?.up || ''}" /></label></div>
    <div class="form-row"><label>Topic DOWN<input type="text" class="vent-down" value="${vent.topics?.down || ''}" /></label></div>
    <div class="form-row"><label>Topic bledu<input type="text" class="vent-error" value="${vent.topics?.error_in || ''}" /></label></div>
    <div class="form-row"><label>Pauza odwrotu [s]<input type="number" step="any" class="vent-reverse" value="${vent.reverse_pause_s ?? ''}" /></label></div>
    <div class="form-row"><label>Minimalny ruch [s]<input type="number" step="any" class="vent-min-move" value="${vent.min_move_s ?? ''}" /></label></div>
    <div class="form-row"><label>Bufor kalibracji [s]<input type="number" step="any" class="vent-calibration" value="${vent.calibration_buffer_s ?? ''}" /></label></div>
    <div class="form-row"><label>Ignoruj delta [%]<input type="number" step="any" class="vent-ignore" value="${vent.ignore_delta_percent ?? ''}" /></label></div>
  `;
  block.appendChild(container);
  return block;
}


function renderVents() {
  clearContainer(elements.ventList);
  (state.vents || []).forEach((vent) => {
    elements.ventList.appendChild(createVentRow(vent));
  });
}

function createGroupRow(group, idx) {
  const row = document.createElement('details');
  row.className = 'group-row list-item';
  row.open = false;
  row.dataset.index = idx;
  const vents = (group.vents || []).join(', ');
  const windRanges = (group.wind_upwind_deg || []).map((rng) => rng.join('-')).join('; ');
  row.innerHTML = `
    <summary>
      <span>${group.id || 'grupa'} – ${group.name || ''}</span>
      <button type="button" class="inline danger" data-action="remove-group">Usun</button>
    </summary>
    <div class="form-grid">
      <div class="form-row"><label>ID<input type="text" class="group-id" value="${group.id || ''}" /></label></div>
      <div class="form-row"><label>Nazwa<input type="text" class="group-name" value="${group.name || ''}" /></label></div>
      <div class="form-row"><label>Wietrzniki (ID, po przecinku)<input type="text" class="group-vents" value="${vents}" /></label></div>
      <div class="form-row checkbox"><label><input type="checkbox" class="group-wind-lock" ${group.wind_lock_enabled === false ? '' : 'checked'} />Blokada wiatrowa</label></div>
      <div class="form-row"><label>Pozycja zamkniecia przy wietrze [%]<input type="number" min="0" max="100" step="any" class="group-wind-close" value="${group.wind_lock_close_percent ?? ''}" /></label></div>
      <div class="form-row"><label>Zakresy wiatru (np. 300-60; 180-270)<input type="text" class="group-wind-ranges" value="${windRanges}" /></label></div>
    </div>
  `;
  return row;
}

function renderGroups() {
  clearContainer(elements.groupList);
  (state.groups || []).forEach((group, idx) => {
    elements.groupList.appendChild(createGroupRow(group, idx));
  });
}
function createStageRow(stage, index) {
  const row = document.createElement('div');
  row.className = 'stage-row list-item';
  row.dataset.index = index;
  const groupOptions = state.groups.map((group) => `<option value="${group.id}">${group.id}</option>`).join('');
  const selectedGroups = new Set((stage.groups || []).map(String));
  row.innerHTML = `
    <header>
      <strong>${stage.id || 'etap'} – ${stage.name || ''}</strong>
      <div class="row-actions">
        <button type="button" class="inline" data-action="stage-up">Gora</button>
        <button type="button" class="inline" data-action="stage-down">Dol</button>
        <button type="button" class="inline danger" data-action="remove-stage">Usun</button>
      </div>
    </header>
    <div class="form-grid">
      <div class="form-row"><label>ID<input type="text" class="stage-id" value="${stage.id || ''}" /></label></div>
      <div class="form-row"><label>Nazwa<input type="text" class="stage-name" value="${stage.name || ''}" /></label></div>
      <div class="form-row"><label>Tryb
        <select class="stage-mode">
          <option value="serial" ${stage.mode === 'parallel' ? '' : 'selected'}>Szeregowy</option>
          <option value="parallel" ${stage.mode === 'parallel' ? 'selected' : ''}>Rownolegly</option>
        </select>
      </label></div>
      <div class="form-row"><label>Krok [%]<input type="number" min="1" max="100" step="any" class="stage-step" value="${stage.step_percent ?? 100}" /></label></div>
      <div class="form-row"><label>Opoznienie [s]<input type="number" min="0" step="any" class="stage-delay" value="${stage.delay_s ?? 0}" /></label></div>
      <div class="form-row">
        <label>Grupy
          <select class="stage-groups" multiple>
            ${groupOptions.replace(/value="([^"]+)"/g, (match, value) => (selectedGroups.has(value) ? `${match} selected` : match))}
          </select>
        </label>
      </div>
    </div>
  `;
  return row;
}

function renderPlan() {
  clearContainer(elements.stageList);
  const stages = state.plan?.stages || [];
  stages.forEach((stage, index) => {
    elements.stageList.appendChild(createStageRow(stage, index));
  });
  elements.planCloseStrategy.value = state.plan?.close_strategy || 'fifo';
}

function renderExternal() {
  const external = state.snapshot?.external || {};
  elements.externalEnabled.checked = Boolean(external.enabled);
  elements.externalProtocol.value = external.protocol || 'https';
  elements.externalHost.value = external.host || '';
  elements.externalPort.value = external.port ?? '';
  elements.externalPath.value = external.path || '/';
  elements.externalToken.value = external.token || '';
}

function updateManualTargets() {
  const groupOptions = state.groups.map((group) => ({ value: group.id, label: `${group.id} – ${group.name || group.id}` }));
  const ventOptions = state.vents.map((vent) => ({ value: vent.id, label: `${vent.id} – ${vent.name || `Vent ${vent.id}`}` }));
  elements.manualTarget.dataset.groups = JSON.stringify(groupOptions);
  elements.manualTarget.dataset.vents = JSON.stringify(ventOptions);
}

function populateManualTarget(scope) {
  const select = elements.manualTarget;
  let options = [];
  if (scope === 'group') {
    options = JSON.parse(select.dataset.groups || '[]');
  } else if (scope === 'vent') {
    options = JSON.parse(select.dataset.vents || '[]');
  }
  select.innerHTML = options.map((item) => `<option value="${item.value}">${item.label}</option>`).join('');
  elements.manualTargetLabel.classList.toggle('hidden', options.length === 0);
}

function renderSimulationList() {
  clearContainer(elements.simulationList);
  const metrics = state.sensors?.metrics || {};
  const overrides = state.testStatus?.test_mode?.overrides || {};
  const keys = Object.keys(metrics).sort();
  keys.forEach((key) => {
    const metric = metrics[key] || {};
    const current = metric.value !== undefined && metric.value !== null ? ` (obecnie ${metric.value}${metric.unit ? ` ${metric.unit}` : ''})` : '';
    const row = document.createElement('div');
    row.className = 'form-row sim-row';
    row.dataset.key = key;
    row.innerHTML = `
      <label>${key}${current}
        <input type="number" step="any" value="${overrides[key] ?? ''}" />
      </label>
      <button type="button" class="inline" data-action="clear-sim">Wyczysć</button>
    `;
    elements.simulationList.appendChild(row);
  });
}

function renderTestStatus() {
  clearContainer(elements.testBoneio);
  clearContainer(elements.testVents);
  clearContainer(elements.testOverrides);
  const status = state.testStatus;
  if (!status) {
    const info = document.createElement('p');
    info.textContent = 'Brak danych diagnostycznych';
    elements.testBoneio.appendChild(info);
    return;
  }
  elements.testModeToggle.checked = Boolean(status.test_mode?.enabled);
  const devices = status.boneio || [];
  devices.forEach((device) => {
    const item = document.createElement('div');
    item.className = 'list-item';
    const ventList = (device.vents || []).map((vent) => `${vent.id}:${vent.name}${vent.available ? '' : ' (offline)'}`).join(', ');
    const subtitle = device.base_topic ? ` (${device.base_topic})` : '';
    item.innerHTML = `<div><strong>${device.device}</strong>${subtitle}</div><div>${ventList || 'brak wietrznikow'}</div>`;
    elements.testBoneio.appendChild(item);
  });
  const vents = status.vents || [];
  vents.forEach((vent) => {
    const item = document.createElement('div');
    item.className = 'list-item';
    item.innerHTML = `<div><strong>${vent.id}</strong> ${vent.name || ''}</div><div>Pozycja: ${vent.position ?? '–'}% (cel: ${vent.target ?? '–'}%)</div><div>${vent.available ? 'online' : 'offline'} ${vent.boneio_device ? `- ${vent.boneio_device}` : ''}</div>`;
    elements.testVents.appendChild(item);
  });
  const testMode = status.test_mode || {};
  const manualHistory = testMode.manual_history || [];
  if (manualHistory.length) {
    const manualCard = document.createElement('div');
    manualCard.className = 'list-item';
    manualCard.innerHTML = `<div><strong>Historia sterowania</strong></div><div>${manualHistory.slice(0, 5).map((entry) => {
      const time = new Date(entry.ts * 1000).toLocaleTimeString();
      const targets = (entry.targets || []).join(', ');
      return `${time}: ${entry.type || 'manual'} -> ${targets || '-'} (${entry.value ?? '–'}%)`;
    }).join('<br />')}</div>`;
    elements.testOverrides.appendChild(manualCard);
  }
  const overrideHistory = testMode.override_history || [];
  if (overrideHistory.length) {
    const overrideCard = document.createElement('div');
    overrideCard.className = 'list-item';
    overrideCard.innerHTML = `<div><strong>Historia symulacji</strong></div><div>${overrideHistory.slice(0, 5).map((entry) => {
      const time = new Date(entry.ts * 1000).toLocaleTimeString();
      const values = Object.entries(entry.values || {}).map(([k, v]) => `${k}=${v}`).join(', ');
      return `${time}: ${values || 'reset'}`;
    }).join('<br />')}</div>`;
    elements.testOverrides.appendChild(overrideCard);
  }
}

function renderRawConfig() {
  elements.rawConfig.textContent = JSON.stringify(state.snapshot, null, 2);
}

function renderAll() {
  renderSensors();
  renderControl();
  renderHeating();
  renderBoneio();
  renderVents();
  renderGroups();
  renderPlan();
  renderExternal();
  updateManualTargets();
  populateManualTarget(elements.manualScope.value);
  renderSimulationList();
  renderTestStatus();
  renderRawConfig();
}
async function loadConfig() {
  try {
    requireToken();
  } catch (err) {
    return;
  }
  try {
    showLoading('Pobieranie konfiguracji...');
    const [snapshot, controlMeta, sensors, testStatus] = await Promise.all([
      apiRequest('/installer/config', { skipSpinner: true }),
      apiRequest('/installer/config/control', { skipSpinner: true }),
      apiRequest('/installer/config/sensors', { skipSpinner: true }),
      apiRequest('/installer/test/status', { skipSpinner: true }).catch(() => null),
    ]);
    state.snapshot = snapshot;
    state.controlMeta = controlMeta;
    state.sensors = sensors;
    state.testStatus = testStatus;
    state.boneio = snapshot.boneio || [];
    state.groups = snapshot.groups || [];
    state.vents = snapshot.vents || [];
    state.plan = snapshot.plan || { close_strategy: 'fifo', stages: [] };
    setConfigVisibility(true);
    renderAll();
    setStatus('Konfiguracja zostala zaladowana', 'ok');
  } catch (err) {
    console.error(err);
    setStatus('Blad ladowania konfiguracji', 'err');
  } finally {
    hideLoading(true);
  }
}

function collectControlPayload() {
  const entries = [...elements.controlDashboard.querySelectorAll('.form-row'), ...elements.controlAdvanced.querySelectorAll('.form-row')];
  const values = {};
  entries.forEach((row) => {
    const key = row.dataset.key;
    const type = row.dataset.type;
    if (!key) {
      return;
    }
    const input = row.querySelector('input');
    if (!input) {
      return;
    }
    let value;
    if (type === 'bool') {
      value = input.checked;
    } else if (type === 'int') {
      value = input.value === '' ? null : parseInt(input.value, 10);
    } else if (type === 'float') {
      value = input.value === '' ? null : parseFloat(input.value);
    } else {
      value = input.value;
    }
    if (value !== null && value !== undefined && value !== '') {
      values[key] = value;
    }
  });
  return values;
}

async function saveControl() {
  try {
    const payload = { values: collectControlPayload() };
    const response = await apiRequest('/installer/config/control', { method: 'POST', body: payload, spinner: 'Zapisywanie parametrow...' });
    state.controlMeta = response;
    setStatus('Zapisano parametry sterownika', 'ok');
    renderControl();
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad zapisu parametrow', 'err');
  }
}

async function saveHeating() {
  try {
    const payload = {
      enabled: elements.heatingEnabled.checked,
      topic: elements.heatingTopic.value.trim() || null,
      payload_on: elements.heatingPayloadOn.value.trim() || null,
      payload_off: elements.heatingPayloadOff.value.trim() || null,
      day_target_c: elements.heatingDayTarget.value === '' ? null : Number(elements.heatingDayTarget.value),
      night_target_c: elements.heatingNightTarget.value === '' ? null : Number(elements.heatingNightTarget.value),
      hysteresis_c: elements.heatingHysteresis.value === '' ? null : Number(elements.heatingHysteresis.value),
      day_start: elements.heatingDayStart.value || null,
      night_start: elements.heatingNightStart.value || null,
    };
    const response = await apiRequest('/installer/config/heating', { method: 'POST', body: payload, spinner: 'Zapisywanie ogrzewania...' });
    state.snapshot.heating = response;
    setStatus('Zapisano konfiguracje ogrzewania', 'ok');
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad zapisu ogrzewania', 'err');
  }
}

async function saveBoneio() {
  try {
    const payload = gatherBoneioRows();
    const response = await apiRequest('/installer/config/boneio', {
      method: 'POST',
      body: payload,
      spinner: 'Zapisywanie urzadzen BoneIO...',
    });
    state.boneio = response;
    if (state.snapshot) {
      state.snapshot.boneio = response;
    }
    setStatus('Zapisano liste urzadzen BoneIO', 'ok');
    renderBoneio();
    renderVents();
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad zapisu urzadzen BoneIO', 'err');
  }
}

function gatherBoneioRows() {
  if (!elements.boneioList) {
    return [];
  }
  const rows = Array.from(elements.boneioList.querySelectorAll('.boneio-row'));
  return rows
    .map((row) => {
      const get = (selector) => row.querySelector(selector);
      const id = get('input.boneio-id')?.value.trim() || '';
      const baseTopic = get('input.boneio-topic')?.value.trim() || '';
      const description = get('input.boneio-description')?.value.trim() || '';
      const availability = get('input.boneio-availability')?.value.trim() || '';
      if (!id && !baseTopic && !description && !availability) {
        return null;
      }
      const entry = { id, base_topic: baseTopic };
      if (description) {
        entry.description = description;
      }
      if (availability) {
        entry.availability_topic = availability;
      }
      return entry;
    })
    .filter(Boolean);
}

function gatherVentRows() {
  const rows = Array.from(elements.ventList.querySelectorAll('.vent-row'));
  return rows.map((row) => {
    const get = (selector) => row.querySelector(selector);
    const deviceNode = row.querySelector('select.vent-device, input.vent-device');
    const boneioDevice = deviceNode ? deviceNode.value.trim() : '';
    return {
      id: Number(get('input.vent-id').value),
      name: get('input.vent-name').value.trim(),
      boneio_device: boneioDevice,
      travel_time_s: Number(get('input.vent-travel').value),
      topics: {
        up: get('input.vent-up').value.trim(),
        down: get('input.vent-down').value.trim(),
        error_in: get('input.vent-error').value.trim() || null,
      },
      reverse_pause_s: get('input.vent-reverse').value === '' ? null : Number(get('input.vent-reverse').value),
      min_move_s: get('input.vent-min-move').value === '' ? null : Number(get('input.vent-min-move').value),
      calibration_buffer_s: get('input.vent-calibration').value === '' ? null : Number(get('input.vent-calibration').value),
      ignore_delta_percent: get('input.vent-ignore').value === '' ? null : Number(get('input.vent-ignore').value),
    };
  });
}


async function saveVents() {
  try {
    const payload = gatherVentRows();
    const response = await apiRequest('/installer/config/vents', { method: 'POST', body: payload, spinner: 'Zapisywanie wietrznikow...' });
    state.vents = response;
    state.snapshot.vents = response;
    renderVents();
    updateManualTargets();
    setStatus('Zapisano konfiguracje wietrznikow', 'ok');
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad zapisu wietrznikow', 'err');
  }
}

function parseGroupRow(row) {
  const id = row.querySelector('.group-id').value.trim();
  const name = row.querySelector('.group-name').value.trim();
  const vents = row.querySelector('.group-vents').value.split(',').map((item) => item.trim()).filter(Boolean).map(Number);
  const lockEnabled = row.querySelector('.group-wind-lock').checked;
  const lockClose = row.querySelector('.group-wind-close').value;
  const windRaw = row.querySelector('.group-wind-ranges').value;
  const ranges = windRaw.split(';').map((entry) => entry.trim()).filter(Boolean).map((entry) => {
    const [start, end] = entry.split('-').map((value) => Number(value.trim()));
    if (Number.isFinite(start) && Number.isFinite(end)) {
      return [start, end];
    }
    return null;
  }).filter(Boolean);
  return {
    id,
    name,
    vents,
    wind_lock_enabled: lockEnabled,
    wind_lock_close_percent: lockClose === '' ? null : Number(lockClose),
    wind_upwind_deg: ranges,
  };
}

async function saveGroups() {
  try {
    const rows = Array.from(elements.groupList.querySelectorAll('.group-row'));
    const payload = rows.map(parseGroupRow);
    const response = await apiRequest('/installer/config/groups', { method: 'POST', body: payload, spinner: 'Zapisywanie grup...' });
    state.groups = response;
    state.snapshot.groups = response;
    renderGroups();
    updateManualTargets();
    renderPlan();
    setStatus('Zapisano grupy', 'ok');
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad zapisu grup', 'err');
  }
}

function parseStageRow(row) {
  const id = row.querySelector('.stage-id').value.trim();
  const name = row.querySelector('.stage-name').value.trim();
  const mode = row.querySelector('.stage-mode').value;
  const step = Number(row.querySelector('.stage-step').value);
  const delay = Number(row.querySelector('.stage-delay').value);
  const groups = Array.from(row.querySelector('.stage-groups').selectedOptions).map((option) => option.value);
  return { id, name, mode, step_percent: step, delay_s: delay, groups };
}

async function savePlan() {
  try {
    const rows = Array.from(elements.stageList.querySelectorAll('.stage-row'));
    const stages = rows.map(parseStageRow);
    const payload = {
      close_strategy: elements.planCloseStrategy.value || 'fifo',
      stages,
    };
    const response = await apiRequest('/installer/config/plan', { method: 'POST', body: payload, spinner: 'Zapisywanie planu...' });
    state.plan = response;
    state.snapshot.plan = response;
    renderPlan();
    setStatus('Zapisano plan', 'ok');
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad zapisu planu', 'err');
  }
}

async function saveExternal() {
  try {
    const payload = {
      enabled: elements.externalEnabled.checked,
      protocol: elements.externalProtocol.value,
      host: elements.externalHost.value.trim(),
      port: elements.externalPort.value === '' ? 443 : Number(elements.externalPort.value),
      path: elements.externalPath.value.trim() || '/',
      token: elements.externalToken.value.trim() || null,
    };
    const response = await apiRequest('/installer/config/external', { method: 'POST', body: payload, spinner: 'Zapisywanie konfiguracji zewnetrznej...' });
    state.snapshot.external = response;
    renderExternal();
    setStatus('Zapisano konfiguracje polaczenia', 'ok');
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad zapisu konfiguracji zewnetrznej', 'err');
  }
}

async function refreshSensors() {
  try {
    const sensors = await apiRequest('/installer/config/sensors', { spinner: 'Odswiezanie statusu...' });
    state.sensors = sensors;
    renderSensors();
    renderSimulationList();
    setStatus('Odswiezono status czujnikow', 'ok');
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad odswiezania statusu', 'err');
  }
}
async function refreshRawSnapshot() {
  try {
    const snapshot = await apiRequest('/installer/config', { spinner: 'Odswiezanie konfiguracji...' });
    state.snapshot = snapshot;
    state.boneio = snapshot.boneio || state.boneio || [];
    state.groups = snapshot.groups || [];
    state.vents = snapshot.vents || [];
    state.plan = snapshot.plan || state.plan;
    renderAll();
    setStatus('Odswiezono konfiguracje', 'ok');
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad odswiezania konfiguracji', 'err');
  }
}

async function calibrateAll() {
  try {
    await apiRequest('/installer/calibrate/all', { method: 'POST', spinner: 'Kalibracja...' });
    setStatus('Rozpoczeto kalibracje wszystkich wietrznikow', 'ok');
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad rozpoczynania kalibracji', 'err');
  }
}

async function refreshTestStatus() {
  try {
    const status = await apiRequest('/installer/test/status', { spinner: 'Odswiezanie diagnostyki...' });
    state.testStatus = status;
    renderTestStatus();
    renderSimulationList();
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad odswiezania diagnostyki', 'err');
  }
}

async function toggleTestMode(enabled) {
  try {
    const response = await apiRequest('/installer/test/control', {
      method: 'POST',
      body: { set_mode: enabled },
      spinner: enabled ? 'Wlaczanie trybu testowego...' : 'Wylaczanie trybu testowego...'
    });
    state.testStatus = response;
    renderTestStatus();
    setStatus(enabled ? 'Wlaczono tryb testowy' : 'Wylaczono tryb testowy', 'ok');
  } catch (err) {
    if (err.message === 'missing-token') {
      elements.testModeToggle.checked = !enabled;
      return;
    }
    console.error(err);
    elements.testModeToggle.checked = !enabled;
    setStatus('Blad zmiany trybu testowego', 'err');
  }
}

async function sendManualCommand() {
  try {
    const scope = elements.manualScope.value;
    let target = null;
    if (scope === 'group' || scope === 'vent') {
      target = elements.manualTarget.value;
      if (!target) {
        setStatus('Wybierz cel polecenia', 'err');
        return;
      }
    }
    const value = Number(elements.manualValue.value);
    if (Number.isNaN(value) || value < 0 || value > 100) {
      setStatus('Podaj wartosć od 0 do 100%', 'err');
      return;
    }
    const payload = { manual: { scope, target, value } };
    const response = await apiRequest('/installer/test/control', { method: 'POST', body: payload, spinner: 'Wysylanie polecenia...' });
    state.testStatus = response;
    renderTestStatus();
    setStatus('Polecenie zostalo wyslane', 'ok');
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad wysylania polecenia testowego', 'err');
  }
}

async function applySimulation() {
  try {
    const overrides = {};
    elements.simulationList.querySelectorAll('.sim-row').forEach((row) => {
      const key = row.dataset.key;
      const input = row.querySelector('input');
      if (input.value !== '') {
        overrides[key] = Number(input.value);
      }
    });
    const response = await apiRequest('/installer/test/simulate', {
      method: 'POST',
      body: { overrides },
      spinner: 'Zastosowanie symulacji...'
    });
    state.testStatus = state.testStatus || {};
    state.testStatus.test_mode = response;
    renderTestStatus();
    renderSimulationList();
    setStatus('Symulacje zostaly zastosowane', 'ok');
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad stosowania symulacji', 'err');
  }
}

async function resetSimulation() {
  try {
    const response = await apiRequest('/installer/test/simulate', {
      method: 'POST',
      body: { reset: true },
      spinner: 'Resetowanie symulacji...'
    });
    state.testStatus = state.testStatus || {};
    state.testStatus.test_mode = response;
    renderTestStatus();
    renderSimulationList();
    setStatus('Symulacje zresetowane', 'ok');
  } catch (err) {
    console.error(err);
    setStatus('Blad resetowania symulacji', 'err');
  }
}

async function loadLogs(kind) {
  try {
    const response = await apiRequest(`/installer/test/logs?kind=${encodeURIComponent(kind)}&limit=200`, { spinner: `Pobieranie logow (${kind})...` });
    elements.logsOutput.textContent = (response.entries || []).join('\n');
    setStatus(`Pobrano logi ${kind.toUpperCase()}`, 'ok');
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad pobierania logow', 'err');
  }
}

async function pingTarget(target) {
  try {
    const response = await apiRequest('/installer/test/ping', {
      method: 'POST',
      body: { targets: [target] },
      spinner: `Pingowanie (${target})...`
    });
    const results = response.results || [];
    elements.pingResults.innerHTML = '';
    results.forEach((result) => {
      const item = document.createElement('div');
      item.className = 'list-item';
      const duration = result.duration_ms ? ` (${result.duration_ms.toFixed(1)} ms)` : '';
      item.innerHTML = `<div><strong>${result.name}</strong></div><div>${result.success ? 'OK' : 'Blad'}${duration}</div><div class="muted">${result.error || ''}</div>`;
      elements.pingResults.appendChild(item);
    });
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Blad testu polaczenia', 'err');
  }
}

function handleSimulationClick(event) {
  const action = event.target.dataset.action;
  if (action === 'clear-sim') {
    const row = event.target.closest('.sim-row');
    if (row) {
      row.querySelector('input').value = '';
    }
  }
}

function addCustomSimulationRow() {
  const key = window.prompt('Podaj nazwe parametru do symulacji');
  if (!key) {
    return;
  }
  const row = document.createElement('div');
  row.className = 'form-row sim-row';
  row.dataset.key = key;
  row.innerHTML = `<label>${key}<input type="number" step="any" /></label><button type="button" class="inline" data-action="clear-sim">Wyczysć</button>`;
  elements.simulationList.appendChild(row);
}

function addBoneioRow() {
  const device = { id: '', base_topic: '', description: '', availability_topic: '' };
  const row = createBoneioRow(device, elements.boneioList?.children.length || 0);
  if (row) {
    row.open = true;
    elements.boneioList?.appendChild(row);
  }
}

function handleBoneioListClick(event) {
  const action = event.target.dataset.action;
  if (action === 'remove-boneio') {
    const row = event.target.closest('.boneio-row');
    row?.remove();
  }
}

function addVentRow() {
  const newVent = { id: '', name: '', boneio_device: '', travel_time_s: 30, topics: { up: '', down: '' } };
  const row = createVentRow(newVent);
  row.open = true;
  elements.ventList.appendChild(row);
}

function addGroupRow() {
  const group = { id: '', name: '', vents: [], wind_lock_enabled: true, wind_upwind_deg: [] };
  const row = createGroupRow(group, elements.groupList.children.length);
  row.open = true;
  elements.groupList.appendChild(row);
}

function addStageRow() {
  const stage = { id: '', name: '', mode: 'serial', step_percent: 100, delay_s: 0, groups: [] };
  const row = createStageRow(stage, elements.stageList.children.length);
  elements.stageList.appendChild(row);
}

function handleVentListClick(event) {
  const action = event.target.dataset.action;
  if (action === 'remove-vent') {
    const row = event.target.closest('.vent-row');
    row?.remove();
  }
}

function handleGroupListClick(event) {
  const action = event.target.dataset.action;
  if (action === 'remove-group') {
    const row = event.target.closest('.group-row');
    row?.remove();
  }
}

function handleStageListClick(event) {
  const action = event.target.dataset.action;
  if (!action) {
    return;
  }
  const row = event.target.closest('.stage-row');
  if (!row) {
    return;
  }
  if (action === 'remove-stage') {
    row.remove();
  } else if (action === 'stage-up') {
    const prev = row.previousElementSibling;
    if (prev) {
      elements.stageList.insertBefore(row, prev);
    }
  } else if (action === 'stage-down') {
    const next = row.nextElementSibling;
    if (next) {
      elements.stageList.insertBefore(next, row);
    }
  }
}

function handleManualScopeChange() {
  const scope = elements.manualScope.value;
  populateManualTarget(scope);
}
function bindEvents() {
  elements.panelTabs.forEach((btn) => {
    btn.addEventListener('click', () => togglePanels(btn.dataset.panel));
  });
  elements.loadBtn?.addEventListener('click', loadConfig);
  elements.refreshSensors?.addEventListener('click', refreshSensors);
  elements.saveControl?.addEventListener('click', saveControl);
  elements.saveHeating?.addEventListener('click', saveHeating);
  elements.addBoneio?.addEventListener('click', addBoneioRow);
  elements.saveBoneio?.addEventListener('click', saveBoneio);
  elements.boneioList?.addEventListener('click', handleBoneioListClick);
  elements.addVent?.addEventListener('click', addVentRow);
  elements.saveVents?.addEventListener('click', saveVents);
  elements.ventList?.addEventListener('click', handleVentListClick);
  elements.addGroup?.addEventListener('click', addGroupRow);
  elements.saveGroups?.addEventListener('click', saveGroups);
  elements.groupList?.addEventListener('click', handleGroupListClick);
  elements.addStage?.addEventListener('click', addStageRow);
  elements.savePlan?.addEventListener('click', savePlan);
  elements.stageList?.addEventListener('click', handleStageListClick);
  elements.saveExternal?.addEventListener('click', saveExternal);
  elements.calibrateAll?.addEventListener('click', calibrateAll);
  elements.refreshRaw?.addEventListener('click', refreshRawSnapshot);
  elements.testModeToggle?.addEventListener('change', (event) => toggleTestMode(event.target.checked));
  elements.refreshTestStatus?.addEventListener('click', refreshTestStatus);
  elements.manualSend?.addEventListener('click', sendManualCommand);
  elements.manualScope?.addEventListener('change', handleManualScopeChange);
  elements.applySim?.addEventListener('click', applySimulation);
  elements.resetSim?.addEventListener('click', resetSimulation);
  elements.addSimRow?.addEventListener('click', addCustomSimulationRow);
  elements.simulationList?.addEventListener('click', handleSimulationClick);
  elements.logButtons.forEach((btn) => btn.addEventListener('click', () => loadLogs(btn.dataset.logKind)));
  elements.pingButtons.forEach((btn) => btn.addEventListener('click', () => pingTarget(btn.dataset.ping)));
}

function init() {
  setConfigVisibility(false);
  bindEvents();
}

init();




