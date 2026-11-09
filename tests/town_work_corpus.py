"""The frozen town decision corpus the town work contract tests replay.

Windows of recorded town decisions (fixtures/ownership-on-replay-20261005.json.gz,
extracted 2026-10-05 for the retired ownership switch) replayed through the
public policy boundary: only causally valid prefixes, one window at a time.
"""

import base64
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import pickle

from hengbot.cli import _consume_response_sequence
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from dataclasses import dataclass

FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = FIXTURES / "ownership-on-replay-20261005.json.gz"


def read_json(path):
    with gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open(encoding="utf-8") as stream:
        return json.load(stream)


def read_rows(path):
    with gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def monraces():
    return load_monrace_knowledge(Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc"))


@lru_cache(maxsize=1)
def static_game_data():
    # Reuse the established loader once. Retain only immutable game data,
    # never its policy state, mutable histories or character calibration.
    from tests.support.recorded import _policy
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix="town-work-data-") as raw:
        template = _policy(Path(raw), monraces())
        return {
            "town_map": template._town_map,
            "town_maps": template._town_maps,
            "wilderness_map": template._wilderness_map,
            "dungeon_knowledge": template._dungeon_knowledge,
            "monrace_knowledge": monraces(),
            "damaging_terrain_ids": template._damaging_terrain_ids,
            "quest_knowledge": template._quest_knowledge,
            "quest_strategies": template._quest_strategies,
            "baseitem_costs": template._baseitem_costs,
        }


def new_policy(directory, calibration=None):
    from hengbot.home_disposal import HomeDisposalState
    arguments = {name: dict(value) if isinstance(value, dict) else value
                 for name, value in static_game_data().items()}
    policy = HengbotPolicy(
        **arguments,
        home_disposal_state=HomeDisposalState(
            directory / "home-withdraw-history.jsonc",
            directory / "home-disposal-decisions.jsonc",
            directory / "home-disposal-queue.json",
            directory / "events.jsonl",
        ),
    )
    policy._character_calibration_path = directory / "character-calibration.json"
    if calibration:
        policy._character_calibration_path.write_bytes((FIXTURES / calibration).read_bytes())
    return policy


def enable_live_switches(policy):
    policy._crossarea_fundraising_enforced = True
    policy._in_store_ops_enabled = True


def run_window(window, directory):
    if "checkpoint_source" in window:
        rows = read_rows(FIXTURES / window["checkpoint_source"])
        captured = rows[window["checkpoint_line"] - 1]
        policy = restore_checkpoint(HengbotPolicy, captured["predecision_policy_checkpoint_pickle_b64"])
        board = pickle.loads(base64.b64decode(captured["decision_snapshot_pickle_b64"]))
        recorded = {"row": captured["decision_index"], "key": captured["key"], "reason": captured["last_reason"]}
        decisions = [(recorded, lambda: board)]
    else:
        policy = new_policy(directory, window.get("calibration"))
        def inputs():
            for index, step in enumerate(window["steps"]):
                def supply(step=step, index=index):
                    _, snapshots = _consume_response_sequence(
                        [json.dumps(raw) + "\n" for raw in step["inputs"]],
                        policy, lambda _key: True, monraces(),
                        knowledge_ledger_path=directory / "knowledge.jsonl",
                    )
                    board = snapshots[-1]
                    if index == 0 and window.get("prime", False):
                        policy.prime(board)
                    # Timer events are external CLI inputs, not policy walls.
                    if step["reason"] == "periodic:game-save":
                        policy.request_game_save()
                    elif step["reason"] == "periodic:character-dump":
                        policy.request_character_dump()
                    return board
                yield step, supply
        decisions = inputs()
    enable_live_switches(policy)
    return replay_window(window["name"], policy, decisions)


@dataclass
class ReplayResult:
    window: str
    rows_replayed: int = 0
    matched_rows: int = 0
    town_rows: int = 0
    first_divergence: dict | None = None


def replay_window(name, policy, decisions):
    """Choose and acknowledge matching decisions only; stop at first difference.

    The caller supplies an iterator of (recorded decision, board supplier). A
    supplier is deliberately lazy: no response/knowledge/effect of the next
    historical command is delivered after a divergence.  Conservatively
    compare both key and reason; even a reason-only difference ends this
    window.  None and the empty key are distinct.
    """
    from hengbot.policy import staged_prompt_chain_matches

    result = ReplayResult(name)
    for recorded, board_supplier in decisions:
        board = board_supplier()
        key = policy.choose_key(board)
        result.rows_replayed += 1
        result.town_rows += bool(board.in_town)
        if (key, policy.last_reason) != (recorded["key"], recorded["reason"]):
            result.first_divergence = {
                "row": recorded["row"],
                "recorded": [recorded["key"], recorded["reason"]],
                "new": [key, policy.last_reason],
            }
            break
        result.matched_rows += 1
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
        if key is None:
            break
    return result
