// JS modem tests:  node modem/tests/test_js.mjs
import { createRequire } from 'module';
import assert from 'assert/strict';

const require = createRequire(import.meta.url);
const HM = require('../../web/js/heimdall-modem.js');

let failed = 0, passed = 0;
function test(name, fn) {
  const t0 = Date.now();
  try { fn(); passed++; console.log(`ok   ${name} (${Date.now() - t0} ms)`); }
  catch (e) { failed++; console.log(`FAIL ${name}\n     ${e.stack.split('\n').slice(0, 3).join('\n     ')}`); }
}

// deterministic RNG (mulberry32) + gaussian
function rng(seed) {
  let a = seed >>> 0;
  const u = () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const g = () => Math.sqrt(-2 * Math.log(u() + 1e-300)) * Math.cos(2 * Math.PI * u());
  return { u, g, int: (n) => Math.floor(u() * n) };
}

function randomFields(r) {
  const floor = r.int(32) - 2;
  return {
    id: r.int(65536).toString(16).toUpperCase().padStart(4, '0'),
    floor: floor === -2 ? null : floor, minutes: r.int(64) * 2, motion: r.u() < 0.5,
    status: HM.SPEC.STATUS[r.int(4)], people: r.int(8), battery: r.int(4), hops: r.int(4), knock: r.u() < 0.5,
  };
}

const V1 = { id: '1A2B', floor: 2, minutes: 14, motion: true, status: 'injured', people: 2, battery: 3, hops: 0, knock: false };
const V2 = { id: '77C1', floor: null, minutes: 61, motion: false, status: 'critical', people: 1, battery: 1, hops: 1, knock: true };

test('CRC-8 check value 0xF4', () => {
  assert.equal(HM.crc8(new TextEncoder().encode('123456789')), 0xF4);
});

test('SPEC test vector 1', () => {
  const b = HM.pack(V1);
  assert.equal(HM.toHex(b), '1A2B20F96066');
  assert.equal(HM.toBits(b).join(''), '000110100010101100100000111110010110000001100110');
  assert.deepEqual(HM.unpack(b), V1);
});

test('SPEC test vector 2', () => {
  const b = HM.pack(V2);
  assert.equal(HM.toHex(b), '77C103CCACEA');
  assert.deepEqual(HM.unpack(b), { ...V2, minutes: 60 });   // 61 min -> min2 30 -> 60
});

test('bad CRC -> null', () => {
  const b = HM.pack(V1);
  for (let i = 0; i < 48; i++) {
    const c = b.slice(); c[i >> 3] ^= 0x80 >> (i & 7);
    assert.equal(HM.unpack(c), null);
  }
  assert.equal(HM.unpack(new Uint8Array(5)), null);
});

test('pack/unpack round-trip, 1000 random field sets', () => {
  const r = rng(42);
  for (let i = 0; i < 1000; i++) {
    const f = randomFields(r), b = HM.pack(f);
    assert.equal(b.length, 6);
    assert.deepEqual(HM.unpack(b), f);
    assert.deepEqual(Array.from(HM.fromBits(HM.toBits(b))), Array.from(b));
  }
});

test('synth: length, peak, phase restart', () => {
  for (const fs of [16000, 44100, 48000]) {
    const x = HM.synth(HM.pack(V1), 1, fs);
    assert.equal(x.length, Math.ceil(2.13 * fs - 1e-9));
    let pk = 0; for (const v of x) pk = Math.max(pk, Math.abs(v));
    assert.ok(pk <= 0.8 + 1e-6 && pk > 0.79, `peak ${pk}`);
    assert.equal(x[0], 0);
    assert.equal(x[Math.round(0.2 * fs)], 0);                        // gap
  }
});

function stream(r, frames, bands, fs, snrDb) {
  const parts = [], truth = [];
  let pos = Math.round(fs * 0.8), total = pos;
  const waves = frames.map((raw, i) => HM.synth(raw, bands[i], fs));
  const starts = waves.map((w) => { const s = total; total += w.length + Math.round(fs * (0.8 + r.u() * 0.8)); return s; });
  const x = new Float32Array(total + fs);
  let p = 0;
  waves.forEach((w, i) => { x.set(w, starts[i]); for (const v of w) p += v * v; truth.push({ hex: HM.toHex(frames[i]), t: starts[i] / fs + 0.2 }); });
  p /= waves.reduce((a, w) => a + w.length, 0);
  if (snrDb !== undefined) { const s = Math.sqrt(p / 10 ** (snrDb / 10)); for (let i = 0; i < x.length; i++) x[i] += s * r.g(); }
  return { x, truth };
}

function decodeAll(x, fs, r) {
  const d = new HM.Decoder(fs);
  let out = [];
  for (let i = 0; i < x.length;) { const n = 256 + r.int(4000); out = out.concat(d.feed(x.subarray(i, i + n))); i += n; }
  return out.concat(d.flush());
}

test('decode clean frames, all bands, 16/44.1/48 kHz, random chunking', () => {
  const r = rng(7);
  for (const fs of [16000, 44100, 48000]) {
    const frames = [], bands = [];
    for (let b = 0; b < 4; b++) { frames.push(HM.pack(randomFields(r))); bands.push(b); }
    const { x, truth } = stream(r, frames, bands, fs);
    const got = decodeAll(x, fs, r);
    assert.deepEqual(got.map((f) => f.rawHex), truth.map((t) => t.hex), `fs ${fs}`);
    got.forEach((f, i) => assert.ok(Math.abs(f.t_end_preamble - truth[i].t) < 0.001, `t ${f.t_end_preamble} vs ${truth[i].t}`));
    got.forEach((f, i) => assert.equal(f.band, bands[i]));
  }
});

test('decode at 0 dB SNR (full band), 10 frames per band', () => {
  const r = rng(9);
  for (let b = 0; b < 4; b++) {
    const frames = Array.from({ length: 10 }, () => HM.pack(randomFields(r)));
    const { x, truth } = stream(r, frames, frames.map(() => b), 16000, 0);
    const got = decodeAll(x, 16000, r).map((f) => f.rawHex);
    const hits = truth.filter((t) => got.includes(t.hex)).length;
    assert.ok(hits >= 9, `band ${b}: ${hits}/10`);
    assert.ok(got.every((h) => truth.some((t) => t.hex === h)), 'wrong frame passed CRC');
  }
});

test('silence and pure noise -> no frames', () => {
  const r = rng(3), fs = 48000, x = new Float32Array(fs * 20);
  assert.equal(decodeAll(x, fs, r).length, 0);
  for (let i = 0; i < x.length; i++) x[i] = 0.1 * r.g();
  assert.equal(decodeAll(x, fs, r).length, 0);
});

test('decoder speed (48 kHz input)', () => {
  const r = rng(5), fs = 48000;
  const { x } = stream(r, [HM.pack(V1), HM.pack(V2)], [1, 2], fs, 10);
  const t0 = process.hrtime.bigint();
  decodeAll(x, fs, r);
  const ms = Number(process.hrtime.bigint() - t0) / 1e6, sec = x.length / fs;
  console.log(`     ${sec.toFixed(1)} s of 48 kHz audio in ${ms.toFixed(0)} ms = ${(100 * ms / 1000 / sec).toFixed(2)}% of one core`);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
