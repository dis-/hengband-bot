"""Record or compare public HengbotPolicy decision streams."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from collections import deque
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MONRACE_DEFS = Path(
    r"C:\hengband\.worktrees\bot-json-output\lib\edit\MonraceDefinitions.jsonc"
)


def _rows(path: Path, *, tail: int | None = None) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    selected = deque(maxlen=tail) if tail else []
    with opener(path, "rt", encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                selected.append(json.loads(line))
    return list(selected)


def _decisions(
    rows: list[dict], knowledge: dict, scenario: str
) -> list[list[str]]:
    policy = HengbotPolicy()
    result = []
    for number, raw in enumerate(rows, 1):
        try:
            snapshot = parse_snapshot(raw, knowledge)
            result.append([policy.choose_key(snapshot), policy.last_reason])
        except Exception as exc:
            raise RuntimeError(
                f"{scenario} row {number} is unreplayable: {type(exc).__name__}: {exc}"
            ) from exc
    return result


def _synthetic_trajectory() -> list[list[str]]:
    # This is the evolving test world used by the golden-trajectory acceptance
    # test.  Each posted key is applied before the next snapshot is produced.
    from test_golden_trajectory import GoldenOpeningTrajectoryTest

    policy, world = GoldenOpeningTrajectoryTest().build()
    result = []
    for decision in range(1, 21):
        world.deliver_events(policy)
        key = policy.choose_key(world.snapshot(decision))
        result.append([key, policy.last_reason])
        confirm = getattr(policy, "confirm_key_posted", None)
        if confirm is not None:
            confirm(key)
        world.apply(key)
    distinct = {tuple(pair) for pair in result}
    if len(distinct) < 8:
        raise RuntimeError(
            "synthetic-town-trajectory-20 coverage collapsed: "
            f"expected at least 8 distinct pairs, got {len(distinct)}"
        )
    return result


def collect(data_root: Path, monrace_defs: Path) -> dict[str, list[list[str]]]:
    knowledge = load_monrace_knowledge(monrace_defs)
    oil_path = data_root / "tests/fixtures/incident-town-oil-stall-turn-712398.jsonl.gz"
    oil = [row for row in _rows(oil_path) if row.get("turn") == 712398][:1]
    loop = _rows(
        data_root
        / "tests/fixtures/incident-20260821-loop-capture-rows.jsonl.gz",
    )
    return {
        "incident-town-oil-stall-turn-712398": _decisions(
            oil, knowledge, "incident-town-oil-stall-turn-712398"
        ),
        "incident-20260821-201515-loop-detected": _decisions(
            loop, knowledge, "incident-20260821-201515-loop-detected"
        ),
        "synthetic-town-trajectory-20": _synthetic_trajectory(),
    }


def _summary(decisions: dict[str, list[list[str]]]) -> str:
    rows = sum(len(stream) for stream in decisions.values())
    distinct = len({tuple(pair) for stream in decisions.values() for pair in stream})
    return (
        f"COVERAGE: rows replayed={rows}, distinct pairs={distinct}, unreplayable=0, "
        "scenarios included=3 "
        "(oil-stall, 20260821-loop-capture, synthetic-town-trajectory), "
        "scenarios omitted=1 (equipment-abandon: decision log has no snapshot substrate)"
    )


def _first_difference(base: dict, target: dict) -> str:
    for scenario in sorted(set(base) | set(target)):
        if scenario not in base:
            return f"scenario {scenario!r} is absent from base"
        if scenario not in target:
            return f"scenario {scenario!r} is absent from target"
        for index, (left, right) in enumerate(
            zip(base[scenario], target[scenario]), 1
        ):
            if left != right:
                return f"{scenario} row {index}: base={left!r}, target={right!r}"
        if len(base[scenario]) != len(target[scenario]):
            return (
                f"{scenario} row {min(len(base[scenario]), len(target[scenario])) + 1}: "
                f"stream lengths differ (base={len(base[scenario])}, "
                f"target={len(target[scenario])})"
            )
    return "encoded streams differ"


def _materialize(ref: str, destination: Path) -> None:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", ref],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    archive_path = destination / "tree.tar"
    archive_path.write_bytes(archive)
    with tarfile.open(archive_path) as bundle:
        bundle.extractall(destination, filter="data")
    archive_path.unlink()


def _collect_from_tree(tree: Path, data_root: Path, monrace_defs: Path) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as output:
        output_path = Path(output.name)
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            (str(tree / "src"), str(tree / "tests"))
        )
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--collect-output",
                str(output_path),
                "--data-root",
                str(data_root),
                "--monrace-defs",
                str(monrace_defs),
            ],
            cwd=tree,
            env=env,
            check=True,
        )
        return json.loads(output_path.read_text(encoding="utf-8"))
    finally:
        output_path.unlink(missing_ok=True)


def _ref_comparison(base_ref: str, target_ref: str | None, args) -> int:
    with tempfile.TemporaryDirectory(prefix="decision-equivalence-") as temporary:
        temporary_root = Path(temporary)
        base_tree = temporary_root / "base"
        base_tree.mkdir()
        _materialize(base_ref, base_tree)
        if target_ref and Path(target_ref).is_dir():
            target_tree = Path(target_ref).resolve()
        elif target_ref:
            target_tree = temporary_root / "target"
            target_tree.mkdir()
            _materialize(target_ref, target_tree)
        else:
            target_tree = ROOT
        base = _collect_from_tree(base_tree, args.data_root, args.monrace_defs)
        target = _collect_from_tree(target_tree, args.data_root, args.monrace_defs)
    if base != target:
        print("DECISION EQUIVALENCE: FAIL")
        print("DIVERGENCE:", _first_difference(base, target))
        print(_summary(target))
        return 1
    print(_summary(target))
    print("DECISION EQUIVALENCE: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write-baseline", type=Path)
    group.add_argument("--baseline", type=Path)
    group.add_argument("--base-ref")
    group.add_argument("--collect-output", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--target-ref", help="git ref or throwaway tree; default is the working tree"
    )
    parser.add_argument("--data-root", type=Path, default=ROOT)
    parser.add_argument("--monrace-defs", type=Path, default=DEFAULT_MONRACE_DEFS)
    args = parser.parse_args()
    if not any((args.write_baseline, args.baseline, args.base_ref, args.collect_output)):
        parser.error("one of --write-baseline, --baseline, or --base-ref is required")
    if args.target_ref and not args.base_ref:
        parser.error("--target-ref requires --base-ref")
    if args.base_ref:
        return _ref_comparison(args.base_ref, args.target_ref, args)

    current = collect(args.data_root, args.monrace_defs)
    encoded = json.dumps(
        current, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if args.collect_output:
        args.collect_output.write_text(encoded + "\n", encoding="utf-8")
        return 0
    if args.write_baseline:
        args.write_baseline.write_text(encoded + "\n", encoding="utf-8")
        print("baseline written", args.write_baseline)
        print(_summary(current))
        return 0
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    if baseline != current:
        print("DECISION EQUIVALENCE: FAIL")
        print("DIVERGENCE:", _first_difference(baseline, current))
        print(_summary(current))
        return 1
    print(_summary(current))
    print("DECISION EQUIVALENCE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
