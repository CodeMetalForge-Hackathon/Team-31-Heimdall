"""Thermal camera (USB UVC; the station's is 640x512 YUYV, which runs in gray mode) -> video for the
operator page + hotspot detections.

Publishes JPEG frames (bus.set_frame -> /thermal.mjpg) and `thermal_det` events (docs/SPEC.md section 3):
x, y = top-left corner of each box, w, h = its size, all 0..1 of the image; deg = where the box is,
using the current pan angle (from `pantilt` events) and the camera's field of view.

Two modes, chosen from what the camera sends (override with cfg "mode"):
  "split": the frame is twice as tall as the picture (e.g. 256x384 YUYV). Top half = picture,
           bottom half = 16-bit raw values; temperature in C = raw / 64 - 273.15 (InfiRay-style).
  "gray":  a normal picture only. Hotspots by brightness; temperatures unknown (temp_c, max_c = null).
Standalone test:  python -m ear.modules.thermal      (also saves thermal_test.jpg every 5 s)
"""
import atexit
import glob
import logging
import os
import threading
import time

import numpy as np

log = logging.getLogger("thermal")

DEFAULTS = {
    "device": "auto",     # video index (e.g. 0) or "auto" = the first UVC camera that delivers frames
    "mode": "auto",       # "auto" | "split" | "gray"
    "hfov_deg": 56.0,     # horizontal field of view of the camera (256x192 phone thermal cams: ~56)
    "flip_h": False,      # mirror left/right. Measured 2026-11-08 on the station camera: the raw picture is a true view
                          # (pan right -> the scene moves left), so no flip. Check from BEHIND the camera: hand right, box right.
    "flip_v": False,
    "rotate": 0,          # 0, 90, 180, 270 (how the camera sits on the tilt plate)
    "fps": 9.0,           # JPEG frames per second for /thermal.mjpg
    "det_hz": 2.0,        # thermal_det events per second
    "min_area": 0.002,    # a hotspot must cover at least this fraction of the image
    "body_min_c": 28.0,   # split mode: ignore anything cooler than this
    "rel_c": 3.0,         # split mode: hot = within this many degrees of the hottest pixel
    "gray_pct": 98.0,     # gray mode: brightness percentile that counts as hot
    "max_hotspots": 3,
    "jpeg_quality": 80,
}
SKIP_NAMES = ("pispbe", "hevc", "rp1-cfe", "bcm2835", "codec", "isp")   # Pi 5 internal video nodes


def video_candidates(device):
    if device != "auto":
        return [int(str(device).replace("/dev/video", ""))]
    out = []
    for p in sorted(glob.glob("/dev/video*"), key=lambda s: int(s[10:]) if s[10:].isdigit() else 999):
        if not p[10:].isdigit():
            continue
        try:
            with open(f"/sys/class/video4linux/{os.path.basename(p)}/name") as f:
                name = f.read().strip().lower()
        except OSError:
            name = ""
        if any(k in name for k in SKIP_NAMES):
            continue
        out.append(int(p[10:]))
    return out


def open_camera(device):
    """(cap, index, first_raw_frame) or (None, None, None)."""
    import cv2
    for i in video_candidates(device):
        cap = cv2.VideoCapture(i, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            continue
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)   # raw bytes: split-mode cameras hide temperatures here
        ok, raw = cap.read()
        if ok and raw is not None and raw.size > 0:
            w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            log.info("camera /dev/video%d: %dx%d, raw frame %s %s", i, w, h, raw.shape, raw.dtype)
            return cap, i, raw
        cap.release()
    return None, None, None


