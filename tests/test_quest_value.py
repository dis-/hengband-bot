"""Which fixed quest is worth taking now (quest_value, 2026-11-27), through the real consumers.

Owner 2026-11-27 「n1-cは長時間49Fで停滞している。これがQ25を放棄して確定入手テレパシーを諦めた代償で
ある。…固定クエストの取り扱いに関して作戦を立てると良い。」 and 「Q33も…しっかり比較検討すること。」.

The recorded board is n1-c life-223's Outpost arrival of 2026-11-27 05:38 with the absorbed-power
lists the game last displayed (tests/fixtures/n1c-223-town-arrival-cl41-1127.provenance.txt): a
Zombie Magic-Eater at CL41, maximum HP 732, Angband recall depth 49 and no telepathy, held at the
50F gate.  The cases drive the fixed-quest head (``_fixed_quest_head``), the acceptance
(``_fixed_quest_target`` / ``_fixed_quest_ready``), the quest's resolved force (over-match), the
Black Market tour's arming and the attempt ledger.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation, also for bare module runs

import dataclasses
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from hengbot import bm_tour, quest_attempt_ledger, quest_force_rows, quest_value, strategy_profile
from hengbot.model import QuestState, parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import QUEST_STATUS_TAKEN, QUEST_STATUS_UNTAKEN
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.town_maps import find_outpost_map, parse_town_map

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name("fixtures") / "n1c-223-town-arrival-cl41-1127.json.gz"
MONRACES = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
QUESTS = load_quest_knowledge(find_quest_definitions(Path(__file__)))
STRATEGIES = load_quest_strategies(ROOT / "strategy" / "quests")
OUTPOST = parse_town_map(find_outpost_map(Path(__file__)))
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)


def _board(**player):
    """The recorded board, HP topped up as after the visit's rest, with ``player`` changes."""
    board = parse_snapshot(CASE["board"], MONRACES)
    changes = {"hp": board.player.max_hp, **player}
    return dataclasses.replace(board, player=dataclasses.replace(board.player, **changes))


def _policy(profile=strategy_profile.DEFAULT_PROFILE, strategies=STRATEGIES) -> HengbotPolicy:
    policy = HengbotPolicy(OUTPOST, quest_knowledge=QUESTS, quest_strategies=strategies)
    policy._instance_profile = profile
    policy._me_device_lists = {kind: (value[0], value[1])
                               for kind, value in CASE["me_device_lists"].items()}
    return policy


class RecordedN1cTakesQ18ForQ25Test(unittest.TestCase):
    """CL41, no telepathy, held at 49F: Q18 (the door to Q25's telepathy) is the head and taken."""

    def test_q18_is_needed_binding_and_taken(self):
        board = _board()
        policy = _policy()
        self.assertEqual(policy._missing_required_abilities(board, 50), {"telepathy"})
        found = quest_value.verdict(policy, board, 18)
        self.assertEqual((found.take, found.why, found.needs, found.binding),
                         (True, "needed", frozenset({"telepathy"}), True))
        self.assertEqual(quest_value.verdict(policy, board, 25).needs, frozenset({"telepathy"}))
        head = policy._fixed_quest_head(board)
        self.assertEqual((head.id, head.status), (18, QUEST_STATUS_UNTAKEN))
        # The absorbed Speed (42 charges at 94%) stands for the 17 Speed potions, and the
        # over-match (HP 732 >= 700, damage 486 >= 300 per 10 game turns) for the 2 Healing
        # potions the character does not carry: Q18 is accepted on this visit.
        self.assertEqual(policy._fixed_quest_target(board), 18)
        self.assertTrue(policy._fixed_quest_readiness["verdict"])
        self.assertEqual(policy.fixed_quest_readiness_state()["quest_value"]["18"]["why"], "needed")

    def test_without_the_over_match_the_healing_potions_hold_it(self):
        stripped = dict(STRATEGIES)
        profile = stripped[18]
        force = {k: v for k, v in profile.required_force.items() if k != quest_force_rows.OVER_MATCH}
        stripped[18] = dataclasses.replace(profile, required_force=force)
        policy = _policy(strategies=stripped)
        self.assertIsNone(policy._fixed_quest_target(_board()))
        self.assertEqual(policy._fixed_quest_readiness["strategy_force"]["failed"], ["heal_potions"])

    def test_q25_over_match_asks_two_healing_potions(self):
        board = _board()
        policy = _policy()
        resolved = policy._strategy_force_for_snapshot(board, STRATEGIES[25])
        self.assertTrue(resolved.get(quest_force_rows.OVER_MATCHED))
        self.assertEqual(resolved["heal_potions"], 2)
        weaker = _board(max_hp=650, hp=650)
        self.assertEqual(policy._strategy_force_for_snapshot(weaker, STRATEGIES[25])["heal_potions"], 5)


