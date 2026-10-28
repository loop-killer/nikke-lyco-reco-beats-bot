"""Record a human play-through and compare the press times with the extracted chart.

Useful as a calibration oracle: on Normal the visual guide lets a skilled player hit
Perfect; the wall-clock instants of those key presses, mapped through the audio
anchor, tell us where the "sweet spot" is relative to our chart timestamps.

Controls: F9 = arm, F10 = stop.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lrbot import win_input  # noqa: E402
from lrbot.audio_sync import BgmTracker, list_loopback_devices  # noqa: E402
from lrbot.chart import describe, load_chart  # noqa: E402

VK_SPACE = 0x20
PLAYER_LOG = Path(os.environ["USERPROFILE"]) / "AppData/LocalLow/com.tencent/胜利女神：新的希望/Player.log"
LOG_LINE = re.compile(r"JudgeSystem OnJudge (\w+)")


def judge_counts_since(byte_offset: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not PLAYER_LOG.exists():
        return counts
    size = PLAYER_LOG.stat().st_size
    start = byte_offset if 0 <= byte_offset <= size else 0
    with PLAYER_LOG.open("rb") as fh:
        fh.seek(start)
        for raw in fh:
            match = LOG_LINE.search(raw.decode("utf-8", "ignore"))
            if match:
                counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    return counts


def audio_path(chart: dict) -> Path:
    bgm = chart.get("bgm", "")
    candidate = ROOT / "audio" / f"{bgm}.wav"
    if candidate.exists():
        return candidate
    raise SystemExit(f"缺少参考音频 audio/{bgm}.wav；请先运行 python tools/extract_bgm.py")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chart", required=True)
    parser.add_argument("--device", default=None)
    parser.add_argument("--no-elevate", action="store_true")
    parser.add_argument("--pause", action="store_true")
    args = parser.parse_args()

    if not args.no_elevate:
        win_input.ensure_admin()

    chart = load_chart(args.chart)
    notes = [float(n["t"]) for n in chart["notes"] if n["type"] == "down"]
    print(describe(chart))

    tracker = BgmTracker(str(audio_path(chart)), device=args.device, log=print)
    print(f"loopback device: {tracker.device_name}")
    print("F9 = arm, then play the stage manually. F10 = stop")

    arm = win_input.KeyWatcher(win_input.VK_F9)
    quit_key = win_input.KeyWatcher(win_input.VK_F10)
    space = win_input.KeyWatcher(VK_SPACE)
    win_input.begin_timer_precision()
    try:
        while not arm.pressed():
            if quit_key.pressed():
                return
            time.sleep(0.02)
        print("armed; waiting for BGM")
        tracker.start()
        deadline = time.perf_counter() + 180
        while time.perf_counter() < deadline:
            if tracker.anchor is not None and tracker.verified:
                break
            if quit_key.pressed():
                return
            time.sleep(0.02)
        anchor = tracker.anchor
        if anchor is None:
            raise SystemExit("no BGM lock")
        print(f"anchor: bgm={anchor.position:.3f}s score={anchor.score:.2f}")
        log_start = PLAYER_LOG.stat().st_size if PLAYER_LOG.exists() else 0

        presses: list[float] = []
        end = time.perf_counter() + chart["duration"] + 3.0
        while time.perf_counter() < end:
            if quit_key.pressed():
                break
            if space.pressed():
                presses.append(time.perf_counter())
            time.sleep(0.0005)
    finally:
        tracker.stop()
        win_input.end_timer_precision()

    # match presses to chart notes (sequential, tolerant)
    matched: list[tuple[float, float, float]] = []  # note_t, press_pos, delta_ms
    index = 0
    for wall in presses:
        pos = anchor.position_at(wall)
        while index < len(notes) and notes[index] < pos - 0.35:
            index += 1
        if index >= len(notes):
            break
        note_t = notes[index]
        if abs(pos - note_t) <= 0.35:
            matched.append((note_t, pos, (pos - note_t) * 1000.0))
            index += 1

    print(f"\npresses: {len(presses)}  matched: {len(matched)} / {len(notes)}")
    counts = judge_counts_since(log_start)
    if counts:
        print(f"game judgements: {counts}")
    if matched:
        deltas = sorted(d for _, _, d in matched)
        n = len(deltas)
        mean = sum(deltas) / n
        median = deltas[n // 2] if n % 2 else (deltas[n // 2 - 1] + deltas[n // 2]) / 2
        var = sum((d - mean) ** 2 for d in deltas) / n
        print(f"delta ms: mean {mean:+.1f}  median {median:+.1f}  sd {var ** 0.5:.1f}  "
              f"min {deltas[0]:+.1f}  max {deltas[-1]:+.1f}")
        print(f"suggested --offset-ms {median:+.0f}  (positive = press later)")
        for note_t, pos, delta in matched[:20]:
            print(f"  note {note_t:7.3f}s  press {pos:7.3f}s  {delta:+7.1f} ms")
        print("  ...")

    out = ROOT / "runs" / f"record_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "chart": chart["level"],
        "anchor": {"position": anchor.position, "wall": anchor.wall, "score": anchor.score},
        "presses": presses,
        "matched": matched,
    }, indent=1), encoding="utf-8")
    print(f"saved {out}")
    if args.pause:
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass


if __name__ == "__main__":
    main()
