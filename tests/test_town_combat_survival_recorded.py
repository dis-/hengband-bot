"""Town combat is survival, with the dungeon's attacks (owner 2026-10-31).

Owner 2026-10-31 「生存の扱いにして数えない + 近接以外の攻撃手段も街で使う」:
a town fight never spends an errand's budget nor retires an owner, and the
Magic-Eater answers with its absorbed / carried ranged attacks first, as in
the dungeon (me_ranged_first, me_device_attacks).

Recorded board: n1-c life-067 2026-10-31 19:26 (D49 stop 1), frozen in
tests/fixtures/town-combat-survival-20261031.json.gz
(tests/extract_town_combat_survival_1031.py).  The bot meleed わめくキチガイ
eleven times, every blow missing; the arbiter retired misc four blows in and
three retirements stopped it on town:blocked:owner-retired-burst.

Supervisor 2026-10-31 (D49 question 2, survival first): a food-critical
staple (no charge left, no other charged device) still goes to the Tower
while a fixed quest holds the town; otherwise the hold stands.  The board is
the D47 Telmora board of tests/fixtures/me-staff-loops-20261031.json.gz.

Every decision is the public ``choose_key``; posted keys go through the
production executor port (test_me_nokey_1031_recorded.PostedKey).
DECLARED CONSTRUCTED: the new process has read the staff power list; the
no-missile cases' boards carry the executor's ``_magic_eater_wand_charges``
-1 annotation (a wand power list without Magic Missile), so the next answer
is a spare lit torch, and the melee case also drops the pack's torches (the
missile case too: beside わめくキチガイ a thrown lit torch out-scores the
2d6 missile, owner 2026-11-01 「見込みの大きい方を使う」,
test_d57_me_combat_1101_recorded); the food cases' pack (staple charges, other devices) as each case states, with
every sequence staff absorbed.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import me_staff_sequence as sequence
from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.control_client import ControlClient
from hengbot.input_executor import OperationExecutor
from hengbot.magic_eater import MISSILE_REASON
from hengbot.me_ranged_first import TORCH_REASON
from tests import test_me_nokey_1031_recorded as nokey
from tests import test_me_staff_loops_1031_recorded as loops
from tests.test_magic_eater_ranged_fire_recorded import PowerGame


FIXTURE = Path(__file__).with_name("fixtures") / "town-combat-survival-20261031.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
ATTACKS = ("melee", MISSILE_REASON, TORCH_REASON)
STAPLE_SLOT = "i"          # 謎の魔法棒 on the Telmora board
OTHER_DEVICES = {"h", "j", "k", "l", "m"}  # Stone to Mud, four Identify staffs


def fight_boards(*, missile=True, torches=True):
    boards = copy.deepcopy(CASE["boards"])
    for raw in boards:
        if not missile:
            raw["_magic_eater_wand_charges"] = -1
        if not torches:
            raw["inventory"] = [item for item in raw["inventory"]
                                if (item.get("tval"), item.get("sval")) != (39, 0)]
    return boards


class MissilePostedKey(nokey.PostedKey):
    """Shared by the recorded Magic-Eater town fights (also D55); no tests."""

    def post(self, policy, raw, key):
        """The absorbed Magic Missile goes through the executor's power prompts
        (cmd-magiceat.cpp, test_magic_eater_ranged_fire_recorded.PowerGame,
        DECLARED CONSTRUCTED: ten charges); every other key as PostedKey."""
        if policy.last_reason != MISSILE_REASON:
            return super().post(policy, raw, key)
        game = PowerGame(copy.deepcopy(raw), 10, direction=key[-1])
        client = ControlClient(1, request_budget=2, retries=1, backoff=0,
                               socket_factory=game.socket_factory)
        self.addCleanup(client.close)
        executor = OperationExecutor(client, drain=lambda: list(game.jsonl))
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual((game.fired, game.wait), (1, "command"))


class TownCombatSurvivalTest(MissilePostedKey, loops.MeStaffLoopsRecordedTest):
    def fight(self, **boards):
        policy = loops.new_policy({**CASE, "boards": CASE["boards"]}, CASE["skill"],
                                  record=CASE["sequence"], monraces=CASE["monraces"])
        attacks = []

        def each(raw, key):
            arbiter = policy._town_turn_arbiter
            self.assertFalse(arbiter.retirement_pending,
                             (raw["turn"], key, policy.last_reason, arbiter.telemetry))
            if policy.last_reason in ATTACKS:
                attacks.append(policy.last_reason)
                self.assertEqual(arbiter.telemetry["producer_owner"], "survival", raw["turn"])

        self.drive(policy, fight_boards(**boards), each)
        return attacks

    def test_recorded_fight_answers_with_the_absorbed_magic_missile(self):
        attacks = self.fight(missile=True, torches=False)
        self.assertGreaterEqual(len(attacks), 11)
        self.assertEqual(set(attacks), {MISSILE_REASON})

    def test_without_the_missile_a_spare_torch_is_thrown(self):
        attacks = self.fight(missile=False)
        self.assertGreaterEqual(len(attacks), 11)
        self.assertEqual(set(attacks), {TORCH_REASON})

    def test_melee_only_fight_spends_no_errand_budget(self):
        attacks = self.fight(missile=False, torches=False)
        self.assertGreaterEqual(len(attacks), 11)
        self.assertEqual(set(attacks), {"melee"})

    def telmora(self, staple_charges, other_devices):
        case = loops.CASE["q2"]
        policy = loops.new_policy(case, loops.CASE["inn"]["skill"])
        sequence.state(policy).absorbed = {sval: 1 for sval in sequence.SEQUENCE_SVALS}
        boards = copy.deepcopy(case["boards"])
        for raw in boards:
            items = []
            for item in raw["inventory"]:
                if item["slot"] == STAPLE_SLOT:
                    item = dict(item, charges=staple_charges)
                if item["slot"] in OTHER_DEVICES and not other_devices:
                    continue
                items.append(item)
            raw["inventory"] = items
        rows = self.drive(policy, boards)
        return rows[-1]

    def test_food_critical_staple_goes_to_the_tower_from_a_quest_town(self):
        _raw, key, reason = self.telmora(0, other_devices=False)
        self.assertTrue(reason.startswith("me-staff:travel-morivant"), (key, reason))

    def test_staple_low_but_not_critical_keeps_the_quest_hold(self):
        for charges, devices in ((0, True), (3, False)):
            _raw, key, reason = self.telmora(charges, other_devices=devices)
            self.assertFalse(reason.startswith("me-staff:"), (charges, devices, key, reason))


if __name__ == "__main__":
    unittest.main()
