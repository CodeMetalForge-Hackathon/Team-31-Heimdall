"""HEIMDALL-AC1 command line.

  python -m modem.cli gen --id 1A2B --floor 2 --minutes 14 --motion 1 --status injured \\
                          --people 2 --battery 3 --band 1 --fs 48000 --repeat 3 --gap 1.0 -o out.wav
  python -m modem.cli decode in.wav
  python -m modem.cli live [--device N] [--fs 48000] [--record session.wav]
  python -m modem.cli selftest [--trials 50] [--quick]
  python -m modem.cli analyze recording.wav
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import wave

import numpy as np

from . import heimdall_ac1 as ac1


# ---------------------------------------------------------------- WAV I/O
def write_wav(path, x, fs):
    x = np.clip(np.asarray(x, dtype=np.float64), -1.0, 1.0)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(fs))
        w.writeframes((np.round(x * 32767)).astype("<i2").tobytes())


def read_wav(path, channel=None):
    """-> (float64 samples in -1..1, fs). Mono: `channel` index, or the mean if None."""
    try:
        with wave.open(path, "rb") as w:
            fs, nch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
            raw = w.readframes(w.getnframes())
        if sw == 1:
            x = (np.frombuffer(raw, np.uint8).astype(np.float64) - 128) / 128
        elif sw == 2:
            x = np.frombuffer(raw, "<i2") / 32768.0
        elif sw == 3:
            b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
            v = (b[:, 0].astype(np.int32) | b[:, 1].astype(np.int32) << 8 | b[:, 2].astype(np.int32) << 16)
            x = np.where(v >= 1 << 23, v - (1 << 24), v) / float(1 << 23)
        else:
            x = np.frombuffer(raw, "<i4") / float(1 << 31)
        x = x.reshape(-1, nch)
    except wave.Error:                        # float WAV etc.
        from scipy.io import wavfile
        fs, x = wavfile.read(path)
        if x.dtype.kind in "iu":
            x = x / float(np.iinfo(x.dtype).max)
        x = np.asarray(x, dtype=np.float64).reshape(len(x), -1)
    x = x[:, channel] if channel is not None else x.mean(axis=1)
    return x, fs


# ---------------------------------------------------------------- gen
def _fields_from_args(a):
    floor = None if str(a.floor).lower() in ("none", "?", "unknown", "") else int(a.floor)
    return {"id": a.id.upper(), "floor": floor, "minutes": a.minutes, "motion": bool(a.motion),
            "status": a.status, "people": a.people, "battery": a.battery, "hops": a.hops,
            "knock": bool(a.knock)}


def cmd_gen(a):
    fields = _fields_from_args(a)
    raw = ac1.pack(fields)
    parts = [np.zeros(int(a.lead * a.fs))]
    for k in range(a.repeat):
        band = (k + int(fields["id"], 16)) % 4 if a.band == "auto" else int(a.band)
        parts.append(ac1.synth(raw, band, a.fs).astype(np.float64))
        parts.append(np.zeros(int((a.gap if k < a.repeat - 1 else a.lead) * a.fs)))
        print(f"frame {k}: band {band} bytes {raw.hex(' ').upper()}", file=sys.stderr)
    write_wav(a.output, np.concatenate(parts), a.fs)
    print(f"wrote {a.output} ({sum(map(len, parts)) / a.fs:.2f} s @ {a.fs} Hz)", file=sys.stderr)


# ---------------------------------------------------------------- decode
def cmd_decode(a):
    x, fs = read_wav(a.input, a.channel)
    d = ac1.Decoder(fs)
    t0 = time.perf_counter()
    frames = []
    for i in range(0, len(x), 4096):
        frames += d.feed(x[i:i + 4096])
    frames += d.flush()
    dt = time.perf_counter() - t0
    for f in frames:
        print(json.dumps(f.to_json()))
    if a.verbose:
        for c in d.candidates:
            print("candidate", json.dumps(c), file=sys.stderr)
    dur = len(x) / fs
    print(f"{len(frames)} frame(s) in {dur:.1f} s @ {fs} Hz; decoder {dt * 1000:.0f} ms "
          f"= {100 * dt / max(dur, 1e-9):.2f}% of one core", file=sys.stderr)


# ---------------------------------------------------------------- live
def cmd_live(a):
    try:
        import sounddevice as sd
    except ImportError:
        sys.exit("live needs sounddevice:  pip install sounddevice")
    import queue

    if a.list:
        print(sd.query_devices())
        return
    fs = a.fs or int(sd.query_devices(a.device, "input")["default_samplerate"])
    q: queue.Queue = queue.Queue()

    def cb(indata, frames, t, status):
        q.put(indata[:, a.channel].copy())

    d = ac1.Decoder(fs)
    rec = [] if a.record else None
    stats = {b: 0 for b in range(4)}
    busy = 0.0
    audio = 0.0
    t_start = time.time()
    last_meter = 0.0
    ch = a.channel + 1
    print(f"listening on device {a.device if a.device is not None else 'default'} @ {fs} Hz "
          f"(Ctrl-C to stop)", file=sys.stderr)
    try:
        with sd.InputStream(samplerate=fs, channels=ch, device=a.device, blocksize=1024,
                            dtype="float32", callback=cb):
            while True:
                x = q.get()
                if rec is not None:
                    rec.append(x)
                t0 = time.perf_counter()
                frames = d.feed(x)
                busy += time.perf_counter() - t0
                audio += len(x) / fs
                for f in frames:
                    stats[f.band] += 1
                    j = f.to_json()
                    j["wall"] = round(time.time() - t_start, 2)
                    sys.stderr.write("\r" + " " * 100 + "\r")
                    print(json.dumps(j), flush=True)
                now = time.time()
                if now - last_meter > 0.2:
                    last_meter = now
                    lvl = d.level_db
                    bar = "#" * int(max(0, min(30, (lvl + 80) / 80 * 30)))
                    ratios = " ".join(f"b{b}:{d.band_ratio_db[b]:4.1f}" for b in range(4))
                    sys.stderr.write(f"\r{lvl:6.1f} dBFS |{bar:<30}| MF dB {ratios} | "
                                     f"cpu {100 * busy / max(audio, 1e-9):4.1f}%  ")
                    sys.stderr.flush()
    except KeyboardInterrupt:
        pass
    print("\n--- summary ---", file=sys.stderr)
    print(f"ran {audio:.0f} s, decoder cpu {100 * busy / max(audio, 1e-9):.2f}% of one core",
          file=sys.stderr)
    print("frames per band: " + ", ".join(f"b{b}={n}" for b, n in stats.items()), file=sys.stderr)
    outc = {}
    for c in d.candidates:
        key = (c["band"], c["outcome"])
        outc[key] = outc.get(key, 0) + 1
    print("preamble detections (band, outcome): " +
          ", ".join(f"b{b} {o}={n}" for (b, o), n in sorted(outc.items())), file=sys.stderr)
    if rec is not None:
        write_wav(a.record, np.concatenate(rec), fs)
        print(f"recorded {a.record}", file=sys.stderr)


# ---------------------------------------------------------------- selftest
def cmd_selftest(a):
    from . import selftest
    ok = selftest.main(trials=a.trials, quick=a.quick, track=not a.no_track)
    sys.exit(0 if ok else 1)


# ---------------------------------------------------------------- analyze
def _stft(x, fs, nfft=1024, hop=256):
    win = np.hanning(nfft)
    n = 1 + max(0, (len(x) - nfft) // hop)
    idx = np.arange(nfft)[None, :] + hop * np.arange(n)[:, None]
    S = np.abs(np.fft.rfft(x[idx] * win, axis=1)) ** 2 / np.sum(win ** 2)
    return S, np.fft.rfftfreq(nfft, 1 / fs), (np.arange(n) * hop + nfft / 2) / fs


def cmd_analyze(a):
    x, fs = read_wav(a.input, a.channel)
    base = os.path.splitext(a.input)[0]
    dur = len(x) / fs
    print(f"file {a.input}: {dur:.2f} s @ {fs} Hz")
    if fs < 16000:
        print("WARNING: sample rate below 16 kHz; band 3 cannot be represented")

    # level / clipping / DC
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    clip = int(np.sum(np.abs(x) >= 0.999))
    # flat tops: 3+ equal samples near the peak (clipping before the recorder's own gain)
    flat = int(np.sum((np.abs(x[1:-1]) > 0.5 * peak) & (x[1:-1] == x[:-2]) & (x[1:-1] == x[2:])))
    print(f"peak {20 * math.log10(peak + 1e-12):.1f} dBFS, rms {10 * math.log10(np.mean(x ** 2) + 1e-12):.1f} dBFS, "
          f"DC {np.mean(x):+.4f}, samples at full scale {clip}, flat-topped samples {flat}")
    if clip > 10 or flat > 10:
        print("  -> CLIPPING at the recorder (or the speaker drive is saturating): lower the PWM/DAC gain")

    S, f, t = _stft(x, fs)
    e = 10 * np.log10(S.sum(axis=1) + 1e-20)
    quiet = e <= np.percentile(e, 15)
    active = e >= np.percentile(e, 15) + 15
    noise_psd = np.median(S[quiet], axis=0) if quiet.any() else np.full(len(f), 1e-20)
    maxhold = np.max(S[active], axis=0) if active.any() else noise_psd
    resp_db = 10 * np.log10(maxhold + 1e-20)
    noise_db = 10 * np.log10(noise_psd + 1e-20)
    snr_f = resp_db - noise_db
    ref = np.max(resp_db[(f >= 1000) & (f <= 7000)]) if np.any((f >= 1000) & (f <= 7000)) else np.max(resp_db)
    print(f"active frames {int(active.sum())}/{len(e)}; noise floor (median of quietest 15%) "
          f"{10 * np.log10(np.sum(noise_psd) + 1e-20):.1f} dB")

    # harmonic distortion: dominant peak f0 per active frame, energy at 2f0 and 3f0
    thd = []
    df = f[1] - f[0]
    for i in np.flatnonzero(active):
        k0 = int(np.argmax(S[i]))
        f0 = f[k0]
        if f0 < 800 or 2 * f0 > f[-1]:
            continue
        p0 = S[i, max(0, k0 - 2):k0 + 3].sum()
        ph = 0.0
        for hmul in (2, 3):
            kh = int(round(hmul * f0 / df))
            if kh + 3 < len(f):
                ph += S[i, kh - 2:kh + 3].sum()
        thd.append((f0, 10 * np.log10(ph / (p0 + 1e-20) + 1e-20)))
    thd = np.array(thd) if thd else np.zeros((0, 2))

    print("\nper-band response (max-hold over active frames, relative to the loudest "
          "1-7 kHz bin) and SNR over the noise floor:")
    print("band  range (Hz)      level dB  ripple dB  SNR dB  2nd+3rd harm dB  verdict")
    verdict = {}
    for b, (lo, hi) in enumerate(ac1.BANDS):
        m = (f >= lo) & (f <= hi)
        lvl = float(np.mean(resp_db[m]) - ref)
        rip = float(np.max(resp_db[m]) - np.min(resp_db[m]))
        snr = float(np.mean(snr_f[m]))
        tm = (thd[:, 0] >= lo) & (thd[:, 0] <= hi) if len(thd) else np.zeros(0, bool)
        h = float(np.median(thd[tm, 1])) if tm.any() else float("nan")
        good = lvl > -12 and snr > 20 and rip < 15 and not (h > -15)
        ok = lvl > -20 and snr > 12
        verdict[b] = "GOOD" if good else ("usable" if ok else "POOR")
        hs = f"{h:7.1f}" if not math.isnan(h) else "    n/a"
        print(f"  {b}   {int(lo):4d}-{int(hi):4d}      {lvl:6.1f}    {rip:6.1f}   {snr:5.1f}   {hs}          {verdict[b]}")
    hi_m = f >= 7000
    if hi_m.any():
        print(f"energy above 7 kHz vs the loudest 1-7 kHz bin: {float(np.max(resp_db[hi_m]) - ref):.1f} dB "
              f"(PWM carrier / aliasing shows up here)")
    tones = f[(noise_db - np.median(noise_db) > 15) & (f > 100)]
    if len(tones):
        print("steady tones in the quiet parts (whine, PWM carrier, ground loop): "
              + ", ".join(f"{v:.0f} Hz" for v in tones[:12]))

    # decoder view
    d = ac1.Decoder(fs)
    frames = []
    for i in range(0, len(x), 4096):
        frames += d.feed(x[i:i + 4096])
    frames += d.flush()
    print(f"\ndecoder: {len(frames)} frame(s) decoded, {len(d.candidates)} preamble detection(s)")
    for c in d.candidates:
        if c["outcome"] != "busy":
            print("  ", json.dumps(c))
    for fr in frames:
        print("  frame", json.dumps(fr.to_json()))

    # plots
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("(matplotlib missing: no PNG)")
        return
    fig, ax = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [2, 1]})
    Sd = 10 * np.log10(S.T + 1e-20)
    vmax = np.percentile(Sd, 99.5)
    ax[0].pcolormesh(t, f, Sd, shading="auto", vmin=vmax - 70, vmax=vmax, cmap="magma")
    for b, (lo, hi) in enumerate(ac1.BANDS):
        ax[0].axhspan(lo, hi, color="cyan", alpha=0.08)
        ax[0].text(t[0] if len(t) else 0, (lo + hi) / 2, f" b{b}", color="cyan", va="center", fontsize=8)
    for c in d.candidates:
        ax[0].axvline(c["t"], color="lime" if c["outcome"] == "ok" else "red", lw=0.6, alpha=0.7)
    ax[0].set_ylim(0, min(fs / 2, 10000))
    ax[0].set_ylabel("Hz")
    ax[0].set_title(f"{os.path.basename(a.input)}  (green = decoded preamble, red = rejected)")
    ax[1].plot(f, resp_db - ref, label="max-hold (sweep response)")
    ax[1].plot(f, noise_db - ref, label="noise floor", alpha=0.7)
    for lo, hi in ac1.BANDS:
        ax[1].axvspan(lo, hi, color="C2", alpha=0.1)
    ax[1].set_xlim(0, min(fs / 2, 10000))
    ax[1].set_ylim(-90, 10)
    ax[1].set_xlabel("Hz")
    ax[1].set_ylabel("dB re max")
    ax[1].legend(loc="upper right")
    ax[1].grid(alpha=0.3)
    fig.tight_layout()
    png = base + "_analysis.png"
    fig.savefig(png, dpi=110)
    print(f"\nwrote {png}")


# ---------------------------------------------------------------- main
def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m modem.cli", description="HEIMDALL-AC1 modem tools")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="write frames to a WAV")
    g.add_argument("--id", default="1A2B")
    g.add_argument("--floor", default="none", help="-1..29 or none")
    g.add_argument("--minutes", type=int, default=0)
    g.add_argument("--motion", type=int, default=0)
    g.add_argument("--status", default="no_response", choices=ac1.STATUS)
    g.add_argument("--people", type=int, default=1)
    g.add_argument("--battery", type=int, default=3)
    g.add_argument("--hops", type=int, default=0)
    g.add_argument("--knock", type=int, default=0)
    g.add_argument("--band", default="1", help="0..3 or 'auto' ((k + id) %% 4)")
    g.add_argument("--fs", type=int, default=48000)
    g.add_argument("--repeat", type=int, default=1)
    g.add_argument("--gap", type=float, default=1.0, help="silence between frames (s)")
    g.add_argument("--lead", type=float, default=0.5, help="silence before/after (s)")
    g.add_argument("-o", "--output", default="out.wav")
    g.set_defaults(fn=cmd_gen)

    d = sub.add_parser("decode", help="decode a WAV, one JSON line per frame")
    d.add_argument("input")
    d.add_argument("--channel", type=int, default=None)
    d.add_argument("-v", "--verbose", action="store_true", help="also list preamble detections")
    d.set_defaults(fn=cmd_decode)

    lv = sub.add_parser("live", help="decode the microphone live")
    lv.add_argument("--device", type=lambda s: int(s) if s.isdigit() else s, default=None)
    lv.add_argument("--fs", type=int, default=None, help="capture rate (default: device default)")
    lv.add_argument("--channel", type=int, default=0)
    lv.add_argument("--record", default=None, help="also save the raw capture to this WAV")
    lv.add_argument("--list", action="store_true", help="list audio devices and exit")
    lv.set_defaults(fn=cmd_live)

    s = sub.add_parser("selftest", help="Monte-Carlo decode-rate table")
    s.add_argument("--trials", type=int, default=50)
    s.add_argument("--quick", action="store_true")
    s.add_argument("--no-track", action="store_true", help="disable drift tracking (SPEC 1.7.5 literal)")
    s.set_defaults(fn=cmd_selftest)

    an = sub.add_parser("analyze", help="spectrogram + per-band report for a speaker recording")
    an.add_argument("input")
    an.add_argument("--channel", type=int, default=None)
    an.set_defaults(fn=cmd_analyze)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
