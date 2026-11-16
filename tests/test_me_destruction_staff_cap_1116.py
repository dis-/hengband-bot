"""The Magic-Eater's Staff of *Destruction* at its absorbed count (owner 2026-11-16).

Owner (verbatim): 「破壊の杖の優先購入だが、魔道具術師で取り込み回数が50を超えたらやめる。
取り込み回数99なら杖を拾わず壊す。」

1. The Black Market's priority purchase of the staff (bm_destruction_fund, owner 2026-11-07 /
   11-15 「何本でも買う」 and the sale of Home's spares for it) stops for a Magic-Eater whose
   absorbed *Destruction* count is above 50 (``bm_destruction_fund.staff_wanted``).
2. At 99 the staff on the floor is walked to and destroyed where it lies
   (``me_capped_pickup.destroy_key``: ``0<count>k-``), not picked up.

Substrates:

* n1-b life-408 (Lv19 Magic-Eater, 2026-11, state.jsonl line 4484, turn 1287297): its own
  Black Market page shelving ``*破壊*の杖 (5回分)`` at 50,748 gold with 11,181 carried
  (tests/fixtures/n1b-408-bm-destruction-staff-1116.json.gz, the board as recorded).
* DECLARED CONSTRUCTED: tests/test_black_market_optional_quantity's town with every departure
  price seen, as a Magic-Eater's, its Black Market page shelving two staves beside Potions of
  Speed with the gold for all of them; no recorded Magic-Eater page has that gold (n1-b
  life-408's had 11,181 for a 50,748 staff), and the recorded Black Market replays
  (tests/test_bm_destruction_fund_recorded, test_bm_destruction_sell_all_1115_recorded) are red
  on main.
* n1c-205-stuck-recall-1113 (tests/test_me_capped_pickup_1113): a Lv38 zombie Magic-Eater's
  seek-loot walk onto the pile at (18,14).  DECLARED CONSTRUCTED: the pile is one known Staff
  of *Destruction* (tval 55, sval 29), still there on the board standing on it; no recorded
  board shows that staff on the floor.

The absorbed count is the displayed staff list's row (me_capability.count), dated before the
window as a list read earlier in the life is; its name is the device table's 「*破壊*」.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from dataclasses import replace
from pathlib import Path
import unittest

from hengbot import bm_destruction_fund, me_capped_pickup
from hengbot.model import Position, STORE_BLACK, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.model import SV_POTION_SPEED, SV_STAFF_DESTRUCTION, TVAL_STAFF
from policy_fixtures import store_item
from tests import test_black_market_optional_quantity as _optional_quantity

FIXTURES = Path(__file__).with_name("fixtures")
BM_PAGE = FIXTURES / "n1b-408-bm-destruction-staff-1116.json.gz"
FLOOR = FIXTURES / "n1c-205-stuck-recall-1113.jsonl.gz"
MONRACES = Path(r"C:\hengband\lib\edit\MonraceDefinitions.jsonc")
PILE = Position(18, 14)
MAGIC_EATER = 16
STAFF_TVAL, STAFF_SVAL = 55, 29
# The boards up to the first one standing on the pile (decision 6 of the window).
FLOOR_WINDOW = 7


def staff_row(count):
    return {"name": "*破壊*", "fail": 5, "success": 95, "current": count, "max": count}


def with_count(policy, turn, count):
    policy._me_device_lists = {"staff": (turn - 1, (staff_row(count),))}


class PriorityPurchaseCountLimitRecordedTest(unittest.TestCase):
    """n1-b life-408's own Black Market page: the staff's errand opens up to 50 only."""

    @classmethod
    def setUpClass(cls):
        with gzip.open(BM_PAGE, "rt", encoding="utf-8") as stream:
            cls.board = json.loads(stream.read())

    def observed(self, count):
        policy = HengbotPolicy()
        with_count(policy, self.board["turn"], count)
        snapshot = parse_snapshot(self.board)
        self.assertEqual(snapshot.player.class_id, MAGIC_EATER)
        self.assertEqual(snapshot.store.store_type, STORE_BLACK)
        self.assertIn("*破壊*の杖 (5回分)", [item.name for item in snapshot.store.items])
        bm_destruction_fund.observe(policy, snapshot)
        return policy, snapshot

    def test_fifty_keeps_the_errand(self):
        policy, snapshot = self.observed(50)
        self.assertEqual(policy._bm_destruction_shelf["ware"], "destruction-staff")
        self.assertEqual(policy._bm_destruction_shelf["price"], 50748)
        self.assertTrue(bm_destruction_fund.staff_wanted(policy, snapshot))

    def test_above_fifty_opens_no_errand(self):
        policy, snapshot = self.observed(51)
        self.assertIsNone(getattr(policy, "_bm_destruction_shelf", None))
        self.assertFalse(bm_destruction_fund.staff_pending(policy, snapshot))
        self.assertFalse(bm_destruction_fund.staff_wanted(policy, snapshot))


class PriorityPurchaseCountLimitShelfTest(unittest.TestCase):
    """The Black Market's optional picks with the staff shelved beside Potions of Speed.

    DECLARED CONSTRUCTED (tests/test_black_market_optional_quantity's town, as a
    Magic-Eater's): the policy has seen every departure price, so the optional reserve is
    known, and the gold covers the reserve, the staff and the potions.
    """

    STAFF_PRICE = 20000

    def page(self, count):
        base = _optional_quantity.BlackMarketOptionalQuantityReserveTest()
        policy, board = base._black_market(staff_charges=36, gold=0)
        reserve = policy._full_departure_resupply_reserve(board)
        self.assertIsNotNone(reserve)
        staff = store_item("X", TVAL_STAFF, SV_STAFF_DESTRUCTION, price=self.STAFF_PRICE,
                           count=2, charges=5, pval=5)
        board = replace(
            board,
            player=replace(board.player, class_id=MAGIC_EATER,
                           gold=reserve + 2 * self.STAFF_PRICE + 10000),
            store=replace(board.store, items=[*board.store.items, staff]))
        with_count(policy, board.turn, count)
        return policy, board, staff

    def test_fifty_picks_the_staff_first_and_every_copy(self):
        policy, board, staff = self.page(50)
        self.assertIs(policy._black_market_optional_purchase(board), staff)
        self.assertEqual(policy._purchase_quantity(board, staff), 2)

    def test_above_fifty_the_staff_is_no_priority_pick(self):
        policy, board, staff = self.page(51)
        pick = policy._black_market_optional_purchase(board)
        self.assertIsNotNone(pick)
        self.assertIsNot(pick, staff)
        self.assertEqual(pick.sval, SV_POTION_SPEED)


def _with_staff_pile(board):
    """The pile at (18,14) as one known Staff of *Destruction*, also on the boards standing on
    it (recorded: the ring there was auto-destroyed by picktype.prf when the player stepped
    on it; the Magic-Eater's line 「(~未鑑定の魔法アイテム:杖」 leaves a staff where it lies)."""
    board = copy.deepcopy(board)
    grid_map = board["grid_map"]
    cells = [cell for cell in grid_map["cells"]
             if (cell.get("y"), cell.get("x")) != (PILE.y, PILE.x) or "o" not in cell]
    grid_map["cells"] = [*cells, {"o": 1, "t": [STAFF_TVAL], "x": PILE.x, "y": PILE.y}]
    for name, entry in (("found_items", [PILE.y, PILE.x, 1, STAFF_TVAL]),
                        ("found_item_ids", [PILE.y, PILE.x, {"sval": STAFF_SVAL}]),
                        ("found_item_names", [PILE.y, PILE.x, "*破壊*の杖 (5回分)"])):
        grid_map[name] = [*(row for row in grid_map[name] if (row[0], row[1]) != (PILE.y, PILE.x)),
                          entry]
    return board


class DestroyOnFloorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FLOOR, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.skill = next(row["board"] for row in rows if row["role"] == "skill-knowledge")
        cls.boards = [_with_staff_pile(row["board"])
                      for row in rows if row["role"] == "board"][:FLOOR_WINDOW]
        cls.monrace = load_monrace_knowledge(MONRACES)

    def replay(self, count):
        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        policy.consume_skill_knowledge(self.skill)
        policy._skill_exp_request_key = lambda snapshot: None
        with_count(policy, self.boards[0]["turn"], count)
        decided = []
        for board in self.boards:
            snapshot = parse_snapshot(board, self.monrace)
            key = policy.choose_key(snapshot)
            if key:
                policy.confirm_key_posted(key)
            decided.append((snapshot.player.position, key, policy.last_reason))
        return policy, snapshot, decided

    def on_pile(self, decided):
        return next(entry for entry in decided if entry[0] == PILE)

    def test_at_ninety_nine_the_staff_is_walked_to_and_destroyed_where_it_lies(self):
        policy, snapshot, decided = self.replay(99)
        self.assertEqual(decided[0][2], "seek-loot")
        self.assertEqual(self.on_pile(decided)[1:], ("099k-", "me-capped:destroy-on-floor"))
        self.assertTrue(me_capped_pickup.capped_pile(policy, snapshot, PILE))
        self.assertTrue(me_capped_pickup.destroys(policy, snapshot, PILE))

    def test_below_ninety_nine_it_is_picked_up_as_before(self):
        policy, snapshot, decided = self.replay(98)
        self.assertEqual(self.on_pile(decided)[1:], ("g", "pickup"))
        self.assertFalse(me_capped_pickup.capped_pile(policy, snapshot, PILE))


if __name__ == "__main__":
    unittest.main()
