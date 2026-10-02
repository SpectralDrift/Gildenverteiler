const guildsEl = document.querySelector('#guilds');
const vikingsEl = document.querySelector('#vikings');
const errorEl = document.querySelector('#error');
const resultEl = document.querySelector('#result');
const configStatusEl = document.querySelector('#config-status');
const sizeStatusEl = document.querySelector('#size-status');
let guildId = 0;
let csrfToken = '';
const MAX_VIKINGS = 20;
const GUILD_MINIMUM_SIZES = [2, 2, 2, 5, 4, 3];
const GUILD_MAXIMUM_SIZES = [3, 3, 3, 6, 5, 4];

function addGuild(name = '', minimumSize = null, maximumSize = null) {
  if (guildsEl.children.length >= 6) return;
  const guildIndex = guildsEl.children.length;
  const wrapper = document.createElement('div');
  wrapper.className = 'guild-field';
  const input = document.createElement('input');
  input.className = 'guild-name';
  input.dataset.id = guildId++;
  input.maxLength = 50;
  input.pattern = '[A-Za-zÄÖÜäöüß0-9]+';
  input.title = 'Nur Buchstaben, deutsche Umlaute und Ziffern';
  input.value = name;
  input.placeholder = `Gilde ${guildsEl.children.length + 1}`;
  input.setAttribute('aria-label', input.placeholder);
  input.addEventListener('input', refreshRankings);
  const minimum = document.createElement('input');
  minimum.className = 'guild-minimum';
  minimum.type = 'number'; minimum.min = '2'; minimum.max = '8'; minimum.step = '1';
  minimum.placeholder = 'Min.';
  minimum.setAttribute('aria-label', `Mindestgröße für ${name || input.placeholder}`);
  minimum.value = String(minimumSize ?? GUILD_MINIMUM_SIZES[guildIndex]);
  minimum.addEventListener('input', updateSizeStatus);
  const minimumField = document.createElement('label'); minimumField.className = 'guild-size-field';
  const minimumLabel = document.createElement('span'); minimumLabel.textContent = 'Min.';
  minimumField.append(minimumLabel, minimum);
  const maximum = document.createElement('input');
  maximum.className = 'guild-maximum';
  maximum.type = 'number'; maximum.min = '2'; maximum.max = '8'; maximum.step = '1';
  maximum.placeholder = 'Max.';
  maximum.setAttribute('aria-label', `Höchstgröße für ${name || input.placeholder}`);
  maximum.value = String(maximumSize ?? GUILD_MAXIMUM_SIZES[guildIndex]);
  maximum.addEventListener('input', updateSizeStatus);
  const maximumField = document.createElement('label'); maximumField.className = 'guild-size-field';
  const maximumLabel = document.createElement('span'); maximumLabel.textContent = 'Max.';
  maximumField.append(maximumLabel, maximum);
  wrapper.append(input, minimumField, maximumField);
  guildsEl.append(wrapper);
  refreshRankings();
}

function shuffle(values) {
  for (let index = values.length - 1; index > 0; index--) {
    const other = Math.floor(Math.random() * (index + 1));
    [values[index], values[other]] = [values[other], values[index]];
  }
  return values;
}

function randomRanking() {
  const guildCount = guildsEl.children.length;
  const guilds = shuffle(Array.from({length: guildCount}, (_, index) => index));
  const possibleExplicitCounts = Array.from({length: guildCount + 1}, (_, count) => count)
    .filter(count => count !== guildCount - 1);
  const explicitCount = possibleExplicitCounts[Math.floor(Math.random() * possibleExplicitCounts.length)];
  const equalCount = guildCount - explicitCount;
  const equalStart = Math.floor(Math.random() * (explicitCount + 1));
  const ranking = guilds.slice(0, explicitCount);
  ranking.splice(equalStart, 0, ...Array(equalCount).fill(null));
  return ranking;
}

function addViking(name = '', savedRanking = null) {
  if (vikingsEl.children.length >= MAX_VIKINGS) return;
  const row = document.createElement('div');
  row.className = 'viking';
  row.innerHTML = `<input class="viking-name" maxlength="50" pattern="[A-Za-zÄÖÜäöüß0-9_. ]+" title="Buchstaben, deutsche Umlaute, Ziffern, Leerzeichen, Punkte und Unterstriche" placeholder="Name des Wikingers" aria-label="Name des Wikingers"><div class="ranking"></div><button class="remove" type="button" aria-label="Wikinger entfernen">Entfernen</button>`;
  row.querySelector('.viking-name').value = name;
  row.querySelector('.remove').addEventListener('click', () => {
    const vikingName = row.querySelector('.viking-name').value.trim() || 'diesen Wikinger';
    if (window.confirm(`${vikingName} wirklich entfernen?`)) { row.remove(); updateButtons(); }
  });
  vikingsEl.append(row);
  refreshRanking(row, savedRanking || randomRanking());
  updateButtons();
}

