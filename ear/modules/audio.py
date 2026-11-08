"""Station audio: XVF3800 mic array -> HEIMDALL-AC1 decode -> GCC-PHAT bearing -> victim/bearing/noise events.

Capture: one sounddevice stream (6 ch, 16 kHz) into a ring buffer of the last few seconds with an
absolute sample counter. A worker loop feeds one channel to modem.Decoder; for every decoded frame it
slices the 4 raw mics around the preamble (or the whole frame) and fits a bearing (SPEC 1.7.8).

Standalone:  python -m ear.modules.audio            (live, prints JSON lines)
             python -m ear.modules.audio --wav x.wav (replay a 6-channel recording)
"""
import argparse
import logging
import math
import threading
import time

import numpy as np

from modem.heimdall_ac1 import BANDS, FRAME_S, PREAMBLE_S, Decoder, preamble_segment

log = logging.getLogger("audio")

ARRAY_NAMES = ("xvf3800", "respeaker")
ASR_CHANNEL = 1
BAND_MARGIN_HZ = 200.0
UPSAMPLE = 16
PHAT_BETA = 0.7
STALL_S = 3.0


# ---------------------------------------------------------------- device + capture
def find_device(device="auto"):
    """-> (index, info) of the input device, or (None, None). "auto" = first input named like the array."""
    import sounddevice as sd
    if device != "auto":
        info = sd.query_devices(device, "input")
        return info["index"], info
    for info in sd.query_devices():
        if info["max_input_channels"] > 0 and any(n in info["name"].lower() for n in ARRAY_NAMES):
            return info["index"], info
    return None, None


class Ring:
    """Last `seconds` of every channel, addressed by absolute sample index since the stream started."""

    def __init__(self, seconds, fs, channels):
        self.n = int(seconds * fs)
        self.buf = np.zeros((self.n, channels), dtype=np.float32)
        self.count = 0                      # samples written so far (absolute index of the next one)
        self.lock = threading.Lock()

    def write(self, block):
        k = len(block)
        with self.lock:
            i = self.count % self.n
            first = min(k, self.n - i)
            self.buf[i:i + first] = block[:first]
            if k > first:
                self.buf[:k - first] = block[first:]
            self.count += k

    def read(self, start, stop):
        """Samples [start, stop) as (stop - start, channels), or None if they are no longer (or not yet) held."""
        with self.lock:
            if start < self.count - self.n or stop > self.count or stop <= start:
                return None
            idx = np.arange(start, stop) % self.n
            return self.buf[idx].copy()


class Capture:
    """sounddevice InputStream -> Ring. The callback only copies."""

    def __init__(self, device, fs, channels, blocksize, ring_s):
        import sounddevice as sd
        self.ring = Ring(ring_s, fs, channels)
        self.fs, self.channels = fs, channels
        self.overflows = 0

        def cb(indata, frames, t, status):
            if status.input_overflow:
                self.overflows += 1
            self.ring.write(indata)

        self.stream = sd.InputStream(device=device, samplerate=fs, channels=channels, blocksize=blocksize,
                                     dtype="float32", callback=cb)

    def __enter__(self):
        self.stream.start()
        return self

    def __exit__(self, *exc):
        self.stream.close()

    @property
    def active(self):
        return self.stream.active


class WavCapture:
    """Replays a multichannel WAV into a Ring at real time (or as fast as possible). For offline tests."""

    def __init__(self, path, ring_s, realtime=True, blocksize=1024):
        self.x, self.fs = read_wav(path)
        self.channels = self.x.shape[1]
        # fast mode may run ahead of the reader, so the ring then holds the whole file
        self.ring = Ring(ring_s if realtime else len(self.x) / self.fs + 1.0, self.fs, self.channels)
        self.realtime, self.blocksize = realtime, blocksize
        self.overflows = 0
        self.done = False
        self._t = threading.Thread(target=self._play, daemon=True)

    def _play(self):
        t0 = time.monotonic()
        for i in range(0, len(self.x), self.blocksize):
            if self.realtime:
                time.sleep(max(0.0, t0 + i / self.fs - time.monotonic()))
            self.ring.write(self.x[i:i + self.blocksize])
        self.done = True

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        pass

    @property
    def active(self):
        return not self.done


def read_wav(path):
    """16-bit WAV -> ((n, channels) float32, fs)."""
    import wave
    with wave.open(path, "rb") as w:
        fs, ch = w.getframerate(), w.getnchannels()
        assert w.getsampwidth() == 2, "16-bit WAV only"
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, ch)
    return x.astype(np.float32) / 32768.0, fs


