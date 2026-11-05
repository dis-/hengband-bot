"""Build tests/fixtures/arena-live-1105.json.gz from the arena's live capture.

Source: C:/hengband-backups/pdca/captures/arena-live-1105/*.json, written by hand-driven
keys and by the bot on the Linux test environment, a copy of a test character (never a
viewing character).  Each file holds the keys sent, then the board and the screen the game
answered with through the control server.  The screen's colours are dropped.
"""
import gzip
import json
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/captures/arena-live-1105")
TARGET = Path(__file__).with_name("fixtures") / "arena-live-1105.json.gz"
LABELS = (
    "01-arena-building", "02-poster", "03-enter", "04-read-refused", "07-step-off", "09-move",
    "10-move", "11-reward-step", "12-travel-to-gate", "13-poster2", "14-enter2", "16-gate-closed",
    "19-reload-in-arena", "20-killed", "21-after-loss-off", "22-loser-step",
)


def main():
    cases = {}
    for label in LABELS:
        record = json.loads((SOURCE / f"{label}.json").read_text(encoding="utf-8"))
        result = record["screen"].get("result", {})  # 01's screen request was malformed
        cases[label] = {
            "keys": record["keys"], "board": record["state"],
            "screen": {name: result[name] for name in ("width", "height", "lines", "cursor")
                       if name in result},
        }
    with gzip.open(TARGET, "wt", encoding="utf-8") as stream:
        json.dump(cases, stream, ensure_ascii=False)
    print(TARGET, TARGET.stat().st_size)


if __name__ == "__main__":
    main()
