// Victim page logic tests:  node web/tests/test_victim_logic.mjs
import { createRequire } from 'module';
import assert from 'assert/strict';

const require = createRequire(import.meta.url);
const HM = require('../js/heimdall-modem.js');
const V = require('../js/victim-logic.js');

let failed = 0, passed = 0;
function test(name, fn) {
  const t0 = Date.now();
  try { fn(); passed++; console.log(`ok   ${name} (${Date.now() - t0} ms)`); }
  catch (e) { failed++; console.log(`FAIL ${name}\n     ${e.stack.split('\n').slice(0, 3).join('\n     ')}`); }
}
function seq(...vals) { let i = 0; return () => vals[i++ % vals.length]; }

const SETTINGS = { id: '1A2B', floor: 2, people: 2, status: 'injured', relay: true, autoFall: false, demoFast: true };

test('payload: test vector 1 from settings', () => {
  const start = 1_000_000;
  const f = V.buildFields(SETTINGS, { startMs: start, nowMs: start + 15 * 60000 - 1, lastMoveMs: start + 15 * 60000 - 5000, battery: 3 });
  assert.deepEqual(f, { id: '1A2B', floor: 2, minutes: 14, motion: true, status: 'injured', people: 2, battery: 3, hops: 0, knock: false });
  assert.equal(HM.toHex(HM.pack(f)), '1A2B20F96066');
});

test('payload: unknown floor, no motion yet, minutes from SOS start', () => {
  const s = Object.assign({}, SETTINGS, { floor: null, status: 'no_response', people: 1 });
  const f = V.buildFields(s, { startMs: 0, nowMs: 125_000, lastMoveMs: null, battery: 1 });
  assert.equal(f.floor, null); assert.equal(f.minutes, 2); assert.equal(f.motion, false); assert.equal(f.battery, 1);
  const back = HM.unpack(HM.pack(f));
  assert.equal(back.floor, null); assert.equal(back.status, 'no_response');
});

test('motion window: 20 s in demo mode, 60 s in normal mode', () => {
  const st = (ago) => ({ startMs: 0, nowMs: 100_000, lastMoveMs: 100_000 - ago, battery: 3 });
  assert.equal(V.buildFields(SETTINGS, st(19_000)).motion, true);
  assert.equal(V.buildFields(SETTINGS, st(21_000)).motion, false);
  const slow = Object.assign({}, SETTINGS, { demoFast: false });
  assert.equal(V.buildFields(slow, st(59_000)).motion, true);
  assert.equal(V.buildFields(slow, st(61_000)).motion, false);
});

test('battery quarters and mic meter', () => {
  assert.equal(V.batteryQuarter(1), 3); assert.equal(V.batteryQuarter(0.8), 3); assert.equal(V.batteryQuarter(0.74), 2);
  assert.equal(V.batteryQuarter(0.3), 1); assert.equal(V.batteryQuarter(0.1), 0); assert.equal(V.batteryQuarter(undefined), 3);
  assert.equal(V.levelToMeter(-80), 0); assert.equal(V.levelToMeter(-35), 0.5); assert.equal(V.levelToMeter(0), 1);
});

test('schedule: period 8 s / 30 s with ±1 s jitter, band (k + id) % 4', () => {
  assert.equal(V.nextDelayS(true, () => 0.5), 8);
  assert.equal(V.nextDelayS(true, () => 0), 7);
  assert.ok(Math.abs(V.nextDelayS(true, () => 0.999999) - 9) < 1e-5);
  assert.equal(V.nextDelayS(false, () => 0.5), 30);
  // 0x1A2B % 4 = 3
  assert.deepEqual([0, 1, 2, 3, 4].map((k) => HM.bandFor(k, '1A2B')), [3, 0, 1, 2, 3]);
});

test('motion sample: still, shaken, rotated', () => {
  assert.equal(V.isMoving(9.81, { alpha: 0, beta: 1, gamma: -2 }), false);
  assert.equal(V.isMoving(10.8, null), true);
  assert.equal(V.isMoving(9.9, { alpha: 0, beta: -25, gamma: 0 }), true);
  assert.equal(V.isMoving(9.2, null), false);
});