def write_wav(path, x, fs):
    """(n, channels) float -> 16-bit WAV."""
    import wave
    x = np.asarray(x)
    x = x.reshape(len(x), -1)
    with wave.open(path, "wb") as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


# ---------------------------------------------------------------- direction
def mic_array(mic_xy, channels=None):
    """config mic_xy {ch: (x, y)} -> (channels, (n, 2) array), sorted by channel."""
    chans = sorted(int(c) for c in mic_xy) if channels is None else list(channels)
    xy = {int(c): v for c, v in mic_xy.items()}
    return chans, np.array([xy[c] for c in chans], dtype=np.float64)


def pair_distances(xy):
    n = len(xy)
    return {(i, j): float(np.hypot(*(xy[i] - xy[j]))) for i in range(n) for j in range(i + 1, n)}


def estimate_bearing(x4, band, fs, mic_xy, c=343.0, offset_deg=0.0, upsample=UPSAMPLE, beta=PHAT_BETA, curve=False):
    """GCC-PHAT bearing of a source in `band` from raw mic signals.

    x4: (n_samples, n_mics), columns in the same order as the rows of mic_xy ((n_mics, 2), meters).
    beta: PHAT exponent (1 = full PHAT). 0.7 picked from the 2 m / 4 m calibration recordings: full
    whitening lets reverb pick a neighbouring cycle of the ~3 kHz carrier on some pairs.
    -> (deg, conf): bearing clockwise from +x (SPEC 2) in -180..180, conf 0..1.
    curve=True -> (deg, conf, score): score = the coarse curve on COARSE_DEG (no offset), scaled so median 0, max 1."""
    x = np.asarray(x4, dtype=np.float64)
    p = np.asarray(mic_xy, dtype=np.float64)
    n, m = x.shape
    x = x - x.mean(axis=0)
    nfft = 1 << int(math.ceil(math.log2(n + 64)))
    X = np.fft.rfft(x, nfft, axis=0)
    f = np.fft.rfftfreq(nfft, 1.0 / fs)
    f_lo, f_hi = BANDS[band]
    sel = (f >= f_lo - BAND_MARGIN_HZ) & (f <= f_hi + BAND_MARGIN_HZ)
    Xb, fb = X[sel], f[sel]

    pairs = [(i, j) for i in range(m) for j in range(i + 1, m)]
    G = np.stack([Xb[:, i] * np.conj(Xb[:, j]) for i, j in pairs], axis=1)
    G /= np.abs(G) ** beta + 1e-12                               # (partial) PHAT weighting
    # Correlation on a lag grid 1/(upsample*fs) wide = the zero-padded (upsample x) inverse FFT,
    # evaluated only at the lags a pair this close can produce.
    max_tau = max(np.hypot(*(p[i] - p[j])) for i, j in pairs) / c
    L = int(math.ceil(max_tau * fs * upsample)) + 2
    lags = np.arange(-L, L + 1) / (fs * upsample)
    E = np.exp(2j * np.pi * np.outer(fb, lags))                  # (bins, lags)
    r = (G.T @ E).real / max(1, len(fb))                         # (pairs, lags), peak at tau = t_i - t_j

    def score(theta_deg):
        th = np.radians(theta_deg)
        u = np.stack([np.cos(th), np.sin(th)], axis=1)          # source direction
        s = np.zeros(len(th))
        for k, (i, j) in enumerate(pairs):
            tau = -((p[i] - p[j]) @ u.T) / c                     # t_i - t_j for a far-field source at u
            s += np.interp(tau, lags, r[k])
        return s

    coarse = np.arange(-180.0, 180.0, 1.0)
    sc = score(coarse)
    best = coarse[int(np.argmax(sc))]
    fine = best + np.arange(-1.0, 1.0001, 0.1)
    deg = float(fine[int(np.argmax(score(fine)))])
    hi, lo, med = float(sc.max()), float(sc.min()), float(np.median(sc))
    conf = min(1.0, max(0.0, (hi - med) / (hi - lo + 1e-9)))
    deg = (deg + offset_deg + 180.0) % 360.0 - 180.0
    if curve:
        return round(deg, 1), round(conf, 2), (sc - med) / (hi - med + 1e-9)
    return round(deg, 1), round(conf, 2)


COARSE_DEG = np.arange(-180.0, 180.0, 1.0)      # the grid of estimate_bearing's coarse curve


