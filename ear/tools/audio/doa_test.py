"""Live direction test: decoder + bearing, one line per frame, a summary at the end (and every 10 frames).

Runs two decoders at once (the raw decode channel and the processed ASR channel) and computes both
bearing windows (preamble, whole frame) for every frame, so one run gives all the A/B numbers.

  python ear/tools/audio/doa_test.py --geometry                       print mic pair distances
  python ear/tools/audio/doa_test.py --true 90 --frames 10 --log calib.csv --save /tmp/r90.wav
  python ear/tools/audio/doa_test.py --wav /tmp/r90.wav --true 90     re-run on a saved recording
Phone: modem_test.html -> "Play burst" (band 1, every 3 s).
"""
import argparse
import csv
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ear.config import CONFIG  # noqa: E402
from ear.modules.audio import (ASR_CHANNEL, Capture, WavCapture, bearing_window, estimate_bearing,  # noqa: E402
                               find_device, mic_array, pair_distances, write_wav)
from modem.heimdall_ac1 import Decoder  # noqa: E402

WINDOWS = ("preamble", "frame")


def circ_stats(degs):
    if not degs:
        return None, None
    r = np.radians(degs)
    s, c = np.mean(np.sin(r)), np.mean(np.cos(r))
    R = min(1.0, math.hypot(s, c))
    return math.degrees(math.atan2(s, c)), math.degrees(math.sqrt(-2 * math.log(max(R, 1e-9))))


def err(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


def main():
    cfg = CONFIG["audio"]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geometry", action="store_true", help="print mic positions and pair distances, then exit")
    ap.add_argument("--wav", help="use a saved 6-channel recording instead of the live array")
    ap.add_argument("--true", type=float, help="true bearing of the phone (deg), for the error column")
    ap.add_argument("--frames", type=int, default=10, help="stop after this many raw-channel frames (0 = never)")
    ap.add_argument("--period", type=float, default=3.0, help="burst period (s), for the decode rate")
    ap.add_argument("--raw", action="store_true", help="ignore bearing_offset_deg (for calibrating it)")
    ap.add_argument("--save", help="save all channels of this run to a WAV")
    ap.add_argument("--log", help="append one summary row per (decoder, window) to this CSV")
    ap.add_argument("--label", default="", help="free text for the CSV (distance, notes)")
    a = ap.parse_args()

    chans, xy = mic_array(cfg["mic_xy"])
    c = cfg["speed_of_sound"]
    offset = 0.0 if a.raw else cfg["bearing_offset_deg"]
    if a.geometry:
        for ch, (x, y) in zip(chans, xy):
            print(f"ch{ch}: x={x:+.4f} y={y:+.4f} m  (at {math.degrees(math.atan2(y, x)):+.0f} deg, "
                  f"r={math.hypot(x, y) * 100:.1f} cm)")
        for (i, j), d in pair_distances(xy).items():
            print(f"ch{chans[i]}-ch{chans[j]}: {d * 100:.1f} cm = max {d / c * 16000:.2f} samples at 16 kHz")
        return

    fs = 16000
    if a.wav:
        cap = WavCapture(a.wav, 8.0, realtime=False)
    else:
        dev, info = find_device(cfg["device"])
        if dev is None:
            sys.exit("no mic array found")
        cap = Capture(dev, fs, info["max_input_channels"], 1024, 8.0)
    if cap.channels < 6:
        sys.exit(f"{cap.channels} channels: need the 6-channel firmware for raw mics")

    raw_ch = cfg["decode_channel"] if cfg["decode_channel"] != "asr" else 2
    decoders = {"raw": (raw_ch, Decoder(fs)), "asr": (ASR_CHANNEL, Decoder(fs))}
    res = {(d, w): [] for d in decoders for w in WINDOWS}
    ids = {d: [] for d in decoders}
    saved = [] if a.save else None
    fed = 0
    print(f"mics {chans}, offset {offset:+.1f}, raw decoder on ch{raw_ch}; play bursts now. Ctrl-C to stop.")

    def summary(final=False):
        elapsed = fed / fs
        rows = []
        print(f"--- {elapsed:.0f} s of audio" + (f", true {a.true:+.0f} deg" if a.true is not None else ""))
        for (d, w), v in res.items():
            degs = [x[0] for x in v]
            mean, std = circ_stats(degs)
            rate = len(degs) * a.period / elapsed if elapsed > 0 else 0.0
            e = f"{err(mean, a.true):+6.1f}" if (mean is not None and a.true is not None) else "     -"
            ms = f"{mean:+7.1f} +- {std:4.1f}" if mean is not None else "      -        "
            confs = f"{np.mean([x[1] for x in v]):.2f}" if v else "-"
            print(f"  {d:3s} ch{decoders[d][0]} {w:8s}: n={len(degs):2d}  mean {ms}  err {e}  conf {confs}  "
                  f"decode rate {min(rate, 1.0) * 100:3.0f}%")
            rows.append(dict(label=a.label, true=a.true, decoder=d, channel=decoders[d][0], window=w, n=len(degs),
                             mean=None if mean is None else round(mean, 1),
                             std=None if std is None else round(std, 1),
                             err=None if mean is None or a.true is None else round(err(mean, a.true), 1),
                             conf=confs, rate=round(min(rate, 1.0), 2), seconds=round(elapsed, 1)))
        if final and a.log:
            new = not Path(a.log).exists()
            with open(a.log, "a", newline="") as fh:
                wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
                if new:
                    wr.writeheader()
                wr.writerows(rows)
            print(f"appended to {a.log}")

    try:
        with cap:
            while True:
                time.sleep(0.05)
                n = cap.ring.count
                if n <= fed:
                    if a.wav and cap.done:
                        for name, (ch, dec) in decoders.items():
                            handle(name, dec.flush(), cap, chans, xy, c, offset, fs, res, ids)
                        break
                    continue
                block = cap.ring.read(fed, n)
                fed = n
                if saved is not None:
                    saved.append(block)
                for name, (ch, dec) in decoders.items():
                    if handle(name, dec.feed(block[:, ch]), cap, chans, xy, c, offset, fs, res, ids) and \
                            name == "raw" and len(ids["raw"]) % 10 == 0:
                        summary()
                if a.frames and len(ids["raw"]) >= a.frames:
                    time.sleep(0.5)
                    break
    except KeyboardInterrupt:
        pass
    summary(final=True)
    if saved:
        write_wav(a.save, np.concatenate(saved), fs)
        print(f"saved {a.save}")


def handle(name, frames, cap, chans, xy, c, offset, fs, res, ids):
    for fr in frames:
        out = []
        for w in WINDOWS:
            start, stop = bearing_window(fr, fs, w)
            x = cap.ring.read(start, stop)
            if x is None:
                out.append(f"{w} -")
                continue
            deg, conf = estimate_bearing(x[:, chans], fr.band, fs, xy, c, offset)
            res[(name, w)].append((deg, conf))
            out.append(f"{w} {deg:+7.1f} ({conf:.2f})")
        ids[name].append(fr.fields["id"])
        print(f"{name:3s} {fr.fields['id']} band {fr.band} snr {fr.snr_db:5.1f} q {fr.quality:.2f} hops "
              f"{fr.fields['hops']} | " + " | ".join(out), flush=True)
    return bool(frames)


if __name__ == "__main__":
    main()
