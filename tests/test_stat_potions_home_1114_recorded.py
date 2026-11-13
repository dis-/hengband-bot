"""The "drink at once" potions at Home are taken out and drunk (stat-potions-home-1114).

Owner 2026-11-13 「自宅に器用さの薬、耐久力の薬など即飲む指示にした薬が蓄積されている。調査して改善。」
The owner's table (consumable_policy.json) marks the stat potions 「拾って使う」.  n1-c life-207
shelved unknown flavours at Home (policy_home ``protected_unknown_consumable``, deepest level
20+): 藍色の薬 (home-withdraw-history.jsonc turn 992709) and 茶斑の薬 (turn 2571185).  A carried
copy of each flavour was identified later (snapshots: turn 2620855 「ザック中: 腕力の薬(h)」, 2622884
「ザック中: 知能の薬(i)」, 4147183 「ザック中: 賢さの薬(g)」, object awareness is per kind) and drunk,
but the Home copies became the Potions of Strength x2, Intelligence x2 and Wisdom x1 and stayed:
the stat-gain quaff reads only the pack, and the Home take for drinking covered only *Enlightenment*
and Self Knowledge.

Recorded: n1-c life-207's town-arrival checkpoint 20261114-040255 (turn 5150183) and its first
journal rows (tests/extract_stat_potions_home_1114_fixture.py).  Row 0 replays; row 1 (recorded
``9`` shop:approach, the Temple) now files the Home take.

Fix: consumable_policy.DRINK_AT_ONCE is the one table of the "drink at once" potions with their
conditions; the Home take (policy_home._bind_home_drink_potion_withdrawal) and the retention read
it, and a potion that does nothing for this character (every stat it raises at the maximum, not
drained: status/base-status.cpp inc_stat) is surplus (item_use_route).

DECLARED CONSTRUCTED: the Home and its entrance (``StatPotionHomeGame``, the arrival's Home
catalogue as its shelf, kept in the catalogue's order), the quaff's effect (the stack shrinks),
and the at-maximum board (the sheet's '!' mark on STR).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import lzma
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import consumable_policy, item_use_route
from hengbot.cli import _ExecutorInputPort, _send_new_decision_key
from hengbot.model import STORE_HOME, TVAL_POTION, parse_snapshot
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import decisions, restore
from tests.support import recorded as harness
from tests.support.recorded import QUAFF_PROMPT
from tests.test_town_withdraw_pack_budget_recorded import HomeEntranceGame

FIXTURE = Path(__file__).with_name("fixtures") / "stat-potions-home-1114"
STRENGTH, INTELLIGENCE, WISDOM = 48, 49, 50
HOME_POTIONS = [("10", "腕力の薬", 2), ("11", "知能の薬", 2), ("12", "賢さの薬", 1)]


def store_row(item):
    """The Home shelf entry of a catalogue item (the ~9 / store page fields)."""
    return {"ac": item.ac, "aware": item.aware, "charges": item.charges, "charging": False,
            "count": item.count, "damage_dice": {"num": item.damage_dice_num,
                                                 "sides": item.damage_dice_sides},
            "fully_known": item.fully_known, "inscription": item.inscription,
            "is_artifact": item.is_artifact, "is_bounty": item.is_bounty,
            "is_broken": item.is_broken, "is_cursed": item.is_cursed, "is_ego": item.is_ego,
            "is_equipment": item.is_equipment, "known": item.known,
            "known_flags": sorted(item.known_flags), "name": item.name, "price": 0,
            "pval": item.pval, "sval": item.sval, "to_a": item.to_a, "to_d": item.to_d,
            "to_h": item.to_h, "tval": item.tval, "weight": item.weight}


class StatPotionHomeGame(HomeEntranceGame):
    """DECLARED CONSTRUCTED: the Home shelf keeps its order; a quaff uses one potion.

    cmd-item/cmd-quaff.cpp do_cmd_quaff_potion opens the item prompt; the chosen
    stack loses one (the stat change is not modelled).
    """
    order = None
    quaffed = None

    def _sort_key(self, item):
        return self.order.get(item["name"], len(self.order))

    def _consume(self, keys):
        for key in keys:
            if self.pending == "quaff":
                self.trace.append(key)
                self.pending = None
                potion = self._letters(self.pack).get(key)
                self.quaffed.append(potion["name"])
                potion["count"] -= 1
                if potion["count"] == 0:
                    self.pack.remove(potion)
                self.turn += 1
            elif key == "q" and not self.inside and self.pending is None and self.modal is None:
                self.trace.append(key)
                self.pending = "quaff"
            else:
                super()._consume(key)

    def request(self, request):
        response = super().request(request)
        if request["op"] == "screen" and self.pending == "quaff":
            response["result"]["lines"][0] = QUAFF_PROMPT
        return response


class StatPotionsHome1114RecordedTest(harness.ProductionHarness):
    def load(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name)
        visit, runtime = root / "town-arrival", root / "runtime"
        visit.mkdir()
        runtime.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(
            gzip.compress(lzma.decompress((FIXTURE / "journal.jsonl.xz").read_bytes())))
        self.journal = [json.loads(line) for line in
                        lzma.decompress((FIXTURE / "journal.jsonl.xz").read_bytes()).splitlines()]
        policy = restore(visit, runtime)
        self.addCleanup(lambda: policy._home_disposal.history_path.unlink(missing_ok=True))
        return policy, list(decisions(policy, visit, runtime))

    def raw(self, row):
        entry = self.journal[row]
        return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])

    def replay(self, policy, rows):
        for recorded, supply in rows:
            board = supply()
            key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
            policy.confirm_key_posted(key)

    def test_the_arrival_home_holds_the_drink_at_once_potions(self):
        policy, rows = self.load()
        self.assertEqual((rows[1][0]["key"], rows[1][0]["reason"]), ("9", "shop:approach"))
        held = [(item.slot, item.name, item.count) for item in policy._home_knowledge_items
                if item.tval == TVAL_POTION and item.aware
                and consumable_policy.drink_row(item) is not None]
        self.assertEqual(held, HOME_POTIONS)
        self.assertTrue(policy._home_knowledge_current)

    def test_home_potions_are_taken_out_and_drunk_through_the_executor(self):
        policy, rows = self.load()
        self.replay(policy, rows[:1])
        board = rows[1][1]()
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("\x1b`n(.", "shop:travel"))
        self.assertEqual(policy._home_pending_item[1:], (TVAL_POTION, WISDOM))
        self.assertEqual(policy._store_visit.store_type, STORE_HOME)
        policy.confirm_key_posted(key)

        outside = self.raw(1)
        entrance = next(grid.position for grid in board.grids.values()
                        if grid.store_number == STORE_HOME)
        catalogue = policy._home_knowledge_items[:policy._home_knowledge_valid_before]
        shelf = [store_row(item) for item in catalogue]
        game = StatPotionHomeGame(
            pack=copy.deepcopy(outside["inventory"]),
            equipment={item["slot"]: item for item in copy.deepcopy(outside["equipment"])},
            pages=[shelf[index:index + 52] for index in range(0, len(shelf), 52)],
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
        reasons = []
        current = board
        for _ in range(40):
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
        # The last shelf slot first, each stack whole; drunk before the next take.
        self.assertEqual(game.quaffed, ["賢さの薬", "知能の薬", "知能の薬", "腕力の薬", "腕力の薬"],
                         reasons)
        takes = [(key, reason) for key, reason in reasons
                 if reason in {"home:atomic-withdraw", "stat-gain:quaff"}]
        self.assertEqual(takes, [("5pm\x1b", "home:atomic-withdraw"), ("qj", "stat-gain:quaff"),
                                 ("5pl2\r\x1b", "home:atomic-withdraw"), ("qj", "stat-gain:quaff"),
                                 ("qj", "stat-gain:quaff"),
                                 ("5pk2\r\x1b", "home:atomic-withdraw"), ("qj", "stat-gain:quaff"),
                                 ("qj", "stat-gain:quaff")], reasons)
        self.assertFalse(policy._deferred_home_items, reasons)
        self.assertFalse([item["name"] for item in game._items()
                          if (item["tval"], item["sval"]) in {(TVAL_POTION, STRENGTH),
                                                              (TVAL_POTION, INTELLIGENCE),
                                                              (TVAL_POTION, WISDOM)}])
        self.assertIsNotNone(game.left_for, reasons)

    def test_a_stat_at_its_maximum_leaves_its_potion_surplus(self):
        policy, rows = self.load()
        self.replay(policy, rows[:1])
        raw = self.raw(1)
        # DECLARED CONSTRUCTED: STR at the character's maximum (the sheet's '!').
        raw["player"]["stats"]["str"]["at_racial_max"] = True
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual(board.player.stats_at_max, ("str",))
        home = {item.sval: item for item in policy._home_knowledge_items
                if item.tval == TVAL_POTION and item.sval in (STRENGTH, INTELLIGENCE)}
        self.assertTrue(item_use_route.surplus(policy, board, home[STRENGTH]))
        self.assertFalse(item_use_route.surplus(policy, board, home[INTELLIGENCE]))
        self.assertEqual([item.name for item in consumable_policy.home_potions_to_drink(policy, board)],
                         ["知能の薬", "賢さの薬"])
        # DECLARED CONSTRUCTED: a carried Potion of Strength is not drunk and not kept.
        potion = dict(store_row(home[STRENGTH]), slot="j", count=1)
        raw["inventory"].append(potion)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        carried = next(item for item in board.inventory if item.sval == STRENGTH
                       and item.tval == TVAL_POTION)
        self.assertIsNone(policy._stat_gain_quaff_key(board, []))
        self.assertEqual(policy._retention_reservation_detail(board, carried)[0], 0)
        self.assertFalse(policy._home_deposit_candidate(carried, board))
        # Drained, the potion restores STR first (do_inc_stat: res_stat): drunk again.
        raw["player"]["stats"]["str"]["drained"] = True
        drained = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertTrue(consumable_policy.drunk_now(drained, carried))

    def test_every_use_potion_has_one_drinker(self):
        """A 「拾って使う」 potion is drunk at once (DRINK_AT_ONCE) or by its named owner."""
        rows = consumable_policy.consumables()
        used = {kind for kind, entry in rows.items() if entry.use and kind[0] == TVAL_POTION}
        owned = {kind for kind in consumable_policy.USE_OWNED_ELSEWHERE if kind[0] == TVAL_POTION}
        self.assertEqual(used, set(consumable_policy.DRINK_AT_ONCE) | owned)
        self.assertFalse(set(consumable_policy.DRINK_AT_ONCE) & owned)


if __name__ == "__main__":
    unittest.main()
