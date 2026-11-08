"""Tracker rules (SPEC 1.7.6 confirmation, hops-0 preference, v1.2 heard-report merge). pytest -q ear/tools/audio/test_tracker.py"""
from ear.modules.audio import Tracker


class ListBus:
    def __init__(self):
        self.events = []

    def publish(self, ev):
        self.events.append(ev)

    def drop_victim(self, vid):
        self.events.append({"t": "drop", "id": vid})


def fields(vid, hops=0, motion=True, status="injured", minutes=10):
    return {"id": vid, "floor": None, "minutes": minutes, "motion": motion, "status": status, "people": 1,
            "battery": 3, "hops": hops, "knock": False}


def make():
    bus = ListBus()
    return Tracker(bus, {"confirm_s": 60.0, "direct_hold_s": 30.0, "report_hold_s": 90.0}), bus


def test_confirmation_needs_a_second_frame():
    t, _ = make()
    assert t.frame(fields("1A2B"), -35.0, 1, 20.0, 0.0)["confirmed"] is False
    assert t.frame(fields("1A2B"), -34.0, 2, 20.0, 8.0)["confirmed"] is True


def test_relayed_copy_of_a_fresh_original_keeps_the_direct_record():
    t, _ = make()
    t.frame(fields("1A2B"), -35.0, 1, 20.0, 0.0)
    ev = t.frame(fields("1A2B", hops=1), 30.0, 3, 15.0, 5.0)            # phone C's relay of A
    assert ev["hops"] == 0 and ev["deg"] == -35.0


def test_phone_report_refreshes_fields_but_keeps_our_direction_and_hops():
    t, _ = make()
    t.frame(fields("A001", hops=1, motion=True), 30.0, 2, 14.0, 0.0)    # station hears only the relay (ignore list)
    t.frame(fields("A001", hops=1, motion=True), 31.0, 0, 14.0, 30.0)
    ev = t.frame(fields("A001", hops=0, motion=False, minutes=12), None, 1, 25.0, 60.0, station=False)
    assert ev["hops"] == 1 and ev["deg"] == 31.0 and ev["band"] == 0     # still "via 1 relay", direction kept
    assert ev["motion"] is False and ev["minutes"] == 12                 # the new state got through
    assert ev["confirmed"] is True


def test_phone_report_stands_alone_after_90_s_of_silence():
    t, _ = make()
    t.frame(fields("A001", hops=1), 30.0, 2, 14.0, 0.0)
    t.frame(fields("A001", hops=1), 30.0, 2, 14.0, 8.0)
    ev = t.frame(fields("A001", hops=0, motion=False), None, 1, 25.0, 100.0, station=False)
    assert ev["deg"] is None and ev["hops"] == 0


def test_phone_report_about_an_unknown_id_is_published_with_deg_null():
    t, bus = make()
    ev = t.frame(fields("77C1"), None, 2, 12.0, 0.0, station=False)
    assert ev["deg"] is None and ev["confirmed"] is False and bus.events[-1]["id"] == "77C1"


def test_frame_without_a_bearing_keeps_the_last_direction():
    """N7 doa_bands: a frame on a band we don't take bearings from carries the last measured deg (up to 90 s)."""
    t, _ = make()
    t.frame(fields("1A2B"), -35.0, 1, 20.0, 0.0)
    ev = t.frame(fields("1A2B"), None, 3, 20.0, 8.0)                    # band 3: no bearing
    assert ev["deg"] == -35.0 and ev["band"] == 3
    ev = t.frame(fields("1A2B"), None, 0, 20.0, 120.0)                  # 2 min later: too old to keep
    assert ev["deg"] is None


def test_relayed_frame_without_a_bearing_keeps_the_relay_direction():
    t, _ = make()
    t.frame(fields("A001", hops=1), 30.0, 1, 14.0, 0.0)
    ev = t.frame(fields("A001", hops=1, motion=False), None, 3, 14.0, 40.0)
    assert ev["deg"] == 30.0 and ev["hops"] == 1 and ev["motion"] is False


def test_skipped_band_never_takes_the_direction_of_a_relayed_copy():
    """Phone A heard directly (-35) and relayed by phone C (+35, C's own position). A's next direct frame on a
    skipped band must keep -35, not swing the head to C's pile."""
    t, _ = make()
    t.frame(fields("1A2B"), -35.0, 1, 20.0, 0.0)
    t.frame(fields("1A2B", hops=1), 35.0, 3, 15.0, 5.0)                # C's relay of A, inside direct_hold_s
    ev = t.frame(fields("1A2B"), None, 3, 20.0, 8.0)                    # A direct on a skipped band
    assert ev["deg"] == -35.0 and ev["hops"] == 0
