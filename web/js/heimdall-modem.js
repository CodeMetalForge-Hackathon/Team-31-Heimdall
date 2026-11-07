/*
 * HEIMDALL-AC1 chirp modem: JS port of modem/heimdall_ac1.py (docs/SPEC.md section 1).
 *
 * Plain JS, no dependencies, no DOM. Works in the browser (window, Web Worker,
 * AudioWorklet) and in Node. Exposes globalThis.HeimdallModem and module.exports.
 *
 *   HeimdallModem.pack(fields)                -> Uint8Array(6)
 *   HeimdallModem.unpack(u8)                  -> fields | null   (null on bad CRC)
 *   HeimdallModem.crc8(u8)                    -> int
 *   HeimdallModem.synth(u8, band, sampleRate) -> Float32Array (2.130 s)
 *   new HeimdallModem.Decoder(sampleRate).feed(Float32Array) -> frames[]
 *       frame = {fields, raw (Uint8Array), rawHex, band, snr_db, t_end_preamble,
 *                sample_index, quality}  -- plain object, safe to postMessage
 *   HeimdallModem.SPEC                        -> constants
 *
 * The receiver mirrors the Python reference step for step; see the header there.
 */
(function (root) {
  'use strict';

  // ------------------------------------------------------------ SPEC constants
  var BANDS = [[1500, 2500], [2500, 3500], [3500, 4500], [5000, 6500]];
  var PREAMBLE_S = 0.200, GAP_S = 0.010, SYMBOL_S = 0.040, N_SYMBOLS = 48;
  var PREAMBLE_RAMP_S = 0.005, SYMBOL_RAMP_S = 0.002, AMPLITUDE = 0.8;
  var FRAME_S = PREAMBLE_S + GAP_S + N_SYMBOLS * SYMBOL_S;
  var DECODE_FS = 16000, DETECT_RATIO = 8.0, MEDIAN_WINDOW_S = 2.0;
  var STATUS = ['no_response', 'ok', 'injured', 'critical'];

  // ------------------------------------------------------------ receiver tuning
  var BP_MARGIN_HZ = 200, BP_ORDER = 4, PAD = 64;
  var MF_NFFT = 8192, SYM_NFFT = 32768, RHO_NFFT = 4096;
  var NMS_GUARD = 4000, MEDIAN_STRIDE = 8;
  var SEARCH_W = 72, INTERCEPT_MAX = 24, N_SLOPES = 25, SLOPE_MAX = 0.0015 * 640, REFINE = 4;
  var ABS_FLOOR = 1e-3, MIN_QUALITY = 0.20, MIN_RHO = 0.25;

  var N_PRE = Math.round(PREAMBLE_S * DECODE_FS);   // 3200
  var N_GAP = Math.round(GAP_S * DECODE_FS);        // 160
  var N_SYM = Math.round(SYMBOL_S * DECODE_FS);     // 640
  var N_FRAME = N_PRE + N_GAP + N_SYMBOLS * N_SYM;  // 34080
  var MEDIAN_N = MEDIAN_WINDOW_S * DECODE_FS;       // 32000

  // ------------------------------------------------------------ payload
  function crc8(data) {
    var crc = 0;
    for (var i = 0; i < data.length; i++) {
      crc ^= data[i] & 0xFF;
      for (var k = 0; k < 8; k++) crc = crc & 0x80 ? ((crc << 1) ^ 0x07) & 0xFF : (crc << 1) & 0xFF;
    }
    return crc;
  }

  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }

  function pack(f) {
    var id = typeof f.id === 'string' ? parseInt(f.id, 16) : f.id | 0;
    if (!(id >= 0 && id <= 0xFFFF)) throw new Error('id out of range: ' + f.id);
    var floorCode = 0;
    if (f.floor !== null && f.floor !== undefined) {
      floorCode = (f.floor | 0) + 2;
      if (floorCode < 1 || floorCode > 31) throw new Error('floor must be -1..29 or null');
    }
    var min2 = clamp(Math.floor((f.minutes | 0) / 2), 0, 63);
    var st = f.status === undefined ? 0 : typeof f.status === 'string' ? STATUS.indexOf(f.status) : f.status | 0;
    if (st < 0 || st > 3) throw new Error('bad status ' + f.status);
    // 40-bit P: high 16 bits = id, low 24 bits = everything else
    var lo = (floorCode << 19) | (min2 << 13) | ((f.motion ? 1 : 0) << 12) | (st << 10) |
      (clamp(f.people | 0, 0, 7) << 7) | (clamp(f.battery | 0, 0, 3) << 5) |
      (clamp(f.hops | 0, 0, 3) << 3) | ((f.knock ? 1 : 0) << 2);
    var b = new Uint8Array(6);
    b[0] = id >> 8; b[1] = id & 0xFF; b[2] = (lo >> 16) & 0xFF; b[3] = (lo >> 8) & 0xFF; b[4] = lo & 0xFF;
    b[5] = crc8(b.subarray(0, 5));
    return b;
  }

  function unpack(b) {
    if (!b || b.length !== 6 || crc8(Array.prototype.slice.call(b, 0, 5)) !== b[5]) return null;
    var id = (b[0] << 8) | b[1];
    var lo = (b[2] << 16) | (b[3] << 8) | b[4];
    var floorCode = (lo >> 19) & 0x1F;
    var hex = id.toString(16).toUpperCase();
    while (hex.length < 4) hex = '0' + hex;
    return {
      id: hex,
      floor: floorCode === 0 ? null : floorCode - 2,
      minutes: ((lo >> 13) & 0x3F) * 2,
      motion: !!((lo >> 12) & 1),
      status: STATUS[(lo >> 10) & 3],
      people: (lo >> 7) & 7,
      battery: (lo >> 5) & 3,
      hops: (lo >> 3) & 3,
      knock: !!((lo >> 2) & 1)
    };
  }

  function toBits(b) {
    var out = [];
    for (var i = 0; i < b.length; i++) for (var k = 7; k >= 0; k--) out.push((b[i] >> k) & 1);
    return out;
  }

  function fromBits(bits) {
    var out = new Uint8Array(bits.length >> 3);
    for (var i = 0; i < out.length; i++) {
      var v = 0;
      for (var k = 0; k < 8; k++) v = (v << 1) | (bits[i * 8 + k] ? 1 : 0);
      out[i] = v;
    }
    return out;
  }

  function toHex(b) {
    var s = '';
    for (var i = 0; i < b.length; i++) s += (b[i] < 16 ? '0' : '') + b[i].toString(16).toUpperCase();
    return s;
  }

  // ------------------------------------------------------------ waveform
  function rampW(tau, T, ramp) {
    if (tau < ramp) return 0.5 - 0.5 * Math.cos(Math.PI * tau / ramp);
    if (tau > T - ramp) return 0.5 - 0.5 * Math.cos(Math.PI * (T - tau) / ramp);
    return 1;
  }

  function chirpPhase(tau, T, f0, f1) {
    return 2 * Math.PI * (f0 * tau + (f1 - f0) * tau * tau / (2 * T));
  }

  /** 6-byte frame -> Float32Array at sampleRate (continuous-time math per SPEC 1.2). */
  function synth(frame, band, fs) {
    var lo = BANDS[band][0], hi = BANDS[band][1];
    var bits = toBits(frame);
    if (bits.length !== N_SYMBOLS) throw new Error('frame must be 6 bytes');
    var n = Math.ceil(FRAME_S * fs - 1e-9);
    var out = new Float32Array(n);
    var data0 = PREAMBLE_S + GAP_S;
    for (var i = 0; i < n; i++) {
      var t = i / fs, v = 0;
      if (t < PREAMBLE_S) {
        v = rampW(t, PREAMBLE_S, PREAMBLE_RAMP_S) * Math.sin(chirpPhase(t, PREAMBLE_S, lo, hi));
      } else {
        var k = Math.floor((t - data0) / SYMBOL_S + 1e-9);
        if (k >= 0 && k < N_SYMBOLS) {
          var tau = Math.max(t - (data0 + k * SYMBOL_S), 0);
          var up = bits[k] === 1;
          v = rampW(tau, SYMBOL_S, SYMBOL_RAMP_S) *
            Math.sin(chirpPhase(tau, SYMBOL_S, up ? lo : hi, up ? hi : lo));
        }
      }
      out[i] = AMPLITUDE * v;
    }
    return out;
  }

  /** The 200 ms preamble at unit peak amplitude, real-valued, at rate fs. */
  function preambleTemplate(band, fs) {
    var lo = BANDS[band][0], hi = BANDS[band][1];
    var n = Math.round(PREAMBLE_S * fs), out = new Float32Array(n);
    for (var i = 0; i < n; i++) {
      var t = i / fs;
      out[i] = rampW(t, PREAMBLE_S, PREAMBLE_RAMP_S) * Math.sin(chirpPhase(t, PREAMBLE_S, lo, hi));
    }
    return out;
  }

  // ------------------------------------------------------------ FFT (radix-2, in place)
  var fftCache = {};
  function fftTables(n) {
    var t = fftCache[n];
    if (t) return t;
    var bits = Math.round(Math.log2(n)), rev = new Uint32Array(n);
    for (var i = 0; i < n; i++) {
      var r = 0, x = i;
      for (var b = 0; b < bits; b++) { r = (r << 1) | (x & 1); x >>= 1; }
      rev[i] = r;
    }
    var cos = new Float64Array(n >> 1), sin = new Float64Array(n >> 1);
    for (var k = 0; k < n >> 1; k++) { cos[k] = Math.cos(2 * Math.PI * k / n); sin[k] = Math.sin(2 * Math.PI * k / n); }
    t = fftCache[n] = { rev: rev, cos: cos, sin: sin };
    return t;
  }

  /** In-place complex FFT. inverse=true computes the scaled inverse (like numpy ifft). */
  function fft(re, im, inverse) {
    var n = re.length, T = fftTables(n), rev = T.rev, i, j, tmp;
    for (i = 0; i < n; i++) {
      j = rev[i];
      if (j > i) { tmp = re[i]; re[i] = re[j]; re[j] = tmp; tmp = im[i]; im[i] = im[j]; im[j] = tmp; }
    }
    var sgn = inverse ? 1 : -1;
    for (var size = 2; size <= n; size <<= 1) {
      var half = size >> 1, step = n / size;
      for (var s = 0; s < n; s += size) {
        for (var k = 0, tw = 0; k < half; k++, tw += step) {
          var wr = T.cos[tw], wi = sgn * T.sin[tw];
          var a = s + k, b = a + half;
          var xr = re[b] * wr - im[b] * wi, xi = re[b] * wi + im[b] * wr;
          re[b] = re[a] - xr; im[b] = im[a] - xi;
          re[a] += xr; im[a] += xi;
        }
      }
    }
    if (inverse) for (i = 0; i < n; i++) { re[i] /= n; im[i] /= n; }
  }

  // ------------------------------------------------------------ growable sample buffer
  function Buf() { this.d = new Float64Array(65536); this.start = 0; this.len = 0; this.base = 0; }
  Buf.prototype.push = function (x, off, cnt) {
    off = off || 0; cnt = cnt === undefined ? x.length - off : cnt;
    if (this.start + this.len + cnt > this.d.length) {
      var cap = this.d.length;
      while (this.len + cnt > cap) cap *= 2;
      var nd = cap === this.d.length ? this.d : new Float64Array(cap);
      nd.set(this.d.subarray(this.start, this.start + this.len), 0);
      this.d = nd; this.start = 0;
    }
    for (var i = 0; i < cnt; i++) this.d[this.start + this.len + i] = x[off + i];
    this.len += cnt;
  };
  Buf.prototype.drop = function (n) {          // drop n oldest samples
    if (n <= 0) return;
    n = Math.min(n, this.len);
    this.start += n; this.len -= n; this.base += n;
  };
  Buf.prototype.at = function (absIdx) { return this.d[this.start + absIdx - this.base]; };
  Buf.prototype.end = function () { return this.base + this.len; };
  /** Copy [abs, abs+n) into dst (zero outside the buffer). */
  Buf.prototype.copy = function (abs, n, dst) {
    for (var i = 0; i < n; i++) {
      var k = abs + i - this.base;
      dst[i] = k >= 0 && k < this.len ? this.d[this.start + k] : 0;
    }
  };

  // ------------------------------------------------------------ resampler
  /** Streaming windowed-sinc resampler (any rate -> 16 kHz), zero delay. Mirrors Python. */
  function Resampler(fsIn, fsOut, cutoff) {
    fsOut = fsOut || DECODE_FS; cutoff = cutoff || 7600;
    this.r = fsIn / fsOut;
    var K = this.K = Math.ceil(16 * this.r), P = Resampler.PHASES, fc = cutoff / fsIn;
    this.taps = 2 * K;
    this.table = new Float64Array(P * this.taps);
    for (var p = 0; p < P; p++) {
      var sum = 0, row = p * this.taps;
      for (var t = 0; t < this.taps; t++) {
        var x = (t - K + 1) - p / P, h = 0;
        if (Math.abs(x) < K) {
          var w = 0.42 + 0.5 * Math.cos(Math.PI * x / K) + 0.08 * Math.cos(2 * Math.PI * x / K);
          var a = 2 * fc * x;
          h = 2 * fc * (a === 0 ? 1 : Math.sin(Math.PI * a) / (Math.PI * a)) * w;
        }
        this.table[row + t] = h; sum += h;
      }
      for (t = 0; t < this.taps; t++) this.table[row + t] /= sum;
    }
    this.buf = new Buf();
    this.buf.base = -K;
    this.buf.push(new Float64Array(K));
    this.n = 0;
  }
  Resampler.PHASES = 512;
  Resampler.prototype.process = function (x) {
    this.buf.push(x);
    var K = this.K, r = this.r, P = Resampler.PHASES, buf = this.buf;
    var lim = buf.end() - K - 1;
    var nEnd = lim > 0 ? Math.floor(lim / r) + 1 : 0;
    while (nEnd > this.n && (nEnd - 1) * r >= lim) nEnd--;
    var cnt = Math.max(0, nEnd - this.n), out = new Float64Array(cnt);
    var d = buf.d, off = buf.start - buf.base, taps = this.taps, table = this.table;
    for (var m = 0; m < cnt; m++) {
      var p = (this.n + m) * r, i0 = Math.floor(p), ph = Math.floor((p - i0) * P + 0.5);
      if (ph >= P) { i0 += 1; ph = 0; }
      var s = 0, row = ph * taps, j0 = off + i0 - K + 1;
      for (var t = 0; t < taps; t++) s += d[j0 + t] * table[row + t];
      out[m] = s;
    }
    if (nEnd > this.n) this.n = nEnd;
    buf.drop(Math.floor(this.n * r) - K - 1 - buf.base);
    return out;
  };

  // ------------------------------------------------------------ templates
  function nextPow2(n) { var p = 1; while (p < n) p <<= 1; return p; }

  function butterBpMag(f, band) {     // f > 0 only; 0 elsewhere
    if (f <= 0) return 0;
    var fl = BANDS[band][0] - BP_MARGIN_HZ, fh = BANDS[band][1] + BP_MARGIN_HZ;
    var x = (f * f - fl * fh) / (f * (fh - fl));
    return 1 / Math.sqrt(1 + Math.pow(x, 2 * BP_ORDER));
  }

  function fftFreq(k, n, fs) { return (k < n / 2 ? k : k - n) * fs / n; }

  /** Band-limit + make analytic; returns {re, im} of length L + 2*PAD, unit energy. */
  function bandTemplate(rawRe, rawIm, band) {
    var L = rawRe.length, n = L + 2 * PAD, nfft = nextPow2(2 * n);
    var re = new Float64Array(nfft), im = new Float64Array(nfft), i;
    for (i = 0; i < L; i++) { re[PAD + i] = rawRe[i]; im[PAD + i] = rawIm[i]; }
    fft(re, im, false);
    for (i = 0; i < nfft; i++) { var h = butterBpMag(fftFreq(i, nfft, DECODE_FS), band); re[i] *= h; im[i] *= h; }
    fft(re, im, true);
    var e = 0;
    for (i = 0; i < n; i++) e += re[i] * re[i] + im[i] * im[i];
    e = Math.sqrt(e);
    var oRe = new Float64Array(n), oIm = new Float64Array(n);
    for (i = 0; i < n; i++) { oRe[i] = re[i] / e; oIm[i] = im[i] / e; }
    return { re: oRe, im: oIm };
  }

  /** conj(FFT(template, nfft)) */
  function conjSpectrum(t, nfft) {
    var re = new Float64Array(nfft), im = new Float64Array(nfft);
    re.set(t.re); im.set(t.im);
    fft(re, im, false);
    for (var i = 0; i < nfft; i++) im[i] = -im[i];
    return { re: re, im: im };
  }

  function analyticChirp(n, T, f0, f1, ramp) {
    var re = new Float64Array(n), im = new Float64Array(n);
    for (var i = 0; i < n; i++) {
      var t = i / DECODE_FS, w = rampW(t, T, ramp), ph = chirpPhase(t, T, f0, f1);
      re[i] = w * Math.cos(ph); im[i] = w * Math.sin(ph);
    }
    return [re, im];
  }

  var TEMPLATES = null;
  function templates() {
    if (TEMPLATES) return TEMPLATES;
    TEMPLATES = [];
    for (var b = 0; b < 4; b++) {
      var lo = BANDS[b][0], hi = BANDS[b][1];
      var p = analyticChirp(N_PRE, PREAMBLE_S, lo, hi, PREAMBLE_RAMP_S);
      var u = analyticChirp(N_SYM, SYMBOL_S, lo, hi, SYMBOL_RAMP_S);
      var d = analyticChirp(N_SYM, SYMBOL_S, hi, lo, SYMBOL_RAMP_S);
      var pre = bandTemplate(p[0], p[1], b), up = bandTemplate(u[0], u[1], b), dn = bandTemplate(d[0], d[1], b);
      var bp = new Float64Array(RHO_NFFT);
      for (var i = 0; i < RHO_NFFT; i++) bp[i] = butterBpMag(Math.abs(fftFreq(i, RHO_NFFT, DECODE_FS)), b);
      TEMPLATES.push({
        bp: bp,
        preLen: pre.re.length, pre: conjSpectrum(pre, MF_NFFT),
        symLen: up.re.length, up: conjSpectrum(up, SYM_NFFT), dn: conjSpectrum(dn, SYM_NFFT)
      });
    }
    return TEMPLATES;
  }

  // ------------------------------------------------------------ helpers
  function median(a) {
    var s = Float64Array.from(a).sort(), n = s.length;
    if (!n) return 0;
    return n & 1 ? s[(n - 1) >> 1] : 0.5 * (s[n / 2 - 1] + s[n / 2]);
  }
  function round(v, d) { var m = Math.pow(10, d); return Math.round(v * m) / m; }

  /** X (re,im) * S (re,im) -> scaled IFFT, returns |result| for the first `count` samples. */
  function corrMag(Xre, Xim, S, count, wre, wim) {
    var n = Xre.length, i;
    for (i = 0; i < n; i++) {
      wre[i] = Xre[i] * S.re[i] - Xim[i] * S.im[i];
      wim[i] = Xre[i] * S.im[i] + Xim[i] * S.re[i];
    }
    fft(wre, wim, true);
    var out = new Float64Array(count);
    for (i = 0; i < count; i++) out[i] = Math.sqrt(wre[i] * wre[i] + wim[i] * wim[i]);
    return out;
  }

  // ------------------------------------------------------------ decoder
  /**
   * Streaming receiver. opts: {bands:[0,1,2,3], minQuality:0.20, track:true}.
   * `candidates` keeps the last 200 preamble detections with their outcome
   * ('ok','weak','crc','reserved','quality','busy','dup').
   */
  function Decoder(fs, opts) {
    opts = opts || {};
    this.fs = fs;
    this.bands = opts.bands || [0, 1, 2, 3];
    this.minQuality = opts.minQuality === undefined ? MIN_QUALITY : opts.minQuality;
    this.track = opts.track === undefined ? true : !!opts.track;
    this._T = templates();
    this._rs = fs === DECODE_FS ? null : new Resampler(fs);
    this._buf = new Buf();
    this._n = 0;
    this._mf = 0;
    this._hist = {};
    for (var i = 0; i < this.bands.length; i++) this._hist[this.bands[i]] = new Buf();
    this._scan = 0;
    this._pending = [];
    this._busy = {};
    for (i = 0; i < this.bands.length; i++) this._busy[this.bands[i]] = -1;
    this._recent = [];
    this.candidates = [];
    this.level_db = -120;
    this.band_ratio_db = {};
    for (i = 0; i < this.bands.length; i++) this.band_ratio_db[this.bands[i]] = 0;
    this._wa = { re: new Float64Array(MF_NFFT), im: new Float64Array(MF_NFFT),
                 wre: new Float64Array(MF_NFFT), wim: new Float64Array(MF_NFFT) };
  }

  Decoder.prototype.feed = function (samples) {
    var x = samples, i;
    if (x.length) {
      var e = 0;
      for (i = 0; i < x.length; i++) e += x[i] * x[i];
      this.level_db = 10 * Math.log10(e / x.length + 1e-12);
    }
    if (this._rs) x = this._rs.process(x);
    if (x.length) { this._buf.push(x); this._n += x.length; }
    while (this._n - this._mf >= MF_NFFT) this._mfBlock();
    var out = this._decodeReady();
    this._trim();
    return out;
  };

  Decoder.prototype.flush = function () {
    return this.feed(new Float32Array(Math.ceil((FRAME_S + 1.5) * this.fs)));
  };

  Decoder.prototype._mfBlock = function () {
    var W = this._wa, V = MF_NFFT - this._T[0].preLen + 1, i;
    this._buf.copy(this._mf, MF_NFFT, W.re);
    W.im.fill(0);
    fft(W.re, W.im, false);
    for (var bi = 0; bi < this.bands.length; bi++) {
      var b = this.bands[bi];
      this._hist[b].push(corrMag(W.re, W.im, this._T[b].pre, V, W.wre, W.wim));
    }
    this._mf += V;
    this._scanBlock();
    var keep = this._mf - (MEDIAN_N + 2 * NMS_GUARD + 16);
    for (bi = 0; bi < this.bands.length; bi++) {
      var h = this._hist[this.bands[bi]];
      h.drop(keep - h.base);
    }
  };

  Decoder.prototype._scanBlock = function () {
    var end = this._mf, h0 = this._hist[this.bands[0]].base;
    var loR = this._scan, hiR = end - NMS_GUARD;
    if (hiR <= loR) return;
    var m0 = Math.max(h0, end - MEDIAN_N);
    m0 += ((-m0 % MEDIAN_STRIDE) + MEDIAN_STRIDE) % MEDIAN_STRIDE;
    var lb = Math.max(h0, loR - NMS_GUARD);
    for (var bi = 0; bi < this.bands.length; bi++) {
      var b = this.bands[bi], h = this._hist[b], i;
      var med = [];
      for (i = m0; i < end; i += MEDIAN_STRIDE) med.push(h.at(i));
      med = median(med);
      var thr = Math.max(DETECT_RATIO * med, ABS_FLOOR);
      var mx = 0;
      for (i = loR; i < end; i++) if (h.at(i) > mx) mx = h.at(i);
      this.band_ratio_db[b] = 20 * Math.log10(mx / Math.max(med, ABS_FLOOR / DETECT_RATIO) + 1e-12);
      // runs above threshold -> one maximum per run
      var maxima = [], inRun = false, bestI = 0, bestV = 0;
      for (i = lb; i <= end; i++) {
        var v = i < end ? h.at(i) : 0, above = i < end && v > thr;
        if (above) {
          if (!inRun || v > bestV) { bestI = i; bestV = v; }
          inRun = true;
        } else if (inRun) {
          maxima.push([bestI, bestV]); inRun = false;
        }
      }
      for (var a = 0; a < maxima.length; a++) {
        var ia = maxima[a][0], va = maxima[a][1];
        if (ia < loR || ia >= hiR) continue;
        var beaten = false;
        for (var c = 0; c < maxima.length; c++) {
          if (c === a) continue;
          var jc = maxima[c][0], uc = maxima[c][1];
          if (Math.abs(jc - ia) <= NMS_GUARD && (uc > va || (uc === va && jc < ia))) { beaten = true; break; }
        }
        if (beaten) continue;
        var frac = 0;
        if (ia - 1 >= h.base && ia + 1 < h.end()) {
          var p0 = h.at(ia - 1), p1 = h.at(ia), p2 = h.at(ia + 1), den = p0 - 2 * p1 + p2;
          if (den < 0) frac = clamp(0.5 * (p0 - p2) / den, -0.5, 0.5);
        }
        this._pending.push({ band: b, start: ia + PAD, frac: frac, peak: va, median: med });
      }
    }
    this._pending.sort(function (p, q) { return p.start - q.start; });
    this._scan = hiR;
  };

  Decoder.prototype._decodeReady = function () {
    var out = [], J = N_SYM * (N_SYMBOLS - 1) + 2 * SEARCH_W + 1;
    var need = J + this._T[0].symLen - 1;
    while (this._pending.length) {
      var c = this._pending[0], seg0 = c.start + N_PRE + N_GAP - SEARCH_W - PAD;
      if (this._n < seg0 + need) break;
      this._pending.shift();
      var fr = this._decode(c, seg0, J);
      if (fr) out.push(fr);
    }
    return out;
  };

  Decoder.prototype._log = function (c, outcome, extra) {
    var d = { band: c.band, t: round((c.start + N_PRE + c.frac) / DECODE_FS, 4),
              snr_db: round(20 * Math.log10(c.peak / Math.max(c.median, ABS_FLOOR / DETECT_RATIO)), 1), outcome: outcome };
    for (var k in extra) d[k] = extra[k];
    this.candidates.push(d);
    if (this.candidates.length > 200) this.candidates.splice(0, this.candidates.length - 200);
  };

  Decoder.prototype._rho = function (c) {
    var c0 = c.start + (N_PRE >> 1) - (RHO_NFFT >> 1), i;
    var re = new Float64Array(RHO_NFFT), im = new Float64Array(RHO_NFFT), bp = this._T[c.band].bp;
    this._buf.copy(c0, RHO_NFFT, re);
    fft(re, im, false);
    for (i = 0; i < RHO_NFFT; i++) { re[i] *= bp[i]; im[i] *= bp[i]; }
    fft(re, im, true);
    var e = 0;
    for (i = c.start - c0; i < c.start - c0 + N_PRE; i++) e += re[i] * re[i];
    return Math.SQRT2 * c.peak / Math.sqrt(e + 1e-20);
  };

  Decoder.prototype._decode = function (c, seg0, J) {
    var b = c.band, i, k;
    if (c.start < this._busy[b]) { this._log(c, 'busy', {}); return null; }
    var rho = this._rho(c);
    if (rho < MIN_RHO) { this._log(c, 'weak', { rho: round(rho, 3) }); return null; }
    var T = this._T[b];
    var Xre = new Float64Array(SYM_NFFT), Xim = new Float64Array(SYM_NFFT);
    var wre = new Float64Array(SYM_NFFT), wim = new Float64Array(SYM_NFFT);
    this._buf.copy(seg0, SYM_NFFT, Xre);
    fft(Xre, Xim, false);
    var U = corrMag(Xre, Xim, T.up, J, wre, wim);
    var D = corrMag(Xre, Xim, T.dn, J, wre, wim);
    var C = 2 * SEARCH_W + 1, center = new Int32Array(N_SYMBOLS);
    if (this.track) {
      var M = new Float64Array(N_SYMBOLS * C);
      for (k = 0; k < N_SYMBOLS; k++) for (i = 0; i < C; i++) {
        var q = N_SYM * k + i;
        M[k * C + i] = U[q] > D[q] ? U[q] : D[q];
      }
      var best = -1, bestS = 0, bestA = 0, step = 2 * SLOPE_MAX / (N_SLOPES - 1);
      for (var si = 0; si < N_SLOPES; si++) {
        var s = si === N_SLOPES - 1 ? SLOPE_MAX : -SLOPE_MAX + si * step;
        for (var a = -INTERCEPT_MAX; a <= INTERCEPT_MAX; a++) {
          var sc = 0;
          for (k = 0; k < N_SYMBOLS; k++) {
            var col = clamp(Math.floor(a + s * k + 0.5) + SEARCH_W, 0, C - 1);
            sc += M[k * C + col];
          }
          if (sc > best) { best = sc; bestS = s; bestA = a; }
        }
      }
      for (k = 0; k < N_SYMBOLS; k++) center[k] = clamp(Math.floor(bestA + bestS * k + 0.5) + SEARCH_W, 0, C - 1);
    } else {
      for (k = 0; k < N_SYMBOLS; k++) center[k] = SEARCH_W;
    }
    var bits = new Array(N_SYMBOLS), qsum = 0;
    for (k = 0; k < N_SYMBOLS; k++) {
      var lo = clamp(center[k] - REFINE, 0, C - 1), hi = clamp(center[k] + REFINE, 0, C - 1);
      var u = 0, dn = 0;
      for (i = lo; i <= hi; i++) {
        var p = N_SYM * k + i;
        if (U[p] > u) u = U[p];
        if (D[p] > dn) dn = D[p];
      }
      bits[k] = u > dn ? 1 : 0;
      qsum += (Math.max(u, dn) - Math.min(u, dn)) / (u + dn + 1e-12);
    }
    var quality = qsum / N_SYMBOLS;
    var raw = fromBits(bits), fields = unpack(raw);
    if (!fields) { this._log(c, 'crc', { quality: round(quality, 3), rho: round(rho, 3) }); return null; }
    if (raw[4] & 3) { this._log(c, 'reserved', { quality: round(quality, 3), rho: round(rho, 3) }); return null; }
    if (quality < this.minQuality) { this._log(c, 'quality', { quality: round(quality, 3), rho: round(rho, 3) }); return null; }
    var hex = toHex(raw);
    for (i = 0; i < this._recent.length; i++) {
      if (this._recent[i][0] === hex && Math.abs(this._recent[i][1] - c.start) < DECODE_FS) {
        this._log(c, 'dup', {}); return null;
      }
    }
    this._recent = this._recent.filter(function (r) { return c.start - r[1] < 4 * DECODE_FS; });
    this._recent.push([hex, c.start]);
    this._busy[b] = c.start + N_FRAME;
    var tEnd = (c.start + N_PRE + c.frac) / DECODE_FS;
    this._log(c, 'ok', { quality: round(quality, 3), rho: round(rho, 3), id: fields.id });
    return {
      fields: fields, raw: raw, rawHex: hex, band: b,
      snr_db: 20 * Math.log10(c.peak / Math.max(c.median, ABS_FLOOR / DETECT_RATIO)),
      t_end_preamble: tEnd, sample_index: Math.floor(tEnd * this.fs + 0.5), quality: quality
    };
  };

  Decoder.prototype._trim = function () {
    var keepFrom = this._mf;
    for (var i = 0; i < this._pending.length; i++)
      keepFrom = Math.min(keepFrom, this._pending[i].start + (N_PRE >> 1) - (RHO_NFFT >> 1));
    keepFrom = Math.min(keepFrom, this._n - 6 * DECODE_FS);
    this._buf.drop(keepFrom - this._buf.base);
  };

  /** Same shape as Python Frame.to_json(): fields + band, snr_db, t, sample_index, raw, quality. */
  function frameToJSON(f) {
    var d = {};
    for (var k in f.fields) d[k] = f.fields[k];
    d.band = f.band; d.snr_db = round(f.snr_db, 1); d.t = round(f.t_end_preamble, 4);
    d.sample_index = f.sample_index; d.raw = f.rawHex; d.quality = round(f.quality, 3);
    return d;
  }

  var SPEC = {
    BANDS: BANDS, PREAMBLE_S: PREAMBLE_S, GAP_S: GAP_S, SYMBOL_S: SYMBOL_S, N_SYMBOLS: N_SYMBOLS,
    PREAMBLE_RAMP_S: PREAMBLE_RAMP_S, SYMBOL_RAMP_S: SYMBOL_RAMP_S, AMPLITUDE: AMPLITUDE,
    FRAME_S: FRAME_S, DECODE_FS: DECODE_FS, DETECT_RATIO: DETECT_RATIO, STATUS: STATUS,
    DEMO_PERIOD_S: 8, NORMAL_PERIOD_S: 30, JITTER_S: 1.0, BURST_PERIOD_S: 3, BURST_BAND: 1,
    RELAY_MAX_HOPS: 3, RELAY_HOLDOFF_S: 30, RELAY_WAIT_MIN_S: 1.5, RELAY_WAIT_MAX_S: 4.0
  };

  var M = {
    SPEC: SPEC, crc8: crc8, pack: pack, unpack: unpack, toBits: toBits, fromBits: fromBits, toHex: toHex,
    synth: synth, preambleTemplate: preambleTemplate, Decoder: Decoder, Resampler: Resampler,
    frameToJSON: frameToJSON, fft: fft,
    /** SPEC 1.5: band for transmission number k of beacon `id` ("1A2B" or int). */
    bandFor: function (k, id) { return (k + (typeof id === 'string' ? parseInt(id, 16) : id)) % 4; }
  };
  root.HeimdallModem = M;
  if (typeof module !== 'undefined' && module.exports) module.exports = M;
})(typeof globalThis !== 'undefined' ? globalThis : typeof self !== 'undefined' ? self : this);
