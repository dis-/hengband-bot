import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from policy_fixtures import (
    grid,
    hostile,
    item,
    player,
    set_completed_equipment_optimization,
)

from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.policy_constants import POLICY_FINAL_STOP_REASONS
from hengbot.model import (
    DUNGEON_ANGBAND,
    DUNGEON_CHAMELEON_CAVE,
    DUNGEON_YEEK_CAVE,
    PLAYER_CLASS_WARRIOR,
    Position,
    SV_FLASK_OIL,
    SV_LITE_LANTERN,
    SV_SCROLL_WORD_OF_RECALL,
    SV_STAFF_IDENTIFY,
    Snapshot,
    TVAL_FLASK,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_POTION,
    TVAL_SCROLL,
    TVAL_STAFF,
)
from hengbot.policy import (
    EMPTY_DIVE_LIMIT,
    HengbotPolicy,
    NO_DEPTH_PROGRESS_DIVE_LIMIT,
    OVEREXTEND_LOOT_MAX,
)


class StatusTest(unittest.TestCase):
    def test_flees_instead_of_meleeing_when_afraid(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 11): grid(10, 11, monster=True),
        }
        mon = hostile(1, 10, 11, hp=10)
        snap = Snapshot(player(10, 10, hp=20, max_hp=20, afraid=True), grids, [mon])
        # Cannot attack while afraid → step away west, never toward the monster (6).
        self.assertEqual(HengbotPolicy().choose_key(snap), "4")

    def test_waits_when_confused_and_safe(self):
        grids = self._grids_with_frontier()
        snap = Snapshot(player(10, 10, confused=True), grids, [])
        self.assertEqual(HengbotPolicy().choose_key(snap), "5")

    def _grids_with_frontier(self):
        return {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, known=False),
        }


