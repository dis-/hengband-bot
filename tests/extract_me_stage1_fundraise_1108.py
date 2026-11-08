"""Extract tests/fixtures/me-stage1-fundraise-20261108/.

Source: n1-b life-340, 2026-11-08 02:53:59 quest:blocked:me-staff
(``fundraise-limit:rumor-travel-recharge:57099``), the automatic incident
capture 20261108-025359-quest-blocked-me-staff, copied read-only from the
server to C:/hengband-backups/pdca/captures/n1b-life340-1108/.  The Lv8
Magic-Eater came back to the Outpost with 28,209 gold from the sixth
me-staff:fundraise:rumor-travel-recharge mining run; the first decision of
the visit (seq 6446, turn 488942) was the stop.

Written: the capture's town-arrival checkpoint (policy.pkl) and visit
journal, recompressed with xz, and the decision-tail rows of the sequence's
run starts, the runs' ascents and the stop (decisions.json).

    python tests/extract_me_stage1_fundraise_1108.py <incident-capture-dir>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "me-stage1-fundraise-20261108"
DECISION_FIELDS = ("decision_sequence", "time", "turn", "reason", "key")


def decision_rows(capture: Path) -> list[dict]:
    rows = []
    for line in (capture / "decision-tail.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # the tail's first line is cut
        reason = row.get("reason") or ""
        if "me-staff:" in reason or reason in {"quest:blocked:me-staff", "fundraise:ascend"}:
            rows.append({**{name: row.get(name) for name in DECISION_FIELDS},
                         "gold": row["player"]["gold"]})
    return rows


def main() -> None:
    capture = Path(sys.argv[1])
    visit = capture / "town-arrival"
    FIXTURE.mkdir(exist_ok=True)
    preset = 9 | lzma.PRESET_EXTREME
    (FIXTURE / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    (FIXTURE / "journal.jsonl.xz").write_bytes(
        lzma.compress(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()), preset=preset))
    rows = decision_rows(capture)
    assert rows[-1]["reason"] == "quest:blocked:me-staff"
    (FIXTURE / "decisions.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
