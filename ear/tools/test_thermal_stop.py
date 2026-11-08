"""The thermal module lets go of the camera when the Ear stops (no SIGABRT at exit). pytest -q ear/tools/test_thermal_stop.py"""
import threading
import time

import numpy as np
import pytest

pytest.importorskip("cv2")

from ear.modules import thermal as T  # noqa: E402


class FakeCam:
    def __init__(self):
        self.released = False

    def read(self):
        time.sleep(0.03)                       # a 30 fps camera
        f = np.full((512, 640, 2), 60, np.uint8)
        f[..., 1] = 128
        return True, f

    def get(self, prop):
        import cv2
        return {cv2.CAP_PROP_FRAME_WIDTH: 640, cv2.CAP_PROP_FRAME_HEIGHT: 512}.get(prop, 0)

    def release(self):
        self.released = True


class NullBus:
    def subscribe(self, *a):
        pass

    def publish(self, ev):
        pass

    def set_frame(self, jpg):
        pass


def test_exit_hook_stops_the_loop_and_releases_the_camera(monkeypatch):
    cam = FakeCam()
    monkeypatch.setattr(T, "open_camera", lambda device: (cam, 0, cam.read()[1]))
    T._stop.clear()
    th = threading.Thread(target=T.run, args=(NullBus(), {}), daemon=True)
    th.start()
    time.sleep(0.3)
    assert th.is_alive()
    t0 = time.time()
    T._release_camera()                        # what Python runs when the Ear stops
    assert not th.is_alive() and time.time() - t0 < 1.0
    assert cam.released
    T._stop.clear()
