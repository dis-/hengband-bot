"""A known monster whose one breath or ball kills from full HP (oneshot_breath, owner 2026-11-08).

Owner 「感知で見えたら備える」: 「感知で見えている敵（眠っていても）のブレス・球の最大の被害を、今の耐性で
計算し、最大HP 以上なら、その階では耐性の薬を先に飲むか、薬が無ければ階を離れる。」

Recorded n1-c life-161 (Zombie Magic-Eater, Lv32, max HP 418, Angband 44F, 2026-11-08 00:14):
the giant ESP showed a sleeping 『ウートガルザ・ロキ』 (race 683, 40d100 FORCE_MAXHP, BR_COLD) at
(30,98) on the boards of turns 3226983-3227072 while the bot walked to a down stair
(``approach-descent``); 130 boards later a teleport put it beside Loki, which woke and breathed
cold for the whole 418 HP.  The pack held no Potion of Resistance and no Resist Cold, so the floor
is left (Word of Recall, the ESP-threat leave).  Boards: tests/fixtures/oneshot-breath-n1c-161-
1108.json.xz (tests/extract_oneshot_breath_1108_fixture.py), every decision through choose_key.

DECLARED CONSTRUCTED: the potions put in the recorded pack, the status bars, the raised max HP,
the kill line, and the approved plan of the quest-floor case.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from hengbot import oneshot_breath
from hengbot.model import SV_POTION_RESIST_COLD, SV_POTION_RESISTANCE, TVAL_POTION, TVAL_SCROLL, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests.support.recorded import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "oneshot-breath-n1c-161-1108.json.xz"
LOKI = 683
LOKI_NAME = "『ウートガルザ・ロキ』"
FIRST_SHOWN = 3226983      # the first board the ESP showed Loki: recorded '8' approach-descent
AFTER_IT_LEFT = 3227084    # the first board without Loki
SV_SCROLL_WORD_OF_RECALL = 11
LEAVE_RECALL = "esp-threat:leave-recall"


def _potion(sval, name):
    return {"ac": 0, "aware": True, "charges": 0, "charging": False, "count": 2,
            "damage_dice": {"num": 1, "sides": 1}, "fully_known": True, "inscription": "",
            "is_artifact": False, "is_bounty": False, "is_broken": False, "is_cursed": False,
            "is_ego": False, "is_equipment": False, "known": True, "known_flags": [], "name": name,
            "pval": 0, "slot": "?", "sval": sval, "to_a": 0, "to_d": 0, "to_h": 0,
            "tval": TVAL_POTION, "weight": 4}


RESISTANCE = _potion(SV_POTION_RESISTANCE, "耐性の薬")
RESIST_COLD = _potion(SV_POTION_RESIST_COLD, "耐冷の薬")


def carrying(*potions):
    """DECLARED CONSTRUCTED: the potions after the recorded speed potion, the letters re-given."""
    def change(raw):
        inventory = raw["inventory"]
        at = next(index for index, item in enumerate(inventory) if item["tval"] == TVAL_POTION) + 1
        inventory[at:at] = [copy.deepcopy(potion) for potion in potions]
        for index, item in enumerate(inventory):
            item["slot"] = chr(ord("a") + index)
    return change


def bar(*keys):
    def change(raw):
        raw["player"]["status_bar"] = [{"id": 0, "key": key, "label": key} for key in keys]
    return change


def both(*changes):
    def change(raw):
        for each in changes:
            each(raw)
    return change


def letter(raw, tval, sval):
    return next(item["slot"] for item in raw["inventory"] if item["tval"] == tval and item["sval"] == sval)


class OneShotBreathRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.boards = payload["boards"]
        cls.skill = payload["skill"]
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def new_policy(self):
        policy = HengbotPolicy(monrace_knowledge=self.races)
        policy.prime(parse_snapshot(copy.deepcopy(self.boards[0]), self.races))
        return policy

    def snapshot(self, policy, raw):
        policy.consume_skill_knowledge({**self.skill, "player": {"level": raw["player"]["level"]}})
        return policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.races))

    def decide(self, policy, raw):
        key = policy.choose_key(self.snapshot(policy, raw))
        if key:
            policy.confirm_key_posted(key)
        return str(key), policy.last_reason

    def replay(self, until, change=None, policy=None):
        """Every recorded board up to ``until`` (``change`` applied to each), one policy."""
        policy = policy or self.new_policy()
        answers = {}
        for raw in self.boards:
            if raw["turn"] > until:
                break
            raw = copy.deepcopy(raw)
            if change is not None:
                change(raw)
            answers[raw["turn"]] = (raw, *self.decide(policy, raw))
        return policy, answers

    def board(self, turn):
        return copy.deepcopy(next(raw for raw in self.boards if raw["turn"] == turn))

    # -- the recorded floor ------------------------------------------------------------------

    def test_the_sleeping_loki_shown_by_esp_leaves_the_floor(self):
        policy, answers = self.replay(FIRST_SHOWN)
        raw, key, reason = answers[FIRST_SHOWN]
        loki = next(monster for monster in raw["detected_monsters"] if monster["race_id"] == LOKI)
        self.assertTrue(loki["asleep"])
        self.assertEqual(raw["visible_monsters"], [])
        # Nothing in the pack answers cold: no Resistance, no Resist Cold.
        self.assertFalse({(item["tval"], item["sval"]) for item in raw["inventory"]}
                         & {(TVAL_POTION, SV_POTION_RESISTANCE), (TVAL_POTION, SV_POTION_RESIST_COLD)})
        self.assertEqual(reason, LEAVE_RECALL)
        self.assertEqual(key, "r" + letter(raw, TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL))
        # The boards before it walked to the down stair as recorded.
        self.assertEqual(answers[FIRST_SHOWN - 15][2], "approach-descent")

    def test_its_breath_is_the_games_damage_through_the_zombies_resistance(self):
        policy = self.new_policy()
        player = self.snapshot(policy, self.board(FIRST_SHOWN)).player
        self.assertEqual((player.max_hp, player.hp), (418, 418))
        loki = self.races[LOKI]
        # min(4000 / 3, 1600) = 1333; one layer 34% -> 453; with the opposition 12% -> 159.
        self.assertEqual(oneshot_breath.largest(loki, player, frozenset()), (453, "BR_COLD"))
        self.assertEqual(oneshot_breath.largest(loki, player, frozenset({"cold"})), (159, "BR_COLD"))
        no_resistance = replace(player, ability_sources=type(player.ability_sources)({}),
                                abilities=player.abilities - {"resist_cold"})
        self.assertEqual(oneshot_breath.largest(loki, no_resistance, frozenset({"cold"})),
                         (453, "BR_COLD"))
        immune = replace(player, immunities=frozenset({"cold"}))
        self.assertEqual(oneshot_breath.largest(loki, immune, frozenset())[0], 0)

    # -- the drink -----------------------------------------------------------------------------

    def test_a_carried_potion_of_resistance_is_drunk_first(self):
        policy, answers = self.replay(FIRST_SHOWN, carrying(RESISTANCE))
        raw, key, reason = answers[FIRST_SHOWN]
        self.assertEqual(reason, oneshot_breath.QUAFF_REASON)
        self.assertEqual(key, "q" + letter(raw, TVAL_POTION, SV_POTION_RESISTANCE))

    def test_resist_cold_alone_answers_the_floor_before_the_resistance(self):
        policy, answers = self.replay(FIRST_SHOWN, carrying(RESIST_COLD, RESISTANCE))
        raw, key, reason = answers[FIRST_SHOWN]
        self.assertEqual(reason, oneshot_breath.QUAFF_REASON)
        self.assertEqual(key, "q" + letter(raw, TVAL_POTION, SV_POTION_RESIST_COLD))

    def test_while_the_opposition_runs_the_walk_goes_on(self):
        policy, answers = self.replay(FIRST_SHOWN, both(carrying(RESISTANCE), bar("resist_cold")))
        self.assertEqual(answers[FIRST_SHOWN][2], "approach-descent")

    def test_drunk_again_when_it_lapses_after_loki_left_the_esp(self):
        # The opposition ran while Loki was shown; it lapses on the first board without it.
        policy, answers = self.replay(AFTER_IT_LEFT - 1, both(carrying(RESISTANCE), bar("resist_cold")))
        for turn, (_, _, reason) in answers.items():
            self.assertNotEqual(reason, oneshot_breath.QUAFF_REASON, turn)
        raw = self.board(AFTER_IT_LEFT)
        self.assertFalse(any(monster["race_id"] == LOKI for monster in raw["detected_monsters"]))
        carrying(RESISTANCE)(raw)
        key, reason = self.decide(policy, raw)
        self.assertEqual(reason, oneshot_breath.QUAFF_REASON)
        self.assertEqual(key, "q" + letter(raw, TVAL_POTION, SV_POTION_RESISTANCE))

    # -- no action -------------------------------------------------------------------------------

    def test_a_breath_below_the_max_hp_changes_nothing(self):
        def sturdier(raw):
            raw["player"]["hp"] = raw["player"]["max_hp"] = 460   # above Loki's 453
        policy, answers = self.replay(FIRST_SHOWN, sturdier)
        self.assertEqual(answers[FIRST_SHOWN][2], "approach-descent")
        self.assertEqual(oneshot_breath.known(policy, self.snapshot(policy, self.board(FIRST_SHOWN))), [])

    def test_its_kill_line_forgets_it(self):
        policy, _ = self.replay(FIRST_SHOWN, bar("resist_cold"))
        self.assertEqual([race.max_hp for race in oneshot_breath.known(
            policy, self.snapshot(policy, self.board(FIRST_SHOWN)))], [4000])
        raw = self.board(FIRST_SHOWN + 9)  # the next recorded board
        raw["detected_monsters"] = [monster for monster in raw["detected_monsters"]
                                    if monster["race_id"] != LOKI]
        raw["messages"] = [LOKI_NAME + "は死んだ。"]
        key, reason = self.decide(policy, raw)
        self.assertEqual(oneshot_breath.known(policy, self.snapshot(policy, raw)), [])
        self.assertNotEqual(reason, LEAVE_RECALL)

    def test_an_approved_quest_plan_goes_first(self):
        # 「作戦が先・即死だけ例外」: the rung never acts on a quest floor with an approved plan.
        policy, _ = self.replay(FIRST_SHOWN - 1)
        raw = self.board(FIRST_SHOWN)
        raw["floor"]["quest_id"] = 25
        snapshot = self.snapshot(policy, raw)
        with patch.object(HengbotPolicy, "approved_quest_strategy",
                          lambda self, quest_id: object() if quest_id == 25 else None):
            oneshot_breath.observe(policy, snapshot)
            self.assertIsNone(oneshot_breath.key(policy, snapshot))
        oneshot_breath.observe(policy, snapshot)
        self.assertEqual(oneshot_breath.key(policy, snapshot)[0], "r")


if __name__ == "__main__":
    unittest.main()
