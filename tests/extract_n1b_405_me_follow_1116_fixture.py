"""Extract tests/fixtures/n1b-405-me-follow-1116.json.xz.

Source: the viewing Magic-Eater n1-b life-405 (Lv46, Angband 80F), its two stops
``stuck-prompt:ranged:magic-eater-device`` of 2026-11-16 05:36:49 and 05:36:56, copied
read-only from the viewing server (life-405/captures/<stop>/) to
C:/hengband-backups/pdca/captures/n1b-405-stuck-me-device-1116/<stop>/:

- state.jsonl.gz: the boards up to the stop (the last one is the decision's board);
- bot-decisions.jsonl.gz: the decisions up to the stop (the last one posted the key);
- control-at-stop.json.gz: the screen left open at the stop.

The absorbed device lists are not in the capture (the spectator frames had rolled to
life-406): the fixture keeps the earliest life-405 lists still kept,
C:/hengband-backups/pdca/captures/n1b-405-disintegrate-1116/first-frame.jsonl
(tests/extract_n1b_405_disintegrate_1116_fixture.py).

    python tests/extract_n1b_405_me_follow_1116_fixture.py <copy-dir> <first-frame.jsonl>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1b-405-me-follow-1116.json.xz"
STOPS = ("20261116-053649-stuck-prompt-ranged-magic-eater-device",
         "20261116-053656-stuck-prompt-ranged-magic-eater-device")


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    root, frame_path = Path(sys.argv[1]), Path(sys.argv[2])
    stops = {}
    for name in STOPS:
        decision = _rows(root / name / "bot-decisions.jsonl.gz")[-1]
        board = _rows(root / name / "state.jsonl.gz")[-1]
        assert board["turn"] == decision["turn"]
        with gzip.open(root / name / "control-at-stop.json.gz", "rt", encoding="utf-8") as stream:
            control = json.load(stream)
        stops[name] = {"board": board,
                       "decision": {key: decision[key] for key in
                                    ("decision_sequence", "turn", "reason", "key")},
                       "stop_screen": control["screen"]}
    frame = json.loads(frame_path.read_text(encoding="utf-8"))
    payload = {"stops": stops, "lists": frame["magic_eater_powers"],
               "lists_decision": frame["decision_sequence"]}
    OUTPUT.write_bytes(lzma.compress(json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        preset=9 | lzma.PRESET_EXTREME))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
