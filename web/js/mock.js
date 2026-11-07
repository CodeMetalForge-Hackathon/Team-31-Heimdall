/* HEIMDALL fake data for offline demos. Loaded only in mock mode (file:// or ?mock).
 * Talks to the screens only through the public hook APIs, exactly like the live code will.
 */
(function () {
  'use strict';

  const now = () => Date.now() / 1000;
  const rnd = (a, b) => a + Math.random() * (b - a);
  const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
  const round1 = (x) => Math.round(x * 10) / 10;
  const norm = (d) => ((d + 180) % 360 + 360) % 360 - 180;

  function toast(msg) {
    let el = document.getElementById('mock-toast');
    if (!el) { el = document.createElement('div'); el.id = 'mock-toast'; el.className = 'toast'; document.body.appendChild(el); }
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove('show'), 1600);
  }

  // =====================================================================
  // OPERATOR
  // =====================================================================
  if (window.HeimdallOperator) {
    const op = window.HeimdallOperator;
    const send = (e) => op.handleEvent(Object.assign({ ts: now() }, e));
    const t0 = Date.now();
    const elapsed = () => (Date.now() - t0) / 1000;

    op.setConnection('mock');
    op.setThermalSource('mock');

    // Fake victims. `base` is where each one really is; bearings drift around it.
    const V = {
      '1A2B': { id: '1A2B', base: -35, floor: 2, minutes: 14, motion: true, status: 'injured', people: 2, battery: 3, hops: 0, knock: false, band: 1 },
      '77C1': { id: '77C1', base: 40, floor: null, minutes: 58, motion: true, status: 'critical', people: 1, battery: 1, hops: 0, knock: false, band: 2 },
      '5E09': { id: '5E09', base: 118, floor: 1, minutes: 31, motion: false, status: 'no_response', people: 1, battery: 2, hops: 1, knock: false, band: 3 },
    };
    const deg = {}; // current noisy bearing per id
    Object.values(V).forEach((v) => { deg[v.id] = v.base; });
    const drift = (id) => {
      V[id].base += rnd(-0.6, 0.6); // the station/rescuer moves a little
      deg[id] = round1(V[id].base + rnd(-4, 4));
      return deg[id];
    };

    const cam = { pan: 0, tilt: 5, mode: 'auto', goal: 0, goalTilt: 5 };
    let lastTarget = '1A2B';

    op.onCommand((cmd) => {
      console.log('[mock] command', cmd);
      toast('Command sent: ' + (cmd.t === 'pantilt_mode' ? 'mode ' + cmd.mode : 'pan ' + cmd.pan + '° tilt ' + cmd.tilt + '°'));
      if (cmd.t === 'pantilt_mode') cam.mode = cmd.mode;
      if (cmd.t === 'pantilt_cmd') { cam.goal = cmd.pan; cam.goalTilt = cmd.tilt; cam.holdUntil = Date.now() + 10000; }
    });

    function victimEvent(id) {
      const v = V[id];
      // 77C1 stops moving after 60 s (shows "STOPPED MOVING")
      if (id === '77C1' && elapsed() > 60) v.motion = false;
      if (id === '1A2B') v.hops = Math.random() < 0.3 ? 1 : 0; // sometimes heard via a relay phone
      v.minutes += 8 / 60 * 4; // sped up 4x so the counter visibly climbs in a demo
      v.knock = id === '1A2B' ? elapsed() > 25 : v.knock;
      const d = drift(id);
      // SPEC v1.1: the first frame of a beacon is unconfirmed until a second one arrives
      const confirmed = heardBefore.has(id);
      heardBefore.add(id);
      send({ t: 'victim', id, floor: v.floor, minutes: Math.floor(v.minutes), motion: v.motion, status: v.status, people: v.people,
        battery: v.battery, hops: v.hops, knock: v.knock, deg: d, band: v.band, snr_db: round1(rnd(9, 22)), confirmed });
      if (confirmed) lastTarget = id; // the camera never chases an unconfirmed beacon
    }
    const heardBefore = new Set();

    // victims every ~8 s (staggered), 5E09 shows up after 20 s
    victimEvent('1A2B');
    setTimeout(() => victimEvent('77C1'), 1500);
    setInterval(() => victimEvent('1A2B'), 8000);
    setTimeout(() => setInterval(() => victimEvent('77C1'), 8000), 4000);
    setTimeout(() => { victimEvent('5E09'); setInterval(() => victimEvent('5E09'), 8000); }, 20000);

    // B40E: only known from a phone's relay report, so the station has no direction (deg null)
    const B40E = { id: 'B40E', floor: 1, minutes: 22, motion: true, status: 'injured', people: 3, battery: 2, hops: 1, knock: false, band: 0 };
    function phoneOnlyEvent() {
      const confirmed = heardBefore.has('B40E');
      heardBefore.add('B40E');
      B40E.minutes += 8 / 60 * 4;
      send(Object.assign({ t: 'victim' }, B40E, { minutes: Math.floor(B40E.minutes), deg: null, snr_db: round1(rnd(6, 12)), confirmed }));
    }
    setTimeout(() => { phoneOnlyEvent(); setInterval(phoneOnlyEvent, 8000); }, 20000);

    // C0DE: heard once (maybe a false alarm), never confirmed, disappears after 60 s
    setTimeout(() => send({ t: 'victim', id: 'C0DE', floor: null, minutes: 0, motion: true, status: 'no_response', people: 1,
      battery: 3, hops: 0, knock: false, deg: round1(rnd(60, 90)), band: 2, snr_db: 6.5, confirmed: false }), 10000);

    // bearings: mostly tags, sometimes an unknown human sound, sometimes a head-scan
    setInterval(() => {
      const r = Math.random();
      if (r < 0.12) {
        send({ t: 'bearing', deg: round1(rnd(-170, -140)), conf: round1(rnd(0.3, 0.6)), band: null, snr_db: round1(rnd(4, 9)), src: 'sound', id: null });
      } else if (r < 0.18) {
        send({ t: 'bearing', deg: round1(cam.pan + rnd(-5, 5)), conf: round1(rnd(0.5, 0.8)), band: null, snr_db: null, src: 'scan', id: null });
      } else {
        const ids = elapsed() > 20 ? ['1A2B', '77C1', '5E09'] : ['1A2B', '77C1'];
        const id = Math.random() < 0.5 ? lastTarget : pick(ids);
        send({ t: 'bearing', deg: drift(id), conf: round1(rnd(0.55, 0.95)), band: V[id].band, snr_db: round1(rnd(9, 22)), src: 'tag', id });
      }
    }, 1500);

    // camera head: in AUTO it follows the newest victim; in MANUAL it goes to the commanded angle
    setInterval(() => {
      const follow = cam.mode === 'auto' && !(cam.holdUntil > Date.now()); // a tapped card holds the aim for 10 s
      const goal = follow ? deg[lastTarget] : cam.goal;
      const goalT = follow ? 5 : cam.goalTilt;
      const clampPan = Math.max(-170, Math.min(170, goal));
      cam.pan = round1(cam.pan + Math.max(-12, Math.min(12, clampPan - cam.pan)));
      cam.tilt = round1(cam.tilt + Math.max(-6, Math.min(6, goalT - cam.tilt)));
      send({ t: 'pantilt', pan: cam.pan, tilt: cam.tilt, mode: cam.mode });
    }, 500);

    // thermal hotspots for whoever is inside the camera's view
    setInterval(() => {
      const FOV = 55;
      const hotspots = [];
      Object.values(V).forEach((v) => {
        if (v.id === '5E09' && elapsed() < 20) return;
        const off = norm(deg[v.id] - cam.pan);
        if (Math.abs(off) > FOV / 2) return;
        const w = 0.12 + (v.people > 1 ? 0.06 : 0), h = 0.3;
        const x = Math.max(0, Math.min(1 - w, 0.5 + off / FOV - w / 2));
        const y = Math.max(0, Math.min(1 - h, 0.5 - (cam.tilt - 5) / 60 - h / 2 + 0.05));
        hotspots.push({ x: round1(x * 100) / 100, y: round1(y * 100) / 100, w, h, temp_c: round1(rnd(32.5, 35.5)), deg: deg[v.id] });
      });
      const max = hotspots.length ? Math.max(...hotspots.map((s) => s.temp_c)) + 0.3 : round1(rnd(19, 22));
      send({ t: 'thermal_det', pan_deg: cam.pan, max_c: round1(max), hotspots });
    }, 700);

    // the rest of the sensors
    let yaw = 212, tx = 0, quiet = false;
    setInterval(() => { yaw = (yaw + rnd(-1.5, 1.5) + 360) % 360; send({ t: 'heading', yaw_deg: round1(yaw) }); }, 1000);
    setInterval(() => {
      const presence = Math.random() < 0.8;
      send({ t: 'radar', presence, breath_bpm: presence ? round1(rnd(12, 17)) : null,
        heart_bpm: presence && Math.random() < 0.6 ? Math.round(rnd(68, 96)) : null,
        dist_m: presence ? round1(rnd(0.8, 2.4)) : null, src: 'tinyrad' });
    }, 2000);
    setInterval(() => { if (Math.random() < 0.15) quiet = !quiet; send({ t: 'noise', band_db: [0, 1, 2, 3].map((i) => round1(rnd(-62, -42) - i * 3 - (quiet ? 14 : 0))), quiet }); }, 1000);
    const knock = () => send({ t: 'knock', source: 'sw420', count: pick([2, 3, 3, 4]), level_db: null });
    setTimeout(knock, 6000); setInterval(knock, 20000);
    const sound = () => send({ t: 'sound', label: pick(['Speech', 'Speech', 'Cough', 'Shout', 'Tapping']), score: Math.round(rnd(0.45, 0.9) * 100) / 100, deg: round1(rnd(-170, -140)) });
    setTimeout(sound, 3000); setInterval(sound, 7000);
    const lora = () => { tx++; send({ t: 'lora', tx, last_ok: Math.random() < 0.9 }); };
    lora(); setInterval(lora, 10000);
    const notes = ['perched', 'perched', 'hovering', 'scouting'];
    const drone = () => send({ t: 'drone', link: Math.random() < 0.93 ? 'ok' : 'weak', note: pick(notes) });
    drone(); setInterval(drone, 5000);
    const health = () => send({ t: 'health', modules: { audio: 'ok', thermal: 'ok', radar: Math.random() < 0.8 ? 'ok' : 'error', knock: 'ok', lora: 'ok', camera: 'ok' } });
    health(); setInterval(health, 10000);

    console.log('[mock] operator mock running. Try: HeimdallOperator.handleEvent({t:"bearing",deg:90,conf:0.9,band:0,snr_db:20,src:"tag",id:"1A2B"})');
  }

  // =====================================================================
  // VICTIM
  // =====================================================================
  if (window.HeimdallVictim) {
    const vic = window.HeimdallVictim;
    let beaconTimer = null, sent = 0, band = 0, next = 0, trigger = null;

    function startBeacon(trig) {
      stopBeacon();
      trigger = trig;
      sent = 0; band = 0;
      const period = () => (vic.getSettings().demoFast ? 8 : 30);
      next = 0;
      const tick = () => {
        if (next <= 0) { sent++; band = (sent - 1) % 4; next = period(); }
        vic.setBeacon({ on: true, band, nextInSec: next, sent, trigger });
        next--;
      };
      tick();
      beaconTimer = setInterval(tick, 1000);
    }
    function stopBeacon() {
      if (beaconTimer) clearInterval(beaconTimer);
      beaconTimer = null;
    }

    vic.onStart(() => { console.log('[mock] SOS start', vic.getSettings()); startBeacon('manual'); });
    vic.onStop(() => { console.log('[mock] SOS stop'); stopBeacon(); vic.setBeacon({ on: false }); });
    vic.onSettingsChange((s) => console.log('[mock] settings', s));

    // mic level (listening for others) and motion
    setInterval(() => vic.setMicLevel(Math.min(1, Math.abs(rnd(-0.25, 0.25)) + (Math.random() < 0.05 ? 0.6 : 0.05))), 120);
    let moving = true;
    vic.setMotion(moving);
    setInterval(() => { if (Math.random() < 0.3) { moving = !moving; vic.setMotion(moving); } }, 5000);

    // other beacons heard nearby, and passed on when relay is on
    const others = [
      { id: '77C1', status: 'injured', people: 2, floor: null, band: 2 },
      { id: 'B40E', status: 'critical', people: 1, floor: 1, band: 0 },
      { id: '3D9A', status: 'no_response', people: 3, floor: 2, band: 3 },
    ];
    function hearOne() {
      const o = Object.assign({}, pick(others), { hops: Math.random() < 0.7 ? 0 : 1, ts: now() });
      vic.logHeard(o);
      if (vic.getSettings().relay && o.hops < 3) {
        setTimeout(() => vic.logRelayed(Object.assign({}, o, { hops: o.hops + 1, ts: now() })), rnd(1500, 4000));
      }
    }
    setTimeout(hearOne, 4000);
    setInterval(hearOne, 15000);

    // rescuers knocking: banner for 5 s every ~40 s
    const knock = () => { vic.showKnock(true); setTimeout(() => vic.showKnock(false), 5000); };
    setTimeout(knock, 12000);
    setInterval(knock, 40000);

    // press F to simulate a fall: 10 s countdown, then auto-SOS
    let fallTimer = null;
    function cancelFall() { if (fallTimer) clearInterval(fallTimer); fallTimer = null; vic.showFallCountdown(null); }
    vic.onCancelFall(() => { console.log('[mock] fall cancelled'); cancelFall(); });
    document.addEventListener('keydown', (e) => {
      if ((e.key === 'f' || e.key === 'F') && !e.metaKey && !e.ctrlKey && !/INPUT|TEXTAREA/.test(document.activeElement.tagName)) {
        if (fallTimer) return;
        let s = 10;
        vic.showFallCountdown(s);
        fallTimer = setInterval(() => {
          s--;
          if (s > 0) { vic.showFallCountdown(s); return; }
          cancelFall();
          startBeacon('fall');
        }, 1000);
      }
    });

    console.log('[mock] victim mock running. Press F for a fake fall.');
  }
})();
