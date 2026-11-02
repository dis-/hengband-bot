"""Freeze the n1-a life-464 19:45:01 town:blocked:survival:depth_abilities boards.

Source: C:/hengband-backups/pdca/captures/hourly-2000-1102/
n1-a-20261102-194501-town-blocked-survival-depth-abilities (bot-ec1f68398);
the boards come from the incident snapshot tail (incident/
snapshots-current.jsonl.gz, a multi-member gzip read from its first member).
Decision 10885 took off 西方国のダガー (main hand, the only Free Action source),
10886 posted its Home deposit, Home answered 「我が家にはもう置く場所がない。」,
10888 abandoned the session and 10935 stopped with free_action missing for
the 23F departure.  Frozen: the skill row of turn 5253074, the Home boards
of 5253084 (before and after the takeoff, the refused deposit), the outside
board of 5253090, the Home list of 5253098, and decisions 10885-10888 /
10935 facts.  Only this tool reads the capture.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import zlib
from pathlib import Path


CAPTURE = Path("C:/hengband-backups/pdca/captures/hourly-2000-1102/"
               "n1-a-20261102-194501-town-blocked-survival-depth-abilities")
SNAPSHOTS = "incident/snapshots-current.jsonl.gz"
OUTPUT = Path(__file__).with_name("fixtures") / "deposit-failure-restore-1102.json.gz"
FACTS = ("decision_sequence", "turn", "reason", "key", "messages", "depth_safety")


def _tail_lines() -> list[str]:
    data = (CAPTURE / SNAPSHOTS).read_bytes()
    start, chunks = data.find(b"\x1f\x8b\x08"), []
    while 0 <= start < len(data):
        member = zlib.decompressobj(31)
        try:
            chunks.append(member.decompress(data[start:]))
        except zlib.error:
            break  # the capped tail cuts its last member
        if not member.unused_data:
            break
        start = len(data) - len(member.unused_data)
    return b"".join(chunks).decode("utf-8").splitlines()


def main() -> None:
    rows = []
    for line in _tail_lines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    def pick(kind, turn, category=None, store=None):
        return [r for r in rows if r["type"] == kind and r["turn"] == turn
                and (category is None or r["knowledge"]["category"] == category)
                and (store is None or (r.get("store") or {}).get("store_type") == store)]

    skill = pick("knowledge", 5253074, "skill_exp")[-1]
    home = pick("knowledge", 5253098, "home")[-1]
    in_home = pick("store", 5253084, store=7)
    assert len(in_home) == 3, len(in_home)
    outside = pick("player_turn", 5253090)[-1]
    decisions = []
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("decision_sequence") in (10885, 10886, 10887, 10888, 10935):
                fact = {key: row.get(key) for key in FACTS}
                fact["departure_failed"] = (row.get("departure_block") or {}).get("failed")
                decisions.append(fact)
    case = dict(
        sources={name: hashlib.sha256((CAPTURE / name).read_bytes()).hexdigest()
                 for name in (SNAPSHOTS, "bot-decisions.jsonl.gz")},
        skill=skill, home=home, before_takeoff=in_home[0], after_takeoff=in_home[1],
        deposit_refused=in_home[2], outside=outside, decisions=decisions)
    OUTPUT.write_bytes(gzip.compress(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0))
    print(OUTPUT, OUTPUT.stat().st_size, [d["reason"] for d in decisions])


if __name__ == "__main__":
    main()
