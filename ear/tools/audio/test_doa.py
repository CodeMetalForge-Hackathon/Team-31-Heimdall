"""pytest ear/tools/audio/test_doa.py: GCC-PHAT bearing on synthetic far-field chirps, on the configured geometry."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ear.config import CONFIG  # noqa: E402
from ear.modules.audio import estimate_bearing, mic_array  # noqa: E402
from modem.heimdall_ac1 import PREAMBLE_S, pack, synth  # noqa: E402

FS = 16000
C = CONFIG["audio"]["speed_of_sound"]
CHANS, XY = mic_array(CONFIG["audio"]["mic_xy"])
FIELDS = dict(id=0x1A2B, floor=2, minutes=14, motion=1, status=2, people=2, battery=3, hops=0, knock=0)


def arrive(sig, theta_deg, xy, snr_db=20.0, seed=0):
    """Far-field plane wave from theta: mic i hears sig delayed by t_i = -(p_i . u) / c, plus white noise."""
    th = np.radians(theta_deg)
    u = np.array([np.cos(th), np.sin(th)])
    t = -(xy @ u) / C
    n = len(sig) + 256
    S = np.fft.rfft(sig, n)
    f = np.fft.rfftfreq(n, 1.0 / FS)
    x = np.stack([np.fft.irfft(S * np.exp(-2j * np.pi * f * (ti + 0.004)), n) for ti in t], axis=1)
    rng = np.random.default_rng(seed)
    x += rng.normal(0, np.std(x) * 10 ** (-snr_db / 20), x.shape)
    return x


def ang_err(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


@pytest.mark.parametrize("band", [0, 1, 2, 3])
@pytest.mark.parametrize("theta", [0.0, 45.0, 90.0, 180.0, -90.0, -135.0, 17.0])
def test_preamble_bearing(theta, band):
    sig = synth(pack(FIELDS), band, FS)[: int(PREAMBLE_S * FS)]
    deg, conf = estimate_bearing(arrive(sig, theta, XY), band, FS, XY, C)
    assert ang_err(deg, theta) <= 3.0, (deg, conf)
    assert conf > 0.3


@pytest.mark.parametrize("theta", [0.0, 90.0, -90.0])
def test_whole_frame_bearing(theta):
    sig = synth(pack(FIELDS), 1, FS)
    deg, _ = estimate_bearing(arrive(sig, theta, XY, snr_db=5.0), 1, FS, XY, C)
    assert ang_err(deg, theta) <= 3.0


def test_right_is_positive():
    """SPEC 2: a source on the right (+y) reads +90, not -90."""
    sig = synth(pack(FIELDS), 1, FS)[: int(PREAMBLE_S * FS)]
    deg, _ = estimate_bearing(arrive(sig, 90.0, XY), 1, FS, XY, C)
    assert 80.0 < deg < 100.0


def test_offset_wraps():
    sig = synth(pack(FIELDS), 1, FS)[: int(PREAMBLE_S * FS)]
    deg, _ = estimate_bearing(arrive(sig, 170.0, XY), 1, FS, XY, C, offset_deg=20.0)
    assert ang_err(deg, -170.0) <= 3.0 and -180.0 <= deg <= 180.0
