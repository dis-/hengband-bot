"""Replay a town stop from an incident capture's town-arrival checkpoint.

An incident capture written since 2026-11-03 holds ``town-arrival/``
(hengbot.town_arrival_checkpoint): the policy pickled just before the first
decision of the town visit, the visit's journal (per decision: the response
lines delivered since the previous decision, the CLI timer latches, the
store-screen verification, the board, and what choose_key returned) and the
decision-log rows from the arrival on.  ``replay`` restores the policy and
decides every journalled board through the public ``choose_key``, comparing
key and reason with the journal (town_work_corpus.replay_window: it stops at
the first difference and acknowledges each matching key as posted).

    PYTHONPATH="src;tests;." python tests/replay_town_arrival.py <incident-capture-dir>

A journal that reached its cap stopped there (``journal-truncated.json``):
its rows still replay, and ``journal_truncated`` names the first decision
left out, so the stop itself is not among the replayed rows.

Not journalled: a key the executor refused and re-chose on the same board
(cli refuse_key_posting), and the CLI's own key rewrites (validate_read_key,
owner retirement) - compare the decision-log rows for those.
"""
import tests  # noqa: F401  -- isolate runtime files before policy imports

import argparse
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.runtime_paths import configured_home_history_dir, configured_runtime_dir
from hengbot.town_arrival_checkpoint import (
    DIRECTORY, JOURNAL_FILE, POLICY_FILE, TRUNCATED_FILE, restore_runtime_files,
)
from town_work_corpus import replay_window


def journal(visit: Path) -> list[dict]:
    with gzip.open(visit / JOURNAL_FILE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def restore(visit: Path, scratch: Path | None = None) -> HengbotPolicy:
    """The arrival policy, reading the runtime files it read at the arrival.

    With ``scratch``, the character dump (not a runtime-directory file) is
    re-pointed there, and every captured runtime file is written to the
    restored policy's isolated locations.
    """
    policy = restore_checkpoint_bytes(HengbotPolicy, (visit / POLICY_FILE).read_bytes())
    if scratch is not None:
        if policy._character_dump_path is not None:
            policy._character_dump_path = scratch / Path(policy._character_dump_path).name
        roots = tuple(root for root in (configured_runtime_dir(),
                                        configured_home_history_dir(), scratch)
                      if root is not None)
        restore_runtime_files(policy, visit, roots)
    return policy


def decisions(policy, visit: Path, scratch: Path):
    """(recorded decision, board supplier) pairs for ``replay_window``."""
    for index, entry in enumerate(journal(visit)):
        def supply(entry=entry):
            inputs = [line + "\n" for line in entry["inputs"]]
            _consume_response_sequence(
                inputs, policy, lambda _key: True, policy._monrace_knowledge,
                parse_snapshots=False,
                knowledge_ledger_path=scratch / "knowledge.jsonl",
            )
            line = entry["line"] if entry["line"] is not None else entry["inputs"][-1]
            for name, value in entry["cli_latches"].items():
                setattr(policy, name, tuple(value) if isinstance(value, list) else value)
            policy.observe_store_screen(entry["store_screen_verified"])
            return parse_snapshot(json.loads(line), policy._monrace_knowledge)
        yield {"row": index, "key": entry["key"], "reason": entry["reason"]}, supply


def truncation(visit: Path) -> dict | None:
    """Where a journal that reached its cap stopped, or None."""
    path = visit / TRUNCATED_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def replay(capture: Path):
    """Restore the capture's arrival policy and replay its visit."""
    visit = capture / DIRECTORY
    with TemporaryDirectory(prefix="town-arrival-replay-") as raw:
        policy = restore(visit, Path(raw))
        result = replay_window(capture.name, policy, decisions(policy, visit, Path(raw)))
    result.journal_truncated = truncation(visit)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("capture", type=Path, help="incident-captures/<stamp>-<kind>")
    result = replay(parser.parse_args().capture)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