class OverExtensionDungeonSwitchTest(unittest.TestCase):
    # Angband is recommended for clvl 30+. A clvl-23 warrior dives it, collects
    # nothing (everything out-damages/out-runs it), and emergency-teleports out.
    # After a run of such empty dives the bot must recall into the deepest
    # already-unlocked dungeon its level can actually loot instead.
    ALL_ENTERED = (DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE, 3, 4, 7, 14)
    # Abilities covering 20F (free action/fire), 21-25F (plus confusion), and
    # 26-30F (pois/cold/elec/acid)
    # bands, so the Mountain (25F entry) counts as resistance-safe for these tests.
    MOUNTAIN_SAFE = frozenset(
        {"free_action", "resist_conf", "resist_fire", "resist_pois", "resist_cold",
         "resist_elec", "resist_acid"}
    )

    def _dk(self):
        return {
            DUNGEON_ANGBAND: DungeonInfo(DUNGEON_ANGBAND, "Angband", 1, 127, 30),
            DUNGEON_YEEK_CAVE: DungeonInfo(DUNGEON_YEEK_CAVE, "Galgals", 1, 13, 1),
            3: DungeonInfo(3, "Orc Cave", 10, 22, 5),
            4: DungeonInfo(
                4, "Labyrinth", 10, 18, 1,
                flags=frozenset({"MAZE", "FORGET"}), guardian_id=1034,
            ),
            7: DungeonInfo(7, "Forest", 15, 32, 5),
            14: DungeonInfo(14, "Mountain", 25, 45, 20),
            DUNGEON_CHAMELEON_CAVE: DungeonInfo(
                DUNGEON_CHAMELEON_CAVE, "Chameleon cave", 30, 45, 30
            ),
        }

    def _policy(self):
        policy = HengbotPolicy(dungeon_knowledge=self._dk())
        set_completed_equipment_optimization(policy)
        return policy

    # All conquerable-within-limit dungeons marked conquered, so the conquest-target
    # override stays out of the way and these tests isolate the over-extension switch.
    ALL_CONQUERED = (3, 4, 7, 14)

    def _town(
        self, *, clvl=23, recall_depth=26, entered=None, abilities=None,
        conquered=None, angband_unlocked=True,
    ):
        return Snapshot(
            player(10, 10, hp=255, max_hp=255, level=clvl, class_id=PLAYER_CLASS_WARRIOR,
                   abilities=self.MOUNTAIN_SAFE if abilities is None else abilities),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            recall_dungeon_id=DUNGEON_ANGBAND,
            recall_depth=recall_depth,
            entered_dungeon_ids=self.ALL_ENTERED if entered is None else entered,
            conquered_dungeon_ids=(
                self.ALL_CONQUERED if conquered is None else conquered
            ),
            angband_recall_unlocked=angband_unlocked,
        )

    def _dungeon(
        self, dungeon_id, level, *, clvl=23, recall_depth=26, abilities=None,
        conquered=None, angband_unlocked=True,
    ):
        return Snapshot(
            player(10, 10, hp=255, max_hp=255, level=clvl, class_id=PLAYER_CLASS_WARRIOR,
                   abilities=self.MOUNTAIN_SAFE if abilities is None else abilities),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(dungeon_id, level, 0),
            recall_dungeon_id=DUNGEON_ANGBAND,
            recall_depth=recall_depth,
            entered_dungeon_ids=self.ALL_ENTERED,
            conquered_dungeon_ids=(
                self.ALL_CONQUERED if conquered is None else conquered
            ),
            angband_recall_unlocked=angband_unlocked,
        )

    def _run_dive(
        self, pol, *, loot=0, emergencies=0, dungeon_id=DUNGEON_ANGBAND, level=26,
        clvl=23, recall_depth=26, abilities=None, conquered=None,
        angband_unlocked=True,
    ):
        dung = self._dungeon(
            dungeon_id, level, clvl=clvl, recall_depth=recall_depth,
            abilities=abilities, conquered=conquered,
            angband_unlocked=angband_unlocked,
        )
        pol.last_reason = "descend"
        pol._observe(dung)  # prev=town -> dive begins
        for _ in range(loot):
            pol.last_reason = "victory:pickup"
            pol._observe(dung)  # counts a pickup
        for _ in range(emergencies):
            pol.last_reason = "emergency:teleport"
            pol._observe(dung)  # counts an emergency escape
        pol.last_reason = "town:return"
        pol._observe(self._town(
            clvl=clvl, recall_depth=recall_depth, abilities=abilities,
            conquered=conquered, angband_unlocked=angband_unlocked,
        ))  # dive ends

    # An over-extended dive mirrors the real telemetry: one trivial pickup and a
    # run of emergency teleports that drain the escape kit.
    OVEREXTENDED = dict(loot=1, emergencies=3)

    def _guardian_bounce(self, pol, trigger):
        """Arrive at Labyrinth (4), then be recalled straight back with the given
        return trigger and no loot — the town<->guardian flip-flop shape."""
        dung = self._dungeon(4, 18, conquered=(3, 7, 14), angband_unlocked=False)
        pol.last_reason = "descend"
        pol._observe(dung)  # dive begins
        pol._target_dungeon_id = 4
        if trigger == "guardian-kit-insufficient":
            # The real return start on the guardian floor: a trigger merely
            # left over from an earlier return is not this dive's bounce
            # (guardian-recall-pingpong-r3).
            self.assertTrue(pol._should_start_town_return(dung))
        else:
            pol._last_return_trigger = trigger
        self.assertEqual(pol._last_return_trigger, trigger)
        pol.last_reason = "town:return"
        pol._observe(self._town(conquered=(3, 7, 14), angband_unlocked=False))

    def test_guardian_kit_bounce_counts_as_over_extension(self):
        pol = self._policy()
        pol._conquest_committed = 4
        pol._target_dungeon_id = 4
        pol._target_empty_dives = 0
        self._guardian_bounce(pol, "guardian-kit-insufficient")
        # The empty guardian bounce is counted, so the empty-dive valve can act
        # instead of flip-flopping forever.
        self.assertEqual(pol._target_empty_dives, 1)

    def test_quiet_non_guardian_dive_still_holds_the_streak(self):
        pol = self._policy()
        pol._target_dungeon_id = 4
        pol._target_empty_dives = 0
        self._guardian_bounce(pol, "recall-low")
        # A non-guardian quiet return keeps the existing HOLD behaviour.
        self.assertEqual(pol._target_empty_dives, 0)

    def test_recall_departure_target_clears_arrival_return_threshold(self):
        # Threshold-inversion guard: departing town by recall to a non-Angband /
        # non-Yeek dungeon (Labyrinth) must leave enough recall that, after the
        # one scroll the descent itself consumes, the arrival count still clears
        # the return threshold. Otherwise the bot recalls straight back and
        # flip-flops. Already satisfied by the +1 departure allowance in
        # _recall_required_target; this locks the invariant against regression.
        pol = self._policy()
        pol._deepest_level = 18
        pol._target_dungeon_id = 4
        town = self._town(angband_unlocked=False, conquered=(3, 7, 14))
        required = pol._recall_required_target(town)
        self.assertEqual(required, pol._recall_target(pol._planned_depth()))

    # --- _pick_alternate_dungeon ------------------------------------------
    def test_picks_shallowest_recall_selectable_dungeon(self):
        pol = self._policy()
        pol._last_overextended_depth = 26
        snap = self._town()
        self.assertEqual(pol._pick_alternate_dungeon(snap), 3)

    def test_skips_a_dungeon_whose_entry_needs_a_missing_resistance(self):
        # The character lacks confusion resistance, so the Mountain (25F entry needs
        # it) is NOT resistance-safe — steer to a sub-20F dungeon with no requirement
        # (Forest 15F) rather than repeating the swarmed, zero-loot Mountain dive.
        pol = self._policy()
        pol._last_overextended_depth = 26
        snap = self._town(abilities=frozenset({"resist_fire", "resist_pois"}))  # no conf
        self.assertEqual(pol._pick_alternate_dungeon(snap), 3)

    def test_alternate_selection_picks_deepest_dungeon_at_or_below_limit(self):
        pol = self._policy()
        snap = self._town(
            abilities=frozenset({"free_action", "resist_fire", "resist_conf"})
        )

        self.assertEqual(
            pol._pick_alternate_dungeon(
                snap, max_entry_depth=20, prefer_deepest=True
            ),
            7,
        )

    def test_owned_loadout_depth_is_not_inferred_from_recall_destinations(self):
        pol = self._policy()
        pol._deepest_level = 31
        pol._target_dungeon_id = DUNGEON_ANGBAND
        snap = replace(
            self._town(clvl=30, abilities=self.MOUNTAIN_SAFE),
            dungeon_recall_depths={1: 32, 3: 23, 4: 18, 7: 24, 14: 25},
        )
        invalid = SimpleNamespace(
            blockers=("no-valid-loadout",),
            result=SimpleNamespace(best=None),
        )
        valid_30f = SimpleNamespace(
            blockers=(),
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(best=SimpleNamespace(loadout=SimpleNamespace())),
        )

        def prepare(_snapshot, *, depth_override=None):
            return valid_30f if depth_override == 30 else invalid

        with patch.object(
            pol, "_carry_procurement_strategy", return_value=None
        ), patch.object(
            pol, "_prepare_equipment_optimization", side_effect=prepare
        ), patch.object(
            pol, "_next_required_store_type", return_value=None
        ):
            self.assertFalse(hasattr(pol, "_activate_loadout_depth_fallback"))

        self.assertEqual(pol._equipment_optimization_depth(snap), 19)

    def test_alternate_selection_uses_recall_landing_not_entrance_depth(self):
        pol = self._policy()
        snap = replace(
            self._town(
                abilities=frozenset({"resist_fire", "resist_pois"}),
                conquered=(),
            ),
            # Labyrinth lands at 16, below its unbeatable guardian's floor
            # (max depth 18): a landing ON that floor is never a fallback
            # (guardian-recall-pingpong, 2026-09-25).
            dungeon_recall_depths={3: 23, 4: 16, 7: 21, 14: 25},
        )

        self.assertEqual(
            pol._pick_alternate_dungeon(snap, max_entry_depth=20),
            4,
        )

        pol._alternate_dungeon = 4
        self.assertEqual(pol._equipment_optimization_depth(snap), 19)

    def test_steps_down_when_the_alternate_also_over_extends(self):
        pol = self._policy()
        pol._last_overextended_depth = 25  # Mountain came up empty too
        self.assertEqual(pol._pick_alternate_dungeon(self._town()), 3)

    def test_never_re_picks_the_alternate_it_is_leaving(self):
        # Even if the bot descended past Mountain's entrance before giving up (so
        # the recorded depth exceeds Mountain's own minDepth), switching away from
        # Mountain must step DOWN, never back into Mountain.
        pol = self._policy()
        pol._alternate_dungeon = 14  # currently in Mountain, over-extended
        pol._last_overextended_depth = 30  # reached L30 there before bailing
        self.assertEqual(pol._pick_alternate_dungeon(self._town()), 3)

    def test_alternate_selection_does_not_use_player_level(self):
        pol = self._policy()
        pol._last_overextended_depth = 26
        snap = self._town(clvl=3)
        self.assertEqual(pol._pick_alternate_dungeon(snap), 3)

    def test_never_picks_a_conquered_forgetting_maze_as_fallback(self):
        pol = self._policy()
        pol._last_overextended_depth = 20
        snap = self._town(
            clvl=30,
            entered=(DUNGEON_ANGBAND, 4),
            conquered=(4,),
        )

        self.assertIsNone(pol._pick_alternate_dungeon(snap))

    def test_never_picks_chameleon_cave_as_fallback(self):
        pol = self._policy()
        snap = replace(
            self._town(clvl=30, conquered=()),
            entered_dungeon_ids=(
                DUNGEON_ANGBAND,
                DUNGEON_CHAMELEON_CAVE,
                14,
            ),
            dungeon_recall_depths={
                DUNGEON_CHAMELEON_CAVE: 30,
                14: 25,
            },
        )

        self.assertEqual(
            pol._pick_alternate_dungeon(
                snap, max_entry_depth=30, prefer_deepest=True
            ),
            14,
        )

    def test_never_switches_to_angband_or_the_yeek_cave(self):
        pol = self._policy()
        pol._last_overextended_depth = 200
        # Only Angband and the fundraising Yeek Cave are unlocked -> no fallback.
        snap = self._town(entered=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE))
        self.assertIsNone(pol._pick_alternate_dungeon(snap))

    def test_bounded_alternate_selection_can_use_the_yeek_cave(self):
        pol = self._policy()
        snap = replace(
            self._town(
                clvl=30,
                entered=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE),
            ),
            dungeon_recall_depths={DUNGEON_YEEK_CAVE: 19},
        )

        self.assertEqual(
            pol._pick_alternate_dungeon(
                snap,
                max_entry_depth=19,
                prefer_deepest=True,
                allow_yeek_cave=True,
            ),
            DUNGEON_YEEK_CAVE,
        )

    # --- _observe dive accounting -----------------------------------------
    def test_switches_after_a_run_of_over_extended_dives(self):
        pol = self._policy()
        for _ in range(EMPTY_DIVE_LIMIT):
            self._run_dive(pol, **self.OVEREXTENDED)
        self.assertEqual(pol._alternate_dungeon, 3)
        self.assertEqual(pol._target_dungeon_id, 3)

    def test_unentered_alternate_is_not_a_walk_in_target(self):
        pol = self._policy()
        pol._alternate_dungeon = 7
        pol._target_dungeon_id = DUNGEON_ANGBAND
        snap = self._town(
            entered=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE),
            abilities=frozenset(),
        )

        pol._observe(snap)

        self.assertEqual(pol._alternate_dungeon, 7)
        self.assertEqual(pol._target_dungeon_id, DUNGEON_ANGBAND)

    def test_a_productive_dive_resets_the_streak(self):
        pol = self._policy()
        self._run_dive(pol, **self.OVEREXTENDED)
        self._run_dive(pol, **self.OVEREXTENDED)
        self._run_dive(pol, loot=5)  # above the four-pickup bar resets the counter
        self.assertEqual(pol._target_empty_dives, 0)
        self._run_dive(pol, **self.OVEREXTENDED)
        self.assertIsNone(pol._alternate_dungeon)  # streak restarted, no switch yet

    def test_switches_after_five_looted_dives_without_new_depth(self):
        pol = self._policy()
        for _ in range(NO_DEPTH_PROGRESS_DIVE_LIMIT):
            self._run_dive(
                pol,
                loot=4,
                emergencies=0,
                level=19,
                recall_depth=19,
            )

        self.assertEqual(pol._alternate_dungeon, 7)
        self.assertEqual(pol._target_dungeon_id, 7)
        self.assertEqual(pol._no_depth_progress_dives, 0)

    def test_new_recall_depth_resets_no_depth_progress_streak(self):
        pol = self._policy()
        for _ in range(NO_DEPTH_PROGRESS_DIVE_LIMIT - 1):
            self._run_dive(pol, loot=4, level=19, recall_depth=19)

        floor19 = self._dungeon(DUNGEON_ANGBAND, 19, recall_depth=19)
        pol.last_reason = "descend"
        pol._observe(floor19)
        floor20 = self._dungeon(DUNGEON_ANGBAND, 20, recall_depth=20)
        pol.last_reason = "descend"
        pol._observe(floor20)
        pol.last_reason = "town:return"
        pol._observe(self._town(recall_depth=20))

        self.assertEqual(pol._no_depth_progress_dives, 0)
        self.assertIsNone(pol._alternate_dungeon)

    def test_conquest_target_is_demoted_after_over_extended_dives(self):
        pol = self._policy()
        pol._target_dungeon_id = 7
        pol._conquest_committed = 7
        abilities = self.MOUNTAIN_SAFE | {"resist_chaos"}
        conquered = (3, 4, 14)

        for _ in range(EMPTY_DIVE_LIMIT):
            self._run_dive(
                pol, dungeon_id=7, level=32, recall_depth=32,
                abilities=abilities, conquered=conquered,
                angband_unlocked=False, **self.OVEREXTENDED,
            )

        self.assertEqual(pol._alternate_dungeon, 3)
        self.assertEqual(pol._target_dungeon_id, 3)
        self.assertIsNone(pol._conquest_committed)

    def test_guardian_conquest_discards_alternate_and_selects_ordinary_target(self):
        pol = self._policy()
        pol._alternate_dungeon = 14
        pol._last_overextended_depth = 26
        pol._target_dungeon_id = 14
        abilities = self.MOUNTAIN_SAFE | {"resist_chaos"}
        before = self._town(
            clvl=30, recall_depth=32, abilities=abilities,
            conquered=(3, 4), angband_unlocked=False,
        )
        conquered = replace(before, conquered_dungeon_ids=(3, 4, 14))

        with patch.object(pol, "_guardian_fight_viable", return_value=True):
            pol._observe(before)
            pol._observe(conquered)

        self.assertIsNone(pol._alternate_dungeon)
        self.assertEqual(pol._last_overextended_depth, 0)
        self.assertEqual(pol._conquest_committed, 7)
        self.assertEqual(pol._target_dungeon_id, 7)

    def test_productive_conquest_dive_resets_streak_without_unlatching(self):
        pol = self._policy()
        pol._target_dungeon_id = 7
        pol._conquest_committed = 7
        pol._target_empty_dives = EMPTY_DIVE_LIMIT - 1
        abilities = self.MOUNTAIN_SAFE | {"resist_chaos"}

        self._run_dive(
            pol, dungeon_id=7, level=32, recall_depth=32,
            loot=OVEREXTEND_LOOT_MAX + 1, abilities=abilities,
            conquered=(3, 4, 14), angband_unlocked=False,
        )

        self.assertEqual(pol._target_empty_dives, 0)
        self.assertEqual(pol._conquest_committed, 7)
        self.assertIsNone(pol._alternate_dungeon)

    def test_four_pickups_still_count_as_over_extended(self):
        pol = self._policy()
        for _ in range(EMPTY_DIVE_LIMIT):
            self._run_dive(pol, loot=4, emergencies=3)
        self.assertEqual(pol._alternate_dungeon, 3)

    def test_five_pickups_reset_the_over_extension_streak(self):
        pol = self._policy()
        self._run_dive(pol, **self.OVEREXTENDED)
        self._run_dive(pol, loot=5, emergencies=3)
        self.assertEqual(pol._target_empty_dives, 0)
        self.assertIsNone(pol._alternate_dungeon)

    def test_a_quiet_empty_dive_without_danger_is_not_over_extended(self):
        # Zero loot but zero danger just means we found nothing — the character is
        # not out of its depth, so do not abandon the dungeon over bad luck.
        pol = self._policy()
        for _ in range(EMPTY_DIVE_LIMIT):
            self._run_dive(pol, loot=0, emergencies=0)
        self.assertEqual(pol._target_empty_dives, 0)
        self.assertIsNone(pol._alternate_dungeon)

    def test_a_single_emergency_does_not_flag_a_dive(self):
        pol = self._policy()
        for _ in range(EMPTY_DIVE_LIMIT):
            self._run_dive(pol, loot=0, emergencies=1)  # one escape is just a scare
        self.assertEqual(pol._target_empty_dives, 0)
        self.assertIsNone(pol._alternate_dungeon)

    def test_a_mild_unproductive_dive_holds_the_streak(self):
        # Live turn ~1213k: after two clearly over-extended dives, a 0-loot dive with
        # a single emergency must NOT reset the streak to zero (weak evidence), or
        # the switch could never accumulate; it holds until the next bad dive tips it.
        pol = self._policy()
        self._run_dive(pol, **self.OVEREXTENDED)      # streak 1
        self._run_dive(pol, **self.OVEREXTENDED)      # streak 2
        self._run_dive(pol, loot=0, emergencies=1)    # mild: HOLD at 2
        self.assertEqual(pol._target_empty_dives, 2)
        self.assertIsNone(pol._alternate_dungeon)
        self._run_dive(pol, **self.OVEREXTENDED)      # streak 3 -> switch
        self.assertEqual(pol._alternate_dungeon, 3)

    def test_only_a_profitable_dive_clears_the_streak(self):
        pol = self._policy()
        self._run_dive(pol, **self.OVEREXTENDED)      # streak 1
        self._run_dive(pol, loot=0, emergencies=0)    # quiet empty: HOLD at 1
        self.assertEqual(pol._target_empty_dives, 1)
        self._run_dive(pol, loot=5)                   # real haul: clears to 0
        self.assertEqual(pol._target_empty_dives, 0)

    def test_fundraising_yeek_cave_dives_do_not_count(self):
        pol = self._policy()
        pol._fundraising_mode = "mine"
        for _ in range(EMPTY_DIVE_LIMIT + 1):
            self._run_dive(pol, dungeon_id=DUNGEON_YEEK_CAVE, level=1, **self.OVEREXTENDED)
        self.assertEqual(pol._target_empty_dives, 0)
        self.assertIsNone(pol._alternate_dungeon)

    def test_level_gain_does_not_release_alternate(self):
        pol = self._policy()
        pol._alternate_dungeon = 14
        pol._last_overextended_depth = 26
        pol._observe(self._town(clvl=50))
        self.assertEqual(pol._alternate_dungeon, 14)
        self.assertEqual(pol._last_overextended_depth, 26)
        self.assertEqual(pol._target_dungeon_id, 14)

    def test_loadout_depth_fallback_survives_town_observation_at_main_level(self):
        pol = self._policy()
        pol._alternate_dungeon = 4
        pol._target_dungeon_id = 4

        pol._observe(self._town(clvl=30))

        self.assertFalse(hasattr(pol, "_loadout_depth_fallback_dungeon"))
        self.assertEqual(pol._alternate_dungeon, 4)
        self.assertEqual(pol._target_dungeon_id, 4)

    def test_loadout_depth_fallback_releases_after_shallow_expedition(self):
        pol = self._policy()
        pol._alternate_dungeon = 4
        pol._target_dungeon_id = 4

        self._run_dive(pol, dungeon_id=4, level=18, clvl=30)

        self.assertFalse(hasattr(pol, "_loadout_depth_fallback_dungeon"))

    def test_stays_switched_while_still_under_levelled(self):
        pol = self._policy()
        pol._alternate_dungeon = 14
        pol._observe(self._town(clvl=29))  # one short of Angband's level
        self.assertEqual(pol._alternate_dungeon, 14)
        self.assertEqual(pol._target_dungeon_id, 14)

    # --- recall wiring ----------------------------------------------------
    def test_recall_targets_the_alternate_dungeon(self):
        inv = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=25),
            item("t", TVAL_SCROLL, 9, count=25),  # 10F+ kit wants a deep teleport stock
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            item("c", TVAL_POTION, 36, count=10),
            item("s", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=20),  # 25F run needs it
        ]
        snap = Snapshot(
            player(
                10, 10, hp=255, max_hp=255, level=23, gold=2000,
                class_id=PLAYER_CLASS_WARRIOR, abilities=self.MOUNTAIN_SAFE,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            width=198,
            height=66,
            town_flag=True,
            inventory=inv,
            equipment=[item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)],
            recall_dungeon_id=14,
            recall_depth=25,
            entered_dungeon_ids=self.ALL_ENTERED,
            angband_recall_unlocked=True,
        )
        pol = self._policy()
        pol._deepest_level = 25
        pol._alternate_dungeon = 14
        pol._target_dungeon_id = 14
        pol._char_dump_done_this_visit = True  # past the pre-dive dump
        # Mountain is index 5 in ALL_ENTERED -> selection letter 'f'.
        self.assertEqual(pol._town_special_key(snap), "rrf")
        self.assertEqual(pol.last_reason, "town:recall-to-alt-dungeon")

    def test_alternate_dungeon_recall_keeps_dungeon_reserve_after_use(self):
        snap = self._town(clvl=23)
        snap = replace(
            snap,
            recall_dungeon_id=14,
            recall_depth=25,
            entered_dungeon_ids=self.ALL_ENTERED,
        )
        pol = self._policy()
        pol._deepest_level = 25
        pol._alternate_dungeon = 14
        pol._target_dungeon_id = 14

        reserve = pol._recall_target(pol._planned_depth())
        self.assertEqual(pol._recall_required_target(snap), reserve)

    def test_alternate_dungeon_recall_never_bypasses_free_slot_requirement(self):
        inv = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=25),
            item("t", TVAL_SCROLL, 9, count=25),
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            item("c", TVAL_POTION, 36, count=9),
            item("s", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=20),
        ]
        inv.extend(
            item(chr(ord("a") + i), TVAL_STAFF, 20 + i, charges=1)
            for i in range(15)
        )
        snap = Snapshot(
            player(10, 10, hp=255, max_hp=255, level=23, gold=2000,
                   class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            width=198,
            height=66,
            town_flag=True,
            inventory=inv,
            equipment=[item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000,
                            is_equipment=True)],
            recall_dungeon_id=14,
            recall_depth=25,
            entered_dungeon_ids=self.ALL_ENTERED,
            angband_recall_unlocked=True,
        )
        pol = self._policy()
        pol._deepest_level = 25
        pol._alternate_dungeon = 14
        pol._target_dungeon_id = 14
        pol._char_dump_done_this_visit = True
        pol._shopping_stuck = True

        self.assertIsNone(pol._town_special_key(snap))
        self.assertNotEqual(pol.last_reason, "town:recall-to-alt-dungeon")