function refreshRankings() {
  document.querySelectorAll('.viking').forEach(row => refreshRanking(row));
  updateButtons();
}

function refreshRanking(row, suppliedRanking = null) {
  const area = row.querySelector('.ranking');
  const old = suppliedRanking || rankingValues(row);
  const guilds = [...guildsEl.querySelectorAll('.guild-name')];
  area.replaceChildren();
  guilds.forEach((_, rank) => {
    const wrapper = document.createElement('div'); wrapper.className = 'rank';
    const label = document.createElement('label'); label.textContent = `${rank + 1}. Wunsch`;
    const select = document.createElement('select'); select.setAttribute('aria-label', `${rank + 1}. Wunsch`);
    guilds.forEach((input, index) => {
      const option = document.createElement('option'); option.value = index;
      option.textContent = input.value.trim() || input.placeholder; select.append(option);
    });
    const equalOption = document.createElement('option'); equalOption.value = 'equal'; equalOption.textContent = 'egal'; select.append(equalOption);
    const fallback = old.includes(null) ? null : guilds.length - 1;
    const selected = old[rank] !== undefined && (old[rank] === null || old[rank] < guilds.length) ? old[rank] : fallback;
    select.value = selected === null ? 'equal' : selected;
    select.dataset.previous = select.value;
    select.addEventListener('change', () => {
      const previous = select.dataset.previous;
      if (select.value !== 'equal') {
        const duplicate = [...area.querySelectorAll('select')].find(other => other !== select && other.value === select.value);
        if (duplicate) { duplicate.value = previous; duplicate.dataset.previous = previous; }
      }
      select.dataset.previous = select.value;
      ensureEqualPair(area, select);
      fillSingleEqual(area);
      updateRankingState(area);
    });
    wrapper.append(label, select); area.append(wrapper);
  });
  fillSingleEqual(area);
  updateRankingState(area);
}

function rankingValues(row) {
  return [...row.querySelectorAll('.ranking select')].map(select => select.value === 'equal' ? null : Number(select.value));
}

function ensureEqualPair(area, changedSelect) {
  const selects = [...area.querySelectorAll('select')];
  if (changedSelect.value !== 'equal'
      || selects.filter(select => select.value === 'equal').length !== 1
      || selects.length < 2) return false;
  const index = selects.indexOf(changedSelect);
  const companion = selects[index + 1] || selects[index - 1];
  companion.value = 'equal';
  companion.dataset.previous = 'equal';
  return true;
}

function fillSingleEqual(area) {
  const selects = [...area.querySelectorAll('select')];
  const equalSelects = selects.filter(select => select.value === 'equal');
  if (equalSelects.length !== 1) return false;
  const used = new Set(selects.filter(select => select.value !== 'equal').map(select => Number(select.value)));
  const missingGuild = Array.from({length: selects.length}, (_, index) => index)
    .find(guild => !used.has(guild));
  equalSelects[0].value = String(missingGuild);
  equalSelects[0].dataset.previous = equalSelects[0].value;
  return true;
}

function updateRankingState(area) {
  const selects = [...area.querySelectorAll('select')];
  selects.forEach(select => {
    select.disabled = false;
    select.dataset.previous = select.value;
  });
}

function updateButtons() {
  document.querySelector('main').style.setProperty('--page-max', '1550px');
  document.querySelector('#add-viking').disabled = vikingsEl.children.length >= MAX_VIKINGS;
  document.querySelectorAll('.viking .remove').forEach(button => button.disabled = vikingsEl.children.length <= 1);
  updateSizeStatus();
}

