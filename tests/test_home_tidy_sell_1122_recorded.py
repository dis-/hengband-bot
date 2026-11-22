"""The Home tidy sells the unneeded ware a store pays for; it destroys only what no store buys.

Owner 2026-11-22, asked 「自宅が満杯の時の片づけで、ゴールドドラゴン・スケイルメイル [40,+14] の
ような高価な防具も「素の装備で、ほかの品に劣る」と判定されれば壊しますか？」, answered
「売れる品は売り、壊すのは売れない品だけ」 (片づけで要らないと判定した品のうち、店で売値が付く
ものは売りに行き、売値の付かない品だけを壊します).

The full-Home relief, its cap tidy and its junk sweep destroy at one site (policy_home
``_home_full_relief_key``, the ware's destroy once it passed the destroy's gates).  There the
ware now goes to the store that pays for it (``_home_full_buyer``: the store that buys the kind,
not refused this visit, the ware not remembered unsellable) by the relief's own sale: the cap
tidy's batch, the sweep's and the full relief's round trip.  A ware no store buys is destroyed
as before.

Recorded, through the public ``choose_key`` with the recorded keys posted:

* n1-c life-217's 99F/100F preparation visit (2026-11-21 05:55, tests/fixtures/n1c-finale-prep-1121):
  the cap tidy took the Gold Dragon Scale Mail [40,+14] {r轟} out at row 3 to destroy it (rows
  0-3 as recorded); at row 4 it joins the tidy's sale batch for the Armoury;
* n1-a life-532's town arrival (2026-11-22 14:09, tests/fixtures/n1a-532-robe-round-trip-1122):
  the junk sweep took the plain broadsword out at row 12 to destroy it (rows 0-12 as recorded);
  at row 13 the sweep walks it to the Weapon Smith.  (The robe [2,+5] of row 16 sells too:
  tests/test_home_relief_take_preserved_1122_recorded.)

DECLARED CONSTRUCTED: for the ware no store buys, the same boards with the ware remembered
unsellable (``_unsellable_items``, the memory a refused sale leaves): the recorded destroy keys
come back unchanged.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import test_home_relief_take_preserved_1122_recorded as robe_case
from hengbot import equipment_target
from hengbot.model import STORE_ARMOURY, STORE_HOME, STORE_WEAPON
from hengbot.policy import staged_prompt_chain_matches
from replay_town_arrival import adopt_calibration
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
FINALE = "n1c-finale-prep-1121"
GOLD_DRAGON = "ゴールドドラゴン・スケイルメイル"
FINALE_DESTROY_ROW = 4
BROADSWORD = "ブロード・ソード"
SWEEP_DESTROY_ROW = 13


def _post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def _decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        return policy.choose_key(board)


def _ware(board, name):
    return next(item for item in board.inventory if name in item.name)


class _Replay(unittest.TestCase):
    fixture = ""
    ware_name = ""
    destroy_row = 0

    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        with contextlib.redirect_stdout(io.StringIO()):
            self.policy, self.journal, self.steps = load(
                FIXTURES / self.fixture, Path(self.scratch.name))
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)

    def prepare(self, recorded, board):
        """The fixture's own constructed inputs before a row's decision."""

    def replay(self, *, unsellable=False):
        """Rows before the destroy row as recorded; then the destroy row's decision."""
        policy = self.policy
        replayed = []
        for recorded, supply in self.steps[:self.destroy_row]:
            board = supply()
            self.prepare(recorded, board)
            key = _decide(policy, board)
            replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            _post(policy, recorded["key"])
        for row, (decided, recorded) in enumerate(replayed):
            self.assertEqual(decided, recorded, row)
        # The record's ware, taken out to be destroyed (the take's errand purpose).
        relief = policy._home_full_relief
        self.assertEqual(relief.mode, "destroy")
        self.assertEqual(self.journal[self.destroy_row - 1]["reason"],
                         "home-errand:atomic-withdraw:full-home-discard")
        recorded, supply = self.steps[self.destroy_row]
        board = supply()
        ware = _ware(board, self.ware_name)
        if unsellable:
            # DECLARED CONSTRUCTED (module docstring): the ware remembered unsellable.
            policy._unsellable_items.add(policy._item_signature(ware))
        key = _decide(policy, board)
        return board, ware, key, policy.last_reason, recorded


class FinaleCapTidyTest(_Replay):
    fixture = FINALE
    ware_name = GOLD_DRAGON
    destroy_row = FINALE_DESTROY_ROW

    def test_the_cap_tidy_sells_the_gold_dragon_scale_mail(self):
        board, ware, key, reason, _recorded = self.replay()
        policy = self.policy
        # Before: ('01kl', 'home:full-destroy-surplus'), the scale mail destroyed.
        self.assertNotEqual(reason, "home:full-destroy-surplus")
        self.assertFalse(key.startswith("0"), key)
        self.assertIn("[40,+14]", ware.name)
        self.assertEqual(policy._home_full_buyer(ware), STORE_ARMOURY)
        relief = policy._home_full_relief
        self.assertTrue(relief.cap)
        # The tidy's sale batch: sold at the Armoury with the batch, not destroyed.
        self.assertIn((policy._item_signature(ware), STORE_ARMOURY),
                      [(entry[0], entry[1]) for entry in relief.carried])
        self.assertIsNone(relief.destroy_work_id)

    def test_a_ware_no_store_buys_is_still_destroyed(self):
        _board, ware, key, reason, _recorded = self.replay(unsellable=True)
        self.assertIsNone(self.policy._home_full_buyer(ware))
        self.assertEqual((key, reason), ("01kl", "home:full-destroy-surplus"))


class SweepBroadswordTest(_Replay):
    fixture = robe_case.FIXTURE.name
    ware_name = BROADSWORD
    destroy_row = SWEEP_DESTROY_ROW

    def prepare(self, recorded, board):
        if recorded["row"] == 1:
            # DECLARED CONSTRUCTED (tests/test_home_relief_take_preserved_1122_recorded): the
            # Lv20 calibration of row 1's dump.
            adopt_calibration(self.policy, robe_case.FIXTURE / "character-calibration-lv20.json",
                              Path(self.scratch.name))
            self.policy._calibration_rejection = None
            self.policy._calibration_unavailable_reason = None
            equipment_target.invalidate_loadout_search(self.policy)

    def test_the_record_destroyed_the_broadsword(self):
        self.assertEqual((self.journal[SWEEP_DESTROY_ROW]["key"],
                          self.journal[SWEEP_DESTROY_ROW]["reason"]),
                         ("01km", "home:junk-sweep:plain-gear"))

    def test_the_sweep_sells_the_broadsword(self):
        _board, ware, key, reason, _recorded = self.replay()
        policy = self.policy
        relief = policy._home_full_relief
        # Before: ('01km', 'home:junk-sweep:plain-gear').
        self.assertTrue(relief.sweep)
        self.assertEqual(policy._home_full_buyer(ware), STORE_WEAPON)
        self.assertEqual((relief.mode, relief.sale[1], relief.withdrawn),
                         ("sale", STORE_WEAPON, True))
        self.assertEqual(reason, "shop:approach")
        self.assertFalse(key.startswith("0"), key)

    def test_a_ware_no_store_buys_is_still_destroyed(self):
        _board, ware, key, reason, _recorded = self.replay(unsellable=True)
        self.assertIsNone(self.policy._home_full_buyer(ware))
        self.assertEqual((key, reason), ("01km", "home:junk-sweep:plain-gear"))
        self.assertEqual(self.policy._home_full_relief.sale[1], STORE_HOME)


if __name__ == "__main__":
    unittest.main()
