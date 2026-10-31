"""Guided offset calibration: run one Normal pass with several offsets and pick the best."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.json"
SWEEP = "-90,-70,-50,-30,-10"
ROW_RE = re.compile(r"note\s+\d+\s+t=\s*[\d.]+s\s+([+-][\d.]+)ms\s+(\w+)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chart", default=str(ROOT / "charts" / "ShootStage_NM.json"))
    parser.add_argument("--device", default=None, help="same as replay.py --device")
    args = parser.parse_args()

    before = {p.name for p in (ROOT / "runs").glob("*.log")}
    cmd = [
        sys.executable, str(ROOT / "tools" / "replay.py"),
        "--chart", args.chart, f"--sweep={SWEEP}", "--no-elevate", "--dump-verdicts",
    ]
    if args.device:
        cmd += ["--device", args.device]
    print("$", " ".join(cmd), flush=True)
    code = subprocess.call(cmd, cwd=ROOT)
    if code != 0:
        print(f"\nreplay.py 退出码 {code}，本次校准作废。")
        print("常见原因：没进 Normal 第一关 / 没按 F9 / 180 秒内没锁到 BGM / 输出设备选错。")
        print("查设备：py -3.13 tools/replay.py --list-devices")
        return

    logs = sorted((ROOT / "runs").glob("*.log"), key=lambda p: p.stat().st_mtime)
    new = [p for p in logs if p.name not in before]
    if not new:
        print("没有找到本次运行的日志")
        return
    text = new[-1].read_text(encoding="utf-8", errors="ignore")
    stats: dict[float, list[int]] = defaultdict(lambda: [0, 0])
    for offset, verdict in ROW_RE.findall(text):
        key = float(offset)
        stats[key][0] += 1
        stats[key][1] += verdict == "Perfect"
    if not stats:
        print("日志里没有判定数据")
        return

    print("\n偏移    Perfect")
    rows = []
    for offset in sorted(stats):
        total, perfect = stats[offset]
        rate = perfect / total if total else 0.0
        print(f"{offset:+6.0f} ms  {perfect}/{total}  ({100 * rate:.0f}%)")
        rows.append((offset, total, perfect, rate))
    if not rows:
        return
    best_rate = max(r[3] for r in rows)
    if best_rate <= 0.0:
        print("\n五个偏移没有任何 Perfect，窗口不在这条区间里。")
        print("可以先 --sweep 手动扩一段再试，例如：")
        print(f"  py -3.13 tools/replay.py --chart {args.chart} --sweep=-140,-120,-100,-80,-60 --dump-verdicts")
        return

    # Ties are the norm, not the exception: offsets are cycled across notes, so a
    # run of neighbouring offsets all scores 100%. Take the middle of that plateau
    # instead of the first one seen, because an edge value has zero headroom.
    winners = [r[0] for r in rows if r[3] == best_rate]
    run = [winners[0]]
    for offset in winners[1:]:
        if offset - run[-1] <= 30:
            run.append(offset)
        else:
            break
    best_offset = (run[0] + run[-1]) / 2.0

    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    cfg["offset_ms"] = int(round(best_offset))
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    if len(run) > 1:
        print(f"\n满分区间 {run[0]:+.0f} ~ {run[-1]:+.0f} ms，取中点 {best_offset:+.0f} ms"
              f"（Perfect 率 {100 * best_rate:.0f}%），已写入 config.json")
    else:
        print(f"\n最佳偏移 {best_offset:+.0f} ms（Perfect 率 {100 * best_rate:.0f}%），已写入 config.json")
    print(f"来源：{new[-1].name}  共 {sum(r[1] for r in rows)} 个判定")


if __name__ == "__main__":
    main()