function updateSizeStatus() {
  const minimumInputs = [...guildsEl.querySelectorAll('.guild-minimum')];
  const maximumInputs = [...guildsEl.querySelectorAll('.guild-maximum')];
  if (minimumInputs.length !== 6 || maximumInputs.length !== 6) {
    sizeStatusEl.textContent = '';
    return;
  }
  const minimumSizes = minimumInputs.map(input => input.value === '' ? null : Number(input.value));
  const maximumSizes = maximumInputs.map(input => input.value === '' ? null : Number(input.value));
  const invalidNumber = minimumSizes.concat(maximumSizes)
    .some(size => !Number.isInteger(size) || size < 2 || size > 8);
  let message;
  let isError = true;
  if (invalidNumber) {
    message = 'Bitte für jedes Minimum und Maximum eine ganze Zahl zwischen 2 und 8 eingeben.';
  } else {
    const invalidRange = minimumSizes.findIndex((minimum, index) => minimum > maximumSizes[index]);
    const vikingCount = vikingsEl.children.length;
    const minimumTotal = minimumSizes.reduce((total, size) => total + size, 0);
    const maximumTotal = maximumSizes.reduce((total, size) => total + size, 0);
    if (invalidRange >= 0) {
      const guildName = guildsEl.children[invalidRange].querySelector('.guild-name').value.trim() || `Gilde ${invalidRange + 1}`;
      message = `${guildName}: Das Minimum darf nicht größer als das Maximum sein.`;
    } else if (minimumTotal > vikingCount) {
      message = `Nicht möglich: Die Mindestgrößen ergeben ${minimumTotal}, vorhanden sind ${vikingCount} Wikinger.`;
    } else if (maximumTotal < vikingCount) {
      message = `Nicht möglich: Die Höchstgrößen ergeben nur ${maximumTotal}, vorhanden sind ${vikingCount} Wikinger.`;
    } else {
      message = `${vikingCount} Wikinger passen in die eingestellten Größenbereiche (${minimumTotal} bis ${maximumTotal} Plätze).`;
      isError = false;
    }
  }
  sizeStatusEl.textContent = message;
  sizeStatusEl.classList.toggle('error', isError);
}

function repairRanking(row) {
  const selects = [...row.querySelectorAll('.ranking select')];
  const used = new Set();
  let repaired = false;
  selects.forEach(select => {
    if (select.value === 'equal') return;
    if (used.has(select.value)) {
      select.value = 'equal';
      repaired = true;
    } else {
      used.add(select.value);
    }
  });
  fillSingleEqual(row.querySelector('.ranking'));
  updateRankingState(row.querySelector('.ranking'));
  return repaired;
}

function currentConfiguration() {
  return {
    version: 1,
    guilds: [...guildsEl.querySelectorAll('.guild-name')].map(input => input.value.trim()),
    guildMinimumSizes: [...guildsEl.querySelectorAll('.guild-minimum')].map(input => input.value === '' ? null : Number(input.value)),
    guildMaximumSizes: [...guildsEl.querySelectorAll('.guild-maximum')].map(input => input.value === '' ? null : Number(input.value)),
    vikings: [...document.querySelectorAll('.viking')].map(row => ({
      name: row.querySelector('.viking-name').value.trim(),
      ranking: rankingValues(row)
    }))
  };
}

function validateConfiguration(config) {
  if (!config || config.version !== 1 || !Array.isArray(config.guilds) || !Array.isArray(config.vikings)) {
    throw new Error('Dies ist keine unterstützte Gildenverteiler-Konfiguration.');
  }
  if (config.guilds.length !== 6) throw new Error('Die Konfiguration muss genau 6 Gilden enthalten.');
  if (config.vikings.length < 1 || config.vikings.length > MAX_VIKINGS) throw new Error('Die Konfiguration muss 1 bis 20 Wikinger enthalten.');
  const guildNamePattern = /^[A-Za-zÄÖÜäöüß0-9]{1,50}$/;
  const vikingNamePattern = /^[A-Za-zÄÖÜäöüß0-9_. ]{1,50}$/;
  const guildNames = config.guilds.map(name => typeof name === 'string' ? name.trim() : '');
  if (guildNames.some(name => !guildNamePattern.test(name)) || new Set(guildNames).size !== guildNames.length) {
    throw new Error('Gildennamen müssen gültig und eindeutig sein.');
  }
  let minimumSizes = config.guildMinimumSizes;
  let maximumSizes = config.guildMaximumSizes;
  if (minimumSizes === undefined && maximumSizes === undefined) {
    const legacySizes = config.guildSizes === undefined ? Array(6).fill(null) : config.guildSizes;
    if (!Array.isArray(legacySizes) || legacySizes.length !== 6) throw new Error('Die Angaben zu den Gildengrößen sind ungültig.');
    minimumSizes = legacySizes.map((size, index) => size ?? GUILD_MINIMUM_SIZES[index]);
    maximumSizes = legacySizes.map((size, index) => size ?? GUILD_MAXIMUM_SIZES[index]);
  }
  if (!Array.isArray(minimumSizes) || minimumSizes.length !== 6
      || !Array.isArray(maximumSizes) || maximumSizes.length !== 6
      || minimumSizes.concat(maximumSizes).some(size => !Number.isInteger(size) || size < 2 || size > 8)
      || minimumSizes.some((minimum, index) => minimum > maximumSizes[index])) {
    throw new Error('Minimum und Maximum müssen ganze Zahlen zwischen 2 und 8 sein; das Minimum darf nicht größer sein.');
  }
  const minimumTotal = minimumSizes.reduce((total, size) => total + size, 0);
  const maximumTotal = maximumSizes.reduce((total, size) => total + size, 0);
  if (minimumTotal > config.vikings.length || maximumTotal < config.vikings.length) {
    throw new Error('Die festen Gildengrößen passen nicht zur Anzahl der Wikinger.');
  }
  const names = config.vikings.map(viking => viking && typeof viking.name === 'string' ? viking.name.trim() : '');
  if (names.some(name => !vikingNamePattern.test(name)) || new Set(names).size !== names.length) {
    throw new Error('Wikingernamen müssen gültig und eindeutig sein.');
  }
  config.vikings.forEach(viking => {
    if (!Array.isArray(viking.ranking) || viking.ranking.length !== config.guilds.length) {
      throw new Error(`Die Rangliste von ${viking.name} ist unvollständig.`);
    }
    const explicit = viking.ranking.filter(value => value !== null);
    if (explicit.some(value => !Number.isInteger(value) || value < 0 || value >= config.guilds.length)
        || new Set(explicit).size !== explicit.length) throw new Error(`Die Rangliste von ${viking.name} ist ungültig.`);
  });
  return {
    version: 1,
    guilds: guildNames,
    guildMinimumSizes: minimumSizes,
    guildMaximumSizes: maximumSizes,
    vikings: config.vikings.map((viking, index) => ({...viking, name: names[index]}))
  };
}

