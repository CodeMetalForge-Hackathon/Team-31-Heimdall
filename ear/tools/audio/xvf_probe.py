"""XVF3800 bring-up helper (run on the Pi from ~/Team-31 with ~/heimdall-venv/bin/python).

  python ear/tools/audio/xvf_probe.py --list              input devices; marks the array
  python ear/tools/audio/xvf_probe.py --record 5 out.wav  all channels, 16-bit
  python ear/tools/audio/xvf_probe.py --levels            live per-channel dBFS bars (5 Hz)
  python ear/tools/audio/xvf_probe.py --tap               live: loudest raw channel (2-5), every 0.2 s
"""
import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ear.modules.audio import ARRAY_NAMES, Capture, find_device, write_wav  # noqa: E402

FS = 16000
RAW = (2, 3, 4, 5)


def db(x):
    return 10 * math.log10(float(np.mean(np.asarray(x, dtype=np.float64) ** 2)) + 1e-12)


def open_capture(a):
    dev, info = find_device(a.device)
    if dev is None:
        sys.exit("no XVF3800/reSpeaker input found; is it plugged in? (--list)")
    ch = info["max_input_channels"]
    print(f"[{dev}] {info['name']}: {ch} input channels" + ("" if ch >= 6 else "  (2-channel firmware: no raw mics!)"))
    return Capture(dev, FS, ch, 1024, 4.0)


def live(cap, period, show):
    pos = cap.ring.count
    with cap:
        while True:
            time.sleep(period)
            n = cap.ring.count
            x = cap.ring.read(max(pos, n - int(period * FS)), n)
            pos = n
            if x is not None and len(x):
                show(x)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", default="auto")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true")
    g.add_argument("--record", nargs=2, metavar=("SECONDS", "OUT_WAV"))
    g.add_argument("--levels", action="store_true")
    g.add_argument("--tap", action="store_true")
    a = ap.parse_args()

    if a.list:
        import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                mark = "  <== mic array" if any(n in d["name"].lower() for n in ARRAY_NAMES) else ""
                print(f"[{i}] {d['name']}: {d['max_input_channels']} in, {d['default_samplerate']:.0f} Hz{mark}")
        return

    cap = open_capture(a)
    if a.record:
        secs, out = float(a.record[0]), a.record[1]
        with cap:
            time.sleep(secs + 0.2)
        x = cap.ring.read(max(0, cap.ring.count - int(secs * FS)), cap.ring.count)
        write_wav(out, x, FS)
        print(f"wrote {out}: {len(x) / FS:.1f} s x {x.shape[1]} ch; per-channel dBFS:",
              " ".join(f"ch{i}={db(x[:, i]):.1f}" for i in range(x.shape[1])))
        return

    try:
        if a.levels:
            def show(x):
                cells = []
                for i in range(x.shape[1]):
                    d = db(x[:, i])
                    cells.append(f"ch{i} {d:6.1f} {'#' * max(0, int((d + 80) / 4)):<20}")
                print(" | ".join(cells), flush=True)
            live(cap, 0.2, show)
        else:
            if cap.channels < 6:
                sys.exit("--tap needs the 6-channel firmware (raw mics on ch2-5)")

            def show(x):
                lv = {c: db(x[:, c]) for c in RAW}
                order = sorted(lv, key=lv.get, reverse=True)
                top, second = order[0], order[1]
                margin = lv[top] - lv[second]
                print(f"loudest ch{top} ({lv[top]:6.1f} dB, +{margin:4.1f} over ch{second})"
                      + ("  <==" if margin > 3 else "") + "   " + "  ".join(f"ch{c} {lv[c]:6.1f}" for c in RAW),
                      flush=True)
            live(cap, 0.2, show)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
