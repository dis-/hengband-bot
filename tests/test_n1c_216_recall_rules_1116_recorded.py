"""n1-c life-216 (2026-11-16 16:41-19:21): about 75 recalls in two and a half hours.

Recorded: tests/fixtures/n1c-216-recall-rules-1116.json.xz
(tests/extract_n1c_216_recall_rules_1116_fixture.py).  The rule of decision 1 started many of the returns of the
Lv39 Magic-Eater (HP 606-811) on 山47階, 城50階 and 城64階.

Decision 1 (sent_away_t1).  The 11-09 rule 「テレポート・アウェイで飛ばした T1 の敵がいる階は、クエストの
外なら帰還する。」: owner 2026-11-16, 「T1 の敵」 is 「飛ばした敵が単独で T1 の時だけ」.  Standing in an
engagement that reads T1, or a T1 held by the decided side (``held_tier``), no longer counts.

- 17:02 山47階: on 2434210 the 土の鬼 stood beside a グレーター・バルログ (the engagement reads T1,
  the 土の鬼 alone T3); the バルログ was sent away first, then on 2434214 the 土の鬼, alone in view
  and held at T1 live, and 2434219 printed 「土の鬼が消え去った！」: the return started.
- 18:47 城64階: the 見習レンジャー alone in view, read T3, held at T1 (decision 97457's telemetry
  ``decided``: index 59 T1); 2820448 printed its 「…が消え去った！」 and the bot recalled.
- 18:05 城50階: a グレーター・バルログ reading T1 on its own (HP 581); 2626269 printed its vanishing.
  It still returns.

Every reading is a fresh policy's on the recorded board (the live absorbed lists and monster
memories are not in the capture), so the boards are read with the race file's knowledge.

The 土の鬼's target and the 見習レンジャー's hold are DECLARED CONSTRUCTED in their tests (the live
hold is not reproduced by a fresh policy).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path

from hengbot import retreat_veto_life, sent_away_t1, threat_tiers
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.threat_tier_memory import TIER_MEMORY, Decided, TierMemory
from tests.support.recorded import EDIT, skill

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-216-recall-rules-1116.json.xz"

OGRE, BALROG, RANGER, WOLF, WHITE_WOLF = (
    "土の鬼", "グレーター・バルログ", "見習レンジャー", "狼", "白狼")


class Recorded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.boards = {raw["turn"]: raw for raw in payload["boards"]}
        cls.decisions = payload["decisions"]
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")

    def raw(self, turn):
        return copy.deepcopy(self.boards[turn])

    def snapshot(self, raw):
        return parse_snapshot(copy.deepcopy(raw), self.races)

    def policy(self, raw):
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(self.snapshot(raw))
        skill(policy, raw)
        return policy

    @staticmethod
    def monster(snapshot, name):
        return next(monster for monster in snapshot.visible_monsters
                    if monster.name == name and monster.hostile)


class SentAwayAloneT1Test(Recorded):
    def aim_then_vanish(self, policy, aim, vanish, name):
        """``remember`` on the aim board (the Teleport Away's target), ``observe`` on the next."""
        board = self.snapshot(self.raw(aim))
        sent_away_t1.remember(policy, board, self.monster(board, name))
        sent_away_t1.observe(policy, self.snapshot(self.raw(vanish)))
        return policy

    def test_the_ogre_in_a_t1_engagement_no_longer_returns(self):
        # 2434210: the decision's reading of the engagement, the 土の鬼 beside the バルログ, is T1;
        # the 土の鬼 alone reads T3.
        raw = self.raw(2434210)
        policy = self.policy(raw)
        board = self.snapshot(raw)
        engaged = threat_tiers.engagement(policy, board)
        self.assertEqual({monster.name for monster in engaged}, {OGRE, BALROG})
        self.assertTrue(threat_tiers.cannot_win(threat_tiers.tiered(policy, board, engaged),
                                                board.player.hp))
        self.assertFalse(threat_tiers.cannot_win(
            threat_tiers.assess(policy, board, [self.monster(board, OGRE)]), board.player.hp))
        # DECLARED CONSTRUCTED: the 土の鬼 as the target on 2434210 (the recorded beam there sent
        # the バルログ away; the 土の鬼's own beam on 2434214, its engagement held at T1 live, is
        # not reproduced by a fresh policy: a summoner in view stops the hold,
        # supply_fight_stopped).  2434219 prints 「土の鬼が消え去った！」.
        self.assertIn("土の鬼が消え去った！", self.boards[2434219]["messages"])
        self.aim_then_vanish(policy, 2434210, 2434219, OGRE)
        self.assertFalse(getattr(policy, "_returning_to_town", False))
        self.assertNotEqual(getattr(policy, "_last_return_trigger", None), sent_away_t1.TRIGGER)

    def test_the_held_ranger_no_longer_returns(self):
        decision = self.decisions["2820444"]
        self.assertEqual((decision["decision_sequence"], decision["reason"]),
                         (97457, sent_away_t1.THREAT_REASON))
        self.assertEqual(decision["threat_tiers"]["decided"],
                         [{"index": 59, "tier": "T1", "leave": True}])
        raw = self.raw(2820444)
        policy = self.policy(raw)
        board = self.snapshot(raw)
        ranger = self.monster(board, RANGER)
        self.assertEqual(ranger.index, 59)
        # DECLARED CONSTRUCTED: the decided side the live policy held (decision 97457's
        # ``decided``: index 59 at T1); the boards that decided it are not in the capture.  Its
        # deciding engagement is given one mate still remembered and out of view (a mate in
        # memory and out of view keeps the hold, ``held_tier``'s ``mates_in_view``).
        ranger_key, mate_key = (ranger.index, ranger.race_id), (9999, ranger.race_id)
        memory = TierMemory(board.floor_key)
        for key in (ranger_key, mate_key):
            memory.decided[key] = Decided(
                "T1", True, None, None, 0, ranger.speed, frozenset({ranger_key, mate_key}),
                retreat_veto_life.Threat(ranger.name, board.turn))
        setattr(policy, TIER_MEMORY, memory)
        self.assertTrue(threat_tiers.cannot_win(threat_tiers.tiered(policy, board, [ranger]),
                                                board.player.hp))
        self.aim_then_vanish(policy, 2820444, 2820448, RANGER)
        self.assertFalse(getattr(policy, "_returning_to_town", False))

    def test_a_balrog_t1_on_its_own_still_returns(self):
        raw = self.raw(2626262)
        policy = self.policy(raw)
        board = self.snapshot(raw)
        self.assertTrue(threat_tiers.cannot_win(
            threat_tiers.assess(policy, board, [self.monster(board, BALROG)]), board.player.hp))
        self.aim_then_vanish(policy, 2626262, 2626269, BALROG)
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._last_return_trigger, sent_away_t1.TRIGGER)

    def test_the_vanishing_line_names_exactly_the_target(self):
        # DECLARED CONSTRUCTED: no recorded board shows a name inside another's.  A 狼 sensed on
        # 2584924 (index 146, telepathy) is remembered as sent away in place of the 白狼 the
        # recorded beam sent; 2584928 prints 「白狼が消え去った！」 only, the 狼 out of view.
        raw = self.raw(2584924)
        policy = self.policy(raw)
        board = self.snapshot(raw)
        wolf = next(monster for monster in board.detected_monsters if monster.name == WOLF)
        setattr(policy, sent_away_t1.MEMORY,
                sent_away_t1.SentAway(board.floor_key, board.turn, wolf.index, wolf.name))
        after = self.raw(2584928)
        self.assertEqual(after["messages"], ["白狼が消え去った！"])
        self.assertEqual(after["visible_monsters"], [])
        sent_away_t1.observe(policy, self.snapshot(after))
        self.assertFalse(getattr(policy, "_returning_to_town", False))

    def test_the_game_lines_in_both_languages(self):
        # DECLARED CONSTRUCTED: the game's strings (effect-monster.cpp:546, printed as
        # str_upcase_first(monster_desc) + note).
        vanished = sent_away_t1.vanished
        self.assertTrue(vanished("白狼が消え去った！", WHITE_WOLF))
        self.assertTrue(vanished("白狼が消え去った！ <x2>", WHITE_WOLF))
        self.assertFalse(vanished("白狼が消え去った！", WOLF))
        self.assertTrue(vanished("The white wolf disappears!", "White wolf"))
        self.assertTrue(vanished("Grip, Farmer Maggot's Dog disappears!",
                                 "Grip, Farmer Maggot's Dog"))
        self.assertFalse(vanished("The white wolf disappears!", "Wolf"))
        self.assertFalse(vanished("白狼には耐性がある！", WHITE_WOLF))


if __name__ == "__main__":
    unittest.main()
