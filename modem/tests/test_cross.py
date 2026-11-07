"""Cross-language tests: JS-made WAVs decode in Python and vice versa, and both decoders
produce the same frames on a hard (noisy, reverberant) stream.  Needs `node` on PATH."""
import json
import os
import shutil
import subprocess

import numpy as np
import pytest

from modem import heimdall_ac1 as ac1
from modem.cli import read_wav, write_wav
from modem.selftest import make_stream, random_fields

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = os.path.join(ROOT, "modem", "tests", "js_tool.mjs")
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def node(*args):
    r = subprocess.run(["node", TOOL, *args], capture_output=True, text=True, check=True)
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def py_decode(path):
    x, fs = read_wav(path)
    d = ac1.Decoder(fs)
    out = []
    for i in range(0, len(x), 4096):
        out += d.feed(x[i:i + 4096])
    return out + d.flush(), d


def test_js_wavs_decode_in_python(tmp_path):
    meta = node("gen", str(tmp_path))[0]
    assert len(meta) == 4
    for m in meta:
        assert m["file"].endswith(f"js_frame_b{m['band']}.wav")
        x, fs = read_wav(m["file"])
        assert fs == 48000
        frames, _ = py_decode(m["file"])
        assert len(frames) == 1, m
        f = frames[0]
        assert f.raw.hex().upper() == m["raw"]
        assert f.band == m["band"]
        assert f.fields == ac1.unpack(bytes.fromhex(m["raw"]))
        # JS packs the same bytes Python does
        assert ac1.pack(m["fields"]).hex().upper() == m["raw"]


def test_python_wavs_decode_in_js(tmp_path):
    rng = np.random.default_rng(11)
    files, want = [], {}
    for band in range(4):
        raw = ac1.pack(random_fields(rng))
        p = str(tmp_path / f"py_frame_b{band}.wav")
        write_wav(p, np.concatenate([np.zeros(8000), ac1.synth(raw, band, 16000), np.zeros(8000)]), 16000)
        files.append(p)
        want[p] = (raw.hex().upper(), band)
    got = node("decode", *files)
    assert len(got) == 4
    for g in got:
        assert (g["raw"], g["band"]) == want[g["file"]]
        assert g == {**g, **ac1.unpack(bytes.fromhex(g["raw"]))}


def test_same_frames_on_hard_stream(tmp_path):
    """Python and JS must agree frame-for-frame (bytes, band, timing) on a stream where
    about half the frames fail: DRR -8 dB room, -3 dB SNR, 0.1% clock error, all 4 bands."""
    rng = np.random.default_rng(21)
    n = 24
    frames = [ac1.pack(random_fields(rng)) for _ in range(n)]
    x, truth = make_stream(rng, frames, [i % 4 for i in range(n)], snr_db=-3, drr_db=-8, speed=0.001)
    x *= 0.5 / np.max(np.abs(x))
    p = str(tmp_path / "hard.wav")
    write_wav(p, x, 16000)
    py, d = py_decode(p)
    js = node("decode", p)
    assert [(f.raw.hex().upper(), f.band) for f in py] == [(g["raw"], g["band"]) for g in js]
    assert all(abs(f.t_end_preamble - g["t"]) < 5e-4 for f, g in zip(py, js))
    assert 0 < len(py) < n
    # and the candidate logs (detections + outcomes) agree too
    cj = node("candidates", p)
    assert [(c["band"], c["outcome"]) for c in d.candidates] == [(c["band"], c["outcome"]) for c in cj]
