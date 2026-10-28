"""LYCO RECO BEATS replay bot.

Usage (run from an elevated terminal, or let the script self-elevate):

    python tools/replay.py --chart charts/ShootStage_HD.json --offset-ms 0

Controls:
    F9   arm / start
    F10  abort

The game window must stay in the foreground.  The script locks onto the stage BGM
through WASAPI loopback and then presses Space at the chart's judge times.
"""
from __future__ import annotations

import argparse
import ctypes
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
from lrbot.chart import build_events, describe, load_chart  # noqa: E402

PLAYER_LOG = Path(os.environ["USERPROFILE"]) / "AppData/LocalLow/com.tencent/胜利女神：新的希望/Player.log"
LOG_LINE = re.compile(r"JudgeSystem OnJudge (\w+)")


class Runner:
    def __init__(self, args) -> None:
        self.args = args
        self.chart = load_chart(args.chart)
        self.events = build_events(self.chart)
        self.hwnd = win_input.find_game_window()
        self.log_path = ROOT / "runs" / f"{datetime.now():%Y%m%d_%H%M%S}.log"
        self.log_path.parent.mkdir(exist_ok=True)
        self._log_file = self.log_path.open("a", encoding="utf-8")
        self.press_times: list[float] = []

    def log(self, message: str) -> None:
        line = f"{datetime.now():%H:%M:%S.%f}"[:-3] + f"  {message}"
        print(line, flush=True)
        self._log_file.write(line + "\n")
        self._log_file.flush()

    # -- helpers ---------------------------------------------------------
    def audio_path(self) -> Path:
        bgm = self.chart.get("bgm", "")
        candidate = ROOT / "audio" / f"{bgm}.wav"
        if candidate.exists():
            return candidate
        raise SystemExit(
            f"缺少参考音频 audio/{bgm}.wav；请先运行 python tools/extract_bgm.py"
        )

    def log_size(self) -> int:
        try:
            return PLAYER_LOG.stat().st_size
        except OSError:
            return 0

    def judge_sequence_since(self, byte_offset: int) -> list[str]:
        """Judgement types logged after `byte_offset` (in order)."""
        if not PLAYER_LOG.exists():
            return []
        size = self.log_size()
        start = byte_offset if 0 <= byte_offset <= size else 0
        seq: list[str] = []
        with PLAYER_LOG.open("rb") as fh:
            fh.seek(start)
            for raw in fh:
                match = LOG_LINE.search(raw.decode("utf-8", "ignore"))
                if match:
                    seq.append(match.group(1))
        return seq

    def gameplay_finished(self, byte_offset: int) -> bool:
        if not PLAYER_LOG.exists():
            return False
        size = self.log_size()
        start = byte_offset if 0 <= byte_offset <= size else 0
        with PLAYER_LOG.open("rb") as fh:
            fh.seek(start)
            return b"Gameplay stopped" in fh.read()

    def judge_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for verdict in self.judge_sequence_since(self.log_size() - 800_000):
            counts[verdict] = counts.get(verdict, 0) + 1
        return counts

    # -- scheduling ------------------------------------------------------
    @staticmethod
    def _sleep_until(target: float) -> float:
        while True:
            now = time.perf_counter()
            remaining = target - now
            if remaining <= 0:
                return now
            if remaining > 0.003:
                time.sleep(remaining - 0.002)

    def play(self, tracker: BgmTracker) -> dict:
        base_offset = self.args.offset_ms / 1000.0
        probe = [float(x) for x in self.args.probe.split(",") if x.strip()] if self.args.probe else []
        sweep = [float(x) for x in self.args.sweep.split(",") if x.strip()] if self.args.sweep else []
        anchor = tracker.anchor
        if anchor is None:
            raise SystemExit("BGM tracker did not lock")
        anchor_pos, anchor_wall = anchor.position, anchor.wall
        self.log(f"anchor: bgm={anchor_pos:.3f}s  score={anchor.score:.2f}  device={tracker.device_name}")
        log_start = self.log_size()

        events = [e for e in self.events if e.t > anchor_pos + self.args.skip_before]
        limit = self.args.max_notes or (len(probe) if probe else 0)
        if limit:
            seen = 0
            limited = []
            for event in events:
                limited.append(event)
                if event.kind == "down":
                    seen += 1
                    if seen >= limit:
                        break
            events = limited
        if not events:
            self.log("no events left")
            return {"sent": 0}

        self.log(f"events to play: {len(events)}  (first at {events[0].t:.3f}s, last {events[-1].t:.3f}s)")
        sent = 0
        errors: list[float] = []
        applied: list[float] = []
        current_offset = base_offset
        down_index = 0
        lost_since: float | None = None
        for event in events:
            if event.kind == "down":
                if sweep:
                    current_offset = sweep[down_index % len(sweep)] / 1000.0
                else:
                    current_offset = probe[down_index] / 1000.0 if down_index < len(probe) else base_offset
                down_index += 1
            target = anchor_wall + (event.t - anchor_pos) + current_offset
            now = time.perf_counter()
            if target < now - 0.05:
                self.log(f"skip {event.kind} @{event.t:.3f} (too late by {1000 * (now - target):.1f} ms)")
                continue
            if event.kind == "down" and not self.args.no_focus_check:
                if not win_input.is_foreground(self.hwnd):
                    self.log("game lost foreground, aborting")
                    break
            self._sleep_until(target)
            actual = time.perf_counter()
            if event.kind == "down":
                win_input.key_down()
                applied.append(current_offset)
                self.press_times.append(actual)
            else:
                win_input.key_up()
            errors.append(actual - target)
            sent += 1

            if self.gameplay_finished(log_start):
                self.log("gameplay finished, aborting")
                break
            if not tracker.signal_alive:
                lost_since = lost_since or time.perf_counter()
                if time.perf_counter() - lost_since > 5:
                    self.log("BGM lost for 5s, aborting")
                    break
            else:
                lost_since = None

        win_input.key_up()
        time.sleep(0.6)  # let the last judgement reach Player.log
        mean = sum(errors) / len(errors) if errors else 0.0
        worst = max((abs(e) for e in errors), default=0.0)
        self.log(f"done: {sent} events, mean error {1000 * mean:+.2f} ms, worst {1000 * worst:.2f} ms")
        sequence = self.judge_sequence_since(log_start)
        counts: dict[str, int] = {}
        for verdict in sequence:
            counts[verdict] = counts.get(verdict, 0) + 1
        self.log(f"judgements this run: {counts}")
        if probe:
            self.log("probe results (note # / offset ms / verdict):")
            for index, offset in enumerate(applied):
                verdict = sequence[index] if index < len(sequence) else "<none>"
                self.log(f"  #{index + 1:02d}  {1000 * offset:+7.1f} ms  {verdict}")
        if self.args.dump_verdicts:
            down_times = [e.t for e in events if e.kind == "down"]
            for index, note_time in enumerate(down_times):
                verdict = sequence[index] if index < len(sequence) else "<none>"
                offset = applied[index] if index < len(applied) else 0.0
                self.log(f"  note {index + 1:03d}  t={note_time:7.3f}s  {1000 * offset:+6.1f}ms  {verdict}")
        return {
            "sent": sent,
            "mean_ms": 1000 * mean,
            "worst_ms": 1000 * worst,
            "judgements": counts,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="LYCO RECO BEATS replay bot")
    parser.add_argument("--chart", required=True, help="chart json produced by extract_charts.py")
    parser.add_argument("--offset-ms", type=float, default=0.0, help="positive = press later")
    parser.add_argument("--device", default=None, help="loopback device name substring")
    parser.add_argument("--skip-before", type=float, default=0.35, help="ignore notes closer than this")
    parser.add_argument("--max-notes", type=int, default=0, help="stop after N notes (0 = all)")
    parser.add_argument("--probe", default="", help="comma separated per-note offsets in ms, e.g. -120,-40,40,120")
    parser.add_argument("--sweep", default="", help="comma separated offsets cycled across all notes, e.g. -30,-20,-10,0")
    parser.add_argument("--dry-run", action="store_true", help="print the timeline, send nothing")
    parser.add_argument("--no-elevate", action="store_true")
    parser.add_argument("--no-focus-check", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--pause", action="store_true", help="wait for Enter before exiting")
    parser.add_argument("--dump-verdicts", action="store_true", help="log every note's verdict")
    parser.add_argument("--record-audio", action="store_true", help="save the captured loopback audio")
    args = parser.parse_args()

    if args.list_devices:
        for name in list_loopback_devices():
            print(name)
        return

    chart = load_chart(args.chart)
    print(describe(chart))
    if args.dry_run:
        events = build_events(chart)
        print(f"{len(events)} events")
        for event in events[:20]:
            print(f"  {event.t:8.3f}  {event.kind:<4} {event.note}")
        print("  ...")
        return

    if not args.no_elevate:
        win_input.ensure_admin()

    runner = Runner(args)
    if not runner.hwnd and not args.no_focus_check:
        raise SystemExit("NIKKE window not found; start the game first")

    print(f"game window: {win_input.window_title(runner.hwnd)!r}  admin={win_input.is_admin()}")
    print(f"chart: {describe(chart)}")
    tracker = BgmTracker(str(runner.audio_path()), device=args.device, log=runner.log)
    print(f"loopback device: {tracker.device_name}")
    print("F9 = arm, F10 = quit")

    arm = win_input.KeyWatcher(win_input.VK_F9)
    quit_key = win_input.KeyWatcher(win_input.VK_F10)
    win_input.begin_timer_precision()
    try:
        while True:
            if quit_key.pressed():
                return
            if arm.pressed():
                break
            time.sleep(0.02)

        runner.log("armed; waiting for BGM")
        if args.record_audio:
            tracker.enable_recording()
        tracker.start()
        deadline = time.perf_counter() + 180
        while time.perf_counter() < deadline:
            if tracker.error:
                raise SystemExit(tracker.error)
            if quit_key.pressed():
                return
            if tracker.anchor is not None and tracker.verified:
                break
            time.sleep(0.02)
        else:
            raise SystemExit(
                "timed out waiting for the stage BGM on "
                f"{tracker.device_name!r}; available: {list_loopback_devices()}"
            )

        result = runner.play(tracker)
        runner.log(f"result: {json.dumps(result)}")

        if args.record_audio:
            tracker.stop()
            time.sleep(0.2)
            stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
            wav_path = ROOT / "runs" / f"audio_{stamp}.wav"
            t0 = tracker.save_recording(wav_path)
            meta = {
                "chart": chart["level"],
                "anchor": vars(anchor) if (anchor := tracker.anchor) else None,
                "t0_wall": t0,
                "presses": runner.press_times,
                "offset_ms": args.offset_ms,
            }
            (ROOT / "runs" / f"audio_{stamp}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
            runner.log(f"audio recorded: {wav_path}")
    finally:
        tracker.stop()
        win_input.key_up()
        win_input.end_timer_precision()
        if args.pause:
            try:
                input("Press Enter to exit...")
            except EOFError:
                pass


if __name__ == "__main__":
    main()
