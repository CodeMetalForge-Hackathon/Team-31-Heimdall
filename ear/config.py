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
    "audio": {"device": "auto", "fs": 16000},
    "lora": {"freq_mhz": 915.0},
    "mock": {},
}

_env = os.environ.get("HEIMDALL_MODULES")
if _env is not None:
    CONFIG["modules"] = [m.strip() for m in _env.split(",") if m.strip()]