class GuardianBounceRoundTripBoundTest(unittest.TestCase):
    """DEFECT CLASS: a town<->guardian recall round trip must not repeat unboundedly.

    Absorbing-state / alternating-owner shape (live 2026-09-25, Orc cave, seven
    round trips; earlier Labyrinth, recall 9 -> 0): the return owner recalls
    out of a guardian floor the kit cannot pass (``guardian-kit-insufficient``)
    and the town owner recalls straight back to the same landing.  Neither
    owner makes floor progress, so only the over-extension valve can end it:
    every such bounce must be counted whatever role the bounced dungeon plays
    (switched alternate or latched conquest target, Angband recall unlocked or
    not), the switch must not land on another guardian floor the kit cannot
    pass, and when no entered dungeon qualifies the run must end visibly.

    Worlds.  SHALLOWER offers a productive landing below the bounced one and a
    shallower decoy guardian floor.  DEEPER_ONLY (the capture's shape) offers
    nothing below the bounced landing, a deeper decoy guardian floor and
    productive landings only deeper still: user decision 2026-09-25
    (guardian-recall-pingpong-r2, 「倒せない階でなければ深くても可」) lets a
    valve fired by guardian bounces only land deeper, as long as the landing
    is not a guardian floor the kit cannot pass.  ALL_BLOCKED lands every
    candidate on its own blocked guardian floor: user decision 2026-09-25
    (guardian-recall-pingpong-r3, 「見える形で停止する」) ends the run with the
    policy-declared final stop ``town:blocked:guardian-bounce-no-alternate``.
    Valves fired by anything else (over-extension, a mixed streak) keep the
    shallower-landing bound and the existing no-candidate behaviour.
    """

    ORC_CAVE = 3  # landing 23 == max depth 23: its guardian floor
    DECOY = 5  # a landing that is its own blocked guardian floor
    FOREST = 7  # productive unless its landing reaches 31 (max depth 32)
    MOUNTAIN = 14  # productive unless its landing reaches 49 (max depth 50)
    ENTERED = (
        DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE, ORC_CAVE, DECOY, FOREST, MOUNTAIN
    )
    SHALLOWER = {
        DUNGEON_ANGBAND: 50, DUNGEON_YEEK_CAVE: 13, ORC_CAVE: 23,
        DECOY: 18, FOREST: 20, MOUNTAIN: 27,
    }
    DEEPER_ONLY = {
        DUNGEON_ANGBAND: 50, DUNGEON_YEEK_CAVE: 13, ORC_CAVE: 23,
        DECOY: 24, FOREST: 26, MOUNTAIN: 27,
    }
    ALL_BLOCKED = {
        DUNGEON_ANGBAND: 50, DUNGEON_YEEK_CAVE: 13, ORC_CAVE: 23,
        DECOY: 24, FOREST: 31, MOUNTAIN: 49,
    }
    # Covers every band up to 49F, so each landing below is refused only for
    # its guardian, never for a missing ability.
    ABILITIES = frozenset(
        {"free_action", "resist_conf", "resist_fire", "resist_pois",
         "resist_cold", "resist_elec", "resist_acid", "resist_chaos",
         "resist_neth"}
    )
    TERMINAL = "guardian-bounce-no-alternate"
    # A drive ceiling well past the valve's own bound; reaching it is the failure.
    ROUND_TRIP_CEILING = 4 * EMPTY_DIVE_LIMIT + 1

    def _policy(self, landings):
        # No monrace knowledge: every guardian below is unbeatable for the kit.
        decoy_max = landings[self.DECOY]
        policy = HengbotPolicy(dungeon_knowledge={
            DUNGEON_ANGBAND: DungeonInfo(DUNGEON_ANGBAND, "Angband", 1, 127, 30),
            DUNGEON_YEEK_CAVE: DungeonInfo(
                DUNGEON_YEEK_CAVE, "Yeek cave", 1, 13, 1, guardian_id=237
            ),
            self.ORC_CAVE: DungeonInfo(
                self.ORC_CAVE, "Orc cave", 10, 23, 5, guardian_id=373
            ),
            self.DECOY: DungeonInfo(
                self.DECOY, "Decoy", 10, decoy_max, 5, guardian_id=900
            ),
            self.FOREST: DungeonInfo(
                self.FOREST, "Forest", 15, 32, 5, guardian_id=481
            ),
            self.MOUNTAIN: DungeonInfo(
                self.MOUNTAIN, "Mountain", 25, 50, 20, guardian_id=468
            ),
        })
        set_completed_equipment_optimization(policy)
        return policy

    def _board(self, floor_key, recall_dungeon, landings, *, angband_unlocked):
        return Snapshot(
            player(10, 10, hp=592, max_hp=592, level=33,
                   class_id=PLAYER_CLASS_WARRIOR, abilities=self.ABILITIES),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=floor_key,
            town_flag=floor_key[0] == 0,
            recall_dungeon_id=recall_dungeon,
            recall_depth=landings[recall_dungeon],
            dungeon_recall_depths=dict(landings),
            entered_dungeon_ids=self.ENTERED,
            conquered_dungeon_ids=(),
            angband_recall_unlocked=angband_unlocked,
        )

    def _town(self, policy, recall_dungeon, landings, *, angband_unlocked):
        board = self._board(
            (0, 0, 0), recall_dungeon, landings, angband_unlocked=angband_unlocked
        )
        policy._observe(board)
        return board

    def _trip(self, policy, landings, *, angband_unlocked, pickups=0,
              emergencies=0):
        """One recall round trip to the target's landing; True if bounced."""
        target = policy._target_dungeon_id
        dungeon = self._board(
            (target, landings[target], 0), target, landings,
            angband_unlocked=angband_unlocked,
        )
        policy.last_reason = "town:recall-to-alt-dungeon"
        policy._observe(dungeon)  # the recall landed: a dive begins
        for _ in range(pickups):
            policy.last_reason = "pickup"
            policy._observe(dungeon)
        for _ in range(emergencies):
            policy.last_reason = "emergency:teleport"
            policy._observe(dungeon)
        bounced = (
            policy._should_start_town_return(dungeon)
            and policy._last_return_trigger == "guardian-kit-insufficient"
        )
        policy.last_reason = "return:recall"
        self._town(policy, target, landings, angband_unlocked=angband_unlocked)
        return target, bounced

    def _drive(self, policy, landings, *, angband_unlocked, start):
        """Round trips until a dive is not bounced or the run stops visibly."""
        self._town(policy, start, landings, angband_unlocked=angband_unlocked)
        trips = []
        for _trip in range(self.ROUND_TRIP_CEILING):
            trips.append(
                self._trip(policy, landings, angband_unlocked=angband_unlocked)
            )
            if not trips[-1][1] or policy._town_blocked_reason is not None:
                return trips
        return trips

    def _assert_bounded(self, trips, *, bounced_on, productive):
        self.assertFalse(
            trips[-1][1],
            f"still bouncing after {len(trips)} round trips: {trips}",
        )
        bounced = [target for target, was in trips if was]
        self.assertLessEqual(len(bounced), EMPTY_DIVE_LIMIT, trips)
        self.assertEqual(set(bounced), {bounced_on}, trips)
        self.assertEqual(trips[-1][0], productive, trips)

    ROLES = {"alternate": "_alternate_dungeon", "conquest": "_conquest_committed"}

    @staticmethod
    def _streak(policy):
        """(streak, guardian share); getattr so pre-fix code fails by assertion."""
        return (
            policy._target_empty_dives,
            getattr(policy, "_guardian_bounce_dives", None),
        )

    def test_bounce_bound_holds_for_every_role_of_the_bounced_dungeon(self):
        worlds = {
            # (landings, the productive dungeon the valve must reach)
            "shallower": (self.SHALLOWER, self.FOREST),
            "deeper-only": (self.DEEPER_ONLY, self.FOREST),
        }
        for world, (landings, productive) in worlds.items():
            for role, attribute in self.ROLES.items():
                for angband_unlocked in (True, False):
                    with self.subTest(
                        world=world, role=role, angband_unlocked=angband_unlocked
                    ):
                        policy = self._policy(landings)
                        setattr(policy, attribute, self.ORC_CAVE)
                        trips = self._drive(
                            policy, landings,
                            angband_unlocked=angband_unlocked,
                            start=self.ORC_CAVE,
                        )
                        self.assertEqual(trips[0], (self.ORC_CAVE, True), trips)
                        self._assert_bounded(
                            trips, bounced_on=self.ORC_CAVE, productive=productive
                        )
                        self.assertIsNone(policy._conquest_committed)
                        self.assertIsNone(policy._town_blocked_reason)

    def test_no_qualifying_alternate_ends_the_run_visibly(self):
        # Round 2 bounced 13 times on the Orc cave here (the drive ceiling).
        landings = self.ALL_BLOCKED
        for role, attribute in self.ROLES.items():
            for angband_unlocked in (True, False):
                with self.subTest(role=role, angband_unlocked=angband_unlocked):
                    policy = self._policy(landings)
                    setattr(policy, attribute, self.ORC_CAVE)
                    trips = self._drive(
                        policy, landings,
                        angband_unlocked=angband_unlocked, start=self.ORC_CAVE,
                    )
                    self.assertEqual(
                        trips, [(self.ORC_CAVE, True)] * EMPTY_DIVE_LIMIT
                    )
                    self.assertEqual(policy._town_blocked_reason, self.TERMINAL)
                    town = self._board(
                        (0, 0, 0), self.ORC_CAVE, landings,
                        angband_unlocked=angband_unlocked,
                    )
                    # The town router's blocked branch names the final stop the
                    # driver ends the run on.
                    policy._town_special_key(town)
                    self.assertEqual(
                        policy.last_reason, f"town:blocked:{self.TERMINAL}"
                    )
                    self.assertIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)

    def test_restored_checkpoint_latch_keeps_the_terminal(self):
        # A checkpoint pickled before the terminal existed carries a town-block
        # latch without it; restoring adds it, so the per-decision release
        # evaluator keeps the terminal instead of clearing it before routing.
        from dataclasses import replace as replace_latch

        from hengbot.latch_onset_capture import checkpoint, restore_checkpoint

        # A bare policy: the optimizer fixture's closures do not pickle.
        policy = HengbotPolicy()
        latch = policy._cross_decision_latches["_town_blocked_reason"]
        self.assertIn(self.TERMINAL, latch.permanent_values)
        policy._cross_decision_latches["_town_blocked_reason"] = replace_latch(
            latch,
            permanent_values=tuple(
                value for value in latch.permanent_values
                if value != self.TERMINAL
            ),
        )
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        restored._town_blocked_reason = self.TERMINAL
        town = self._board(
            (0, 0, 0), self.ORC_CAVE, self.ALL_BLOCKED, angband_unlocked=True
        )
        restored._evaluate_cross_decision_latches(town)
        self.assertEqual(restored._town_blocked_reason, self.TERMINAL)

    def test_latched_alternate_whose_landing_became_a_guardian_floor(self):
        # Forest was a productive alternate; its saved recall depth has since
        # reached 31, its guardian's floor (max depth 32), and that guardian is
        # beyond the kit.  The bounces of the latched alternate are counted
        # and the guardian valve leaves Forest for the shallowest landing that
        # is not a blocked guardian floor: Mountain 27, passing over the Orc
        # cave 23 and the decoy 24, both blocked guardian floors.
        landings = {**self.DEEPER_ONLY, self.FOREST: 31}
        for angband_unlocked in (True, False):
            with self.subTest(angband_unlocked=angband_unlocked):
                policy = self._policy(landings)
                policy._alternate_dungeon = self.FOREST
                trips = self._drive(
                    policy, landings,
                    angband_unlocked=angband_unlocked, start=self.FOREST,
                )
                self._assert_bounded(
                    trips, bounced_on=self.FOREST, productive=self.MOUNTAIN
                )

    def test_restored_checkpoint_without_the_bounce_count_still_switches(self):
        # A checkpoint pickled before _guardian_bounce_dives existed, taken
        # with no streak running: its bounces are counted from zero.
        policy = self._policy(self.DEEPER_ONLY)
        policy.__dict__.pop("_guardian_bounce_dives", None)
        policy.__dict__.pop("_dive_guardian_return", None)
        policy._alternate_dungeon = self.ORC_CAVE
        trips = self._drive(
            policy, self.DEEPER_ONLY, angband_unlocked=True, start=self.ORC_CAVE
        )
        self._assert_bounded(trips, bounced_on=self.ORC_CAVE, productive=self.FOREST)

    def test_restored_checkpoint_with_a_running_streak_is_judged_mixed_once(self):
        # A checkpoint pickled mid-streak (two counted dives, no guardian
        # share recorded) cannot prove those dives were guardian bounces.  Its
        # streak is judged as ordinary over-extension once -- shallower bound,
        # nothing below 23 qualifies, no terminal, the alternate is kept --
        # and the next streak, now all guardian bounces, switches to Forest.
        policy = self._policy(self.DEEPER_ONLY)
        policy.__dict__.pop("_guardian_bounce_dives", None)
        policy._alternate_dungeon = self.ORC_CAVE
        policy._target_empty_dives = 2
        self._town(policy, self.ORC_CAVE, self.DEEPER_ONLY, angband_unlocked=True)
        first = self._trip(policy, self.DEEPER_ONLY, angband_unlocked=True)
        self.assertEqual(first, (self.ORC_CAVE, True))
        self.assertEqual(policy._last_overextended_depth, 23)
        self.assertEqual(policy._alternate_dungeon, self.ORC_CAVE)
        self.assertIsNone(policy._town_blocked_reason)
        self.assertEqual(
            self._streak(policy), (0, 0)
        )
        trips = [first]
        for _trip in range(self.ROUND_TRIP_CEILING):
            trips.append(
                self._trip(policy, self.DEEPER_ONLY, angband_unlocked=True)
            )
            if not trips[-1][1]:
                break
        self.assertEqual(
            trips,
            [(self.ORC_CAVE, True)] * (1 + EMPTY_DIVE_LIMIT)
            + [(self.FOREST, False)],
        )

    def test_mixed_streak_keeps_the_shallower_landing_bound(self):
        # One over-extended Forest dive (two emergency escapes at landing 26),
        # then Forest's landing reaches 31, its blocked guardian floor, and two
        # bounces complete the streak.  The streak is not all guardian
        # bounces, so the shallower bound applies: below 31 only the blocked
        # Orc cave (23) and decoy (24) remain, the valve finds nothing, keeps
        # Forest and does not stop the run.  A guardian-only streak would have
        # moved on to Mountain (33).
        landings = {**self.DEEPER_ONLY, self.MOUNTAIN: 33}
        policy = self._policy(landings)
        policy._alternate_dungeon = self.FOREST
        self._town(policy, self.FOREST, landings, angband_unlocked=False)
        self.assertEqual(
            self._trip(policy, landings, angband_unlocked=False, emergencies=2),
            (self.FOREST, False),
        )
        self.assertEqual(
            self._streak(policy), (1, 0)
        )
        landings = {**landings, self.FOREST: 31}
        for _bounce in range(EMPTY_DIVE_LIMIT - 1):
            self.assertEqual(
                self._trip(policy, landings, angband_unlocked=False),
                (self.FOREST, True),
            )
        self.assertEqual(policy._last_overextended_depth, 31)
        self.assertEqual(policy._alternate_dungeon, self.FOREST)
        self.assertIsNone(policy._town_blocked_reason)
        town = self._board((0, 0, 0), self.FOREST, landings, angband_unlocked=False)
        self.assertEqual(
            policy._pick_alternate_dungeon(
                town, guardian_bounced_dungeon=self.FOREST
            ),
            self.MOUNTAIN,
        )

    def test_over_extension_valve_keeps_the_shallower_landing_bound(self):
        # Three over-extended Forest dives (two emergency escapes each, no
        # guardian involved).  Only shallower landings qualify, and in this
        # world both (Orc cave 23, decoy 24) are blocked guardian floors, so
        # the valve does not jump to the deeper Mountain; the existing
        # no-candidate behaviour keeps Forest and does not stop the run.
        landings = self.DEEPER_ONLY
        policy = self._policy(landings)
        policy._alternate_dungeon = self.FOREST
        town = self._town(policy, self.FOREST, landings, angband_unlocked=False)
        for _dive in range(EMPTY_DIVE_LIMIT):
            self.assertEqual(
                self._trip(policy, landings, angband_unlocked=False, emergencies=2),
                (self.FOREST, False),
            )
        self.assertEqual(policy._last_overextended_depth, landings[self.FOREST])
        self.assertEqual(policy._target_empty_dives, 0)
        self.assertEqual(policy._alternate_dungeon, self.FOREST)
        self.assertIsNone(policy._town_blocked_reason)
        self.assertEqual(
            policy._pick_alternate_dungeon(
                town, guardian_bounced_dungeon=self.FOREST
            ),
            self.MOUNTAIN,
        )

    def test_a_stale_guardian_trigger_does_not_count_another_return(self):
        # The previous return was a guardian bounce, so _last_return_trigger
        # still reads guardian-kit-insufficient.  This Forest dive (landing 26,
        # no guardian near) returns through a path that never writes the
        # trigger (a stuck/livelock recall escape, full-pack triage, a
        # disengage recall ...): it is not a bounce and must not be counted.
        for angband_unlocked in (True, False):
            with self.subTest(angband_unlocked=angband_unlocked):
                policy = self._policy(self.DEEPER_ONLY)
                policy._alternate_dungeon = self.FOREST
                self._town(
                    policy, self.FOREST, self.DEEPER_ONLY,
                    angband_unlocked=angband_unlocked,
                )
                policy._last_return_trigger = "guardian-kit-insufficient"
                dungeon = self._board(
                    (self.FOREST, 26, 0), self.FOREST, self.DEEPER_ONLY,
                    angband_unlocked=angband_unlocked,
                )
                policy.last_reason = "town:recall-to-alt-dungeon"
                policy._observe(dungeon)
                self.assertFalse(policy._guardian_descent_blocked(dungeon))
                policy.last_reason = "stuck:recall-escape"
                self._town(
                    policy, self.FOREST, self.DEEPER_ONLY,
                    angband_unlocked=angband_unlocked,
                )
                self.assertEqual(policy._last_return_trigger, "guardian-kit-insufficient")
                self.assertEqual(
                    self._streak(policy),
                    (0, 0),
                )

    def test_a_profitable_pursued_dive_clears_the_guardian_bounces(self):
        # Two guardian bounces are on the streak; then a dive of the same
        # pursued alternate with Angband's recall unlocked hauls more than
        # OVEREXTEND_LOOT_MAX items.  Like the loot reset of the judged
        # dives, the haul clears the streak and its guardian share.
        policy = self._policy(self.DEEPER_ONLY)
        policy._alternate_dungeon = self.FOREST
        self._town(policy, self.FOREST, self.DEEPER_ONLY, angband_unlocked=True)
        policy._target_empty_dives = 2
        policy._guardian_bounce_dives = 2
        self.assertEqual(
            self._trip(
                policy, self.DEEPER_ONLY, angband_unlocked=True,
                pickups=OVEREXTEND_LOOT_MAX + 1,
            ),
            (self.FOREST, False),
        )
        self.assertEqual(
            self._streak(policy), (0, 0)
        )

    def test_guardian_valve_never_re_picks_the_bounced_dungeon(self):
        # The conquest target is not the alternate, so only the explicit
        # exclusion keeps it out: if its guardian verdict flips on the
        # arrival board (a consumable now makes the fight project as
        # viable), the Orc cave (23) would be the shallowest landing.
        policy = self._policy(self.DEEPER_ONLY)
        policy._conquest_committed = self.ORC_CAVE
        town = self._town(
            policy, self.ORC_CAVE, self.DEEPER_ONLY, angband_unlocked=True
        )
        self.assertIsNone(policy._alternate_dungeon)
        real = policy._guardian_fight_viable

        def flipped(snapshot, info):
            return info.id == self.ORC_CAVE or real(snapshot, info)

        # Declared wall: the consumable-dependent fight projection is the
        # precondition the review finding names; the picker's exclusion is the
        # subject.
        with patch.object(policy, "_guardian_fight_viable", side_effect=flipped):
            self.assertFalse(
                policy._guardian_floor_blocked(town, self.ORC_CAVE, 23)
            )
            self.assertEqual(
                policy._pick_alternate_dungeon(
                    town, guardian_bounced_dungeon=self.ORC_CAVE
                ),
                self.FOREST,
            )

    def test_depth_progress_count_still_judges_only_the_dives_it_judged(self):
        # sol review P2: four stalled Angband dives, then ONE stalled dive of a
        # latched conquest target with Angband's recall unlocked.  The depth
        # progress leash judges the Angband dives only, as it did before, so
        # the conquest dive cannot complete NO_DEPTH_PROGRESS_DIVE_LIMIT and
        # demote the conquest (a shallow Forest landing would be available).
        landings = {**self.SHALLOWER, self.ORC_CAVE: 15, self.FOREST: 12}
        policy = self._policy(landings)
        self.assertEqual(NO_DEPTH_PROGRESS_DIVE_LIMIT, 5)
        self._town(policy, DUNGEON_ANGBAND, landings, angband_unlocked=True)
        for _dive in range(NO_DEPTH_PROGRESS_DIVE_LIMIT - 1):
            self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
            self._trip(policy, landings, angband_unlocked=True)
        self.assertEqual(
            policy._no_depth_progress_dives, NO_DEPTH_PROGRESS_DIVE_LIMIT - 1
        )
        policy._conquest_committed = self.ORC_CAVE
        self._town(policy, DUNGEON_ANGBAND, landings, angband_unlocked=True)
        self.assertEqual(policy._target_dungeon_id, self.ORC_CAVE)
        self.assertEqual(
            self._trip(policy, landings, angband_unlocked=True),
            (self.ORC_CAVE, False),
        )
        self.assertEqual(
            policy._no_depth_progress_dives, NO_DEPTH_PROGRESS_DIVE_LIMIT - 1
        )
        self.assertEqual(policy._conquest_committed, self.ORC_CAVE)
        self.assertIsNone(policy._alternate_dungeon)

    def _recall_ready_town(self, landings, *, angband_unlocked):
        """A town board on which the town router reads Word of Recall.

        The supplies cover a 23F expedition (the landing every world below
        uses for the Orc cave), so the departure gate is open and the next
        departure action is the recall read itself.
        """
        inventory = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=25),
            item("t", TVAL_SCROLL, 9, count=25),
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            item("c", TVAL_POTION, 36, count=10),
            item("s", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=20),
        ]
        return replace(
            self._board(
                (0, 0, 0), self.ORC_CAVE, landings,
                angband_unlocked=angband_unlocked,
            ),
            player=player(
                10, 10, hp=592, max_hp=592, level=33, gold=2000,
                class_id=PLAYER_CLASS_WARRIOR, abilities=self.ABILITIES,
            ),
            width=198,
            height=66,
            inventory=inventory,
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)
            ],
        )

    def test_town_never_recalls_onto_a_blocked_guardian_landing(self):
        """G3 extended to the path of the 2026-09-25 06:22:31 recall.

        Live: the conquest latch (_conquest_committed) committed the Orc cave
        on a board whose kit could beat its guardian and then held it after
        the kit changed, so the town router recalled onto landing 23, the
        guardian floor, and the dive came straight back
        (guardian-kit-insufficient).  Whatever put the target there (a
        latched conquest or a latched alternate), the town router never
        chooses a recall destination whose landing is a guardian floor the
        current kit cannot pass.  It switches the way the guardian valve does
        (user decision 2026-09-25, 「倒せない階でなければ深くても可」: the
        shallowest landing that is not a blocked guardian floor, deeper
        allowed) and recalls there; with no such landing it ends the run
        visibly (「見える形で停止する」, town:blocked:guardian-bounce-no-alternate).
        """
        worlds = {
            "shallower": (self.SHALLOWER, self.FOREST),
            "deeper-only": (self.DEEPER_ONLY, self.FOREST),
            "all-blocked": (self.ALL_BLOCKED, None),
        }
        for world, (landings, productive) in worlds.items():
            for role, attribute in self.ROLES.items():
                for angband_unlocked in (True, False):
                    with self.subTest(
                        world=world, role=role, angband_unlocked=angband_unlocked
                    ):
                        policy = self._policy(landings)
                        setattr(policy, attribute, self.ORC_CAVE)
                        policy._deepest_level = landings[self.ORC_CAVE]
                        policy._char_dump_done_this_visit = True
                        board = self._recall_ready_town(
                            landings, angband_unlocked=angband_unlocked
                        )
                        policy._observe(board)
                        # The path: the latched role makes the Orc cave the
                        # target, and its landing is a blocked guardian floor.
                        self.assertEqual(policy._target_dungeon_id, self.ORC_CAVE)
                        self.assertTrue(policy._guardian_floor_blocked(
                            board, self.ORC_CAVE, landings[self.ORC_CAVE]
                        ))
                        orc_cave_recall = "rr" + policy._recall_selection_key(
                            board, self.ORC_CAVE
                        )
                        key = policy._town_special_key(board)
                        self.assertNotEqual(key, orc_cave_recall)
                        if productive is None:
                            self.assertEqual(
                                policy.last_reason,
                                f"town:blocked:{self.TERMINAL}",
                            )
                            self.assertIn(
                                policy.last_reason, POLICY_FINAL_STOP_REASONS
                            )
                            continue
                        self.assertEqual(
                            (key, policy.last_reason),
                            ("5", "town:unsafe-recall-fallback"),
                        )
                        self.assertEqual(
                            (
                                policy._alternate_dungeon,
                                policy._target_dungeon_id,
                                policy._conquest_committed,
                            ),
                            (productive, productive, None),
                        )
                        # The same board then recalls to the switched landing.
                        key = policy._town_special_key(board)
                        self.assertEqual(
                            policy.last_reason, "town:recall-to-alt-dungeon"
                        )
                        self.assertEqual(
                            key,
                            "rr" + policy._recall_selection_key(board, productive),
                        )

    def test_picker_skips_a_landing_on_a_blocked_guardian_floor(self):
        policy = self._policy(self.SHALLOWER)
        policy._last_overextended_depth = 23
        board = self._board(
            (0, 0, 0), self.ORC_CAVE, self.SHALLOWER, angband_unlocked=True
        )
        # The decoy is the shallowest landing below 23 but it is the decoy's
        # guardian floor; so is the Orc cave inside the unsafe-recall bound.
        self.assertTrue(policy._guardian_floor_blocked(board, self.DECOY, 18))
        self.assertTrue(policy._guardian_floor_blocked(board, self.ORC_CAVE, 23))
        self.assertFalse(policy._guardian_floor_blocked(board, self.FOREST, 20))
        self.assertEqual(policy._pick_alternate_dungeon(board), self.FOREST)
        self.assertEqual(
            policy._pick_alternate_dungeon(board, max_entry_depth=49),
            self.FOREST,
        )
