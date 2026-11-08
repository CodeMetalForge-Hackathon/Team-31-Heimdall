"""Ear configuration. One dict. Override the module list with env HEIMDALL_MODULES=mock,thermal."""
import logging
import os
from pathlib import Path


def _env_num(name, conv, default):
    """A numeric env override, or `default` (with one log line) when the value doesn't parse:
    a typo in ~/heimdall.env must not crash-loop the service at import."""
    v = os.environ.get(name)
    if not v:
        return default
    try:
        return conv(v)
    except ValueError:
        logging.getLogger("config").error("bad %s=%r, keeping %r", name, v, default)
        return default



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
    "pantilt": {"port": "auto", "pan_center_raw": 90, "tilt_level_raw": 90,
                # Measured 2026-11-08 on the stage head (thermal frames at servo -62/0/+62 + video): a positive servo pan
                # turns this camera LEFT, and with the servo centred it looks 30 deg right of the mic array's front arrow.
                "pan_dir": -1,           # -1 if a positive servo pan turns the camera LEFT (servo mounted the other way round)
                "pan_offset_deg": 30.0},  # bearing the camera looks at with the pan servo centred (its zero vs the mic front arrow)
    "thermal": {"device": "auto"},
    "audio": {
        "device": "auto",            # sounddevice name or index; "auto" = first input whose name has XVF3800/reSpeaker
        "fs": 16000,                 # the array's max rate; every SPEC band is below 7 kHz
        "channels": 6,               # 6-ch firmware: ch0 conference, ch1 ASR, ch2-5 raw mics 0-3
        "blocksize": 1024,
        "ring_s": 8.0,               # seconds of all channels kept for the bearing windows
        "decode_channel": 2,         # 2..5 = a raw mic, "asr" = ch1. A/B at 2-4 m: raw 87-96% decoded, asr 29-48%
        "doa_window": "preamble",    # "preamble" (200 ms) or "frame" (2.13 s); preamble won the A/B (74% vs 68% within 15 deg)
        # Mic openings (x, y) in meters, keyed by raw channel. Origin = array center, +x = front arrow
        # (12 o'clock, opposite the USB cable), +y = right (SPEC 2). Measured: 6.65 cm square, 9.35 cm diagonal.
        "mic_xy": {4: (0.03325, -0.03325),    # 10:30 front-left
                   5: (0.03325, 0.03325),     # 1:30 front-right
                   2: (-0.03325, 0.03325),    # 4:30 back-right
                   3: (-0.03325, -0.03325)},  # 7:30 back-left
        "speed_of_sound": 343.0,     # m/s
        "phat_beta": 0.7,            # GCC-PHAT whitening exponent (1 = full PHAT); 0.7 won on the calibration set
        "bearing_offset_deg": 0.0,   # added to every bearing so "ahead" reads 0 (calibration)
        "quiet_db": -55.0,           # noise.quiet = every band below this (dBFS)
        "confirm_s": 60.0,           # a new id needs a 2nd frame within this to be confirmed (SPEC 1.7.6)
        "direct_hold_s": 30.0,       # a hops-0 frame this recent makes relayed copies only refresh "last heard"
        "ignore_direct_ids": [],     # relay demo: drop hops-0 frames from these ids, e.g. ["1A2B"]
        "report_hold_s": 90.0,       # a phone's heard report about an id we decoded this recently only refreshes its fields (SPEC v1.2)
        "doa_accumulate": 1,         # 1 = bearing from each frame alone; 4 = sum the last 4 frames' score curves per id
        "doa_accumulate_s": 40.0,    # ...but only frames from the last 40 s
        "doa_bands": [0, 1, 2, 3],   # bands whose frames give a bearing; the others keep the last one (N7)
        "doa_front_deg": 95,         # bearings further than this from the front arrow are reflections on stage
                                     # (nothing chirps behind the station): dropped, the last one kept. 0 = off
        "cpu_log_s": 30.0,           # how often to log the decoder CPU share
    },
    "lora": {"freq_mhz": 915.0},
    "mock": {},
}

_env = os.environ.get("HEIMDALL_MODULES")
if _env is not None:
    CONFIG["modules"] = [m.strip() for m in _env.split(",") if m.strip()]

# Relay demo on stage: HEIMDALL_IGNORE_DIRECT=1A2B ear/tools/restart_ear.sh   (see README, Audio)
_env = os.environ.get("HEIMDALL_IGNORE_DIRECT")
if _env is not None:
    CONFIG["audio"]["ignore_direct_ids"] = [v.strip().upper() for v in _env.split(",") if v.strip()]

# Bearing smoothing (N6): HEIMDALL_DOA_ACCUMULATE=4 sums the last 4 frames' score curves per id; 1 = off
CONFIG["audio"]["doa_accumulate"] = max(1, _env_num("HEIMDALL_DOA_ACCUMULATE", int, CONFIG["audio"]["doa_accumulate"]))

# Front-only bearings (N11): HEIMDALL_DOA_FRONT=95 ; 0 = take bearings from all around
CONFIG["audio"]["doa_front_deg"] = _env_num("HEIMDALL_DOA_FRONT", float, CONFIG["audio"]["doa_front_deg"])

# Camera head mount (N11): HEIMDALL_PAN_DIR=-1 (a positive servo pan turns the camera left), HEIMDALL_PAN_OFFSET=30
CONFIG["pantilt"]["pan_dir"] = -1 if _env_num("HEIMDALL_PAN_DIR", int, CONFIG["pantilt"]["pan_dir"]) < 0 else 1
CONFIG["pantilt"]["pan_offset_deg"] = _env_num("HEIMDALL_PAN_OFFSET", float, CONFIG["pantilt"]["pan_offset_deg"])

# Bands that give bearings (N7): HEIMDALL_DOA_BANDS=1,2 ; empty = all four
CONFIG["audio"]["doa_bands"] = _env_num("HEIMDALL_DOA_BANDS", lambda s: [int(b) for b in s.split(",") if b.strip()],
                                        CONFIG["audio"]["doa_bands"])
