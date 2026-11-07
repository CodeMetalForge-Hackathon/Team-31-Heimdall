"""Ear configuration. One dict. Override the module list with env HEIMDALL_MODULES=mock,thermal."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CONFIG = {
    "modules": ["mock"],
    "host": "0.0.0.0",
    "port": 8443,
    "cert": str(ROOT / "ear" / "certs" / "cert.pem"),
    "key": str(ROOT / "ear" / "certs" / "key.pem"),
    "web_dir": str(ROOT / "web"),
    "health_period_s": 5.0,
    "restart_delay_s": 3.0,

    # per-module settings (placeholders until the hardware is wired)
    "pantilt": {"port": "auto", "pan_center_raw": 90, "tilt_level_raw": 90},
    "thermal": {"device": "auto"},
    "audio": {
        "device": "auto",            # sounddevice name or index; "auto" = first input whose name has XVF3800/reSpeaker
        "fs": 16000,                 # the array's max rate; every SPEC band is below 7 kHz
        "channels": 6,               # 6-ch firmware: ch0 conference, ch1 ASR, ch2-5 raw mics 0-3
        "blocksize": 1024,
        "ring_s": 8.0,               # seconds of all channels kept for the bearing windows
        "decode_channel": 2,         # channel fed to the decoder: 2..5 = a raw mic, "asr" = ch1 (processed)
        "doa_window": "preamble",    # "preamble" = the 200 ms preamble, "frame" = preamble start .. frame end
        # Mic openings (x, y) in meters, keyed by raw channel. Origin = array center, +x = front arrow
        # (12 o'clock, opposite the USB cable), +y = right (SPEC 2). Measured: 6.65 cm square, 9.35 cm diagonal.
        "mic_xy": {4: (0.03325, -0.03325),    # 10:30 front-left
                   5: (0.03325, 0.03325),     # 1:30 front-right
                   2: (-0.03325, 0.03325),    # 4:30 back-right
                   3: (-0.03325, -0.03325)},  # 7:30 back-left
        "speed_of_sound": 343.0,     # m/s
        "bearing_offset_deg": 0.0,   # added to every bearing so "ahead" reads 0 (calibration)
        "quiet_db": -55.0,           # noise.quiet = every band below this (dBFS)
        "confirm_s": 60.0,           # a new id needs a 2nd frame within this to be confirmed (SPEC 1.7.6)
        "direct_hold_s": 30.0,       # a hops-0 frame this recent makes relayed copies only refresh "last heard"
        "ignore_direct_ids": [],     # relay demo: drop hops-0 frames from these ids, e.g. ["1A2B"]
        "cpu_log_s": 30.0,           # how often to log the decoder CPU share
    },
    "lora": {"freq_mhz": 915.0},
    "mock": {},
}

_env = os.environ.get("HEIMDALL_MODULES")
if _env is not None:
    CONFIG["modules"] = [m.strip() for m in _env.split(",") if m.strip()]
