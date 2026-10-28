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
    args = parser.parse_args()

    before = {p.name for p in (ROOT / "runs").glob("*.log")}
    cmd = [
        sys.executable, str(ROOT / "tools" / "replay.py"),
        "--chart", args.chart, "--sweep", SWEEP, "--no-elevate", "--dump-verdicts",
    ]
    print("$", " ".join(cmd))
    subprocess.call(cmd, cwd=ROOT)

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
    best_offset, best_rate = None, -1.0
    for offset in sorted(stats):
        total, perfect = stats[offset]
        rate = perfect / total if total else 0.0
        print(f"{offset:+6.0f} ms  {perfect}/{total}  ({100 * rate:.0f}%)")
        if rate > best_rate:
            best_offset, best_rate = offset, rate
    if best_offset is None:
        return
    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    cfg["offset_ms"] = int(best_offset)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n最佳偏移 {best_offset:+.0f} ms（Perfect 率 {100 * best_rate:.0f}%），已写入 config.json")


if __name__ == "__main__":
    main()
