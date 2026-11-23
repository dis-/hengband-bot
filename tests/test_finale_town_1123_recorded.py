"""In town with Angband refused for its 96F+ recall depth, the finale's preparation (n1-b life-416).

Owner rules: 2026-11-21 (LOCKED) 「帰還の深さが96F以上なら遠征以外で鉄獄へ帰還しない」; 2026-11-19
「鉄獄50F以降は浅い階層へのフォールバックをやめる。行き先を変えるのはダンジョンの主討伐のみとする。」;
2026-11-20 「4つの街を回ってテレポートの巻物を買い足す」 「一周する毎に宿屋で一泊する」 (finale_hold
``applies`` / ``town_key``, angband_hold ``held`` / ``deep_refused``).

Recorded (tests/extract_finale_town_1123_fixture.py, ``n1b-416-finale-town-1123``): the
town-arrival checkpoint of 21:13:45 (turn 4308361, back from the Castle 64F).  Rows 0-18 are
decided through the public ``choose_key`` and compared with the record; row 19 was
``town:entrance-step-off:town:unsafe-recall-fallback`` (the Castle chosen), row 21
``town:recall-to-alt-dungeon``.  The board owned 79 of the 84 Restore Mana and every other supply.

DECLARED CONSTRUCTED: ``test_teleportation_short_shops_first`` and
``test_suppliers_tried_take_the_circuit`` (this town's two suppliers marked tried) raise the
Teleportation count to 45 and lower the Restore Mana carry to the 79 owned
(angband_finale ``restore_mana_carry``), as ``test_supplies_owned_enter_the_phase`` does.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import angband_finale, angband_hold, finale_hold, finale_prep, finale_teleport_tour
from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

TOWN = Path(__file__).with_name("fixtures") / "n1b-416-finale-town-1123"
FALLBACK_ROW = 19


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class FinaleTownHold1123RecordedTest(unittest.TestCase):
    def replay(self):
        """(policy, the fallback row's board, the replayed rows' (decided, recorded))."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, _journal, steps = load(TOWN, Path(scratch.name))
        replayed = []
        for recorded, supply in steps[:FALLBACK_ROW]:
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(supply())
            replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            post(policy, recorded["key"])
        return policy, steps[FALLBACK_ROW][1](), replayed

    def decide(self, policy, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return key, policy.last_reason

    def test_no_fallback_and_the_restore_mana_short_is_asked(self):
        policy, board, replayed = self.replay()
        for row, (decided, recorded) in enumerate(replayed):
            self.assertEqual(decided, recorded, row)
        self.assertTrue(angband_hold.held(policy, board))
        self.assertTrue(angband_hold.deep_refused(policy, board))

        key, reason = self.decide(policy, board)

        # Recorded: ('1', 'town:entrance-step-off:town:unsafe-recall-fallback'), the Castle 64F.
        self.assertEqual(reason, "town:blocked:finale-not-in-town:restore_mana")
        self.assertEqual((policy._target_dungeon_id, policy._alternate_dungeon), (DUNGEON_ANGBAND, None))
        owned = angband_finale.memory(policy).report["owned"]
        self.assertEqual((owned["restore_mana"]["measured"], owned["restore_mana"]["required"]), (79, 84))
        self.assertTrue(all(row["ready"] for name, row in owned.items() if name != "restore_mana"))

    def test_teleportation_short_shops_first(self):
        policy, board, _replayed = self.replay()
        # DECLARED CONSTRUCTED (module docstring).
        with mock.patch.object(angband_finale, "restore_mana_carry", return_value=79), \
                mock.patch.dict(angband_finale.CARRY, {angband_finale.TELEPORT: 45}):
            key, reason = self.decide(policy, board)
            self.assertEqual(finale_hold.short_rows(policy), ["teleport"])
        # This town's supplier first (angband_finale's errand); the circuit and its night come
        # where the departure would be (finale_hold ``town_key``), never the Castle.
        self.assertEqual(reason, "shop:travel")
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
        self.assertIsNone(policy._alternate_dungeon)

    def test_suppliers_tried_take_the_circuit(self):
        policy, board, _replayed = self.replay()
        # DECLARED CONSTRUCTED (module docstring), and this town's two suppliers tried.
        with mock.patch.object(angband_finale, "restore_mana_carry", return_value=79),                 mock.patch.dict(angband_finale.CARRY, {angband_finale.TELEPORT: 45}),                 mock.patch.object(type(policy), "_shelf_stop_tried", return_value=True):
            self.decide(policy, board)
            self.assertTrue(finale_hold.applies(policy, board))
            self.assertTrue(finale_teleport_tour.due(policy, board))
            key = finale_hold.town_key(policy, board)
        self.assertIsNotNone(key)
        self.assertIsNotNone(finale_teleport_tour.circuit(policy))
        self.assertEqual(policy._cross_town_shopping_funds["circuit"], "angband-finale-teleport")

    def test_supplies_owned_enter_the_phase(self):
        policy, board, _replayed = self.replay()
        # DECLARED CONSTRUCTED (module docstring).
        with mock.patch.object(angband_finale, "restore_mana_carry", return_value=79):
            key, reason = self.decide(policy, board)
        self.assertNotIn("unsafe-recall-fallback", reason)
        self.assertNotEqual(finale_prep.phase(policy).step, finale_prep.IDLE)
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)


if __name__ == "__main__":
    unittest.main()
