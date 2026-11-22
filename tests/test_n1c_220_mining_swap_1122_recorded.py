"""n1-c life-220: the weapon hand alternated between ロング・ソード in town and シャベル on Yeek cave 1F.

Owner 2026-11-22 Q6 (after a temporary swap -- mining, a quest, Zul -- the visit's target-loadout
weapon is worn) and 「決まりは足さず、着け直しを記録。往復が起きたら停止して直す。」.

What happened (2026-11-22 06:04-06:13, build bot-56fa91268, Lv8 Magic-Eater,
me-staff:fundraise:staff-stockout; jsonlog/equipment-visit.jsonl): the staff stock-out loop opens
one one-run mining set per town visit.  The run's floor wore シャベル in both hands
(policy_equipment._wield_digging_tool_key, mining-loadout); its return to town ended the set
(policy_observation, the run count) and the visit's first decisions took the hands back -- the
town re-arm (town:restore-combat-weapon) or the visit's swap (equipment-transaction:takeoff 'tb',
'ta', equip 'wi', then the two shovels deposited in the Home) -- and late in the same visit the
next set's kit withdrew a shovel again (home:queue-digging-tool-withdraw) and the next floor
stripped the sword.  Before that (06:03:54-06:04:04) the town re-arm took the off-hand シャベル off
under the swap's own pending take-off of it; the swap's take-off went stale, its abandonment
restored the shovel ('wky', restore:6014bec50c328225) and the re-arm took it off again, nine times,
until town:blocked:stage-deadline:equipment.  The E0 stop never fired: the town trail collapses an
empty off hand (シャベル, -, シャベル is no round trip), and out of town nothing was read.

Recorded (tests/extract_n1c_220_mining_swap_1122_fixture.py): the visit of 06:07:56 (town-arrival
turn 293876, シャベル in both hands), a later visit with no digger (06:26:42, 追加攻撃のカタナ) and
three boards of the stop's snapshot ring (town sword, 1F shovel, town sword).

DECLARED CONSTRUCTED:
* the departure's question (``_combat_weapon_ready``) asked on the visit's second board, as the
  ordinary departure asks it (the live visit asked it only at its descent, row 38), then the
  visit's next equipment decision (``_prepare_equipment_optimization``) on that board: with the
  lending the shop travel of row 0 keeps the second board, and the swap is planned when the
  equipment owner next decides;
* for the swap's ownership of the hands, the mining run's lending ended the same way.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import gzip
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import equipment_visit_journal, mining_loadout
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
MINING_VISIT = FIXTURES / "n1c-220-mining-visit-1122"
KATANA_VISIT = FIXTURES / "n1c-220-katana-visit-1122"
HAND_TRAIL = FIXTURES / "n1c-220-hand-trail-1122.json.gz"
KATANA_ROWS = 12


def _decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    if key:
        policy.confirm_key_posted(key)
    return key


def _prepare(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        policy._prepare_equipment_optimization(policy._with_cached_skill_exp(board))


def _hands(board):
    return {item.slot: item.name for item in board.equipment
            if item.slot in mining_loadout.HANDS}


class _Visit(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)

    def load(self, fixture):
        policy, _journal, steps = load(fixture, Path(self.scratch.name) / fixture.name)
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        return policy, steps


class MiningRunReturnKeepsTheHandsTest(_Visit):
    """The visit a mining run came back to: one owner (the lending) for the hands."""

    def test_the_visits_first_boards_leave_the_diggers_in_hand(self):
        """Before the fix the second board took the off-hand shovel off ('tb',
        equipment-transaction:takeoff) and the third the main-hand one ('ta')."""
        policy, steps = self.load(MINING_VISIT)
        first = steps[0][1]()
        self.assertTrue(all("シャベル" in name for name in _hands(first).values()), _hands(first))
        self.assertEqual(_decide(policy, first), steps[0][0]["key"])   # shop:travel, as recorded
        # The run's return ended its one-run set (the run count): no set is open now.
        self.assertIsNone(policy._fundraising_mode)
        second = steps[1][1]()
        self.assertEqual(steps[1][0]["reason"], "equipment-transaction:takeoff")
        key = _decide(policy, second)
        self.assertNotEqual(key, "tb")
        self.assertTrue(mining_loadout.hands_lent(policy, second))
        self.assertFalse(policy.last_reason.startswith(("equipment-transaction:", "town:restore")),
                         policy.last_reason)
        self.assertIsNone(policy._equipment_transaction_session)
        # The town re-arm names the lending.
        self.assertIsNone(policy._town_restore_weapon_key(second))

    def test_an_ordinary_departure_ends_the_lending_and_the_target_is_worn(self):
        """Q6: once the visit asks for its ordinary departure, the visit's swap wears the target's
        weapon: both shovels off and ロング・ソード into the main hand, the recorded swap (rows 1-3:
        'tb', 'ta', 'wi'), with the town re-arm waiting on it."""
        policy, steps = self.load(MINING_VISIT)
        _decide(policy, steps[0][1]())
        second = steps[1][1]()
        self.assertTrue(mining_loadout.hands_lent(policy, second))
        self.assertFalse(policy._combat_weapon_ready(second))   # DECLARED: the departure asks
        self.assertFalse(mining_loadout.hands_lent(policy, second))
        _prepare(policy, second)          # DECLARED: the visit's next equipment decision
        session = policy._equipment_transaction_session
        self.assertIsNotNone(session)
        planned = [(action.kind, action.target_slot) for action in session.plan.actions]
        self.assertIn(("takeoff", "main_hand"), planned)
        self.assertIn(("takeoff", "sub_hand"), planned)
        self.assertIn(("equip", "main_hand"), planned)
        names = {item.id: item.item.name for item in policy._equipment_catalog.items}
        wielded = [names.get(action.item_id, action.item_id) for action in session.plan.actions
                   if (action.kind, action.target_slot) == ("equip", "main_hand")]
        self.assertTrue(all("ロング・ソード" in name for name in wielded), wielded)

    def test_the_swap_owns_the_hands_the_town_rearm_waits(self):
        """Before the fix the town re-arm wielded the remembered ロング・ソード into the main hand
        ('w?a', town:restore-combat-weapon) under the swap's own pending take-offs of the same
        hands -- the two owners of 06:03:54 (stage-deadline:equipment)."""
        policy, steps = self.load(MINING_VISIT)
        _decide(policy, steps[0][1]())
        second = steps[1][1]()
        mining_loadout.end_lending(policy)                      # DECLARED: as the departure ends it
        _prepare(policy, second)
        self.assertIsNotNone(policy._equipment_transaction_session)
        self.assertIsNone(policy._town_restore_weapon_key(second))


class NoDiggerVisitUnchangedTest(_Visit):
    def test_a_visit_without_a_digger_replays_as_recorded(self):
        policy, steps = self.load(KATANA_VISIT)
        for recorded, supply in steps[:KATANA_ROWS]:
            board = supply()
            self.assertFalse(mining_loadout.hands_lent(policy, board))
            key = _decide(policy, board)
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                             recorded.get("decision_sequence"))


class HandTrailRecordsTheRoundTripTest(_Visit):
    """The town's edge: ロング・ソード (town) -> シャベル (1F) -> ロング・ソード (town), record only."""

    def test_the_round_trip_over_the_towns_edge_is_written_not_stopped(self):
        policy, _steps = self.load(KATANA_VISIT)
        with gzip.open(HAND_TRAIL, "rt", encoding="utf-8") as stream:
            raw = json.load(stream)["boards"]
        boards = [parse_snapshot(board, policy._monrace_knowledge) for board in raw]
        self.assertEqual([board.in_town for board in boards], [True, False, True])
        self.assertEqual(["ロング" in _hands(board)["main_hand"] for board in boards],
                         [True, False, True])
        for board in boards:
            equipment_visit_journal.observe(policy, board)
            self.assertIsNone(equipment_visit_journal.held_stop(policy, board))
        rows = [row for row in equipment_visit_journal.journal(policy)["rows"]
                if row["kind"].startswith(equipment_visit_journal.HAND_ROUNDTRIP_EVENT)]
        self.assertEqual([row["kind"] for row in rows],
                         [f"{equipment_visit_journal.HAND_ROUNDTRIP_EVENT}:main_hand"])
        self.assertEqual([place[0] for place in rows[0]["where"]], ["town", "away", "town"])
        self.assertFalse(rows[0]["stops"])


if __name__ == "__main__":
    unittest.main()
