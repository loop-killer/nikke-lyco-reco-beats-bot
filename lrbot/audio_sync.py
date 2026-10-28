"""Real-time BGM position tracking via WASAPI loopback + normalized cross-correlation.

The game's timeline is driven by the BGM audio source, so "where the music is" is
the authoritative clock.  We capture what the speakers play, correlate it with the
reference track extracted from the game files, and lock onto the playback position.

Design note: this is an *anchor*, not a servo.  Once locked we keep the
(wall_time, bgm_position) pair and let the caller extrapolate with perf_counter;
continuous re-locking would add jitter for no benefit over a 70-second song.
The tracker keeps watching the signal only to report whether the BGM is still
playing (so the runner can abort when the level ends).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np
import soundcard as sc
from scipy.io import wavfile
from scipy.signal import fftconvolve

SR_CAPTURE = 44100
DECIMATE = 4
SR_REF = SR_CAPTURE // DECIMATE  # 11025
WINDOW_SECONDS = 0.6
BUFFER_SECONDS = 6.0
LOCK_SCORE = 0.50
SIGNAL_SCORE = 0.15


def list_loopback_devices() -> list[str]:
    return [m.name for m in sc.all_microphones(include_loopback=True) if m.isloopback]


def pick_loopback(device: str | None = None):
    mics = [m for m in sc.all_microphones(include_loopback=True) if m.isloopback]
    if not mics:
        raise RuntimeError("no WASAPI loopback device found")
    if device:
        matches = [m for m in mics if device.lower() in m.name.lower()]
        if not matches:
            raise RuntimeError(f"no loopback device matching {device!r}; available: {[m.name for m in mics]}")
        return matches[0]
    speaker = sc.default_speaker()
    for mic in mics:
        if mic.name == speaker.name:
            return mic
    return mics[0]


def load_reference(wav_path: str) -> np.ndarray:
    sr, data = wavfile.read(wav_path)
    if sr != SR_CAPTURE:
        raise ValueError(f"reference must be {SR_CAPTURE} Hz, got {sr}")
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = data.astype(np.float32) / 32768.0
    n = (len(data) // DECIMATE) * DECIMATE
    ref = data[:n].reshape(-1, DECIMATE).mean(axis=1)
    return ref - ref.mean()


def _downsample(x: np.ndarray) -> np.ndarray:
    n = (len(x) // DECIMATE) * DECIMATE
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    return x[:n].reshape(-1, DECIMATE).mean(axis=1)


@dataclass(frozen=True)
class Anchor:
    position: float
    wall: float
    score: float

    def position_at(self, wall: float) -> float:
        return self.position + (wall - self.wall)


class BgmTracker:
    def __init__(self, wav_path: str, device: str | None = None, log=print):
        self.ref = load_reference(wav_path)
        self.device = pick_loopback(device)
        self.log = log

        self._buf = np.zeros(int(SR_CAPTURE * BUFFER_SECONDS), dtype=np.float32)
        self._buf_n = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._anchor: Anchor | None = None
        self._verified = False
        self._signal_time = 0.0
        self._first_sound_wall = 0.0
        self._armed_wall = 0.0
        self._sound_seen = False
        self._score = 0.0
        self._error: str | None = None
        self._record_blocks: list[np.ndarray] | None = None
        self._record_t0 = 0.0

    # -- capture ---------------------------------------------------------
    def _write(self, mono: np.ndarray) -> None:
        n = len(mono)
        if n >= len(self._buf):
            self._buf[:] = mono[-len(self._buf):]
            self._buf_n += n
            return
        end = self._buf_n % len(self._buf)
        first = min(n, len(self._buf) - end)
        self._buf[end:end + first] = mono[:first]
        if n > first:
            self._buf[:n - first] = mono[first:]
        self._buf_n += n

    def _tail(self, seconds: float) -> np.ndarray:
        want = min(int(seconds * SR_CAPTURE), len(self._buf), self._buf_n)
        if want <= 0:
            return np.zeros(0, dtype=np.float32)
        start = (self._buf_n - want) % len(self._buf)
        if start + want <= len(self._buf):
            return self._buf[start:start + want].copy()
        part = len(self._buf) - start
        return np.concatenate([self._buf[start:], self._buf[:want - part]])

    def _capture_loop(self) -> None:
        try:
            with self.device.recorder(samplerate=SR_CAPTURE, channels=2, blocksize=512) as rec:
                while not self._stop.is_set():
                    block = rec.record(numframes=512)
                    mono = np.asarray(block, dtype=np.float32).mean(axis=1)
                    if not self._sound_seen and float(np.sqrt(np.mean(mono ** 2))) > 0.006:
                        self._sound_seen = True
                        now = time.perf_counter()
                        # Only treat it as "the BGM just started" when it came a while after
                        # arming; if music was already playing, the start position is unknown.
                        if self._armed_wall and now - self._armed_wall >= 0.4:
                            self._first_sound_wall = now
                    with self._lock:
                        self._write(mono)
                    if self._record_blocks is not None:
                        if not self._record_blocks:
                            self._record_t0 = time.perf_counter() - len(mono) / SR_CAPTURE
                        self._record_blocks.append(mono.copy())
        except Exception as exc:  # noqa: BLE001
            self._error = f"{type(exc).__name__}: {exc}"

    # -- correlation -----------------------------------------------------
    @staticmethod
    def _correlate(segment: np.ndarray, query: np.ndarray) -> np.ndarray:
        q = query - query.mean()
        qn = float(np.linalg.norm(q)) + 1e-9
        n = len(q)
        if len(segment) < n + 8:
            return np.zeros(0, dtype=np.float32)
        conv = fftconvolve(segment, q[::-1], mode="valid")
        c = np.concatenate([[0.0], np.cumsum(segment, dtype=np.float64)])
        c2 = np.concatenate([[0.0], np.cumsum(segment.astype(np.float64) ** 2)])
        mean = (c[n:] - c[:-n]) / n
        var = (c2[n:] - c2[:-n]) / n - mean * mean
        denom = np.sqrt(np.maximum(var, 1e-12) * n) * qn
        return conv / denom

    def _measure(self, now: float) -> tuple[float, float]:
        with self._lock:
            raw = self._tail(WINDOW_SECONDS)
        return self._measure_window(now, raw, WINDOW_SECONDS)

    def _measure_window(self, now: float, raw: np.ndarray, window: float) -> tuple[float, float]:
        query = _downsample(raw)
        if len(query) < SR_REF * 0.3:
            return 0.0, 0.0
        if self._anchor is None:
            # If we saw the BGM start, the playback position cannot be far ahead of the
            # elapsed time since that moment.  Restricting the search avoids locking onto
            # a repeated section later in the track (which happens on loop-heavy BGMs).
            if self._first_sound_wall and (now - self._first_sound_wall) < 120.0:
                hint = now - self._first_sound_wall
                a = max(0, int((hint - 3.0) * SR_REF))
                b = min(len(self.ref), int((hint + 3.0) * SR_REF))
            else:
                a, b = 0, len(self.ref)
        else:
            predicted = self._anchor.position_at(now)
            margin = 0.3 if window > WINDOW_SECONDS else 0.5
            a = max(0, int((predicted - margin) * SR_REF))
            b = min(len(self.ref), int((predicted + margin + window) * SR_REF))
        corr = self._correlate(self.ref[a:b], query)
        if len(corr) == 0:
            return 0.0, 0.0
        idx = int(np.argmax(corr))
        return (a + idx + len(query) - 1) / SR_REF, float(corr[idx])

    def _track_loop(self) -> None:
        refined = False
        cand: tuple[float, float] | None = None
        while not self._stop.is_set():
            time.sleep(0.05 if self._anchor is None else 0.25)
            try:
                now = time.perf_counter()
                if self._anchor is None:
                    with self._lock:
                        raw = self._tail(1.2)
                    pos, score = self._measure_window(now, raw, 1.2)
                else:
                    pos, score = self._measure(now)
            except Exception as exc:  # noqa: BLE001
                self._error = f"{type(exc).__name__}: {exc}"
                return
            self._score = score
            if score >= SIGNAL_SCORE:
                self._signal_time = now
            if self._anchor is None:
                plausible = True
                if self._first_sound_wall and now - self._first_sound_wall < 15.0:
                    elapsed = now - self._first_sound_wall
                    plausible = pos <= elapsed + 2.0
                if score >= LOCK_SCORE and plausible:
                    if cand is not None:
                        predicted = cand[0] + (now - cand[1])
                        if abs(pos - predicted) < 0.15 and now - cand[1] < 1.0:
                            self._anchor = Anchor(pos, now, score)
                            refined = False
                            self._verified = False
                            self.log(f"[tracker] locked at {pos:.3f}s (score {score:.2f})")
                        else:
                            cand = (pos, now)
                    else:
                        cand = (pos, now)
                else:
                    cand = None
            elif not refined and now - self._anchor.wall > 0.5:
                refined = True
                with self._lock:
                    raw = self._tail(1.2)
                pos2, score2 = self._measure_window(now, raw, 1.2)
                self._verified = True
                if score2 > max(0.5, self._anchor.score * 0.9):
                    self._anchor = Anchor(pos2, now, score2)
                    self.log(f"[tracker] refined at {pos2:.3f}s (score {score2:.2f})")
                elif score2 < 0.30:
                    # Quiet passage: no strong match anywhere does not invalidate the
                    # initial lock, so keep it instead of chasing repeats.
                    self.log(f"[tracker] weak verification at {pos2:.2f}s (score {score2:.2f}); keeping lock")

    # -- public ----------------------------------------------------------
    def enable_recording(self) -> None:
        self._record_blocks = []

    def save_recording(self, path) -> float:
        """Write the captured mono stream as a 16-bit WAV; return the wall time of sample 0."""
        import wave
        from pathlib import Path

        blocks = self._record_blocks or []
        if not blocks:
            return 0.0
        data = np.concatenate(blocks)
        pcm = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as fh:
            fh.setnchannels(1)
            fh.setsampwidth(2)
            fh.setframerate(SR_CAPTURE)
            fh.writeframes(pcm.tobytes())
        return self._record_t0

    def start(self) -> None:
        self._armed_wall = time.perf_counter()
        threading.Thread(target=self._capture_loop, daemon=True).start()
        threading.Thread(target=self._track_loop, daemon=True).start()
        time.sleep(0.2)
        if self._error:
            raise RuntimeError(self._error)

    def stop(self) -> None:
        self._stop.set()

    @property
    def anchor(self) -> Anchor | None:
        return self._anchor

    @property
    def verified(self) -> bool:
        return self._verified and self._anchor is not None

    @property
    def signal_alive(self) -> bool:
        return (time.perf_counter() - self._signal_time) < 1.5

    @property
    def score(self) -> float:
        return self._score

    @property
    def device_name(self) -> str:
        return self.device.name

    @property
    def error(self) -> str | None:
        return self._error



