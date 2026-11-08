"""python -m pytest ear/tools/test_pantilt.py : the head on a fake servo board (a pty, no hardware).

The head starts straight ahead, aims at a victim, and goes back to straight when the Ear stops.
"""
import os
import pty
import threading
import time
import tty

import pytest

pytest.importorskip("serial")

from ear.bus import Bus  # noqa: E402
from ear.modules import pantilt  # noqa: E402


def fake_board():
    """A fake Seeeduino on a pty: says HELLO, answers PING, records every line it gets."""
    master, slave = pty.openpty()
    tty.setraw(slave)
    got = []

    def serve():
        time.sleep(0.3)
        os.write(master, b"HELLO HEIMDALL-SERVO 1\r\n")
        buf = b""
        while True:
            try:
                buf += os.read(master, 256)
            except OSError:
                return
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                got.append(line.decode().strip())
                if got[-1] == "PING":
                    os.write(master, b"PONG\r\n")

    threading.Thread(target=serve, daemon=True).start()
    return os.ttyname(slave), got


def moves(got):
    return [g for g in got if g.startswith("P ")]


def test_starts_straight_aims_then_parks_straight():
    port, got = fake_board()
    pantilt._shared.update(aimer=None, park=None)
    bus = Bus()
    threading.Thread(target=pantilt.run, args=(bus, {"port": port, "hold_s": 0.2}), daemon=True).start()
    time.sleep(1.0)
    assert moves(got) == ["P 0 0"], "a new run starts straight ahead"

    bus.publish({"t": "victim", "id": "77C1", "status": "critical", "motion": False, "minutes": 10,
                 "deg": 40.0, "confirmed": True, "ts": time.time()})
    time.sleep(0.6)
    assert moves(got)[-1] == "P 40 0", "then it aims at the victim"

    pantilt._park_at_exit()            # what Python runs when the Ear stops
    time.sleep(0.3)
    assert moves(got)[-1] == "P 0 0", "stopping points it straight again"

    n = len(moves(got))
    bus.publish({"t": "victim", "id": "77C1", "status": "critical", "motion": False, "minutes": 10,
                 "deg": -30.0, "confirmed": True, "ts": time.time()})
    time.sleep(0.6)
    assert len(moves(got)) == n, "nothing moves the head after it's parked"


def test_just_stopped_moving_beats_more_minutes():
    a = pantilt.Aimer(dict(pantilt.DEFAULTS))
    t = time.time()
    # Phone A: injured, still, 10 min since SOS. The Tag: injured, moving, only 1 min (switched on late).
    a.on_victim({"id": "1429", "status": "injured", "motion": False, "minutes": 10, "deg": -27.0, "ts": t})
    a.on_victim({"id": "A001", "status": "injured", "motion": True, "minutes": 1, "deg": 27.0, "ts": t})
    assert a.target(t)[2] == "victim 1429", "while the Tag moves, phone A comes first"

    a.on_victim({"id": "A001", "status": "injured", "motion": False, "minutes": 1, "deg": 27.0, "ts": t + 30})
    assert a.target(t + 30)[2] == "victim A001", "the Tag just stopped moving: first, whatever the minutes"

    a.on_victim({"id": "1429", "status": "injured", "motion": False, "minutes": 16, "deg": -27.0, "ts": t + 340})
    a.on_victim({"id": "A001", "status": "injured", "motion": False, "minutes": 7, "deg": 27.0, "ts": t + 340})
    assert a.target(t + 345)[2] == "victim 1429", "5 min after it stopped, it's just still: minutes decide again"


def test_servo_pan_direction_and_offset():
    # This mount: the camera looks at +30 with the servo centred, and a positive servo pan turns it LEFT.
    cfg = {**pantilt.DEFAULTS, "pan_dir": -1, "pan_offset_deg": 30.0}
    assert pantilt.servo_pan(cfg, 62) == -32 and pantilt.servo_pan(cfg, 0) == 30 and pantilt.servo_pan(cfg, -35) == 65
    assert pantilt.servo_pan(cfg, -89) == 90, "clamped to the servo's range"
    assert pantilt.servo_pan(pantilt.DEFAULTS, 62) == 62, "defaults: the board gets the bearing as it is"


def test_reversed_servo_mount_still_aims_at_the_victim():
    port, got = fake_board()
    pantilt._shared.update(aimer=None, park=None)
    bus = Bus()
    cfg = {"port": port, "hold_s": 0.2, "pan_dir": -1, "pan_offset_deg": 30.0}
    threading.Thread(target=pantilt.run, args=(bus, cfg), daemon=True).start()
    time.sleep(1.0)
    assert moves(got) == ["P 30 0"], "straight ahead is servo +30 on this mount"

    bus.publish({"t": "victim", "id": "A001", "status": "ok", "motion": False, "minutes": 3,
                 "deg": 62.0, "confirmed": True, "ts": time.time()})
    time.sleep(0.6)
    assert moves(got)[-1] == "P -32 0", "the Tag at +62 needs servo -32"
    assert bus.snapshot()["last"]["pantilt"]["pan"] == 62.0, "events stay in bearing degrees (dial, thermal boxes)"

    pantilt._park_at_exit()
    time.sleep(0.3)
    assert moves(got)[-1] == "P 30 0", "parking is straight ahead, not servo 0"


def test_switching_to_manual_keeps_the_head_where_it_is():
    a = pantilt.Aimer(dict(pantilt.DEFAULTS))
    t = time.time()
    a.on_cmd({"pan": 75, "tilt": 0})                 # an earlier manual command
    a.on_mode({"mode": "auto"})
    a.on_victim({"id": "A001", "status": "ok", "motion": False, "minutes": 3, "deg": 61.0, "ts": t})
    assert a.target(t)[:2] == (61.0, 0), "auto: on the Tag"
    a.current = (61, 0)                               # run() records every move here
    a.on_mode({"mode": "manual"})
    assert a.target(t) == (61, 0, "manual"), "Manual takes over at the current position, not at the stale 75"
    a.on_cmd({"pan": 20, "tilt": 5})
    assert a.target(t) == (20.0, 5.0, "manual"), "a new command still moves it"
