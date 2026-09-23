"""Freeze the 2026-09-23 20:10 "read the recall on top of the drop" board.

The capture is the stop that followed the incident (the bot recalled to town
and stopped on a prompt there), so its retained decision tail and emitter ring
still hold the dungeon window: Forest 24F, decisions 5280-5386, turn
5169096-5171822.  Decision 5386 read Word of Recall while seven items lay on
the floor, three of them under and beside the player, no hostile visible and
``threat_prediction.total`` zero.

Each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, and every boundary row must carry the
decision record's turn; that walk validates for the whole retained tail.  The
frozen window keeps the END row of each decision, which is the board the policy
actually decided on (some decisions drained two rows, e.g. a redraw at the same
turn).

The retained ring begins mid-member (the live generation is a byte tail), so
the bytes before the first gzip magic are dropped and the rest decompresses
whole.  The ``~f`` skill list of this same run IS in the ring (turn 5160185),
so no board has to be borrowed from another fixture.

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_NAME = "20260923-201024-stuck-prompt"
CAPTURE = next(
    candidate
    for candidate in (
        ROOT / "incident-captures" / CAPTURE_NAME,
        Path("C:/hengband/bot-client/incident-captures") / CAPTURE_NAME,
        Path("C:/hengband-backups/incident-captures") / CAPTURE_NAME,
    )
    if (candidate / "meta.json").is_file()
)
OUTPUT = ROOT / "tests" / "fixtures" / "loot-before-recall-20260923.jsonl.gz"
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
FIRST = 5280  # first frozen decision
LAST = 5386  # the decision that read the recall on top of the drop


def _emitter_rows() -> list[dict]:
    raw = (CAPTURE / "snapshots" / "snapshots-current.jsonl.gz").read_bytes()
    offset = raw.find(b"\x1f\x8b\x08")
    if offset < 0:
        raise RuntimeError("capture contains no intact gzip member")
    decoded = gzip.GzipFile(fileobj=io.BytesIO(raw[offset:])).read()
    rows = []
    for line in decoded.splitlines():
        try:
            rows.append(json.loads(line))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return rows


def _decision_rows() -> list[dict]:
    rows = []
    for line in (CAPTURE / "decision-tail.jsonl").read_text(
        encoding="utf-8", errors="replace"
    ).splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("decision_sequence"):
            rows.append(row)
    return rows


def _input_ends(decisions: list[dict], rows: list[dict]) -> list[int]:
    """Walk back from the final row: the last decision's input is the last row."""
    drains = [
        int(row.get("timing", {}).get("jsonl_drain_records") or 0)
        for row in decisions
    ]
    ends = [len(rows) - 1]
    for index in range(len(decisions) - 1, 0, -1):
        end = max(0, ends[-1] - drains[index - 1])
        while end > 0 and rows[end].get("turn") != decisions[index - 1]["turn"]:
            end -= 1
        ends.append(end)
    ends.reverse()
    for decision, end in zip(decisions, ends):
        if rows[end].get("turn") != decision["turn"]:
            raise RuntimeError(
                f"turn mismatch at decision {decision['decision_sequence']}"
            )
    return ends


def _skill_knowledge(rows: list[dict]) -> dict:
    for row in rows:
        knowledge = row.get("knowledge")
        if isinstance(knowledge, dict) and knowledge.get("category") == "skill_exp":
            return row
    raise RuntimeError("no recorded skill_exp board in the retained ring")


def main() -> None:
    rows = _emitter_rows()
    decisions = _decision_rows()
    ends = _input_ends(decisions, rows)
    selected = [
        (decision, end)
        for decision, end in zip(decisions, ends)
        if FIRST <= decision["decision_sequence"] <= LAST
    ]
    sequences = [decision["decision_sequence"] for decision, _end in selected]
    if sequences != list(range(FIRST, LAST + 1)):
        raise RuntimeError("the frozen window is not one contiguous decision run")
    skill = _skill_knowledge(rows)
    records = [
        {
            "role": "capture",
            "capture": CAPTURE.name,
            "stop": json.loads((CAPTURE / "meta.json").read_text(encoding="utf-8")),
        },
        {"role": "skill-knowledge", "board": skill},
    ]
    records.extend(
        {"role": "decision-input", "decision": decision, "board": rows[end]}
        for decision, end in selected
    )
    payload = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    ).encode("utf-8")
    with OUTPUT.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as zipped:
            zipped.write(payload)
    first, last = selected[0][0], selected[-1][0]
    multi = [
        decision["decision_sequence"]
        for index, (decision, end) in enumerate(selected)
        if index and end - selected[index - 1][1] != 1
    ]
    PROVENANCE.write_text(
        f"Source: incident-captures/{CAPTURE.name}/\n"
        f"Selection: decisions {FIRST}-{LAST} of the retained decision tail "
        f"({first['time']} - {last['time']}), Forest 24F, turn "
        f"{first['turn']}-{last['turn']}; decision {LAST} is the recorded "
        "return:recall 'rg' read on top of the unique's drop.\n"
        "Boundary rule: walking back from the final emitter row, each "
        "decision's input ends drain(previous decision) rows earlier and must "
        "carry the decision record's turn; the walk validates for all "
        f"{len(decisions)} retained decisions with no mismatch.  The frozen "
        "board of each decision is that END row; decisions whose input drained "
        f"more than one row: {multi}.\n"
        "Truncated ring: the retained bytes begin mid-member, so everything "
        "before the first gzip magic is dropped; the remainder decompressed "
        f"whole into {len(rows)} rows with no undecodable line.\n"
        "Skill list: the recorded ~f skill_exp board of this same run, turn "
        f"{skill['turn']}, player level {skill['player']['level']}.\n"
        f"Records: {len(records)}; decompressed sha256: "
        f"{hashlib.sha256(payload).hexdigest()}\n"
        f"File sha256: {hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(OUTPUT.name, hashlib.sha256(OUTPUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
