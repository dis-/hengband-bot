"""Owner 2026-11-08 「境に余裕を持たせる」: the threat tiers' decided side holds near a boundary.

The recorded bear pack (tests/test_choke_stall_recreate_1108_recorded.py, n1-c life-162, Orc
cave 19F, 2026-11-08 01:46): at (33, 91) thirteen hostiles in view, eight of them 闘熊, read T2
with no selected target by 3-29 HP (the free attacks' 380-386 over 21 turns against HP 376-357),
so step 6 left them (flee '9' to (32, 92)); at (32, 92) the pack hides (the hiding move decider)
and seek-loot stepped '1' back onto (33, 91): flee / seek-loot until loop-detected.  The HP also
moves the reading across the T3/T2 boundary (HP 384 reads T3 against 383).

The owner's answer: once a monster's tier is decided, small HP / estimate changes do not flip it;
fight or leave stays on the side decided first (threat_tiers.decided).  The band is the reading's
own reserve, D7 max(10% of max HP, the next-action p95): 38-48 HP on these boards.

Owner 2026-11-12 (「死なない側に置き直す」, t3-survival-1112 B): the T3 band now lies on the side
the projection survives: T3 is entered at a free margin of the reserve, a first reading too, and
left once the margin is below 0; the T2/T1 band is unchanged.  The tests below that crossed the
T3 boundary inside the old band are re-driven to that rule (named at each).

The boards are the recorded ones, fed in order through the public ``choose_key``, every key
posted by the production executor (``_ExecutorInputPort``).  DECLARED CONSTRUCTED: the boards
whose player HP / max HP or a monster's haste this module changes (named at each test), and the
next board after each posted key (the executor's command screen).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from dataclasses import replace
import unittest

from hengbot import latch_onset_capture, policy_state, retreat_veto_life, threat_tiers
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position, parse_snapshot
from hengbot.policy import ConservativePolicy
from hengbot.threat_tiers import T1, T2, T3, Assessment, held_tier
import test_choke_stall_recreate_1108_recorded as choke
from tests.support import recorded as executor_pins


OPEN_CELL, CHOKE = choke.OPEN_CELL, choke.CHOKE
LEAVING = ("flee", "emergency:")
RECORDED_ROWS = 12  # decisions 508-519: five flee / seek-loot laps
# The game's prompts of the two-key commands decided here (quaff, read, rest).
PROMPTS = {"q": "どの薬を飲みますか? ", "r": "どの巻物を読みますか? ",
           "R": "休憩 (0-9999, '*' で HP/MP全快, '&' で必要なだけ): &"}


def leaves(reason: str) -> bool:
    return reason.startswith(LEAVING)


def with_player(row, **player) -> dict:
    """DECLARED CONSTRUCTED: the recorded board with the player's fields changed."""
    raw = copy.deepcopy(row["board"])
    raw["player"].update(player)
    return raw


def stepped_onto(snapshot, key) -> Position | None:
    move = choke.DIRECTIONS.get(key)
    if move is None:
        return None
    here = snapshot.player.position
    return Position(here.y + move[0], here.x + move[1])


class BearPackHoldRecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        choke.ChokeStallRecreateRecorded.setUpClass.__func__(cls)

    policy = choke.ChokeStallRecreateRecorded.__dict__["policy"]

    def decide(self, policy, raw):
        snapshot = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), self.monrace))
        key = policy.choose_key(snapshot)
        self.post(policy, raw, snapshot, key)
        return snapshot, key, policy.last_reason

    def post(self, policy, raw, snapshot, key):
        """The production executor posts the decided key (the command's prompt, then the next
        board: a command screen)."""
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        prompts = ([executor_pins.prompt_screen(PROMPTS[key[0]])]
                   if len(key) > 1 and key[0] in PROMPTS else [])
        game.screens = [*prompts, executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(copy.deepcopy(raw), turn=raw["turn"] + 10) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=snapshot, posting_contract=PostingContract())
        self.assertTrue(sent, (key, port.last_result.stop_line))
        policy.confirm_key_posted(key)

    def tier(self, policy, snapshot):
        return threat_tiers.tiered(policy, snapshot, policy._strategic_hostiles(snapshot))

    def memory(self, policy):
        return getattr(policy, threat_tiers.TIER_MEMORY).decided

    # ------------------------------------------------------------ the recorded laps

    def test_the_left_pack_is_not_walked_back_to(self):
        policy = self.policy()
        rows = self.rows[:RECORDED_ROWS]
        # Recorded: every board at (32, 92) after a step away stepped '1' back (seek-loot).
        self.assertEqual({row["decision"]["key"] for row in rows[2:10:2]}, {"1"})
        left = False
        for row in rows:
            with self.subTest(sequence=row["decision"]["decision_sequence"]):
                snapshot, key, reason = self.decide(policy, row["board"])
                if snapshot.player.position == OPEN_CELL:
                    self.assertTrue(leaves(reason), (key, reason))
                    self.assertEqual(self.tier(policy, snapshot).tier, T2)
                    if not left:  # the decision row's telemetry names the decided sides
                        sides = threat_tiers.facts(policy, snapshot)["decided"]
                        self.assertEqual((len(sides), {side["leave"] for side in sides}),
                                         (13, {True}))
                    left = True
                    continue
                self.assertFalse(snapshot.visible_monsters)
                if left:
                    self.assertNotEqual(reason, "seek-loot", key)
                    self.assertNotEqual(stepped_onto(snapshot, key), OPEN_CELL, reason)
                    # Out of sight the pack keeps its decided side, and the fled cell its veto.
                    self.assertEqual({entry.leave for entry in self.memory(policy).values()},
                                     {True})
                    self.assertEqual(len(self.memory(policy)), 13)
                    self.assertIn(OPEN_CELL, policy._engagement_avoid_cells)
        self.assertTrue(left)

    # ------------------------------------------------------------ the leave side near T3

    def test_a_small_rise_across_t3_keeps_the_leave(self):
        """DECLARED CONSTRUCTED: decision 511's board at HP = max HP 400 (the free attacks' 383:
        T3 by 17, inside the band max(40, 36))."""
        rise = with_player(self.rows[3], hp=400, max_hp=400)
        policy = self.policy()
        snapshot, key, reason = self.decide(policy, self.rows[1]["board"])
        self.assertTrue(leaves(reason), reason)
        snapshot, key, reason = self.decide(policy, rise)
        result = self.tier(policy, snapshot)
        self.assertEqual((result.tier, result.raw_tier, result.free_margin, result.reserve),
                         (T2, T3, 17, 40))
        self.assertTrue(leaves(reason), (key, reason))
        # The held T2 spends nothing: the free attacks win (no Speed, no resistance drunk).
        self.assertEqual((result.supply_plan.categories, result.supply_plan.speed_doses,
                          result.supply_plan.resistance), ((), 0, 0))
        # Read first, the same board is not entered as T3 either (B: T3 by 17, below the reserve
        # 40) and is left.
        fresh = self.policy()
        snapshot, key, reason = self.decide(fresh, rise)
        self.assertEqual((self.tier(fresh, snapshot).tier, self.tier(fresh, snapshot).raw_tier),
                         (T2, T3))
        self.assertTrue(leaves(reason), (key, reason))

    def test_a_decisive_rise_turns_the_pack_to_fight(self):
        """DECLARED CONSTRUCTED: decision 511's board at HP = max HP 440 (T3 by 57, past the band
        max(44, 36)): the decided leave turns to fight and the fled cell's veto is lifted."""
        policy = self.policy()
        self.decide(policy, self.rows[1]["board"])
        self.assertIn(OPEN_CELL, policy._engagement_avoid_cells)
        snapshot, key, reason = self.decide(policy, with_player(self.rows[3], hp=440, max_hp=440))
        result = self.tier(policy, snapshot)
        self.assertEqual((result.tier, result.raw_tier, result.free_margin), (T3, None, 57))
        self.assertFalse(leaves(reason), (key, reason))
        self.assertEqual({entry.leave for entry in self.memory(policy).values()}, {False})
        self.assertNotIn(OPEN_CELL, policy._engagement_avoid_cells)

    # ------------------------------------------------------------ the fight side near T2

    def test_the_fight_side_holds_through_a_small_drop_and_turns_on_a_decisive_one(self):
        """DECLARED CONSTRUCTED: max HP 430.  Decision 509's board at HP 430 reads T3 (the free
        attacks' 380); decision 511's at HP 380 reads T2 by 3: B leaves a held T3 once the margin
        is below 0 (it was held T3 and fought before 2026-11-12); decision 513's at HP 330 reads
        T2 by 56: left."""
        policy = self.policy()
        snapshot, key, reason = self.decide(policy, with_player(self.rows[1], hp=430, max_hp=430))
        self.assertEqual(self.tier(policy, snapshot).tier, T3)
        self.assertFalse(leaves(reason), (key, reason))
        snapshot, key, reason = self.decide(policy, with_player(self.rows[3], hp=380, max_hp=430))
        result = self.tier(policy, snapshot)
        self.assertEqual((result.tier, result.raw_tier, result.free_margin), (T2, None, -3))
        self.assertTrue(leaves(reason), (key, reason))
        snapshot, key, reason = self.decide(policy, with_player(self.rows[5], hp=330, max_hp=430))
        result = self.tier(policy, snapshot)
        self.assertEqual((result.tier, result.raw_tier, result.free_margin, result.reserve),
                         (T2, None, -56, 43))
        self.assertTrue(leaves(reason), (key, reason))

    def test_a_hasted_pack_member_is_read_as_it_is(self):
        """DECLARED CONSTRUCTED: max HP 430; decision 509's board at HP 430 decides T3, then
        decision 511's at HP 425 with one bear hasted (fast) reads T2 by 24, inside the band
        max(43, 43): a stronger engagement, not an estimate's drift, so it is taken as read."""
        policy = self.policy()
        self.decide(policy, with_player(self.rows[1], hp=430, max_hp=430))
        raw = with_player(self.rows[3], hp=425, max_hp=430)
        bear = next(monster for monster in raw["visible_monsters"]
                    if monster["race_id"] == choke.BEAR)
        bear["fast"] = True
        snapshot, key, reason = self.decide(policy, raw)
        result = self.tier(policy, snapshot)
        self.assertEqual((result.tier, result.raw_tier, result.free_margin, result.reserve),
                         (T2, None, -24, 43))
        self.assertTrue(leaves(reason), (key, reason))

    def test_instant_death_is_taken_as_read(self):
        """The 1-turn 即死 overrides the hold: a T1 reading inside the band of a decided T2 is
        taken when it is also 即死 (re-driven to the T2/T1 band, which B leaves as it was: the
        reading constructed from decision 511's at HP 380, T2 by 3, read T1 by 3 of supply
        margin)."""
        policy = self.policy()
        self.decide(policy, with_player(self.rows[1], hp=430, max_hp=430))
        snapshot = policy.with_known_skill_exp(
            parse_snapshot(with_player(self.rows[3], hp=380, max_hp=430), self.monrace))
        hostiles = policy._strategic_hostiles(snapshot)
        raw = threat_tiers.assess(policy, snapshot, hostiles)
        self.assertEqual((raw.tier, raw.free_margin), (T2, -3))
        self.assertEqual(threat_tiers.decided(policy, snapshot, hostiles, raw).tier, T2)
        weaker = replace(raw, tier=T1, supply_margin=-3, supply_plan=None)
        self.assertEqual(threat_tiers.decided(policy, snapshot, hostiles, weaker).tier, T2)
        lethal = replace(weaker, instant_death=True)
        self.assertEqual(threat_tiers.decided(policy, snapshot, hostiles, lethal).tier, T1)
        self.assertEqual({entry.tier for entry in self.memory(policy).values()}, {T1})

    # ------------------------------------------------------------ the pack out of sight

    def three_bears(self, row, turns=10):
        """DECLARED CONSTRUCTED: decision 511's board with three of the eight bears in view and
        the other ten hostiles out of sight, ``turns`` game turns after decision 509."""
        raw = copy.deepcopy(row["board"])
        bears = [monster for monster in raw["visible_monsters"]
                 if monster["race_id"] == choke.BEAR][:3]
        raw["visible_monsters"] = bears
        raw["turn"] = self.rows[1]["board"]["turn"] + turns
        return raw

    def test_the_visible_part_of_a_left_pack_is_not_fought_alone(self):
        policy = self.policy()
        self.decide(policy, self.rows[1]["board"])
        snapshot, key, reason = self.decide(policy, self.three_bears(self.rows[3]))
        result = self.tier(policy, snapshot)
        self.assertEqual((result.tier, result.raw_tier), (T2, T3))
        self.assertGreaterEqual(result.free_margin, result.reserve)  # decisive, were it alone
        self.assertTrue(leaves(reason), (key, reason))

    def test_pack_mates_unseen_for_the_veto_window_are_forgotten(self):
        """retreat_veto_life.UNSEEN_GAME_TURNS (the hunt's 1,000 game turns) after decision 509
        the ten not shown since are forgotten: the three bears in view are read as they are."""
        policy = self.policy()
        self.decide(policy, self.rows[1]["board"])
        later = self.three_bears(self.rows[3], turns=retreat_veto_life.UNSEEN_GAME_TURNS)
        snapshot, key, reason = self.decide(policy, later)
        result = self.tier(policy, snapshot)
        self.assertEqual((result.tier, result.raw_tier), (T3, None))
        self.assertEqual(len(self.memory(policy)), 3)
        self.assertFalse(leaves(reason), (key, reason))

    def test_a_new_floor_visit_forgets_the_decided_sides(self):
        """DECLARED CONSTRUCTED: the boards of another level observed in between (a new level
        reuses the floor key and the monster indices): back on 19F the rise is read afresh."""
        policy = self.policy()
        self.decide(policy, self.rows[1]["board"])
        elsewhere = copy.deepcopy(self.rows[2]["board"])
        elsewhere["floor"]["level"] += 1
        policy.prime(parse_snapshot(elsewhere, self.monrace))
        policy.prime(parse_snapshot(copy.deepcopy(self.rows[2]["board"]), self.monrace))
        self.assertIsNone(getattr(policy, threat_tiers.TIER_MEMORY))
        # HP 440 (T3 by 57, past the reserve 44): a fresh reading enters T3 (B; at HP 400 a
        # fresh reading, T3 by 17, is no longer entered).
        snapshot, key, reason = self.decide(policy, with_player(self.rows[3], hp=440, max_hp=440))
        self.assertEqual(self.tier(policy, snapshot).tier, T3)
        self.assertFalse(leaves(reason), (key, reason))

    # ------------------------------------------------------------ checkpoints

    def test_a_restored_checkpoint_keeps_the_decided_side(self):
        """The memory is policy state: a checkpoint taken after the decided leave restores it,
        and the small rise of ``test_a_small_rise_across_t3_keeps_the_leave`` is still left.
        A checkpoint from before the memory decides afresh."""
        rise = with_player(self.rows[3], hp=400, max_hp=400)
        policy = self.policy()
        self.decide(policy, self.rows[1]["board"])
        payload = latch_onset_capture.checkpoint_bytes(policy)
        restored = latch_onset_capture.restore_checkpoint_bytes(ConservativePolicy, payload)
        self.assertEqual(self.memory(restored), self.memory(policy))
        snapshot, key, reason = self.decide(restored, rise)
        self.assertTrue(leaves(reason), (key, reason))
        older = latch_onset_capture.restore_checkpoint_bytes(ConservativePolicy, payload)
        del older.__dict__[threat_tiers.TIER_MEMORY]
        policy_state.normalize_policy_state(older, restart=True)
        self.assertIsNone(getattr(older, threat_tiers.TIER_MEMORY))
        # Afresh at HP 440 (B: a fresh T3 needs the reserve; at 400 it is not entered either).
        snapshot, key, reason = self.decide(older, with_player(self.rows[3], hp=440, max_hp=440))
        self.assertFalse(leaves(reason), (key, reason))


