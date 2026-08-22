"""Record or compare public HengbotPolicy decision streams."""

from __future__ import annotations

import argparse
import gzip
import json
from collections import deque
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT


def _rows(path: Path, *, tail: int | None = None) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    selected = deque(maxlen=tail) if tail else []
    with opener(path, "rt", encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                selected.append(json.loads(line))
    return list(selected)


def _decisions(rows: list[dict]) -> list[list[str]]:
    policy = HengbotPolicy()
    result = []
    for raw in rows:
        try:
            snapshot = parse_snapshot(raw, {})
            result.append([policy.choose_key(snapshot), policy.last_reason])
        except Exception as exc:
            result.append(["<unreplayable>", f"{type(exc).__name__}:{exc}"])
    return result


def collect() -> dict[str, object]:
    oil_path = DATA_ROOT / "tests/fixtures/incident-town-oil-stall-turn-712398.jsonl.gz"
    oil = [row for row in _rows(oil_path) if row.get("turn") == 712398][:1]
    loop = _rows(
        DATA_ROOT / "incident-captures/20260821-201515-loop-detected/snapshots/snapshots-current.jsonl.gz",
        tail=50,
    )
    equipment = _rows(
        DATA_ROOT / "jsonlog/incident-equipment-abandon-loop-20260822.jsonl", tail=1
    )
    return {
        "incident-town-oil-stall-turn-712398": _decisions(oil),
        "incident-20260821-201515-loop-detected": _decisions(loop),
        "incident-equipment-abandon-loop-20260822-derived": _decisions(equipment),
        "synthetic-town-trajectory-20": _decisions(oil * 20),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write-baseline", type=Path)
    group.add_argument("--baseline", type=Path)
    parser.add_argument("--data-root", type=Path, default=ROOT)
    args = parser.parse_args()
    global DATA_ROOT
    DATA_ROOT = args.data_root
    current = collect()
    encoded = json.dumps(
        current, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if args.write_baseline:
        args.write_baseline.write_text(encoded + "\n", encoding="utf-8")
        print("baseline written", args.write_baseline)
        return 0
    if encoded != args.baseline.read_text(encoding="utf-8").rstrip("\n"):
        print("DECISION EQUIVALENCE: FAIL")
        return 1
    for name, decisions in current.items():
        print(f"{name}: {len(decisions)} byte-identical decisions")
    print("DECISION EQUIVALENCE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
