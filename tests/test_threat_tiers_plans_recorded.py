"""Threat tiers plan step 4 (docs/threat-tiers-design.md 2.5, 3.1, 5): 即死 inside the quest plans.

Owner 2026-11-07, answer 11: 「作戦が先・即死だけ例外」; OQ-2: 「作戦中と物資を使って倒しに行くときは
次の1手のみ」.  Inside a plan of dungeon_ladder.FLOOR_PLANS the plan's own order goes first, and the
one label that pre-empts it is the 1-turn 即死: the next player action's p95 damage (each monster at
``speed + 10*fast - 10*slow``) plus the observed unseen loss reaches the HP.  The new SURVIVAL rung
``threat_tiers.instant_death_key`` heads every board with an enemy.  Its answer (owner 2026-11-07
「作戦の逃げ方を使う」: 「即死の危険の時は、その作戦が決めている逃げ方（Q25 なら作戦の HP の線の
テレポートなど）を先に使う。作戦に逃げ方が無ければ緊急の逃げ方。」) is the plan's own escape rung
asked without its HP line (Q25 and the room sweep: ``quest_room_sweep._below_line``, Teleportation
or, after one that left an enemy on the player, a potion; quest_find_exit: ``_below_line_recall``);
the escape the emergency ladder chooses when ``lethal`` holds only when the plan has none left.

Recorded: n1-b life-312's death in Quest 25 (tests/fixtures/q25-summons-n1b-312-1105.json.gz, the
revised plan ``quest25_battle`` answers there today).  One policy decides the boards in order with
the rung off (the recording's trajectory); on every board where the rung's own test fired inside
that decision, a copy of the policy decides with the rung on (``decided_with_and_without``).  The
diff of decided keys over the floor is limited to those boards.
DECLARED CONSTRUCTED where a test edits a board or forces the test (the Q18 wiring), as it says.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle
from hengbot import quest25_battle, quest_find_exit, quest_room_sweep, threat_tiers
from hengbot.cli import _PolicyObserverScope
from hengbot.model import parse_snapshot
from tests import test_plan_floor_summons_1105_recorded as summons
from tests import test_q18_water_cave as q18
from tests import test_q25_haunted_house as q25

OFF = threat_tiers.InstantDeath()
EMERGENCY_TELEPORT = "emergency:teleport"
PLAN_TELEPORT = quest_room_sweep.TELEPORT_REASON

# The recorded boards the 1-turn test fires on, and what answered there before the rung.
# (turn, HP, the plan's recorded answer)
FIRED = {
    11652725: (1003, "summons:leave-teleport"),
    11652731: (940, "summons:leave-teleport"),
    11652737: (378, "quest-strategy:sweep-teleport"),
    11653273: (939, "quest-strategy:melee"),
    11653279: (939, "summoner:ranged-kill:named-caster"),
    11653286: (742, "summoner:ranged-kill:named-caster"),
    11653293: (570, "summoner:ranged-kill:named-caster"),
    11653298: (570, "quest-strategy:melee"),
    11653307: (577, "quest-strategy:melee"),
    11653315: (570, "quest-strategy:melee"),
    11653325: (369, "quest-strategy:sweep-teleport"),
    11653357: (60, "quest-strategy:sweep-teleport"),
    11653399: (108, "quest-strategy:sweep-teleport"),
}


def decide(policy, raw):
    board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    return board, str(policy.choose_key(board)), policy.last_reason


def decided_with_and_without(new_policy, raws, fires=lambda death: death.holds):
    """turn -> (without, with, the InstantDeath read) on every board whose decision asked the test
    and got it holding.  Pass 1 decides with the test answering "no" and notes where its real value
    held; pass 2 copies the policy before those boards and decides the copy with the test on."""
    real = threat_tiers.instant_death
    fired = {}

    def noting(policy, snapshot, hostiles=None):
        death = real(policy, snapshot, hostiles)
        if fires(death):
            fired.setdefault(snapshot.turn, death)
        return OFF

    with patch.object(threat_tiers, "instant_death", noting):
        policy = new_policy()
        for raw in raws:
            _board, key, _reason = decide(policy, raw)
            policy.confirm_key_posted(key)
    answers = {}
    with patch.object(threat_tiers, "instant_death", lambda *args, **kwargs: OFF):
        policy = new_policy()
    for raw in raws:
        twin = copy.deepcopy(policy) if raw["turn"] in fired else None
        with patch.object(threat_tiers, "instant_death", lambda *args, **kwargs: OFF):
            _board, key, reason = decide(policy, raw)
        if twin is not None:
            _board, twin_key, twin_reason = decide(twin, raw)
            answers[raw["turn"]] = ((key, reason), (twin_key, twin_reason), fired[raw["turn"]])
        policy.confirm_key_posted(key)
    return answers


ANSWERS = {}


def q25_answers():
    if not ANSWERS:
        ANSWERS.update(decided_with_and_without(summons._new_policy, summons.CASE["boards"]))
    return ANSWERS


class Q25RecordedTest(unittest.TestCase):
    def test_only_the_boards_the_one_turn_test_fires_on_change(self):
        answers = q25_answers()
        self.assertEqual(set(answers), set(FIRED))
        for turn, (before, after, death) in answers.items():
            with self.subTest(turn=turn):
                hp, recorded_reason = FIRED[turn]
                self.assertEqual(before[1], recorded_reason)
                self.assertGreaterEqual(death.next_action_p95 + death.unseen_correction, hp)
                # The plan's own escape answers: its below-line Teleportation, at any HP.
                self.assertEqual(after[1], PLAN_TELEPORT)
                self.assertTrue(after[0].startswith("r"), after)
        # Where the plan read that Teleportation already, nothing changes.
        unchanged = {turn for turn, (before, after, _death) in answers.items() if before == after}
        self.assertEqual(unchanged, {turn for turn, (_hp, reason) in FIRED.items()
                                     if reason == PLAN_TELEPORT})

    def test_the_plan_acts_where_the_test_does_not_fire(self):
        # 11653273: 撲殺の悪魔 in front of the nearest レッサー・バルログ, the plan's blow recorded.
        real, read = threat_tiers.instant_death, []

        def spy(*args, **kwargs):
            read.append(real(*args, **kwargs))
            return read[-1]
        with patch.object(threat_tiers, "instant_death", spy):
            policy, raw, key = summons.replay_until(summons.CASTER_BEHIND_A_BODY)
        death = read[-1]  # the read of the rung inside that board's decision
        self.assertTrue(death.next_action)
        self.assertGreaterEqual(death.next_action_p95, raw["player"]["hp"])  # the p95 alone
        self.assertEqual(policy.last_reason, PLAN_TELEPORT)
        # DECLARED CONSTRUCTED: the same replay with the next-action test not holding on it.
        with summons.below_instant_death():
            policy, raw, key = summons.replay_until(summons.CASTER_BEHIND_A_BODY)
        self.assertEqual(policy.last_reason, quest_find_exit.MELEE_REASON)

    def test_the_q25_plan_answers_and_its_rung_heads_the_enemy_branch(self):
        calls = []
        real = threat_tiers.instant_death_key

        def spy(policy, snapshot, *rest):
            answer = real(policy, snapshot, *rest)
            calls.append((snapshot.turn, answer, policy.last_reason))
            return answer
        plan_answers = []
        real_plan = quest25_battle.key

        def plan_spy(policy, snapshot):
            answer = real_plan(policy, snapshot)
            plan_answers.append((snapshot.turn, answer))
            return answer
        with patch.object(threat_tiers, "instant_death_key", spy), \
                patch.object(quest25_battle, "key", plan_spy):
            policy, raw, key = summons.replay_until(summons.CASTER_BESIDE)
        # The revised Q25 plan answered the board, through its rung, with the escape.
        self.assertEqual(plan_answers[-1], (summons.CASTER_BESIDE, key))
        self.assertEqual(calls[-1], (summons.CASTER_BESIDE, key, PLAN_TELEPORT))

    def test_the_escape_is_sent(self):
        policy, raw, key = summons.replay_until(summons.CASTER_BESIDE)
        self.assertEqual(policy.last_reason, PLAN_TELEPORT)
        slot = next(item["slot"] for item in raw["inventory"]
                    if item["tval"] == q25.TVAL_SCROLL and item["sval"] == q25.SV_TELEPORT)
        self.assertEqual(key, "r" + slot)
        sender = summons.Q25RecordedTest("test_the_first_cast_from_the_dark_reads_the_light")
        self.addCleanup(sender.doCleanups)
        sender.post(SimpleNamespace(last_reason=policy.last_reason,
                                    _decision_sequence=policy._decision_sequence), raw, key,
                    screens=[summons.prompt_screen(text)
                             for command, text in summons.COMMAND_PROMPTS.items()
                             if key.startswith(command)])


class QuestFindExitWiringTest(unittest.TestCase):
    """DECLARED CONSTRUCTED: q18's choke with a squid beside the player (quest_find_exit's
    "an enemy for the line" board).  The squid's next-action p95 (90) is far below the HP, so the
    plan's blow answers; with the test forced to hold, the rung answers with the plan's own escape
    (its below-line Recall, at any HP), and with no Recall to read with the emergency ladder."""

    CHOKE = (1, 3)

    def board(self):
        return q18.board(self.CHOKE, monsters=[q18.monster(q18.SQUID, 1, 4)], speed=0)

    def test_the_plans_blow_without_the_test(self):
        key, reason, policy = q18.decide(self.board())
        self.assertEqual((key, reason), (q18.step_key(self.CHOKE, (1, 4)), quest_find_exit.MELEE_REASON))
        board = parse_snapshot(copy.deepcopy(self.board()), policy._monrace_knowledge)
        with _PolicyObserverScope(policy):
            self.assertFalse(threat_tiers.instant_death(policy, board).next_action)

    def test_the_rung_answers_when_the_test_holds(self):
        forced = threat_tiers.InstantDeath((threat_tiers.NEXT_ACTION_P95,), 900, 0)
        asked = []

        def recall(policy, snapshot, reason):
            asked.append(snapshot.player.hp_ratio)
            policy.last_reason = reason
            return "r-recall"
        # The plan's Recall read stubbed: on this one-time floor once_quest_recall holds it while
        # Teleportation is carried, and the rung then falls to the emergency ladder (below).
        with patch.object(threat_tiers, "instant_death", lambda *args, **kwargs: forced), \
                patch.object(quest_find_exit.once_quest_recall, "read_key", recall):
            key, reason, _policy = q18.decide(self.board())
        self.assertEqual((key, reason), ("r-recall", quest_find_exit.RECALL_REASON))
        self.assertEqual(asked, [1.0])  # at full HP, over the plan's line

    def test_with_no_plan_escape_left_the_emergency_ladder_answers(self):
        forced = threat_tiers.InstantDeath((threat_tiers.NEXT_ACTION_P95,), 900, 0)
        with patch.object(threat_tiers, "instant_death", lambda *args, **kwargs: forced), \
                patch.object(quest_find_exit.once_quest_recall, "read_key", lambda *args: None):
            key, reason, _policy = q18.decide(self.board())
        self.assertTrue(reason.startswith("emergency:"), (key, reason))
        self.assertNotEqual(reason, quest_find_exit.MELEE_REASON)

    def test_the_paralyser_and_hallucination_labels_answer_too(self):
        # Design 3.1 defines both as 即死; the HP model cannot see them (forced here).
        for label in ("paralyzer-contact", "hallucination"):
            with self.subTest(label=label):
                forced = threat_tiers.InstantDeath((label,), 0, 0)
                with patch.object(threat_tiers, "instant_death", lambda *args, **kwargs: forced):
                    key, reason, _policy = q18.decide(self.board())
                self.assertNotEqual(reason, quest_find_exit.MELEE_REASON, (key, reason))


class EmergencyEscapeTest(unittest.TestCase):
    """The rung's answer is the emergency ladder's escape: a supplied unique fight is no answer to
    即死 (design 3.4 「only the 1-turn 即死 does」 abort it).  DECLARED CONSTRUCTED: the drink of
    ``_unique_combat_consumable`` is stubbed on q18's choke board."""

    def test_no_supplied_unique_fight_is_drunk_for_first(self):
        raw = q18.board(QuestFindExitWiringTest.CHOKE, monsters=[q18.monster(q18.SQUID, 1, 4)],
                        speed=0)
        policy = q18.new_policy(raw)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        hostiles = threat_tiers.engagement(policy, board)
        with patch.object(ConservativePolicy, "_unique_combat_consumable",
                          lambda self, snapshot, hostiles: "q-unique"):
            self.assertEqual(policy._emergency_item(board, hostiles), "q-unique")
            answer = policy._emergency_item(board, hostiles, instant_death=True)
        self.assertNotEqual(answer, "q-unique")
        self.assertTrue(policy.last_reason.startswith("emergency:"), policy.last_reason)


class RungTest(unittest.TestCase):
    def test_no_hostile_no_answer(self):
        policy = q18.new_policy()
        raw = q18.board(QuestFindExitWiringTest.CHOKE, monsters=[], speed=0)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(threat_tiers.instant_death(policy, board), OFF)
        self.assertIsNone(threat_tiers.instant_death_key(policy, board))


if __name__ == "__main__":
    unittest.main()
