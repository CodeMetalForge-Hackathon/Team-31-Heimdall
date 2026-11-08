/* HEIMDALL victim page, live mode: beacon (SPEC 1.5), listen, relay (SPEC 1.6), forward to the station.
 * Loaded after heimdall-modem.js. Talks to the screen only through window.HeimdallVictim.
 * The pure logic at the top is exported for Node (web/tests/test_victim_logic.mjs); the browser
 * part below it only runs when the victim screen is there.
 * URL switches: ?listen=0|1 (mic on/off, default on), ?session=0 (skip navigator.audioSession),
 * ?debug=1 (status line with rate, pipeline, detections, socket).
 */
(function (root) {
  'use strict';

  const HM = root.HeimdallModem || (typeof require === 'function' ? require('./heimdall-modem.js') : null);
  const SPEC = HM.SPEC;
  const FRAME_S = SPEC.FRAME_S;          // 2.13 s on air
  const TX_GUARD_S = 0.1;                // silence between two of our own frames
  const OWN_DUE_S = 2.5;                 // SPEC 1.6.5: relay waits if our beacon is due this soon
  const ECHO_MARGIN_S = 0.15;            // ignore what we decode while our own frame plays, + this
  const G = 9.81;

  // ================================================================ pure logic
  const periodS = (demoFast) => (demoFast ? SPEC.DEMO_PERIOD_S : SPEC.NORMAL_PERIOD_S);
  const motionWindowS = (demoFast) => (demoFast ? 20 : 60);
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));

  /** Seconds until the next own frame: period ± jitter (SPEC 1.5). rand() in [0, 1). */
  function nextDelayS(demoFast, rand) {
    return periodS(demoFast) + (2 * rand() - 1) * SPEC.JITTER_S;
  }

  /** navigator.getBattery() level 0..1 -> quarters 0..3 (SPEC 1.3); unknown -> 3. */
  function batteryQuarter(level) {
    if (typeof level !== 'number' || !(level >= 0)) return 3;
    return clamp(Math.floor(level * 4), 0, 3);
  }

  /** Decoder input level −60…−10 dBFS -> meter 0…1. */
  function levelToMeter(db) {
    return clamp((db + 60) / 50, 0, 1);
  }

  /** One devicemotion sample: |a incl. gravity| off 1 g by > 0.8 m/s², or rotating > 20°/s. */
  function isMoving(aMag, rot) {
    if (Math.abs(aMag - G) > 0.8) return true;
    if (rot) for (const k of ['alpha', 'beta', 'gamma']) if (Math.abs(rot[k] || 0) > 20) return true;
    return false;
  }

  /** Payload fields (SPEC 1.3) for our own beacon. st: {startMs, nowMs, lastMoveMs|null, battery}. */
  function buildFields(s, st) {
    const minutes = Math.max(0, Math.floor((st.nowMs - st.startMs) / 60000));
    const motion = st.lastMoveMs !== null && st.lastMoveMs !== undefined &&
      st.nowMs - st.lastMoveMs <= motionWindowS(s.demoFast) * 1000;
    return {
      id: s.id, floor: s.floor === undefined ? null : s.floor, minutes, motion,
      status: s.status || 'no_response', people: clamp(s.people | 0, 0, 7),
      battery: st.battery === undefined ? 3 : st.battery, hops: 0, knock: false,
    };
  }

  /** Does a received span [t0, t1] (context time) overlap one of our own frames, with the
   * end pushed out by the speaker->mic latency + 150 ms? booked: [{start, end}]. */
  function overlapsOwn(t0, t1, booked, latencyS) {
    for (const b of booked) if (t0 < b.end + latencyS + ECHO_MARGIN_S && t1 > b.start) return true;
    return false;
  }

  /** Is a decoded frame the echo of one of our own transmissions? Same id, hops and band as a frame we
   * played, overlapping it in time (+ latency + 150 ms). Frames of other phones that overlap ours are kept
   * (N4: the time-only rule threw away 8 of 13 frames of a phone in step with us). */
  function isOwnEcho(f, t0, t1, booked, latencyS) {
    for (const b of booked) {
      if (b.id !== f.id || b.hops !== f.hops || b.band !== f.band) continue;
      if (t0 < b.end + latencyS + ECHO_MARGIN_S && t1 > b.start) return true;
    }
    return false;
  }

  /** Earliest start >= t for a relay: never on top of a booked frame, never within 2.5 s
   * before our next beacon (then right after it ends) (SPEC 1.6.5). */
  function planRelay(t, booked, nextOwnAt) {
    let s = t;
    for (let moved = true, n = 0; moved && n < 50; n++) {
      moved = false;
      for (const b of booked) {
        if (s < b.end + TX_GUARD_S && s + FRAME_S + TX_GUARD_S > b.start) { s = b.end + TX_GUARD_S; moved = true; }
      }
      if (nextOwnAt !== null && nextOwnAt !== undefined && s > nextOwnAt - OWN_DUE_S && s < nextOwnAt + FRAME_S + TX_GUARD_S) {
        s = nextOwnAt + FRAME_S + TX_GUARD_S; moved = true;
      }
    }
    return s;
  }

  /** Earliest start >= t for our own beacon that doesn't land on a booked relay. */
  function planOwn(t, booked) {
    let s = t;
    for (let moved = true, n = 0; moved && n < 50; n++) {
      moved = false;
      for (const b of booked) {
        if (s < b.end + TX_GUARD_S && s + FRAME_S + TX_GUARD_S > b.start) { s = b.end + TX_GUARD_S; moved = true; }
      }
    }
    return s;
  }

  /** SPEC 1.6 relay decisions. Times in seconds on one clock (the page uses AudioContext time). */
  class RelayQueue {
    constructor(myId, rand, holdoffS) {
      this.myId = myId;
      this.rand = rand || Math.random;
      this.holdoffS = holdoffS === undefined ? SPEC.RELAY_HOLDOFF_S : holdoffS;   // 0 on a relay-only phone (SPEC v1.3)
      this.lastTc = undefined;    // context time of the last detection that restarted a wait
      this.pending = [];          // {fields, band, waitStart, due, rewaits}
      this.lastRelayed = new Map(); // id -> time we last took it for transmission
      this.dropped = 0;
    }

    wait() { return SPEC.RELAY_WAIT_MIN_S + this.rand() * (SPEC.RELAY_WAIT_MAX_S - SPEC.RELAY_WAIT_MIN_S); }

    /** A valid decoded frame. Returns 'queued' or why not. */
    offer(fields, band, now) {
      const id = fields.id;
      if (id === this.myId) return 'own';
      if (!(fields.hops < SPEC.RELAY_MAX_HOPS)) return 'hops';
      if (this.pending.some((p) => p.fields.id === id)) return 'pending';
      const last = this.lastRelayed.get(id);
      if (last !== undefined && now - last < this.holdoffS) return 'holdoff';
      this.pending.push({ fields: Object.assign({}, fields), band, waitStart: now, due: now + this.wait(), rewaits: 0 });
      return 'queued';
    }

    /** A preamble ending at time tc was heard (reported at `now`): everyone waiting since before it waits again. */
    preamble(tc, now) {
      // One frame on the air gives several detections within about 0.7 s (its preamble, leakage into the next band,
      // data symbols that look like one): a detection < 0.8 s after the last one that counted is the same frame,
      // so it must not eat another of the 3 re-waits.
      if (this.lastTc !== undefined && Math.abs(tc - this.lastTc) < 0.8) { this.lastTc = tc; return; }
      let counted = false;
      this.pending = this.pending.filter((p) => {
        if (tc < p.waitStart || now >= p.due) return true;
        counted = true;
        if (++p.rewaits > 3) { this.dropped++; return false; }
        p.waitStart = now;
        p.due = now + this.wait();
        return true;
      });
      if (counted) this.lastTc = tc;   // a detection that restarted a wait opens the 0.8 s window; the ones inside it extend it
    }

    /** Relays whose wait is over: same fields with hops + 1, band (rx band + 2) % 4 (SPEC v1.2). */
    take(now) {
      const out = [];
      this.pending = this.pending.filter((p) => {
        if (now < p.due) return true;
        this.lastRelayed.set(p.fields.id, now);
        out.push({ fields: Object.assign({}, p.fields, { hops: p.fields.hops + 1 }), band: (p.band + 2) % 4, rxBand: p.band });
        return false;
      });
      return out;
    }

    nextDue() { return this.pending.reduce((m, p) => Math.min(m, p.due), Infinity); }
  }

  /** Free fall (|a| < 3 m/s² for >= 80 ms), impact (> 25 m/s²) within 1 s, then 2 s still. feed() -> true on a fall. */
  class FallDetector {
    constructor() { this.reset(); }
    reset() { this.state = 'idle'; this.t0 = 0; this.stillSince = null; }
    feed(tMs, aMag, moving) {
      switch (this.state) {
        case 'idle':
          if (aMag < 3) { this.state = 'ff'; this.t0 = tMs; }
          return false;
        case 'ff':
          if (aMag < 3) return false;
          if (tMs - this.t0 < 80) { this.state = 'idle'; return false; }
          this.state = 'impact'; this.t0 = tMs;
          // fall through: this sample may already be the impact
        case 'impact': // eslint-disable-line no-fallthrough
          if (aMag > 25) { this.state = 'settle'; this.t0 = tMs; this.stillSince = null; }
          else if (tMs - this.t0 > 1000) this.state = 'idle';
          return false;
        case 'settle':
          if (tMs - this.t0 < 300) return false;   // let the bounce die down
          if (moving) this.stillSince = null;
          else if (this.stillSince === null) this.stillSince = tMs;
          if (this.stillSince !== null && tMs - this.stillSince >= 2000) { this.reset(); return true; }
          if (tMs - this.t0 > 8000) this.reset(); // kept moving: they're fine
          return false;
      }
      return false;
    }
  }

  const Logic = { periodS, motionWindowS, nextDelayS, batteryQuarter, levelToMeter, isMoving, buildFields,
    overlapsOwn, isOwnEcho, planRelay, planOwn, RelayQueue, FallDetector, FRAME_S };
  root.HeimdallVictimLogic = Logic;
  if (typeof module !== 'undefined' && module.exports) module.exports = Logic;

  if (!root.HeimdallVictim || !root.document) return;

  // ================================================================ browser
  const vic = root.HeimdallVictim;
  const params = new URLSearchParams(location.search);
  const IOS = /iP(hone|ad|od)/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const LISTEN = params.has('listen') ? params.get('listen') !== '0' : true;
  const RELAY_ONLY = params.get('mode') === 'relay';   // ?mode=relay: listen + relay, no beacon of our own (SPEC v1.3)
  const STILL = RELAY_ONLY ? ' This phone relays nothing until its microphone works.' : ' Your SOS still plays.';
  const USE_SESSION = params.get('session') !== '0';
  const DEBUG = params.has('debug');
  const log = (...a) => console.log('[HEIMDALL victim]', ...a);

  const S = {
    ctx: null, unlocked: false,
    active: false, trigger: null, startMs: 0, k: 0, sent: 0, lastBand: null,
    nextAt: null,            // context time of our next beacon
    booked: [],              // {start, end, kind, src} frames we scheduled
    tick: null,
    relay: null,
    listen: null,            // {stream, src, node, sink, worker, mode}
    lastMoveMs: null, motionOn: false, battery: 3,
    wake: null, ws: null, wsRetry: null, wsBackoff: 2,
    fall: new FallDetector(), fallTimer: null,
    errs: {},
    stats: { detect: 0, frames: 0, echo: 0, heard: 0, relayed: 0, level: -120, cpu: 0 },
  };
  root.HeimdallVictimLive = S; // for debugging in the console

  function setErr(key, msg) {
    if (msg) S.errs[key] = msg; else delete S.errs[key];
    const all = Object.values(S.errs);
    vic.showError(all.length ? all.join(' ') : null);
  }

  // ---------------------------------------------------------------- audio
  function audio() {
    if (!S.ctx) {
      const AC = root.AudioContext || root.webkitAudioContext;
      if (!AC) { setErr('audio', 'This browser cannot play sound. Use Safari or Chrome.'); return null; }
      S.ctx = new AC({ latencyHint: 'interactive' });
      S.ctx.onstatechange = () => log('audio', S.ctx.state);
    }
    if (S.ctx.state !== 'running') S.ctx.resume().catch(() => {});
    return S.ctx;
  }

  /** Call inside a tap: browsers only start sound from a user gesture. */
  function unlockAudio() {
    if (USE_SESSION && navigator.audioSession) {
      try { navigator.audioSession.type = 'play-and-record'; } catch (e) { log('audioSession', e); }
    }
    const c = audio();
    if (!c) return;
    if (!S.unlocked) {
      // a silent sample started in the gesture unlocks output on iOS
      const b = c.createBuffer(1, 1, c.sampleRate), src = c.createBufferSource();
      src.buffer = b; src.connect(c.destination); src.start();
      S.unlocked = true;
    }
  }

  const bufCache = new Map();
  function frameBuffer(fields, band) {
    const c = S.ctx, bytes = HM.pack(fields), key = HM.toHex(bytes) + '/' + band;
    let buf = bufCache.get(key);
    if (!buf) {
      const x = HM.synth(bytes, band, c.sampleRate);
      buf = c.createBuffer(1, x.length, c.sampleRate);
      if (buf.copyToChannel) buf.copyToChannel(x, 0); else buf.getChannelData(0).set(x);
      if (bufCache.size > 24) bufCache.delete(bufCache.keys().next().value);
      bufCache.set(key, buf);
    }
    return buf;
  }

  function play(fields, band, at, kind) {
    const c = S.ctx;
    const src = c.createBufferSource();
    src.buffer = frameBuffer(fields, band);
    src.connect(c.destination);
    at = Math.max(at, c.currentTime + 0.03);
    src.start(at);
    S.booked.push({ start: at, end: at + FRAME_S, kind, src, id: fields.id, hops: fields.hops, band });
    return at;
  }

  function latencyS() {
    const c = S.ctx;
    return (c && ((c.outputLatency || 0) + (c.baseLatency || 0))) + 0.05;
  }

  // ---------------------------------------------------------------- beacon
  function startBeacon(trigger) {
    const c = audio();
    if (!c) return;
    S.active = true;
    S.trigger = trigger;
    S.startMs = Date.now();
    S.k = 0; S.sent = 0; S.lastBand = null;
    S.nextAt = RELAY_ONLY ? Infinity : c.currentTime + 0.15;   // relay only: our own beacon is never due
    // a relay-only phone has no beacon of its own, so it passes on every frame it hears (no 30 s hold-off):
    // phone A's card then gets a fresh direction every ~10 s instead of every 32-42 s
    S.relay = new RelayQueue(vic.getSettings().id, undefined, RELAY_ONLY ? 0 : undefined);
    clearInterval(S.tick);
    S.tick = setInterval(tick, 250);
    tick();
    connectStation();
    requestWakeLock();
    if (RELAY_ONLY) setErr('mode', 'Relay only: this phone passes on other SOS calls and sends none of its own.');
    log(RELAY_ONLY ? 'relay only on' : 'beacon on', trigger, c.sampleRate + ' Hz');
  }

  function stopBeacon() {
    S.active = false;
    clearInterval(S.tick); S.tick = null;
    for (const b of S.booked) { try { b.src.stop(); } catch (e) { /* not started yet or done */ } }
    S.booked = [];
    S.relay = null;
    stopMic();
    releaseWakeLock();
    disconnectStation();
    vic.setBeacon({ on: false });
    vic.setMicLevel(0);
    setErr('mic', null);
    setErr('mode', null);
    log('beacon off');
  }

  function tick() {
    const c = S.ctx;
    if (!S.active || !c) return;
    if (c.state !== 'running') c.resume().catch(() => {});
    const now = c.currentTime;
    S.booked = S.booked.filter((b) => b.end > now - 30);
    const s = vic.getSettings();
    if (S.relay) S.relay.myId = s.id;

    if (S.nextAt < now - 0.5) S.nextAt = now + 0.1; // the page was asleep: send now, don't burst
    if (!RELAY_ONLY && now >= S.nextAt - 0.3) {
      const fields = buildFields(s, { startMs: S.startMs, nowMs: Date.now(), lastMoveMs: S.lastMoveMs, battery: S.battery });
      const band = HM.bandFor(S.k, s.id);
      const at = play(fields, band, planOwn(S.nextAt, S.booked), 'own');
      S.k++; S.sent++; S.lastBand = band;
      S.nextAt = at + nextDelayS(s.demoFast, Math.random);
      if (DEBUG) log('beacon', HM.toHex(HM.pack(fields)), 'band', band, 'at', at.toFixed(2));
    }

    if (S.relay) {
      for (const r of S.relay.take(now)) {
        const at = play(r.fields, r.band, planRelay(now + 0.05, S.booked, S.nextAt), 'relay');
        S.stats.relayed++;
        const entry = Object.assign({}, r.fields, { band: r.band, ts: Date.now() / 1000 + (at - now) });
        setTimeout(() => { if (S.active) vic.logRelayed(entry); }, Math.max(0, (at - now) * 1000));
        log('relay', r.fields.id, 'hop', r.fields.hops, 'band', r.band, 'in', (at - now).toFixed(2), 's');
      }
    }

    vic.setBeacon(RELAY_ONLY ? { on: true, sent: S.stats.relayed, trigger: S.trigger }
      : { on: true, band: S.lastBand, nextInSec: Math.max(0, S.nextAt - now), sent: S.sent, trigger: S.trigger });
    vic.setMotion(S.lastMoveMs !== null && Date.now() - S.lastMoveMs < 2000);
    if (DEBUG) debugLine();
  }

  // ---------------------------------------------------------------- listen
  function startMic() {
    if (!LISTEN) { log('listening off (?listen=0)'); return; }
    if (S.listen) return;
    if (!root.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setErr('mic', 'To hear other phones, open the page from https://10.42.0.1:8443 .' + STILL);
      return;
    }
    const pending = navigator.mediaDevices.getUserMedia({ audio: {
      echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 } });
    S.listen = { starting: true };
    pending.then((stream) => {
      if (!S.active || !S.listen || !S.listen.starting) { stream.getTracks().forEach((t) => t.stop()); return; }
      return buildPipeline(stream);
    }).then(() => setErr('mic', null)).catch((e) => {
      log('mic failed', e);
      S.listen = null;
      setErr('mic', e && e.name === 'NotAllowedError'
        ? 'Microphone blocked: this phone can\'t pass on other SOS calls.' + STILL
        : 'Microphone did not start (' + (e && e.message || e) + ').' + STILL);
    });
  }

  async function buildPipeline(stream) {
    const c = S.ctx;
    const L = { stream, src: c.createMediaStreamSource(stream), sink: c.createGain(), node: null, worker: null, mode: '' };
    L.sink.gain.value = 0;
    L.sink.connect(c.destination);
    L.worker = new Worker('js/heimdall-listen-worker.js');
    L.worker.onmessage = (e) => onWorker(e.data);
    L.worker.onerror = (e) => log('worker error', e.message);
    let worklet = false;
    if (c.audioWorklet && root.MessageChannel && root.AudioWorkletNode) {
      try {
        await c.audioWorklet.addModule('js/heimdall-tap-worklet.js');
        const ch = new MessageChannel();
        L.node = new AudioWorkletNode(c, 'heimdall-tap', { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1 });
        L.worker.postMessage({ type: 'init', rate: c.sampleRate, port: ch.port2 }, [ch.port2]);
        L.node.port.postMessage({ port: ch.port1 }, [ch.port1]);
        L.mode = 'worklet';
        worklet = true;
      } catch (e) { log('AudioWorklet failed, using ScriptProcessor', e); }
    }
    if (!worklet) {
      L.node = c.createScriptProcessor(4096, 1, 1);
      L.worker.postMessage({ type: 'init', rate: c.sampleRate });
      L.node.onaudioprocess = (e) => {
        const x = new Float32Array(e.inputBuffer.getChannelData(0));
        const f0 = Math.round((e.playbackTime - x.length / c.sampleRate) * c.sampleRate);
        L.worker.postMessage({ type: 'audio', x, f0 }, [x.buffer]);
      };
      L.mode = 'scriptprocessor';
    }
    L.src.connect(L.node);
    L.node.connect(L.sink);
    if (!S.active) { teardown(L); return; }
    S.listen = L;
    log('listening', c.sampleRate + ' Hz', L.mode);
  }

  function teardown(L) {
    try { L.src.disconnect(); L.node.disconnect(); L.sink.disconnect(); } catch (e) { /* ignore */ }
    if (L.stream) L.stream.getTracks().forEach((t) => t.stop());
    if (L.worker) L.worker.terminate();
  }

  function stopMic() {
    const L = S.listen;
    S.listen = null;
    if (L && !L.starting) teardown(L);
  }

  function onWorker(d) {
    if (!S.active) return;
    if (d.type === 'stats') {
      S.stats.level = d.level; S.stats.cpu = d.cpu;
      vic.setMicLevel(levelToMeter(d.level));
      return;
    }
    if (d.type === 'detect') {
      S.stats.detect++;
      if (overlapsOwn(d.tc - 0.2, d.tc, S.booked, latencyS())) return;
      if (S.relay) S.relay.preamble(d.tc, S.ctx.currentTime);
      return;
    }
    if (d.type !== 'frame') return;
    const f = d.f, s = vic.getSettings();
    S.stats.frames++;
    if (f.id === s.id) return;                                         // our own beacon, maybe relayed back
    if (isOwnEcho(f, d.tc - SPEC.PREAMBLE_S, d.tc + FRAME_S - SPEC.PREAMBLE_S, S.booked, latencyS())) {
      S.stats.echo++;
      return;
    }
    S.stats.heard++;
    const fields = { id: f.id, floor: f.floor, minutes: f.minutes, motion: f.motion, status: f.status,
      people: f.people, battery: f.battery, hops: f.hops, knock: f.knock };
    vic.logHeard(Object.assign({}, fields, { band: f.band, ts: Date.now() / 1000 }));
    log('heard', f.id, 'hops', f.hops, 'band', f.band, 'snr', f.snr_db);
    sendStation({ t: 'heard', id: f.id, fields, band: f.band, snr_db: f.snr_db, via: 'phone-' + s.id });
    if ((s.relay || RELAY_ONLY) && S.relay) {   // a relay-only phone relays even if the Settings toggle is off
      const r = S.relay.offer(fields, f.band, S.ctx.currentTime);
      if (r !== 'queued') log('not relaying', f.id, r);
    }
  }

  // ---------------------------------------------------------------- station socket (fire and forget)
  function connectStation() {
    if (S.ws || !S.active) return;
    let ws;
    try { ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws'); }
    catch (e) { return; }
    S.ws = ws;
    ws.onopen = () => { S.wsBackoff = 2; log('station socket open'); };
    ws.onclose = () => {
      if (S.ws !== ws) return;
      S.ws = null;
      if (S.active) S.wsRetry = setTimeout(connectStation, S.wsBackoff * 1000);
      S.wsBackoff = Math.min(10, S.wsBackoff * 2);
    };
    ws.onerror = () => {};
  }
  function disconnectStation() {
    clearTimeout(S.wsRetry);
    const ws = S.ws;
    S.ws = null;
    if (ws) try { ws.close(); } catch (e) { /* ignore */ }
  }
  function sendStation(msg) {
    if (S.ws && S.ws.readyState === WebSocket.OPEN) try { S.ws.send(JSON.stringify(msg)); } catch (e) { /* ignore */ }
  }

  // ---------------------------------------------------------------- motion + fall
  function startMotion() {
    if (S.motionOn || !('DeviceMotionEvent' in root)) return;
    const on = () => {
      if (S.motionOn) return;
      S.motionOn = true;
      root.addEventListener('devicemotion', onMotion);
      setErr('motion', null);
    };
    if (typeof DeviceMotionEvent.requestPermission === 'function') {
      // iOS: must be called from the tap itself
      DeviceMotionEvent.requestPermission().then((r) => {
        if (r === 'granted') on();
        else setErr('motion', 'Motion is blocked, so rescuers won\'t see if you move. Allow Motion & Orientation for this site.');
      }).catch((e) => log('motion permission', e));
    } else on();
  }

  function onMotion(e) {
    const a = e.accelerationIncludingGravity;
    if (!a || a.x === null || a.x === undefined) return;
    const mag = Math.hypot(a.x, a.y || 0, a.z || 0);
    const moving = isMoving(mag, e.rotationRate);
    const now = Date.now();
    if (moving) S.lastMoveMs = now;
    if (vic.getSettings().autoFall && S.unlocked && !S.active && !S.fallTimer) {
      if (S.fall.feed(now, mag, moving)) startFallCountdown();
    }
  }

  function startFallCountdown() {
    let n = 10;
    log('fall detected');
    vic.showFallCountdown(n);
    S.fallTimer = setInterval(() => {
      n--;
      if (n > 0) { vic.showFallCountdown(n); return; }
      cancelFall();
      startSOS('fall');
    }, 1000);
  }
  function cancelFall() {
    clearInterval(S.fallTimer);
    S.fallTimer = null;
    vic.showFallCountdown(null);
    S.fall.reset();
  }

  // ---------------------------------------------------------------- battery + wake lock
  if (navigator.getBattery) {
    navigator.getBattery().then((b) => {
      const upd = () => { S.battery = batteryQuarter(b.level); };
      upd();
      b.addEventListener('levelchange', upd);
    }).catch(() => {});
  }

  function requestWakeLock() {
    if (!navigator.wakeLock || S.wake || document.visibilityState !== 'visible') return;
    navigator.wakeLock.request('screen').then((w) => {
      S.wake = w;
      w.addEventListener('release', () => { if (S.wake === w) S.wake = null; });
    }).catch((e) => log('wake lock', e && e.message));
  }
  function releaseWakeLock() {
    const w = S.wake;
    S.wake = null;
    if (w) w.release().catch(() => {});
  }

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    if (S.ctx && S.ctx.state !== 'running') S.ctx.resume().catch(() => {});
    if (S.active) { requestWakeLock(); connectStation(); }
  });

  // ---------------------------------------------------------------- hooks
  function startSOS(trigger) {
    if (S.active) return;
    startBeacon(trigger);
    startMic();
  }

  vic.onStart(() => {
    // synchronous inside the SOS tap: unlock sound, motion and mic here
    unlockAudio();
    startMotion();
    if (S.fallTimer) cancelFall();
    startSOS('manual');
  });
  vic.onStop(() => { if (S.active) stopBeacon(); else vic.setBeacon({ on: false }); });
  vic.onCancelFall(() => cancelFall());

  let prevFall = vic.getSettings().autoFall;
  vic.onSettingsChange((s) => {
    if (s.autoFall && !prevFall) { unlockAudio(); startMotion(); } // the toggle is a tap: unlock now
    if (!s.autoFall && S.fallTimer) cancelFall();
    prevFall = s.autoFall;
    if (S.relay) S.relay.myId = s.id;
    if (S.active && S.ctx) {
      // a shorter period takes effect now; a longer one after the frame already planned
      const last = S.booked.filter((b) => b.kind === 'own').pop();
      if (last) S.nextAt = Math.min(S.nextAt, last.start + periodS(s.demoFast));
    }
  });

  // Auto-SOS on fall was left on from an earlier visit: arm it on the first tap anywhere.
  if (vic.getSettings().autoFall) {
    const once = () => {
      document.removeEventListener('click', once, true);
      if (!vic.getSettings().autoFall) return;
      unlockAudio(); startMotion();
    };
    document.addEventListener('click', once, true);
  }

  if (!root.isSecureContext) {
    setErr('https', 'Open the page from https://10.42.0.1:8443 so this phone can listen and use motion. The SOS sound still works.');
  }

  // ---------------------------------------------------------------- ?debug=1
  let dbgEl = null;
  function debugLine() {
    if (!dbgEl) {
      dbgEl = document.createElement('pre');
      dbgEl.style.cssText = 'position:fixed;left:0;right:0;bottom:0;margin:0;padding:4px 8px;font:11px/1.3 ui-monospace,monospace;' +
        'background:rgba(0,0,0,.75);color:#9f9;z-index:99;white-space:pre-wrap;pointer-events:none';
      document.body.appendChild(dbgEl);
    }
    const c = S.ctx, L = S.listen, st = S.stats;
    dbgEl.textContent =
      (c ? c.sampleRate + ' Hz ' + c.state + ' lat ' + Math.round(latencyS() * 1000) + ' ms' : 'no audio') +
      ' · mic ' + (L ? (L.starting ? 'starting' : L.mode) : LISTEN ? 'off' : 'disabled') +
      ' · ' + st.level.toFixed(0) + ' dBFS cpu ' + st.cpu.toFixed(1) + '%\n' +
      'detect ' + st.detect + ' · frames ' + st.frames + ' · echo ' + st.echo + ' · heard ' + st.heard +
      ' · relayed ' + st.relayed + (S.relay ? ' · queue ' + S.relay.pending.length + ' dropped ' + S.relay.dropped : '') +
      ' · ws ' + (S.ws ? ['connecting', 'open', 'closing', 'closed'][S.ws.readyState] : '-') +
      (IOS ? ' · iOS' : '') + (navigator.audioSession ? ' session ' + navigator.audioSession.type : '');
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
