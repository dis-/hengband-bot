"""n1-b life-340 (2026-11-08 02:53): the stage-1 expedition stopped on its run limit.

Owner 2026-11-08 (question 「魔道具術師の第1段（噂の遠征でモリバントの塔へ行き、
杖を充填して取り込む）が、低いレベルで資金が足りない時はどうしますか？」, answer
「資金集めを続ける」: 「資金集めの回数の上限を外し、届くまで資金集めを続ける。」).

The Lv8 Magic-Eater came back to the Outpost with 28,209 gold from its sixth
me-staff:fundraise:rumor-travel-recharge mining run (every run had brought
gold home), and the first decision of the visit stopped as
quest:blocked:me-staff with fundraise-limit:rumor-travel-recharge:57099
(FUNDRAISE_RUN_LIMIT 6).  Lives 326 and 327 (2026-11-06) were retired by the
same stop.

Recorded: the capture's town-arrival checkpoint and journal
(tests/extract_me_stage1_fundraise_1108.py).  The journal's one row, the stop
board, goes through the public chooser.  The boards after it are constructed
(marked).

The sequence prices the Tower's recharge from lib/edit/BaseitemDefinitions.jsonc
(morivant_tower.device_definitions, looked up from the working directory):
51,145 of the recorded 57,099 target is the recharge, 50,050 of it for the
unidentified 檜の杖 priced as the dearest staff kind (recharge_all_price), so
the case needs the repository's lib/edit.

Owner 2026-11-08 on that estimate: 「一旦他の杖を自宅に仕舞って鑑定の杖と財宝感知の杖
だけ取り込んで、鑑定してから再度考える。」 (me_staff_sequence.stows): the board
now shelves the 檜の杖 at Home first (StowStaffsTest).  The uncapped
fundraising cases keep the staff carried by a Home that refused it this
visit (DECLARED CONSTRUCTED in ``arrival``), which prices it as recorded.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import me_capability, me_staff_sequence as sequence
from hengbot.model import parse_snapshot
from hengbot.policy_constants import STORE_STUCK_LIMIT
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import decisions, journal, restore


FIXTURE = Path(__file__).with_name("fixtures") / "me-stage1-fundraise-20261108"
DECISIONS = json.loads((FIXTURE / "decisions.json").read_text(encoding="utf-8"))
RECORDED_TARGET = 57099   # the stop's rumor expedition cost
SIXTH_RUN_TARGET = 57075  # the target the sixth run was started with
EXPEDITION = f"me-staff:fundraise:rumor-travel-recharge:{RECORDED_TARGET}"


class Arrival(unittest.TestCase):
    def arrival(self, *, staff_refused=False):
        """The restored arrival policy, the journal and the stop board.

        DECLARED CONSTRUCTED (``staff_refused``): Home refused the 檜の杖 this
        visit (``_home_rejected_deposits``), so it stays carried
        (me_staff_sequence._stow_pending).
        """
        raw = Path(self.enterContext(TemporaryDirectory()))
        visit = raw / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((FIXTURE / "journal.jsonl.xz").read_bytes())))
        scratch = raw / "scratch"
        scratch.mkdir()
        policy = restore(visit, scratch)
        rows = journal(visit)
        steps = list(decisions(policy, visit, scratch))
        self.assertEqual(len(steps), 1)
        board = steps[0][1]()
        if staff_refused:
            policy._home_rejected_deposits.add(policy._item_signature(
                next(item for item in board.inventory if item.name == "檜の杖")))
        return policy, rows, board

    def decide(self, policy, raw):
        key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
        if key:
            policy.confirm_key_posted(key)
        return key


class RecordedStopTest(Arrival):

    def test_capture_pins_the_stop_after_runs_that_each_brought_gold(self):
        policy, rows, board = self.arrival()
        self.assertEqual((rows[-1]["reason"], rows[-1]["key"]), ("quest:blocked:me-staff", ""))
        record = sequence.state(policy)
        self.assertIsNone(record.failure)
        self.assertEqual((record.stage, record.absorbed, sorted(record.bought)), (1, {}, [5, 10]))
        self.assertEqual((record.fundraise_runs, record.reached_runs),
                         (sequence.FUNDRAISE_RUN_LIMIT, 0))
        self.assertEqual((record.fundraise_why, record.fundraise_target),
                         ("rumor-travel-recharge", SIXTH_RUN_TARGET))
        self.assertEqual((board.player.level, board.player.gold), (8, 28209))
        self.assertTrue(board.in_town)
        self.assertEqual(tuple(board.visited_town_ids), (0,))  # Morivant not yet unlocked
        stop = DECISIONS[-1]
        self.assertEqual((stop["reason"], stop["turn"], stop["gold"]),
                         ("quest:blocked:me-staff", 488942, 28209))
        ascents = [row["gold"] for row in DECISIONS if row["reason"] == "fundraise:ascend"]
        self.assertEqual(ascents, [22558, 24385, 24402, 25903, 27826, 28189, 28209])


class FundraisingContinuesTest(Arrival):

    def test_stop_board_starts_the_next_rumor_expedition_run(self):
        policy, _rows, board = self.arrival(staff_refused=True)
        key = policy.choose_key(board)
        record = sequence.state(policy)
        self.assertIsNone(record.failure, policy.last_reason)
        # The town's entrance step-off carries the sequence's run start.
        self.assertTrue(key, policy.last_reason)
        self.assertTrue(policy.last_reason.endswith(EXPEDITION), policy.last_reason)
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(policy._supply_stockout_gold_target, RECORDED_TARGET)
        self.assertEqual(policy._planned_mining_runs, 1)
        # The returned sixth run was settled short; an expedition run is in
        # neither count while short, so the staff purchase keeps its budget.
        self.assertEqual((record.fundraise_runs, record.reached_runs, record.expedition_runs),
                         (sequence.FUNDRAISE_RUN_LIMIT, 0, 1))

    def test_runs_that_bring_gold_continue_until_the_cost_is_reached(self):
        # DECLARED CONSTRUCTED: the same arrival after more short runs, each
        # bringing 1,500 gold (the recorded runs brought 17 to about 3,000).
        # The record's count is the recorded one or larger.
        for extra in (1, 6, 18):
            with self.subTest(extra=extra):
                policy, rows, _board = self.arrival(staff_refused=True)
                record = sequence.state(policy)
                record.fundraise_runs += extra
                raw = json.loads(rows[-1]["line"])
                raw["player"]["gold"] += 1500 * extra
                key = self.decide(policy, raw)
                self.assertIsNone(record.failure, policy.last_reason)
                self.assertTrue(key, policy.last_reason)
                self.assertTrue(policy.last_reason.endswith(EXPEDITION), policy.last_reason)
                self.assertEqual(policy._fundraising_mode, "prepare")
        # Reached: the rumor phase reads the inn's rumors.
        policy, rows, _board = self.arrival(staff_refused=True)
        raw = json.loads(rows[-1]["line"])
        raw["player"]["gold"] = RECORDED_TARGET
        self.decide(policy, raw)
        self.assertIsNone(sequence.state(policy).failure, policy.last_reason)
        self.assertEqual(policy.last_reason, "town:rumor")

    def test_identical_boards_end_as_no_progress(self):
        # DECLARED CONSTRUCTED: the sequence's run start is asked again and
        # again on the same cell with the same gold and pack, as when a run
        # ended at once without game time.  The existing standstill bound
        # (_no_progress, STORE_STUCK_LIMIT boards) ends it as a named stop;
        # the run limit no longer does.
        policy, _rows, board = self.arrival(staff_refused=True)
        # The finished run's mode, as the recorded decision saw it (null).
        policy._fundraising_mode = None
        keys = []
        for _ in range(2 * STORE_STUCK_LIMIT):
            keys.append(sequence.town_key(policy, board, []))
            if not keys[-1]:
                break
            policy._fundraising_mode = None
        self.assertEqual(keys, [sequence.WAIT_KEY] * (STORE_STUCK_LIMIT - 1) + [""])
        self.assertEqual(sequence.state(policy).failure, "no-progress:rumor")
        self.assertEqual(policy.last_reason, sequence.STOP_REASON)


class KeptLimitsTest(Arrival):
    """The limits the owner decision does not touch."""

    def test_staff_purchase_runs_keep_their_limit(self):
        policy, _rows, board = self.arrival()
        record = sequence.state(policy)
        self.assertEqual(sequence._fundraise(policy, board, 900, "staffs"), "")
        self.assertEqual(record.failure, "fundraise-limit:staffs:900")

    def test_expedition_target_drift_keeps_its_limit(self):
        policy, _rows, board = self.arrival()
        record = sequence.state(policy)
        record.fundraise_runs = record.reached_runs = sequence.FUNDRAISE_RUN_LIMIT
        self.assertEqual(
            sequence._fundraise(policy, board, RECORDED_TARGET, "rumor-travel-recharge"), "")
        self.assertEqual(record.failure,
                         f"fundraise-target-drift:rumor-travel-recharge:{RECORDED_TARGET}")

    def test_met_expedition_run_counts_as_met_in_both_counts(self):
        # DECLARED CONSTRUCTED: the sixth run came back with its target met
        # (and the gold went elsewhere before the next decision).
        policy, _rows, board = self.arrival(staff_refused=True)
        record = sequence.state(policy)
        record.fundraise_runs, record.target_reached = 2, True
        policy.choose_key(board)
        self.assertEqual((record.fundraise_runs, record.reached_runs), (3, 1))
        self.assertIsNone(record.failure, policy.last_reason)


class StowStaffsTest(Arrival):
    """Owner 2026-11-08: the other staffs wait at Home while stage 1 is worked."""

    def staff(self, board):
        return next(item for item in board.inventory if item.name == "檜の杖")

    def test_capture_carries_one_unidentified_staff(self):
        _policy, _rows, board = self.arrival()
        staff = self.staff(board)
        self.assertEqual((staff.tval, staff.aware, staff.known), (55, False, False))
        staves = sorted(item.name for item in board.inventory if item.tval == 55)
        self.assertEqual(staves, sorted(["檜の杖", "財宝感知の杖 (15回分)", "鑑定の杖 (0回分)"]))
        # The 'a' estimate the recorded stop priced: the unknown staff as the
        # dearest staff kind.
        self.assertEqual(sequence.recharge_cost(board), 51145)

    def test_stop_board_shelves_the_unknown_staff_before_any_fundraising(self):
        policy, _rows, board = self.arrival()
        staff = self.staff(board)
        key = policy.choose_key(board)
        record = sequence.state(policy)
        self.assertTrue(key, policy.last_reason)
        self.assertIsNone(record.failure, policy.last_reason)
        self.assertNotIn("me-staff:fundraise", policy.last_reason)
        self.assertNotEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(record.expedition_runs, 0)
        self.assertEqual([item.name for item in sequence.stowed_staffs(policy, board)], ["檜の杖"])
        # Home's own deposit flow takes it, whole; it is no junk.
        self.assertTrue(policy._home_deposit_candidate(staff, board))
        self.assertEqual(policy._home_deposit_quantity(board, staff), 1)
        self.assertIsNone(policy._junk_class(board, staff))

    def test_home_finder_takes_the_staff_after_the_mining_scrolls(self):
        # DECLARED CONSTRUCTED: the Treasure Detection scrolls (off duty,
        # first in the pack) are shelved; the finder's next pick is the staff.
        policy, rows, _board = self.arrival()
        raw = json.loads(rows[-1]["line"])
        raw["inventory"] = [item for item in raw["inventory"] if item["name"] != "財宝感知の巻物"]
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual(policy._find_home_deposit(board).name, "檜の杖")

    def test_after_the_deposit_the_expedition_goes_on(self):
        # DECLARED CONSTRUCTED: the 檜の杖 shelved at Home, nothing else changed.
        policy, rows, _board = self.arrival()
        raw = json.loads(rows[-1]["line"])
        raw["inventory"] = [item for item in raw["inventory"] if item["name"] != "檜の杖"]
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(sequence.recharge_cost(board), 1095)
        self.decide(policy, raw)
        self.assertIsNone(sequence.state(policy).failure, policy.last_reason)
        self.assertEqual(policy.last_reason, "town:rumor")
        cost = sequence._rumor_expedition_cost(board, sequence.supply_cost(policy, board))
        self.assertLess(cost, board.player.gold)
        self.assertLess(cost, 8000)

    def test_refused_staff_is_priced_carried(self):
        # DECLARED CONSTRUCTED: Home refused it this visit; the
        # expedition is priced with it carried (uncapped fundraising).
        policy, _rows, board = self.arrival(staff_refused=True)
        policy.choose_key(board)
        self.assertTrue(policy.last_reason.endswith(EXPEDITION), policy.last_reason)

    def test_stage_one_staffs_are_not_stowed_and_stage_two_stows_nothing(self):
        policy, _rows, board = self.arrival()
        kept = [item for item in board.inventory if item.tval == 55 and item.aware]
        self.assertEqual(len(kept), 2)
        self.assertFalse(any(sequence.stows(policy, board, item) for item in kept))
        # DECLARED CONSTRUCTED: stage 1 complete; the ordinary Home rules
        # take the stored staff up again (the absorbed Identify).
        record = sequence.state(policy)
        record.absorbed = {**record.absorbed,
                           **{me_capability.record_key("staff", sval): 1
                              for sval in sequence.STAGES[0].svals}}
        self.assertFalse(sequence.stows(policy, board, self.staff(board)))


if __name__ == "__main__":
    unittest.main()
