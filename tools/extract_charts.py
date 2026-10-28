"""Extract LYCO RECO BEATS charts from the local NIKKE asset cache (read-only).

Pipeline
--------
1. Locate the Addressables bundles in `nikke_Data/runtime_data/cache` by hash.
2. Read `LycorisLevelData` (BPM / EndBeat / Tracks[].SubBeats / KeyDatas) and
   `LycorisPresetData` (ActionName -> JudgeDatas with sub-beat offsets).
3. Join them: judge_time = (sub_beat + judge_offset) * 60 / (BPM * 24).
4. Emit one JSON per level, including which tracks are active for a given mod set.

Nothing in the game directory is modified.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import UnityPy

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lrbot.gamefiles import GameFiles  # noqa: E402

# Mods -> extra tracks, mirroring TrackPlaySystem.HDTracks / FLTracks
MOD_EXTRA_TRACKS = {"HD": (6, 7), "FL": (8, 9)}

# LycorisActionJudgeType: ADown=0, BDown=1(obsolete), AUp=2, BUp=3(obsolete), AHold=4
JUDGE_TYPES = {0: "down", 2: "up", 4: "hold"}

SUBBEATS_PER_BEAT = 24


def bundle_path(gf: GameFiles, key: str) -> Path:
    if key == "levels":
        return gf.bundle_data("requiredminigamelycoris-level", suffix=True)
    if key == "presets":
        return gf.bundle_data("minigamelycoris.asset")
    raise KeyError(key)


def read_presets(gf: GameFiles) -> dict[int, dict]:
    env = UnityPy.load(str(bundle_path(gf, "presets")))
    presets: dict[int, dict] = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        data = obj.read()
        uid = getattr(data, "_uid", None)
        if not uid:
            continue
        actions = {}
        for action in data.PresetActions or []:
            actions[action.ActionName] = {
                "action_type": int(action.ActionType),
                "length": int(action.ActionLength),
                "judges": [
                    {
                        "type": JUDGE_TYPES.get(int(j.JudgeType), str(j.JudgeType)),
                        "offset": int(j.JudgeSubBeatOffset),
                        "sound": j.HitSound or "",
                    }
                    for j in (action.JudgeDatas or [])
                ],
            }
        presets[int(uid)] = {"name": data.PresetName, "actions": actions}
    return presets


def read_levels(gf: GameFiles) -> dict[str, dict]:
    env = UnityPy.load(str(bundle_path(gf, "levels")))
    levels: dict[str, dict] = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        data = obj.read()
        if not hasattr(data, "Tracks"):
            continue
        levels[data.LevelName] = {
            "asset": data.m_Name,
            "level_name": data.LevelName,
            "bgm": data.BGM,
            "bgm_teach": getattr(data, "BGMTEACH", ""),
            "bpm": int(data.BPM),
            "difficulty": int(data.Difficulty),
            "end_beat": int(data.EndBeat),
            "tracks_enable": [bool(x) for x in data.TracksEnable],
            "tracks": [
                {
                    "sub_beats": [int(x) for x in track.SubBeats],
                    "keys": [
                        {
                            "preset_uid": int(key.PresetUid),
                            "action": key.KeyAction,
                        }
                        for key in track.KeyDatas
                    ],
                }
                for track in data.Tracks
            ],
        }
    return levels


def build_chart(level: dict, presets: dict[int, dict], mods: set[str]) -> dict:
    bpm = level["bpm"]
    subbeat_seconds = 60.0 / (bpm * SUBBEATS_PER_BEAT)
    active_tracks = set(i for i, on in enumerate(level["tracks_enable"]) if on)
    for mod in mods:
        active_tracks.update(MOD_EXTRA_TRACKS.get(mod, ()))

    notes = []
    problems = []
    for track_index, track in enumerate(level["tracks"]):
        if track_index not in active_tracks:
            continue
        for sub_beat, key in zip(track["sub_beats"], track["keys"]):
            preset = presets.get(key["preset_uid"])
            if preset is None:
                problems.append(f"track {track_index}: preset {key['preset_uid']} not found")
                continue
            action = preset["actions"].get(key["action"])
            if action is None:
                problems.append(f"track {track_index}: action {key['action']!r} not found in {preset['name']}")
                continue
            for judge in action["judges"]:
                t = (sub_beat + judge["offset"]) * subbeat_seconds
                notes.append(
                    {
                        "t": round(t, 6),
                        "sub_beat": sub_beat,
                        "judge_offset": judge["offset"],
                        "type": judge["type"],
                        "track": track_index,
                        "action": key["action"],
                        "sound": judge["sound"],
                    }
                )

    notes.sort(key=lambda n: (n["t"], n["track"]))
    return {
        "level": level["level_name"],
        "asset": level["asset"],
        "bgm": level["bgm"],
        "bpm": bpm,
        "end_beat": level["end_beat"],
        "duration": round(level["end_beat"] * 60.0 / bpm, 3),
        "subbeat_seconds": subbeat_seconds,
        "mods": sorted(mods),
        "active_tracks": sorted(active_tracks),
        "note_count": len(notes),
        "counts": {t: sum(1 for n in notes if n["type"] == t) for t in ("down", "hold", "up")},
        "notes": notes,
        "problems": problems,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "charts"), help="output directory")
    parser.add_argument("--game-dir", default=None, help="NIKKE install dir (auto-detected by default)")
    parser.add_argument(
        "--mods",
        default="HD,FL",
        help="comma separated extra mods that add tracks (HD,FL); PF/SD/HR/DT do not change the chart",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    mods = {m.strip().upper() for m in args.mods.split(",") if m.strip()}

    game = GameFiles(args.game_dir)
    print(f"game dir: {game.root}")
    presets = read_presets(game)
    levels = read_levels(game)
    print(f"presets: {[(u, p['name']) for u, p in presets.items()]}")
    print(f"levels : {list(levels)}")

    for name, level in levels.items():
        chart = build_chart(level, presets, mods)
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(chart, ensure_ascii=False, indent=1), encoding="utf-8")
        print(
            f"{name:<20} bpm={chart['bpm']:>3} dur={chart['duration']:>6}s "
            f"tracks={chart['active_tracks']} notes={chart['note_count']:>3} {chart['counts']}"
            + (f" PROBLEMS={chart['problems']}" if chart["problems"] else "")
        )


if __name__ == "__main__":
    main()
