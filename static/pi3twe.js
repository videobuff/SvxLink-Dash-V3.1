'use strict';
const csrf = document.querySelector('meta[name="pi3twe-csrf"]').content;
const message = document.getElementById('operation-message');
let latestState, formsLoaded = false;
function notify(text, error = false) { message.textContent = text; message.classList.toggle('error', error); }
async function api(path, method = 'GET', data) {
    const options = {method, headers: {'X-CSRF-Token': csrf}};
    if (data instanceof FormData) options.body = data;
    else if (data !== undefined) { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(data); }
    const response = await fetch(`/pi3twe/api/${path}`, options);
    if (response.redirected || !response.headers.get('content-type')?.includes('application/json')) throw new Error('Log opnieuw in op SvxDash of ververs de pagina.');
    const body = await response.json();
    if (!response.ok || !body.ok) throw new Error(body.error || `Opdracht mislukt (${response.status})`);
    return body;
}
function fill(form, values) {
    for (const [name, value] of Object.entries(values)) {
        const input = form.elements.namedItem(name);
        if (!input) continue;
        if (input.type === 'checkbox') input.checked = !!value;
        else input.value = value ?? '';
    }
}
function badge(id, text, on) { const el = document.getElementById(id); el.textContent = text; el.className = `pi3twe-badge ${on ? 'on' : 'off'}`; }
async function refresh() {
    try {
        const state = await api('state'); latestState = state;
        const power = state.radio.repeater_on;
        badge('power-state', power ? 'AAN' : 'UIT', power);
        badge('mode-state', state.mode.mode.toUpperCase(), state.mode.mode === 'aan');
        badge('news-state', state.logic.settings.news_enabled ? 'Toegestaan' : 'Geblokkeerd', state.logic.settings.news_enabled);
        document.getElementById('relay-health').textContent = state.radio.hardware.relays.message || 'Relaisbewaking actief';
        document.getElementById('engine-state').textContent = `Service: ${state.mode.engine.service_state} · Audio-engine: ${state.mode.engine.native_ready ? 'gereed' : 'niet gereed'}`;
        document.getElementById('current-news').textContent = state.current_news ? `Uitzending: ${state.current_news} (${state.logic.phase})` : 'Geen nieuwsuitzending actief.';
        document.getElementById('audio-info').textContent = state.audio.error || `Audio-uitgang: ${state.audio.output_mode === 'transmit' ? 'zendmodus' : 'analoge monitor'}`;
        document.getElementById('system-state').textContent = `Host ${state.radio.hostname} · uptime ${Math.floor(state.radio.uptime_s / 3600)} uur`;
        if (!formsLoaded) {
            fill(document.getElementById('logic-form'), state.logic.settings);
            fill(document.getElementById('audio-form'), state.audio);
            formsLoaded = true;
        }
        const radioReady = power && state.mode.mode === 'aan' && state.mode.engine.native_ready;
        document.getElementById('test-call').disabled = state.news_busy || !radioReady || !state.mode.engine.call_test_available;
        document.getElementById('test-news').disabled = state.news_busy || !radioReady || !state.logic.settings.news_enabled || !document.getElementById('news-test-select').value;
        for (const button of document.querySelectorAll('.news-play')) button.disabled = state.news_busy || !power || state.mode.mode !== 'aan' || !state.logic.settings.news_enabled;
    } catch (error) { notify(error.message, true); }
}
async function action(button, path, method, data, success, reloadNews = false) {
    if (button) button.disabled = true;
    try { await api(path, method, data); notify(success); if (reloadNews) await loadNews(); await refresh(); return true; }
    catch (error) { notify(error.message, true); return false; }
    finally { if (button) button.disabled = false; if (latestState) updateTestButtons(); }
}
for (const button of document.querySelectorAll('[data-api]')) button.addEventListener('click', () => action(button, button.dataset.api, 'POST', undefined, button.dataset.success));
function updateTestButtons() {
    if (!latestState) return;
    const ready = latestState.radio.repeater_on && latestState.mode.mode === 'aan' && latestState.mode.engine.native_ready;
    document.getElementById('test-call').disabled = latestState.news_busy || !ready || !latestState.mode.engine.call_test_available;
    document.getElementById('test-news').disabled = latestState.news_busy || !ready || !latestState.logic.settings.news_enabled || !document.getElementById('news-test-select').value;
    for (const button of document.querySelectorAll('.news-play')) button.disabled = latestState.news_busy || !ready || !latestState.logic.settings.news_enabled;
}
const newsTest = document.getElementById('news-test-form');
newsTest.addEventListener('submit', event => { event.preventDefault(); const id = document.getElementById('news-test-select').value; if (id) action(document.getElementById('test-news'), `news/${id}/play`, 'POST', undefined, 'Test nieuws gestart'); });
document.getElementById('news-test-select').addEventListener('change', updateTestButtons);
async function loadNews() {
    const body = await api('news');
    const select = document.getElementById('news-test-select'); const selected = select.value;
    select.replaceChildren();
    if (!body.items.length) { const option = document.createElement('option'); option.value = ''; option.textContent = 'Lees eerst een bulletin in'; select.append(option); }
    for (const item of body.items) { const option = document.createElement('option'); option.value = String(item.id); option.textContent = `${item.label} — ${item.original_filename}`; select.append(option); }
    if (body.items.some(item => String(item.id) === selected)) select.value = selected;
    updateTestButtons();
    const list = document.getElementById('news-list'); list.replaceChildren();
    if (!body.items.length) { const p = document.createElement('p'); p.textContent = 'Nog geen bulletins ingelezen.'; list.append(p); }
    for (const item of body.items) {
        const article = document.getElementById('news-template').content.firstElementChild.cloneNode(true);
        article.querySelector('h3').textContent = item.label;
        article.querySelector('.news-file').textContent = item.original_filename;
        article.querySelector('audio').src = `/pi3twe/api/news/${item.id}/audio`;
        const form = article.querySelector('form');
        fill(form, {valid_from: item.valid_from_input, valid_until: item.valid_until_input, enabled: item.enabled});
        article.querySelector('.news-period').textContent = `${item.enabled ? 'Actief' : 'Niet actief'} · ${item.within_period ? 'binnen' : 'buiten'} geldigheidsperiode`;
        form.addEventListener('submit', event => { event.preventDefault(); action(form.querySelector('button'), `news/${item.id}`, 'PUT', {valid_from: form.valid_from.value, valid_until: form.valid_until.value, enabled: form.enabled.checked}, 'Bulletin opgeslagen', true); });
        const play = article.querySelector('.news-play'); play.addEventListener('click', () => action(play, `news/${item.id}/play`, 'POST', undefined, 'Nieuwsuitzending gestart'));
        const remove = article.querySelector('.news-delete'); remove.addEventListener('click', () => { if (confirm(`${item.label} verwijderen?`)) action(remove, `news/${item.id}`, 'DELETE', undefined, 'Bulletin verwijderd', true); });
        list.append(article);
    }
    if (latestState) for (const button of list.querySelectorAll('.news-play')) button.disabled = latestState.news_busy || !latestState.radio.repeater_on || latestState.mode.mode !== 'aan' || !latestState.logic.settings.news_enabled;
}
const upload = document.getElementById('news-upload');
upload.addEventListener('submit', async event => { event.preventDefault(); if (await action(upload.querySelector('button'), 'news', 'POST', new FormData(upload), 'Bulletin ingelezen. Activeer het voor de uurplanning.', true)) upload.audio.value = ''; });
for (const name of ['logic', 'audio']) {
    const form = document.getElementById(`${name}-form`);
    form.addEventListener('submit', event => {
        event.preventDefault(); const data = {};
        for (const input of form.querySelectorAll('[name]')) data[input.name] = input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value) : input.value;
        action(form.querySelector('button'), name, 'PUT', data, 'Instellingen opgeslagen');
    });
}
function localInput(date) { const parts = Object.fromEntries(new Intl.DateTimeFormat('sv-SE', {timeZone: 'Europe/Amsterdam', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'}).formatToParts(date).map(part => [part.type, part.value])); return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`; }
upload.valid_from.value = localInput(new Date()); upload.valid_until.value = localInput(new Date(Date.now() + 7 * 86400000));
refresh().then(() => loadNews()).catch(error => notify(error.message, true));
setInterval(refresh, 5000);
