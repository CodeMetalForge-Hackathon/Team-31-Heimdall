"""Directions from behind the station are dropped (N11). pytest -q ear/tools/audio/test_front.py"""
import types

import numpy as np

from ear.modules import audio


class ListBus:
    def __init__(self):
        self.events = []

    def publish(self, ev):
        self.events.append(ev)


def test_behind():
    assert audio.behind(156.0, 95) and audio.behind(-149.0, 95)
    assert not audio.behind(27.0, 95) and not audio.behind(-90.0, 95)
    assert not audio.behind(156.0, None) and not audio.behind(None, 95)


def test_a_reflection_from_behind_is_dropped_and_the_last_direction_kept(monkeypatch):
    raws = iter([24.0, 156.0, -149.0])
    monkeypatch.setattr(audio, "bearing_window", lambda fr, fs, window: (0, 10))
    monkeypatch.setattr(audio, "estimate_bearing", lambda *a, **k: (next(raws), 0.9))
    capture = types.SimpleNamespace(ring=types.SimpleNamespace(read=lambda a, b: np.zeros((10, 6), np.float32)))
    bus = ListBus()
    tracker = audio.Tracker(bus, {"confirm_s": 60.0, "direct_hold_s": 30.0, "report_hold_s": 90.0})
    cpu = {"feed": 0.0, "doa": 0.0}
    fields = {"id": "A001", "floor": None, "minutes": 1, "motion": False, "status": "injured", "people": 1,
              "battery": 3, "hops": 0, "knock": False}
    for t, band in ((0.0, 0), (8.0, 1), (16.0, 2)):
        fr = types.SimpleNamespace(fields=dict(fields), band=band, snr_db=20.0, quality=0.5)
        audio.handle_frame(fr, 0, capture, [0, 1, 2, 3], None, "preamble", 343.0, 0.0, set(), tracker, bus, cpu,
                           16000, True, t, front=95.0)
    bearings = [e["deg"] for e in bus.events if e["t"] == "bearing"]
    victims = [e["deg"] for e in bus.events if e["t"] == "victim"]
    assert bearings == [24.0], "no bearing event for the two reflections"
    assert victims and all(d == 24.0 for d in victims), "the victim keeps its front direction"


def test_a_sum_that_points_behind_is_dropped_too(monkeypatch):
    # 08:52 run: each frame was in front, but the sum of the last 3 curves (with older echoes) read -130 -> pan -90
    sums = iter([(40.0, 0.6, 1), (-130.0, 0.4, 3)])
    monkeypatch.setattr(audio, "bearing_window", lambda fr, fs, window: (0, 10))
    monkeypatch.setattr(audio, "estimate_bearing", lambda *a, **k: (30.0, 0.9, None))
    acc = types.SimpleNamespace(add=lambda *a, **k: next(sums))
    capture = types.SimpleNamespace(ring=types.SimpleNamespace(read=lambda a, b: np.zeros((10, 6), np.float32)))
    bus = ListBus()
    tracker = audio.Tracker(bus, {"confirm_s": 60.0, "direct_hold_s": 30.0, "report_hold_s": 90.0})
    cpu = {"feed": 0.0, "doa": 0.0}
    fields = {"id": "A001", "floor": None, "minutes": 1, "motion": False, "status": "injured", "people": 1,
              "battery": 3, "hops": 0, "knock": False}
    for t in (0.0, 8.0):
        fr = types.SimpleNamespace(fields=dict(fields), band=3, snr_db=20.0, quality=0.5)
        audio.handle_frame(fr, 0, capture, [0, 1, 2, 3], None, "preamble", 343.0, 0.0, set(), tracker, bus, cpu,
                           16000, True, t, acc=acc, front=95.0)
    assert [e["deg"] for e in bus.events if e["t"] == "bearing"] == [40.0]
    assert all(e["deg"] == 40.0 for e in bus.events if e["t"] == "victim")
