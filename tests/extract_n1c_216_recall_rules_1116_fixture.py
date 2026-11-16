"""Extract tests/fixtures/n1c-216-recall-rules-1116.json.xz.

Source: the viewing Magic-Eater n1-c life-216 (Lv39, 2026-11-16 16:41-19:21, about 75 recalls),
its boards copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1c-216-recall-rules-1116/:

- snapshots-2434200-2795420.jsonl.gz: the boards of turns 2434200-2434240, 2584900-2584960,
  2626240-2626300 and 2790000-2795420 out of
  ~/hengbot-soak/n1-c/life-216/jsonlog/snapshots/snapshots-20261116-{170733,180632,184606}-*.jsonl.gz;
- state-2819400-2820500.jsonl.gz and state-2915802-2948210.jsonl.gz: slices of
  ~/hengbot-soak/n1-c/life-216/state.jsonl taken during the investigation;
- decision-2820444.jsonl: the decision row of turn 2820444 (decision 97457) from
  ~/hengbot-soak/n1-c/life-216/jsonlog/bot-decisions.jsonl*.

The fixture keeps the player_turn boards of ``TURNS`` (the first copy of each) and the decision
row's threat_tiers telemetry.

    python tests/extract_n1c_216_recall_rules_1116_fixture.py [<source-dir>]
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1c-216-recall-rules-1116.json.xz"
SOURCE = Path("C:/hengband-backups/pdca/captures/n1c-216-recall-rules-1116")
FILES = ("snapshots-2434200-2795420.jsonl.gz", "state-2819400-2820500.jsonl.gz",
         "state-2915802-2948210.jsonl.gz")
TURNS = (
    # Teleport Away (sent_away_t1)
    2434210, 2434214, 2434219,          # 17:02 土の鬼 beside a グレーター・バルログ, then alone
    2584924, 2584928,                   # 18:01 白狼 (the 狼 of the name test)
    2626262, 2626269,                   # 18:05 グレーター・バルログ, T1 alone
    2820444, 2820448,                   # 18:47 見習レンジャー, held T1
    # summons (summon_response): the boards with a cast of three floor visits
    2793866, 2794036, 2795383,          # 18:38-18:39 three casts 15-19 cells away, recalled
    2918106, 2918127, 2918138,          # 19:08 casts between monsters, recalled
    2924850, 2925802, 2926706, 2926726,  # 19:10-19:11 casts at the player, recalled at 2926706
)


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    boards = {}
    for name in FILES:
        with gzip.open(root / name, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row.get("type") == "player_turn" and row["turn"] in TURNS:
                    boards.setdefault(row["turn"], row)
    missing = sorted(set(TURNS) - set(boards))
    if missing:
        raise SystemExit(f"missing boards {missing}")
    with open(root / "decision-2820444.jsonl", encoding="utf-8") as stream:
        decision = json.loads(stream.readline())
    payload = {
        "boards": [boards[turn] for turn in TURNS],
        "decisions": {str(decision["turn"]): {
            key: decision[key] for key in ("decision_sequence", "turn", "reason", "key",
                                           "threat_tiers")}},
    }
    OUTPUT.write_bytes(lzma.compress(json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        preset=9 | lzma.PRESET_EXTREME))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
