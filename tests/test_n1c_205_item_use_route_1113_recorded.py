"""n1-c life-205 keeps items no consumer uses (item-use-route-1113).

Owner 2026-11-13 (verbatim): 「n1-cの現状を見ると、挑まないQ25用のアイテム、使用経路のない薬や巻物、
魔道具術師では不要な解呪、捨てると決めた岩石溶解を持っている。アイテムが整理できていない。」

Recorded: two town-arrival checkpoints of the Lv45 zombie Magic-Eater
(tests/extract_n1c_205_item_use_route_1113_fixture.py), replayed through the public chooser and
the live CLI's owner-retirement entrance (--owner-retired-log-only):

 * ``v1329`` (2026-11-13 13:29, the Home list current at the arrival).  The pack held Potions of
   Speed x2 although the absorbed Speed staff is reliable (96%, owner 2026-11-01: no potion is
   carried), *Remove Curse* x1 and the Home Remove Curse x19 / *Identify* x6 although the
   absorbed Remove Curse and Perception staffs' powerful activation replaces them (owner
   2026-10-31, 2026-11-13), Stone to Mud wands x7 although the absorbed power is at its 99 cap
   (owner 2026-11-07 / 11-13), and Home devices the device table never absorbs.  Row 8 is the
   Magic shop page after the recorded sale: the recorded bot left (``shop:in-store-done``).
 * ``v1336`` (13:36).  Row 3's weight-overload deposit shelved the Remove Curse scroll (slot l)
   at Home with the bolts and the unidentified weapons.

Fix: item_use_route's consumer table: an item with no live consumer keeps no reservation, is
never shelved, is sold where a store buys it (the town organization sale; the Home sweep for a
Home copy) and is never bought back; me_capability.REPLACES gains the Remove Curse scroll row.

Walls: none.  The Q25 carries (Restore Strength, Enlightenment) stay: the bot's own Q25
readiness is short only of Restore Life Levels 0/2 and Restore Strength 1/2, so the plan is live
(the report's owner question).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import base64
import copy
import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hengbot import item_fate, item_use_route
from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _handle_owner_retirement, _send_new_decision_key,
)
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from tests.support.recorded import FaithfulHookGame, ProductionHarness, store_screen


FIXTURES = Path(__file__).with_name("fixtures") / "n1c-205-item-use-route-1113"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
POTION, SCROLL, ROD, WAND, STAFF = 75, 70, 66, 65, 55
SPEED, STAR_REMOVE_CURSE, REMOVE_CURSE, STONE_TO_MUD = (POTION, 29), (SCROLL, 15), (SCROLL, 14), (WAND, 6)
# What some consumer uses: the essentials and the other kept kinds of the two packs.
KEPT_PACK = {
    (POTION, 30): "oneshot_breath.DRINKS",              # Resist Heat
    (POTION, 32): "heroism_potion",                     # Heroism x15 (owner 2026-11-11)
    (POTION, 36): "supply-ledger:cure",
    (POTION, 37): "policy_constants.HEAL_ORDER",        # Healing
    (POTION, 38): "policy_constants.HEAL_ORDER",        # *Healing*
    (POTION, 42): "stat-restore",                       # Restore Strength (and the Q25 carry)
    (POTION, 56): "quest_optional_carry",               # Enlightenment (Q25 optional carry)
    (POTION, 60): "resist_potion",
    (POTION, 61): "owner-pending",                      # Curing: no consumer yet (Q-ITEM-1)
    (SCROLL, 8): "policy_combat:relocation",            # Phase Door
    (SCROLL, 9): "supply-ledger:teleport",
    (SCROLL, 11): "supply-ledger:recall",
    (SCROLL, 12): "identification",
    (WAND, 24): "mana-food:staple",                     # Wand of Wonder
}
SURPLUS_PACK_1329 = {SPEED, STAR_REMOVE_CURSE, STONE_TO_MUD, (WAND, 13)}   # 13: Polymorph wand
SURPLUS_HOME_1329 = {
    (SCROLL, 13), REMOVE_CURSE, (SCROLL, 24),           # *Identify*, Remove Curse, Light
    (ROD, 7), (ROD, 16), (ROD, 17), (ROD, 19),          # Probing, Sleep, Slow, Polymorph rods
    (WAND, 8), (STAFF, 21), (STAFF, 30),                # Sleep wand, Slow Monsters, Animate Dead
}


def kind(item):
    return item.tval, item.sval


class N1c205ItemUseRoute1113RecordedTest(ProductionHarness):
    def load(self, name):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        fixture, visit = FIXTURES / name, Path(scratch.name) / "town-arrival"
        (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
        (visit / POLICY_FILE).write_bytes(lzma.decompress((fixture / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((fixture / "journal.jsonl.xz").read_bytes())))
        sidecars = json.loads(lzma.decompress((fixture / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(
            json.dumps(sidecars["manifest"], ensure_ascii=False), encoding="utf-8")
        for role, data in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(base64.b64decode(data))
        runtime = Path(scratch.name) / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path", runtime)
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def replay_live(self, policy, recorded, steps):
        for row, supply in steps:
            board = supply()
            visit_before = copy.copy(policy._store_visit)
            chosen = policy.choose_key(board)
            self.assertEqual((chosen, policy.last_reason),
                             (recorded[row["row"]]["key"], recorded[row["row"]]["reason"]),
                             row["row"])
            key = policy.validate_read_key(board, chosen)
            key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
            if key:
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def post(self, board, key, reason):
        """The entrance and ``key`` through the production executor port (the Magic shop's
        page answers both: DECLARED CONSTRUCTED game replies)."""
        game = FaithfulHookGame()
        state = dict(self.store_state(board.turn), store={"store_type": board.store.store_type,
                                                          "items": []})
        game.screens = [store_screen(), store_screen()]
        game.states = [state, dict(state, turn=board.turn + 1)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        posted = set()
        for sequence, (surface, sent_key, in_store) in enumerate(
                (("entrance", "5", False), ("magic", key, True)), 1):
            sent, _line = _send_new_decision_key(
                port, surface, sent_key, None, posted, in_store=in_store,
                decision={"sequence": sequence, "reason": reason},
                snapshot=board, posting_contract=PostingContract())
            self.assertTrue(sent, sent_key)
        return game.accepted

    def test_arrival_names_exactly_the_surplus(self):
        """v1329 row 0: every carried and Home kind is kept by a consumer, or is surplus."""
        policy, recorded, steps = self.load("v1329")
        board = steps[0][1]()
        self.assertTrue(policy._home_knowledge_current)
        pack = {kind(item): item_use_route.uses(policy, board, item) for item in board.inventory
                if item_use_route.in_scope(board, item)}
        self.assertEqual({k for k, uses in pack.items() if not uses}, SURPLUS_PACK_1329)
        for k, consumer in KEPT_PACK.items():
            if k in pack:
                self.assertIn(consumer, pack[k], k)
        home = {kind(item) for item in policy._home_knowledge_items
                if item_use_route.surplus(policy, board, item)}
        self.assertEqual(home, SURPLUS_HOME_1329)
        for item in board.inventory:
            if kind(item) in SURPLUS_PACK_1329:
                self.assertEqual(policy._retention_reservation_detail(board, item), (0, None))
                self.assertFalse(policy._home_deposit_candidate(item, board))
        # The survival kit keeps its own reservation (owner: survival first).
        reserved = {kind(item): policy._retention_reservation_detail(board, item)[1]
                    for item in board.inventory}
        self.assertEqual(reserved[(SCROLL, 11)], "supply-ledger:recall")
        self.assertEqual(reserved[(POTION, 32)], "heroism-carry")
        self.assertEqual(reserved[(POTION, 60)], "resistance-potion")

    def test_magic_shop_sells_the_replaced_speed_potions(self):
        """v1329 row 8, the Magic shop.  Live: ``\\x1b`` shop:in-store-done (kept them)."""
        policy, recorded, steps = self.load("v1329")
        self.assertEqual((recorded[8]["key"], recorded[8]["reason"]), ("\x1b", "shop:in-store-done"))
        self.replay_live(policy, recorded, steps[:8])
        board = steps[8][1]()
        self.assertEqual(board.store.store_type, 5)
        speed = next(item for item in board.inventory if kind(item) == SPEED)
        self.assertEqual((speed.slot, speed.count), ("a", 2))
        self.assertTrue(policy._entire_stack_is_surplus(board, speed))
        self.assertIs(policy._find_town_organization_surplus(board), speed)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("{a@0\r", "shop:in-store-inscribe"))
        self.assertEqual(self.post(board, key, policy.last_reason), ["5", "{a@0\r"])
        # Nothing no consumer uses is bought back from this page.
        for ware in board.store.items:
            if item_use_route.surplus(policy, board, ware):
                self.assertEqual(policy._matching_live_purchase_rungs(board, ware), (), ware.name)
        self.assertFalse(any(item_use_route.surplus(policy, board, ware)
                             for ware in [policy._next_purchase(board)] if ware is not None))

    def test_home_sweep_takes_a_home_surplus_out_for_sale(self):
        """v1329 row 0: the Home sweep's ware is a Home kind no consumer uses."""
        policy, recorded, steps = self.load("v1329")
        board = steps[0][1]()
        ware = item_fate.sweep_ware(policy, board, policy._home_knowledge_items)
        self.assertIsNotNone(ware)
        (result, _store, _value), stock = ware
        self.assertIn(kind(stock), SURPLUS_HOME_1329)
        self.assertEqual(policy._retention_reservation(board, result), 0)

    def test_enlightenment_waits_at_home_for_q25(self):
        """v1329 row 0, DECLARED CONSTRUCTED: no quest is being prepared.  The Home
        Enlightenment still waits for Q25, untaken (owner 2026-11-05 「自宅にある場合は受注前に
        持ち出して」)."""
        policy, recorded, steps = self.load("v1329")
        board = steps[0][1]()
        self.assertNotIn(25, board.quests)
        stock = next(item for item in policy._home_knowledge_items if kind(item) == (POTION, 56))
        with patch.object(type(policy), "_carry_procurement_strategy", lambda *args, **kw: None),                 patch.object(type(policy), "_quest_strategy_for_errand_or_floor", lambda *args: None):
            self.assertEqual(item_use_route.uses(policy, board, stock), ("quest_optional_carry",))

    def test_no_buyer_makes_it_junk(self):
        """v1336 row 3, DECLARED CONSTRUCTED: no store buys the Remove Curse scroll."""
        policy, recorded, steps = self.load("v1336")
        self.replay_live(policy, recorded, steps[:3])
        board = steps[3][1]()
        scroll = next(item for item in board.inventory if kind(item) == REMOVE_CURSE)
        self.assertIsNone(policy._junk_class(board, scroll))
        policy._unsellable_items.add(policy._item_signature(scroll))
        self.assertEqual(policy._junk_class(board, scroll), "no-use-route")

    def test_surplus_is_never_bought(self):
        """v1329 row 13, the Alchemist page where the recorded bot bought Teleportation (``pd2``).

        DECLARED CONSTRUCTED: the table without the Teleportation rows, so the scroll has no
        consumer; then no purchase rung takes it.  (The departure ledger's own requirement still
        would: its kinds always have a survival row, tests/test_item_use_route_lint.py.)"""
        policy, recorded, steps = self.load("v1329")
        self.assertEqual((recorded[13]["key"], recorded[13]["reason"]), ("pd2\r\r", "shop:in-store-buy"))
        boards = [supply() for _row, supply in steps]
        board = boards[13]
        ware = next(item for item in board.store.items if item.letter == "d")
        self.assertEqual(kind(ware), (SCROLL, 9))
        self.assertNotEqual(policy._matching_live_purchase_rungs(board, ware), ())
        routes = tuple(route for route in item_use_route.ROUTES
                       if (route.tval, route.sval) not in {(SCROLL, 9), (SCROLL, None)})
        with patch.object(item_use_route, "ROUTES", routes):
            self.assertTrue(item_use_route.surplus(policy, board, ware))
            self.assertEqual(policy._matching_live_purchase_rungs(board, ware), ())

    def test_home_deposit_leaves_the_remove_curse_scroll_for_sale(self):
        """v1336 row 3, Home.  Live: ``dv25\\rdtdsdrdl\\x1b`` (shelved slot l, Remove Curse)."""
        policy, recorded, steps = self.load("v1336")
        self.assertEqual(recorded[3]["key"], "dv25\rdtdsdrdl\x1b")
        self.replay_live(policy, recorded, steps[:3])
        board = steps[3][1]()
        scroll = next(item for item in board.inventory if kind(item) == REMOVE_CURSE)
        self.assertEqual(scroll.slot, "l")
        self.assertEqual(item_use_route.uses(policy, board, scroll), ())
        self.assertTrue(item_use_route.has_buyer(policy, scroll))
        self.assertFalse(policy._home_deposit_candidate(scroll, board))
        # The table's 「自宅に片付ける」 no longer keeps it from its buyer.
        self.assertIsNotNone(policy._town_organization_sale_store(board, scroll))
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         ("dv25\rdtdsdr\x1b", "home:weight-overload-deposit"))


if __name__ == "__main__":
    unittest.main()