class BearingAccumulator:
    """Sum the last n score curves per (id, hops) (N4: single-frame bearings jump with the band, because each
    band reflects differently; the true direction is the one the bands agree on). n = 1 means off."""

    def __init__(self, n=4, max_age_s=40.0):
        self.n, self.max_age_s, self.hist = int(n), float(max_age_s), {}

    def add(self, key, now, score, offset_deg=0.0):
        h = [(t, sc) for t, sc in self.hist.get(key, []) if now - t <= self.max_age_s][-(self.n - 1):] if self.n > 1 else []
        h.append((now, score))
        self.hist[key] = h
        tot = np.sum([sc for _, sc in h], axis=0)
        k = int(np.argmax(tot))
        hi, lo, med = float(tot[k]), float(tot.min()), float(np.median(tot))
        conf = min(1.0, max(0.0, (hi - med) / (hi - lo + 1e-9)))
        deg = (float(COARSE_DEG[k]) + offset_deg + 180.0) % 360.0 - 180.0
        return round(deg, 1), round(conf, 2), len(h)


def bearing_window(frame, fs, window):
    """(start, stop) sample range (decoder timeline) used for the bearing of `frame`."""
    start, stop = preamble_segment(range(frame.sample_index + 1), frame, fs)   # only len() is used
    if window == "frame":
        stop = start + int(round(FRAME_S * fs))
    return start, stop


def band_noise_db(x, fs):
    """Mean power (dBFS, 10log10 of mean square) inside each SPEC band of a mono signal."""
    x = np.asarray(x, dtype=np.float64)
    X = np.fft.rfft(x - x.mean())
    f = np.fft.rfftfreq(len(x), 1.0 / fs)
    psd = np.abs(X) ** 2 * 2.0 / (len(x) ** 2)                  # sum over all bins = mean square
    return [round(10 * math.log10(float(psd[(f >= lo) & (f <= hi)].sum()) + 1e-12), 1) for lo, hi in BANDS]


# ---------------------------------------------------------------- victims
REPORT_FIELDS = ("floor", "minutes", "motion", "status", "people", "battery", "knock")   # what a phone report may refresh


class Tracker:
    """One record per id: confirmation (SPEC 1.7.6), hops-0 preference, phones' heard reports."""

    def __init__(self, bus, cfg):
        self.bus = bus
        self.confirm_s = cfg.get("confirm_s", 60.0)
        self.hold_s = cfg.get("direct_hold_s", 30.0)
        self.report_hold_s = cfg.get("report_hold_s", 90.0)
        self.recs = {}
        self.lock = threading.Lock()

    def _rec(self, vid, now):
        r = self.recs.get(vid)
        if r is None:
            r = self.recs[vid] = {"first": now, "confirmed": False, "direct": None, "station": None, "event": None}
        elif not r["confirmed"] and now - r["first"] <= self.confirm_s:
            r["confirmed"] = True
        return r

    def frame(self, fields, deg, band, snr_db, now, station=True):
        """A valid frame for fields["id"] (station=False: from a phone's heard report). -> published event."""
        vid = fields["id"]
        with self.lock:
            r = self._rec(vid, now)
            hops = fields.get("hops", 0) or 0
            if not station and r["station"] is not None and now - r["station"] < self.report_hold_s and r["event"]:
                # SPEC v1.2: a phone's report about an id we decoded ourselves refreshes the fields only.
                # Our deg, band, snr_db and hops stay (N4: without this "via 1 relay" flipped to "no fix").
                ev = dict(r["event"])
                ev.update({k: fields[k] for k in REPORT_FIELDS if k in fields})
            elif station and hops > 0 and r["direct"] is not None and now - r["direct"] < self.hold_s and r["event"]:
                r["station"] = now
                ev = dict(r["event"])           # relayed copy of a fresh original: only "last heard" moves
            else:
                if station:
                    r["station"] = now
                    if deg is not None:
                        r["deg"], r["deg_t"], r["deg_hops"] = deg, now, hops
                    elif r.get("deg") is not None and r["deg_hops"] == hops and now - r["deg_t"] < self.report_hold_s:
                        # this band gives no bearing (doa_bands): keep the last one we measured at the same hops.
                        # Not from a relayed copy of a phone we hear directly: that's the relaying phone's direction.
                        deg = r["deg"]
                ev = {"t": "victim", **fields, "deg": deg, "band": band, "snr_db": round(snr_db, 1)}
                if hops == 0 and station:
                    r["direct"] = now
            ev["confirmed"] = r["confirmed"]
            ev.pop("ts", None)
            r["event"] = ev
        self.bus.publish(dict(ev))
        return ev

    def expire(self, now):
        with self.lock:
            gone = [v for v, r in self.recs.items() if not r["confirmed"] and now - r["first"] > self.confirm_s]
            for v in gone:
                del self.recs[v]
        for v in gone:
            log.info("victim %s unconfirmed for %.0f s, forgotten", v, self.confirm_s)
            self.bus.drop_victim(v)

    def is_confirmed(self, vid):
        r = self.recs.get(vid)
        return bool(r and r["confirmed"])


