"""Extract viewing-bot town boards for the town work observer check (D39).

The n1-c Magic-Eater town decisions of 2026-10-30 that the slow-decision
sampler caught (fixedquest:claim:approach, quest:enter:approach and the
town approach walks) took 0.2-1 s, about half of it in the town_work
profile hook. Each case keeps the recorded board of one such decision, the
knowledge rows observed before it and the monster races it shows. Policy
state beyond that is not reconstructed: the check compares two observers
on the same board, not the recorded key.
"""
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


ROOT = Path(r"C:\hengband-backups\pdca\captures")
TARGET = Path(__file__).with_name("fixtures") / "town-work-observer-20261031.json.gz"
# (capture, recorded reason): the first decision with that reason whose board
# is in the capture's snapshot ring.
CASES = (
    ("n1c-1030-2100/life-035/incident-captures/20261030-204653-town-blocked-owner-retired-burst",
     "fixedquest:claim:approach"),
    ("n1c-1030-2100/life-035/incident-captures/20261030-204653-town-blocked-owner-retired-burst",
     "quest:enter:approach"),
    ("n1c-1030-2230/life-042/incident-captures/20261030-221916-no-key-exhausted",
     "town:kill-mob-approach"),
    ("n1c-1030-2230/life-042/incident-captures/20261030-221916-no-key-exhausted",
     "fixedquest:reward-approach"),
)


def rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def decisions(path):
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            found.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # The bounded tail starts in the middle of a JSON record.
    return found


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    cases = []
    for name, reason in CASES:
        capture = ROOT / name
        ring = capture / "snapshots" / "snapshots-current.jsonl.gz"
        tail_path = capture / "decision-tail.jsonl"
        observations = rows(ring)
        boards = {row["turn"]: index for index, row in enumerate(observations)
                  if row["type"] == "player_turn"}
        recorded = next(d for d in decisions(tail_path)
                        if (d.get("reason") or "").startswith(reason) and d.get("turn") in boards)
        start = boards[recorded["turn"]]
        board = observations[start]
        ids = {m["race_id"] for field in ("visible_monsters", "detected_monsters")
               for m in board.get(field, [])}
        cases.append(dict(
            id=f"{name.split('/')[1]}/{reason}",
            sources={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (ring, tail_path)},
            snapshot=board,
            knowledge=[row for row in observations[:start] if row["type"] == "knowledge"],
            monraces={str(k): asdict(races[k]) for k in ids if k in races},
            state={"modes_and_latches": {}},
            recorded=dict(sequence=recorded.get("decision_sequence"), turn=recorded["turn"],
                          reason=recorded["reason"], key=recorded.get("key"),
                          choose_key_ms=(recorded.get("timing") or {}).get("choose_key_ms")),
        ))
    with gzip.open(TARGET, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(cases, stream, ensure_ascii=False, separators=(",", ":"), default=sorted)
    print(TARGET, TARGET.stat().st_size)
    for case in cases:
        print(case["id"], case["recorded"])


if __name__ == "__main__":
    main()
