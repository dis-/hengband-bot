"""Extract the boards for the 2026-10-31 D30 follow-ups (owner rules 1-3).

* n1-a life-440 (20261030-204457-loop-detected): entered Yeek cave 1F,
  status-threat:stairs straight back to town, then stuck:wander with
  descent_refusal descent-cooldown until the forced departure waited out.
* n1-a life-427 (20261030-083148-loop-detected): a committed forced
  departure lost its minimum in a town fight (HP, temporary status) and the
  repetition rungs waited until the named-block stop.
* n1-b life-256 (20261030-142009-loop-detected): a mana eater at Home with
  19 of 23 pack slots used.

Sources are the read-only viewing captures; only this tool reads them.  The
snapshot ring is a multi-member gzip tail, so decoding starts at the first
member header.
"""
import gzip
import hashlib
import io
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


ROOT = Path(r"C:\hengband-backups\pdca\captures\unfixed-24h-1031")
TARGET = Path(__file__).with_name("fixtures") / "town-followups-20261031.json.gz"
# case -> (capture, {role: ring row}, recorded decision sequences)
CASES = {
    "cooldown": ("n1-a/life-440/incident-captures/20261030-204457-loop-detected",
                 dict(home=3317, town=3429, dungeon=3430, arrival=3435), (83, 84)),
    "lost-departure": ("n1-a/life-427/incident-captures/20261030-083148-loop-detected",
                       dict(fight=2848, board=2849), (9204,)),
    "mana-home": ("n1-b/life-256/incident-captures/20261030-142009-loop-detected",
                  dict(home=244, outside=479, page=480), (10125,)),
}
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "inventory",
                   "descent_refusal", "procurement_requirements")


def ring(path):
    data = path.read_bytes()
    rows = []
    try:
        with gzip.open(io.BytesIO(data[data.find(b"\x1f\x8b\x08"):]), "rt",
                       encoding="utf-8") as stream:
            for line in stream:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except EOFError:
        pass  # The copied tail may end inside a member.
    return rows


def decisions(path, sequences):
    found = {}
    with path.open("rb") as stream:
        for raw in stream:
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue  # The bounded tail starts inside a record.
            if row.get("decision_sequence") in sequences and "reason" in row:
                found.setdefault(row["decision_sequence"], []).append(
                    {key: row.get(key) for key in DECISION_FIELDS})
    return found


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    cases = {}
    for name, (capture_name, roles, sequences) in CASES.items():
        capture = ROOT / capture_name
        ring_path = capture / "snapshots" / "snapshots-current.jsonl.gz"
        rows = ring(ring_path)
        picked = {role: rows[index] for role, index in roles.items()}
        ids = {m["race_id"] for row in picked.values()
               for field in ("visible_monsters", "detected_monsters")
               for m in row.get(field, [])}
        cases[name] = dict(
            id=capture_name,
            sources={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in (ring_path, capture / "decision-tail.jsonl")},
            rows=picked,
            monraces={str(k): asdict(races[k]) for k in ids if k in races},
            recorded=decisions(capture / "decision-tail.jsonl", set(sequences)),
        )
    with open(TARGET, "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
            stream.write(json.dumps(cases, ensure_ascii=False, default=sorted,
                                    separators=(",", ":")).encode("utf-8"))
    print(TARGET, TARGET.stat().st_size)
    for name, case in cases.items():
        print(name, {role: (row["type"], row["turn"]) for role, row in case["rows"].items()},
              {seq: [r["reason"] for r in rows] for seq, rows in case["recorded"].items()})


if __name__ == "__main__":
    main()
