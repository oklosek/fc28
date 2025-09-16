const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const elements = {
  token: $('#tokenInput'),
  loadBtn: $('#loadConfig'),
  status: $('#status'),
  controlSection: $('#controlSection'),
  groupsSection: $('#groupsSection'),
  planSection: $('#planSection'),
  manualSection: $('#manualSection'),
  actionsSection: $('#actionsSection'),
  rawSection: $('#rawSection'),
  controlFields: $('#controlFields'),
  groupList: $('#groupList'),
  stageList: $('#stageList'),
  planCloseStrategy: $('#planCloseStrategy'),
  addGroupBtn: $('#addGroup'),
  addStageBtn: $('#addStage'),
  saveControlBtn: $('#saveControl'),
  saveGroupsBtn: $('#saveGroups'),
  manualGroupSelect: $('#manualGroupSelect'),
  manualGroupValue: $('#manualGroupValue'),
  manualGroupSend: $('#manualGroupSend'),
  calibrateAllBtn: $('#calibrateAll'),
  rawConfig: $('#rawConfig'),
};

let currentConfig = null;

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

function showConfigSections(visible) {
  $$('.requires-config').forEach((el) => {
    if (visible) {
      el.classList.remove('hidden');
    } else {
      el.classList.add('hidden');
    }
  });
}

function renderControl(control) {
  elements.controlFields.innerHTML = '';
  Object.entries(control).forEach(([key, value]) => {
    const row = document.createElement('div');
    row.className = 'form-row';

    const label = document.createElement('label');
    label.textContent = key;

    let input;
    if (typeof value === 'boolean') {
      input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = value;
      input.dataset.type = 'boolean';
    } else if (!Number.isNaN(Number(value))) {
      input = document.createElement('input');
      input.type = 'number';
      input.value = value;
      input.step = 'any';
      input.dataset.type = 'number';
    } else {
      input = document.createElement('input');
      input.type = 'text';
      input.value = value ?? '';
      input.dataset.type = 'text';
    }
    input.dataset.key = key;

    label.appendChild(input);
    row.appendChild(label);
    elements.controlFields.appendChild(row);
  });
}

function createVentOptions(selected = []) {
  const select = document.createElement('select');
  select.multiple = true;
  select.className = 'group-vents';
  (currentConfig?.vents || []).forEach((vent) => {
    const option = document.createElement('option');
    option.value = String(vent.id);
    option.textContent = `#${vent.id} ${vent.name}`;
    if (selected.includes(vent.id) || selected.includes(String(vent.id))) {
      option.selected = true;
    }
    select.appendChild(option);
  });
  return select;
}

function createGroupRow(group = { id: '', name: '', vents: [] }) {
  const row = document.createElement('div');
  row.className = 'group-row';

  const idLabel = document.createElement('label');
  idLabel.textContent = 'ID grupy';
  const idInput = document.createElement('input');
  idInput.type = 'text';
  idInput.value = group.id || '';
  idInput.className = 'group-id';
  idLabel.appendChild(idInput);

  const nameLabel = document.createElement('label');
  nameLabel.textContent = 'Nazwa';
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.value = group.name || '';
  nameInput.className = 'group-name';
  nameLabel.appendChild(nameInput);

  const ventsLabel = document.createElement('label');
  ventsLabel.textContent = 'Wietrzniki';
  const ventsSelect = createVentOptions(group.vents || []);
  ventsLabel.appendChild(ventsSelect);

  const removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.className = 'small';
  removeBtn.textContent = 'Usuń';
  removeBtn.dataset.action = 'remove-group';

  row.append(idLabel, nameLabel, ventsLabel, removeBtn);
  return row;
}

function renderGroups(groups) {
  elements.groupList.innerHTML = '';
  (groups || []).forEach((group) => {
    elements.groupList.appendChild(createGroupRow(group));
  });
  if (!groups || groups.length === 0) {
    elements.groupList.appendChild(createGroupRow());
  }
  refreshGroupTargets();
}