test('relay: own id, hops 3, holdoff 30 s, already pending', () => {
  const q = new V.RelayQueue('1A2B', () => 0);
  const f = { id: '77C1', hops: 0 };
  assert.equal(q.offer({ id: '1A2B', hops: 0 }, 1, 0), 'own');
  assert.equal(q.offer({ id: '5E09', hops: 3 }, 1, 0), 'hops');
  assert.equal(q.offer(f, 2, 0), 'queued');
  assert.equal(q.offer(f, 2, 0.5), 'pending');
  assert.deepEqual(q.take(1.0), []);
  const out = q.take(1.5);
  assert.equal(out.length, 1);
  assert.equal(out[0].fields.hops, 1); assert.equal(out[0].band, 0); assert.equal(out[0].rxBand, 2);   // (2 + 2) % 4, SPEC v1.2
  assert.equal(q.offer(f, 2, 20), 'holdoff');
  assert.equal(q.offer(f, 2, 31.6), 'queued');
});

test('relay: wait is 1.5..4 s and restarts on a preamble, dropped after 3 restarts', () => {
  const q = new V.RelayQueue('1A2B', seq(0, 1));
  q.offer({ id: '77C1', hops: 1 }, 3, 10);
  assert.equal(q.pending[0].due, 11.5);
  q.preamble(9.9, 10.5);              // ended before the wait began: no effect
  assert.equal(q.pending[0].due, 11.5);
  q.preamble(10.6, 11.0);             // heard during the wait: new wait from now, 4.0 s
  assert.equal(q.pending[0].due, 15.0);
  q.preamble(11.5, 12.0); q.preamble(12.5, 13.0);
  assert.equal(q.pending.length, 1);
  q.preamble(13.5, 14.0);             // 4th preamble: give up
  assert.equal(q.pending.length, 0);
  assert.equal(q.dropped, 1);
  assert.equal(q.offer({ id: '77C1', hops: 1 }, 3, 15), 'queued'); // dropped, never sent: no holdoff
});

test('relay timing: never on top of our own frame, never 2.5 s before our next beacon', () => {
  const F = V.FRAME_S;
  // own frame playing 10.0..12.13 -> relay after it
  assert.ok(Math.abs(V.planRelay(11, [{ start: 10, end: 10 + F }], 18) - (10 + F + 0.1)) < 1e-9);
  // own beacon due in 2 s -> relay right after that beacon
  assert.ok(Math.abs(V.planRelay(16, [], 18) - (18 + F + 0.1)) < 1e-9);
  // own beacon due in 3 s -> relay now (ends before it starts)
  assert.equal(V.planRelay(15, [], 18), 15);
  // two relays back to back don't overlap
  const a = V.planRelay(5, [], 30);
  const b = V.planRelay(5, [{ start: a, end: a + F }], 30);
  assert.ok(b >= a + F);
  // own beacon slides past a booked relay
  assert.ok(Math.abs(V.planOwn(20, [{ start: 19, end: 19 + F }]) - (19 + F + 0.1)) < 1e-9);
});

test('echo window: decodes overlapping our own frame (+latency +150 ms) are ignored', () => {
  const F = V.FRAME_S, booked = [{ start: 10, end: 10 + F }];
  assert.equal(V.overlapsOwn(10.1, 10.1 + F, booked, 0.1), true);     // our own frame, heard late
  assert.equal(V.overlapsOwn(12.3, 12.3 + F, booked, 0.1), true);     // starts 40 ms after ours ends + lat
  assert.equal(V.overlapsOwn(12.5, 12.5 + F, booked, 0.1), false);
  assert.equal(V.overlapsOwn(7.0, 7.0 + F, booked, 0.1), false);
});

test('echo: only a decode that matches a frame we played (id, hops, band) is dropped', () => {
  const F = V.FRAME_S;
  const booked = [{ start: 10, end: 10 + F, id: '77C1', hops: 1, band: 0 }];   // our relay of 77C1
  assert.equal(V.isOwnEcho({ id: '77C1', hops: 1, band: 0 }, 10.1, 10.1 + F, booked, 0.1), true);
  assert.equal(V.isOwnEcho({ id: '77C1', hops: 0, band: 2 }, 10.1, 10.1 + F, booked, 0.1), false); // the original
  assert.equal(V.isOwnEcho({ id: '5E09', hops: 0, band: 1 }, 10.5, 10.5 + F, booked, 0.1), false); // another phone
  assert.equal(V.isOwnEcho({ id: '77C1', hops: 1, band: 0 }, 13.0, 13.0 + F, booked, 0.1), false); // too late
});

