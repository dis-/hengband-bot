"""On the floor the finale's regeneration climbed to, the finale's own recall line (n1-b life-416).

Owner 2026-11-21: a lap of 99F/100F that finds nothing regenerates the floor (up the stairs, then
straight down), and 「巻物が尽きたら取り込んだテレポートの杖、杖も尽きたら帰還して補給」 (finale_hold
``relay_floor`` / ``return_due``, policy_town ``_should_start_town_return``).

Recorded (tests/extract_finale_relay_1123_fixture.py, ``finale-relay-1123``): the regeneration's
last 99F board (live seq639 '<', 4301176) and the 98F boards up to live seq644 (4301186), where the
ordinary return check read Word of Recall ('rf', ``return:recall``, trigger ``teleport-low``) with
no Teleportation scroll carried.

DECLARED CONSTRUCTED: the expedition's mark (finale_prep ``lifted``) and the absorbed-device lists
(tests/support/finale_416 ``device_lists``: the Staff of Teleportation charged; the snapshot log
carries no list, and the 98F boards show the staffs cast, 'mAj', 'mAw'); the regeneration's quest
and its ``ascend`` phase on the 99F board (the policy is primed on that board only);
``test_no_staff_charge_recalls``: the Teleportation staff's row at 0 charges;
``test_healing_spent_recalls``: the last 98F board's Healing (26) and *Healing* (15) taken out
(owner 2026-11-25: the relay floor recalls with both spent, as the way down does).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import dataclasses
import gzip
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import finale_descent, finale_hold, finale_prep, me_capability
from hengbot.me_absorbed_substitutes import TELEPORTATION
from hengbot.model import (
    DUNGEON_ANGBAND, SV_POTION_CURE_CRITICAL, SV_POTION_HEALING, SV_POTION_STAR_HEALING,
    parse_snapshot)
from hengbot.monrace_knowledge import load_monrace_knowledge
from support import finale_416
from support.recorded import EDIT, _policy

RELAY = Path(__file__).with_name("fixtures") / "finale-relay-1123" / "boards.jsonl.gz"
RECALL_TURN = 4301186
OBERON_QUEST = 8


def relay_boards():
    with gzip.open(RELAY, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    seen, kept = set(), []
    for row in rows:
        # Live decided the first of the arrival turn's boards (the others answer its pref command).
        if row["turn"] in seen:
            continue
        seen.add(row["turn"])
        kept.append(row)
    return kept


class FinaleRelayFloor1123RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.raws = relay_boards()

    def drive(self, staff_charges=None):
        """(policy, [(turn, key, reason)]): the boards as recorded, open loop."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(self.raws[0]), self.monrace))
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        held = finale_prep.phase(policy)
        held.lifted, held.step = True, finale_prep.DONE
        decided, owner = [], None
        for raw in self.raws:
            raw = copy.deepcopy(raw)
            if owner:
                raw["_completed_operation_owner"] = owner
            board = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
            lists = finale_416.device_lists(board.turn)
            if staff_charges is not None:
                turn, rows = lists["staff"]
                teleportation = me_capability.names(*TELEPORTATION)[0]
                lists["staff"] = (turn, tuple(
                    {**row, "current": staff_charges} if row["name"] == teleportation
                    else row for row in rows))
            policy._me_device_lists = lists
            if board.dungeon_level == 99:
                policy._quest_regen_id, policy._quest_regen_phase = OBERON_QUEST, "ascend"
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            decided.append((board.turn, key, policy.last_reason))
            owner = policy.last_reason if key else None
            if key:
                policy.confirm_key_posted(key)
        return policy, board, decided

    def test_the_absorbed_staff_keeps_the_relay_floor(self):
        policy, board, decided = self.drive()
        self.assertEqual((board.floor_key, board.turn), ((DUNGEON_ANGBAND, 98, 0), RECALL_TURN))
        self.assertEqual(policy._quest_regen_phase, "descend")
        self.assertTrue(finale_hold.relay_floor(policy, board))
        self.assertEqual(policy._count_teleport_scrolls(board), 0)
        self.assertFalse(finale_hold.return_due(policy, board))
        self.assertFalse(policy._should_start_town_return(board))
        # Recorded: ('rf', 'return:recall') under the trigger teleport-low.
        turn, key, reason = decided[-1]
        self.assertEqual(turn, RECALL_TURN)
        self.assertNotIn(reason, ("return:recall", "return:wait-recall"))
        self.assertFalse(policy._returning_to_town)

    def test_no_staff_charge_recalls(self):
        policy, board, decided = self.drive(staff_charges=0)
        self.assertTrue(finale_hold.return_due(policy, board))
        self.assertEqual(decided[-1][1:], ("rf", "return:recall"))
        self.assertEqual(policy._last_return_trigger, finale_hold.RETURN_TRIGGER)

    def test_healing_spent_recalls(self):
        policy, board, _decided = self.drive()
        self.assertTrue(finale_hold.relay_floor(policy, board))
        self.assertFalse(policy._should_start_town_return(board))

        def without(*svals):
            return dataclasses.replace(board, inventory=[
                item for item in board.inventory
                if not (item.is_potion and item.sval in svals)])

        # Either kind left keeps the floor; the Cure Critical Wounds are not counted.
        self.assertFalse(policy._should_start_town_return(without(SV_POTION_HEALING)))
        self.assertFalse(policy._should_start_town_return(without(SV_POTION_STAR_HEALING)))
        self.assertFalse(policy._should_start_town_return(without(SV_POTION_CURE_CRITICAL)))
        spent = without(SV_POTION_HEALING, SV_POTION_STAR_HEALING)
        self.assertEqual(len(spent.inventory), len(board.inventory) - 2)
        self.assertTrue(policy._should_start_town_return(spent))
        self.assertEqual(policy._last_return_trigger, finale_descent.HEALING_TRIGGER)


if __name__ == "__main__":
    unittest.main()
