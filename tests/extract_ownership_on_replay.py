"""Freeze needed prefixes from copied captures; never read the live checkout.

Run manually with PYTHONPATH=src;tests. Extraction records defects, too; it
does not turn observed violations into allowed expectations. Test execution
uses only the committed manifest and the existing pinned checkpoints.
"""

import tests  # noqa: F401 -- runtime-file write guard
from contextlib import contextmanager
import gzip
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ownership_on_corpus import FIXTURES, MANIFEST, read_json, read_rows, run_window, sha256

BACKUPS = Path("C:/hengband-backups/state-logs")
ROOTS = (BACKUPS / "s33-phase2b-shadow-20261004", BACKUPS / "choke-hold-loop-20261005-0611")


@contextmanager
def isolated_directory():
    with TemporaryDirectory(prefix="ownership-on-") as raw:
        directory = Path(raw)
        with patch.dict(os.environ, {"HENGBOT_RUNTIME_DIR": raw, "HENGBOT_HOME_HISTORY_DIR": raw}):
            yield directory


def freeze(window):
    """Materialize only what the bounded replay actually consumes."""
    source_steps = window.get("steps")
    kept = []
    if source_steps is not None:
        def remember():
            for step in source_steps:
                kept.append(step)
                yield step
        window["steps"] = remember()
    with isolated_directory() as directory:
        result = run_window(window, directory)
    if source_steps is not None:
        window["steps"] = kept
    print(window["name"], result.rows_replayed, "divergence", result.first_divergence,
          "violations", len(result.violations), flush=True)
    return window


def boundary_window(path):
    boundary = read_json(path)
    if not boundary.get("recorded") or not boundary.get("input_rows"):
        return None
    stem = path.name.removesuffix(".boundaries.json")
    state = FIXTURES / (stem + ".gz" if stem.endswith(".jsonl") else stem + ".jsonl.gz")
    if not state.exists():
        return None
    fields = boundary.get("recorded_fields", ["key", "reason"])
    calibration = next((p.name for p in FIXTURES.glob(stem.removesuffix(".jsonl") + ".character-calibration.json")), None)
    if stem.startswith("town-approach"):
        calibration = "guardian-recall-pingpong-20260925.character-calibration.json"
    def steps():
        with gzip.open(state, "rt", encoding="utf-8") as stream:
            for index, (count, values) in enumerate(zip(boundary["input_rows"], boundary["recorded"])):
                recorded = values if isinstance(values, dict) else dict(zip(fields, values))
                inputs = [json.loads(next(stream)) for _ in range(count)]
                # Some older boundaries name keys as tuple elements only.
                yield {"row": index, "key": recorded["key"], "reason": recorded["reason"], "inputs": inputs}
    sources = {p.name: sha256(p) for p in (state, path)}
    if calibration:
        sources[calibration] = sha256(FIXTURES / calibration)
    first_recorded = boundary["recorded"][0]
    first_reason = (first_recorded["reason"] if isinstance(first_recorded, dict)
                    else dict(zip(fields, first_recorded))["reason"])
    initialization = ("process-start" if first_reason == "periodic:skill-exp-knowledge"
                      else "independent-restart-substrate (boundary starts mid-process)")
    return {"name": stem, "initialization": initialization, "prime": True,
            "calibration": calibration,
            "sources": sources, "steps": steps()}


def signature(row):
    player = row.get("player") or {}
    return row.get("turn"), player.get("y"), player.get("x"), (row.get("store") or {}).get("store_type")


def decision_signature(row):
    position = row.get("position") or {}
    return row.get("turn"), position.get("y"), position.get("x"), row.get("store_type")


def paired_substrates():
    """Include older seam pins as declared independent restart substrates.

    Do not pretend their reconstructed plans are serialized live checkpoints.
    Keep a single decision per incident; no subsequent effect is licensed by
    a chance command match on a cold restart.
    """
    names = ("town-owner-cluster-20260910.json.gz", "town-overflow-20261003.json.gz",
             "town-home-candidate-stall-20260927.json.gz", "s33-live-short-entrance-224.json.gz",
             "town-loot-store-20260926.jsonl.gz", "town-plan-exhausted-wander-20260923.jsonl.gz",
             "posted-effect-unobserved-20260923.jsonl.gz", "loot-choke-oscillation-20260923.jsonl.gz",
             "calibration-visit-blocked-loop-20260923.jsonl.gz", "newchar-town-wander-20260928.jsonl.gz")
    for name in names:
        path = FIXTURES / name
        data = read_rows(path) if ".jsonl" in name else read_json(path)
        if name.startswith("newchar-"):
            boards = [row["value"] for row in data if row["kind"] == "state"]
            paired = []
            for row in data:
                if row["kind"] != "decisions":
                    continue
                board = next((board for board in boards if signature(board) == decision_signature(row["value"])), None)
                if board:
                    paired.append({"board": board, "decision": row["value"]})
            data = paired
        if isinstance(data, dict):
            if "pins" in data:
                pins = [row for row in data["pins"] if row.get("turn") == data["board"].get("turn")]
                data = [{"board": data["board"], "decision": pins[-1]}] if pins else []
            else:
                data = [data]
        seen = set()
        for number, row in enumerate(data, 1):
            board = row.get("board") or row.get("snapshot") or row.get("state")
            decision = row.get("decision") or row.get("recorded")
            incident = row.get("capture", name)
            if not board or not decision or "key" not in decision or incident in seen:
                continue
            seen.add(incident)
            yield {"name": f"{name}:restart:{number}",
                   "initialization": "independent-restart-substrate (not original process state)", "prime": True,
                   "sources": {name: sha256(path)}, "steps": [{"row": number, "key": decision["key"],
                   "reason": decision["reason"], "inputs": [board]}]}


