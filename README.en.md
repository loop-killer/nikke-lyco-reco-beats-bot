# LYCO RECO BEATS Auto-Perfect

> A chart-replay bot for the **LYCO RECO BEATS** minigame in *Goddess of Victory: NIKKE* (CN client) × *Lycoris Recoil* collab.

[中文文档](README.md) | English

Verified on all three Hard stages with every MOD enabled:

| Stage | Result |
|---|---|
| ShootStage (1st) | **Perfect 76 / 76** |
| Training (2nd) | **Perfect 78 / 78** |
| DessertStage (3rd, with long holds) | **Perfect 50 / 50** |

> No screen reading, no audio-onset guessing, no "which gun is it" recognition, and no game files are modified.

---

## How it works

This minigame is not a reaction test — it is a **memorization** test. Every judgement timestamp already exists in the client assets.

1. **Chart extraction** — read `LycorisLevelData` (per-track `SubBeats`) and `LycorisPresetData` (per-action judge offsets) from the local Addressables cache and compute
   `t = (SubBeat + JudgeOffset) × 60 / (BPM × 24)`.
2. **Clock sync** — capture the game's BGM through WASAPI loopback and cross-correlate it with the reference track exported from the game, locking onto the current playback position.
3. **Replay** — send Space with `SendInput` at the computed instants; keep the key down through Hold sections and release on Up judgements.

Because timing comes from the chart, the only error sources are scheduling jitter (~1 ms measured) and the constant audio-path latency (calibrated once). Hard mode removes the visual guide and dims the screen — a vision-based approach cannot work there anyway.

---

## Requirements

- Windows 10/11
- NIKKE **CN PC client** (`nikke.exe`)
- Python 3.10+ (3.13 recommended)
- The minigame must have been opened at least once, so Addressables has downloaded its assets

## Install

```bat
py -3.13 -m pip install -r requirements.txt
```

Or just double-click `start.bat`; it installs missing dependencies automatically.

## Usage

Run **`start.bat`** (it requests administrator rights) and use the menu:

1. **Extract game assets** — run once, and again after a game update. Produces `charts/`, `audio/` and `audio/sfx/`. Read-only; nothing in the game directory is modified.
2. **Calibrate offset** — plays Normal stage 1 once with five different offsets and stores the best one in `config.json`. Re-run after changing headphones or output devices.
3. **Play a stage** — select Hard and enable every MOD in-game, then follow the prompt and press **F9** before starting.

During a run:

- **F9** arm / start
- **F10** quit
- The game window must stay in the foreground; switching away aborts the run
- The bot stops automatically on pause/death/result screens, so it will not press Space in menus

## Offset

`offset_ms` in `config.json` shifts every press: **positive = later, negative = earlier**.

Audio output latency differs per machine, so calibrate once. The default `-45` was measured on an NVIDIA HDMI output with the CN client. The Perfect window is roughly 60–70 ms wide, so ±10 ms of calibration error is fine.

## Scope

- Only the three **Hard** stages (ShootStage / Training / DessertStage) are covered.
- MODs (HR/DT/HD/FL/SD/PF) do not change these charts; they only change judgement windows and rules, so a correct offset is all that is needed.
- After a game update the bundle hashes change, but `extract_charts.py` re-parses `catalog.json`, so no code change is normally required. A chart-structure change would need adaptation.

## FAQ

**"Asset not downloaded"**
Open LYCO RECO BEATS once in-game (no need to finish a stage) so Addressables caches its bundles.

**"timed out waiting for the stage BGM"**
Wrong output device. Run `py -3.13 tools/replay.py --list-devices`, then put a substring in `config.json` as `"device": "..."`.

**Locked, but every judgement is Great**
Offset is off. Re-calibrate, or nudge `offset_ms` by 10–20 ms in either direction.

**No judgements at all**
Space is not reaching the game. Make sure the script runs elevated ( `start.bat` does it), the game is foreground, and it is the CN client.

**Will I get banned?**
The bot only simulates external input (`SendInput`) and reads local files. It does not inject into the process, modify game files, or touch ACE. Automation still violates the game's ToS — use at your own risk.

## Layout

```
lrbot/                 core library
  audio_sync.py        loopback capture + cross-correlation position lock
  win_input.py         SendInput / window / hotkeys
  chart.py             chart -> press/release events
  gamefiles.py         locate the install, resolve bundles by name
tools/
  extract_charts.py    extract charts from game assets
  extract_bgm.py       export reference BGM
  extract_sfx.py       export judge SFX (for calibration/analysis)
  replay.py            replay engine
  calibrate.py         automatic offset calibration
  record.py            record a manual performance (advanced)
  analyze_latency.py   measure audio-path latency from a recording
  dev/                 development-time sweep/test scripts (optional)
docs/
  CALIBRATION.md       calibration details (Chinese)
charts/                generated charts (git-ignored)
audio/                 generated reference audio (git-ignored)
runs/                  per-run logs (git-ignored)
```

## Technical notes

- 24 sub-beats per beat: `t = (SubBeat + JudgeOffset) × 60 / (BPM × 24)` seconds.
- Three judge types: `Down`, `Up`, `Hold`. A Hold is auto-Perfect while the key stays down; an Up is judged at release.
- MODs: `HR` +1 difficulty (tighter windows), `DT` damage multiplier, `HD` adds tracks 6/7, `FL` flashlight effect (darker screen), `SD` a single Miss ends the run, `PF` Great/Good count as Miss.
- On these three Hard stages the HD/FL tracks are empty, so those MODs do not change the chart.

## Disclaimer

For learning and experimentation only. Not affiliated with SHIFT UP, Level Infinite, or Tencent.
Using this tool may violate the game's Terms of Service and lead to account penalties; you accept all consequences.
Do not redistribute game assets extracted with these tools (charts, audio).
