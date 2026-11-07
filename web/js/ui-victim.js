/* HEIMDALL victim screen.
 * Public hook API (used by mock.js now, victim-logic.js later):
 *   getSettings(), onStart(fn), onStop(fn), onSettingsChange(fn), onCancelFall(fn),
 *   setBeacon(state), setMicLevel(0..1), setMotion(bool), logHeard(frame), logRelayed(frame),
 *   showKnock(bool), showFallCountdown(seconds|null), showError(msg)
 */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const STORE_KEY = 'heimdall.victim.v1';
  const STATUS_WORD = { no_response: 'no response', ok: 'ok', injured: 'injured', critical: 'critical' };
  const FLOOR_MIN = -1, FLOOR_MAX = 29; // SPEC 1.3
  const LOG_MAX = 50;

  const fns = { start: [], stop: [], change: [], cancelFall: [] };
  const call = (list, arg) => list.forEach((fn) => { try { fn(arg); } catch (e) { console.error('[HEIMDALL] handler failed', e); } });

  function randomId() {
    const a = new Uint8Array(2);
    (window.crypto || window.msCrypto).getRandomValues(a);
    return ((a[0] << 8) | a[1]).toString(16).toUpperCase().padStart(4, '0');
  }
  const validId = (s) => typeof s === 'string' && /^[0-9A-F]{4}$/.test(s);

  // ---------- settings (kept in localStorage) ----------
  const defaults = { id: null, floor: null, people: 1, status: 'no_response', relay: true, autoFall: false, demoFast: true };
  let settings = Object.assign({}, defaults);
  try {
    const saved = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
    settings = Object.assign(settings, saved);
  } catch (e) { /* private mode or blocked storage: run with defaults */ }
  if (!validId(settings.id)) settings.id = randomId();
  if (!(settings.status in STATUS_WORD)) settings.status = 'no_response';
  settings.people = Math.max(0, Math.min(7, Math.round(Number(settings.people)) || 0));
  if (settings.floor !== null) settings.floor = Math.max(FLOOR_MIN, Math.min(FLOOR_MAX, Math.round(Number(settings.floor)) || 0));
  save();

  function save() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(settings)); } catch (e) { /* ignore */ }
  }
  function getSettings() {
    return { id: settings.id, floor: settings.floor, people: settings.people, status: settings.status,
      relay: !!settings.relay, autoFall: !!settings.autoFall, demoFast: !!settings.demoFast };
  }
  function changed() { save(); render(); call(fns.change, getSettings()); }

  // ---------- render settings ----------
  function render() {
    $('my-id').textContent = settings.id;
    document.querySelectorAll('.stbtn').forEach((b) => {
      const on = b.dataset.s === settings.status;
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', String(on));
    });
    $('people-val').textContent = settings.people >= 7 ? '7+' : settings.people;
    $('floor-val').textContent = settings.floor === null ? '?' : settings.floor;
    $('floor-unk').classList.toggle('on', settings.floor === null);
    $('set-relay').checked = !!settings.relay;
    $('set-fall').checked = !!settings.autoFall;
    $('set-demo').checked = !!settings.demoFast;
    if (document.activeElement !== $('set-id')) $('set-id').value = settings.id;
  }

  document.querySelectorAll('.stbtn').forEach((b) => b.addEventListener('click', () => {
    // tapping the selected status again clears it (back to "no response")
    settings.status = settings.status === b.dataset.s ? 'no_response' : b.dataset.s;
    changed();
  }));
  $('people-minus').addEventListener('click', () => { if (settings.people > 0) { settings.people--; changed(); } });
  $('people-plus').addEventListener('click', () => { if (settings.people < 7) { settings.people++; changed(); } });
  $('floor-minus').addEventListener('click', () => {
    settings.floor = settings.floor === null ? 0 : Math.max(FLOOR_MIN, settings.floor - 1); changed();
  });
  $('floor-plus').addEventListener('click', () => {
    settings.floor = settings.floor === null ? 1 : Math.min(FLOOR_MAX, settings.floor + 1); changed();
  });
  $('floor-unk').addEventListener('click', () => { settings.floor = null; changed(); });
  $('set-relay').addEventListener('change', (e) => { settings.relay = e.target.checked; changed(); });
  $('set-fall').addEventListener('change', (e) => { settings.autoFall = e.target.checked; changed(); });
  $('set-demo').addEventListener('change', (e) => { settings.demoFast = e.target.checked; changed(); });
  function saveId() {
    const v = $('set-id').value.trim().toUpperCase();
    if (!validId(v)) { showError('Beacon ID must be 4 characters: 0-9 and A-F.'); return; }
    showError(null);
    settings.id = v;
    $('set-id').blur();
    changed();
  }
  $('set-id-save').addEventListener('click', saveId);
  $('set-id').addEventListener('keydown', (e) => { if (e.key === 'Enter') saveId(); });

  // ---------- SOS button ----------
  let active = false;
  function setActiveUI(on) {
    active = on;
    $('sos-wrap').classList.toggle('active', on);
    $('sos').setAttribute('aria-pressed', String(on));
    $('sos').innerHTML = on ? 'SOS ACTIVE<small>tap to stop</small>' : 'SEND SOS';
    if (!on) $('beacon-line').innerHTML = '<span class="beacon-idle">Tap the button to call for help</span>';
  }
  $('sos').addEventListener('click', () => {
    // fn() is called synchronously here: browsers only allow sound + mic from a direct tap.
    if (!active) { setActiveUI(true); $('beacon-line').textContent = 'Starting beacon…'; call(fns.start); }
    else { setActiveUI(false); call(fns.stop); }
  });

  function setBeacon(s) {
    s = s || {};
    if (!s.on) { if (active) setActiveUI(false); return; }
    if (!active) setActiveUI(true);
    const parts = [];
    if (s.band !== undefined && s.band !== null) parts.push('Chirping on band <b>' + Number(s.band) + '</b>');
    if (s.nextInSec !== undefined && s.nextInSec !== null) parts.push('next in <b>' + Math.max(0, Math.round(s.nextInSec)) + ' s</b>');
    if (s.sent !== undefined && s.sent !== null) parts.push('<b>' + Number(s.sent) + '</b> sent');
    if (s.trigger === 'fall') parts.push('started by fall');
    $('beacon-line').innerHTML = parts.join(' · ') || 'Beacon on';
  }

  // ---------- small indicators ----------
  function setMicLevel(level) {
    const v = Math.max(0, Math.min(1, Number(level) || 0));
    $('mic-meter').style.width = (v * 100).toFixed(1) + '%';
  }
  function setMotion(moving) {
    $('motion-line').textContent = 'Motion: ' + (moving ? 'phone is moving' : 'phone is still');
  }

  // ---------- relay log ----------
  let logCount = 0;
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function timeStr(ts) {
    const d = ts ? new Date(ts > 1e12 ? ts : ts * 1000) : new Date(); // accepts seconds or ms
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }
  function addLog(html, ts) {
    const li = document.createElement('li');
    li.innerHTML = '<time>' + timeStr(ts) + '</time><span>' + html + '</span>';
    const log = $('log');
    log.insertBefore(li, log.firstChild);
    while (log.children.length > LOG_MAX) log.removeChild(log.lastChild);
    logCount++;
    $('log-count').textContent = '(' + logCount + ')';
    $('log-empty').classList.add('hidden');
  }
  function logHeard(f) {
    f = f || {};
    const n = Number(f.people);
    const ppl = Number.isFinite(n) ? (n >= 7 ? '7+' : n) + ' ' + (n === 1 ? 'person' : 'people') : null;
    const bits = [STATUS_WORD[f.status] || f.status || 'unknown', ppl].filter(Boolean).join(', ');
    addLog('Heard <b>' + esc(f.id || '????') + '</b> (' + esc(bits) + ')', f.ts);
  }
  function logRelayed(f) {
    f = f || {};
    addLog('<span class="relay">Passed on <b>' + esc(f.id || '????') + '</b> &rarr; hop ' + esc(f.hops ?? '?') + '</span>', f.ts);
  }

  // ---------- banners ----------
  function showKnock(on) { $('knock-banner').classList.toggle('hidden', !on); }
  function showFallCountdown(s) {
    const show = s !== null && s !== undefined;
    $('fall-overlay').classList.toggle('hidden', !show);
    if (show) { $('fall-sec').textContent = Math.max(0, Math.round(s)); $('fall-cancel').focus(); }
  }
  $('fall-cancel').addEventListener('click', () => { showFallCountdown(null); call(fns.cancelFall); });
  function showError(msg) {
    const el = $('err');
    el.textContent = msg || '';
    el.classList.toggle('hidden', !msg);
  }

  render();
  setActiveUI(false);

  window.HeimdallVictim = {
    getSettings,
    onStart(fn) { if (typeof fn === 'function') fns.start.push(fn); },
    onStop(fn) { if (typeof fn === 'function') fns.stop.push(fn); },
    onSettingsChange(fn) { if (typeof fn === 'function') fns.change.push(fn); },
    onCancelFall(fn) { if (typeof fn === 'function') fns.cancelFall.push(fn); },
    setBeacon, setMicLevel, setMotion, logHeard, logRelayed, showKnock, showFallCountdown, showError,
  };
})();
