// node web/tests/test_relay_only.mjs : runs the browser half of victim-logic.js in node with fake browser objects.
// Normal mode beacons every ~8 s; ?mode=relay (SPEC v1.3) sends no own frames but still relays (hop 1, 2 bands up).
import vm from 'vm';
import fs from 'fs';
const WEB = process.argv[2] || new URL('..', import.meta.url).pathname.replace(/\/$/, '');

function run(search, seconds) {
  let now = 0, tickFn = null, startCb = null;
  const plays = [], beacons = [], errors = {};
  const ctx = {
    currentTime: 0, sampleRate: 48000, state: 'running', destination: {}, baseLatency: 0.01, outputLatency: 0.02,
    resume() { return Promise.resolve(); },
    createBuffer(ch, n, fs) { return { getChannelData: () => new Float32Array(n), copyToChannel() {} }; },
    createBufferSource() { return { connect() {}, start(at) { plays.push(at); }, stop() {} }; },
  };
  const sandbox = {
    console: { log() {}, warn() {}, error: console.error },
    location: { search, protocol: 'https:' },
    navigator: { userAgent: 'node', platform: 'Linux', maxTouchPoints: 0 },
    document: { addEventListener() {}, removeEventListener() {}, visibilityState: 'visible', createElement: () => ({ style: {} }), body: { appendChild() {} } },
    isSecureContext: true,
    AudioContext: function () { return ctx; },
    setInterval: (fn) => { tickFn = fn; return 1; }, clearInterval() {}, setTimeout: (fn) => 0, clearTimeout() {},
    WebSocket: function () { return { close() {}, send() {}, readyState: 0 }; },
    Date: { now: () => now * 1000 },
    Math, URLSearchParams, Float32Array, Uint8Array, Map, Set, Promise, Object, Array, Number, String, JSON, Infinity, isFinite,
    HeimdallVictim: {
      getSettings: () => ({ id: '1A2B', floor: null, people: 1, status: 'injured', relay: true, autoFall: false, demoFast: true }),
      onStart: (cb) => { startCb = cb; }, onStop() {}, onCancelFall() {}, onSettingsChange() {},
      setBeacon: (s) => beacons.push(s), setMicLevel() {}, setMotion() {}, logHeard() {}, logRelayed() {},
      showKnock() {}, showFallCountdown() {}, showError: (m) => { errors.last = m; },
    },
  };
  sandbox.globalThis = sandbox; sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(WEB + '/js/heimdall-modem.js', 'utf8'), sandbox);
  vm.runInContext(fs.readFileSync(WEB + '/js/victim-logic.js', 'utf8'), sandbox);
  startCb();                                   // the SOS tap
  const S = sandbox.HeimdallVictimLive;
  let offered = false;
  for (now = 0; now <= seconds; now += 0.25) {
    ctx.currentTime = now;
    if (!offered && now >= 20) {               // a frame from 77C1 heard on band 2 at t = 20 s
      S.relay.offer({ id: '77C1', floor: null, minutes: 3, motion: false, status: 'critical', people: 1, battery: 2, hops: 0, knock: false }, 2, now);
      offered = true;
    }
    tickFn();
  }
  const relays = S.booked.filter((b) => b.kind === 'relay');
  return { plays: plays.length, own: S.sent, relays: relays.map((b) => ({ id: b.id, hops: b.hops, band: b.band })), last: beacons[beacons.length - 1], err: errors.last };
}

const normal = run('', 40);
const relayOnly = run('?mode=relay', 40);
console.log('normal    :', JSON.stringify(normal));
console.log('relay only:', JSON.stringify(relayOnly));
const ok = normal.own >= 4 && relayOnly.own === 0 && relayOnly.plays === 2 && relayOnly.relays.length === 1 &&
  relayOnly.relays[0].hops === 1 && relayOnly.relays[0].band === 0 && /Relay only/.test(relayOnly.err || '') &&
  relayOnly.last && relayOnly.last.nextInSec === undefined;
console.log(ok ? 'PASS' : 'FAIL');
process.exit(ok ? 0 : 1);
