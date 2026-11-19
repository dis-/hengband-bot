"""n1-c life-217 2026-11-19 16:44:00, no-key-exhausted (bot main 96e6938927): a full store.

The Home cap tidy (home_cap) sells many wares in one visit, so a store fills up.  The Magic shop
refused the one-shot sale of the Staff of Detect Objects {@2} with 「すいませんが、店にはもう置く
場所がありません。」 (store/sell-order.cpp store_sell: store_check_num finds no free slot, the
store's stock limit of store.cpp check_free_space); the sale's 'y' then reached the store's
command loop (「そのコマンドは店の中では使えません。」) and its ESC left the store.  The sale's watch
waited for an effect that could never come, the next entry found it still owning the page, and
the bot sent no key.

Earlier the same visit (16:15:43, decision 573) the same refusal of an in-store sale was read as
a broken in-store transport (refused:store-command) and tripped the in-store breaker, which
stays on across restarts and sends every later sale through one entry per ware.

Now the refusal is a full store: the store takes no more sales this visit
(``_store_sale_refused``), the sale's watch and the visit's posted operation end, the breaker
stays clear, and the relief's ware goes to another store that buys it -- the Black Market last,
which buys every kind (store/service-checker.cpp switch_store_check's default).

Recorded: the stop's last six boards (tests/extract_n1c_217_store_full_1119_fixture.py) and the
character's town-arrival checkpoint of the same visit 29 minutes earlier
(tests/fixtures/n1c-217-home-cap-deadline-1119): the restarted process's own checkpoint is not
in the capture.

DECLARED CONSTRUCTED: the posted one-shot sale (its store visit and its sale watch, as the
decision log of decisions 9-10 shows them: Magic shop, 'd2y<ESC>', tag @2), the refusal board
carrying both refusal messages as the decision log's decision 11 shows them, and the cap tidy's
relief holding the staff as its batch sale.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot import me_device_policy
from hengbot.home_full_relief import HomeFullRelief
from hengbot.model import STORE_BLACK, STORE_FULL_SALE_MESSAGES, STORE_MAGIC, parse_snapshot
from hengbot.policy_constants import IN_STORE_SELL_REASON
from hengbot.policy_types import StoreVisit, StoreVisitPhase
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-home-cap-deadline-1119"
BOARDS = Path(__file__).with_name("fixtures") / "n1c-217-store-full-1119" / "boards.jsonl.xz"


class N1c217StoreFull1119RecordedTest(unittest.TestCase):
    def setUp(self):
        # DECLARED CONSTRUCTED: the staff is the relief's sale ware, as recorded.  Owner
        # 2026-11-19 「魔法道具を自宅にため込んでいる。魔道具術師の処理ルールに従って処分」 now
        # absorbs a carried charged Staff of Object Location (absorb_now, 25 of 99) in town
        # (me_device_policy.absorbed_in_town, tests/test_me_home_devices_1119_recorded); the
        # full store's handling is asked of a ware the table does not absorb.
        patcher = patch.object(me_device_policy, "absorbed_in_town", lambda *args: False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.scratch = TemporaryDirectory()
        self.policy, _, steps = load(FIXTURE, Path(self.scratch.name))
        raw = [json.loads(line) for line in lzma.decompress(BOARDS.read_bytes()).splitlines()]
        (self.page, self.full, self.stray, self.outside, self.outside2,
         self.reentered) = [parse_snapshot(row, self.policy._monrace_knowledge) for row in raw]
        # The run's first board (the restarted process's visit).
        self.policy.choose_key(self.outside2)
        self.staff = next(item for item in self.page.inventory if "@2" in item.name)

    def tearDown(self):
        self.scratch.cleanup()

    def post_sale(self):
        policy, staff = self.policy, self.staff
        policy._store_visit = StoreVisit(
            owner="shop-one-shot", purpose="observed-transaction", store_type=STORE_MAGIC,
            phase=StoreVisitPhase.APPROACHING, opened_sequence=policy._decision_sequence,
            operation_posted=True, operation_released=True, composed_key="d2y\x1b",
            posted_sequence=policy._decision_sequence, posted_turn=self.page.turn)
        policy._batch_sell_pending = {
            "store_type": STORE_MAGIC, "phase": "await-sale",
            "entries": [{"signature": policy._sale_item_identity(staff), "tag": "2",
                         "count": staff.count, "quantity": staff.count}],
            "before_gold": self.page.player.gold, "wait_count": 0}

    def refusal_board(self):
        """Decision 11's board: outside, with the two refusal messages."""
        return replace(self.outside, messages=(*self.full.messages, *self.stray.messages))

    def test_the_recorded_refusal(self):
        self.assertEqual(self.page.store.store_type, STORE_MAGIC)
        self.assertTrue(set(self.full.messages) & STORE_FULL_SALE_MESSAGES)
        self.assertEqual(self.stray.messages, ("そのコマンドは店の中では使えません。",))
        self.assertEqual(self.reentered.store.store_type, STORE_MAGIC)

    def test_a_full_store_ends_the_sale_and_never_leaves_the_bot_without_a_key(self):
        policy = self.policy
        self.post_sale()
        key = policy.choose_key(self.refusal_board())
        policy.confirm_key_posted(key)
        self.assertIn(STORE_MAGIC, policy._store_sale_refused)
        self.assertIsNone(policy._batch_sell_pending)
        self.assertEqual(policy._store_visit_last_closed.outcome, "one-shot-sale-store-full")
        # The re-entered page (the stop's board) gets a key.
        key = policy.choose_key(self.reentered)
        self.assertNotEqual(key, "")
        self.assertNotEqual(policy.last_reason, "shop:one-shot-in-flight")

    def test_the_relief_sells_the_ware_to_another_store(self):
        policy, board = self.policy, self.outside
        before = sum(item.count for item in board.inventory
                     if policy._sale_item_identity(item) == policy._sale_item_identity(self.staff))
        policy._home_full_relief = HomeFullRelief(
            remaining=10, town=policy._effective_town_id(board), cap=True,
            sale=(policy._item_signature(self.staff), STORE_MAGIC, before - self.staff.count),
            withdrawn=True, pack_only=True, mode="sale",
            rank_released=policy._item_signature(self.staff))
        policy._store_sale_refused.add(STORE_MAGIC)
        policy._home_full_relief_key(board)
        relief = policy._home_full_relief
        self.assertIsNotNone(relief)
        self.assertEqual(relief.sale[0], policy._item_signature(self.staff))
        # Only the Magic shop and the Black Market buy a staff: the Black Market.
        self.assertEqual(relief.sale[1], STORE_BLACK)

    def test_with_every_buyer_full_the_tidy_keeps_the_ware(self):
        policy, board = self.policy, self.outside
        signature = policy._item_signature(self.staff)
        before = sum(item.count for item in board.inventory
                     if policy._sale_item_identity(item) == policy._sale_item_identity(self.staff))
        policy._home_full_relief = HomeFullRelief(
            remaining=10, town=policy._effective_town_id(board), cap=True,
            sale=(signature, STORE_MAGIC, before - self.staff.count),
            withdrawn=True, pack_only=True, mode="sale", rank_released=signature)
        policy._store_sale_refused.update({STORE_MAGIC, STORE_BLACK})
        # Today's disposal rule would destroy it (no store takes it now) ...
        self.assertIsNotNone(policy._home_full_discard_candidate(board, self.staff))
        policy._home_full_relief_key(board)
        relief = policy._home_full_relief
        # ... the cap tidy keeps it: its fate is not destroy.
        self.assertNotEqual(relief.mode, "destroy")
        self.assertEqual(relief.skipped.get(signature), "sale-refused-item-protected")

    def test_an_in_store_full_refusal_trips_no_breaker(self):
        policy = self.policy
        self.post_sale()
        policy.reconcile_input_operation(IN_STORE_SELL_REASON, "refused:store-full")
        self.assertIsNone(getattr(policy, "_in_store_breaker", None))
        self.assertIn(STORE_MAGIC, policy._store_sale_refused)
        self.assertIsNone(policy._batch_sell_pending)
        self.assertFalse(policy._store_visit.operation_posted)
        # A command the store loop refused for any other cause still trips it.
        self.post_sale()
        policy.reconcile_input_operation(IN_STORE_SELL_REASON, "refused:store-command")
        self.assertEqual(policy._in_store_breaker[0], "store-command-refused")


if __name__ == "__main__":
    unittest.main()
