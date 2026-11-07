"""Monte-Carlo self test for the HEIMDALL-AC1 receiver (run: python -m modem.cli selftest).

SNR is full-band at 16 kHz: received-signal power during the frame / white-noise
power over 0..8 kHz. (In-band SNR is ~7-9 dB higher.) The room is a synthetic
impulse response: a unit direct path plus an exponentially decaying white-noise tail
(RT60 0.4 s) scaled to the requested direct-to-reverberant ratio."""
from __future__ import annotations

import time

import numpy as np

from . import heimdall_ac1 as ac1

FS = ac1.DECODE_FS


def random_fields(rng) -> dict:
    floor = int(rng.integers(-2, 30))
    return {
        "id": f"{int(rng.integers(0, 65536)):04X}",
        "floor": None if floor == -2 else floor,
        "minutes": int(rng.integers(0, 64)) * 2,
        "motion": bool(rng.integers(0, 2)),
        "status": ac1.STATUS[int(rng.integers(0, 4))],
        "people": int(rng.integers(0, 8)),
        "battery": int(rng.integers(0, 4)),
        "hops": int(rng.integers(0, 4)),
        "knock": bool(rng.integers(0, 2)),
    }


def room_ir(rng, drr_db: float, rt60: float = 0.4, fs: int = FS) -> np.ndarray:
    n = int(rt60 * fs * 1.2)
    h = np.zeros(n)
    h[0] = 1.0
    t = np.arange(n)
    tail = rng.standard_normal(n) * np.exp(-6.908 * t / (rt60 * fs))
    tail[:16] = 0.0                       # first reflections after ~1 ms
    tail *= np.sqrt(10 ** (-drr_db / 10) / np.sum(tail ** 2))
    return h + tail


def fftconv(x, h):
    n = len(x) + len(h) - 1
    nf = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, nf) * np.fft.rfft(h, nf), nf)[:n]


def make_stream(rng, frames, bands, snr_db=None, drr_db=None, speed=0.0, offsets=None,
                lead=1.0, gap=(0.8, 1.6)):
    """Concatenate frames (or overlay them at `offsets`) with impairments.
    Returns (audio, truth) where truth = [(raw, band, t_end_preamble)]."""
    fs_tx = FS / (1.0 + speed)            # tx clock fast by `speed` -> played back sped up
    waves = []
    for raw, band in zip(frames, bands):
        w = ac1._synth(raw, band, fs_tx)
        if drr_db is not None:
            w = fftconv(w, room_ir(rng, drr_db))
        waves.append(w)
    truth, starts = [], []
    if offsets is None:
        pos = int(lead * FS)
        for w in waves:
            starts.append(pos)
            pos += len(w) + int(rng.uniform(*gap) * FS)
        total = pos
    else:
        starts = [int((lead + o) * FS) for o in offsets]
        total = max(s + len(w) for s, w in zip(starts, waves)) + int(lead * FS)
    x = np.zeros(total)
    p_sig = []
    for s, w, raw, band in zip(starts, waves, frames, bands):
        x[s:s + len(w)] += w
        n_frame = int(ac1.FRAME_S * fs_tx)
        p_sig.append(np.mean(w[:n_frame] ** 2))
        truth.append((bytes(raw), band, (s + ac1.PREAMBLE_S * fs_tx) / FS))
    if snr_db is not None:
        x += rng.standard_normal(total) * np.sqrt(np.mean(p_sig) / 10 ** (snr_db / 10))
    return x, truth


