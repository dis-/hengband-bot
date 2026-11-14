"""One owner per Home potion: the drinker or the Home sweep (stat-potion-ownership-1114).

n1-c life-207 2026-11-14 05:50 (town:blocked:owner-retired-burst): the drink-at-once take
(stat-potions-home-1114) carried the whole 知能の薬 x2 stack out (row 16 ``5pl2``) and drank both
(rows 18, 20); the second raised INT to its maximum.  The confirmed take shortened the Home
catalogue's addressable prefix but left the emptied stack listed, so at row 21 the Home sweep
(item_use_route: a stat potion at the maximum is surplus) filed the take of that absent stack
(home-errand:request-knowledge:full-home-sale); the fresh list no longer held it, every Home leg
was refused (``_shopping_approach_key`` home-withdraw (('知能の薬', 75, 49), ()) ->
reservation-unavailable) and the stay burst.

Fix: the observed take leaves the catalogue (policy_home._remove_taken_from_home_catalogue, from
_confirm_home_withdrawal_address): a stack taken whole is no longer listed, a partly taken one
keeps the rest.  The drinker lists only the potions that still do something
(consumable_policy.drunk_now, read on every board), the sweep only the surplus ones
(item_use_route), so each Home potion has one owner.

Recorded: the capture's town-arrival checkpoint, journal rows and sidecars, the fixture of
tests/test_n1c_207_wait_recall_1114_recorded.py (tests/fixtures/n1c-207-wait-recall-1114).  Rows 0-20 replay but the declared FORCED
rows, which post the recorded key.

DECLARED CONSTRUCTED: the Home and its entrance (StatPotionHomeGame, the catalogue as its
shelf); a 知能の薬 x2 Home stack and a carried 知能の薬 for the surplus cases.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import time
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import consumable_policy, item_fate, item_use_route
from hengbot.cli import _ExecutorInputPort, _send_new_decision_key
from hengbot.model import STORE_HOME, TVAL_POTION, parse_snapshot
from support.town_arrival_fixture import load
from tests.support import recorded as harness
from tests.test_stat_potions_home_1114_recorded import StatPotionHomeGame, store_row

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-207-wait-recall-1114"
STRENGTH, INTELLIGENCE = 48, 49
STR_KIND, INT_KIND = (TVAL_POTION, STRENGTH), (TVAL_POTION, INTELLIGENCE)
# DECLARED: rows whose recorded key is posted undecided-equal: row 10 (the same ``1``, its reason
# names the end step-off on the restored policy) and row 19 (the periodic character dump's
# timer runs on the replay's clock; the live board drinks there and the recorded row 20 does).
FORCED = {10, 19}


def kinds(items):
    return [(item.tval, item.sval) for item in items]


class StatPotionOwnership1114RecordedTest(harness.ProductionHarness):
    def load(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, self.journal, rows = load(FIXTURE, Path(scratch.name))
        self.addCleanup(lambda: policy._home_disposal.history_path.unlink(missing_ok=True))
        return policy, rows

    def raw(self, row):
        entry = self.journal[row]
        return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])

    def to_row_21(self):
        """Rows 0-20 decided as recorded; row 21's board (INT now at its maximum)."""
        policy, rows = self.load()
        for recorded, supply in rows[:21]:
            board = supply()
            key = policy.choose_key(board)
            if recorded["row"] not in FORCED:
                self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                                 recorded["row"])
            policy.confirm_key_posted(recorded["key"])
        board = rows[21][1]()
        self.assertIn("int", board.player.stats_at_max)
        self.assertEqual(rows[21][0]["reason"], "periodic:character-dump")
        self.assertEqual(rows[22][0]["reason"], "home-errand:request-knowledge:full-home-sale")
        return policy, board

    def drive(self, policy, board, key, shelf, limit=30):
        """Post each decided key through the production executor into the constructed Home."""
        outside = self.raw(21)
        entrance = next(grid.position for grid in board.grids.values()
                        if grid.store_number == STORE_HOME)
        game = StatPotionHomeGame(
            pack=copy.deepcopy(outside["inventory"]),
            equipment={item["slot"]: item for item in copy.deepcopy(outside["equipment"])},
            pages=[shelf[index:index + 52] for index in range(0, len(shelf), 52)] or [[]],
            inside=False, state_template=copy.deepcopy(outside), home_limit=len(shelf) + 20)
        game.order = {item["name"]: index for index, item in enumerate(shelf)}
        game.quaffed = []
        game.entrance = entrance.y, entrance.x
        game.position = outside["player"]["y"], outside["player"]["x"]
        game.turn = outside["turn"]
        _, _, executor = self.make(game)
        executor.drain = lambda: [game._state()]
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 5).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2,
                                  policy=policy)
        reasons = [(key, policy.last_reason)]
        current = board
        for _ in range(limit):
            _send_new_decision_key(
                port, json.dumps(game._state()), key, None, set(),
                in_store=current.store is not None, snapshot=current,
                decision={"sequence": policy._decision_sequence,
                          "reason": policy.last_reason, "key": key})
            self.assertEqual(port.last_result.outcome, "completed",
                             (reasons, port.last_result.reason))
            policy.confirm_key_posted(key)
            if game.left_for is not None:
                break
            current = parse_snapshot(port.last_result.board, policy._monrace_knowledge)
            key = policy.choose_key(current)
            reasons.append((key, policy.last_reason))
            if policy.last_reason.startswith(("town:recall", "town:blocked")):
                break
        return game, reasons

    def test_the_whole_taken_stack_leaves_the_catalogue(self):
        policy, board = self.to_row_21()
        catalogue = policy._home_knowledge_items
        # Rows 14 and 16 took 賢さの薬 x1 and 知能の薬 x2 whole: neither is listed.
        self.assertEqual([kind for kind in kinds(catalogue) if consumable_policy.drink_row(
            next(item for item in catalogue if (item.tval, item.sval) == kind))],
                         [STR_KIND])
        self.assertNotIn(INT_KIND, kinds(catalogue))
        ware = item_fate.sweep_ware(policy, board, catalogue)
        self.assertFalse(ware is not None and (ware[1].tval, ware[1].sval) == INT_KIND)

    def test_row_21_takes_the_useful_stack_and_never_the_absent_one(self):
        """Recorded row 22: ``~9`` full-home-sale (the absent 知能の薬 take) -> the burst."""
        policy, board = self.to_row_21()
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("5pk2\r\x1b", "home:atomic-withdraw"))
        self.assertEqual(policy._home_pending_item[1:], STR_KIND)
        shelf = [store_row(item) for item in policy._home_knowledge_items]
        game, reasons = self.drive(policy, board, key, shelf)
        self.assertEqual(game.quaffed, ["腕力の薬", "腕力の薬"], reasons)
        self.assertFalse([reason for _key, reason in reasons
                          if "full-home-sale" in reason or reason.startswith("town:blocked")
                          or "reservation-unavailable" in reason], reasons)
        self.assertFalse([item for item in (*game.pack, *game._items())
                          if (item["tval"], item["sval"]) == INT_KIND])

    def test_a_surplus_home_stack_is_the_sweeps_and_sold(self):
        policy, board = self.to_row_21()
        # DECLARED CONSTRUCTED: the Home still holds a 知能の薬 x2 stack (a fresh ~9 list).
        catalogue = list(policy._home_knowledge_items)
        strength = next(index for index, item in enumerate(catalogue)
                        if (item.tval, item.sval) == STR_KIND)
        stack = replace(catalogue[strength], name="知能の薬", sval=INTELLIGENCE,
                        slot=str(strength + 1))
        catalogue.insert(strength + 1, stack)
        policy.consume_home_knowledge(tuple(catalogue))
        self.assertTrue(policy._home_knowledge_current)
        home_int = next(item for item in policy._home_knowledge_items
                        if (item.tval, item.sval) == INT_KIND)
        # The drinker does not list it (INT at its maximum); it is surplus, the sweep's ware.
        self.assertEqual(kinds(consumable_policy.home_potions_to_drink(policy, board)), [STR_KIND])
        self.assertTrue(item_use_route.surplus(policy, board, home_int))
        key = policy.choose_key(board)
        shelf = [store_row(item) for item in policy._home_knowledge_items]
        game, reasons = self.drive(policy, board, key, shelf)
        # The sweep takes the surplus stack out and walks to sell it; nothing drinks it.
        self.assertEqual(reasons[:2], [("5pl2\r\x1b", "home-errand:atomic-withdraw:full-home-sale"),
                                       ("\x1b`n%.", "shop:approach")], reasons)
        self.assertEqual(game.quaffed, [])
        carried = [item for item in game.pack if (item["tval"], item["sval"]) == INT_KIND]
        self.assertEqual([item["count"] for item in carried], [2], reasons)
        self.assertIsNotNone(game.left_for, reasons)
        # The useful stack stays the drinker's: still on the Home shelf for its take.
        after = parse_snapshot(game._state(), policy._monrace_knowledge)
        self.assertIn(STR_KIND, [(item["tval"], item["sval"]) for item in game._items()])
        taken = next(item for item in after.inventory if (item.tval, item.sval) == INT_KIND)
        self.assertTrue(item_use_route.surplus(policy, after, taken))
        self.assertFalse(consumable_policy.drunk_now(after, taken))

    def test_a_carried_potion_past_the_maximum_is_released_to_the_sale(self):
        policy, board = self.to_row_21()
        raw = self.raw(21)
        # DECLARED CONSTRUCTED: a second 知能の薬 still carried after INT reached its maximum.
        home_strength = next(item for item in policy._home_knowledge_items
                             if (item.tval, item.sval) == STR_KIND)
        used = {item["slot"] for item in raw["inventory"]}
        raw["inventory"].append(dict(store_row(home_strength), name="知能の薬", sval=INTELLIGENCE,
                                     count=1, slot=next(c for c in "abcdefghijklmnopqrstuvw"
                                                        if c not in used)))
        carried_board = parse_snapshot(raw, policy._monrace_knowledge)
        carried = next(item for item in carried_board.inventory
                       if (item.tval, item.sval) == INT_KIND)
        self.assertFalse(consumable_policy.drunk_now(carried_board, carried))
        self.assertIsNone(policy._stat_gain_quaff_key(carried_board, []))
        self.assertEqual(policy._retention_reservation_detail(carried_board, carried)[0], 0)
        self.assertTrue(item_use_route.surplus(policy, carried_board, carried))
        self.assertFalse(policy._home_deposit_candidate(carried, carried_board))


if __name__ == "__main__":
    unittest.main()
