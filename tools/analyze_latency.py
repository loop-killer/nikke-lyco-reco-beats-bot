"""Measure the game's audio path latency from a recorded run.

For every Space press the game plays a hit sound immediately when it judges the
press.  Finding that sound in the loopback recording gives
    L = (when the sound comes out of the speakers) - (when we pressed),
which is exactly the anchor lag we need to compensate.

Usage:
    python tools/analyze_latency.py --wav runs/audio_xxx.wav --meta runs/audio_xxx.json
                                    --sfx audio/sfx/vrshooting_down.wav
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import fftconvolve

SR = 44100


def load_mono(path: str) -> np.ndarray:
    sr, data = wavfile.read(path)
    if sr != SR:
        raise SystemExit(f"{path}: expected {SR} Hz, got {sr}")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    else:
        data = data.astype(np.float32)
    return data


def make_template(sfx: np.ndarray, seconds: float = 0.12) -> np.ndarray:
    threshold = 0.02 * np.abs(sfx).max()
    start = int(np.argmax(np.abs(sfx) > threshold))
    return sfx[start:start + int(seconds * SR)].copy()


def ncc(segment: np.ndarray, template: np.ndarray) -> np.ndarray:
    t = template - template.mean()
    tn = float(np.linalg.norm(t)) + 1e-9
    n = len(t)
    if len(segment) < n + 8:
        return np.zeros(0, dtype=np.float32)
    conv = fftconvolve(segment, t[::-1], mode="valid")
    c = np.concatenate([[0.0], np.cumsum(segment, dtype=np.float64)])
    c2 = np.concatenate([[0.0], np.cumsum(segment.astype(np.float64) ** 2)])
    mean = (c[n:] - c[:-n]) / n
    var = (c2[n:] - c2[:-n]) / n - mean * mean
    denom = np.sqrt(np.maximum(var, 1e-12) * n) * tn
    return conv / denom


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--sfx", default="", help="comma separated sfx wavs; default: hit + perfect")
    parser.add_argument("--search", type=float, default=0.45, help="seconds after the press to search")
    args = parser.parse_args()

    audio = load_mono(args.wav)
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    t0 = float(meta["t0_wall"])
    presses = [float(x) for x in meta["presses"]]
    if args.sfx:
        sfx_paths = [Path(p) for p in args.sfx.split(",")]
    else:
        sfx_paths = [Path(__file__).resolve().parent.parent / "audio" / "sfx" / n
                     for n in ("vrshooting_down.wav", "perfect.wav")]
    templates = {p.stem: make_template(load_mono(str(p))) for p in sfx_paths if p.exists()}
    print(f"audio {len(audio) / SR:.1f}s, presses {len(presses)}, templates {list(templates)}")

    results = []
    for press in presses:
        idx = int((press - t0) * SR)
        a = max(0, idx - int(0.03 * SR))
        b = min(len(audio), idx + int(args.search * SR))
        window = audio[a:b]
        best = None
        for name, template in templates.items():
            corr = ncc(window, template)
            if len(corr) == 0:
                continue
            peak = int(np.argmax(corr))
            score = float(corr[peak])
            if best is None or score > best[0]:
                best = (score, name, (a + peak - idx) / SR * 1000.0)
        if best is not None:
            results.append((best[2], best[0], best[1]))

    if not results:
        print("no presses analysed")
        return
    print(f"{'latency ms':>10} {'score':>6}  sfx")
    for latency, score, name in results:
        print(f"{latency:10.1f} {score:6.2f}  {name}")
    lats = np.array([r[0] for r in results])
    good = np.array([r[0] for r in results if r[1] >= 0.45])
    print(f"\nall:     mean {lats.mean():+.1f} ms  median {np.median(lats):+.1f}  sd {lats.std():.1f}")
    if len(good):
        print(f"score>=.45: n={len(good)}  median {np.median(good):+.1f} ms  "
              f"implied --offset-ms {-np.median(good):+.0f} (positive = press later)")


if __name__ == "__main__":
    main()
