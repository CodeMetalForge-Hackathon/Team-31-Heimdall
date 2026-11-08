"""Pan-tilt head + knock sensor: the Seeeduino on USB serial (docs/SPEC.md section 4).

- auto mode: aims the thermal camera at the most urgent confirmed victim
  (critical > injured > no_response > ok; then "just stopped moving" (last 5 min) > still > moving;
  then longest since SOS),
  or else at the newest confident bearing.
- manual mode: follows pantilt_cmd from the operator page; pantilt_mode "auto" switches back.
- publishes `pantilt` after every move and every 2 s, and `knock` for every KNOCK line
  (the SW-420 sits on the same board, and a serial port can only be opened once).
- the head starts straight ahead and goes back there when the Ear stops, so a new run never
  starts from wherever the last one left it.

Standalone test (no audio needed):
  python -m ear.modules.pantilt          print what the board says, aim at nothing
  python -m ear.modules.pantilt --demo   fake bearings -45, 0, +45 every 3 s: the head should follow
"""
import atexit
import glob
import logging
import threading
import time

log = logging.getLogger("pantilt")

DEFAULTS = {
    "port": "auto",       # e.g. "/dev/ttyUSB0"; "auto" = the first port whose board says HELLO or PONG
    "baud": 115200,
    "tilt": 0,            # tilt used in auto mode (degrees, + = up)
    "min_conf": 0.3,      # ignore bearings less confident than this
    "min_move_deg": 4,    # auto mode: don't re-aim for a smaller change (less servo noise near the mics)
    "hold_s": 1.5,        # auto mode: at least this long between moves
    "fresh_s": 30.0,      # victims / bearings older than this are not aimed at
    "status_s": 2.0,      # publish a pantilt event at least this often
    "pan_dir": 1,         # -1 if a positive servo pan turns the camera LEFT (servo mounted the other way round)
    "pan_offset_deg": 0.0,  # bearing the camera looks at with the pan servo centred (its zero vs the mic front arrow)
}
PAN_MIN, PAN_MAX = -90, 90
TILT_MIN, TILT_MAX = -30, 25
RANK = {"critical": 0, "injured": 1, "no_response": 2, "ok": 3}
HOME = (0, 0)   # straight ahead and level, where the board puts the head on power-up
STOP_WINDOW_S = 300   # someone who stopped moving in the last 5 min outranks everyone else of the same status


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def servo_pan(cfg, pan):
    """The pan to send to the board so the camera looks at `pan` (bearing degrees, + = right of the front arrow).
    The camera's zero is pan_offset_deg off the mic array's front arrow, and pan_dir is -1 when the servo is
    mounted so that a positive pan turns it left. Everything else (events, the dial, thermal boxes) stays in bearing degrees."""
    return clamp(int(round(cfg["pan_dir"] * (pan - cfg["pan_offset_deg"]))), PAN_MIN, PAN_MAX)


