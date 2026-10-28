"""Export the BGM tracks referenced by the extracted charts (read-only)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import UnityPy

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lrbot.gamefiles import GameFiles  # noqa: E402

OUT = ROOT / "audio"


def chart_bgm_keys() -> list[str]:
    keys: list[str] = []
    for path in sorted((ROOT / "charts").glob("*.json")):
        try:
            bgm = json.loads(path.read_text(encoding="utf-8")).get("bgm", "")
        except Exception:  # noqa: BLE001
            continue
        if bgm and bgm not in keys:
            keys.append(bgm)
    return keys


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    game = GameFiles()
    print(f"game dir: {game.root}")
    keys = chart_bgm_keys()
    if not keys:
        raise SystemExit("charts/ 里没有 BGM 信息，请先运行 extract_charts.py")
    for key in keys:
        try:
            path = game.bundle_data(f"audiogroupminigame_assets_{key}")
        except (LookupError, FileNotFoundError) as exc:
            print(f"{key}: skipped ({exc.__class__.__name__})")
            continue
        env = UnityPy.load(str(path))
        found = False
        for obj in env.objects:
            if obj.type.name != "AudioClip":
                continue
            clip = obj.read()
            name, data = next(iter(clip.samples.items()))
            out = OUT / f"{key}.wav"
            out.write_bytes(bytes(data))
            print(f"{key:<40} {clip.m_Length:6.3f}s -> {out}")
            found = True
        if not found:
            print(f"{key}: no AudioClip found")


if __name__ == "__main__":
    main()
