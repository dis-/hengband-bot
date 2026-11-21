"""The 99F/100F preparation phase (finale_prep): its steps on n1-c's and n1-b's town visits.

Owner 2026-11-21 (verbatim, LOCKED): 「99Fに挑む要件を満たしたら専用の準備フェイズを作って準備して。
変に既存の仕組みを使おうとして破綻しているように見える」; question 1 「キー操作だけ既存の着け替えの処理に
任せる」; questions 2 and 3 as proposed (finale_prep's docstring).

Recorded: n1-c life-217's town visit of 2026-11-21 05:55:10 (tests/fixtures/n1c-finale-prep-1121,
143 journal rows: every supply owned once its Teleportation are bought at row 34, the Home's
Restore Mana, Healing and *Healing* not carried, the recall read at row 74) and n1-b life-411's of
05:50:19 (tests/fixtures/n1b-finale-prep-1121, 267 rows, every supply owned on arrival).  Both were
played by the build before the phase, so a replay matches the record only until the phase acts:
from there the recorded keys are delivered row by row as the game received them (``deliver``).

DECLARED CONSTRUCTED:
* ``stocked``: n1-c's recorded board with the pack's finale stacks set to their counts (a missing
  kind copies the Healing stack's row), as after the supplies step's withdrawals, and the food step's
  three Wands of Wonder under three inscriptions;
* the swap's done-check board: the phase's fixed target set to the worn set's pieces (as after the
  equipment transaction), the transaction left none;
* the next visit's arrival: the expedition's board as Angband 99F, then the town board again with
  no swap under way;
* n1-b's 04:55 visit (tests/fixtures/n1b-411-switch-loop-1121) with the phase at its check step;
* n1-c's Home census without its Mushroom of Restoring, as after its withdrawal.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_cap, angband_finale, finale_prep
from hengbot.magic_eater_devices import SV_WAND_WONDER
from hengbot.model import DUNGEON_ANGBAND, TVAL_WAND
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
N1C = "n1c-finale-prep-1121"
N1B = "n1b-finale-prep-1121"
N1C_ENTRY = 34       # the first board with every supply owned (its Teleportation bought)
N1C_HOME_PAGE = 53   # the board where the supplies step's Home withdrawal is composed
N1C_RECALL = 74      # the recorded Word of Recall read


class FinalePrepRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()

    def tearDown(self):
        self.scratch.cleanup()

    def load(self, name):
        policy, _journal, steps = load(FIXTURES / name, Path(self.scratch.name) / name)
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        return policy, steps

    @staticmethod
    def decide(policy, board):
        with contextlib.redirect_stdout(io.StringIO()):
            return policy.choose_key(board)

    @staticmethod
    def deliver(policy, key):
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def n1c_until(self, last_row):
        """n1-c's visit decided row by row through ``last_row``: [(row, board, key, reason)]."""
        policy, steps = self.load(N1C)
        decided = []
        for recorded, supply in steps[:last_row + 1]:
            board = supply()
            key = self.decide(policy, board)
            decided.append((recorded["row"], board, key, policy.last_reason))
            if recorded["row"] < N1C_ENTRY:
                self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
            self.deliver(policy, recorded["key"])
        return policy, decided

    def stocked(self, policy, board, *, mushrooms_taken=True):
        """DECLARED: the pack holding the finale's counts; with ``mushrooms_taken``, every Mushroom
        of Restoring at Home taken out too (finale_prep._restoring_at_home)."""
        targets = {**angband_finale.CARRY,
                   angband_finale.RESTORE_MANA: angband_finale.restore_mana_carry(policy, board)}
        pack = [replace(item, count=targets[(item.tval, item.sval)])
                if (item.tval, item.sval) in targets else item for item in board.inventory]
        template = next(item for item in board.inventory
                        if (item.tval, item.sval) == angband_finale.HEALING)
        held = {(item.tval, item.sval) for item in pack}
        for kind, count in targets.items():
            if kind not in held:
                pack.append(replace(template, tval=kind[0], sval=kind[1], count=count,
                                    slot=chr(ord("a") + len(pack))))
        if mushrooms_taken:
            for _index, mushroom in finale_prep._restoring_at_home(policy):
                pack.append(replace(mushroom, slot=chr(ord("a") + len(pack))))
            policy._home_knowledge_items = tuple(
                item for item in policy._home_knowledge_items
                if (item.tval, item.sval) != angband_finale.RESTORING)
        # DECLARED: the food step's three Wands of Wonder, each under its own inscription
        # (finale_prep FOOD; n1-c is a Zombie, its food the charges).
        pack = [item for item in pack if not finale_prep.food_stacks(replace(board, inventory=(item,)))]
        for label in finale_prep.FOOD_LABELS[:finale_prep.FOOD_WANDS]:
            pack.append(replace(template, tval=TVAL_WAND, sval=SV_WAND_WONDER, count=1, charges=20,
                                known=True, inscription=label, name="謎の魔法棒",
                                slot=chr(ord("a") + len(pack))))
        return replace(board, inventory=tuple(pack))

    # -- n1-c ------------------------------------------------------------------------------

    def test_n1c_enters_reads_home_checks_and_takes_the_supplies(self):
        policy, decided = self.n1c_until(N1C_HOME_PAGE)
        held = finale_prep.phase(policy)
        steps = [step for _sequence, step, _note in held.log]
        self.assertEqual(steps[:3], [finale_prep.HOME, finale_prep.CHECK, finale_prep.SUPPLIES])
        row, _board, key, reason = decided[N1C_ENTRY]
        self.assertEqual((key, reason), ("~9\x1b", finale_prep.HOME_REASON))  # the Home read
        # At the Home the supplies step's withdrawal is composed by the Home executor (entry and
        # withdrawal in one key).
        _row, _board, key, reason = decided[N1C_HOME_PAGE]
        self.assertTrue(reason.startswith("home-errand:atomic-withdraw:" + finale_prep.PURPOSE), reason)
        self.assertTrue(key.startswith("5p"), key)
        self.assertEqual(policy._home_errand.request.purpose, finale_prep.PURPOSE)
        # The carry holds from the supplies step: nothing deposits them again.
        self.assertTrue(finale_prep.carrying(policy))
        self.assertFalse(finale_prep.lifted(policy))

    def test_n1c_loadout_fixes_the_target_and_the_swap_composes_toward_it(self):
        policy, decided = self.n1c_until(N1C_ENTRY + 4)
        held = finale_prep.phase(policy)
        self.assertEqual(held.step, finale_prep.SUPPLIES)
        board = self.stocked(policy, decided[-1][1])
        self.decide(policy, board)   # the supplies carried: the loadout step's search fixes the set
        self.assertEqual(held.step, finale_prep.SWAP)
        self.assertEqual(len(held.target), 12)
        self.assertTrue(finale_prep.dedicated_order(policy))
        # Every other owned piece is out of the search: the transaction goes toward the target.
        catalog = policy._equipment_catalog.items
        excluded = finale_prep.excluded_ids(policy, catalog)
        self.assertEqual({finale_prep._signature(owned.id) for owned in catalog
                          if owned.id not in excluded}, set(held.target))
        session = policy._equipment_transaction_session
        self.assertIsNotNone(session)
        moved = {finale_prep._signature(action.item_id) for action in session.plan.actions
                 if action.kind in ("withdraw", "equip")}
        self.assertTrue(moved)
        self.assertLessEqual(moved, set(held.target))
        # The next search (the swap's own inputs) sees only the target's pieces.
        policy._equipment_transaction_session = None  # DECLARED: no action posted yet
        with contextlib.redirect_stdout(io.StringIO()):
            policy._prepare_equipment_optimization(board)
        surviving = {finale_prep._signature(item_id)
                     for item_id in policy._equipment_optimization_search_surviving_ids}
        self.assertTrue(surviving)
        self.assertLessEqual(surviving, set(held.target))

    def test_n1c_the_worn_target_lifts_the_cap_and_the_recall_reads_past_95(self):
        policy, decided = self.n1c_until(N1C_ENTRY + 4)
        held = finale_prep.phase(policy)
        board = self.stocked(policy, decided[-1][1])
        self.decide(policy, board)
        self.assertEqual(held.step, finale_prep.SWAP)
        self.assertEqual(angband_cap.cap(DUNGEON_ANGBAND, policy), angband_cap.ANGBAND_DEPTH_CAP)
        # DECLARED: the transaction done, the target worn.
        held.target = frozenset(finale_prep._signature(owned.id)
                                for owned in policy._equipment_catalog.items
                                if owned.origin == "equipped")
        policy._equipment_transaction_session = None
        self.decide(policy, board)
        self.assertEqual(held.step, finale_prep.RECALL)
        self.assertTrue(finale_prep.lifted(policy))
        self.assertIsNone(angband_cap.cap(DUNGEON_ANGBAND, policy))
        # The departure read toward Angband: the small-floor option first, then the recall.
        policy.last_reason = "town:recall-to-angband"
        self.assertEqual(angband_finale.town_recall_key(policy, board, "rfa"),
                         angband_finale.SMALL_FLOOR_MACRO)
        recalling = replace(board, player=replace(board.player, recalling=True))
        self.decide(policy, recalling)
        self.assertEqual(held.step, finale_prep.DONE)
        # The mark carries through the expedition to the next town.
        dungeon = replace(board, floor_key=(DUNGEON_ANGBAND, 99, 0), town_flag=False)
        angband_finale.observe(policy, dungeon)
        self.assertTrue(finale_prep.lifted(policy) and finale_prep.carrying(policy))
        policy._equipment_transaction_session = None  # DECLARED: no swap under way on arrival
        angband_finale.observe(policy, board)
        self.assertFalse(finale_prep.lifted(policy))
        # Entered again in town (the Home census current: its home step done at once).
        self.assertEqual([step for _s, step, _n in held.log], [finale_prep.HOME, finale_prep.CHECK])

    def test_n1c_every_mushroom_of_restoring_is_taken(self):
        """Owner 2026-11-21 「99F100Fに全復活のキノコをあるだけ持っていく」: every one at Home is taken
        out in the supplies step (no count, no condition) and kept.  Recorded: n1-c's Home holds a
        Mushroom of Restoring."""
        policy, decided = self.n1c_until(N1C_ENTRY + 4)
        held = finale_prep.phase(policy)
        self.assertEqual(held.step, finale_prep.SUPPLIES)
        board = self.stocked(policy, decided[-1][1], mushrooms_taken=False)
        at_home = finale_prep._restoring_at_home(policy)
        self.assertTrue(at_home)
        angband_finale.observe(policy, board)
        self.assertEqual(held.step, finale_prep.SUPPLIES)  # the counts carried, the mushroom not
        policy._home_errand.cancel_unposted()
        finale_prep.town_key(policy, board)
        request = policy._home_errand.request
        _index, mushroom = at_home[0]
        self.assertEqual((request.purpose, request.signature, request.quantity),
                         (finale_prep.PURPOSE, policy._item_signature(mushroom), mushroom.count))
        # Carried, it is kept whole (the expedition's carry).
        self.assertEqual(angband_finale.carry_target(policy, board, replace(mushroom, slot="w")),
                         angband_finale.RESTORING_CARRY)
        # DECLARED: taken out (none left at Home): the step goes on.
        policy._home_errand.cancel_unposted()
        policy._home_knowledge_items = tuple(
            item for item in policy._home_knowledge_items
            if (item.tval, item.sval) != angband_finale.RESTORING)
        angband_finale.observe(policy, board)
        self.assertEqual(held.step, finale_prep.LOADOUT)

    def test_n1c_a_step_left_unfinished_at_the_departure_stops_by_name(self):
        policy, decided = self.n1c_until(N1C_ENTRY + 4)
        held = finale_prep.phase(policy)
        self.assertEqual(held.step, finale_prep.SUPPLIES)
        finale_prep.departure_reached(policy, decided[-1][1])
        self.assertEqual(held.step, finale_prep.STOPPED)
        self.assertEqual(held.stopped, "supplies:unfinished-at-departure")
        self.assertFalse(finale_prep.carrying(policy) or finale_prep.lifted(policy))
        self.assertEqual(angband_cap.cap(DUNGEON_ANGBAND, policy), angband_cap.ANGBAND_DEPTH_CAP)

    def test_n1c_no_twilight_robe_in_the_finale_set(self):
        """Owner 2026-11-21 「99F 100Fでも宵闇のローブは禁止」: the finale's rank reads no AC, so the
        robe (TWILIGHT: every resistance, NO_AC) would win on its resistances; the searches in the
        finale's rank (the check's and the loadout step's, which fixes the target) never take it."""
        from hengbot.equipment_optimizer import ABILITY_FLAG
        from hengbot.equipment_rules import TR_NO_AC
        policy, steps = self.load(N1C)
        robe = None

        def carrying_robe(board):
            nonlocal robe
            if robe is None:
                # DECLARED: a robe of twilight carried (the worn body armour's row, AC 0, every
                # resistance, resist curse and NO_AC: without the rule it would win the rank).
                worn = next(item for item in board.equipment if item.slot == "body")
                flags = frozenset(flag for name, flag in ABILITY_FLAG.items()
                                  if name.startswith("resist_")) | {TR_NO_AC, 148}
                robe = replace(worn, slot=chr(ord("a") + len(board.inventory)),
                               name="宵闇のローブ", ac=0, to_a=0,
                               known_flags=frozenset(worn.known_flags) | flags)
            return replace(board, inventory=(*board.inventory, robe))

        for recorded, supply in steps[:N1C_ENTRY + 4]:
            board = supply()
            if recorded["row"] >= N1C_ENTRY:
                board = carrying_robe(board)
            self.decide(policy, board)
            self.deliver(policy, recorded["key"])
        held = finale_prep.phase(policy)
        # The check's own search, with the robe among the owned gear: not in its set.
        best = policy._angband_finale_feasibility.result.best
        self.assertNotIn("宵闇のローブ", [item.item.name for _slot, item in best.loadout.slots])
        angband_finale.observe(policy, carrying_robe(board))  # its done-check on the next board
        self.assertEqual(held.step, finale_prep.SUPPLIES)  # the check passed
        self.decide(policy, carrying_robe(self.stocked(policy, board)))  # the loadout step's search
        self.assertEqual(held.step, finale_prep.SWAP)
        robes = {finale_prep._signature(owned.id) for owned in policy._equipment_catalog.items
                 if owned.item.name == "宵闇のローブ"}
        self.assertTrue(robes)
        self.assertFalse(robes & held.target)

    def test_n1c_int_before_speed_beyond_the_gate(self):
        """Owner 2026-11-21 「過剰な加速よりもまず知力を十分上げることを優先して」「成功率95%まで」:
        among sets meeting the conditions, the absorbed Rockets' success up to 95% (the INT) comes
        before any speed beyond the +25 gate; past 95% the speed comes first again."""
        from hengbot.equipment_optimizer import FINALE_POWER_SUCCESS, finale_rank
        policy, decided = self.n1c_until(N1C_ENTRY + 4)
        held = finale_prep.phase(policy)
        board = self.stocked(policy, decided[-1][1])
        self.decide(policy, board)
        self.assertEqual(held.step, finale_prep.SWAP)
        best = policy._equipment_optimization_preparation.result.best
        # The search's own sets carry the Rockets' success under their INT (the game's formula).
        self.assertIsNotNone(best.metrics.finale_power_success)

        def variant(speed, success):  # DECLARED: the chosen set with these two figures
            return replace(best, metrics=replace(best.metrics, player_speed=speed,
                                                 finale_power_success=success))
        faster, surer = variant(140, FINALE_POWER_SUCCESS - 5), variant(136, FINALE_POWER_SUCCESS)
        self.assertGreater(finale_rank(surer), finale_rank(faster))
        # Past 95% the speed decides again.
        self.assertGreater(finale_rank(variant(140, FINALE_POWER_SUCCESS)),
                           finale_rank(variant(136, 99)))
        # Below the +25 gate no INT makes up for it.
        self.assertGreater(finale_rank(variant(135, 80)), finale_rank(variant(134, 99)))

    # -- n1-b ------------------------------------------------------------------------------

    def test_n1b_enters_on_arrival_and_no_ordinary_swap_starts_before_its_own(self):
        policy, steps = self.load(N1B)
        held = finale_prep.phase(policy)
        recorded, supply = steps[0]
        board = supply()
        key = self.decide(policy, board)
        self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
        # The census is current: the Home step is done at once, the check runs its search.
        self.assertEqual([step for _s, step, _n in held.log], [finale_prep.HOME, finale_prep.CHECK])
        self.assertTrue(finale_prep.holds_swap(policy))
        self.assertFalse(finale_prep.carrying(policy))


    # -- n1-b at 04:55, in a NO_MAGIC armour ----------------------------------------------

    def test_n1b_the_checked_set_has_its_own_destruction_means(self):
        """n1-b life-411's town visit of 2026-11-21 04:55:39 (tests/fixtures/n1b-411-switch-loop-1121)
        arrived in a NO_MAGIC armour: its absorbed *Destruction* is no means on that board, but the
        set the check step's search chose leaves the armour at Home, so it has the means (the
        visit's own record: the swap took the armour off and the means came back)."""
        from hengbot import destruction_use
        from hengbot.me_power_success import worn_anti_magic
        policy, steps = self.load("n1b-411-switch-loop-1121")
        held = finale_prep.phase(policy)
        held.in_town, held.step, held.since = True, finale_prep.CHECK, policy._decision_sequence  # DECLARED
        for recorded, supply in steps[:2]:
            board = supply()
            key = self.decide(policy, board)
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
            self.deliver(policy, key)
        self.assertIsNotNone(policy._angband_finale_feasibility)  # the check step's search
        angband_finale.observe(policy, board)  # its done-check on the next board
        self.assertTrue(worn_anti_magic(board))
        self.assertFalse(destruction_use.holds_means(policy, board))
        self.assertEqual(held.step, finale_prep.SUPPLIES)  # the checked set meets every condition


