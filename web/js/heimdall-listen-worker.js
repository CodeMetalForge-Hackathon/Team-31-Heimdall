/* HEIMDALL listen worker: runs the HEIMDALL-AC1 decoder off the main thread.
 * In:  {type:'init', rate, port?}   port = MessageChannel end fed by heimdall-tap-worklet.js
 *      {type:'audio', x, f0}        (ScriptProcessor fallback) f0 = context frame of x[0]
 * Out: {type:'frame', f, tc}        f = HeimdallModem.frameToJSON(frame), tc = context time of the preamble end
 *      {type:'detect', band, tc, snr_db}   a preamble was detected (before it is decoded, ~0.5 s latency)
 *      {type:'stats', level, cpu}    every 150 ms: input level in dBFS, decoder share of real time in %
 * Context time = AudioContext.currentTime of the matching sample, so the page can line up what it
 * hears with what it played.
 */
importScripts('heimdall-modem.js');

let dec = null, rate = 48000;
let fed = 0;            // input samples fed to the decoder so far
const chunks = [];      // recent {pos, f0, n}: decoder sample position -> context frame
let busy = 0, secs = 0, lastStats = 0;
const reported = new Map(); // detection key -> decoder sample position, so each is posted once

// decoder time (s since the first sample) -> AudioContext time (s)
function ctxTime(t) {
  const idx = t * rate;
  for (let i = chunks.length - 1; i >= 0; i--) {
    const c = chunks[i];
    if (idx >= c.pos || i === 0) return (c.f0 + idx - c.pos) / rate;
  }
  return idx / rate;
}

function handle(x, f0) {
  if (!dec) return;
  chunks.push({ pos: fed, f0: f0, n: x.length });
  fed += x.length;
  while (chunks.length > 1 && fed - chunks[0].pos > 12 * rate) chunks.shift();

  const t0 = performance.now();
  const frames = dec.feed(x);
  busy += performance.now() - t0;
  secs += x.length / rate;

  // New preamble detections (internal queue of the decoder; each waits there ~2 s for its symbols).
  const DFS = HeimdallModem.SPEC.DECODE_FS, NPRE = Math.round(HeimdallModem.SPEC.PREAMBLE_S * DFS);
  for (const p of dec._pending) {
    const key = p.band + ':' + p.start;
    if (reported.has(key)) continue;
    reported.set(key, p.start);
    const t = (p.start + NPRE + p.frac) / DFS;
    postMessage({ type: 'detect', band: p.band, tc: ctxTime(t),
      snr_db: Math.round(200 * Math.log10(p.peak / Math.max(p.median, 1.25e-4))) / 10 });
  }
  if (reported.size > 64) {
    const cut = fed / rate * DFS - 10 * DFS;
    for (const [k, s] of reported) if (s < cut) reported.delete(k);
  }

  for (const fr of frames) {
    postMessage({ type: 'frame', f: HeimdallModem.frameToJSON(fr), tc: ctxTime(fr.t_end_preamble) });
  }

  const now = performance.now();
  if (now - lastStats > 150) {
    lastStats = now;
    postMessage({ type: 'stats', level: dec.level_db, cpu: busy / 10 / Math.max(secs, 1e-9) });
  }
}

onmessage = (e) => {
  const d = e.data;
  if (d.type === 'init') {
    rate = d.rate;
    dec = new HeimdallModem.Decoder(rate);
    if (d.port) d.port.onmessage = (m) => handle(m.data.x, m.data.f0);
  } else if (d.type === 'audio') {
    handle(d.x, d.f0);
  }
};