function applyConfiguration(config) {
  guildsEl.replaceChildren(); vikingsEl.replaceChildren(); guildId = 0;
  config.guilds.forEach((name, index) => addGuild(name, config.guildMinimumSizes[index], config.guildMaximumSizes[index]));
  config.vikings.forEach(viking => addViking(viking.name, viking.ranking));
  resultEl.hidden = true;
}

async function apiRequest(url, options) {
  const requestOptions = {...(options || {})};
  if (requestOptions.method && requestOptions.method !== 'GET') {
    requestOptions.headers = {...(requestOptions.headers || {}), 'X-CSRF-Token': csrfToken};
  }
  const response = await fetch(url, requestOptions);
  const data = await response.json();
  if (response.status === 401) {
    window.location.replace('/login.html');
    throw new Error('Die Sitzung ist abgelaufen.');
  }
  if (!response.ok) throw new Error(data.error || 'Serveranfrage fehlgeschlagen.');
  return data;
}

const savedConfigsEl = document.querySelector('#saved-configs');
const configNameEl = document.querySelector('#config-name');

function showConfigStatus(message, isError = false) {
  configStatusEl.textContent = message;
  configStatusEl.classList.toggle('error', isError);
}

async function refreshSavedConfigurations(selected = '') {
  const data = await apiRequest('/api/configurations');
  savedConfigsEl.replaceChildren();
  if (!data.configurations.length) {
    const option = document.createElement('option'); option.textContent = 'Noch keine gespeichert'; option.value = '';
    savedConfigsEl.append(option);
  } else {
    data.configurations.forEach(name => {
      const option = document.createElement('option'); option.value = name; option.textContent = name; savedConfigsEl.append(option);
    });
    if (data.configurations.includes(selected)) savedConfigsEl.value = selected;
  }
  const disabled = !data.configurations.length;
  document.querySelector('#load-config').disabled = disabled;
  document.querySelector('#delete-config').disabled = disabled;
}

document.querySelector('#save-config').addEventListener('click', async () => {
  showConfigStatus('');
  const repaired = [...document.querySelectorAll('.viking')].filter(repairRanking);
  if (repaired.length) {
    showConfigStatus('Doppelte Wünsche wurden korrigiert. Bitte prüfen und erneut speichern.', true);
    return;
  }
  const button = document.querySelector('#save-config');
  button.disabled = true;
  try {
    const config = validateConfiguration(currentConfiguration());
    const name = configNameEl.value.trim();
    if (!/^[A-Za-zÄÖÜäöüß0-9_.-]{1,50}$/.test(name)) throw new Error('Bitte einen gültigen Konfigurationsnamen eingeben.');
    const existing = [...savedConfigsEl.options].some(option => option.value === name);
    if (existing && !window.confirm(`${name} wirklich überschreiben?`)) return;
    await apiRequest('/api/configurations/save', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name, configuration: config})
    });
    await refreshSavedConfigurations(name);
    showConfigStatus(`Konfiguration „${name}“ wurde auf dem Raspberry Pi gespeichert.`);
  } catch (error) { showConfigStatus(error.message, true); }
  finally { button.disabled = false; }
});