test('fall: free fall, impact, stillness -> fall; a hop or a shake is not', () => {
  const run = (samples) => {
    const d = new V.FallDetector();
    let hit = null;
    for (const [t, a, m] of samples) if (d.feed(t, a, m) && hit === null) hit = t;
    return hit;
  };
  const still = (t0, t1) => { const o = []; for (let t = t0; t <= t1; t += 20) o.push([t, 9.81, false]); return o; };
  const ff = (t0, ms) => { const o = []; for (let t = t0; t < t0 + ms; t += 20) o.push([t, 0.5, true]); return o; };
  const fall = [...still(0, 500), ...ff(520, 400), [920, 40, true], [940, 18, true], [960, 12, true], ...still(980, 4000)];
  const t = run(fall);
  assert.ok(t !== null && t >= 980 + 2000 && t < 980 + 2400, 'fall at ' + t);
  // free fall too short (40 ms)
  assert.equal(run([...still(0, 500), ...ff(520, 40), [560, 40, true], ...still(580, 4000)]), null);
  // impact too late (1.2 s after the free fall)
  assert.equal(run([...still(0, 500), ...ff(520, 200), ...still(720, 1900), [1940, 40, true], ...still(1960, 5000)]), null);
  // fall but the person keeps moving for 8 s
  const moving = []; for (let t = 980; t < 9500; t += 20) moving.push([t, 11, true]);
  assert.equal(run([...still(0, 500), ...ff(520, 400), [920, 40, true], ...moving]), null);
});

test('end to end: decode A, relay it as hop 1 two bands up, decode the relay', () => {
  const fs = 16000;
  const A = { id: '77C1', floor: null, minutes: 60, motion: false, status: 'critical', people: 1, battery: 1, hops: 0, knock: true };
  const bandA = HM.bandFor(0, A.id);
  const dec = new HM.Decoder(fs);
  const lead = new Float32Array(fs / 2);
  const rx = [...dec.feed(lead), ...dec.feed(HM.synth(HM.pack(A), bandA, fs)), ...dec.flush()];
  assert.equal(rx.length, 1);
  const q = new V.RelayQueue('1A2B', () => 0.5);
  assert.equal(q.offer(rx[0].fields, rx[0].band, 0), 'queued');
  const [r] = q.take(10);
  assert.equal(r.band, (bandA + 2) % 4);
  const dec2 = new HM.Decoder(48000);
  const rx2 = [...dec2.feed(new Float32Array(24000)), ...dec2.feed(HM.synth(HM.pack(r.fields), r.band, 48000)), ...dec2.flush()];
  assert.equal(rx2.length, 1);
  assert.deepEqual(rx2[0].fields, Object.assign({}, A, { hops: 1 }));
  assert.equal(rx2[0].band, r.band);
});

test('relay-only phone (holdoff 0) passes on every frame; a normal phone holds off 30 s', () => {
  const c = new V.RelayQueue('C', () => 0, 0);
  assert.equal(c.offer({ id: '1429', hops: 0 }, 0, 0), 'queued');
  assert.equal(c.take(2).length, 1);
  assert.equal(c.offer({ id: '1429', hops: 0 }, 1, 8), 'queued', 'no hold-off: the next frame is relayed too');
  const n = new V.RelayQueue('B', () => 0);
  assert.equal(n.offer({ id: '1429', hops: 0 }, 0, 0), 'queued');
  n.take(2);
  assert.equal(n.offer({ id: '1429', hops: 0 }, 1, 8), 'holdoff');
});

test('relay: the several detections of one frame restart the wait once, not three times', () => {
  const q = new V.RelayQueue('1A2B', () => 0);
  q.offer({ id: '77C1', hops: 0 }, 3, 10);          // due 11.5
  q.preamble(10.6, 11.0);                          // the frame's preamble: new wait, due 12.5
  assert.equal(q.pending[0].due, 12.5);
  q.preamble(10.9, 11.3); q.preamble(11.2, 11.6);  // leakage and data symbols of the same frame: nothing
  assert.equal(q.pending[0].rewaits, 1);
  assert.equal(q.pending[0].due, 12.5);
  q.preamble(12.1, 12.4);                          // a second frame: counts again
  assert.equal(q.pending[0].rewaits, 2);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
