"""n1-a life-530 (2026-11-18 06:40, Yeek cave 1F) mining-abort recall wait.

The mining run sighted the ruled-out unique, latched the abort return
(_mining_unbeatable_unique_abort_key), read Word of Recall
(return:recall 'rg', message 「回りの大気が張りつめてきた...」 =
recall_player set word_recall) and then waited under the abort's name
(_mining_abort_exit_key: fundraise:abort-unbeatable-unique:wait-recall)
while player.recalling.  The game counts word_recall down once per
TURNS_PER_TICK (world-movement-processor.cpp execute_recall) from
randint0(21) + 15, i.e. up to 350 game turns; the 33 recorded waits covered
168 game turns from the read, so the recall had not yet fired when the cell loop guard
stopped the bot after 40 decisions.

Source bot-decisions.jsonl.gz SHA256:
7c7e39c86bfd23583ae62dd5a79ac90df244f600e95ac9716b30ff1f5fd6b5d3
(captures/20261118-064003-loop-detected; decisions 20100-20140, the
first one only the previous position of the guard's first board).
"""

from __future__ import annotations

from collections import deque
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hengbot.cli import (
    LOOP_WINDOW,
    STATIONARY_REASONS,
    _cell_loop_guard_applies,
    _is_looping,
)
from hengbot.model import Position
from hengbot.policy_constants import MINING_ABORT_REASON_PREFIX

FIXTURE = (
    Path(__file__).parent / "fixtures"
    / "mining-abort-wait-recall-loop-20261118.jsonl.gz"
)
WAIT = f"{MINING_ABORT_REASON_PREFIX}:wait-recall"


def _rows():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def _guard_stop_sequence(rows):
    recent = deque(maxlen=LOOP_WINDOW)
    previous = None
    for row in rows:
        position = Position(row["position"]["y"], row["position"]["x"])
        floor = row["floor"]
        snapshot = SimpleNamespace(
            in_town=False,
            inside_arena=False,
            floor_key=(floor["dungeon_id"], floor["level"], floor["quest_id"]),
            player=SimpleNamespace(position=position),
        )
        if _cell_loop_guard_applies(snapshot, row["reason"], previous):
            recent.append((snapshot.floor_key, position.y, position.x))
            if _is_looping(recent):
                return row["decision_sequence"]
        else:
            recent.clear()
        previous = position
    return None


class MiningAbortWaitRecallRecordedTest(unittest.TestCase):
    def test_fixture_is_the_recorded_stop(self):
        self.assertEqual(
            hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            "9ed499f23d4cdfdbd75928b04ea18fb482947fc012336ffe21ecb7a42e04dec5",
        )
        rows = _rows()
        self.assertEqual(len(rows), LOOP_WINDOW + 1)
        self.assertEqual(
            (rows[0]["decision_sequence"], rows[-1]["decision_sequence"]),
            (20100, 20140),
        )
        recall = [row["reason"] for row in rows].index("return:recall")
        self.assertEqual(rows[recall]["key"], "rg")
        # The read activated the recall (spells-world.cpp recall_player).
        self.assertIn(
            "回りの大気が張りつめてきた...", rows[recall + 1]["messages"]
        )
        self.assertEqual(
            {(row["reason"], row["key"]) for row in rows[recall + 1:]},
            {(WAIT, "5")},
        )
        self.assertEqual(len(rows) - recall - 1, 33)
        # 168 game turns from the read: inside the 150-350 game-turn countdown.
        self.assertEqual(rows[-1]["turn"] - rows[recall]["turn"], 168)

    def test_abort_recall_wait_clears_the_cell_guard(self):
        self.assertIn(WAIT, STATIONARY_REASONS)
        rows = _rows()
        self.assertIsNone(_guard_stop_sequence(rows))
        # Without the registration the exact live stop returns.
        with patch(
            "hengbot.cli.STATIONARY_REASONS", STATIONARY_REASONS - {WAIT}
        ):
            self.assertEqual(_guard_stop_sequence(rows), 20140)


if __name__ == "__main__":
    unittest.main()
