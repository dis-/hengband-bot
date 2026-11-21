"""n1-c life-220: three equipment round trips in one morning (2026-11-22), one owner per visit.

Owner 2026-11-22 「決まりは足さず、着け直しを記録。往復が起きたら停止して直す。」 and Q1 (decide the
visit's target once; decide again on buying, picking up, withdrawing from Home).  n1-c life-220
(Magic-Eater Lv21-23) stopped three times on the E0 round-trip stop; every A, B, A was the visit
target's own transaction (policy_equipment ``_equipment_transaction_home_key``), the target
decided twice:

* feet, 06:53:42 (bot-cc0ba74d6): the visit wore its target's 浮遊の軟革ブーツ over the 硬革ブーツ;
  then *Identify* made a carried 革グローブ [1] a [1,+2] (``candidate-gained``) and the whole search,
  every slot open again, chose the 硬革ブーツ back (the 1% margin band of
  equipment_optimizer ``_stable_operational_best`` held the two boots equal beside the [1,+0]
  gloves, 34.32 / 34.62 survival, not beside the [1,+2] ones, 34.80 / 35.47).  Fix: a piece the
  visit already owned that is only known better is ``candidate-identified``: the search runs
  over the held target and the better-known pieces (equipment_target
  ``identified_search_exclusion``).
* sub_ring, 07:23:21: the target put 耐火の指輪 with 耐冷の指輪, the transaction deposited the
  浮遊の指輪; the destination's band moved (19 -> 20, ``destination-band-floor``) and the new
  search wore the 浮遊の指輪 again.  The two rings tied on every metric and the last tie-break
  was the catalogue ids, which name where a piece is ('equipped:4827..' over 'equipped:2ca7..',
  then 'home:2ca7..' over 'equipped:4827..').  Fix: the tie-break reads the pieces' identities.
* body, 07:45:12 (bot-af35fa0d9): the visit's start planned the transaction (胴丸 over the
  オログのローブ); it waited behind Quest 25's reward (a ring, picked up) and two *Identify*s
  (耐混乱の指輪, スピードの硬革ブーツ (+4)), the in-flight session returned the old target on every
  decision, wore the 胴丸, and only its end let the search see the gains: robe back on.  Fix:
  a session that has moved nothing yields to a gained or better-known candidate.

Recorded (tests/extract_n1c_220_flipflops_1122_fixtures.py): each stop's town-arrival
checkpoint and the journal rows read here.

DECLARED CONSTRUCTED:

* feet: the character calibration at Lv21.  The checkpoint's sidecar is the Lv20 one (stale:
  ``calibration-stale:level``) and the dump the visit wrote at its row 4 is not in the capture;
  it is the sidecar with the level, base HP (max HP minus the CON bonus, as
  ``derive_equipped_calibration``) and HP floor of row 134's board.  With it the search gives
  the live loadout-report's survival exactly (34.3164616741415 at 06:52:35, 35.46982214841637 and
  34.79982401589997 at 06:53:40).  The Home is row 131's page (the visit's last Home page before
  the *Identify*), the visit's target the search on row 134's board.
* sub_ring: the 浮遊の指輪 moved to the Home in the search's catalogue (the transaction's
  deposit, rows 33-36) with the destination floor of the re-decision (band 20).
* body: rows 2-61 (Quest 25's walk and claim) are left out; the boards of rows 62-65 are decided
  in order after rows 0-1.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import hengbot.policy  # noqa: F401 -- import order (circular import when run alone)
from hengbot import equipment_target, equipment_visit_journal
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.warrior_optimization import (
    constitution_hp_bonus, load_character_calibration, prepare_warrior_optimization,
)
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures") / "n1c-220-flipflops-1122"
HARD_BOOTS = "硬革ブーツ [3,+6]"
LEVITATION_BOOTS = "浮遊の軟革ブーツ [2,+5] {r恐;浮}"
LEVITATION_RING = "浮遊の指輪"
ROBE = "オログのローブ"
SPEED_BOOTS = "スピードの硬革ブーツ"
CONFUSION_RING = "耐混乱の指輪"


def _quiet(call, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return call(*args, **kwargs)


def _slots(result) -> dict:
    return {slot: owned.item.name for slot, owned in result.best.loadout.slots}


def _post(policy, recorded) -> None:
    posted = recorded["key"]
    if posted:
        policy.confirm_key_posted(posted)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, posted):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": posted})


class FeetIdentifiedGlovesTest(unittest.TestCase):
    """06:53: *Identify* of a carried piece does not reopen the visit's boots."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.addClassCleanup(cls.scratch.cleanup)
        policy, journal, _steps = _quiet(load, FIXTURES / "feet", Path(cls.scratch.name))
        cls.rows = json.loads((FIXTURES / "feet" / "rows.json").read_text(encoding="utf-8"))
        boards = {}
        for row, entry in zip(cls.rows, journal):
            line = entry["line"] if entry["line"] is not None else entry["inputs"][-1]
            boards[row] = policy._with_cached_skill_exp(
                parse_snapshot(json.loads(line), policy._monrace_knowledge))
        recorded = load_character_calibration(policy._character_calibration_path)
        level = boards[134].player.level
        # DECLARED CONSTRUCTED (module docstring): the Lv21 calibration.
        cls.calibration = replace(
            recorded, level=level, hp_floor=level + 1,
            base_hp=boards[134].player.max_hp
            - constitution_hp_bonus(recorded.base_stats[4], level))
        policy._adopt_home_catalogue(tuple(
            policy._inventory_item_from_store_item(item) for item in boards[131].store.items))
        cls.policy, cls.boards = policy, boards
        cls.catalogue = {}
        for row in (134, 135):
            policy._refresh_carried_equipment_catalog(boards[row])
            cls.catalogue[row] = policy._operational_equipment_catalog(boards[row])
        cls.decided = cls.search(134)
        candidates, pieces = policy._visit_candidate_census(cls.catalogue[134])
        cls.held = equipment_target.VisitTarget(
            1, candidates, (None, 19, 0, (False, False)), cls.decided.result, pieces)
        policy._home_disposal.history_path.unlink(missing_ok=True)

    @classmethod
    def search(cls, row, excluded=frozenset()):
        return _quiet(prepare_warrior_optimization, cls.boards[row], cls.catalogue[row],
                      cls.policy._monrace_knowledge, depth=None, home_scan_complete=True,
                      calibration=cls.calibration, timeout_seconds=120.0,
                      search_excluded_item_ids=excluded)

    def test_recorded_boards(self):
        self.assertEqual(self.rows, [131, 134, 135])
        carried = {row: [item.name for item in self.boards[row].inventory
                         if item.name.startswith("革グローブ")] for row in (134, 135)}
        self.assertEqual(carried, {134: ["革グローブ [1]"], 135: ["革グローブ [1,+2]"]})
        worn = {item.slot: item.name for item in self.boards[135].equipment}
        self.assertEqual(worn["feet"], LEVITATION_BOOTS)
        self.assertIn(HARD_BOOTS, [item.name for item in self.boards[131].store.items])

    def test_the_visit_target_wears_the_levitation_boots(self):
        """The live target (survival as loadout-report 06:52:35)."""
        self.assertEqual(_slots(self.decided.result)["feet"], LEVITATION_BOOTS)
        self.assertEqual(self.decided.result.best.metrics.survival_turns, 34.3164616741415)

    def test_the_whole_search_after_the_identify_takes_the_boots_back(self):
        """What the live re-decision did (loadout-report 06:53:40): the round trip's B -> A."""
        best = self.search(135).result
        self.assertEqual(_slots(best)["feet"], HARD_BOOTS)
        self.assertEqual(best.best.metrics.survival_turns, 35.46982214841637)

    def test_the_identify_is_a_better_known_piece_not_a_gained_one(self):
        """On main the [1,+2] gloves were ``candidate-gained``: the whole search ran."""
        candidates, pieces = self.policy._visit_candidate_census(self.catalogue[135])
        self.assertEqual(
            equipment_target.redecide_events(self.held, candidates, self.held.context, pieces),
            (equipment_target.EVENT_CANDIDATE_IDENTIFIED,))

    def test_the_held_target_takes_the_gloves_and_keeps_the_boots(self):
        candidates, pieces = self.policy._visit_candidate_census(self.catalogue[135])
        excluded, events = equipment_target.identified_search_exclusion(
            self.held, self.catalogue[135], candidates, pieces,
            self.policy._usable_unidentified_candidate)
        self.assertEqual(events, ())
        best = self.search(135, excluded).result
        self.assertEqual(_slots(best)["feet"], LEVITATION_BOOTS)
        self.assertEqual(_slots(best)["arms"], "革グローブ [1,+2]")
        self.assertEqual(best.best.metrics.survival_turns, 34.79982401589997)


