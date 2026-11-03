"""Extract tests/fixtures/mana-quest-hunger-20261103.json.gz.

Source: the n1-a life-471 incident capture of the restarted process
(2026-11-03 11:14:14, town:blocked:survival-mana-no-charges, Q2 final
patrol, build bot-e9361bf60).  Its snapshot ring ends with the board the
fresh process primed on, the ~f skill-list response its first decision
requested, and the same board decided again into the stop.

    python tests/extract_mana_quest_hunger_fixture.py <incident-capture-dir>
"""
import gzip
import json
import sys
import zlib
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "mana-quest-hunger-20261103.json.gz"


def records(ring: bytes) -> list[dict]:
    """Decode a multi-member gzip tail from its first member header."""
    position, text = ring.find(b"\x1f\x8b\x08"), b""
    while position != -1:
        member = zlib.decompressobj(16 + zlib.MAX_WBITS)
        text += member.decompress(ring[position:])
        rest = member.unused_data
        position = ring.find(b"\x1f\x8b\x08", len(ring) - len(rest)) if rest else -1
    rows = []
    for line in text.split(b"\n"):
        try:
            rows.append(json.loads(line))
        except ValueError:  # the cut first line of the tail
            continue
    return rows


def main() -> None:
    capture = Path(sys.argv[1])
    rows = records((capture / "snapshots" / "snapshots-current.jsonl.gz").read_bytes())
    knowledge = max(index for index, row in enumerate(rows) if row.get("type") == "knowledge")
    primed, response, board = rows[knowledge - 1], rows[knowledge], rows[knowledge + 1]
    assert primed["type"] == board["type"] == "player_turn"
    tail = (capture / "decision-tail.jsonl").read_bytes().splitlines()
    decision = json.loads(tail[-1])
    case = {
        "source": f"{capture.parent.parent.name}/{capture.name}",
        "primed": primed, "response": response, "board": board,
        "decision": {name: decision[name] for name in
                     ("decision_sequence", "turn", "key", "reason")},
    }
    with gzip.open(FIXTURE, "wt", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False)


if __name__ == "__main__":
    main()
