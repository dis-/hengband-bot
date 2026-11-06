"""A worn unidentified item the game refuses to take off stays pinned.

n1-c life-154 (2026-11-06 20:53:26-20:53:34, town:blocked:owner-retired-burst):
the unidentified タルワール (2d4) {Q34} wielded from the Q34 reward turned out
cursed (「うわ！ すさまじく冷たい！」).  The optimizer planned to take it off for a
pack weapon; do_cmd_takeoff answered 「ふーむ、どうやら呪われているようだ。」
(cmd-equipment.cpp) and changed nothing.  The planner pins a worn item and adds
the cursed-equipped blocker only on ``is_cursed``, which the emitter sends for
identified items only (bot-json-output.cpp), so each takeoff was awaited for
the whole confirmation budget, stalled, quarantined the worn item out of the
optimizer's view, and was planned again: four cycles until the equipment-txn
owner retired three times.

Board rows: tests/fixtures/optimizer-lamp-20261019.jsonl.gz rows 0-4 (a town
board, ~f skill list, board, the ~9 Home list, board).  DECLARED CONSTRUCTED:
the main hand holds the unidentified Q34 talwar and the recorded (パターン)
スモール・ソード moves to the pack (the better weapon the optimizer wants), the
worn torch has 3300 turns and the empty pack lantern and Home lights are left
out (light is not the question here).  The refusal boards repeat the last board
with the game's refusal message after each posted takeoff.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.warrior_optimization import CharacterCalibration
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "optimizer-lamp-20261019.jsonl.gz"
REFUSAL = "ふーむ、どうやら呪われているようだ。"
TALWAR = {
    "ac": 0, "aware": True, "charges": 0, "charging": False, "count": 1,
    "damage_dice": {"num": 2, "sides": 4}, "fully_known": False,
    "inscription": "Q34", "is_artifact": False, "is_bounty": False,
    "is_broken": False, "is_cursed": False, "is_ego": False,
    "is_equipment": True, "known": False, "known_flags": [],
    "name": "タルワール (2d4) {Q34}", "pval": 0, "slot": "main_hand", "sval": 15,
    "to_a": 0, "to_d": 0, "to_h": 0, "tval": 23, "weight": 100,
}


class TownCursedTakeoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines = gzip.decompress(FIXTURE.read_bytes()).decode("utf-8").splitlines()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.policy = _policy(self.directory, self.monrace)
        self.policy._crossarea_fundraising_enforced = True
        player = parse_snapshot(json.loads(self.lines[0]), {}).player
        # DECLARED CONSTRUCTED: calibration constants of the captured character.
        self.policy._character_calibration = CharacterCalibration(
            race_id=player.race_id,
            class_id=player.class_id,
            personality_id=player.personality_id,
            level=player.level,
            stat_cur=tuple(player.printed_stat_cur_key),
            base_stats=tuple(player.stat_max),
            base_hp=player.max_hp,
            base_ac_bonus=0,
            intrinsic_abilities=frozenset(),
        )
        self.policy._character_calibration_loaded = True

    def _rows(self, *, feeling=None):
        rows = []
        for line in self.lines[:5]:
            row = json.loads(line)
            if row.get("type") == "player_turn":
                sword = next(item for item in row["equipment"] if item["slot"] == "main_hand")
                talwar = dict(TALWAR)
                if feeling is not None:
                    talwar.update(pseudo_feeling=feeling,
                                  name="タルワール (2d4) {呪われている, Q34}")
                row["equipment"] = [
                    talwar if item["slot"] == "main_hand" else item
                    for item in row["equipment"]
                ]
                torch = next(item for item in row["equipment"] if item["slot"] == "light")
                torch.update(light_turns=3300, name="松明(3300ターンの寿命)")
                pack = [item for item in row["inventory"] if item.get("slot") != "m"]
                pack.append(dict(sword))
                for index, item in enumerate(pack):
                    item["slot"] = chr(ord("a") + index)
                row["inventory"] = pack
            if row.get("knowledge", {}).get("category") == "home":
                row["knowledge"]["items"] = [
                    item for item in row["knowledge"]["items"] if item.get("tval") != 39
                ]
            rows.append(json.dumps(row, ensure_ascii=False))
        return rows

    def _decide(self, line):
        _decoded, snapshots = _consume_response_sequence(
            [line], self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        if json.loads(line).get("type") != "player_turn":
            return None
        key = self.policy.choose_key(snapshots[-1])
        self.policy.confirm_key_posted(key)
        return key, self.policy.last_reason

    def _cursed_blockers(self):
        # The pin keeps the talwar in the chosen loadout; without it the plan
        # stops on the cursed-equipped blocker, whose remove-curse servers read
        # is_cursed and never serve an unidentified item.
        blockers = getattr(self.policy._equipment_optimization_preparation, "blockers", ())
        return [blocker for blocker in blockers if blocker.startswith("cursed-equipped:")]

    def _main_hand_takeoff_planned(self):
        session = self.policy._equipment_transaction_session
        return session is not None and any(
            action.kind == "takeoff" and action.target_slot == "main_hand"
            for action in session.plan.actions
        )

    def test_refused_takeoff_is_settled_and_not_planned_again(self):
        rows = self._rows()
        decisions = [decision for decision in map(self._decide, rows) if decision]
        # The live first step: the optimizer takes the worn talwar off.
        self.assertEqual(decisions[-1], ("ta", "equipment-transaction:takeoff"))
        board = json.loads(rows[-1])
        later = []
        for step in range(20):
            board["turn"] += 10
            board["messages"] = [REFUSAL] if later == [] or later[-1][0] == "ta" else []
            later.append(self._decide(json.dumps(board, ensure_ascii=False)))
        reasons = [reason for _key, reason in later]
        # Live: seven await-confirmation boards, a confirmation stall and the
        # same takeoff again, four times.
        self.assertNotIn("equipment-transaction:await-confirmation", reasons)
        self.assertNotIn("equipment-transaction:confirmation-stall-bound", reasons)
        self.assertNotIn("equipment-transaction:takeoff", reasons)
        self.assertFalse(self._main_hand_takeoff_planned())
        self.assertEqual(self._cursed_blockers(), [])

    def test_worn_item_sensed_cursed_is_never_taken_off(self):
        decisions = [decision for decision in map(self._decide, self._rows(feeling="cursed"))
                     if decision]
        self.assertNotEqual(decisions[-1], ("ta", "equipment-transaction:takeoff"))
        self.assertFalse(self._main_hand_takeoff_planned())
        self.assertEqual(self._cursed_blockers(), [])


if __name__ == "__main__":
    unittest.main()