def run_stream(x, fs=FS, chunk=1024, rng=None, **dec_kw):
    d = ac1.Decoder(fs, **dec_kw)
    out = []
    i = 0
    while i < len(x):
        n = chunk if rng is None else int(rng.integers(chunk // 4, chunk * 2))
        out += d.feed(x[i:i + n])
        i += n
    out += d.flush()
    return out, d


def score(found, truth, tol=0.05):
    """-> (hits, wrong) ; wrong = valid-CRC frames whose bytes match no transmission."""
    hit = [False] * len(truth)
    wrong = 0
    for f in found:
        ok = False
        for i, (raw, band, t) in enumerate(truth):
            if not hit[i] and f.raw == raw and abs(f.t_end_preamble - t) < tol:
                hit[i] = ok = True
                break
        if not ok and not any(f.raw == raw for raw, _, _ in truth):
            wrong += 1
    return sum(hit), wrong


CONDITIONS = [
    ("clean", dict()),
    ("snr20", dict(snr_db=20)),
    ("snr10", dict(snr_db=10)),
    ("snr5", dict(snr_db=5)),
    ("snr0", dict(snr_db=0)),
    ("snr-5", dict(snr_db=-5)),
    ("drr0+5dB", dict(drr_db=0, snr_db=5)),
    ("drr-5+5dB", dict(drr_db=-5, snr_db=5)),
    ("spd+.1%+5dB", dict(speed=0.001, snr_db=5)),
    ("spd-.1%+5dB", dict(speed=-0.001, snr_db=5)),
    ("drr-5+5dB+spd", dict(drr_db=-5, snr_db=5, speed=0.001)),
    ("drr-5+0dB", dict(drr_db=-5, snr_db=0)),
]


def decode_table(trials=50, seed=1, conditions=CONDITIONS, verbose=True, **dec_kw):
    rng = np.random.default_rng(seed)
    rows = {}
    total_wrong = 0
    t0 = time.time()
    audio_s = 0.0
    for band in range(4):
        for name, kw in conditions:
            frames = [ac1.pack(random_fields(rng)) for _ in range(trials)]
            x, truth = make_stream(rng, frames, [band] * trials, **kw)
            audio_s += len(x) / FS
            found, _ = run_stream(x, rng=rng, **dec_kw)
            hits, wrong = score(found, truth)
            total_wrong += wrong
            rows[(band, name)] = (hits / trials, wrong)
        if verbose:
            print(f"  band {band} done ({time.time() - t0:.0f} s)", flush=True)
    return rows, total_wrong, audio_s, time.time() - t0


def format_table(rows, conditions=CONDITIONS):
    names = [n for n, _ in conditions]
    w = max(len(n) for n in names) + 1
    lines = ["condition".ljust(w) + "".join(f"  band{b}" for b in range(4))]
    for n in names:
        cells = []
        for b in range(4):
            rate, wrong = rows[(b, n)]
            cells.append(f"{rate * 100:6.0f}%" + ("!" if wrong else " "))
        lines.append(n.ljust(w) + "".join(cells))
    return "\n".join(lines)


def collision_test(trials=20, seed=2, snr_db=10, drr_db=None):
    """Two frames on different bands, start times 0..0.5 s apart, equal level."""
    rng = np.random.default_rng(seed)
    pairs = [(0, 1), (1, 2), (2, 3), (0, 2), (1, 3), (0, 3)]
    res = {}
    for a, b in pairs:
        both = one = none = wrong = 0
        for _ in range(trials):
            fr = [ac1.pack(random_fields(rng)) for _ in range(2)]
            x, truth = make_stream(rng, fr, [a, b], snr_db=snr_db, drr_db=drr_db,
                                   offsets=[0.0, float(rng.uniform(0, 0.5))])
            found, _ = run_stream(x, rng=rng)
            hits, wr = score(found, truth)
            wrong += wr
            both += hits == 2
            one += hits == 1
            none += hits == 0
        res[(a, b)] = (both, one, none, wrong)
    return res


def same_band_collision(trials=20, seed=3, snr_db=10):
    rng = np.random.default_rng(seed)
    both = one = none = wrong = 0
    for _ in range(trials):
        band = int(rng.integers(0, 4))
        fr = [ac1.pack(random_fields(rng)) for _ in range(2)]
        x, truth = make_stream(rng, fr, [band, band], snr_db=snr_db,
                               offsets=[0.0, float(rng.uniform(0, 1.5))])
        found, _ = run_stream(x, rng=rng)
        hits, wr = score(found, truth)
        wrong += wr
        both += hits == 2
        one += hits == 1
        none += hits == 0
    return both, one, none, wrong


def false_alarm_test(seconds=300, seed=4):
    """Noise + clicks + tone bursts + band-limited noise bursts + off-spec chirps.
    Returns (frames_reported, preamble_candidates)."""
    rng = np.random.default_rng(seed)
    n = int(seconds * FS)
    x = 0.01 * rng.standard_normal(n)
    t = 0
    while t < n - FS:
        t += int(rng.uniform(0.1, 0.6) * FS)
        kind = rng.integers(0, 4)
        amp = 10 ** rng.uniform(-2, -0.2)
        if kind == 0:                                   # click / knock
            L = int(rng.integers(10, 200))
            x[t:t + L] += amp * rng.standard_normal(L) * np.exp(-np.arange(L) / (L / 4))
        elif kind == 1:                                 # whistle / alarm tone
            L = int(rng.uniform(0.05, 1.0) * FS)
            f = rng.uniform(1000, 7000)
            x[t:t + L] += amp * np.sin(2 * np.pi * f * np.arange(L) / FS)[:len(x[t:t + L])]
        elif kind == 2:                                 # speech-like noise burst
            L = int(rng.uniform(0.1, 0.8) * FS)
            seg = rng.standard_normal(L)
            spec = np.fft.rfft(seg)
            f = np.fft.rfftfreq(L, 1 / FS)
            fc = rng.uniform(1000, 6000)
            spec *= np.exp(-((f - fc) / 600) ** 2)
            seg = np.fft.irfft(spec, L)
            seg *= amp / (np.std(seg) + 1e-12)
            x[t:t + L] += seg[:len(x[t:t + L])]
        else:                                           # chirp at a wrong rate/length
            T = rng.uniform(0.05, 0.6)
            L = int(T * FS)
            f0, f1 = rng.uniform(1000, 7000, 2)
            tt = np.arange(L) / FS
            x[t:t + L] += (amp * np.sin(2 * np.pi * (f0 * tt + (f1 - f0) * tt * tt / (2 * T))))[:len(x[t:t + L])]
    found, d = run_stream(x)
    return len(found), d


def main(trials=50, quick=False, track=True):
    if quick:
        trials = min(trials, 10)
    print(f"HEIMDALL-AC1 selftest: {trials} random frames per band x condition, 16 kHz, "
          f"streamed in random chunks{'' if track else ', drift tracking OFF'}")
    rows, wrong, audio_s, dt = decode_table(trials, track=track)
    print()
    print(format_table(rows))
    print(f"\nwrong frames with valid CRC: {wrong}   ('!' marks a cell with any)")
    print(f"decoded {audio_s:.0f} s of audio in {dt:.1f} s "
          f"(incl. simulation) -> {audio_s / dt:.0f}x real time")
    target = rows[(0, "drr-5+5dB")][0], rows[(1, "drr-5+5dB")][0], rows[(2, "drr-5+5dB")][0], rows[(3, "drr-5+5dB")][0]
    ok = min(target) >= 0.9 and wrong == 0
    print(f"target (>= 90% at 5 dB SNR, DRR -5 dB, every band): {'PASS' if ok else 'FAIL'}")

    ct = 5 if quick else 20
    print(f"\nTwo frames at once on different bands ({ct} trials per pair, 10 dB SNR, start 0..0.5 s apart)")
    print("pair   both  one  none  wrong   |  same with DRR -5 dB room")
    r1 = collision_test(ct)
    r2 = collision_test(ct, seed=5, drr_db=-5)
    for k in r1:
        a, b = r1[k], r2[k]
        print(f"{k[0]}+{k[1]}    {a[0]:4d} {a[1]:4d} {a[2]:5d} {a[3]:6d}   |  {b[0]:4d} {b[1]:4d} {b[2]:5d} {b[3]:6d}")
    sb = same_band_collision(ct)
    print(f"same band, 0..1.5 s apart: both {sb[0]}  one {sb[1]}  none {sb[2]}  wrong {sb[3]}")

    secs = 60 if quick else 300
    nf, d = false_alarm_test(secs)
    outcomes = {}
    for c in d.candidates:
        outcomes[c["outcome"]] = outcomes.get(c["outcome"], 0) + 1
    print(f"\nFalse alarms: {secs} s of noise + clicks + tones + speech-like bursts + "
          f"off-spec chirps -> {nf} frames reported; last-200 candidate outcomes {outcomes}")
    return ok
