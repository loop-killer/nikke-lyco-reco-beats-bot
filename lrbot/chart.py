"""Chart model: turn the extracted note list into press/release events."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

TAP_HOLD_SECONDS = 0.045
MIN_HOLD_SECONDS = 0.020


@dataclass(frozen=True)
class Event:
    t: float
    kind: str  # "down" | "up"
    note: str = ""


def load_chart(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_events(chart: dict, tap_hold: float = TAP_HOLD_SECONDS) -> list[Event]:
    notes = chart["notes"]
    events: list[Event] = []
    i = 0
    while i < len(notes):
        note = notes[i]
        if note["type"] != "down":
            i += 1
            continue
        start = float(note["t"])
        up: float | None = None
        j = i + 1
        while j < len(notes) and notes[j]["type"] in ("hold", "up"):
            if notes[j]["type"] == "up":
                up = float(notes[j]["t"])
                j += 1
                break
            j += 1
        if up is None:
            next_t = float(notes[j]["t"]) if j < len(notes) else start + 1.0
            up = min(start + tap_hold, next_t - MIN_HOLD_SECONDS)
            if up <= start:
                up = start + MIN_HOLD_SECONDS
        events.append(Event(start, "down", note["action"]))
        events.append(Event(up, "up", note["action"]))
        i = j

    events.sort(key=lambda e: (e.t, 0 if e.kind == "down" else 1))
    # collapse exact duplicates (same instant, same kind)
    deduped: list[Event] = []
    for event in events:
        if deduped and deduped[-1].kind == event.kind and abs(deduped[-1].t - event.t) < 1e-6:
            continue
        deduped.append(event)
    return deduped


def describe(chart: dict) -> str:
    counts = chart.get("counts", {})
    return (
        f"{chart['level']}  bpm={chart['bpm']}  end={chart['duration']}s  "
        f"notes={chart['note_count']}  down={counts.get('down', 0)} hold={counts.get('hold', 0)} up={counts.get('up', 0)}"
    )