def shadow_audit():
    path = ROOTS[0] / "shadow-rows-live.jsonl"
    rows = read_rows(path)
    return {"source": str(path.relative_to(BACKUPS)), "sha256": sha256(path), "rows": len(rows),
            "stops": [{"source_line": number, "time": row.get("time"), "decision_sequence": row.get("decision_sequence"),
                       "would_stop": (row.get("s33_shadow") or {}).get("would_stop")}
                      for number, row in enumerate(rows, 1) if (row.get("s33_shadow") or {}).get("would_stop")]}


def choke_controls():
    """The choke capture is in the dungeon; include it as an ON control."""
    root = ROOTS[1]
    state = root / "state.jsonl.gz"
    for path in sorted(root.glob("*decisions*.gz")):
        decisions = read_rows(path)
        wanted = {decision_signature(row): (number, row) for number, row in enumerate(decisions, 1)
                  if "decision_sequence" in row and "key" in row}
        with gzip.open(state, "rt", encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                board = json.loads(line)
                matched = wanted.get(signature(board))
                if matched:
                    decision_line, decision = matched
                    yield {"name": root.name + "/" + path.name + ":dungeon-control",
                           "initialization": "independent-restart-substrate (dungeon control)", "prime": True,
                           "sources": {str(p.relative_to(BACKUPS)): sha256(p) for p in (path, state)},
                           "steps": [{"row": decision_line, "key": decision["key"], "reason": decision["reason"],
                                      "inputs": [board], "source_state_lines": [number, number]}]}
                    break
            else:
                print("Excluded choke rotation:", path.name, "no board retained in copied state tail", flush=True)


def focused_copied_ranges():
    """Retain the explicitly copied S3.3 town ranges as restart substrates."""
    root = ROOTS[0]
    for decision_name, state_name in (
        ("decisions-1301-1344.jsonl", "state-upto-1344.jsonl.gz"),
        ("decisions-1436-1447.jsonl", "state-upto-1447.jsonl.gz"),
    ):
        decision_path, state_path = root / decision_name, root / state_name
        decisions = read_rows(decision_path)
        wanted = {decision_signature(row): (number, row) for number, row in enumerate(decisions, 1)
                  if "key" in row and (row.get("floor") or {}).get("level") == 0}
        turns = {key[0] for key in wanted}
        with gzip.open(state_path, "rt", encoding="utf-8") as stream:
            for state_line, line in enumerate(stream, 1):
                # Most of these large state rows predate the small copied
                # range. Decode only candidate turns, preserving the full
                # original board when a strict position/store join succeeds.
                turn = re.search(r'"turn"\s*:\s*(\d+)', line)
                if turn is None or int(turn.group(1)) not in turns:
                    continue
                board = json.loads(line)
                matched = wanted.get(signature(board))
                if matched:
                    row, decision = matched
                    yield {"name": root.name + "/" + decision_name + ":restart",
                           "initialization": "independent-restart-substrate (not original process state)", "prime": True,
                           "sources": {str(p.relative_to(BACKUPS)): sha256(p) for p in (decision_path, state_path)},
                           "steps": [{"row": row, "key": decision["key"], "reason": decision["reason"],
                                      "inputs": [board], "source_state_lines": [state_line, state_line]}]}
                    break
            else:
                raise ValueError(f"no copied board joins the focused range {decision_name}")


def capture_window(decision_path, state_path):
    """Last complete process, joined backwards using the recorded drain counts.

    Tails lacking a session marker cannot reconstruct historical policy state.
    Their first town board is retained as a separately labelled, ONE decision
    restart substrate. It never authorizes any later historical board.
    """
    decisions = read_rows(decision_path)
    markers = [i for i, row in enumerate(decisions) if row.get("kind") == "session-start"]
    process = decisions[markers[-1] + 1:] if markers else decisions
    process = [row for row in process if "decision_sequence" in row and "key" in row]
    if not process or not any((row.get("floor") or {}).get("level") == 0 for row in process):
        return None, "no town decisions in retained process"
    state = read_rows(state_path)
    if not markers:
        decision = next(row for row in process if (row.get("floor") or {}).get("level") == 0)
        matches = [i for i, row in enumerate(state) if signature(row) == decision_signature(decision)]
        if not matches:
            return None, "town board absent from copied state tail"
        end = matches[-1]
        kept = [{"row": decisions.index(decision) + 1, "key": decision["key"], "reason": decision["reason"],
                 "inputs": [state[end]], "source_state_lines": [end + 1, end + 1]}]
        initialization = "independent-restart-substrate (not original process state)"
    else:
        cursor = len(state) - 1
        ends = []
        for index in range(len(process) - 1, -1, -1):
            wanted = decision_signature(process[index])
            while cursor >= 0 and signature(state[cursor]) != wanted:
                cursor -= 1
            if cursor < 0:
                return None, "process-start board not retained in copied state tail"
            ends.append(cursor)
            if index:
                cursor -= int((process[index - 1].get("timing") or {}).get("jsonl_drain_records") or 0)
        ends.reverse()
        first = ends[0] - int((process[0].get("timing") or {}).get("jsonl_drain_records") or 0)
        if first < 0:
            return None, "attach board absent from copied state tail"
        starts = [first] + [end + 1 for end in ends[:-1]]
        kept = [{"row": markers[-1] + 2 + i, "key": decision["key"], "reason": decision["reason"],
                 "inputs": state[start:end + 1], "source_state_lines": [start + 1, end + 1]}
                for i, (decision, start, end) in enumerate(zip(process, starts, ends))]
        initialization = "process-start"
    return {"name": decision_path.parent.name + "/" + decision_path.name,
            "initialization": initialization, "prime": True,
            "sources": {str(p.relative_to(BACKUPS)): sha256(p) for p in (decision_path, state_path)},
            "steps": iter(kept)}, None


def main():
    windows, exclusions = [], []
    # Inventory exactly the recorded files named by existing town/ownership pins.
    inventory = set()
    for path in Path(__file__).parent.glob("test_*.py"):
        if "town" in path.name or "ownership" in path.name:
            inventory.update(name for name in re.findall(r"[\w.-]+\.json(?:l)?(?:\.gz)?", path.read_text(encoding="utf-8"))
                             if (FIXTURES / name).exists())
    # Also include the complete boundary recordings used transitively by the
    # ownership trajectory pins (Home, travel, recall and equipment windows).
    for path in sorted(FIXTURES.glob("*boundaries.json")):
        if not path.name.startswith(("town-", "unaffordable-claim-tour", "overweight-home-", "home-withdraw-failed-", "morivant-", "entrance-travel-", "stuck-prompt-")):
            continue
        window = boundary_window(path)
        if window:
            windows.append(freeze(window))
    windows.extend(freeze(window) for window in paired_substrates())
    windows.extend(freeze(window) for window in choke_controls())
    windows.extend(freeze(window) for window in focused_copied_ranges())
    for name in ("town-restock-stall-hungry-checkpoints.jsonl.gz", "food-store-unreachable-checkpoints.jsonl.gz",
                 "recall-store-unreachable-checkpoints.jsonl.gz", "device-purchase-preempted-checkpoint.jsonl.gz"):
        path = FIXTURES / name
        for number, row in enumerate(read_rows(path), 1):
            windows.append(freeze({"name": f"{name}:{row['decision_index']}", "initialization": "exact-predecision-checkpoint",
                                   "checkpoint_source": name, "checkpoint_line": number,
                                   "sources": {name: sha256(path)}}))
    for root in ROOTS:
        for decision_path in sorted(root.glob("*decisions*.gz")):
            state_path = root / decision_path.name.replace("bot-decisions", "bot-state-fixed")
            if state_path == decision_path:
                state_path = root / "state.jsonl.gz"
            if not state_path.exists():
                exclusions.append({"source": decision_path.name, "reason": "no paired state file (overlapping decision-only copy)"})
                continue
            window, reason = capture_window(decision_path, state_path)
            if window:
                windows.append(freeze(window))
            else:
                exclusions.append({"source": decision_path.name, "reason": reason})
    represented = {name for window in windows for name in window["sources"]}
    excluded_existing = [{"source": name, "sha256": sha256(FIXTURES / name),
                          "reason": "no complete decision boundaries or exact predecision checkpoint; seam/telemetry/scenario pin only"}
                         for name in sorted(inventory - represented)]
    payload = {"format": 1, "inventory": sorted(inventory), "windows": windows, "copied_shadow_audit": shadow_audit(),
               "excluded_existing": excluded_existing, "excluded_captures": exclusions}
    MANIFEST.write_bytes(gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0))
    print("Frozen", len(windows), "windows;", MANIFEST.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