class HeldTierTest(unittest.TestCase):
    """The boundary rule alone (constructed readings; the band is the reading's reserve, 40)."""

    @staticmethod
    def reading(tier, free_margin=None, supply_margin=None):
        return Assessment(tier=tier, reserve=40, free_margin=free_margin,
                          supply_margin=supply_margin)

    def held(self, held, raw, worse_as_read=False, mates_in_view=True):
        return held_tier(held, raw, worse_as_read=worse_as_read, mates_in_view=mates_in_view)

    def test_t2_to_t3_needs_the_band(self):
        self.assertEqual(self.held(T2, self.reading(T3, 39, -1)), T2)
        self.assertEqual(self.held(T2, self.reading(T3, 40, 0)), T3)

    def test_an_absent_pack_mate_keeps_the_worse_side(self):
        self.assertEqual(self.held(T2, self.reading(T3, 400, 360), mates_in_view=False), T2)

    def test_t3_is_left_below_zero(self):
        """B: a held T3 is left once the free margin is below 0 (inside [0, reserve) it holds)."""
        self.assertEqual(self.held(T3, self.reading(T2, -1, 100)), T2)
        self.assertEqual(self.held(T3, self.reading(T3, 0, -40)), T3)
        self.assertEqual(self.held(T3, self.reading(T3, 39, -1)), T3)
        self.assertEqual(self.held(T3, self.reading(T2, None, 100)), T2)  # no free attack left

    def test_a_stronger_engagement_is_read_as_it_is(self):
        self.assertEqual(self.held(T3, self.reading(T2, -1, 100), worse_as_read=True), T2)

    def test_t2_to_t1_needs_the_band(self):
        self.assertEqual(self.held(T2, self.reading(T1, -500, -39)), T2)
        self.assertEqual(self.held(T2, self.reading(T1, -500, -40)), T1)
        self.assertEqual(self.held(T2, self.reading(T1, None, None)), T1)  # nothing clears it

    def test_t1_to_t3_crosses_both_boundaries(self):
        # A T3 reading's supply margin is its free margin less the reserve (the free win as a
        # plan): out of T1 it needs twice the band.
        self.assertEqual(self.held(T1, self.reading(T3, 79, 79 - 40)), T1)
        self.assertEqual(self.held(T1, self.reading(T3, 80, 80 - 40)), T3)
        self.assertEqual(self.held(T1, self.reading(T2, -500, 40)), T2)

    def test_t3_to_t1_crosses_both_boundaries(self):
        # B leaves T3 below 0; the T2/T1 band is the supply margin's, unchanged.
        self.assertEqual(self.held(T3, self.reading(T1, -1, -39)), T2)
        self.assertEqual(self.held(T3, self.reading(T1, -1, -40)), T1)


if __name__ == "__main__":
    unittest.main()
