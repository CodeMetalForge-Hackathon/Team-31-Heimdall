// Node helper for the cross-language tests (driven by modem/tests/test_cross.py).
//   node modem/tests/js_tool.mjs gen <outdir>          -> js_frame_b<band>.wav (48 kHz) + js_frames.json
//   node modem/tests/js_tool.mjs decode <wav> [...]    -> one JSON line per frame: {file, ...frame}
//   node modem/tests/js_tool.mjs candidates <wav>      -> one JSON line per preamble detection
import { createRequire } from 'module';
import fs from 'fs';
import path from 'path';

const require = createRequire(import.meta.url);
const HM = require('../../web/js/heimdall-modem.js');

export function writeWav(file, x, rate) {
  const n = x.length, buf = Buffer.alloc(44 + 2 * n);
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + 2 * n, 4); buf.write('WAVE', 8);
  buf.write('fmt ', 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22);
  buf.writeUInt32LE(rate, 24); buf.writeUInt32LE(rate * 2, 28); buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34);
  buf.write('data', 36); buf.writeUInt32LE(2 * n, 40);
  for (let i = 0; i < n; i++) buf.writeInt16LE(Math.round(Math.max(-1, Math.min(1, x[i])) * 32767), 44 + 2 * i);
  fs.writeFileSync(file, buf);
}

export function readWav(file) {
  const b = fs.readFileSync(file);
  if (b.toString('ascii', 0, 4) !== 'RIFF' || b.toString('ascii', 8, 12) !== 'WAVE') throw new Error('not a WAV');
  let p = 12, fmt = null, data = null;
  while (p + 8 <= b.length) {
    const id = b.toString('ascii', p, p + 4), size = b.readUInt32LE(p + 4);
    if (id === 'fmt ') fmt = { tag: b.readUInt16LE(p + 8), ch: b.readUInt16LE(p + 10), rate: b.readUInt32LE(p + 12), bits: b.readUInt16LE(p + 22) };
    if (id === 'data') data = b.subarray(p + 8, p + 8 + size);
    p += 8 + size + (size & 1);
  }
  const bytes = fmt.bits / 8, n = Math.floor(data.length / (bytes * fmt.ch)), x = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const o = i * bytes * fmt.ch;
    x[i] = fmt.tag === 3 ? data.readFloatLE(o) : fmt.bits === 16 ? data.readInt16LE(o) / 32768 : data.readInt32LE(o) / 2147483648;
  }
  return { x, rate: fmt.rate };
}

export function decodeFile(file, chunk = 4096) {
  const { x, rate } = readWav(file);
  const d = new HM.Decoder(rate);
  let out = [];
  for (let i = 0; i < x.length; i += chunk) out = out.concat(d.feed(x.subarray(i, i + chunk)));
  out = out.concat(d.flush());
  return { frames: out, decoder: d, rate, seconds: x.length / rate };
}

const FIELDS = [
  { id: '1A2B', floor: 2, minutes: 14, motion: true, status: 'injured', people: 2, battery: 3, hops: 0, knock: false },
  { id: '77C1', floor: null, minutes: 60, motion: false, status: 'critical', people: 1, battery: 1, hops: 1, knock: true },
  { id: 'B002', floor: -1, minutes: 126, motion: true, status: 'ok', people: 7, battery: 0, hops: 3, knock: false },
  { id: 'FFFF', floor: 29, minutes: 0, motion: false, status: 'no_response', people: 0, battery: 2, hops: 2, knock: true },
];

const [cmd, ...args] = process.argv.slice(2);
if (cmd === 'gen') {
  const dir = args[0], rate = 48000, meta = [];
  fs.mkdirSync(dir, { recursive: true });
  for (let band = 0; band < 4; band++) {
    const raw = HM.pack(FIELDS[band]), s = HM.synth(raw, band, rate);
    const x = new Float32Array(Math.round(0.5 * rate) * 2 + s.length);
    x.set(s, Math.round(0.5 * rate));
    const file = path.join(dir, `js_frame_b${band}.wav`);
    writeWav(file, x, rate);
    meta.push({ file, band, raw: HM.toHex(raw), fields: FIELDS[band] });
  }
  fs.writeFileSync(path.join(dir, 'js_frames.json'), JSON.stringify(meta, null, 1));
  console.log(JSON.stringify(meta));
} else if (cmd === 'decode') {
  for (const file of args) {
    const { frames } = decodeFile(file);
    for (const f of frames) console.log(JSON.stringify({ file, ...HM.frameToJSON(f) }));
  }
} else if (cmd === 'candidates') {
  const { decoder } = decodeFile(args[0]);
  for (const c of decoder.candidates) console.log(JSON.stringify(c));
}
