"""Extract the 2026-10-30 D30 Home-withdraw loops (town pack budget).

Each case is the Home page on which the loop began (the first
home:queue-* decision of the loop), the outside board just before it (the
Home page export carries no grid map), the Home catalogue the policy held
(the preceding ~9 answer, or the open page when the capture has none) and
the town errand plan the capture's policy-state recorded.

Sources are the read-only viewing captures under
C:\\hengband-backups\\pdca\\captures\\unfixed-24h-1031; only this tool reads
them.  The snapshot ring is a multi-member gzip tail, so decoding starts at
the first member header.
"""
import gzip
import hashlib
import io
import json
from pathlib import Path


ROOT = Path(r"C:\hengband-backups\pdca\captures\unfixed-24h-1031")
TARGET = Path(__file__).with_name("fixtures") / "town-withdraw-pack-budget-20261030.json.gz"
# (case, capture, Home knowledge row or None, Home page row, recorded decision)
CASES = (
    ("n1-a/life-420", "20261030-023711-loop-detected", 2004, 2007, 21573),
    ("n1-b/life-252", "20261030-080919-loop-detected", None, 2118, 1735),
    ("n1-a/life-445", "20261030-225135-loop-detected", 2794, 2899, 4385),
)


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


def decision(path, sequence):
    found = None
    with path.open("rb") as stream:
        for raw in stream:
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue  # The bounded tail starts inside a record.
            if row.get("decision_sequence") == sequence and "reason" in row:
                found = row
    return found


def main():
    cases = []
    for life, name, knowledge_index, page_index, sequence in CASES:
        capture = ROOT / life / "incident-captures" / name
        ring_path = capture / "snapshots" / "snapshots-current.jsonl.gz"
        rows = ring(ring_path)
        page = rows[page_index]
        assert page["type"] == "store" and page["store"]["store_type"] == 7
        outside = next(row for row in reversed(rows[:page_index])
                       if row["type"] == "player_turn")
        knowledge = rows[knowledge_index] if knowledge_index is not None else None
        if knowledge is not None:
            assert knowledge["type"] == "knowledge"
            assert knowledge["knowledge"]["category"] == "home"
        state = json.loads((capture / "policy-state.json").read_text(encoding="utf-8"))
        recorded = decision(capture / "decision-tail.jsonl", sequence)
        assert recorded["turn"] == page["turn"], (recorded["turn"], page["turn"])
        meta = json.loads((capture / "meta.json").read_text(encoding="utf-8"))
        cases.append(dict(
            id=f"{life}/{name}",
            sources={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in (ring_path, capture / "policy-state.json",
                                  capture / "decision-tail.jsonl")},
            page=page,
            outside=outside,
            knowledge=knowledge,
            plan=state["state"]["_town_errand_plan"],
            pending=dict(item=state["state"]["_home_pending_item"],
                         quantity=state["state"]["_home_pending_quantity"]),
            fundraising_mode=state["modes_and_latches"]["_fundraising_mode"],
            recorded=dict(
                decision_sequence=recorded["decision_sequence"], turn=recorded["turn"],
                reason=recorded["reason"], key=recorded["key"],
                inventory=recorded["inventory"], last_reasons=meta["last_reasons"],
            ),
        ))
    with open(TARGET, "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
            stream.write(json.dumps(cases, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8"))
    print(TARGET, TARGET.stat().st_size)
    for case in cases:
        print(case["id"], case["recorded"]["reason"], case["recorded"]["inventory"])


if __name__ == "__main__":
    main()
