"""Freeze rows used by capture-backed tests before recorder eviction."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _freeze_lines(source: Path, target: Path, predicate) -> None:
    raw_lines = source.read_bytes().splitlines(keepends=True)
    selected = [line for line in raw_lines if predicate(json.loads(line))]
    if not selected:
        raise RuntimeError(f"no matching rows in {source}")
    target.write_bytes(b"".join(selected))


def main() -> None:
    wanted = {
        "shop:approach",
        "store:entry-await-observation",
        "home:route-claim-unfulfilled",
    }
    _freeze_lines(
        ROOT / "incident-captures"
        / "20260913-221354-posting-contract-identical-repost-unobserved"
        / "decision-tail.jsonl",
        FIXTURES / "home-door-bounce-decisions.jsonl",
        lambda row: row.get("reason") in wanted,
    )
    for capture, target in (
        ("20260919-2334-prepare-choke-oscillation", "prepare-choke-snapshots.jsonl"),
        ("20260920-0025-choke-vs-loot-oscillation", "choke-vs-loot-snapshots.jsonl"),
    ):
        source = ROOT / "incident-captures" / capture / "snapshots.jsonl"
        (FIXTURES / target).write_bytes(source.read_bytes())


if __name__ == "__main__":
    main()
