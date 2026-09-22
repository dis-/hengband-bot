"""Freeze the 23:09:45-23:09:47 entrance-travel retirement at recorded decision boundaries.

Live 2026-09-22 (protocol 3): decisions 20633..20636 are
``town:travel-entrance`` -> ``town:kill-mob-friendly`` ->
``town:travel-entrance`` -> ``town:blocked:owner-retired``.

The bot process's early decisions were lost to log rotation (the rotated
decision log begins at sequence 6185) and the live snapshot generation begins
at decision 17209, so no whole-lifetime replay exists for this incident.  The
fixture therefore keeps only the input rows of the four recorded decisions and
their recorded arbiter telemetry; the tests re-derive the arbiter's accounting
from those boards and reasons.

Sources are the preserved copies in the backup capture directory (copied after
the stop, bot held):
- ``snapshots-current-full-generation.jsonl.gz``: the live snapshot generation;
  the automatic capture's 16 MiB tail is its exact byte suffix.
- ``bot-decisions.jsonl-at-stop``: the decision log current at the stop.
- ``policy-state.json``: the capture's diagnostic policy view, which names the
  descent target the producer was travelling to.

Each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, walking back from the final emitter row;
every boundary row must carry the decision record's turn.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKUP = Path(
    "C:/hengband-backups/incident-captures/20260922-230947-town-blocked-owner-retired"
)
GENERATION = BACKUP / "snapshots-current-full-generation.jsonl.gz"
GENERATION_SHA256 = "02d774192369b472a37be3db75622ebf7605984b4584cdfd537a2de9b944b084"
DECISIONS = BACKUP / "bot-decisions.jsonl-at-stop"
DECISIONS_SHA256 = "22985b6064041837d679dad4b75aeacefb60f4806abc1d0ea341c0440fab8be3"
CAPTURE_TAIL = BACKUP / "snapshots" / "snapshots-current.jsonl.gz"
POLICY_STATE = BACKUP / "policy-state.json"
OUTPUT = ROOT / "tests" / "fixtures" / "entrance-travel-retired-20260922.jsonl.gz"
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
FIRST, LAST = 20633, 20636
TELEMETRY = (
    "producer_owner", "progress", "budget_remaining_estimate",
    "would_retire", "retirement_set",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _decisions() -> list[dict]:
    if _sha256(DECISIONS) != DECISIONS_SHA256:
        raise RuntimeError("decision log copy changed")
    rows = []
    for line in DECISIONS.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if FIRST - 1 <= (row.get("decision_sequence") or 0) <= LAST:
            rows.append(row)
    if [row["decision_sequence"] for row in rows] != list(range(FIRST - 1, LAST + 1)):
        raise RuntimeError("recorded decisions are not contiguous")
    return rows


def _rows() -> list[bytes]:
    raw = GENERATION.read_bytes()
    if hashlib.sha256(raw).hexdigest() != GENERATION_SHA256:
        raise RuntimeError("generation copy changed")
    tail = CAPTURE_TAIL.read_bytes()
    if raw[-len(tail):] != tail:
        raise RuntimeError("capture tail is not a suffix of the generation")
    return gzip.GzipFile(fileobj=io.BytesIO(raw)).read().splitlines(keepends=True)


def main() -> None:
    decisions = _decisions()
    lines = _rows()
    turns = [json.loads(line).get("turn") for line in lines]
    drains = [
        int((row.get("timing") or {}).get("jsonl_drain_records") or 0)
        for row in decisions
    ]
    ends = [len(lines) - 1]
    for index in range(len(decisions) - 1, 0, -1):
        end = ends[-1] - drains[index - 1]
        while turns[end] != decisions[index - 1]["turn"]:
            end -= 1
        ends.append(end)
    ends.reverse()
    for decision, end in zip(decisions, ends):
        if turns[end] != decision["turn"]:
            raise RuntimeError(f"turn mismatch at {decision['decision_sequence']}")
    selected = lines[ends[0] + 1 : ends[-1] + 1]
    counts = [ends[i] - ends[i - 1] for i in range(1, len(ends))]
    recorded = decisions[1:]
    state = json.loads(POLICY_STATE.read_text(encoding="utf-8"))
    goal = state["state"]["_descent_target_goal"]
    payload = b"".join(selected)
    with OUTPUT.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as zipped:
            zipped.write(payload)
    BOUNDARIES.write_text(
        json.dumps(
            {
                "decision_sequences": [row["decision_sequence"] for row in recorded],
                "input_rows": counts,
                "recorded": [[row["key"], row["reason"]] for row in recorded],
                "recorded_positions": [
                    [row["position"]["y"], row["position"]["x"]] for row in recorded
                ],
                "recorded_arbiter": [
                    {name: row["arbiter"].get(name) for name in TELEMETRY}
                    for row in recorded
                ],
                "descent_target_goal": goal,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    PROVENANCE.write_text(
        "Source: C:/hengband-backups capture 20260922-230947-town-blocked-owner-"
        "retired: snapshots-current-full-generation.jsonl.gz (sha256 "
        f"{GENERATION_SHA256}; the automatic capture's 16 MiB snapshot tail is its "
        "exact byte suffix), bot-decisions.jsonl-at-stop (sha256 "
        f"{DECISIONS_SHA256}), policy-state.json (_descent_target_goal {goal}).\n"
        f"Selection: the input rows of decisions {FIRST}..{LAST} (2026-09-22 "
        "23:09:45-23:09:47+09:00) and their recorded key, reason, position and "
        "arbiter telemetry.  The process's decisions before 6185 were lost to log "
        "rotation and the generation begins at decision 17209, so no lifetime "
        "replay exists.\n"
        "Boundary rule: walking back from the final emitter row, each decision's "
        "input ends drain(previous decision) rows earlier, moved back to the row "
        "carrying the decision record's turn.\n"
        f"Emitter rows: {len(selected)} (input rows {counts}); decompressed "
        f"sha256: {hashlib.sha256(payload).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
