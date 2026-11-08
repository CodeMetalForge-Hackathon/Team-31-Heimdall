"""Mock data: realistic fake events for every type in docs/SPEC.md section 3, plus fake thermal video.

Lets the phone UI be built before the sensors exist. When a real module is also enabled
(e.g. HEIMDALL_MODULES=mock,thermal) the mock stops faking what that module produces.
"""
import logging
import math
import queue
import random
import time

import cv2
import numpy as np

log = logging.getLogger("mock")

# Real module -> what the mock stops faking when that module is enabled.
REPLACED_BY = {
    "audio": {"victim", "bearing", "sound", "noise"},
    "thermal": {"frame", "thermal_det"},
    "pantilt": {"pantilt", "knock"},
    "knock": {"knock"},
    "radar": {"radar"},
    "lora": {"lora"},
}

W, H = 256, 192
THERMAL_HFOV = 56.0       # degrees across the 256-px width (close enough for a fake)
PAN_SLEW_DEG_S = 40.0
VICTIM_PERIOD_S = 8.0

STATUS_NAMES = ["no_response", "ok", "injured", "critical"]

_commands = queue.Queue()
_subscribed = set()


def _on_command(event):
    log.info("received %s: %s", event["t"], {k: v for k, v in event.items() if k not in ("t", "ts")})
    _commands.put(event)


def _skip_types():
    try:
        from ear.config import CONFIG
        enabled = set(CONFIG["modules"])
    except Exception:
        enabled = set()
    skip = set()
    for mod, types in REPLACED_BY.items():
        if mod in enabled:
            skip |= types
    return skip


