"""The stops of n1-a lives 509 and 510 (2026-11-11, build bot-69967a2e2).

Recorded: each capture's town-arrival checkpoint, town journal and sidecars and,
for the two floor stops, the quest floor's boards from the snapshot ring
(tests/extract_n1a_510_quest_stops_1111_fixture.py).  Every board goes through the
public ``choose_key`` on the one restored policy, so what the deciding state holds
was made by the real producers from the recorded boards.

Q34 (life-510, 11:04): the last volley at the second death sword left two torches
rolled onto the approved stand (9,9) and none carried; the planned throw had
nothing to throw and the stand stopped as quest:blocked:fixed-target-not-visible
beside them.

Q2 Tower trip (life-510, 11:36 and 11:45): Telmora had never been visited
(visited_town_ids [0, 2]), so the inn's list (tele_town, spells-world.cpp) had no
'b': the onward '1mb' changed nothing, step-off and back until no-progress:onward,
after paying the Tower's recharge.

Q18 (life-509, 11:03): the escape episode's first board read its haste baseline on
that board, so the 加速(+10) the plan's dose had given did not count and the last
Speed potion went down instead of the Recall the ladder had chosen.

DECLARED CONSTRUCTED replies are named where they appear; each is the one game
reply the pin needs after the recorded boards end.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import base64
import copy
from dataclasses import replace
import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import q2_tower_recharge
from hengbot.model import TVAL_LITE, parse_snapshot
from hengbot.policy_constants import TOWN_TELEPORT_COST
from hengbot.policy_quest import QUEST_STAND_TORCH_PICKUP_REASON
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from town_work_corpus import replay_window

FIXTURES = Path(__file__).with_name("fixtures") / "n1a-510-quest-stops-1111"
TELMORA = 1
RECORDED_STOP = "quest:blocked:fixed-target-not-visible"
ONWARD_REASON = q2_tower_recharge.REASON + "return-telmora-unlisted"


class N1a510QuestStopsRecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self, stop):
        """The stop's arrival policy, its journal rows and its board suppliers."""
        self.loads = getattr(self, "loads", 0) + 1
        root = self.scratch / f"{stop}-{self.loads}"
        visit = root / "town-arrival"
        (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
        fixture = FIXTURES / stop
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((fixture / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((fixture / "journal.jsonl.xz").read_bytes())))
        sidecars = json.loads(lzma.decompress((fixture / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(
            json.dumps(sidecars["manifest"], ensure_ascii=False), encoding="utf-8")
        for role, data in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(base64.b64decode(data))
        runtime = root / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        calibration = visit / SIDECAR_DIRECTORY / "_character_calibration_path"
        if calibration.exists():
            adopt_calibration(policy, calibration, runtime)
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    @staticmethod
    def floor(stop):
        text = lzma.decompress((FIXTURES / stop / "floor.jsonl.xz").read_bytes()).decode("utf-8")
        return [json.loads(line) for line in text.splitlines() if line]

    def replay_town(self, name, policy, steps):
        result = replay_window(name, policy, iter(steps))
        self.assertIsNone(result.first_divergence)
        self.assertEqual(result.matched_rows, len(steps))

    @staticmethod
    def board(policy, raw):
        return parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)

    def drive_floor(self, policy, rows, *, until_turn):
        """Decide the recorded floor boards before ``until_turn`` on this policy."""
        for raw in rows:
            if raw["type"] == "knowledge":
                policy.consume_skill_knowledge(raw)
                continue
            if raw["turn"] >= until_turn:
                return raw
            key = policy.choose_key(self.board(policy, raw))
            if key:
                policy.confirm_key_posted(key)
        self.fail(f"no recorded board at or after turn {until_turn}")

    # Q34: the throwing stand's own torches ------------------------------------

    def q34_at_the_stop(self):
        policy, _, steps = self.load("q34")
        self.replay_town("q34", policy, steps)
        rows = self.floor("q34")
        raw = self.drive_floor(policy, rows, until_turn=76892)
        return policy, raw, rows

    def test_q34_takes_back_the_torches_on_its_stand(self):
        policy, raw, _ = self.q34_at_the_stop()
        board = self.board(policy, raw)
        self.assertFalse(any(item.is_torch for item in board.inventory))
        here = board.grid_at(board.player.position)
        self.assertIn(TVAL_LITE, here.object_tvals)

        key = policy.choose_key(board)

        self.assertEqual((key, policy.last_reason), ("g", QUEST_STAND_TORCH_PICKUP_REASON))
        self.assertNotEqual(policy.last_reason, RECORDED_STOP)

    def test_q34_throws_again_once_the_torches_are_carried(self):
        policy, raw, rows = self.q34_at_the_stop()
        key = policy.choose_key(self.board(policy, raw))
        self.assertEqual(key, "g")
        policy.confirm_key_posted(key)
        # DECLARED CONSTRUCTED: the reply to 'g' -- the stand's two torches in the
        # pack.  The item row is the recorded torch of the board before the last
        # throw, its count the pile's two.
        carried = next(item for row in reversed(rows) if row["type"] == "player_turn"
                       for item in row["inventory"] if item["tval"] == TVAL_LITE)
        after = copy.deepcopy(raw)
        after["turn"] += 10
        after["messages"] = []
        after["inventory"].append(dict(carried, count=2, slot="d"))

        key = policy.choose_key(self.board(policy, after))

        self.assertEqual(policy.last_reason, "quest-strategy:throw-torch")
        self.assertTrue(key.startswith("v") and key.endswith("2"), key)

    def test_q34_a_pickup_that_changed_nothing_is_not_repeated(self):
        policy, raw, _ = self.q34_at_the_stop()
        key = policy.choose_key(self.board(policy, raw))
        self.assertEqual(key, "g")
        policy.confirm_key_posted(key)
        # DECLARED CONSTRUCTED: the same pile on the next board (nothing taken).
        after = copy.deepcopy(raw)
        after["turn"] += 10
        after["messages"] = []

        key = policy.choose_key(self.board(policy, after))

        self.assertNotEqual(policy.last_reason, QUEST_STAND_TORCH_PICKUP_REASON)
        self.assertEqual(policy.last_reason, RECORDED_STOP)

    # Q18: the haste already on when the escape starts --------------------------

    def q18_at_the_escape(self):
        policy, _, steps = self.load("death-509")
        self.replay_town("death-509", policy, steps)
        rows = self.floor("death-509")
        raw = self.drive_floor(policy, rows, until_turn=1277422)
        return policy, raw

    def test_q18_escape_reads_recall_instead_of_a_second_speed_dose(self):
        policy, raw = self.q18_at_the_escape()
        board = self.board(policy, raw)
        self.assertEqual(board.player.speed, 120)  # 加速(+10), the plan's dose at 1277366
        self.assertEqual(board.player.hp, 136)

        key = policy.choose_key(board)

        self.assertEqual(policy.last_reason, "emergency:recall-quest-fail")
        self.assertTrue(key.startswith("r"), key)

    def test_q18_unhasted_escape_still_takes_its_speed_dose(self):
        policy, raw = self.q18_at_the_escape()
        # DECLARED CONSTRUCTED: the same board with the haste gone (the field a
        # plain +0, as on the recorded board before the dose at 1277366): the
        # rule the haste check gates stays.
        unhasted = copy.deepcopy(raw)
        unhasted["player"]["speed"] = 110
        unhasted["player"]["speed_display"] = {"color": "white", "riding": False, "text": "", "value": 0}
        board = self.board(policy, unhasted)
        policy._haste_read_memory = None  # the line memory: the board's own field decides

        key = policy.choose_key(board)

        self.assertEqual(policy.last_reason, "emergency:quaff-speed")
        self.assertTrue(key.startswith("q"), key)

if __name__ == "__main__":
    unittest.main()
