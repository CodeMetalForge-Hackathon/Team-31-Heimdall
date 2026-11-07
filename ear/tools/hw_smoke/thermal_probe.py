#!/usr/bin/env python3
"""Grab one frame from the Hti thermal camera and report UVC yes/no."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

OUT_DEFAULT = "/tmp/thermal_frame.jpg"


def try_opencv(index: int, out_path: str) -> bool:
    try:
        import cv2  # type: ignore
    except ImportError:
        return False
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        return False
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return False
    if not cv2.imwrite(out_path, frame):
        return False
    h, w = frame.shape[:2]
    print(f"UVC yes: opencv /dev/video{index} {w}x{h} saved {out_path}")
    return True


def try_ffmpeg(dev: str, out_path: str) -> bool:
    if not os.path.exists(dev):
        return False
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "v4l2",
        "-i",
        dev,
        "-frames:v",
        "1",
        out_path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if r.returncode != 0 or not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
        return False
    print(f"UVC yes: ffmpeg {dev} saved {out_path}")
    return True


def try_fswebcam(dev: str, out_path: str) -> bool:
    if not os.path.exists(dev):
        return False
    cmd = ["fswebcam", "-d", dev, "--no-banner", "-r", "160x120", out_path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if r.returncode != 0 or not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
        return False
    print(f"UVC yes: fswebcam {dev} saved {out_path}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Heimdall thermal UVC probe")
    ap.add_argument("--device", default=None, help="e.g. /dev/video0")
    ap.add_argument("--out", default=OUT_DEFAULT)
    args = ap.parse_args()

    indices = []
    if args.device:
        if args.device.startswith("/dev/video"):
            indices = [int(args.device.replace("/dev/video", ""))]
        else:
            indices = [0]
    else:
        indices = list(range(0, 6))

    for i in indices:
        dev = args.device if args.device else f"/dev/video{i}"
        if try_opencv(i, args.out):
            return 0
        if try_ffmpeg(dev, args.out):
            return 0
        if try_fswebcam(dev, args.out):
            return 0

    print("UVC no: no camera produced a frame")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
