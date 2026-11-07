"""Restore and decide the mid-visit checkpoints of tests/fixtures/town-stops-1107/.

The fixtures are written by tests/extract_town_stops_1107_fixtures.py (its
docstring names the sources).  ``restore`` gives the checkpointed policy with
its runtime files in an isolated scratch directory; ``decide`` delivers one
journal row's inputs and board and returns what ``choose_key`` answers, as
tests/replay_town_arrival.py does for an arrival.
"""
import tests  # noqa: F401  -- isolate runtime files before policy imports

import json
import lzma
import os
from pathlib import Path
from unittest import mock

from hengbot.cli import _consume_response_sequence
from hengbot.home_disposal import HOME_HISTORY_DIR_ENV
from hengbot.runtime_paths import RUNTIME_DIR_ENV
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import (
    POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from replay_town_arrival import adopt_calibration, restore as restore_visit

FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1107"


def journal(case: str) -> list[dict]:
    raw = lzma.decompress((FIXTURES / case / "journal.jsonl.xz").read_bytes())
    return [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]


def replay_facts(case: str) -> dict:
    return json.loads((FIXTURES / case / "replay.json").read_text(encoding="utf-8"))


def restore(case: str, scratch: Path):
    """The checkpointed policy, its runtime files under ``scratch``."""
    visit = scratch / "town-arrival"
    visit.mkdir()
    (visit / POLICY_FILE).write_bytes(lzma.decompress((FIXTURES / case / "policy.pkl.xz").read_bytes()))
    sidecars = json.loads(lzma.decompress((FIXTURES / case / "sidecars.json.xz").read_bytes()))
    (visit / SIDECAR_MANIFEST).write_text(json.dumps(sidecars["manifest"]), encoding="utf-8")
    (visit / SIDECAR_DIRECTORY).mkdir()
    for role, text in sidecars["files"].items():
        (visit / SIDECAR_DIRECTORY / role).write_bytes(text.encode("latin-1"))
    runtime = scratch / "runtime"
    runtime.mkdir()
    # The restored runtime files (the Home transaction history among them)
    # go under ``scratch``, not the test process's shared runtime directory,
    # where a later test's policy would load them.
    with mock.patch.dict(os.environ, {RUNTIME_DIR_ENV: str(runtime),
                                      HOME_HISTORY_DIR_ENV: str(runtime / "home-history")}):
        policy = restore_visit(visit, runtime)
    calibration = visit / SIDECAR_DIRECTORY / "_character_calibration_path"
    if calibration.is_file():
        adopt_calibration(policy, calibration, runtime)
    return policy


def board(policy, entry: dict, scratch: Path, transform=None):
    """Deliver ``entry``'s inputs and return its board (``transform``ed)."""
    inputs = [line + "\n" for line in entry["inputs"]]
    _consume_response_sequence(
        inputs, policy, lambda _key: True, policy._monrace_knowledge,
        parse_snapshots=False, knowledge_ledger_path=scratch / "knowledge.jsonl",
    )
    line = entry["line"] if entry["line"] is not None else entry["inputs"][-1]
    for name, value in entry["cli_latches"].items():
        setattr(policy, name, tuple(value) if isinstance(value, list) else value)
    policy.observe_store_screen(entry["store_screen_verified"])
    state = json.loads(line)
    if transform is not None:
        state = transform(state)
    return parse_snapshot(state, policy._monrace_knowledge)


def post(policy, key) -> None:
    """Acknowledge ``key`` as posted (the replay's acknowledgement)."""
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