def decode(raw, w, h, mode="auto"):
    """Raw OpenCV frame -> (gray uint8 image, temperatures in C or None, mode used)."""
    import cv2
    a = np.asarray(raw)
    if a.ndim == 2 and a.shape[0] == 1 and a.size == w * h * 2:
        a = a.reshape(h, w, 2)                         # YUYV bytes delivered as one row
    if a.ndim == 3 and a.shape[2] == 2:                # YUYV: [..., 0] = brightness (Y)
        if mode in ("auto", "split") and h % 2 == 0 and h >= 2 * 120:
            top, bot = a[: h // 2], a[h // 2:]
            raw16 = bot[..., 0].astype(np.uint16) | (bot[..., 1].astype(np.uint16) << 8)
            temps = raw16.astype(np.float32) / 64.0 - 273.15
            med = float(np.median(temps))
            if mode == "split" or -20.0 < med < 60.0:  # plausible room temperatures -> real split frame
                return top[..., 0].copy(), temps, "split"
        return a[..., 0].copy(), None, "gray"
    if a.ndim == 2 and a.dtype == np.uint16:           # Y16: raw counts
        temps = a.astype(np.float32) / 64.0 - 273.15
        if -20.0 < float(np.median(temps)) < 60.0:
            g = cv2.normalize(temps, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            return g, temps, "split"
        g = cv2.normalize(a, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        return g, None, "gray"
    if a.ndim == 3 and a.shape[2] == 3:                # BGR picture
        return cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), None, "gray"
    if a.ndim == 2:
        return a.astype(np.uint8), None, "gray"
    raise ValueError(f"unknown frame layout {a.shape} {a.dtype}")


def orient(img, cfg):
    import cv2
    rot = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
    if img is None:
        return None
    if cfg["rotate"] in rot:
        img = cv2.rotate(img, rot[cfg["rotate"]])
    if cfg["flip_h"]:
        img = img[:, ::-1]
    if cfg["flip_v"]:
        img = img[::-1, :]
    return np.ascontiguousarray(img)


def hotspots(gray, temps, cfg, pan):
    """Up to max_hotspots boxes, hottest first."""
    import cv2
    H, W = gray.shape
    if temps is not None:
        thr = max(cfg["body_min_c"], float(temps.max()) - cfg["rel_c"])
        mask = (temps >= thr).astype(np.uint8)
    else:
        thr = max(float(np.percentile(gray, cfg["gray_pct"])), float(gray.mean() + 2 * gray.std()))
        mask = (gray >= thr).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out = []
    for k in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[k])
        if area < cfg["min_area"] * W * H:
            continue
        region = labels == k
        t = float(temps[region].max()) if temps is not None else None
        cx = (x + w / 2) / W
        out.append(({"x": round(x / W, 3), "y": round(y / H, 3), "w": round(w / W, 3), "h": round(h / H, 3),
                     "temp_c": None if t is None else round(t, 1),
                     "deg": round(pan + (cx - 0.5) * cfg["hfov_deg"], 1)},
                    t if t is not None else float(gray[region].max())))
    out.sort(key=lambda d: -d[1])
    return [d for d, _ in out[: cfg["max_hotspots"]]]


def colorize(gray, temps):
    import cv2
    if temps is not None:   # fixed 18..38 C scale so colors mean the same thing every frame
        g = np.clip((temps - 18.0) / 20.0 * 255.0, 0, 255).astype(np.uint8)
    else:
        g = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return cv2.applyColorMap(g, cv2.COLORMAP_INFERNO)


_shared = {"pan": 0.0, "subscribed": False, "thread": None}
_stop = threading.Event()


@atexit.register
def _release_camera():
    """The Ear is stopping: let run() leave cap.read() and release the camera before Python exits.
    A daemon thread killed inside OpenCV aborts the process ("FATAL: exception not rethrown", SIGABRT)."""
    _stop.set()
    t = _shared["thread"]
    if t is not None and t is not threading.current_thread():
        t.join(timeout=1.5)


def _on_pantilt(ev):
    if ev.get("pan") is not None:
        _shared["pan"] = float(ev["pan"])


def run(bus, cfg: dict) -> None:
    import cv2
    cfg = {**DEFAULTS, **(cfg or {})}
    cap, idx, raw = open_camera(cfg["device"])
    if cap is None:
        # raise, not return: the supervisor then looks again in 3 s (after a power cut the camera may not be ready yet)
        raise RuntimeError("no thermal camera delivered a frame (unplugged, or not ready yet)")
    if not _shared["subscribed"]:
        bus.subscribe("pantilt", _on_pantilt)
        _shared["subscribed"] = True
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    mode_logged, last_jpg, last_det, fails = None, 0.0, 0.0, 0
    _shared["thread"] = threading.current_thread()
    try:
        while not _stop.is_set():
            ok, raw = cap.read()
            if not ok or raw is None:
                fails += 1
                if fails > 50:
                    raise RuntimeError("thermal camera stopped sending frames")
                time.sleep(0.02)
                continue
            fails = 0
            gray, temps, mode = decode(raw, w, h, cfg["mode"])
            if mode != mode_logged:
                log.info("mode %s (%s)", mode, "temperatures in C" if temps is not None else "brightness only")
                mode_logged = mode
            gray, temps = orient(gray, cfg), orient(temps, cfg)
            now = time.time()
            if now - last_jpg >= 1.0 / cfg["fps"]:
                ok, jpg = cv2.imencode(".jpg", colorize(gray, temps), [cv2.IMWRITE_JPEG_QUALITY, cfg["jpeg_quality"]])
                if ok:
                    bus.set_frame(jpg.tobytes())
                last_jpg = now
            if now - last_det >= 1.0 / cfg["det_hz"]:
                pan = _shared["pan"]
                bus.publish({"t": "thermal_det", "pan_deg": round(pan, 1),
                             "max_c": None if temps is None else round(float(temps.max()), 1),
                             "hotspots": hotspots(gray, temps, cfg, pan)})
                last_det = now
    finally:
        cap.release()


if __name__ == "__main__":
    from ear.bus import PrintBus
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname).1s %(name)s: %(message)s")
    bus = PrintBus()

    def saver():
        while True:
            time.sleep(5.0)
            f = bus.get_frame()
            if f:
                with open("thermal_test.jpg", "wb") as fh:
                    fh.write(f)
    threading.Thread(target=saver, daemon=True).start()
    try:
        run(bus, {})
    except KeyboardInterrupt:
        pass
