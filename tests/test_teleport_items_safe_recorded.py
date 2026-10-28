"""Replay the C4-A town stop on a carried (unequipped) anti-teleport amulet.

The fixture is state rows 17-30 of the soak capture
c4a-loops-20261016/20261021-193715-town-blocked-departure-unsatisfiable,
copied as-is (life-014, Level 33, town): the restart that repeated the
20261021-170527 stop 17 seconds after it.  The pack holds
"反テレポートのアミュレット" (slot m, known TR_NO_TELE) UNEQUIPPED.

Live (285b3089, enforce_crossarea_fundraising and in_store_shop_ops on), the
departure board judged ``teleport_items_safe`` over pack AND equipment, so
the carried amulet failed the gate and no owner could satisfy it
(town:blocked:departure-unsatisfiable, failed == ["teleport_items_safe"]).

Hengband derives anti-teleportation only from the wielding slots:
has_anti_tele -> common_cause_flags -> check_equipment_flags, which loops
INVEN_WIELDING_SLOTS (INVEN_MAIN_HAND..INVEN_FEET) only
(src/player/player-status-flags.cpp:57-74, 117-134, 814-817;
src/inventory/inventory-slot-types.h:32; player_ptr->anti_tele is set from it
at src/player/player-status.cpp:287).  A carried NO_TELE item never blocks
teleportation.

DECLARED CONSTRUCTED: the ~9 request answered by the knowledge rows (the
fresh policy is marked as awaiting it), the ~f skill-exp cache, and in the
controls the amulet worn in the neck slot (swapped with the worn amulet) and
an armed Word of Recall countdown.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import copy
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import TR_NO_TELE
from test_esp_threat_rest_recorded import EDIT, _policy
from recorded_pack_headroom import pre_pack_headroom_class


FIXTURE = Path(__file__).parent / "fixtures" / "teleport-items-safe-c4a-20261021.jsonl.gz"
SHA256 = "4fd2324f203d448b74572905a6e90b3b0e2241d3333412238e3db5164a5a8075"
RECORDED = FIXTURE.with_name("teleport-items-safe-c4a-20261021.recorded.json")
RECORDED_SHA256 = "a07d5ae11901aff9fe413a603382f41f9183df880fd9fda4a90bcbc78df0a339"
DEPART_BOARD = 10  # state row 27: first outside board after the town errands
NEXT_BOARD = 11  # state row 28: the same town board after the next key
STOP_BOARD = 13  # state row 30: the recorded stop board
AMULET = "反テレポートのアミュレット"


@pre_pack_headroom_class  # declared wall: measured row-6 surplus order; hazard checks stay live
class TeleportItemsSafeRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == SHA256
        cls.lines = gzip.decompress(payload).decode("utf-8").splitlines()
        recorded = RECORDED.read_bytes()
        assert hashlib.sha256(recorded).hexdigest() == RECORDED_SHA256
        cls.recorded = json.loads(recorded.decode("utf-8"))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.temporary = TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        cls.policy = _policy(cls.directory, cls.monrace)
        cls.policy._crossarea_fundraising_enforced = True
        cls.policy._in_store_ops_enabled = True
        cls.decisions = {}
        for index in range(DEPART_BOARD):
            decision = cls._feed(cls.lines[index])
            if decision is not None:
                cls.decisions[index] = decision
        # The policy right before the departure board; each test continues
        # from its own copy.
        cls.before_departure = copy.deepcopy(cls.policy)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @staticmethod
    def _await_recorded_knowledge(policy):
        # DECLARED CONSTRUCTED: the fresh policy awaits the recorded ~9, as
        # the posted request the capture does not include would leave it.
        policy._home_knowledge_scan_inflight = True
        policy._home_knowledge_scan_epoch = None

    @classmethod
    def _feed(cls, line, policy=None):
        policy = cls.policy if policy is None else policy
        knowledge = json.loads(line).get("type") == "knowledge"
        if knowledge:
            cls._await_recorded_knowledge(policy)
        _decoded, snapshots = _consume_response_sequence(
            [line], policy, lambda _key: True, cls.monrace,
            knowledge_ledger_path=cls.directory / "knowledge.jsonl",
        )
        if knowledge or not snapshots:
            return None
        board = snapshots[-1]
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        return board, policy.choose_key(board), policy.last_reason

    @staticmethod
    def _worn_amulet_row(line):
        # DECLARED CONSTRUCTED: the amulet worn in the neck slot, the worn
        # amulet carried in its pack letter instead.
        row = json.loads(line)
        carried = next(i for i in row["inventory"] if i["name"] == AMULET)
        worn = next(i for i in row["equipment"] if i["slot"] == "neck")
        carried["slot"], worn["slot"] = worn["slot"], carried["slot"]
        row["inventory"] = [worn if i is carried else i for i in row["inventory"]]
        row["equipment"] = [carried if i is worn else i for i in row["equipment"]]
        return json.dumps(row, ensure_ascii=False)

    @staticmethod
    def _recall_armed_row(line):
        # DECLARED CONSTRUCTED: a Word of Recall countdown already armed.
        row = json.loads(line)
        row["player"]["recalling"] = True
        return json.dumps(row, ensure_ascii=False)

    def test_recorded_stop_failed_only_on_the_carried_amulet(self):
        decisions = self.recorded["decisions"]
        self.assertEqual(
            (decisions["8"]["key"], decisions["8"]["reason"]),
            ("1", "town:blocked:departure-unsatisfiable"))
        self.assertEqual(decisions["6"]["departure_block_failed"],
                         ["teleport_items_safe"])
        self.assertEqual(
            self.recorded["previous_run_stop"]["departure_block_failed"],
            ["teleport_items_safe"])
        for index in (DEPART_BOARD, STOP_BOARD):
            row = json.loads(self.lines[index])
            amulets = [i for i in row["inventory"] if i["name"] == AMULET]
            self.assertEqual([i["slot"] for i in amulets], ["m"])
            self.assertIn(TR_NO_TELE, amulets[0]["known_flags"])
            self.assertFalse(any(
                TR_NO_TELE in i.get("known_flags", ())
                for i in row["equipment"]))
            self.assertEqual(row["player"]["level"], 33)

    def test_replay_reaches_the_recorded_departure_board(self):
        self.assertEqual(
            [self.decisions[n][1:] for n in (6, 9)],
            [("\x1b`n'.", "shop:travel"),
             ("\x1b", "shop:observe-and-leave")])

    def test_carried_amulet_does_not_block_departure(self):
        policy = copy.deepcopy(self.before_departure)
        board, key, reason = self._feed(self.lines[DEPART_BOARD], policy)
        conjuncts = policy._town_departure_conjuncts(board)
        self.assertTrue(conjuncts["teleport_items_safe"])
        self.assertEqual([k for k, v in conjuncts.items() if not v], [])
        self.assertTrue(
            policy._departure_minimum(board, 1)["values"]["teleport_items_safe"])
        self.assertNotEqual(reason, "town:blocked:departure-unsatisfiable")
        self.assertEqual((key, reason), ("Cf\ry\x1b\x1b", "town:character-dump"))
        _board, key, reason = self._feed(self.lines[NEXT_BOARD], policy)
        self.assertEqual((key, reason), ("rfa", "town:recall-to-angband"))

    def test_control_worn_amulet_still_blocks_departure(self):
        policy = copy.deepcopy(self.before_departure)
        board, _key, reason = self._feed(
            self._worn_amulet_row(self.lines[DEPART_BOARD]), policy)
        self.assertEqual(
            [i.name for i in board.equipment if TR_NO_TELE in i.known_flags],
            [AMULET])
        conjuncts = policy._town_departure_conjuncts(board)
        self.assertFalse(conjuncts["teleport_items_safe"])
        self.assertFalse(
            policy._departure_minimum(board, 1)["values"]["teleport_items_safe"])
        self.assertNotEqual(reason, "town:recall-to-angband")

    def test_armed_recall_is_not_cancelled_for_the_carried_amulet(self):
        policy = copy.deepcopy(self.before_departure)
        board, key, reason = self._feed(
            self._recall_armed_row(self.lines[DEPART_BOARD]), policy)
        self.assertTrue(board.player.recalling)
        self.assertNotEqual(reason, "town:cancel-unsafe-recall")
        self.assertEqual((key, reason), ("1", "town:wait-recall-step-off"))

    def test_control_armed_recall_is_cancelled_for_the_worn_amulet(self):
        policy = copy.deepcopy(self.before_departure)
        line = self._recall_armed_row(self._worn_amulet_row(self.lines[DEPART_BOARD]))
        _board, key, reason = self._feed(line, policy)
        self.assertEqual(reason, "town:cancel-unsafe-recall")
        self.assertTrue(key.startswith("r"))

    def _quest_readiness_reason(self, line):
        # DECLARED CONSTRUCTED: the first approved fixed-quest strategy's
        # force judged ready, so the readiness check reaches its inventory hazards.
        policy = copy.deepcopy(self.before_departure)
        board, _key, _reason = self._feed(line, policy)
        quest_id = next(
            q for q in sorted(policy._quest_knowledge)
            if policy.approved_quest_strategy(q) is not None)
        with patch.object(
            policy, "_approved_strategy_force_ready", return_value=True
        ):
            policy._fixed_quest_ready_for_travel(board, quest_id)
        return policy._fixed_quest_readiness.get("reason")

    def test_carried_amulet_does_not_reject_fixed_quest_entry(self):
        self.assertNotEqual(
            self._quest_readiness_reason(self.lines[DEPART_BOARD]),
            "random-teleport")

    def test_control_worn_amulet_rejects_fixed_quest_entry(self):
        self.assertEqual(
            self._quest_readiness_reason(
                self._worn_amulet_row(self.lines[DEPART_BOARD])),
            "random-teleport")


if __name__ == "__main__":
    unittest.main()