class VerdictTest(unittest.TestCase):
    """Not needed, under-strength, a profile skip, and Q33's speed need."""

    def test_a_character_with_telepathy_passes_q18_over(self):
        abilities = frozenset(_board().player.abilities | {"telepathy"})
        board = _board(abilities=abilities)
        policy = _policy()
        found = quest_value.verdict(policy, board, 18)
        self.assertEqual((found.take, found.why), (False, "no-need"))
        # Q33 (offered: Q32 is finished) is not needed either at a 49F recall depth.
        self.assertEqual(quest_value.verdict(policy, board, 33).why, "no-need")
        self.assertIsNone(policy._fixed_quest_head(board))
        self.assertIsNone(policy._fixed_quest_target(board))

    def test_an_under_strength_character_defers_and_keeps_levelling(self):
        board = _board(level=34)
        policy = _policy()
        found = quest_value.verdict(policy, board, 18)
        self.assertEqual((found.take, found.why, found.min_cl, found.binding),
                         (False, "deferred", 37, True))
        self.assertIsNone(policy._fixed_quest_head(board))
        self.assertIsNone(policy._quest_strategy_for_errand_or_floor(board))

    def test_the_profile_skip_still_wins(self):
        policy = _policy(strategy_profile.parse({"skip_quests": [18]}))
        self.assertIsNone(policy._fixed_quest_head(_board()))
        played = _policy(strategy_profile.parse({"quest_value": False}))
        self.assertEqual(played._fixed_quest_head(_board()).id, 18)

    def test_q33_is_needed_for_the_speed_gates_from_its_level(self):
        board = _board()
        # The recall depth + 15 reaches the +25 row (91F since owner 2026-11-28, 81F before).
        deep = dataclasses.replace(board, dungeon_recall_depths={**board.dungeon_recall_depths, 1: 76})
        policy = _policy()
        found = quest_value.verdict(policy, deep, 33)
        self.assertIn("speed+25", found.needs)
        self.assertEqual((found.take, found.why, found.min_cl), (False, "deferred", 46))
        stronger = dataclasses.replace(deep, player=dataclasses.replace(deep.player, level=46))
        self.assertEqual(quest_value.verdict(policy, stronger, 33).why, "needed")

    def test_a_taken_quest_is_never_held_back(self):
        board = _board(abilities=frozenset(_board().player.abilities | {"telepathy"}))
        taken = dataclasses.replace(board, quests={**board.quests, 18: QuestState(
            id=18, name="", status=QUEST_STATUS_TAKEN, type=4, level=35, flags=6, fixed=True)})
        policy = _policy()
        self.assertFalse(quest_value.holds_back(policy, taken, 18))
        self.assertEqual(policy._fixed_quest_head(taken).id, 18)


class GateBoundTourTest(unittest.TestCase):
    """66,444 gold, held at the 50F gate by telepathy: the Black Market tour is armed."""

    def test_gate_bound_arms_the_tour_below_the_gold_line(self):
        board = _board()
        policy = _policy()
        bm_tour.note_recall_return(policy, board)
        bm_tour.town_key(policy, board)
        self.assertEqual(bm_tour.facts(policy)["why"], "gate-bound:telepathy")
        self.assertTrue(bm_tour.facts(policy)["armed"])

        held = _board(abilities=frozenset(_board().player.abilities | {"telepathy"}))
        other = _policy()
        bm_tour.note_recall_return(other, held)
        bm_tour.town_key(other, held)
        self.assertEqual(bm_tour.facts(other)["closed"], f"gold-below-{bm_tour.MIN_GOLD}")


class LedgerTest(unittest.TestCase):
    """A status change and a quest floor entry are written; the first board writes nothing."""

    def test_rows(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / quest_attempt_ledger.FILE_NAME
            policy = _policy()
            policy._quest_outcome_ledger_path = path
            board = _board()
            quest_attempt_ledger.observe(policy, board)
            self.assertFalse(path.exists())
            taken = dataclasses.replace(board, quests={**board.quests, 18: QuestState(
                id=18, name="", status=QUEST_STATUS_TAKEN, type=4, level=35, flags=6, fixed=True)})
            quest_attempt_ledger.observe(policy, taken)
            inside = dataclasses.replace(taken, floor_key=(0, 1, 18))
            quest_attempt_ledger.observe(policy, inside)
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(row["quest"], row["event"]) for row in rows], [(18, "taken"), (18, "entered")])
        self.assertEqual((rows[0]["cl"], rows[0]["max_hp"], rows[0]["deepest_recall"]), (41, 732, 49))


if __name__ == "__main__":
    unittest.main()
