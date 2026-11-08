/* HEIMDALL operator screen.
 * Public hook API (used by mock.js now, operator-live.js later):
 *   HeimdallOperator.handleEvent(evt)   every station event goes through here
 *   HeimdallOperator.setConnection(s)   "connecting" | "live" | "lost" | "mock"
 *   HeimdallOperator.setThermalSource(src)  "mock" or an image/MJPEG URL
 *   HeimdallOperator.onCommand(fn)      fn(cmd) for pantilt_cmd / pantilt_mode
 */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const SVGNS = 'http://www.w3.org/2000/svg';
  const STATUS_RANK = { critical: 0, injured: 1, no_response: 2, ok: 3 };
  const STATUS_LABEL = { critical: 'Critical', injured: 'Injured', no_response: 'No response', ok: 'OK' };
  const STOP_WINDOW_MS = 2 * 60 * 1000;
  const UNCONF_HIDE_MS = 60 * 1000;
  const THERMAL_FOV = 55; // degrees, mock only

  const state = {
    victims: new Map(),   // id -> { v: lastVictimEvent, heardAt, stoppedAt, prevMotion }
    bearings: [],         // recent bearing events with local receive time `_at`
    selected: null,       // victim id chosen by the user (null = follow latest signal)
    pantilt: { pan: 0, tilt: 0, mode: 'auto' },
    thermal: null,        // last thermal_det
    knockAt: null,
    cmdFns: [],
    aimDragging: false,
  };

  // ---------- helpers ----------
  const fmt = (n, d = 0) => (n === null || n === undefined || Number.isNaN(n) ? '—' : Number(n).toFixed(d));
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const normDeg = (d) => { let x = ((Number(d) + 180) % 360 + 360) % 360 - 180; return x === -180 ? 180 : x; };
  function ago(ms) {
    if (ms === null || ms === undefined) return '—';
    const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
    if (s < 60) return s + ' s ago';
    const m = Math.floor(s / 60);
    return m < 60 ? m + ' min ago' : Math.floor(m / 60) + ' h ago';
  }
  function sideDeg(deg) {
    if (deg === null || deg === undefined) return '—';
    const d = Math.round(normDeg(deg));
    if (d === 0) return '0°';
    return (d > 0 ? 'R ' : 'L ') + Math.abs(d) + '°';
  }
  function emit(cmd) {
    for (const fn of state.cmdFns) {
      try { fn(cmd); } catch (e) { console.error('[HEIMDALL] command handler failed', e); }
    }
  }

  // ---------- top bar ----------
  function setConnection(s) {
    const el = $('conn');
    const ok = ['connecting', 'live', 'lost', 'mock'].includes(s) ? s : 'connecting';
    el.className = 'pill ' + ok;
    el.textContent = ok;
  }

  const POINTS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  function onHeading(e) {
    const yaw = ((Number(e.yaw_deg) % 360) + 360) % 360;
    $('compass-text').textContent = Math.round(yaw) + '° ' + POINTS[Math.round(yaw / 45) % 8];
    $('compass-needle').setAttribute('transform', 'rotate(' + (-yaw) + ')'); // needle points to north
  }

  function onDrone(e) {
    const note = e.note || e.link || '—';
    const el = $('drone');
    el.innerHTML = 'Drone: <b>' + esc(note) + '</b>';
    el.style.color = e.link && e.link !== 'ok' ? 'var(--critical)' : '';
  }

  function onHealth(e) {
    const mods = e.modules || {};
    $('health').innerHTML = Object.keys(mods).map((k) => {
      const v = mods[k] === 'ok' ? 'ok' : mods[k] === 'error' ? 'error' : 'off';
      return '<span class="hdot ' + v + '" title="' + esc(k) + ': ' + esc(mods[k]) + '"><i></i>' + esc(k) + '</span>';
    }).join('');
  }

  function setModeUI(mode) {
    const manual = mode === 'manual';
    $('mode-auto').classList.toggle('on', !manual);
    $('mode-manual').classList.toggle('on', manual);
    $('mode-auto').setAttribute('aria-pressed', String(!manual));
    $('mode-manual').setAttribute('aria-pressed', String(manual));
    $('aim').classList.toggle('hidden', !manual);
  }

  // ---------- pan / tilt ----------
  function onPantilt(e) {
    state.pantilt = { pan: Number(e.pan) || 0, tilt: Number(e.tilt) || 0, mode: e.mode || state.pantilt.mode };
    setModeUI(state.pantilt.mode);
    $('thermal-pt').textContent = 'pan ' + fmt(state.pantilt.pan) + '° · tilt ' + fmt(state.pantilt.tilt) + '°';
    $('cam-big').textContent = state.pantilt.mode.toUpperCase();
    $('cam-line').innerHTML = 'pan <b>' + sideDeg(state.pantilt.pan) + '</b> · tilt <b>' + fmt(state.pantilt.tilt) + '°</b>';
    $('dial-cam').setAttribute('transform', 'rotate(' + normDeg(state.pantilt.pan) + ')');
    if (!state.aimDragging) {
      $('aim-pan').value = Math.round(state.pantilt.pan);
      $('aim-tilt').value = Math.round(state.pantilt.tilt);
      $('aim-pan-v').textContent = Math.round(state.pantilt.pan) + '°';
      $('aim-tilt-v').textContent = Math.round(state.pantilt.tilt) + '°';
    }
  }

  // ---------- dial ----------
  (function buildTicks() {
    const g = $('dial-ticks');
    for (let a = 0; a < 360; a += 15) {
      const major = a % 90 === 0;
      const l = document.createElementNS(SVGNS, 'line');
      l.setAttribute('x1', 0); l.setAttribute('x2', 0);
      l.setAttribute('y1', -96); l.setAttribute('y2', major ? -86 : -91);
      l.setAttribute('stroke', major ? '#8a96a3' : '#3a4654');
      l.setAttribute('stroke-width', major ? 2 : 1);
      l.setAttribute('transform', 'rotate(' + a + ')');
      g.appendChild(l);
    }
  })();

  // Which signal does the dial point at? The selected victim, or else the newest bearing.
  function currentTarget() {
    if (state.selected && state.victims.has(state.selected)) {
      const rec = state.victims.get(state.selected);
      const b = [...state.bearings].reverse().find((x) => x.id === state.selected);
      const useB = b && b._at >= rec.heardAt;
      return {
        key: state.selected,
        id: state.selected,
        deg: useB ? b.deg : rec.v.deg,
        conf: useB ? b.conf : 0.7,
        band: useB ? b.band : rec.v.band,
        snr: useB ? b.snr_db : rec.v.snr_db,
        src: 'tag',
        hops: rec.v.hops || 0,
        at: useB ? b._at : rec.heardAt,
      };
    }
    // Auto mode never picks an unconfirmed beacon (SPEC v1.1): skip bearings from those ids.
    const b = [...state.bearings].reverse().find((x) => !x.id || !state.victims.has(x.id) || state.victims.get(x.id).confirmed);
    if (!b) return null;
    const rec = b.id ? state.victims.get(b.id) : null;
    return {
      key: b.id || b.src, id: b.id, deg: b.deg, conf: b.conf, band: b.band, snr: b.snr_db,
      src: b.src, hops: rec ? rec.v.hops || 0 : 0, at: b._at,
    };
  }

  function renderDial() {
    const t = currentTarget();
    const arrow = $('dial-arrow');
    const hist = $('dial-hist');
    hist.innerHTML = '';
    if (t && (t.deg === null || t.deg === undefined)) {
      // selected victim the station only knows from a phone's report (SPEC v1.1: deg null)
      arrow.setAttribute('opacity', 0);
      $('instr').className = 'instr idle';
      $('instr').textContent = 'NO DIRECTION FIX';
      $('instr-sub').textContent = 'reported by a phone · ' + ago(t.at);
      $('instr-note').className = 'instr-note relay';
      $('instr-note').textContent = 'Search near the phone that relayed it';
      $('target-name').innerHTML = 'Selected · Beacon <b>' + esc(t.id) + '</b>';
      return;
    }
    if (!t) {
      arrow.setAttribute('opacity', 0);
      $('instr').className = 'instr idle';
      $('instr').textContent = 'WAITING';
      $('instr-sub').innerHTML = '&nbsp;';
      $('instr-note').textContent = '';
      $('target-name').textContent = 'No signal yet';
      return;
    }
    const deg = normDeg(t.deg);
    const ageS = (Date.now() - t.at) / 1000;
    const stale = ageS > 30;
    const conf = Math.max(0, Math.min(1, Number(t.conf) || 0));
    arrow.setAttribute('transform', 'rotate(' + deg + ')');
    arrow.setAttribute('opacity', (0.25 + 0.75 * conf) * (stale ? 0.4 : 1));

    // last 10 bearings of the same target, as faded dots
    const same = state.bearings.filter((b) => (b.id || b.src) === t.key).slice(-10);
    same.forEach((b, i) => {
      const c = document.createElementNS(SVGNS, 'circle');
      c.setAttribute('cx', 0); c.setAttribute('cy', -80); c.setAttribute('r', 3.5);
      c.setAttribute('fill', '#ffb020');
      c.setAttribute('opacity', (0.12 + 0.5 * (i + 1) / same.length).toFixed(2));
      c.setAttribute('transform', 'rotate(' + normDeg(b.deg) + ')');
      hist.appendChild(c);
    });

    const a = Math.abs(deg);
    let text;
    if (a < 10) text = 'AHEAD';
    else if (a > 150) text = 'TURN AROUND';
    else text = (deg > 0 ? 'TURN RIGHT ' : 'TURN LEFT ') + Math.round(a) + '°';
    $('instr').className = 'instr';
    $('instr').textContent = text;

    const parts = [];
    if (t.snr !== null && t.snr !== undefined) parts.push('signal ' + fmt(t.snr) + ' dB');
    if (t.band !== null && t.band !== undefined) parts.push('band ' + t.band);
    parts.push('conf ' + Math.round(conf * 100) + '%');
    parts.push(stale ? 'last ' + ago(t.at) : ago(t.at));
    $('instr-sub').textContent = parts.join(' · ');

    const note = $('instr-note');
    if (t.src === 'sound') { note.className = 'instr-note muted'; note.textContent = 'Unknown human sound'; }
    else if (t.src === 'scan') { note.className = 'instr-note muted'; note.textContent = 'Head-scan result'; }
    else if (t.hops > 0) { note.className = 'instr-note relay'; note.textContent = 'via relay: direction points to the relaying phone'; }
    else { note.className = 'instr-note'; note.textContent = ''; }

    const who = t.id ? 'Beacon <b>' + esc(t.id) + '</b>' : t.src === 'sound' ? 'Unknown sound' : 'Scan';
    $('target-name').innerHTML = (state.selected ? 'Selected · ' : 'Latest signal · ') + who;
  }

  function onBearing(e) {
    if (e.deg === null || e.deg === undefined) return;
    state.bearings.push(Object.assign({}, e, { _at: Date.now() }));
    if (state.bearings.length > 60) state.bearings.splice(0, state.bearings.length - 60);
    renderDial();
  }

  // ---------- triage ----------
  function onVictim(e) {
    if (!e.id) return;
    const now = Date.now();
    let rec = state.victims.get(e.id);
    if (!rec) { rec = { v: e, heardAt: now, stoppedAt: null }; state.victims.set(e.id, rec); }
    const wasMoving = rec.v.motion;
    if (wasMoving === true && e.motion === false) rec.stoppedAt = now;
    if (e.motion === true) rec.stoppedAt = null;
    rec.v = e;
    rec.heardAt = now;
    rec.confirmed = e.confirmed !== false; // SPEC v1.1: missing counts as confirmed
    renderQueue();
    renderDial();
  }

  // Unconfirmed beacons disappear 60 s after their last event (SPEC v1.1).
  const isVisible = (rec, now) => rec.confirmed || now - rec.heardAt <= UNCONF_HIDE_MS;

  function sortedVictims() {
    const now = Date.now();
    if (state.selected && state.victims.has(state.selected) && !isVisible(state.victims.get(state.selected), now)) state.selected = null;
    return [...state.victims.values()].filter((r) => isVisible(r, now)).sort((a, b) => {
      if (a.confirmed !== b.confirmed) return a.confirmed ? -1 : 1; // unconfirmed below every confirmed card
      const ra = STATUS_RANK[a.v.status] ?? 2, rb = STATUS_RANK[b.v.status] ?? 2;
      if (ra !== rb) return ra - rb;
      const ma = a.v.motion ? 1 : 0, mb = b.v.motion ? 1 : 0; // not moving first
      if (ma !== mb) return ma - mb;
      return (Number(b.v.minutes) || 0) - (Number(a.v.minutes) || 0);
    });
  }

  const MOVE_ICON = '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M1 7h3l2-4 2 8 2-4h3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>';
  const STILL_ICON = '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M1 7h12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';

  function batteryHTML(q) {
    const n = Math.max(0, Math.min(3, Number(q) || 0));
    let h = '<span class="battery' + (n <= 1 ? ' low' : '') + '" title="battery ' + n + '/3">';
    for (let i = 0; i < 3; i++) h += '<i class="' + (i < n ? 'f' : '') + '"></i>';
    return h + '</span>';
  }

  function renderQueue() {
    const list = sortedVictims();
    $('queue-count').textContent = list.length ? '(' + list.length + ')' : '';
    if (!list.length) { $('queue').innerHTML = '<div class="queue-empty">No victims heard yet.</div>'; return; }
    const now = Date.now();
    $('queue').innerHTML = list.map(({ v, heardAt, stoppedAt, confirmed }) => {
      const status = STATUS_RANK[v.status] !== undefined ? v.status : 'no_response';
      const stopped = stoppedAt && !v.motion && now - stoppedAt < STOP_WINDOW_MS;
      const people = Number(v.people) >= 7 ? '7+' : fmt(v.people);
      const floor = v.floor === null || v.floor === undefined ? 'floor ?' : 'floor ' + v.floor;
      const hops = Number(v.hops) || 0;
      const noFix = v.deg === null || v.deg === undefined;
      return '<button type="button" class="vcard bl-' + status + (stopped ? ' stopped' : '') + (confirmed ? '' : ' unconf') + (state.selected === v.id ? ' sel' : '') + '" data-id="' + esc(v.id) + '">' +
        '<div class="vrow"><span class="vid">' + esc(v.id) + '</span>' +
          '<span class="chip s-' + status + '">' + STATUS_LABEL[status] + '</span>' +
          (confirmed ? '' : '<span class="badge unconf">Unconfirmed</span>') +
          (stopped ? '<span class="badge stop">Stopped moving</span>' : '') +
          '<span class="vbear">' + (noFix ? '' : sideDeg(v.deg)) + '</span></div>' +
        (noFix ? '<div class="vrow vmeta nofix">direction: no fix (reported by a phone)</div>' : '') +
        '<div class="vrow vmeta"><span><b>' + people + '</b> ' + (people === '1' ? 'person' : 'people') + '</span><span>' + floor + '</span>' +
          '<span><b>' + fmt(v.minutes) + '</b> min since SOS</span>' +
          '<span class="moveicon" style="color:' + (v.motion ? 'var(--ok)' : 'var(--muted)') + '">' + (v.motion ? MOVE_ICON + 'moving' : STILL_ICON + 'still') + '</span>' +
          batteryHTML(v.battery) + '</div>' +
        '<div class="vrow vmeta">' +
          (hops > 0 ? '<span class="badge relay">via ' + hops + ' relay' + (hops > 1 ? 's' : '') + '</span>' : '') +
          (v.knock ? '<span class="badge knock">heard knock</span>' : '') +
          '<span>last heard ' + ago(heardAt) + '</span></div>' +
        '</button>';
    }).join('');
  }

  $('queue').addEventListener('click', (ev) => {
    const card = ev.target.closest('.vcard');
    if (!card) return;
    const id = card.dataset.id;
    if (state.selected === id) { state.selected = null; renderQueue(); renderDial(); return; }
    state.selected = id;
    renderQueue();
    renderDial();
    const rec = state.victims.get(id);
    if (!rec || rec.v.deg === null || rec.v.deg === undefined) return; // no direction fix: select only, don't aim
    const t = currentTarget();
    const deg = t && t.deg !== null && t.deg !== undefined ? t.deg : rec.v.deg;
    emit({ t: 'pantilt_cmd', pan: Math.round(normDeg(deg) * 10) / 10, tilt: 0 });
  });

  // ---------- sensors ----------
  function onRadar(e) {
    $('radar-pres').textContent = e.presence === true ? 'PRESENCE' : e.presence === false ? 'none' : '—';
    $('radar-pres').style.color = e.presence ? 'var(--ok)' : '';
    $('radar-line').innerHTML = 'breath <b>' + fmt(e.breath_bpm, 1) + '</b>/min · heart <b>' + fmt(e.heart_bpm) + '</b>/min<br>' +
      'dist <b>' + fmt(e.dist_m, 1) + ' m</b> · ' + esc(e.src || '—');
  }
  function onKnock(e) {
    state.knockAt = Date.now();
    state.knockEvt = e;
    renderKnock();
  }
  function renderKnock() {
    const e = state.knockEvt;
    if (!e) return;
    $('knock-big').textContent = (e.count ?? '—') + ' knock' + (e.count === 1 ? '' : 's');
    $('knock-line').innerHTML = '<b>' + ago(state.knockAt) + '</b> · ' + esc(e.source || '—') + (e.level_db !== null && e.level_db !== undefined ? ' · ' + fmt(e.level_db) + ' dB' : '');
  }
  function onSound(e) {
    $('sound-big').textContent = e.label || '—';
    $('sound-line').innerHTML = 'score <b>' + fmt(e.score, 2) + '</b> · dir <b>' + sideDeg(e.deg) + '</b>';
  }
  function onNoise(e) {
    const bars = $('noise-bars').querySelectorAll('i');
    const vals = Array.isArray(e.band_db) ? e.band_db : [];
    bars.forEach((b, i) => {
      const v = vals[i];
      // map -90 dB .. -30 dB to 0..100%
      const pct = v === null || v === undefined ? 0 : Math.max(4, Math.min(100, ((v + 90) / 60) * 100));
      b.style.height = pct + '%';
    });
    $('noise-line').innerHTML = (e.quiet ? '<span class="badge knock quiet-badge">Quiet window</span>' : 'bands 0–3 · ' + vals.map((v) => fmt(v)).join(' / ') + ' dB');
  }
  function onLora(e) {
    $('lora-big').textContent = (e.tx ?? '—') + ' sent';
    $('lora-line').innerHTML = 'last packet <b style="color:' + (e.last_ok ? 'var(--ok)' : 'var(--critical)') + '">' + (e.last_ok ? 'ok' : 'failed') + '</b>';
  }

  // ---------- thermal ----------
  const thermal = {
    mode: null, raf: 0, cells: null, W: 32, H: 24,
    mockCv: $('thermal-mock'), ovCv: $('thermal-overlay'), img: $('thermal-img'),
  };

  function setThermalSource(src) {
    cancelAnimationFrame(thermal.raf);
    if (src === 'mock') {
      thermal.mode = 'mock';
      thermal.img.classList.add('hidden');
      thermal.img.removeAttribute('src');
      thermal.mockCv.classList.remove('hidden');
      $('thermal-src').textContent = 'MOCK FEED';
      thermal.raf = requestAnimationFrame(mockFrame);
    } else if (src) {
      thermal.mode = 'img';
      thermal.mockCv.classList.add('hidden');
      thermal.img.classList.remove('hidden');
      thermal.img.src = src;
      $('thermal-src').textContent = 'LIVE';
    }
  }

  // ironbow-ish palette: black -> purple -> red -> orange -> yellow -> white
  const PAL = [[0, 0, 10], [40, 0, 90], [140, 0, 120], [220, 40, 40], [255, 140, 0], [255, 220, 60], [255, 255, 230]];
  function palette(t) {
    t = Math.max(0, Math.min(1, t)) * (PAL.length - 1);
    const i = Math.floor(t), f = t - i, a = PAL[i], b = PAL[Math.min(i + 1, PAL.length - 1)];
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
  }

  function mockFrame(ts) {
    const cv = thermal.mockCv;
    const { W, H } = thermal;
    if (cv.width !== W) { cv.width = W; cv.height = H; }
    const ctx = cv.getContext('2d');
    const img = ctx.createImageData(W, H);
    const t = ts / 1000;
    const spots = (thermal.mode === 'mock' && state.thermal && state.thermal.hotspots) || [];
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        // cool rubble background with slow drifting texture
        let v = 0.18 + 0.06 * Math.sin(x * 0.45 + t * 0.6) * Math.cos(y * 0.5 - t * 0.4) + 0.04 * Math.sin((x + y) * 0.9 + t);
        v += (Math.random() - 0.5) * 0.04;
        for (const s of spots) {
          const cx = (s.x + s.w / 2) * W, cy = (s.y + s.h / 2) * H;
          const rx = Math.max(1, s.w * W * 0.55), ry = Math.max(1, s.h * H * 0.55);
          const d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2;
          v += 0.75 * Math.exp(-d * 1.4) * (0.95 + 0.05 * Math.sin(t * 3));
        }
        const [r, g, b] = palette(v);
        const k = (y * W + x) * 4;
        img.data[k] = r; img.data[k + 1] = g; img.data[k + 2] = b; img.data[k + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
    thermal.raf = requestAnimationFrame(mockFrame);
  }

  function sizeOverlay() {
    const cv = thermal.ovCv, r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    const w = Math.round(r.width * dpr), h = Math.round(r.height * dpr);
    if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
    return { w, h, dpr };
  }

  function drawOverlay() {
    const cv = thermal.ovCv;
    const { w, h, dpr } = sizeOverlay();
    const ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    // center crosshair
    ctx.strokeStyle = 'rgba(232,237,242,0.75)';
    ctx.lineWidth = 1.5 * dpr;
    const cx = w / 2, cy = h / 2, L = 14 * dpr, G = 5 * dpr;
    ctx.beginPath();
    ctx.moveTo(cx - L, cy); ctx.lineTo(cx - G, cy); ctx.moveTo(cx + G, cy); ctx.lineTo(cx + L, cy);
    ctx.moveTo(cx, cy - L); ctx.lineTo(cx, cy - G); ctx.moveTo(cx, cy + G); ctx.lineTo(cx, cy + L);
    ctx.stroke();
    // hotspots (x,y = top-left corner, normalized)
    const spots = (state.thermal && state.thermal.hotspots) || [];
    ctx.font = '700 ' + 12 * dpr + 'px system-ui, sans-serif';
    ctx.textBaseline = 'bottom';
    for (const s of spots) {
      const x = s.x * w, y = s.y * h, bw = s.w * w, bh = s.h * h;
      ctx.strokeStyle = '#39d98a';
      ctx.lineWidth = 2 * dpr;
      ctx.strokeRect(x, y, bw, bh);
      const label = fmt(s.temp_c, 1) + ' °C';
      const tw = ctx.measureText(label).width + 8 * dpr;
      const ly = y > 18 * dpr ? y : y + bh + 18 * dpr;
      ctx.fillStyle = 'rgba(0,0,0,0.65)';
      ctx.fillRect(x, ly - 17 * dpr, tw, 17 * dpr);
      ctx.fillStyle = '#39d98a';
      ctx.fillText(label, x + 4 * dpr, ly - 2 * dpr);
    }
  }

  function onThermal(e) {
    state.thermal = e;
    $('thermal-max').textContent = 'max ' + fmt(e.max_c, 1) + ' °C';
    drawOverlay();
  }

  if ('ResizeObserver' in window) new ResizeObserver(drawOverlay).observe($('thermal-wrap'));
  else window.addEventListener('resize', drawOverlay);

  // ---------- controls ----------
  function setMode(mode) {
    state.pantilt.mode = mode;
    setModeUI(mode);
    $('cam-big').textContent = mode.toUpperCase();
    emit({ t: 'pantilt_mode', mode });
  }
  $('mode-auto').addEventListener('click', () => setMode('auto'));
  $('mode-manual').addEventListener('click', () => setMode('manual'));

  function sendAim() {
    emit({ t: 'pantilt_cmd', pan: Number($('aim-pan').value), tilt: Number($('aim-tilt').value) });
  }
  ['aim-pan', 'aim-tilt'].forEach((id) => {
    const el = $(id);
    el.addEventListener('input', () => { state.aimDragging = true; $(id + '-v').textContent = el.value + '°'; });
    el.addEventListener('change', () => { state.aimDragging = false; sendAim(); });
    el.addEventListener('pointerup', () => { state.aimDragging = false; });
  });
  $('aim-center').addEventListener('click', () => {
    $('aim-pan').value = 0; $('aim-tilt').value = 0;
    $('aim-pan-v').textContent = '0°'; $('aim-tilt-v').textContent = '0°';
    sendAim();
  });

  // live counters ("last heard 6 s ago")
  setInterval(() => { renderQueue(); renderDial(); renderKnock(); }, 1000);

  // ---------- public API ----------
  const HANDLERS = {
    bearing: onBearing, victim: onVictim, thermal_det: onThermal, pantilt: onPantilt,
    radar: onRadar, knock: onKnock, sound: onSound, noise: onNoise, heading: onHeading,
    lora: onLora, drone: onDrone, health: onHealth,
  };

  window.HeimdallOperator = {
    handleEvent(evt) {
      if (!evt || typeof evt !== 'object') return;
      const h = HANDLERS[evt.t];
      if (!h) return; // unknown types are ignored on purpose
      try { h(evt); } catch (e) { console.error('[HEIMDALL] bad event', evt, e); }
    },
    setConnection,
    setThermalSource,
    onCommand(fn) { if (typeof fn === 'function') state.cmdFns.push(fn); },
  };
})();