class SubRingTieTest(unittest.TestCase):
    """07:23: the tie between the cold and the levitation ring does not read where they are."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.addClassCleanup(cls.scratch.cleanup)
        policy, _journal, steps = _quiet(load, FIXTURES / "sub_ring", Path(cls.scratch.name))
        cls.replayed = []
        for recorded, supply in steps[:29]:
            board = supply()
            key = _quiet(policy.choose_key, board)
            cls.replayed.append((recorded, key, policy.last_reason))
            _post(policy, recorded)
        cls.policy, cls.board = policy, board
        cls.held = equipment_target.visit_target(policy, policy._town_visit_epoch)
        _quiet(policy._prepare_equipment_optimization, policy._with_cached_skill_exp(board))
        cls.stash = policy._equipment_shelf_search
        policy._home_disposal.history_path.unlink(missing_ok=True)

    def test_the_visit_replays_unchanged_to_its_first_ring_move(self):
        for recorded, key, reason in self.replayed:
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]),
                             recorded["row"])
        self.assertEqual(self.replayed[-1][1], "tb")   # the shield off; row 29 was 'te'

    def test_the_ring_after_the_deposit_is_the_visit_targets(self):
        """On main the target took the cold ring ('equipped:4827..' > 'equipped:2ca7..') and the
        same search with the levitation ring in the Home took that one ('home:..' first)."""
        held = _slots(self.held.result)
        _sequence, board, _signature, catalog, inputs, finale, cap_lifted = self.stash
        levitation = next(owned for owned in catalog
                          if owned.item.name.startswith(LEVITATION_RING))
        self.assertEqual(levitation.origin, "equipped")
        # DECLARED CONSTRUCTED (module docstring): the ring deposited, the band moved to 20.
        deposited = tuple(
            replace(owned, id=owned.id.replace("equipped:", "home:"), origin="home",
                    equipped_slot=None) if owned is levitation else owned
            for owned in catalog)
        after = _quiet(prepare_warrior_optimization, board, deposited,
                       self.policy._monrace_knowledge,
                       **{**inputs, "destination_floor": 20, "loadout_report_path": None},
                       finale=finale, cap_lifted=cap_lifted)
        self.assertEqual(_slots(after.result)["sub_ring"], held["sub_ring"])
        self.assertEqual(_slots(after.result)["main_ring"], held["main_ring"])


class BodyUnstartedSessionTest(unittest.TestCase):
    """07:45: the unstarted transaction yields to Quest 25's reward and the *Identify*s."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.addClassCleanup(cls.scratch.cleanup)
        policy, _journal, steps = _quiet(load, FIXTURES / "body", Path(cls.scratch.name))
        cls.rows = json.loads((FIXTURES / "body" / "rows.json").read_text(encoding="utf-8"))
        cls.seen = {}
        for row, (recorded, supply) in zip(cls.rows, steps):
            board = supply()
            key = _quiet(policy.choose_key, board)
            held = equipment_target.visit_target(policy, policy._town_visit_epoch)
            session = policy._equipment_transaction_session
            cls.seen[row] = (board, _slots(held.result),
                             None if session is None else session.started)
            if key == recorded["key"]:
                _post(policy, recorded)
        cls.searches = [row.get("events") for row in equipment_visit_journal.journal(policy)["rows"]
                        if row["kind"] == "search"]
        policy._home_disposal.history_path.unlink(missing_ok=True)

    def test_recorded_boards(self):
        self.assertEqual(self.rows, [0, 1, 62, 63, 64, 65])
        worn = {item.slot: item.name for item in self.seen[65][0].equipment}
        self.assertTrue(worn["body"].startswith(ROBE))
        pack = [item.name for item in self.seen[62][0].inventory]
        self.assertIn("サファイアの指輪", pack)          # Quest 25's reward, unidentified

    def test_the_visit_start_target_wears_the_dou_maru(self):
        self.assertTrue(self.seen[0][1]["body"].startswith("胴丸"))
        self.assertFalse(self.seen[1][2])            # planned, nothing moved yet

    def test_the_reward_decides_again_before_the_session_moves(self):
        """On main the in-flight session returned the start's target until it had worn the
        胴丸; the reward's ring and the identified boots decided only after its deposit."""
        self.assertEqual(self.searches[:2], [["visit-start"], ["candidate-gained"]])
        self.assertTrue(self.seen[62][1]["body"].startswith(ROBE))

    def test_the_identifies_join_the_target_and_keep_the_robe(self):
        self.assertEqual(self.searches[2:],
                         [["candidate-identified"]] * (len(self.searches) - 2))
        target = self.seen[65][1]
        self.assertTrue(target["body"].startswith(ROBE))
        self.assertTrue(target["feet"].startswith(SPEED_BOOTS))
        self.assertIn(CONFUSION_RING, (target["main_ring"], target["sub_ring"]))
        for row in (62, 63, 64, 65):
            self.assertTrue(self.seen[row][1]["body"].startswith(ROBE), row)
            self.assertFalse(self.seen[row][2], row)


if __name__ == "__main__":
    unittest.main()