document.querySelector('#load-config').addEventListener('click', async () => {
  showConfigStatus('');
  try {
    const name = savedConfigsEl.value;
    const config = validateConfiguration(await apiRequest(`/api/configurations/load?name=${encodeURIComponent(name)}`));
    applyConfiguration(config); configNameEl.value = name;
    showConfigStatus(`Konfiguration „${name}“ wurde geladen.`);
  } catch (error) { showConfigStatus(`Konfiguration konnte nicht geladen werden: ${error.message}`, true); }
});

document.querySelector('#delete-config').addEventListener('click', async () => {
  const name = savedConfigsEl.value;
  if (!name || !window.confirm(`Konfiguration „${name}“ wirklich dauerhaft löschen?`)) return;
  showConfigStatus('');
  try {
    await apiRequest('/api/configurations/delete', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name})
    });
    await refreshSavedConfigurations();
    showConfigStatus(`Konfiguration „${name}“ wurde gelöscht.`);
  } catch (error) { showConfigStatus(error.message, true); }
});

document.querySelector('#logout').addEventListener('click', async () => {
  try {
    await apiRequest('/api/logout', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
    });
  } finally {
    window.location.replace('/login.html');
  }
});

document.querySelector('#add-viking').addEventListener('click', () => addViking());
document.querySelector('#calculate').addEventListener('click', async () => {
  errorEl.textContent = ''; resultEl.hidden = true;
  const button = document.querySelector('#calculate'); button.disabled = true; button.textContent = 'Runen werden befragt …';
  try {
    const repaired = [...document.querySelectorAll('.viking')].filter(repairRanking);
    if (repaired.length) {
      const names = repaired.map(row => row.querySelector('.viking-name').value.trim() || 'Unbenannt').join(', ');
      throw new Error(`Doppelte Wünsche wurden bei ${names} korrigiert. Bitte Rangliste prüfen und erneut auslosen.`);
    }
    const payload = {
      guilds: [...guildsEl.querySelectorAll('.guild-name')].map(input => input.value.trim()),
      guildMinimumSizes: [...guildsEl.querySelectorAll('.guild-minimum')].map(input => input.value === '' ? null : Number(input.value)),
      guildMaximumSizes: [...guildsEl.querySelectorAll('.guild-maximum')].map(input => input.value === '' ? null : Number(input.value)),
      vikings: [...document.querySelectorAll('.viking')].map(row => ({
        name: row.querySelector('.viking-name').value.trim(),
        ranking: rankingValues(row)
      }))
    };
    const data = await apiRequest('/api/optimize', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    renderResult(data);
  } catch (error) { errorEl.textContent = error.message; }
  finally { button.disabled = false; button.textContent = 'Optimale Verteilung auslosen'; }
});

function renderResult(data) {
  resultEl.replaceChildren();
  const heading = document.createElement('h2'); heading.textContent = 'Optimale Verteilung';
  const summary = document.createElement('p'); summary.className = 'summary';
  summary.textContent = `${data.score} von ${data.maximumScore} Wunschpunkten · zufällig ausgewählt aus ${data.optimalSolutionCount} gleich guten Lösung${data.optimalSolutionCount === 1 ? '' : 'en'}`;
  const grid = document.createElement('div'); grid.className = 'group-grid';
  data.groups.forEach(group => {
    const card = document.createElement('article'); card.className = 'group';
    const title = document.createElement('h3'); title.textContent = `${group.name} (${group.members.length})`;
    const list = document.createElement('ul');
    group.members.forEach(member => { const item = document.createElement('li'); item.textContent = member.name; const rank = document.createElement('small'); rank.textContent = member.equal ? ` · ${member.rank}. Wunsch (egal)` : ` · ${member.rank}. Wunsch`; item.append(rank); list.append(item); });
    card.append(title, list); grid.append(card);
  });
  resultEl.append(heading, summary, grid); resultEl.hidden = false; resultEl.scrollIntoView({behavior:'smooth'});
}

['Bauern', 'Holzfäller', 'Köche', 'Jäger', 'Schmelzer', 'Steinmetze'].forEach(name => addGuild(name));

async function initialize() {
  const session = await apiRequest('/api/session');
  csrfToken = session.csrfToken;
  session.defaultVikings.forEach(name => addViking(name));
  await refreshSavedConfigurations();
}

initialize().catch(error => { showConfigStatus(`Initialisierung fehlgeschlagen: ${error.message}`, true); });