# ---------------------------------------------------------------- module
def _decode_channel(cfg):
    ch = cfg.get("decode_channel", 2)
    return ASR_CHANNEL if ch == "asr" else int(ch)


def run(bus, cfg: dict, capture=None) -> None:
    fs = int(cfg.get("fs", 16000))
    if capture is None:
        try:
            dev, info = find_device(cfg.get("device", "auto"))
        except Exception as e:
            log.warning("audio device lookup failed (%s); audio off", e)
            return
        if dev is None:
            log.warning("no XVF3800/reSpeaker mic array found (plug it into the Pi); audio off")
            return
        channels = min(int(cfg.get("channels", 6)), int(info["max_input_channels"]))
        log.info("mic array: [%d] %s, %d input channels", dev, info["name"], info["max_input_channels"])
        capture = Capture(dev, fs, channels, int(cfg.get("blocksize", 1024)), float(cfg.get("ring_s", 8.0)))
    channels = capture.channels

    raw_chans, mic_xy = mic_array(cfg["mic_xy"])
    doa_ok = channels > max(raw_chans)
    dch = _decode_channel(cfg)
    if not doa_ok:
        log.warning("only %d channels (2-channel firmware?): no raw mics, so no bearings. "
                    "Flash the 6-channel firmware (README, Audio). Decoding the ASR channel.", channels)
        dch = ASR_CHANNEL
    window = cfg.get("doa_window", "preamble")
    beta = float(cfg.get("phat_beta", PHAT_BETA))
    c = float(cfg.get("speed_of_sound", 343.0))
    offset = float(cfg.get("bearing_offset_deg", 0.0))
    ignore = {str(v).upper() for v in cfg.get("ignore_direct_ids", [])}
    quiet_db = float(cfg.get("quiet_db", -55.0))
    log.info("decoding ch%d, bearing window %s, raw mics %s, offset %+.1f deg%s", dch, window, raw_chans, offset,
             f", ignoring direct frames from {sorted(ignore)}" if ignore else "")

    tracker = Tracker(bus, cfg)
    doa_bands = {int(b) for b in cfg.get("doa_bands", (0, 1, 2, 3))}
    if doa_bands != {0, 1, 2, 3}:
        log.info("bearings only from bands %s (doa_bands); other frames keep the last direction", sorted(doa_bands))
    n_acc = int(cfg.get("doa_accumulate", 1))
    acc = BearingAccumulator(n_acc, float(cfg.get("doa_accumulate_s", 40.0))) if n_acc > 1 else None
    if acc:
        log.info("bearing = sum of the last %d frames' score curves per id (doa_accumulate)", n_acc)

    def on_heard(ev):
        fields = dict(ev.get("fields") or {})
        vid = str(ev.get("id") or fields.get("id") or "").upper()
        if not vid:
            return
        fields["id"] = vid
        fields = {k: v for k, v in fields.items() if k not in ("t", "ts", "deg", "band", "snr_db", "confirmed")}
        out = tracker.frame(fields, None, ev.get("band"), float(ev.get("snr_db") or 0.0), time.monotonic(),
                            station=False)
        if out:
            log.info("heard report %s via %s -> victim (deg %s, hops %s, confirmed=%s)", vid, ev.get("via"),
                     out.get("deg"), out.get("hops"), out["confirmed"])

    bus.subscribe("heard", on_heard)

    dec = Decoder(fs)
    base = 0                      # absolute sample index of the decoder's sample 0
    fed = 0                       # absolute index of the next sample to feed
    cpu = {"feed": 0.0, "doa": 0.0}
    audio_s = 0.0
    last_cpu_log = last_noise = last_data = time.monotonic()

    def frames_out(frames, now):
        for fr in frames:
            handle_frame(fr, base, capture, raw_chans, mic_xy, window, c, offset, ignore, tracker, bus, cpu, fs,
                         doa_ok, now, beta, acc, doa_bands)

    with capture:
        while True:
            time.sleep(0.05)
            now = time.monotonic()
            count = capture.ring.count
            if count > fed:
                last_data = now
            elif isinstance(capture, WavCapture) and capture.done:
                frames_out(dec.flush(), now)
                log.info("wav finished")
                return
            elif not capture.active:
                raise RuntimeError("audio stream stopped (array unplugged?)")
            elif now - last_data > STALL_S:
                raise RuntimeError(f"no audio from the array for {STALL_S:.0f} s (unplugged?)")

            if count - fed > capture.ring.n - fs:     # fell behind the ring: restart the decoder there
                log.warning("decoder fell %.1f s behind; skipping ahead", (count - fed) / fs)
                fed = base = count - fs
                dec = Decoder(fs)

            if count > fed:
                block = capture.ring.read(fed, count)
                t0 = time.thread_time()
                frames = dec.feed(block[:, dch])
                cpu["feed"] += time.thread_time() - t0
                audio_s += (count - fed) / fs
                fed = count
                frames_out(frames, now)

            if now - last_noise >= 1.0 and fed >= fs:
                last_noise = now
                x = capture.ring.read(fed - fs, fed)
                if x is not None:
                    band_db = band_noise_db(x[:, dch], fs)
                    bus.publish({"t": "noise", "band_db": band_db, "quiet": all(d < quiet_db for d in band_db)})
                tracker.expire(now)

            if now - last_cpu_log >= cfg.get("cpu_log_s", 30.0) and audio_s > 0:
                log.info("decoder CPU %.1f%% of one core (decode %.1f%%, bearing %.1f%%), %d overflows",
                         100 * (cpu["feed"] + cpu["doa"]) / audio_s, 100 * cpu["feed"] / audio_s,
                         100 * cpu["doa"] / audio_s, capture.overflows)
                cpu = {"feed": 0.0, "doa": 0.0}
                audio_s = 0.0
                last_cpu_log = now