class Victim:
    def __init__(self, vid, base_deg, floor, minutes, status, people, battery, knock, stops_after=None):
        self.id = vid
        self.base_deg = base_deg
        self.floor = floor
        self.minutes0 = minutes
        self.status = status
        self.people = people
        self.battery = battery
        self.knock = knock
        self.stops_after = stops_after
        self.k = 0  # transmission counter, for the band rule
        self.phase = random.uniform(0, 2 * math.pi)

    def deg(self, t):
        # slow drift, a few degrees per minute, as the rescuer walks
        return self.base_deg + 12.0 * math.sin(t / 45.0 + self.phase)

    def event(self, t):
        band = (self.k + int(self.id, 16)) % 4
        self.k += 1
        minutes = min(126, (int(self.minutes0 + t / 60.0) // 2) * 2)
        motion = not (self.stops_after is not None and t > self.stops_after)
        hops = 1 if (self.id == "77C1" and random.random() < 0.3) else 0
        snr = round(random.uniform(10.0, 22.0) - 4.0 * hops, 1)
        deg = round(self.deg(t) + random.gauss(0, 2.0), 1)
        return {
            "t": "victim", "id": self.id, "floor": self.floor, "minutes": minutes, "motion": motion,
            "status": self.status, "people": self.people, "battery": self.battery, "hops": hops,
            "knock": self.knock, "deg": deg, "band": band, "snr_db": snr,
        }


class Thermal:
    def __init__(self):
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.xx, self.yy = xx, yy
        self.bg = 20.0 + 1.5 * (yy / H) + np.random.normal(0, 0.4, (H, W)).astype(np.float32)

    def blob(self, t):
        x = 0.5 + 0.3 * math.sin(t / 6.0)
        y = 0.55 + 0.08 * math.sin(t / 3.7)
        return x, y, 0.12, 0.30

    def frame(self, t):
        x, y, w, h = self.blob(t)
        cx, cy, sx, sy = x * W, y * H, w * W / 2.5, h * H / 2.5
        temp = self.bg + np.random.normal(0, 0.3, (H, W)).astype(np.float32)
        temp += 14.0 * np.exp(-(((self.xx - cx) / sx) ** 2 + ((self.yy - cy) / sy) ** 2))
        img = np.clip((temp - 18.0) / (36.0 - 18.0) * 255.0, 0, 255).astype(np.uint8)
        img = cv2.applyColorMap(img, cv2.COLORMAP_INFERNO)
        cv2.putText(img, "MOCK", (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return jpg.tobytes() if ok else None, float(temp.max())

    def detection(self, t, pan):
        x, y, w, h = self.blob(t)
        temp_c = round(33.0 + random.uniform(0.0, 1.5), 1)
        return {
            "t": "thermal_det", "pan_deg": round(pan, 1), "max_c": round(temp_c + 0.3, 1),
            "hotspots": [{"x": round(x - w / 2, 3), "y": round(y - h / 2, 3), "w": w, "h": h,
                          "temp_c": temp_c, "deg": round(pan + (x - 0.5) * THERMAL_HFOV, 1)}],
        }


class Every:
    """Fires at a period with optional ± jitter."""

    def __init__(self, period, jitter=0.0, start=0.0):
        self.period, self.jitter = period, jitter
        self.next = start

    def due(self, now):
        if now < self.next:
            return False
        self.next = now + self.period + random.uniform(-self.jitter, self.jitter)
        return True


def run(bus, cfg: dict) -> None:
    if id(bus) not in _subscribed:
        for topic in ("pantilt_cmd", "pantilt_mode", "heard"):
            bus.subscribe(topic, _on_command)
        _subscribed.add(id(bus))

    skip = _skip_types()
    if skip:
        log.info("real modules enabled, not faking: %s", ", ".join(sorted(skip)))

    def pub(event):
        if event["t"] not in skip:
            bus.publish(event)

    victims = [
        Victim("1A2B", -35.0, floor=2, minutes=14, status="injured", people=2, battery=3, knock=False),
        Victim("77C1", 40.0, floor=None, minutes=61, status="critical", people=1, battery=1, knock=True,
               stops_after=60.0),
    ]
    thermal = Thermal()

    t0 = time.monotonic()
    victim_timers = [Every(VICTIM_PERIOD_S, 1.0, start=0.5), Every(VICTIM_PERIOD_S, 1.0, start=3.0)]
    frame_t, det_t, pantilt_t = Every(0.2), Every(0.5), Every(0.5)
    radar_t, noise_t, heading_t = Every(1.0), Every(1.0), Every(0.5)
    knock_t, sound_t = Every(30.0, 5.0, start=10.0), Every(20.0, 4.0, start=6.0)
    lora_t, drone_t = Every(10.0, start=2.0), Every(5.0, start=1.0)

    pan, tilt, mode = 0.0, 0.0, "auto"
    target_pan, target_tilt = 0.0, 0.0
    noise_db = [-48.0, -51.0, -55.0, -60.0]
    yaw = 212.0
    lora_tx = 0
    drone_n = 0
    last_tick = t0

    while True:
        now = time.monotonic()
        t = now - t0
        dt = now - last_tick
        last_tick = now

        # commands from phones
        while not _commands.empty():
            cmd = _commands.get_nowait()
            if cmd["t"] == "pantilt_cmd":
                mode = "manual"
                target_pan = max(-90.0, min(90.0, float(cmd.get("pan", target_pan))))
                target_tilt = max(-30.0, min(60.0, float(cmd.get("tilt", target_tilt))))
            elif cmd["t"] == "pantilt_mode" and cmd.get("mode") in ("auto", "manual"):
                mode = cmd["mode"]

        # victims + tag bearings
        for v, timer in zip(victims, victim_timers):
            if timer.due(t):
                ev = v.event(t)
                pub(ev)
                pub({"t": "bearing", "deg": ev["deg"], "conf": round(random.uniform(0.6, 0.92), 2),
                     "band": ev["band"], "snr_db": ev["snr_db"], "src": "tag", "id": v.id})
                if mode == "auto":
                    target_pan = max(-90.0, min(90.0, ev["deg"]))
                    target_tilt = 5.0

        # human sound (classifier) + its bearing, roughly where 77C1 is
        if sound_t.due(t):
            deg = round(victims[1].deg(t) + random.gauss(0, 5.0), 1)
            pub({"t": "sound", "label": random.choice(["Speech", "Shout", "Speech", "Groan"]),
                 "score": round(random.uniform(0.5, 0.9), 2), "deg": deg})
            pub({"t": "bearing", "deg": deg, "conf": round(random.uniform(0.4, 0.7), 2), "band": None,
                 "snr_db": round(random.uniform(6.0, 14.0), 1), "src": "sound", "id": None})

        # pan-tilt slews toward target
        step = PAN_SLEW_DEG_S * dt
        pan += max(-step, min(step, target_pan - pan))
        tilt += max(-step, min(step, target_tilt - tilt))
        if pantilt_t.due(t):
            pub({"t": "pantilt", "pan": round(pan, 1), "tilt": round(tilt, 1), "mode": mode})

        # thermal
        if "frame" not in skip and frame_t.due(t):
            jpg, _ = thermal.frame(t)
            if jpg:
                bus.set_frame(jpg)
        if det_t.due(t):
            pub(thermal.detection(t, pan))

        if radar_t.due(t):
            presence = random.random() < 0.85
            pub({"t": "radar", "presence": presence,
                 "breath_bpm": round(random.gauss(14.0, 0.8), 1) if presence else None,
                 "heart_bpm": (round(random.gauss(78.0, 3.0), 1) if presence and random.random() < 0.5 else None),
                 "dist_m": round(random.gauss(1.1, 0.05), 2) if presence else None, "src": "mock"})

        if noise_t.due(t):
            noise_db = [max(-75.0, min(-35.0, d + random.gauss(0, 0.8))) for d in noise_db]
            pub({"t": "noise", "band_db": [round(d, 1) for d in noise_db], "quiet": max(noise_db) < -50.0})

        if heading_t.due(t):
            yaw = (yaw + random.gauss(0, 1.5)) % 360.0
            pub({"t": "heading", "yaw_deg": round(yaw, 1)})

        if knock_t.due(t):
            pub({"t": "knock", "source": "sw420", "count": random.randint(1, 4), "level_db": None})

        if lora_t.due(t):
            lora_tx += 1
            pub({"t": "lora", "tx": lora_tx, "last_ok": random.random() < 0.9})

        if drone_t.due(t):
            pub({"t": "drone", "link": "ok", "note": "scouting" if (drone_n // 3) % 2 == 0 else "perched"})
            drone_n += 1

        time.sleep(0.05)


if __name__ == "__main__":
    from ear.bus import PrintBus
    logging.basicConfig(level=logging.INFO)
    run(PrintBus(), {})
