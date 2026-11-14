"""n1-a life-522 2026-11-14 16:34:50, town:blocked:overweight-retained-only (bot cdf059701).

The Lv39 warrior was taking catalogued Home weapons out one at a time, giving each its
*Identify* and putting it back (identification-catalog takes, then the equipment
transaction's Home deposits).  On the stop board (turn 2788301, 2170 over a 1750 limit)
the pack held 殺戮のブロード・ソード and 滅邪のフランベルジュ, *identified* on the two boards
before and planned as the equipment transaction's two Home deposits (Home 147/240), and
★スモール・ソード『エクスカリバー・ジュニア』 and 追加攻撃のバトル・アックス, known but not
yet *identified*, with two *Identify* scrolls carried for them.  An overweight-surplus
disposal state set on the board before (when the carried surplus bolts still cleared the
excess) sent the decision to _overweight_surplus_sale_key; the weight relief found no
deposit (the transaction's reservation hid both weapons, the identification hid the
other two, the Identify staves were kept as the identify-staff supply), the surplus no
longer cleared the excess, and the visit stopped as retained-only.  Its record named
None for the staves and the two transaction weapons.

The weight relief now reads a held item whose owner still takes it out of the pack (the
transaction's own Home deposit, an identification with its source carried) as
``owner-pending``: those owners go first and the disposal state gives way, so the stop
board posts the transaction's Home deposit.  Every held item is recorded with the hold
that kept it from the deposits (owner 2026-10-10 「常に記録」).

Recorded: the incident capture's town-arrival checkpoint, its whole journal and sidecar
files (tests/extract_n1a_522_overweight_1114_fixture.py), every row decided through the
public choose_key and compared with the record; the stop board's key is posted through
the production executor (_ExecutorInputPort).

DECLARED CONSTRUCTED: the visit's two character dumps (rows 77 and 101) were written by
the game to the dump file, which the journal does not hold.  On the board after each,
the arrival calibration is supplied with the printed stat key the board shows (row 73
quaffed Restore Charisma; the recorded bot re-derived the same constants from the dump).
The later boards of the second test are the stop board with the owners' effects applied
(the two deposits leave the pack; the *Identify* reads consume both scrolls and fully
identify the two weapons).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.warrior_optimization import load_character_calibration
from support.town_arrival_fixture import load
from tests.support import recorded as executor_harness

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-522-overweight-1114"
STOP_ROW = 156
STOP = "town:blocked:overweight-retained-only"
LIMIT = 1750


def reobserve(policy, arrival, board):
    """DECLARED CONSTRUCTED (module docstring): the dump the journal does not hold."""
    if policy._calibration_dump_response is None:
        return
    policy._calibration_dump_response = None
    policy._calibration_dump_pending = None
    policy._character_calibration = replace(
        arrival, visible_stat_key=board.player.printed_stat_cur_key)
    policy._character_calibration_loaded = True
    policy._calibration_unavailable_reason = None
    policy._equipment_optimization_signature = None


def post_recorded(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class N1a522OverweightRecordedTest(executor_harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        # The dungeon-1031 corpus of RecordedHarness is not read.  The visit is
        # replayed once (rows 0-155 through choose_key, each compared with the
        # record); every test restores the policy on the stop board.
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        arrival = load_character_calibration(policy._character_calibration_path)
        cls.replayed = []
        for recorded, supply in steps[:STOP_ROW]:
            board = supply()
            reobserve(policy, arrival, board)
            key = policy.choose_key(board)
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            post_recorded(policy, key)
        cls.board = steps[STOP_ROW][1]()
        reobserve(policy, arrival, cls.board)
        cls.checkpoint = checkpoint_bytes(policy)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)

    def stop_board(self):
        return self.board

    def raw(self, row):
        entry = self.journal[row]
        return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])

    def test_the_transaction_deposit_goes_first_and_every_hold_is_named(self):
        self.assertEqual(self.journal[STOP_ROW]["reason"], STOP)
        board = self.stop_board()
        policy = self.policy
        self.assertIsNone(board.store)
        self.assertEqual((policy._inventory_weight(board), policy._inventory_weight_limit(board)),
                         (2170, LIMIT))
        pack = {item.slot: item for item in board.inventory}
        # Both weapons the identification holds are known, not yet *identified*,
        # and the pack carries the two *Identify* scrolls for them.
        for slot in "lo":
            self.assertTrue(pack[slot].known and not pack[slot].fully_known, pack[slot].name)
        self.assertEqual((pack["g"].name, pack["g"].count), ("*鑑定*の巻物", 2))
        relief = policy._weight_relief_selection(board)
        self.assertEqual((relief.route, relief.deposits), ("owner-pending", ()))
        held = {slot: reason for slot, _, _, reason in relief.retained}
        self.assertEqual({slot: held[slot] for slot in "klmno"}, {
            "k": "required-supply:identify-staff",
            "l": "identification-flow",
            "m": "equipment-transaction:deposit",
            "n": "equipment-transaction:deposit",
            "o": "identification-flow",
        })
        self.assertNotIn(None, held.values())
        # The need router no longer files a surplus sale ahead of those owners.
        self.assertIsNone(policy._overweight_surplus_disposal)

        key = policy.choose_key(board)

        self.assertEqual((key, policy.last_reason), ("5", "equipment-transaction:atomic-deposit"))
        self.assertIsNone(policy._town_blocked_reason)
        raw = self.raw(STOP_ROW)
        self.assertEqual(self.post(policy, raw, key, [], self.later(raw)), ["5"])

    def test_a_surplus_sale_filed_before_gives_way_to_the_pending_owners(self):
        board = self.stop_board()
        policy = self.policy
        # DECLARED CONSTRUCTED: the state the recorded bot's need router filed on
        # row 155, when the carried surplus bolts still cleared the excess.
        policy._overweight_surplus_disposal = {"town": policy._effective_town_id(board)}

        key = policy.choose_key(board)

        self.assertEqual((key, policy.last_reason), ("5", "equipment-transaction:atomic-deposit"))
        self.assertNotEqual(policy.last_reason, STOP)
        self.assertIsNone(policy._town_blocked_reason)
        self.assertIsNone(policy._overweight_surplus_disposal)

    def test_the_unused_weapons_leave_once_their_owners_are_done(self):
        board = self.stop_board()
        policy = self.policy
        # DECLARED CONSTRUCTED: the transaction's two Home deposits have landed.
        deposited = replace(board, inventory=tuple(
            item for item in board.inventory if item.slot not in "mn"))
        self.assertEqual(policy._inventory_weight(deposited), 1790)
        self.assertNotEqual(policy._weight_relief_selection(deposited).route, "retained-only")
        # DECLARED CONSTRUCTED: both *Identify* scrolls were read on the two weapons.
        identified = replace(deposited, inventory=tuple(
            replace(item, fully_known=True) if item.slot in "lo" else item
            for item in deposited.inventory if item.slot != "g"))
        relief = policy._weight_relief_selection(identified)
        self.assertEqual(relief.route, "deposit")
        names = {item.name for item in relief.deposits}
        self.assertEqual(names, {
            "★スモール・ソード『エクスカリバー・ジュニア』 (2d6) (+3,+5) (+2攻撃)",
            "追加攻撃のバトル・アックス (2d8) (+6,+5) (+1攻撃)",
        })
        shed = sum(item.weight * policy._retention_surplus(identified, item)
                   for item in relief.deposits)
        self.assertLessEqual(policy._inventory_weight(identified) - shed, LIMIT)
        self.assertIn(policy._overweight_home_deposit(identified), relief.deposits)


if __name__ == "__main__":
    import unittest
    unittest.main()
