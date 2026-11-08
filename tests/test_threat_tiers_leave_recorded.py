"""Threat tiers plan step 6 on recorded boards: leave at T1 and at an unselected T2.

Owner 2026-11-07, answer 6 (「倒しきれない -> don't fight, leave」) and answer 4 (only selected
targets are fought with supplies).  Acceptance (design step 6, and the caller's: no escape turned
into a stay): the recorded death lives of n1-a 450/466/470/474/475, n1-b 299/306/325, n1-c
077/084/085/099/103/123, n1-a 475's summons and n1-c's D57 lives (d57-me-combat-083/084,
d57-n1c-079/083) were replayed with the step off (the recorded trajectory) and, on every board, a
copy of the policy decided with it on (``decided_with_and_without``).  Every board whose decision
changed is pinned below; on each the change is toward leaving:

- n1-a life-475 (Lv~40 warrior, undead and summoners, HP 853 -> 652 of 970): nine melee boards are
  T1 (not even every supply wins) and now read the flee rung's Teleportation (``flee:scroll``).
- n1-c life-084 (HP 151 -> 136 of 151, ジャイアント・サラマンダー, faster than the player): T1; three
  absorbed Magic Missile boards read the flee rung's Teleportation (a faster monster is not walked
  from, design 3.2).
- n1-c life-083: the beetle board (HP 118/171, T1 with nothing absorbed shown, the beetle faster)
  reads Teleportation instead of firing; three boards beside three ogres and a king cobra (T1)
  leave by the flee rung (walk where none is faster, Teleportation) instead of firing; on 1186736
  (HP 71/171) the flee rung's walk now answers before the return rung's Word of Recall read (both
  leave; noted in the report).

The 11-05 Resistance-potion boards (Quest 25, moved to a plain floor as test_resist_potion_1105_
recorded does, DECLARED CONSTRUCTED) are in that module.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle
from hengbot import threat_tiers
from hengbot.cli import _PolicyObserverScope
from hengbot.model import parse_snapshot
from tests import test_threat_tiers_recorded as recorded


def decide(policy, raw):
    board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    return str(policy.choose_key(board)), policy.last_reason


def decided_with_and_without(name, off, turns=None):
    """turn -> ((key, reason) with the step off, (key, reason) with it on) on every board whose
    decision differs (or on ``turns`` only); the trajectory is the step-off one.  ``off`` is a list
    of (object, attribute, value) patches that switch the step off."""
    case = recorded.CASES.get(name) or recorded.load(name)
    raws = recorded.boards(case)
    policy = recorded.d57.loops.new_policy(dict(case, boards=raws), case["skill"],
                                           monraces=case.get("monraces"))

    def patches():
        return [patch.object(obj, attribute, value) for obj, attribute, value in off]
    changed = {}
    for raw in raws:
        twin = copy.deepcopy(policy) if turns is None or raw["turn"] in turns else None
        stack = patches()
        for each in stack:
            each.start()
        try:
            before = decide(policy, raw)
        finally:
            for each in stack:
                each.stop()
        if twin is not None:
            after = decide(twin, raw)
            if after != before:
                changed[raw["turn"]] = (before, after)
        policy.confirm_key_posted(before[0])
    return changed


OFF = [(threat_tiers, "leave_due", lambda *args, **kwargs: None)]
MISSILE = "quest-strategy:ranged-fire:magic-eater"
N1A_475 = (2038954, 2038961, 2038970, 2038974, 2038982, 2038988, 2038996, 2039000, 2039009)


class LeaveRecordedTest(unittest.TestCase):
    def test_n1a_475_t1_melee_becomes_the_flee_teleport(self):
        changed = decided_with_and_without("death-n1a-475-1104.json.gz", OFF)
        self.assertEqual(set(changed), set(N1A_475))
        for turn, (before, after) in changed.items():
            self.assertEqual(before[1], "melee", turn)
            self.assertEqual(after[1], "flee:scroll", turn)
            self.assertTrue(after[0].startswith("r"), turn)
        policy, board = recorded.replay_to("death-n1a-475-1104.json.gz", 2039000)
        self.assertEqual(recorded.assess(policy, board).tier, threat_tiers.T1)

    def test_n1c_084_t1_missiles_become_the_flee_teleport(self):
        changed = decided_with_and_without("d57-me-combat-084-1101.json.gz", OFF)
        self.assertEqual(set(changed), {1287854, 1287893, 1287920})
        for turn, (before, after) in changed.items():
            self.assertEqual(before[1], MISSILE, turn)
            self.assertEqual(after[1], "flee:scroll", turn)

    def test_n1c_083_t1_boards_leave(self):
        changed = decided_with_and_without("d57-n1c-083-1101.json.gz", OFF)
        self.assertEqual({turn: (before[1], after[1]) for turn, (before, after) in changed.items()}, {
            1186736: ("return:recall", "flee"),
            1186984: (MISSILE, "flee"),
            1187014: (MISSILE, "flee:scroll"),
            1187020: (MISSILE, "flee:scroll"),
        })
        changed = decided_with_and_without("d57-me-combat-083-1101.json.gz", OFF)
        self.assertEqual({turn: (before[1], after[1]) for turn, (before, after) in changed.items()},
                         {1190789: (MISSILE, "flee:scroll")})

    def test_lives_with_no_change(self):
        for name in ("death-n1a-470-1103.json.gz", "death-n1b-306-1104.json.gz",
                     "death-n1c-085-1101.json.gz", "death-n1c-099-1102.json.gz",
                     "death-n1c-103-1102.json.gz", "d57-n1c-079-1101.json.gz"):
            with self.subTest(life=name):
                self.assertEqual(decided_with_and_without(name, OFF), {})


class SelectedTargetRecordedTest(unittest.TestCase):
    """The n1-c life-083 beetle board with the absorbed Speed listed at 10 charges (DECLARED
    CONSTRUCTED list, as test_me_speed_fight_1104_recorded shows it): T2 by the Speed dose, and a
    reward race (answer 5), so a selected target that is not left."""

    def board(self):
        from tests import test_d57_me_combat_1101_recorded as combat
        from tests import test_me_speed_fight_1104_recorded as fight
        raw = copy.deepcopy(next(r for r in combat.CASE_083["boards"] if r["turn"] == combat.BEETLE_TURN))
        policy = combat.d57.new_policy(combat.CASE_083)
        fight.show(policy, raw, 10, 20)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        return policy, board

    def flee(self, policy, board):
        hostiles = policy._strategic_hostiles(board)
        with _PolicyObserverScope(policy):
            result = threat_tiers.assess(policy, board, hostiles)
        return result, policy._should_flee(board, hostiles, [m for m in hostiles if m.distance <= 1])

    def test_the_selected_beetle_is_not_left(self):
        policy, board = self.board()
        result, flee = self.flee(policy, board)
        self.assertEqual(result.tier, threat_tiers.T2)
        self.assertEqual(result.supply_plan.categories, ("speed",))
        beetle = result.selected[0]
        self.assertEqual(result.per_monster[beetle].selected, ("reward",))
        self.assertFalse(flee)
        # DECLARED CONSTRUCTED: with the reward taken away it is an unselected T2 and is left; as
        # the active quest's target it is selected again and not left.
        with patch.object(threat_tiers, "reward_reasons", return_value=()):
            result, flee = self.flee(*self.board())
            self.assertEqual((result.tier, result.selected), (threat_tiers.T2, []))
            self.assertTrue(flee)
            with patch.object(threat_tiers, "_quest_races",
                              return_value={result.per_monster[beetle].race_id}):
                result, flee = self.flee(*self.board())
                self.assertEqual(result.per_monster[beetle].selected, ("quest-target",))
                self.assertFalse(flee)


class JudgeDeath168RecordedTest(unittest.TestCase):
    """n1-c life-168 (Lv32), Angband 49F, decision 3434 (tests/fixtures/n1c-168-judge-death-1108):
    闇の審判『デス』 awake in view, five cells away, speed 120 against the player's 110, HP 388/514.
    Recorded: ``summoner:retreat`` (a walk), then at HP 75 the emergency teleport, then death.  The
    board is T1; step 6 leaves it, and since the monster is faster the leave does not walk
    (design 3.2): the flee rung reads Teleportation.  Restart replay of the unmodified board (a
    fresh policy, the skill-exp cache seeded, as test_choke_stall_recreate_1108_recorded does)."""

    @classmethod
    def setUpClass(cls):
        import gzip
        import json
        from pathlib import Path
        from hengbot.monrace_knowledge import load_monrace_knowledge
        from test_esp_threat_rest_recorded import EDIT
        path = Path(__file__).with_name("fixtures") / "n1c-168-judge-death-1108.json.gz"
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def decide(self, *patches):
        import tempfile
        from contextlib import ExitStack
        from pathlib import Path
        from test_esp_threat_rest_recorded import _policy
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            policy = _policy(Path(directory), self.monrace)
            raw = self.case["board"]
            policy.prime(parse_snapshot(copy.deepcopy(raw), self.monrace))
            policy._skill_exp_cache = (0, 0, raw["player"]["level"], None)
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            for each in patches:
                stack.enter_context(each)
            key = str(policy.choose_key(board))
            with _PolicyObserverScope(policy):
                result = threat_tiers.assess(policy, board, policy._strategic_hostiles(board))
            return key, policy.last_reason, result, board

    def test_the_recorded_rows(self):
        self.assertEqual([(row["key"], row["reason"]) for row in self.case["decisions"]],
                         [("9", "summoner:retreat"), ("re", "emergency:teleport")])

    def test_the_faster_t1_summoner_is_left_by_teleport(self):
        key, reason, result, board = self.decide()
        death = next(monster for monster in board.visible_monsters if monster.hostile)
        self.assertEqual((death.speed, board.player.speed, death.distance, death.asleep),
                         (120, 110, 5, False))
        self.assertTrue(death.can_summon)
        self.assertEqual(result.tier, threat_tiers.T1)
        self.assertEqual((key, reason), ("re", "flee:scroll"))
        scroll = next(item for item in board.inventory if item.slot == "e")
        self.assertTrue(scroll.is_teleport_scroll)

    def test_without_the_step_it_walks_away(self):
        key, reason, _result, _board = self.decide(
            patch.object(threat_tiers, "leave_due", lambda *args, **kwargs: None))
        self.assertEqual(reason, "summoner:retreat")

    def test_without_the_faster_rule_the_leave_walks(self):
        key, reason, _result, _board = self.decide(
            patch.object(threat_tiers, "walk_leaves", lambda *args, **kwargs: True))
        self.assertEqual(reason, "flee")


if __name__ == "__main__":
    unittest.main()