function createStageRow(stage = {}) {
  const row = document.createElement('div');
  row.className = 'stage-row';

  const idLabel = document.createElement('label');
  idLabel.textContent = 'ID etapu';
  const idInput = document.createElement('input');
  idInput.type = 'text';
  idInput.value = stage.id || '';
  idInput.className = 'stage-id';
  idLabel.appendChild(idInput);

  const nameLabel = document.createElement('label');
  nameLabel.textContent = 'Nazwa';
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.value = stage.name || '';
  nameInput.className = 'stage-name';
  nameLabel.appendChild(nameInput);

  const modeLabel = document.createElement('label');
  modeLabel.textContent = 'Tryb';
  const modeSelect = document.createElement('select');
  modeSelect.className = 'stage-mode';
  ['serial', 'parallel'].forEach((mode) => {
    const option = document.createElement('option');
    option.value = mode;
    option.textContent = mode === 'serial' ? 'Szeregowo' : 'Równolegle';
    if ((stage.mode || 'serial') === mode) {
      option.selected = true;
    }
    modeSelect.appendChild(option);
  });
  modeLabel.appendChild(modeSelect);

  const stepLabel = document.createElement('label');
  stepLabel.textContent = 'Krok [%]';
  const stepInput = document.createElement('input');
  stepInput.type = 'number';
  stepInput.min = '1';
  stepInput.max = '100';
  stepInput.value = stage.step_percent ?? 100;
  stepInput.className = 'stage-step';
  stepLabel.appendChild(stepInput);

  const delayLabel = document.createElement('label');
  delayLabel.textContent = 'Opóźnienie [s]';
  const delayInput = document.createElement('input');
  delayInput.type = 'number';
  delayInput.min = '0';
  delayInput.step = '0.1';
  delayInput.value = stage.delay_s ?? 0;
  delayInput.className = 'stage-delay';
  delayLabel.appendChild(delayInput);

  const closeLabel = document.createElement('label');
  closeLabel.textContent = 'Strategia zamykania';
  const closeSelect = document.createElement('select');
  closeSelect.className = 'stage-close';
  const globalFlag = Number(elements.planCloseStrategy.value || currentConfig?.plan?.close_strategy_flag || 0);
  const stageFlag = stage.close_strategy_flag;
  const options = [
    { value: 'inherit', label: 'Dziedzicz globalną' },
    { value: '0', label: 'FIFO' },
    { value: '1', label: 'LIFO' },
  ];
  options.forEach(({ value, label }) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    if (value === 'inherit') {
      if (stageFlag === undefined || stageFlag === null) {
        option.selected = true;
      } else if (stageFlag === globalFlag) {
        option.selected = true;
      }
    } else if (stageFlag !== undefined && stageFlag !== null && String(stageFlag) === value) {
      option.selected = true;
    }
    closeSelect.appendChild(option);
  });
  closeLabel.appendChild(closeSelect);

  const groupsLabel = document.createElement('label');
  groupsLabel.textContent = 'Grupy w etapie';
  const groupsSelect = document.createElement('select');
  groupsSelect.multiple = true;
  groupsSelect.className = 'stage-groups';
  groupsLabel.appendChild(groupsSelect);

  const moveUp = document.createElement('button');
  moveUp.type = 'button';
  moveUp.textContent = '↑';
  moveUp.className = 'small';
  moveUp.dataset.action = 'stage-up';

  const moveDown = document.createElement('button');
  moveDown.type = 'button';
  moveDown.textContent = '↓';
  moveDown.className = 'small';
  moveDown.dataset.action = 'stage-down';

  const removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.textContent = 'Usuń';
  removeBtn.className = 'small';
  removeBtn.dataset.action = 'remove-stage';

  row.append(
    idLabel,
    nameLabel,
    modeLabel,
    stepLabel,
    delayLabel,
    closeLabel,
    groupsLabel,
    moveUp,
    moveDown,
    removeBtn,
  );

  // Ustaw wartości grup po wyrenderowaniu opcji
  requestAnimationFrame(() => {
    updateStageGroupOptions();
    const selected = (stage.groups || []).map(String);
    $$('.stage-row select.stage-groups').forEach((select) => {
      if (select === groupsSelect) {
        Array.from(select.options).forEach((opt) => {
          if (selected.includes(opt.value)) {
            opt.selected = true;
          }
        });
      }
    });
  });

  return row;
}

function renderPlan(plan) {
  const flag = Number(plan?.close_strategy_flag ?? 0);
  elements.planCloseStrategy.value = String(flag);
  elements.stageList.innerHTML = '';
  (plan?.stages || []).forEach((stage) => {
    elements.stageList.appendChild(createStageRow(stage));
  });
  if (!plan || plan.stages?.length === 0) {
    elements.stageList.appendChild(createStageRow());
  }
  updateStageGroupOptions();
}

