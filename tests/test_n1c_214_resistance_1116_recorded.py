"""n1-c life-214 (2026-11-16 10:09, Angband 80F): three Potions of Resistance, then Teleportation.

Recorded: tests/fixtures/n1c-214-resistance-1116.json.xz
(tests/extract_n1c_214_resistance_1116_fixture.py).  The Lv47 Magic-Eater (HP 899, lasting
resistance to the five elements from its equipment) met a 銀ライネル (race 1415, speed +15,
4x 8d11 HURT, 1_IN_3 MISSILE / BO_MANA / PSY_SPEAR / BR_FIRE, IM_FIRE/COLD/ELEC; lib/edit
MonraceDefinitions.jsonc) at [27,165].  The supply fight (threat tiers, T2, the lynel a reward
race) drank a Potion of Resistance at turn 7275151 (HP 684, after the fire breath burnt a
Teleportation scroll); the opposition showed on the status bar from turn 7275157 on.  It drank
again at 7275157 (HP 510) and 7275160 (HP 463), and at 7275165 (HP 414) read Teleportation as
instant death (``next-action-p95`` 420 >= 414).  It landed in a mind-worm nest
(マインドワーム x20, BRAIN_SMASH) and died before its next decision (HP -22).

Two defects of the approved rules:

- 「効いている間は飲みません」 (owner 2026-11-05, resist_potion): the supply fight's
  ``threat_projection._resistance_after`` asked only for ``OPPOSITION_ABILITY``, which no board
  carried, so it planned (and ``supply_fight._resistance_key`` drank) the potion on every turn.
- 「耐性の薬を飲んだ後の予備」 (owner 2026-11-11): the plan credits the drink with the resisted
  next action (p95 271 here), but once drunk the board itself never carried the opposition, so
  the projection read the fire breath at one layer again (p95 420) and called HP 414 instant
  death.  ``model.parse_snapshot`` now adds ``OPPOSITION_ABILITY`` when the status bar shows the
  opposition and every element also has a lasting resistance (two layers each, as the game:
  player-status-resist.cpp); with no lasting resistance the ``resist_<element>`` ability already
  is the opposition's single layer.

The decisions on these boards also depend on the absorbed lists (not in the capture), so the
tiers are asked directly (``threat_tiers.assess``) on a fresh policy, as
test_threat_tiers_supply_fight_recorded does.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.policy import HengbotPolicy  # noqa: F401 -- first: the plan modules import in a cycle
from hengbot import supply_fight, threat_tiers
from hengbot.cli import _PolicyObserverScope
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import OPPOSITION_ABILITY
from hengbot.threat_projection import _resistance_after
from tests.support.recorded import EDIT, skill

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-214-resistance-1116.json.xz"
BEFORE = 7275151           # the first drink: no opposition yet
OPPOSED = (7275157, 7275160, 7275165)
TELEPORT = 7275165
LYNEL = "銀ライネル"
FIVE = ("acid", "elec", "fire", "cold", "pois")
BAR = {f"resist_{name}" for name in FIVE}


class N1c214ResistanceRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.rows = {row["board"]["turn"]: row for row in payload["boards"]}
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")

    def raw(self, turn):
        return copy.deepcopy(self.rows[turn]["board"])

    def assessed(self, raw):
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(raw), self.races))
        skill(policy, raw)
        board = parse_snapshot(copy.deepcopy(raw), self.races)
        with _PolicyObserverScope(policy):
            result = threat_tiers.assess(policy, board, policy._strategic_hostiles(board))
        return policy, board, result

    def test_the_recorded_decisions(self):
        recorded = [(self.rows[turn]["decision"]["reason"], self.rows[turn]["decision"]["key"])
                    for turn in (BEFORE, *OPPOSED)]
        self.assertEqual(recorded, [(supply_fight.SUPPLY_RESIST_REASON, "qc")] * 3
                         + [("emergency:teleport", "re")])
        bars = {turn: {entry["key"] for entry in self.raw(turn)["player"]["status_bar"]}
                for turn in (BEFORE, *OPPOSED)}
        self.assertFalse(bars[BEFORE] & BAR)
        for turn in OPPOSED:
            self.assertLessEqual(BAR, bars[turn])
        for turn in (BEFORE, *OPPOSED):
            self.assertEqual([monster["name"] for monster in self.raw(turn)["visible_monsters"]],
                             [LYNEL])

    def test_the_first_drink_is_still_planned(self):
        _policy, board, result = self.assessed(self.raw(BEFORE))
        self.assertNotIn(OPPOSITION_ABILITY, board.player.abilities)
        self.assertIsNotNone(_resistance_after(board))
        self.assertEqual(result.tier, threat_tiers.T2)
        self.assertEqual(result.supply_plan.resistance, 1)

    def test_no_second_drink_while_the_opposition_runs(self):
        for turn in OPPOSED:
            with self.subTest(turn=turn):
                policy, board, result = self.assessed(self.raw(turn))
                self.assertIn(OPPOSITION_ABILITY, board.player.abilities)
                self.assertIsNone(_resistance_after(board))
                self.assertEqual(result.supply_plan.resistance, 0)
                lynel = next(monster for monster in policy._strategic_hostiles(board)
                             if monster.name == LYNEL)
                self.assertIsNone(supply_fight._resistance_key(policy, board, lynel))

    def test_the_running_opposition_is_the_planned_next_action(self):
        # The first drink's plan credited the resisted next action; the drunk board reads it.
        _policy, _board, planned = self.assessed(self.raw(BEFORE))
        _policy, _board, result = self.assessed(self.raw(TELEPORT))
        self.assertEqual(planned.supply_plan.reserve, result.next_action_p95)
        self.assertLess(result.next_action_p95, self.raw(TELEPORT)["player"]["hp"])
        self.assertFalse(result.instant_death)

    def test_no_layer_without_a_lasting_resistance(self):
        # DECLARED CONSTRUCTED: the recorded board with the five resistances' equipment source
        # taken away, the opposition alone (one layer, already the resist_<element> ability).
        raw = self.raw(TELEPORT)
        for name in FIVE:
            raw["player"]["ability_sources"][f"resist_{name}"] = {
                "equipment": False, "permanent": False, "temporary": True}
        board = parse_snapshot(raw, self.races)
        self.assertNotIn(OPPOSITION_ABILITY, board.player.abilities)
        self.assertLessEqual(BAR, board.player.abilities)
        self.assertIsNone(_resistance_after(board))

    def test_without_the_bar_the_temporary_source_is_the_opposition(self):
        # DECLARED CONSTRUCTED: the recorded board without the status bar and the parsed layer
        # (a pre-protocol-3 emitter): the drink reads the temporary source.
        board = parse_snapshot(self.raw(TELEPORT), self.races)
        bare = replace(board, player=replace(board.player, status_bar=None,
                                             abilities=board.player.abilities
                                             - {OPPOSITION_ABILITY}))
        self.assertIsNone(_resistance_after(bare))


if __name__ == "__main__":
    unittest.main()