class FinalePrepCensusDroppedRecordedTest(unittest.TestCase):
    """n1-c life-217's town visit of 2026-11-21 11:32:22 (tests/fixtures/n1c-finale-prep-stall-1121,
    the first 33 journal rows of capture n1c-217-20261121-finale-prep-stall): the phase entered at
    row 27 (its Home read), checked at row 28 and reached the supplies step at row 29, with 98
    Healing, 24 *Healing* and 124 Restore Mana at Home and the pack holding 9, 0 and 0.  The
    full-home-sale take of a crossbow (rows 30-31) dropped the Home census, and on row 32 the
    supplies step found no Healing stack in the empty catalogue and stopped as
    ``supplies:not-at-home:75-37``; the visit then went on as the 95F exploration (the same at
    11:31:14, where the *Healing* take at slot 4 left the Restore Mana at slots 6-7 unaddressed
    and the supplies just withdrawn were deposited again on the next decision).

    DECLARED CONSTRUCTED: the census read again after row 32 (row 29's catalogue without the
    crossbow taken), and its slots past the Healing left unaddressed by an earlier take."""

    def setUp(self):
        self.scratch = TemporaryDirectory()

    def tearDown(self):
        self.scratch.cleanup()

    def until(self, last_row):
        name = "n1c-finale-prep-stall-1121"
        policy, _journal, steps = load(FIXTURES / name, Path(self.scratch.name) / name)
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        census, board = None, None
        for recorded, supply in steps[:last_row + 1]:
            board = supply()
            key = FinalePrepRecordedTest.decide(policy, board)
            if recorded["row"] < last_row:
                self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
                if recorded["row"] == 29:
                    census = policy._home_knowledge_items
                FinalePrepRecordedTest.deliver(policy, recorded["key"])
        return policy, board, key, census

    def test_a_census_dropped_by_another_take_is_read_again_not_a_stop(self):
        policy, board, key, census = self.until(32)
        held = finale_prep.phase(policy)
        self.assertEqual([step for _s, step, _n in held.log],
                         [finale_prep.HOME, finale_prep.CHECK, finale_prep.SUPPLIES])
        self.assertIsNone(held.stopped)
        self.assertEqual(held.step, finale_prep.SUPPLIES)
        self.assertFalse(policy._home_knowledge_items)  # the take dropped the census
        self.assertEqual((key, policy.last_reason), ("~9", finale_prep.HOME_REASON))
        self.assertTrue(finale_prep.carrying(policy))
        # DECLARED: the census read again; the step files the Healing take it was short of.
        crossbow = next(item for item in census if item.tval == 19)
        policy._home_knowledge_items = tuple(item for item in census if item is not crossbow)
        policy._home_knowledge_valid_before = len(policy._home_knowledge_items)
        policy._home_knowledge_current, policy._home_knowledge_invalidated = True, False
        policy._home_knowledge_scan_inflight, policy._home_knowledge_scan_epoch = False, None
        self.assertIsNone(finale_prep.town_key(policy, board))
        request = policy._home_errand.request
        self.assertEqual(request.purpose, finale_prep.PURPOSE)
        self.assertEqual(request.signature[1:], angband_finale.HEALING)
        self.assertEqual(request.quantity, 30 - 9)
        self.assertEqual(held.step, finale_prep.SUPPLIES)

    def test_a_stack_an_earlier_take_left_unaddressed_is_filed_for_the_errands_read(self):
        policy, board, _key, census = self.until(32)
        held = finale_prep.phase(policy)
        # DECLARED: the census current, but an earlier take at slot 3 left the later slots
        # (the Healing at slot 3 among them) to a fresh read.
        crossbow = next(item for item in census if item.tval == 19)
        policy._home_knowledge_items = tuple(item for item in census if item is not crossbow)
        healing = next(index for index, item in enumerate(policy._home_knowledge_items)
                       if (item.tval, item.sval) == angband_finale.HEALING)
        policy._home_knowledge_valid_before = healing
        policy._home_knowledge_current, policy._home_knowledge_invalidated = True, False
        self.assertIsNone(finale_prep.town_key(policy, board))
        self.assertIsNone(held.stopped)
        request = policy._home_errand.request
        self.assertEqual((request.purpose, request.signature[1:]),
                         (finale_prep.PURPOSE, angband_finale.HEALING))
        self.assertTrue(policy._home_errand.needs_knowledge)  # the errand reads the Home first


if __name__ == "__main__":
    unittest.main()
