"""Captured Yeek Cave return wander and its bounded Recall escape."""

import tests  # noqa: F401
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.model import (
    SV_SCROLL_WORD_OF_RECALL,
    TVAL_SCROLL,
    parse_snapshot,
)
from hengbot.policy import HengbotPolicy, READ_KEY, UP_STAIRS_KEY
from hengbot.policy_constants import SEARCH_LIMIT, STUCK_ESCAPE_LIMIT
from policy_fixtures import item

FIXTURE = Path(__file__).parent / "fixtures/return-wander-20261016.jsonl.gz"


def captured_rows():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def replay_captured_wander(record, snapshot=None):
    """Replay the public policy with the recorded return owner/search state."""
    snapshot = snapshot or parse_snapshot(record["board"], {})
    policy = HengbotPolicy()
    policy.prime(snapshot)
    policy._returning_to_town = True
    policy._last_return_trigger = record["decision"]["last_return_trigger"]
    policy._build_grid_index(snapshot)
    # DECLARED REPLAY STATE: the captured return:wander decision proves that
    # wall-search budgets and frontier exploration had already been exhausted;
    # those per-process counters are not part of a protocol board.
    for position in snapshot.grids:
        policy._search_counts[(position.y, position.x)] = SEARCH_LIMIT
        policy._wall_search_counts[(position.y, position.x)] = SEARCH_LIMIT
    with (
        patch.object(policy, "_skill_exp_request_key", return_value=None),
        patch.object(policy, "_explore_step", return_value=None),
        patch.object(policy, "_is_oscillating", return_value=False),
    ):
        key = policy.choose_key(snapshot)
    return policy, key


class ReturnWanderRecallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = captured_rows()

    def test_captured_boards_replay_return_wander_without_recall(self):
        self.assertEqual(len(self.records), 3)
        for record in self.records:
            with self.subTest(capture=record["capture"]):
                decision = record["decision"]
                self.assertEqual(decision["reason"], "return:wander")
                self.assertEqual(decision["last_return_trigger"], "escape-kit-empty")
                self.assertEqual(decision["map_memory"]["up_stairs"], [])
                self.assertEqual(
                    (
                        record["board"]["floor"]["dungeon_id"],
                        record["board"]["floor"]["level"],
                        record["board"]["floor"]["quest_id"],
                    ),
                    (2, 2, 0),
                )
                policy, _key = replay_captured_wander(record)
                self.assertIsNone(policy._find_recall_scroll(
                    parse_snapshot(record["board"], {})
                ))
                self.assertEqual(policy.last_reason, "return:wander")

    def test_stuck_bound_reads_constructed_readable_recall(self):
        record = self.records[0]
        snapshot = parse_snapshot(record["board"], {})
        # DECLARED CONSTRUCTED: add one carried, readable Word of Recall scroll
        # to the exact captured board; the three supplied captures carry none.
        recall = item(
            "p", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
            name="帰還の詔の巻物",
        )
        snapshot = replace(snapshot, inventory=(*snapshot.inventory, recall))
        policy = HengbotPolicy()
        policy.prime(snapshot)
        policy._returning_to_town = True
        policy._last_return_trigger = record["decision"]["last_return_trigger"]
        policy.last_reason = "return:wander"
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1

        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            key = policy.choose_key(snapshot)

        self.assertEqual(policy.last_reason, "stuck:recall-escape")
        self.assertEqual(key, READ_KEY + recall.slot)
        self.assertEqual(policy._stuck_escape_streak, 0)

    def test_known_reachable_upstairs_still_takes_stairs(self):
        record = self.records[0]
        snapshot = parse_snapshot(record["board"], {})
        # DECLARED CONSTRUCTED: mark the current captured tile as a known stair
        # to pin the existing immediate-ascend rung.
        here = snapshot.grid_at(snapshot.player.position)
        snapshot = replace(
            snapshot,
            grids={
                **snapshot.grids,
                snapshot.player.position: replace(here, has_up_stairs=True),
            },
        )
        policy = HengbotPolicy()
        policy.prime(snapshot)
        policy._returning_to_town = True
        policy._last_return_trigger = record["decision"]["last_return_trigger"]
        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            key = policy.choose_key(snapshot)

        self.assertEqual((key, policy.last_reason), (UP_STAIRS_KEY, "return:ascend"))

    def test_blind_or_confused_return_does_not_read_recall(self):
        record = self.records[0]
        for status in ("blind", "confused"):
            with self.subTest(status=status):
                snapshot = parse_snapshot(record["board"], {})
                # DECLARED CONSTRUCTED: apply the status to the captured board
                # while keeping its readable Recall scroll and exhausted return.
                recall = item(
                    "p", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
                    name="帰還の詔の巻物",
                )
                snapshot = replace(
                    snapshot,
                    inventory=(*snapshot.inventory, recall),
                    player=replace(snapshot.player, **{status: True}),
                )
                policy = HengbotPolicy()
                policy.prime(snapshot)
                policy._returning_to_town = True
                policy._last_return_trigger = record["decision"]["last_return_trigger"]
                policy.last_reason = "return:wander"
                policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
                with patch.object(
                    policy, "_skill_exp_request_key", return_value=None
                ):
                    key = policy.choose_key(snapshot)

                self.assertNotEqual(policy.last_reason, "stuck:recall-escape")
                self.assertFalse(key.startswith(READ_KEY))


if __name__ == "__main__":
    unittest.main()