function updateStageGroupOptions() {
  const groupIds = collectGroupIds();
  $$('.stage-groups').forEach((select) => {
    const selected = new Set(Array.from(select.selectedOptions).map((opt) => opt.value));
    select.innerHTML = '';
    groupIds.forEach((id) => {
      const option = document.createElement('option');
      option.value = id;
      option.textContent = id;
      if (selected.has(id)) {
        option.selected = true;
      }
      select.appendChild(option);
    });
  });
  refreshGroupTargets();
}

function refreshGroupTargets() {
  const groupSelect = elements.manualGroupSelect;
  const currentValue = groupSelect.value;
  groupSelect.innerHTML = '<option value="">-- wybierz grupę --</option>';
  collectGroupIds().forEach((id) => {
    const option = document.createElement('option');
    option.value = id;
    option.textContent = id;
    groupSelect.appendChild(option);
  });
  if (currentValue) {
    const option = Array.from(groupSelect.options).find((opt) => opt.value === currentValue);
    if (option) {
      option.selected = true;
    }
  }
}

function collectGroupIds() {
  return $$('.group-row .group-id')
    .map((input) => input.value.trim())
    .filter((id) => id.length > 0);
}

async function loadConfig() {
  try {
    const token = requireToken();
    setStatus('Ładowanie...');
    const response = await fetch('/installer/config', {
      headers: {
        'x-admin-token': token,
      },
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || response.statusText);
    }
    const data = await response.json();
    currentConfig = data;
    setStatus('Konfiguracja załadowana', 'ok');
    showConfigSections(true);
    renderControl(data.control || {});
    renderGroups(data.groups || []);
    renderPlan(data.plan || {});
    updateStageGroupOptions();
    elements.rawConfig.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Błąd ładowania konfiguracji', 'err');
  }
}

function collectControlPayload() {
  const payload = {};
  $$('#controlFields input').forEach((input) => {
    const key = input.dataset.key;
    const type = input.dataset.type;
    if (!key) {
      return;
    }
    if (type === 'boolean') {
      payload[key] = input.checked;
    } else if (type === 'number') {
      const value = input.value.trim();
      if (value === '') {
        return;
      }
      const numberValue = Number(value);
      payload[key] = Number.isInteger(numberValue) ? parseInt(value, 10) : numberValue;
    } else {
      payload[key] = input.value;
    }
  });
  return payload;
}

function collectGroupsPayload() {
  const groups = [];
  $$('.group-row').forEach((row, index) => {
    const id = row.querySelector('.group-id').value.trim() || `group_${index + 1}`;
    const name = row.querySelector('.group-name').value.trim() || id;
    const vents = Array.from(row.querySelectorAll('.group-vents option:checked')).map((opt) => Number(opt.value));
    if (vents.length === 0) {
      return;
    }
    groups.push({ id, name, vents });
  });
  return groups;
}

function collectPlanPayload() {
  const plan = {
    close_strategy_flag: Number(elements.planCloseStrategy.value || 0),
    stages: [],
  };
  $$('.stage-row').forEach((row, index) => {
    const id = row.querySelector('.stage-id').value.trim() || `stage_${index + 1}`;
    const name = row.querySelector('.stage-name').value.trim() || id;
    const mode = row.querySelector('.stage-mode').value;
    const step = Number(row.querySelector('.stage-step').value || 100);
    const delay = Number(row.querySelector('.stage-delay').value || 0);
    const closeValue = row.querySelector('.stage-close').value;
    const groups = Array.from(row.querySelectorAll('.stage-groups option:checked')).map((opt) => opt.value);
    if (groups.length === 0) {
      return;
    }
    const stage = {
      id,
      name,
      mode,
      step_percent: step,
      delay_s: delay,
      groups,
    };
    if (closeValue !== 'inherit') {
      stage.close_strategy_flag = Number(closeValue);
    }
    plan.stages.push(stage);
  });
  return plan;
}

