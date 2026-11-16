"""Extract tests/fixtures/n1c-214-resistance-1116.json.xz.

Source: the viewing Magic-Eater n1-c life-214 (Lv47, Angband 80F), its death of 2026-11-16
10:09:14 (stop ``exit-no-marker``), copied read-only from the viewing server
(life-214/captures/20261116-100912-exit-no-marker/) to
C:/hengband-backups/pdca/captures/n1c-deaths-1116/life-214/20261116-100912-exit-no-marker/:

- state.jsonl.gz: the boards up to the death;
- bot-decisions.jsonl.gz: the decisions up to the death.

The fixture keeps the four boards beside the 銀ライネル (turns 7275151, 7275157, 7275160,
7275165) with the decision posted on each.

    python tests/extract_n1c_214_resistance_1116_fixture.py <capture-dir>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1c-214-resistance-1116.json.xz"
TURNS = (7275151, 7275157, 7275160, 7275165)


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    root = Path(sys.argv[1])
    boards = {row["turn"]: row for row in _rows(root / "state.jsonl.gz")}
    decisions = {row["turn"]: row for row in _rows(root / "bot-decisions.jsonl.gz")}
    payload = {"boards": [
        {"board": boards[turn],
         "decision": {key: decisions[turn][key]
                      for key in ("decision_sequence", "turn", "reason", "key")}}
        for turn in TURNS]}
    OUTPUT.write_bytes(lzma.compress(json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        preset=9 | lzma.PRESET_EXTREME))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
