"""Extract the minigame judge / hit SFX (read-only)."""
from __future__ import annotations

import sys
from pathlib import Path

import UnityPy

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lrbot.gamefiles import GameFiles  # noqa: E402

OUT = ROOT / "audio" / "sfx"

CLIPS = {
    "perfect": "audiogroupui_assets_sfx_mini_ce008_perfect",
    "miss": "audiogroupui_assets_sfx_mini_ce008_miss",
    "vrshooting_down": "audiogroupui_assets_sfx_mini_ce008_vrshooting_down",
    "training_down_2_1": "audiogroupui_assets_sfx_mini_ce008_training_down_2_1",
    "desert_long_down": "audiogroupui_assets_sfx_mini_ce008_desert_long_down",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    game = GameFiles()
    print(f"game dir: {game.root}")
    for name, pattern in CLIPS.items():
        try:
            path = game.bundle_data(pattern)
        except (LookupError, FileNotFoundError) as exc:
            print(f"{name}: {exc}")
            continue
        env = UnityPy.load(str(path))
        for obj in env.objects:
            if obj.type.name != "AudioClip":
                continue
            clip = obj.read()
            clip_name, data = next(iter(clip.samples.items()))
            out = OUT / f"{name}.wav"
            out.write_bytes(bytes(data))
            print(f"{name:<20} {clip_name:<40} {clip.m_Length:6.3f}s -> {out}")


if __name__ == "__main__":
    main()