class Aimer:
    """Decides where the head should point. Pure logic (no serial), so it can be unit-tested."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.mode = "auto"
        self.manual = (0.0, 0.0)
        self.current = HOME        # where the head was last sent (bearing degrees), kept up to date by run()
        self.victims = {}          # id -> latest fields + "deg", "deg_ts"
        self.last_bearing = None   # (deg, ts) of the newest confident bearing

    def on_victim(self, ev):
        vid = ev.get("id")
        if not vid:
            return
        ts = ev.get("ts") or time.time()
        with self.lock:
            v = self.victims.setdefault(vid, {})
            moving = bool(ev.get("motion"))
            if moving:
                v["stopped_ts"] = None
            elif v.get("motion"):        # was moving, now still: this person just stopped moving
                v["stopped_ts"] = ts
            v.update(status=ev.get("status"), motion=moving,
                     confirmed=ev.get("confirmed", True), minutes=ev.get("minutes") or 0, ts=ts)
            if ev.get("deg") is not None:
                v["deg"], v["deg_ts"] = float(ev["deg"]), ts

    def on_bearing(self, ev):
        if ev.get("deg") is None:
            return
        ts = ev.get("ts") or time.time()
        with self.lock:
            if (ev.get("conf") or 0) >= self.cfg["min_conf"]:
                self.last_bearing = (float(ev["deg"]), ts)
            vid = ev.get("id")
            if vid and vid in self.victims:
                self.victims[vid]["deg"], self.victims[vid]["deg_ts"] = float(ev["deg"]), ts

    def on_cmd(self, ev):
        with self.lock:
            self.mode = "manual"
            self.manual = (clamp(float(ev.get("pan") or 0), PAN_MIN, PAN_MAX),
                           clamp(float(ev.get("tilt") or 0), TILT_MIN, TILT_MAX))

    def on_mode(self, ev):
        if ev.get("mode") in ("auto", "manual"):
            with self.lock:
                if ev["mode"] == "manual" and self.mode != "manual":
                    self.manual = self.current   # take over where the head is, not where a manual command left it earlier
                self.mode = ev["mode"]

    def target(self, now):
        """(pan, tilt, why) the head should point at now, or None = stay where it is."""
        with self.lock:
            if self.mode == "manual":
                return self.manual[0], self.manual[1], "manual"
            fresh = self.cfg["fresh_s"]
            cands = [(vid, v) for vid, v in self.victims.items()
                     if v.get("confirmed", True) and v.get("deg") is not None
                     and now - v.get("deg_ts", 0) <= fresh]
            if cands:
                vid, v = min(cands, key=lambda kv: (RANK.get(kv[1].get("status"), 4),
                                                    motion_rank(kv[1], now),
                                                    -(kv[1].get("minutes") or 0)))
                return clamp(v["deg"], PAN_MIN, PAN_MAX), self.cfg["tilt"], "victim " + vid
            if self.last_bearing and now - self.last_bearing[1] <= fresh:
                return clamp(self.last_bearing[0], PAN_MIN, PAN_MAX), self.cfg["tilt"], "bearing"
            return None


def motion_rank(v, now):
    """0 = just stopped moving (most urgent), 1 = still, 2 = moving (responsive)."""
    if v.get("motion", True):
        return 2
    st = v.get("stopped_ts")
    return 0 if st is not None and now - st < STOP_WINDOW_S else 1


def candidate_ports():
    return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
                  + glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.usbmodem*"))


def open_board(port, baud):
    """An open serial.Serial talking to the Heimdall servo board, or None."""
    import serial  # pyserial
    for p in (candidate_ports() if port == "auto" else [port]):
        try:
            s = serial.Serial(p, baud, timeout=0.2)
        except (OSError, serial.SerialException) as e:
            log.info("skip %s: %s", p, e)
            continue
        t0, pinged = time.time(), False
        while time.time() - t0 < 5.0:
            line = s.readline().decode(errors="replace").strip()
            if line.startswith("HELLO HEIMDALL-SERVO") or line == "PONG":
                log.info("servo board on %s (%s)", p, line)
                return s
            if not pinged and time.time() - t0 > 2.5:   # opening the port resets the board: let it boot
                s.write(b"PING\n")
                pinged = True
        s.close()
        log.info("no servo board on %s", p)
    return None


_shared = {"aimer": None, "park": None}   # one Aimer + one set of subscriptions, even if run() is restarted


@atexit.register
def _park_at_exit():
    """The Ear is stopping (Ctrl-C, systemctl stop, restart_ear.sh): point the head straight ahead."""
    if _shared["park"]:
        _shared["park"]()


def run(bus, cfg: dict) -> None:
    cfg = {**DEFAULTS, **(cfg or {})}
    s = open_board(cfg["port"], cfg["baud"])
    if s is None:
        log.warning("no servo board found (Seeeduino unplugged?): pantilt off")
        return
    aimer = _shared["aimer"]
    if aimer is None:
        aimer = _shared["aimer"] = Aimer(cfg)
        bus.subscribe("victim", aimer.on_victim)
        bus.subscribe("bearing", aimer.on_bearing)
        bus.subscribe("pantilt_cmd", aimer.on_cmd)
        bus.subscribe("pantilt_mode", aimer.on_mode)

    state = {"error": None, "reset": False, "parked": False}
    write_lock = threading.Lock()

    def send(cmd):
        with write_lock:
            if not state["parked"]:        # once parked, nothing may move the head again
                s.write((cmd + "\n").encode())

    def park():
        with write_lock:
            if state["parked"]:
                return
            state["parked"] = True
            try:
                s.write(("P %d %d\n" % (servo_pan(cfg, HOME[0]), HOME[1])).encode())
                s.flush()                  # the board finishes the move after we're gone
                log.info("parked: head straight (pan %d tilt %d)", *HOME)
            except Exception:              # board already gone: nothing to park
                pass

    _shared["park"] = park

    def reader():
        try:
            while state["error"] is None:
                line = s.readline().decode(errors="replace").strip()
                if not line:
                    continue
                if line.startswith("KNOCK"):
                    parts = line.split()
                    count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
                    bus.publish({"t": "knock", "source": "sw420", "count": count, "level_db": None})
                    log.info("knock x%d", count)
                elif line.startswith("HELLO"):
                    state["reset"] = True        # the board rebooted: send the target again
                    log.warning("servo board rebooted")
                elif line.startswith("ERR"):
                    log.warning("board: %s", line)
        except Exception as e:  # unplugged, I/O error
            state["error"] = e

    threading.Thread(target=reader, daemon=True, name="pantilt-reader").start()

    send("P %d %d" % (servo_pan(cfg, HOME[0]), HOME[1]))   # start straight, not where the last run left the head
    log.info("start: head straight (pan %d tilt %d; servo %d: pan_dir %d, offset %+.0f)", *HOME,
             servo_pan(cfg, HOME[0]), cfg["pan_dir"], cfg["pan_offset_deg"])
    last_sent, last_move, last_status = HOME, time.time(), 0.0
    try:
        while True:
            if state["error"] is not None:
                raise RuntimeError(f"servo board lost: {state['error']}")
            if state["reset"]:
                state["reset"], last_sent = False, None
            now = time.time()
            tgt = aimer.target(now)
            if tgt is not None:
                pan, tilt, why = int(round(tgt[0])), int(round(tgt[1])), tgt[2]
                if why == "manual":
                    move = last_sent != (pan, tilt)
                else:
                    move = (last_sent is None
                            or abs(pan - last_sent[0]) >= cfg["min_move_deg"]
                            or abs(tilt - last_sent[1]) >= 2) and now - last_move >= cfg["hold_s"]
                if move:
                    sp = servo_pan(cfg, pan)
                    send(f"P {sp} {tilt}")
                    last_sent, last_move = (pan, tilt), now
                    aimer.current = (pan, tilt)
                    log.info("aim pan %d tilt %d (%s) -> servo %d", pan, tilt, why, sp)
                    last_status = 0.0   # publish right away
            if now - last_status >= cfg["status_s"]:
                pan, tilt = last_sent or (0, 0)
                bus.publish({"t": "pantilt", "pan": float(pan), "tilt": float(tilt), "mode": aimer.mode})
                last_status = now
            time.sleep(0.05)
    finally:
        park()
        state["error"] = state["error"] or "stopped"
        s.close()


if __name__ == "__main__":
    import sys
    from ear.bus import PrintBus
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname).1s %(name)s: %(message)s")
    bus = PrintBus()
    if "--demo" in sys.argv:
        def fake_bearings():
            while True:
                for deg in (-45.0, 0.0, 45.0):
                    time.sleep(3.0)
                    bus.publish({"t": "bearing", "deg": deg, "conf": 0.9, "band": 1, "snr_db": 20.0,
                                 "src": "tag", "id": None})
        threading.Thread(target=fake_bearings, daemon=True).start()
    try:
        run(bus, {})
    except KeyboardInterrupt:
        pass
