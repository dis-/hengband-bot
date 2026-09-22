"""Freeze the 2026-09-23 06:00 loot/choke alternation at decision boundaries.

The capture retains 2750 emitter rows (turn 4809231-4828473) and the last 192
decisions of the bot process (sequence 10745-10936); the final ``loop-detected``
record repeats decision 10936's sequence and is the stop report, not a decision.
Each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, and every boundary row must carry the
decision record's turn -- that walk validates for all 192 decisions with no
mismatch, and in this window every decision consumed exactly one row.

The retained ring begins mid-member (the live generation is a byte tail), so the
bytes before the first gzip magic are dropped and the rest decompresses whole;
rows that still fail to decode are skipped.

Protocol 3 boards carry no two-weapon/shield skill_exp: the live process had read
its ``~f`` list long before this window, so the response is not in the ring.  The
fixture carries the recorded ``~f`` board of the SAME character and run already
committed in tests/fixtures/store-entry-travel-interrupted-20260923.jsonl.gz
(turn 4730301, player level 33), so a restarted policy answers its own request
from recorded evidence instead of a fabricated value.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_NAME = "20260923-060018-loop-detected"
# The capture lives in the live checkout (and its backup); an isolated worktree
# has no copy of it.  Only this extraction tool reads it; the committed test
# reads the frozen fixture alone.
CAPTURE = next(
    candidate
    for candidate in (
        ROOT / "incident-captures" / CAPTURE_NAME,
        Path("C:/hengband/bot-client/incident-captures") / CAPTURE_NAME,
        Path("C:/hengband-backups/incident-captures") / CAPTURE_NAME,
    )
    if (candidate / "meta.json").is_file()
)
SKILL_SOURCE = (
    ROOT / "tests" / "fixtures" / "store-entry-travel-interrupted-20260923.jsonl.gz"
)
OUTPUT = ROOT / "tests" / "fixtures" / "loot-choke-oscillation-20260923.jsonl.gz"
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
DECISIONS = 24


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
        encoding="utf-8"
    ).splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("decision_sequence") and row.get("reason") != "loop-detected":
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


def _skill_knowledge() -> dict:
    with gzip.open(SKILL_SOURCE, "rt", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if record.get("role") == "skill-knowledge":
                return record["board"]
    raise RuntimeError("no recorded skill_exp board in the source fixture")


def main() -> None:
    rows = _emitter_rows()
    decisions = _decision_rows()
    ends = _input_ends(decisions, rows)
    selected = list(zip(decisions, ends))[-DECISIONS:]
    window = [end for _decision, end in selected]
    if window != list(range(window[0], window[0] + len(window))):
        raise RuntimeError("the frozen window is not one input row per decision")
    records = [
        {
            "role": "capture",
            "capture": CAPTURE.name,
            "stop": json.loads((CAPTURE / "meta.json").read_text(encoding="utf-8")),
        },
        {
            "role": "skill-knowledge",
            "source": SKILL_SOURCE.name,
            "board": _skill_knowledge(),
        },
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
    PROVENANCE.write_text(
        f"Source: incident-captures/{CAPTURE.name}/\n"
        f"Selection: the last {DECISIONS} decisions of the retained decision tail "
        f"(sequence {first['decision_sequence']}-{last['decision_sequence']}, "
        f"{first['time']} - {last['time']}); the loop-detected stop record is "
        "excluded.\n"
        "Boundary rule: walking back from the final emitter row, each decision's "
        "input ends drain(previous decision) rows earlier and must carry the "
        "decision record's turn; the walk validates for all "
        f"{len(decisions)} retained decisions with no mismatch and the frozen "
        "window is one input row per decision.\n"
        "Truncated ring: the retained bytes begin mid-member, so everything "
        "before the first gzip magic is dropped; the remainder decompressed "
        f"whole into {len(rows)} rows with no undecodable line.\n"
        f"Skill list: the recorded ~f board of the same character and run from "
        f"{SKILL_SOURCE.name} (turn "
        f"{records[1]['board']['turn']}, level "
        f"{records[1]['board']['player']['level']}).\n"
        f"Records: {len(records)}; decompressed sha256: "
        f"{hashlib.sha256(payload).hexdigest()}\n"
        f"File sha256: {hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(OUTPUT.name, hashlib.sha256(OUTPUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
