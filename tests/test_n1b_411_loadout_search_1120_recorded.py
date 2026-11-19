"""n1-b life-411's loadout kept the ★運命のオーブ (2026-11-20 06:01, 81F band).

Owner: 「私の見立てでは今の装備は最適ではない。全ての組み合わせを試せているか？」
-> 「案A：打撃の上位3つの周りも探す」.

Recorded: the town-arrival checkpoint of the 06:01 visit and journal rows 0-1
(tests/extract_n1b_411_loadout_search_1120_fixture.py), through the public
choose_key.  Row 1 runs the equipment optimizer on the 235-item catalog (past
the incremental threshold: the single-slot closure).

The Magic-Eater wore ★シミター『アイシングデス』 with ★運命のオーブ: 1926.7 melee
per game time, survival / kill ratio 133.55.  Its neighbour ★飛行石 (+2 speed;
1980.2, 130.66) lost inside the 1% ratio band, since it was itself the field's
best melee and the 95% cut (1881) kept the worn set.  The 飛行石 set's own
neighbour ★鉄鋲底の靴『炎の鉄ゲタ』 (2067.4; the boots alone drop the worn set
to +23 speed, under the 81F +25 gate) lifts the cut to 1964: the worn set
falls under it and the 飛行石 set wins.  A field of ~41,000 sets (every two-
slot change, repeated) and a four-change beam search chose the same set.

The closure now also expands around the three sets of the chosen band with
the most melee per game time (warrior_optimization.CLOSURE_MELEE_LEADERS):
row 1 plans the 飛行石, and from the 飛行石 set the closure keeps it.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import warrior_optimization
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-loadout-search-1120"
OPTIMIZER_ROW = 1
HIKOUSEKI = "★飛行石"
ORB = "★運命のオーブ"


def winner_only_closure(current, neighbours, optimize):
    """The closure as recorded: only the chosen set's neighbourhood is expanded."""
    candidates, expanded, seed = {}, set(), current
    while True:
        expanded.add((seed.item_ids, seed.hand_mode))
        for loadout in neighbours(seed):
            candidates.setdefault((loadout.item_ids, loadout.hand_mode), loadout)
        result = optimize(tuple(candidates.values()))
        best = result.best
        if (best is None or result.timed_out
                or (best.loadout.item_ids, best.loadout.hand_mode) in expanded):
            return result
        seed = best.loadout


class N1b411LoadoutSearch1120RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, self.recorded, self.steps = load(FIXTURE, Path(scratch.name))

    def decide(self, row):
        board = self.steps[row][1]()
        return board, self.policy.choose_key(board), self.policy.last_reason

    def post(self, key):
        policy = self.policy
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def optimizer_row(self):
        _board, key, reason = self.decide(0)
        self.assertEqual((key, reason), (self.recorded[0]["key"], self.recorded[0]["reason"]))
        self.post(key)
        return self.decide(OPTIMIZER_ROW)

    def test_recorded_selection_keeps_the_orb(self):
        with mock.patch.object(warrior_optimization, "optimize_single_slot_closure",
                               winner_only_closure):
            board, key, reason = self.optimizer_row()
        # Recorded: shop:travel (the worn set kept).  Since the sellable-artifact
        # rule (main 2026-11-20) the visit starts at the Home instead; either
        # way no equipment transaction.
        self.assertFalse(reason.startswith("equipment-transaction"), (key, reason))
        self.assertIn(ORB, next(item.name for item in board.equipment if item.slot == "light"))
        result = self.policy._equipment_optimization_preparation.result
        self.assertEqual(result.best.loadout.item_at("light").item.name[:len(ORB)], ORB)

    def test_closure_plans_the_hikouseki_and_keeps_it(self):
        calls = []
        real = warrior_optimization.optimize_single_slot_closure

        def recording(current, neighbours, optimize):
            calls.append((neighbours, optimize))
            return real(current, neighbours, optimize)

        with mock.patch.object(warrior_optimization, "optimize_single_slot_closure", recording):
            _board, key, reason = self.optimizer_row()
        result = self.policy._equipment_optimization_preparation.result
        best = result.best.loadout
        current = self.policy._equipment_optimization_preparation.current
        changed = {slot: item.item.name for slot, item in best.slots
                   if current.item_at(slot) is None or current.item_at(slot).id != item.id}
        self.assertEqual(list(changed), ["light"])
        self.assertTrue(changed["light"].startswith(HIKOUSEKI), changed)
        self.assertEqual(best.item_at("main_hand").item.name[:len("★シミター『アイシングデス』")],
                         "★シミター『アイシングデス』")
        self.assertEqual(result.chosen_depth, 81)
        self.assertEqual(reason, "equipment-transaction:travel-home")
        self.assertNotEqual(key, self.recorded[OPTIMIZER_ROW]["key"])
        # A fixed point: the closure started from the 飛行石 set keeps it.
        neighbours, optimize = calls[-1]
        again = real(best, neighbours, optimize).best.loadout
        self.assertEqual((again.item_ids, again.hand_mode), (best.item_ids, best.hand_mode))


if __name__ == "__main__":
    unittest.main()
