"""n1-c life-216 (Magic-Eater Lv50, Angband 80F, 2026-11-18 13:36): killed while Recall counted
down by an unseen はぐれメタル (race 871: speed +80, AC 10000, 3d2 HP, EMPTY_MIND, casting every
turn), recorded.

The character (speed +29, see invisible, telepathy; the absorbed *Destruction* x70, Healing staff
and rod, Teleportation staff, Teleport Away wand; 5 Potions of Healing and 15 Teleportation
scrolls) was hit from the dark (「何かが純ログルスを放った。」), saw the metal once at distance 3
(game turn 7228517), walked on with the unseen retreat, read Recall at 758 HP and waited with
'5' while HP fell 758 -> 555 -> 630 (after a Potion of Healing; 225 taken) -> 261 -> 230 -> 361
-> 133 -> 288 -> dead (505 in one turn).

Four defects, one class each:

1. ``HiddenByHealingTest``: the observation's ``_took_damage`` compared HP with the previous
   board's only, so the drink's +300 hid the 225 taken after it and the Recall wait's
   unseen-attacker rung was skipped (``return:wait-recall`` at 7228541).  heal_offset.
2. (next commits)

Recorded: tests/fixtures/n1c-216-death-1118.jsonl.gz (tests/extract_n1c_216_death_1118_fixture.py),
the live boards 7228502-7228558, replayed by one fresh policy through the public ``choose_key``
from the first board on, as tests/test_n1c_207_death_1114_recorded does.  The fresh process reads
Recall on its first boards (it has no record of the live process's floor plan), which leaves the
boards' own observation untouched: the recorded HP, messages and pack are what each board reads.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import unittest
from unittest import mock

from hengbot import heal_offset
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-216-death-1118.jsonl.gz"
EDIT = Path(r"C:\hengband\lib\edit")
METAL = 871                 # はぐれメタル, MonraceDefinitions.jsonc
SEEN = 7228517              # the one board the metal was in view (distance 3)
FIRST_DRINK = 7228538       # HP 555: 「何かが魔力の矢の呪文を唱えた。」, the first Healing drunk
AFTER_DRINK = 7228541       # HP 630: +300 from the drink, 225 from the next bolt


class Replay:
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.costs = load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc")

    def board(self, turn):
        return next(board for board in self.boards if board["turn"] == turn)

    def decide(self, turn, edit=None):
        """(policy, the board of ``turn``, its key) after replaying the boards before it;
        ``edit(raw)`` changes the raw board of ``turn`` before it is parsed."""
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        policy._skill_exp_request_key = lambda snapshot: None
        with mock.patch.object(HengbotPolicy, "_missing_required_abilities",
                               lambda self, *args, **kwargs: frozenset()):
            for raw in self.boards:
                if raw["turn"] > turn:
                    break
                raw = copy.deepcopy(raw)
                if raw["turn"] == turn and edit is not None:
                    edit(raw)
                snapshot = parse_snapshot(raw, self.monrace)
                key = policy.choose_key(snapshot)
                if raw["turn"] == turn:
                    return policy, snapshot, key
                if key:
                    policy.confirm_key_posted(key)
        raise AssertionError(turn)


class TheRecordingTest(Replay, unittest.TestCase):

    def test_the_boards(self):
        self.assertEqual(len(self.boards), 23)
        hp = {board["turn"]: board["player"]["hp"] for board in self.boards}
        self.assertEqual((hp[FIRST_DRINK], hp[AFTER_DRINK]), (555, 630))
        seen = [monster["race_id"] for monster in self.board(SEEN)["visible_monsters"]]
        self.assertEqual(seen, [METAL])
        after = self.board(AFTER_DRINK)["messages"]
        self.assertTrue(any(message.endswith("気分が良くなった。") for message in after))
        self.assertTrue(any(message.startswith("何かが魔力の矢") for message in after))


class HiddenByHealingTest(Replay, unittest.TestCase):

    def test_the_damage_after_the_drink_is_damage(self):
        policy, snapshot, key = self.decide(AFTER_DRINK)
        self.assertTrue(policy._took_damage)
        self.assertEqual(policy._last_damage_amount, 555 + 300 - 630)
        self.assertIsNotNone(policy._unseen_attack_evidence)
        # The Recall wait's unseen-attacker rung answers it (live: return:wait-recall '5').
        self.assertNotEqual(policy.last_reason, "return:wait-recall")
        self.assertTrue(policy.last_reason.startswith("unseen-recall:"), policy.last_reason)

    def test_no_message_no_credit(self):
        # DECLARED CONSTRUCTED control: hp_player's message removed from the board; a potion that
        # left the pack without it (sold, dropped, destroyed) restores nothing.
        def silent(raw):
            raw["messages"] = [message for message in raw["messages"]
                               if not message.endswith(heal_offset.HEAL_MESSAGES)]
        policy, _snapshot, _key = self.decide(AFTER_DRINK, silent)
        self.assertFalse(policy._took_damage)


if __name__ == "__main__":
    unittest.main()
