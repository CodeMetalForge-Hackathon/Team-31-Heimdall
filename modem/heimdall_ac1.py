"""HEIMDALL-AC1 chirp modem: Python reference implementation of docs/SPEC.md section 1.

Pure numpy. The JS port (web/js/heimdall-modem.js) mirrors this file function by
function; keep the two in sync.

Receiver outline (all at 16 kHz internally):
  1. Resample the input to 16 kHz (windowed-sinc, streaming).
  2. Per band, matched-filter against the analytic preamble template. The 4th-order
     Butterworth band-pass of SPEC 1.7.1 is folded into every template as a
     zero-phase magnitude response, so it costs nothing extra.
  3. Detection: |corr| peak / median(|corr| over the last 2 s) > 8, with
     non-maximum suppression over +-0.25 s that is independent of block edges.
  4. Symbols: non-coherent |<x, complex template>| for up and down chirps. Timing is
     a line (offset + drift per symbol) fitted jointly over all 48 symbols, so a
     +-0.15% clock error is tracked; each symbol then searches +-0.25 ms around the line.
  5. Gates before a frame is reported: normalized preamble correlation (rejects
     adjacent-band leakage and clicks before decoding), CRC-8, reserved bits == 0,
     and a symbol-quality floor. CRC-8 alone would pass 1 in 256 garbage decodes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "BANDS", "PREAMBLE_S", "GAP_S", "SYMBOL_S", "N_SYMBOLS", "PREAMBLE_RAMP_S",
    "SYMBOL_RAMP_S", "AMPLITUDE", "FRAME_S", "DECODE_FS", "DETECT_RATIO", "STATUS",
    "crc8", "pack", "unpack", "to_bits", "from_bits", "synth", "preamble_template",
    "preamble_segment", "Frame", "Decoder", "Resampler",
]

# ---------------------------------------------------------------- SPEC constants
BANDS = ((1500.0, 2500.0), (2500.0, 3500.0), (3500.0, 4500.0), (5000.0, 6500.0))
PREAMBLE_S = 0.200
GAP_S = 0.010
SYMBOL_S = 0.040
N_SYMBOLS = 48
PREAMBLE_RAMP_S = 0.005
SYMBOL_RAMP_S = 0.002
AMPLITUDE = 0.8
FRAME_S = PREAMBLE_S + GAP_S + N_SYMBOLS * SYMBOL_S  # 2.130 s
DECODE_FS = 16000
DETECT_RATIO = 8.0
MEDIAN_WINDOW_S = 2.0
STATUS = ("no_response", "ok", "injured", "critical")

# ---------------------------------------------------------------- receiver tuning
BP_MARGIN_HZ = 200.0      # band-pass = f_lo - 200 .. f_hi + 200 (SPEC 1.7.1)
BP_ORDER = 4
PAD = 64                  # samples of band-pass tail kept on each side of a template
MF_NFFT = 8192            # preamble matched-filter block (overlap-save)
SYM_NFFT = 32768          # symbol correlation FFT (one per detected frame)
NMS_GUARD = 4000          # +-0.25 s non-maximum suppression
MEDIAN_STRIDE = 8         # median over every 8th |corr| sample (envelope is smooth)
SEARCH_W = 72             # +-4.5 ms raw timing window per symbol
INTERCEPT_MAX = 24        # +-1.5 ms offset of symbol 0 vs. the preamble estimate
N_SLOPES = 25             # drift grid, +-0.15 % clock error
SLOPE_MAX = 0.0015 * 640
REFINE = 4                # +-0.25 ms final per-symbol search around the fitted line
ABS_FLOOR = 1e-3          # |corr| floor (unit-energy template), ignores digital silence
MIN_QUALITY = 0.30        # mean (win-lose)/(win+lose) over symbols; real >= 0.33, junk <= 0.29
MIN_RHO = 0.2             # normalized preamble correlation; leakage/clicks sit below 0.1
RHO_NFFT = 4096

N_PRE = int(round(PREAMBLE_S * DECODE_FS))          # 3200
N_GAP = int(round(GAP_S * DECODE_FS))               # 160
N_SYM = int(round(SYMBOL_S * DECODE_FS))            # 640
N_FRAME = N_PRE + N_GAP + N_SYMBOLS * N_SYM         # 34080
MEDIAN_N = int(MEDIAN_WINDOW_S * DECODE_FS)         # 32000


# ---------------------------------------------------------------- payload
def crc8(data) -> int:
    """CRC-8/SMBUS: poly 0x07, init 0, no reflection, no final XOR."""
    crc = 0
    for b in bytes(data):
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def pack(fields: dict) -> bytes:
    """Field dict (keys as the SPEC `victim` event) -> 6 bytes incl. CRC."""
    fid = fields["id"]
    fid = int(fid, 16) if isinstance(fid, str) else int(fid)
    if not 0 <= fid <= 0xFFFF:
        raise ValueError(f"id out of range: {fields['id']!r}")
    floor = fields.get("floor")
    if floor is None:
        floor_code = 0
    else:
        floor_code = int(floor) + 2
        if not 1 <= floor_code <= 31:
            raise ValueError(f"floor must be -1..29 or None, got {floor!r}")
    min2 = _clamp(int(fields.get("minutes", 0)) // 2, 0, 63)
    status = fields.get("status", "no_response")
    status = STATUS.index(status) if isinstance(status, str) else int(status)
    if not 0 <= status <= 3:
        raise ValueError(f"bad status {fields.get('status')!r}")
    p = (fid << 24
         | floor_code << 19
         | min2 << 13
         | (1 if fields.get("motion") else 0) << 12
         | status << 10
         | _clamp(int(fields.get("people", 0)), 0, 7) << 7
         | _clamp(int(fields.get("battery", 0)), 0, 3) << 5
         | _clamp(int(fields.get("hops", 0)), 0, 3) << 3
         | (1 if fields.get("knock") else 0) << 2)
    body = p.to_bytes(5, "big")
    return body + bytes([crc8(body)])


def unpack(b) -> dict | None:
    """6 bytes -> field dict, or None if the length or CRC is wrong."""
    b = bytes(b)
    if len(b) != 6 or crc8(b[:5]) != b[5]:
        return None
    p = int.from_bytes(b[:5], "big")
    floor_code = (p >> 19) & 0x1F
    return {
        "id": f"{(p >> 24) & 0xFFFF:04X}",
        "floor": None if floor_code == 0 else floor_code - 2,
        "minutes": ((p >> 13) & 0x3F) * 2,
        "motion": bool((p >> 12) & 1),
        "status": STATUS[(p >> 10) & 3],
        "people": (p >> 7) & 7,
        "battery": (p >> 5) & 3,
        "hops": (p >> 3) & 3,
        "knock": bool((p >> 2) & 1),
    }


def _reserved(b) -> int:
    return bytes(b)[4] & 0x03


def to_bits(b) -> list[int]:
    """Bytes -> bit list in air order (byte 0 first, MSB first)."""
    return [(byte >> (7 - i)) & 1 for byte in bytes(b) for i in range(8)]


def from_bits(bits) -> bytes:
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        v = 0
        for bit in bits[i:i + 8]:
            v = (v << 1) | (1 if bit else 0)
        out.append(v)
    return bytes(out)


# ---------------------------------------------------------------- waveform
def _ramp_window(tau, T, ramp):
    w = np.ones_like(tau)
    a = tau < ramp
    w[a] = 0.5 - 0.5 * np.cos(np.pi * tau[a] / ramp)
    e = tau > T - ramp
    w[e] = 0.5 - 0.5 * np.cos(np.pi * (T - tau[e]) / ramp)
    return w


def _chirp_phase(tau, T, f0, f1):
    return 2.0 * np.pi * (f0 * tau + (f1 - f0) * tau * tau / (2.0 * T))


def _synth(frame, band, fs: float) -> np.ndarray:
    """float64 frame at any (even non-integer) rate; continuous-time math per SPEC 1.2."""
    f_lo, f_hi = BANDS[band]
    bits = np.array(to_bits(frame), dtype=np.int64)
    if len(bits) != N_SYMBOLS:
        raise ValueError("frame must be 6 bytes")
    n = int(math.ceil(FRAME_S * fs - 1e-9))
    t = np.arange(n) / fs
    out = np.zeros(n)
    pre = t < PREAMBLE_S
    tp = t[pre]
    out[pre] = _ramp_window(tp, PREAMBLE_S, PREAMBLE_RAMP_S) * np.sin(_chirp_phase(tp, PREAMBLE_S, f_lo, f_hi))
    data0 = PREAMBLE_S + GAP_S
    k = np.floor((t - data0) / SYMBOL_S + 1e-9).astype(np.int64)
    d = (k >= 0) & (k < N_SYMBOLS)
    kd = k[d]
    tau = np.maximum(t[d] - (data0 + kd * SYMBOL_S), 0.0)
    up = bits[kd] == 1
    f0 = np.where(up, f_lo, f_hi)
    f1 = np.where(up, f_hi, f_lo)
    out[d] = _ramp_window(tau, SYMBOL_S, SYMBOL_RAMP_S) * np.sin(_chirp_phase(tau, SYMBOL_S, f0, f1))
    return AMPLITUDE * out


def synth(frame, band: int, fs: int) -> np.ndarray:
    """6-byte frame -> float32 waveform (2.130 s) on `band` at sample rate `fs`."""
    return _synth(frame, band, float(fs)).astype(np.float32)


def preamble_template(band: int, fs: int, analytic: bool = False) -> np.ndarray:
    """The 200 ms preamble at unit peak amplitude (real, or complex w*exp(j*phi))."""
    f_lo, f_hi = BANDS[band]
    tau = np.arange(int(round(PREAMBLE_S * fs))) / fs
    w = _ramp_window(tau, PREAMBLE_S, PREAMBLE_RAMP_S)
    phi = _chirp_phase(tau, PREAMBLE_S, f_lo, f_hi)
    return w * np.exp(1j * phi) if analytic else (w * np.sin(phi)).astype(np.float32)


def preamble_segment(audio, frame: "Frame", fs: int, offset: int = 0) -> tuple[int, int]:
    """(start, stop) sample range of `frame`'s preamble inside `audio` (rate fs).

    `offset` = index in `audio` of the first sample that was fed to the Decoder.
    The range is clipped to the audio length; slice every mic channel with it."""
    stop = frame.sample_index - offset
    start = stop - int(round(PREAMBLE_S * fs))
    n = len(audio)
    return max(0, min(n, start)), max(0, min(n, stop))


# ---------------------------------------------------------------- resampler
class Resampler:
    """Streaming windowed-sinc resampler (any rate -> 16 kHz), zero delay.

    Output sample n is the input interpolated at time n / fs_out. Blackman-windowed
    sinc, cutoff 7.6 kHz, 512-phase table (nearest phase)."""

    PHASES = 512

    def __init__(self, fs_in: float, fs_out: float = DECODE_FS, cutoff: float = 7600.0):
        self.r = float(fs_in) / float(fs_out)
        self.K = K = int(math.ceil(16 * self.r))
        fc = cutoff / float(fs_in)
        j = np.arange(-K + 1, K + 1)                       # tap offsets
        x = j[None, :] - (np.arange(self.PHASES) / self.PHASES)[:, None]
        win = 0.42 + 0.5 * np.cos(np.pi * x / K) + 0.08 * np.cos(2 * np.pi * x / K)
        win[np.abs(x) >= K] = 0.0
        h = 2 * fc * np.sinc(2 * fc * x) * win
        self.table = h / h.sum(axis=1, keepdims=True)
        self.j = j
        self.buf = np.zeros(K)
        self.buf0 = -K          # absolute input index of buf[0]
        self.n = 0              # next output index

    def process(self, x) -> np.ndarray:
        self.buf = np.concatenate([self.buf, np.asarray(x, dtype=np.float64)])
        end = self.buf0 + len(self.buf)
        lim = end - self.K - 1                             # need n*r < lim
        n_end = int(math.floor(lim / self.r)) + 1 if lim > 0 else 0
        while n_end > self.n and (n_end - 1) * self.r >= lim:
            n_end -= 1
        outs = []
        for c0 in range(self.n, n_end, 8192):
            nn = np.arange(c0, min(n_end, c0 + 8192))
            p = nn * self.r
            i0 = np.floor(p).astype(np.int64)
            ph = np.floor((p - i0) * self.PHASES + 0.5).astype(np.int64)
            wrap = ph >= self.PHASES
            i0[wrap] += 1
            ph[wrap] = 0
            idx = (i0 - self.buf0)[:, None] + self.j[None, :]
            outs.append(np.einsum("ij,ij->i", self.buf[idx], self.table[ph]))
        if n_end > self.n:
            self.n = n_end
        keep = int(math.floor(self.n * self.r)) - self.K - 1 - self.buf0
        if keep > 0:
            self.buf = self.buf[keep:]
            self.buf0 += keep
        return np.concatenate(outs) if outs else np.zeros(0)


# ---------------------------------------------------------------- templates
def _next_pow2(n):
    return 1 << (int(n) - 1).bit_length()


def _fft_freqs(n, fs):
    k = np.arange(n)
    return np.where(k < n // 2, k, k - n) * (fs / n)


def _butter_bp_mag(f, band):
    """|H| of an analog 4th-order Butterworth band-pass (LP->BP), f > 0 only."""
    f_lo, f_hi = BANDS[band]
    fl, fh = f_lo - BP_MARGIN_HZ, f_hi + BP_MARGIN_HZ
    out = np.zeros_like(f)
    pos = f > 0
    fp = f[pos]
    x = (fp * fp - fl * fh) / (fp * (fh - fl))
    out[pos] = 1.0 / np.sqrt(1.0 + x ** (2 * BP_ORDER))
    return out


def _band_template(raw, band):
    """Band-limit + make exactly analytic; returns len(raw) + 2*PAD, unit energy.
    Original sample 0 sits at index PAD."""
    L = len(raw)
    n = L + 2 * PAD
    nfft = _next_pow2(2 * n)
    buf = np.zeros(nfft, dtype=complex)
    buf[PAD:PAD + L] = raw
    spec = np.fft.fft(buf) * _butter_bp_mag(_fft_freqs(nfft, DECODE_FS), band)
    out = np.fft.ifft(spec)[:n]
    return out / np.sqrt(np.sum(np.abs(out) ** 2))


_TEMPLATES = None


def _templates():
    global _TEMPLATES
    if _TEMPLATES is None:
        tp = np.arange(N_PRE) / DECODE_FS
        ts = np.arange(N_SYM) / DECODE_FS
        wp = _ramp_window(tp, PREAMBLE_S, PREAMBLE_RAMP_S)
        ws = _ramp_window(ts, SYMBOL_S, SYMBOL_RAMP_S)
        T = []
        for b, (lo, hi) in enumerate(BANDS):
            pre = _band_template(wp * np.exp(1j * _chirp_phase(tp, PREAMBLE_S, lo, hi)), b)
            up = _band_template(ws * np.exp(1j * _chirp_phase(ts, SYMBOL_S, lo, hi)), b)
            dn = _band_template(ws * np.exp(1j * _chirp_phase(ts, SYMBOL_S, hi, lo)), b)
            f = _fft_freqs(RHO_NFFT, DECODE_FS)
            T.append({
                "bp": _butter_bp_mag(np.abs(f), b),
                "pre_len": len(pre),
                "pre_f": np.conj(np.fft.fft(pre, MF_NFFT)),
                "sym_len": len(up),
                "up_f": np.conj(np.fft.fft(up, SYM_NFFT)),
                "dn_f": np.conj(np.fft.fft(dn, SYM_NFFT)),
            })
        _TEMPLATES = T
    return _TEMPLATES


# ---------------------------------------------------------------- decoder
@dataclass
class Frame:
    fields: dict
    raw: bytes
    band: int
    snr_db: float
    t_end_preamble: float        # seconds since the decoder started
    sample_index: int            # preamble end, in input samples (rate fs) since start
    quality: float = 0.0         # mean symbol margin 0..1

    def to_json(self) -> dict:
        d = dict(self.fields)
        d.update(band=self.band, snr_db=round(self.snr_db, 1),
                 t=round(self.t_end_preamble, 4), sample_index=self.sample_index,
                 raw=self.raw.hex().upper(), quality=round(self.quality, 3))
        return d


@dataclass
class _Cand:
    band: int
    start: int          # absolute 16 kHz index of the preamble's first sample
    frac: float         # sub-sample peak offset
    peak: float
    median: float
    info: dict = field(default_factory=dict)


class Decoder:
    """Streaming HEIMDALL-AC1 receiver. feed() any chunk size; returns new Frames.

    `candidates` keeps the last 200 preamble detections with their outcome
    ("ok", "weak", "crc", "reserved", "quality", "busy", "dup") for debugging/analysis."""

    def __init__(self, fs: int, bands=(0, 1, 2, 3), min_quality: float = MIN_QUALITY,
                 track: bool = True):
        self.fs = fs
        self.bands = tuple(bands)
        self.min_quality = min_quality
        self.track = track
        self._T = _templates()
        self._rs = None if fs == DECODE_FS else Resampler(fs)
        self._buf = np.zeros(0)
        self._buf0 = 0
        self._n = 0
        self._mf = 0
        self._hist = {b: np.zeros(0) for b in self.bands}
        self._hist0 = 0
        self._scan = 0
        self._pending: list[_Cand] = []
        self._busy = {b: -1 for b in self.bands}
        self._recent: list[tuple[bytes, int]] = []
        self.candidates: list[dict] = []
        self.level_db = -120.0          # RMS of the last fed chunk (dBFS)

    # -- public
    def feed(self, samples) -> list[Frame]:
        x = np.asarray(samples, dtype=np.float64).ravel()
        if len(x):
            self.level_db = 10 * math.log10(float(np.mean(x * x)) + 1e-12)
        if self._rs is not None:
            x = self._rs.process(x)
        if len(x):
            self._buf = np.concatenate([self._buf, x])
            self._n += len(x)
        while self._n - self._mf >= MF_NFFT:
            self._mf_block()
        out = self._decode_ready()
        self._trim()
        return out

    def flush(self) -> list[Frame]:
        """Feed silence so frames near the end of a recording get decoded."""
        return self.feed(np.zeros(int(math.ceil((FRAME_S + 1.5) * self.fs))))

    # -- matched filter + detection
    def _mf_block(self):
        i0 = self._mf - self._buf0
        X = np.fft.fft(self._buf[i0:i0 + MF_NFFT])
        V = MF_NFFT - self._T[0]["pre_len"] + 1
        for b in self.bands:
            c = np.abs(np.fft.ifft(X * self._T[b]["pre_f"])[:V])
            self._hist[b] = np.concatenate([self._hist[b], c])
        self._mf += V
        self._scan_block()
        keep = self._mf - (MEDIAN_N + 2 * NMS_GUARD + 16) - self._hist0
        if keep > 0:
            for b in self.bands:
                self._hist[b] = self._hist[b][keep:]
            self._hist0 += keep

    def _scan_block(self):
        end, h0 = self._mf, self._hist0
        lo_r, hi_r = self._scan, end - NMS_GUARD
        if hi_r <= lo_r:
            return
        m0 = max(h0, end - MEDIAN_N)
        m0 += (-m0) % MEDIAN_STRIDE
        lb = max(h0, lo_r - NMS_GUARD)
        for b in self.bands:
            h = self._hist[b]
            med = float(np.median(h[m0 - h0:end - h0:MEDIAN_STRIDE]))
            thr = max(DETECT_RATIO * med, ABS_FLOOR)
            seg = h[lb - h0:end - h0]
            above = np.concatenate([[False], seg > thr, [False]])
            edges = np.flatnonzero(above[1:] != above[:-1])
            if len(edges) == 0:
                continue
            maxima = []
            for rs, re in zip(edges[::2], edges[1::2]):
                i = rs + int(np.argmax(seg[rs:re]))
                maxima.append((lb + i, float(seg[i])))
            for i, v in maxima:
                if not lo_r <= i < hi_r:
                    continue
                if any(abs(j - i) <= NMS_GUARD and (u > v or (u == v and j < i))
                       for j, u in maxima if j != i):
                    continue
                k = i - h0
                frac = 0.0
                if 0 < k < len(h) - 1:
                    a, c = h[k - 1], h[k + 1]
                    den = a - 2 * h[k] + c
                    if den < 0:
                        frac = float(_clamp(0.5 * (a - c) / den, -0.5, 0.5))
                self._pending.append(_Cand(b, i + PAD, frac, v, med))
        self._pending.sort(key=lambda c: c.start)
        self._scan = hi_r

    # -- symbol decoding
    def _decode_ready(self) -> list[Frame]:
        out = []
        sym_len = self._T[0]["sym_len"]
        J = N_SYM * (N_SYMBOLS - 1) + 2 * SEARCH_W + 1
        need = J + sym_len - 1
        while self._pending:
            c = self._pending[0]
            seg0 = c.start + N_PRE + N_GAP - SEARCH_W - PAD
            if self._n < seg0 + need:
                break
            self._pending.pop(0)
            fr = self._decode(c, seg0, J)
            if fr is not None:
                out.append(fr)
        return out

    def _log(self, c: _Cand, outcome: str, **kw):
        d = {"band": c.band, "t": round(float(c.start + N_PRE + c.frac) / DECODE_FS, 4),
             "snr_db": round(float(20 * math.log10(c.peak / max(c.median, 1e-12))), 1),
             "outcome": outcome}
        d.update(kw)
        self.candidates.append(d)
        del self.candidates[:-200]

    def _rho(self, c: _Cand) -> float:
        """sqrt(2) * peak / sqrt(band-passed energy over the preamble): ~1 for a clean
        preamble, ~0.4 at -5 dB DRR, < 0.1 for adjacent-band leakage and clicks."""
        c0 = c.start + N_PRE // 2 - RHO_NFFT // 2
        i0 = c0 - self._buf0
        seg = np.zeros(RHO_NFFT)
        a, z = max(0, -i0), min(RHO_NFFT, len(self._buf) - i0)
        if z > a:
            seg[a:z] = self._buf[i0 + a:i0 + z]
        y = np.fft.ifft(np.fft.fft(seg) * self._T[c.band]["bp"]).real
        e = float(np.sum(y[c.start - c0:c.start - c0 + N_PRE] ** 2))
        return math.sqrt(2.0) * c.peak / math.sqrt(e + 1e-20)

    def _decode(self, c: _Cand, seg0: int, J: int) -> Frame | None:
        b = c.band
        if c.start < self._busy[b]:
            self._log(c, "busy")
            return None
        rho = self._rho(c)
        if rho < MIN_RHO:
            self._log(c, "weak", rho=round(rho, 3))
            return None
        T = self._T[b]
        i0 = seg0 - self._buf0
        seg = self._buf[i0:i0 + SYM_NFFT]
        if len(seg) < SYM_NFFT:
            seg = np.concatenate([seg, np.zeros(SYM_NFFT - len(seg))])
        X = np.fft.fft(seg)
        U = np.abs(np.fft.ifft(X * T["up_f"])[:J])
        D = np.abs(np.fft.ifft(X * T["dn_f"])[:J])
        k = np.arange(N_SYMBOLS)
        idx = (N_SYM * k)[:, None] + np.arange(2 * SEARCH_W + 1)[None, :]
        Uk, Dk = U[idx], D[idx]                     # (48, 2W+1); column W = nominal
        if self.track:
            M = np.maximum(Uk, Dk)
            slopes = np.linspace(-SLOPE_MAX, SLOPE_MAX, N_SLOPES)
            inter = np.arange(-INTERCEPT_MAX, INTERCEPT_MAX + 1)
            d = np.floor(inter[None, :, None] + slopes[:, None, None] * k[None, None, :] + 0.5)
            d = np.clip(d.astype(np.int64) + SEARCH_W, 0, 2 * SEARCH_W)
            score = M[k[None, None, :], d].sum(axis=2)
            si, ai = np.unravel_index(int(np.argmax(score)), score.shape)
            center = d[si, ai]
        else:
            center = np.full(N_SYMBOLS, SEARCH_W)
        lo = np.clip(center - REFINE, 0, 2 * SEARCH_W)
        hi = np.clip(center + REFINE, 0, 2 * SEARCH_W) + 1
        cols = np.arange(2 * SEARCH_W + 1)[None, :]
        win = (cols >= lo[:, None]) & (cols < hi[:, None])
        u = np.where(win, Uk, 0).max(axis=1)
        dn = np.where(win, Dk, 0).max(axis=1)
        bits = (u > dn).astype(int).tolist()
        quality = float(np.mean((np.maximum(u, dn) - np.minimum(u, dn)) / (u + dn + 1e-12)))
        raw = from_bits(bits)
        fields = unpack(raw)
        if fields is None:
            self._log(c, "crc", quality=round(quality, 3), rho=round(rho, 3))
            return None
        if _reserved(raw):
            self._log(c, "reserved", quality=round(quality, 3), rho=round(rho, 3))
            return None
        if quality < self.min_quality:
            self._log(c, "quality", quality=round(quality, 3), rho=round(rho, 3))
            return None
        for r, s in self._recent:
            if r == raw and abs(s - c.start) < DECODE_FS:
                self._log(c, "dup")
                return None
        self._recent = [(r, s) for r, s in self._recent if c.start - s < 4 * DECODE_FS]
        self._recent.append((raw, c.start))
        self._busy[b] = c.start + N_FRAME
        t_end = float(c.start + N_PRE + c.frac) / DECODE_FS
        snr = 20 * math.log10(c.peak / max(c.median, 1e-12))
        self._log(c, "ok", quality=round(quality, 3), rho=round(rho, 3), id=fields["id"])
        return Frame(fields, raw, b, snr, t_end, int(round(t_end * self.fs)), quality)

    def _trim(self):
        keep_from = self._mf
        for c in self._pending:
            keep_from = min(keep_from, c.start + N_PRE // 2 - RHO_NFFT // 2)
        keep_from = min(keep_from, self._n - 6 * DECODE_FS)
        drop = keep_from - self._buf0
        if drop > 0:
            self._buf = self._buf[drop:]
            self._buf0 += drop
