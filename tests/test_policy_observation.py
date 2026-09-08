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
        pol._last_return_trigger = trigger
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
            dungeon_recall_depths={3: 23, 4: 18, 7: 21, 14: 25},
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
