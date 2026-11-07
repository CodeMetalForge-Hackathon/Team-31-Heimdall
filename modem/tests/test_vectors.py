"""Python modem tests:  python -m pytest modem/tests"""
import numpy as np
import pytest

from modem import heimdall_ac1 as ac1
from modem.selftest import make_stream, random_fields, run_stream, score

V1 = dict(id="1A2B", floor=2, minutes=14, motion=True, status="injured", people=2, battery=3, hops=0, knock=False)
V2 = dict(id="77C1", floor=None, minutes=61, motion=False, status="critical", people=1, battery=1, hops=1, knock=True)


def test_crc_check_value():
    assert ac1.crc8(b"123456789") == 0xF4


def test_vector_1():
    b = ac1.pack(V1)
    assert b.hex().upper() == "1A2B20F96066"
    assert "".join(map(str, ac1.to_bits(b))) == "000110100010101100100000111110010110000001100110"
    assert ac1.unpack(b) == V1


def test_vector_2():
    b = ac1.pack(V2)
    assert b.hex().upper() == "77C103CCACEA"
    assert ac1.unpack(b) == dict(V2, minutes=60)      # 61 min -> min2 30 -> 60


def test_bad_crc_rejected():
    b = bytearray(ac1.pack(V1))
    for i in range(48):
        c = bytearray(b)
        c[i // 8] ^= 0x80 >> (i % 8)
        assert ac1.unpack(c) is None
    assert ac1.unpack(b[:5]) is None


def test_roundtrip_1000_random():
    rng = np.random.default_rng(42)
    for _ in range(1000):
        f = random_fields(rng)
        b = ac1.pack(f)
        assert len(b) == 6
        assert ac1.unpack(b) == f
        assert ac1.from_bits(ac1.to_bits(b)) == b


def test_pack_rejects_out_of_range():
    with pytest.raises(ValueError):
        ac1.pack(dict(V1, floor=30))
    with pytest.raises(ValueError):
        ac1.pack(dict(V1, id="12345"))
    assert ac1.unpack(ac1.pack(dict(V1, minutes=500)))["minutes"] == 126   # capped
    assert ac1.unpack(ac1.pack(dict(V1, people=12)))["people"] == 7        # 7 = 7+


@pytest.mark.parametrize("fs", [16000, 44100, 48000])
def test_synth_shape(fs):
    x = ac1.synth(ac1.pack(V1), 1, fs)
    assert x.dtype == np.float32
    assert len(x) == int(np.ceil(ac1.FRAME_S * fs - 1e-9))
    assert 0.79 < np.max(np.abs(x)) <= 0.8 + 1e-6
    assert x[0] == 0 and x[round(0.2 * fs)] == 0


@pytest.mark.parametrize("fs", [16000, 44100, 48000])
def test_decode_clean_all_bands(fs):
    rng = np.random.default_rng(fs)
    frames = [ac1.pack(random_fields(rng)) for _ in range(4)]
    for band, raw in enumerate(frames):
        x = np.concatenate([np.zeros(fs), ac1.synth(raw, band, fs), np.zeros(fs // 2)])
        found, _ = run_stream(x, fs=fs, chunk=3000, rng=rng)
        assert [f.raw for f in found] == [raw]
        f = found[0]
        assert f.band == band
        assert abs(f.t_end_preamble - 1.2) < 1e-3
        assert abs(f.sample_index - round(1.2 * fs)) <= 2


def test_chunking_does_not_change_result():
    rng = np.random.default_rng(3)
    frames = [ac1.pack(random_fields(rng)) for _ in range(6)]
    x, truth = make_stream(rng, frames, [0, 1, 2, 3, 1, 2], snr_db=5, drr_db=0)
    a, _ = run_stream(x, chunk=160)
    b, _ = run_stream(x, chunk=50000)
    c, _ = run_stream(x, rng=np.random.default_rng(1))
    key = lambda fr: [(f.raw, f.band, round(f.t_end_preamble, 4)) for f in fr]
    assert key(a) == key(b) == key(c)
    assert score(a, truth) == (6, 0)


def test_noise_only_no_frames():
    rng = np.random.default_rng(5)
    found, _ = run_stream(0.1 * rng.standard_normal(16000 * 30))
    assert found == []
    found, _ = run_stream(np.zeros(48000 * 10), fs=48000)
    assert found == []


def test_preamble_segment():
    fs = 48000
    x = np.concatenate([np.zeros(fs), ac1.synth(ac1.pack(V1), 2, fs), np.zeros(fs)])
    found, _ = run_stream(x, fs=fs)
    s, e = ac1.preamble_segment(x, found[0], fs)
    assert abs(s - fs) <= 2 and e - s == round(0.2 * fs)
    tpl = ac1.preamble_template(2, fs)
    assert len(tpl) == e - s
    seg = x[s:e]
    assert np.dot(seg, tpl) / (np.linalg.norm(seg) * np.linalg.norm(tpl)) > 0.99