async function saveControl() {
  try {
    const token = requireToken();
    const payload = collectControlPayload();
    setStatus('Zapisywanie parametrów...', 'info');
    const response = await fetch('/installer/config/control', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-admin-token': token,
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    setStatus('Zapisano parametry sterowania', 'ok');
    await loadConfig();
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Błąd zapisu parametrów', 'err');
  }
}

async function saveGroupsAndPlan() {
  try {
    const token = requireToken();
    const groups = collectGroupsPayload();
    const plan = collectPlanPayload();
    if (groups.length === 0) {
      setStatus('Dodaj przynajmniej jedną grupę z wietrznikami', 'err');
      return;
    }
    if (plan.stages.length === 0) {
      setStatus('Dodaj przynajmniej jeden etap w planie', 'err');
      return;
    }
    setStatus('Zapisywanie grup i planu...', 'info');
    const response = await fetch('/installer/config/groups', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-admin-token': token,
      },
      body: JSON.stringify({ groups, plan }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    setStatus('Zapisano grupy i plan', 'ok');
    await loadConfig();
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Błąd zapisu grup lub planu', 'err');
  }
}

async function sendManualGroup() {
  const groupId = elements.manualGroupSelect.value;
  const position = Number(elements.manualGroupValue.value);
  if (!groupId) {
    setStatus('Wybierz grupę do sterowania', 'err');
    return;
  }
  if (Number.isNaN(position) || position < 0 || position > 100) {
    setStatus('Podaj wartość od 0 do 100%', 'err');
    return;
  }
  try {
    setStatus(`Wysyłanie polecenia dla ${groupId}...`, 'info');
    const response = await fetch(`/api/vents/group/${encodeURIComponent(groupId)}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ position }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    setStatus(`Polecenie wysłane dla ${groupId}`, 'ok');
  } catch (err) {
    console.error(err);
    setStatus('Błąd wysyłania polecenia do grupy', 'err');
  }
}

async function calibrateAll() {
  try {
    const token = requireToken();
    setStatus('Uruchamianie kalibracji...', 'info');
    const response = await fetch('/installer/calibrate/all', {
      method: 'POST',
      headers: {
        'x-admin-token': token,
      },
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    setStatus('Kalibracja wystartowała', 'ok');
  } catch (err) {
    if (err.message === 'missing-token') {
      return;
    }
    console.error(err);
    setStatus('Błąd uruchamiania kalibracji', 'err');
  }
}

// Event listeners
if (elements.loadBtn) {
  elements.loadBtn.addEventListener('click', loadConfig);
}
if (elements.saveControlBtn) {
  elements.saveControlBtn.addEventListener('click', saveControl);
}
if (elements.addGroupBtn) {
  elements.addGroupBtn.addEventListener('click', () => {
    elements.groupList.appendChild(createGroupRow());
    updateStageGroupOptions();
  });
}
if (elements.addStageBtn) {
  elements.addStageBtn.addEventListener('click', () => {
    elements.stageList.appendChild(createStageRow());
    updateStageGroupOptions();
  });
}
if (elements.groupList) {
  elements.groupList.addEventListener('click', (event) => {
    const action = event.target.dataset.action;
    if (action === 'remove-group') {
      const row = event.target.closest('.group-row');
      row?.remove();
      updateStageGroupOptions();
    }
  });
  elements.groupList.addEventListener('input', (event) => {
    if (event.target.classList.contains('group-id')) {
      updateStageGroupOptions();
    }
  });
}
if (elements.stageList) {
  elements.stageList.addEventListener('click', (event) => {
    const action = event.target.dataset.action;
    if (!action) {
      return;
    }
    const row = event.target.closest('.stage-row');
    if (!row) {
      return;
    }
    switch (action) {
      case 'remove-stage':
        row.remove();
        break;
      case 'stage-up': {
        const prev = row.previousElementSibling;
        if (prev) {
          elements.stageList.insertBefore(row, prev);
        }
        break;
      }
      case 'stage-down': {
        const next = row.nextElementSibling;
        if (next) {
          elements.stageList.insertBefore(next, row);
        }
        break;
      }
      default:
        break;
    }
  });
}
if (elements.saveGroupsBtn) {
  elements.saveGroupsBtn.addEventListener('click', saveGroupsAndPlan);
}
if (elements.manualGroupSend) {
  elements.manualGroupSend.addEventListener('click', sendManualGroup);
}
if (elements.calibrateAllBtn) {
  elements.calibrateAllBtn.addEventListener('click', calibrateAll);
}

// Przy pierwszym załadowaniu ukryj sekcje do czasu pobrania konfiguracji
showConfigSections(false);
