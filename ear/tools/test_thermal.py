"""python -m pytest ear/tools/test_thermal.py : the thermal module on fake frames (no camera)."""
import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from ear.modules import thermal as T  # noqa: E402


def test_station_camera_640x512_yuyv_gives_gray_mode_and_a_box_on_the_warm_spot():
    W, H = 640, 512
    f = np.zeros((H, W, 2), np.uint8)
    f[..., 0], f[..., 1] = 60, 128            # room: Y = 60, U/V = 128
    f[200:330, 400:460, 0] = 230               # a warm person right of center
    gray, temps, mode = T.decode(f, W, H)
    assert mode == "gray" and temps is None and gray.shape == (H, W)
    spots = T.hotspots(gray, temps, dict(T.DEFAULTS), pan=0.0)
    assert len(spots) == 1
    s = spots[0]
    assert abs(s["x"] - 400 / W) < 0.01 and s["deg"] > 0 and s["temp_c"] is None
    ok, jpg = cv2.imencode(".jpg", T.colorize(gray, temps))
    assert ok and len(jpg) > 1000


def test_split_frame_gives_temperatures():
    W, H = 256, 192
    temps = np.full((H, W), 22.0, np.float32)
    temps[60:120, 154:180] = 34.0
    raw16 = np.round((temps + 273.15) * 64).astype(np.uint16)
    bot = np.stack([(raw16 & 0xFF).astype(np.uint8), (raw16 >> 8).astype(np.uint8)], axis=-1)
    top = np.zeros((H, W, 2), np.uint8)
    gray, t, mode = T.decode(np.concatenate([top, bot], axis=0), W, 2 * H)
    assert mode == "split" and abs(float(t.max()) - 34.0) < 0.1
    assert T.hotspots(gray, t, dict(T.DEFAULTS), pan=0.0)[0]["temp_c"] == 34.0