def handle_frame(fr, base, capture, raw_chans, mic_xy, window, c, offset, ignore, tracker, bus, cpu, fs, doa_ok,
                 now, beta=PHAT_BETA, acc=None, bands=None):
    f = fr.fields
    vid, hops = f["id"], f.get("hops", 0)
    if hops == 0 and vid in ignore:
        log.info("frame %s hops 0 dropped (ignore_direct_ids, relay demo)", vid)
        return
    deg = conf = raw = None
    if doa_ok and (bands is None or fr.band in bands):
        start, stop = bearing_window(fr, fs, window)
        x = capture.ring.read(base + start, base + stop)
        if x is None:
            log.warning("frame %s: bearing window no longer in the ring", vid)
        else:
            t0 = time.thread_time()
            if acc is None:
                deg, conf = estimate_bearing(x[:, raw_chans], fr.band, fs, mic_xy, c, offset, beta=beta)
                raw = deg
            else:
                raw, conf1, sc = estimate_bearing(x[:, raw_chans], fr.band, fs, mic_xy, c, offset, beta=beta, curve=True)
                deg, conf, used = acc.add((vid, hops), now, sc, offset)
                log.info("frame %s band %d raw bearing %+.1f (conf %.2f) -> %+.1f over %d frames", vid, fr.band, raw,
                         conf1, deg, used)
            cpu["doa"] += time.thread_time() - t0
    if deg is not None and hops == 0:
        # A relayed frame's direction is the relaying phone's, not the victim's: no bearing event for it.
        bus.publish({"t": "bearing", "deg": deg, "conf": conf, "band": fr.band, "snr_db": round(fr.snr_db, 1),
                     "src": "tag", "id": vid, "raw_deg": raw})
    ev = tracker.frame(f, deg, fr.band, fr.snr_db, now)
    log.info("frame %s band %d snr %.1f q %.2f deg %s conf %s hops %d confirmed %s", vid, fr.band, fr.snr_db,
             fr.quality, deg, conf, hops, ev["confirmed"] if ev else None)


if __name__ == "__main__":
    from ear.bus import PrintBus
    from ear.config import CONFIG
    ap = argparse.ArgumentParser(description="Station audio module, standalone (prints JSON events)")
    ap.add_argument("--wav", help="replay a 6-channel 16-bit WAV instead of the live array")
    ap.add_argument("--fast", action="store_true", help="with --wav: don't wait for real time")
    ap.add_argument("--window", choices=["preamble", "frame"], help="override doa_window")
    ap.add_argument("--channel", help='override decode_channel (2..5 or "asr")')
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    cfg = dict(CONFIG["audio"])
    if a.window:
        cfg["doa_window"] = a.window
    if a.channel:
        cfg["decode_channel"] = a.channel if a.channel == "asr" else int(a.channel)
    cap = WavCapture(a.wav, max(cfg["ring_s"], 8.0), realtime=not a.fast) if a.wav else None
    try:
        run(PrintBus(), cfg, capture=cap)
    except KeyboardInterrupt:
        pass
