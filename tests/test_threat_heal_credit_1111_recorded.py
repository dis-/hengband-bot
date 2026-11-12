"""The supply plan's healing credit and its pessimistic gaps (owner 2026-11-11).

n1-b life-370 (Magic-Eater, Zombie, Lv44, HP 597/648, speed 125 hasted, racial rPois, no rFear /
rBlind) on 2026-11-11 23:30:54 read a sleeping ヴェノム・ワーム (race 1196, HP 3300) T1 and fled
(``me-power:unbeatable-in-range:teleport-away``; recorded supply_margin -452).  Owner:
「体力回復を10使ったら倒すまで25手、被害が大体2600で倒しきれそうに思えるが？」.  The plan credited
each of the ten Potions of Healing 0 HP: drunk at min(max HP, reserve + next-action p95) = 544 it
restored min(300, 648 - 544) = 104, and 104 does not out-heal the next action (272).

Owner decision 2026-11-11 (「回復と悲観側のずれを全部」): 「飲む時の HP を次の1手の最大を基準にし、
二重の条件を外して1本300を数える。耐性の薬を飲んだ後の予備と毒の打撃の軽減、ブレスが敵の今の HP で
弱くなることも入れる。恐怖・盲目の呪文を持つ相手で耐性が無い時は T2 にしない。」  Addition (answer to
「恐怖耐性が無い時のヒーローの薬…は、いつ飲みますか？」): a carried Potion of Heroism (or a running
heroism / berserk) covers the fear spell; the blindness exclusion stays.

Recorded: tests/fixtures/n1b-370-wyrm-t1-1111.json.gz (tests/extract_n1b_370_wyrm_fixture.py), the
board the decision read, driven through the real ``threat_tiers.assess`` / ``tiered``.  The
ヴェノム・ワーム casts SCARE and BLIND and the character resists neither, so the owner's own
exclusion keeps this very board T1 -- now with the reason recorded and a winning plan behind it
(supply_margin +225).  DECLARED CONSTRUCTED: the boards that add ``resist_fear`` / ``resist_blind``,
a Potion of Heroism, the heroism status or a wounded health band to the recorded board, and the
blow unit boards.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle
from hengbot import fear_cover, spectator_threat, threat_tiers
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.monster_ranged_evaluator import maximum_ability_hp_damage
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import OPPOSITION_ABILITY

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-370-wyrm-t1-1111.json.gz"
SHA256 = "9cd2d1c85720e25de2f949f388329c1f6c8dbe82b068f12719d5a6f970b34548"
EDIT = Path("C:/hengband/lib/edit")
WYRM, WYRM_INDEX = 1196, 4
COVERED = frozenset({"resist_fear", "resist_blind"})


def setUpModule():
    global CASE, RACES, DUNGEONS
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SHA256
    CASE = json.loads(gzip.decompress(raw))
    RACES = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
    DUNGEONS = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")


def board_raw():
    return json.loads(CASE["board"])


def setup(raw=None, abilities=frozenset(), status_bar=None):
    """(a fresh policy primed on the board, the board) -- the run's own skill rows as zero."""
    raw = board_raw() if raw is None else raw
    policy = HengbotPolicy(monrace_knowledge=dict(RACES), dungeon_knowledge=dict(DUNGEONS))
    policy.prime(parse_snapshot(copy.deepcopy(raw), RACES))
    policy.consume_skill_knowledge({"player": {"level": raw["player"]["level"]},
                                    "knowledge": {"skills": [{"id": 1, "exp": 0},
                                                             {"id": 3, "exp": 0}]}})
    board = parse_snapshot(copy.deepcopy(raw), RACES)
    player = board.player
    if abilities:
        player = replace(player, abilities=player.abilities | abilities)
    if status_bar is not None:
        player = replace(player, status_bar=tuple(status_bar))
    return policy, replace(board, player=player)


def with_heroism(raw):
    """The recorded pack plus one Potion of Heroism (sv-potion-types.h:37, sval 32)."""
    potion = copy.deepcopy(next(item for item in raw["inventory"]
                                if item["tval"] == 75 and item["sval"] == 37))
    potion.update(sval=fear_cover.SV_POTION_HEROISM, count=1, name="Heroism", slot="o")
    raw["inventory"].append(potion)
    return raw


def wyrm_health(raw, health):
    for monster in (*raw["visible_monsters"], *raw["detected_monsters"]):
        if monster.get("race_id") == WYRM:
            monster["health"] = health
    return raw


class RecordedWyrmTest(unittest.TestCase):
    def test_recorded_reading_was_t1_short_by_452(self):
        recorded = CASE["decision"]
        self.assertEqual(recorded["turn"], 8344271)
        self.assertEqual(recorded["reason"], "me-power:unbeatable-in-range:teleport-away")
        self.assertEqual(recorded["threat_tiers"]["tier"], "T1")
        self.assertEqual(recorded["threat_tiers"]["supply_margin"], -452)
        self.assertEqual(recorded["threat_tiers"]["next_action_p95"], 272)

    def test_recorded_board_wins_on_hp_but_fear_and_blindness_keep_it_t1(self):
        policy, board = setup()
        result = threat_tiers.tiered(policy, board, threat_tiers.engagement(policy, board))
        self.assertEqual(result.tier, threat_tiers.T1)
        self.assertEqual(result.t2_withheld, (fear_cover.FEAR_WITHHELD, fear_cover.BLIND_WITHHELD))
        self.assertIsNone(result.supply_plan)
        # Every supply now wins: the margin is the winning plan's (was -452).
        self.assertEqual(result.supply_margin, 225)
        self.assertEqual(result.as_dict()["t2_withheld"], ["fear-spell", "blind-spell"])
        self.assertTrue(threat_tiers.cannot_win(result, board.player.hp))

    def test_covered_board_is_t2_with_resistance_and_one_healing(self):
        """DECLARED CONSTRUCTED: the recorded board with rFear and rBlind."""
        policy, board = setup(abilities=COVERED)
        result = threat_tiers.tiered(policy, board, threat_tiers.engagement(policy, board))
        self.assertEqual(result.tier, threat_tiers.T2)
        self.assertEqual(result.t2_withheld, ())
        plan = result.supply_plan
        self.assertEqual(plan.categories, threat_tiers.PLAN_ORDER)  # the healing prefix
        self.assertEqual((plan.turns, plan.resistance, plan.heals, plan.speed_doses),
                         (17, 1, (300,), 0))
        self.assertEqual((plan.incoming, plan.capacity), (576, 897))
        # The resisted board's own reserve: its next action (the poison breath x 0.12), not 272.
        self.assertEqual(plan.reserve, 96)
        self.assertEqual(result.reserve, 272)


class HealCreditTest(unittest.TestCase):
    def test_a_dose_is_drunk_at_the_next_action_p95(self):
        self.assertEqual(threat_tiers.heal_credit(300, 648, 272), 300)  # was 104, then dropped
        self.assertEqual(threat_tiers.heal_credit(300, 648, 400), 248)
        self.assertEqual(threat_tiers.heal_credit(1200, 648, 96), 552)
        self.assertEqual(threat_tiers.heal_credit(300, 648, 700), 0)

    def test_a_dose_smaller_than_the_next_action_still_counts(self):
        """The double condition is gone: 300 is credited against a 350 next action."""
        self.assertEqual(threat_tiers.heal_credit(300, 1000, 350), 300)

    def test_the_plan_counts_every_carried_healing(self):
        policy, board = setup()
        self.assertEqual(threat_tiers._heal_doses(policy, board, 272, 648), [300] * 10)


class ResistedReserveTest(unittest.TestCase):
    def test_the_resisted_plan_reads_the_resisted_next_action(self):
        policy, board = setup(abilities=COVERED)
        hostiles = threat_tiers.engagement(policy, board)
        result = threat_tiers.assess(policy, board, hostiles)
        after = threat_tiers._resistance_after(board)
        resisted = policy.threat_prediction(after, hostiles, 1)["operational_total"]
        self.assertEqual(resisted, 96)
        self.assertEqual(result.supply_plan.reserve,
                         threat_tiers.plan_reserve(board.player.max_hp, resisted))


class PoisonBlowTest(unittest.TestCase):
    def blow(self, abilities, effect, damage):
        _policy, board = setup()
        board = replace(board, player=replace(board.player, abilities=frozenset(abilities)))
        return HengbotPolicy._maximum_melee_blow_damage(board, effect, damage)

    def test_poison_blow_layers_the_opposition(self):
        """calc_blow_poison: calc_nuke_damage_rate, 100 -> 40 -> 16 (player-status-resist.cpp)."""
        self.assertEqual(self.blow((), "POISON", 168), 168)
        self.assertEqual(self.blow(("resist_pois",), "POISON", 168), 67)
        self.assertEqual(self.blow((OPPOSITION_ABILITY,), "POISON", 168), 67)
        self.assertEqual(self.blow(("resist_pois", OPPOSITION_ABILITY), "POISON", 168), 26)

    def test_disease_blow_layers_the_opposition(self):
        """calc_blow_disease: (1d4 + 4) / 9 per layer, at most 8/9 (monster-attack-lose.cpp)."""
        self.assertEqual(self.blow(("resist_pois",), "DISEASE", 90), 80)
        self.assertEqual(self.blow((OPPOSITION_ABILITY,), "DISEASE", 90), 80)
        self.assertEqual(self.blow(("resist_pois", OPPOSITION_ABILITY), "DISEASE", 90), 71)


class BreathHpTest(unittest.TestCase):
    def test_breath_follows_the_health_band(self):
        """DECLARED CONSTRUCTED: the ヴェノム・ワーム badly wounded (band upper 24%: HP 792)."""
        knowledge = RACES[WYRM]
        self.assertEqual(maximum_ability_hp_damage("BR_POIS", knowledge), 800)
        self.assertEqual(maximum_ability_hp_damage("BR_POIS", knowledge, monster_hp=792), 264)
        self.assertEqual(maximum_ability_hp_damage("BR_POIS", knowledge, monster_hp=9999), 800)
        for health, hp, ranged in (("unhurt", 3300, 272), ("badly_wounded", 792, 89)):
            policy, board = setup(wyrm_health(board_raw(), health))
            hostiles = threat_tiers.engagement(policy, board)
            self.assertEqual([monster.hp for monster in hostiles], [hp])
            row = policy.threat_prediction(board, hostiles, 1)["monsters"][0]
            # min(hp / 3, 800) through rPois's 34% (mspell-damage-calculator.cpp:101-102).
            self.assertEqual(row["ranged_prediction"], ranged)
            self.assertEqual(threat_tiers.assess(policy, board, hostiles).next_action_p95, ranged)


class FearCoverTest(unittest.TestCase):
    def test_fear_caster_without_rfear_stays_t1(self):
        """DECLARED CONSTRUCTED: rBlind only."""
        policy, board = setup(abilities=frozenset({"resist_blind"}))
        result = threat_tiers.assess(policy, board)
        self.assertEqual((result.tier, result.t2_withheld), (threat_tiers.T1, ("fear-spell",)))

    def test_blind_caster_without_rblind_stays_t1(self):
        policy, board = setup(abilities=frozenset({"resist_fear"}))
        result = threat_tiers.assess(policy, board)
        self.assertEqual((result.tier, result.t2_withheld), (threat_tiers.T1, ("blind-spell",)))

    def test_a_carried_heroism_covers_the_fear(self):
        """DECLARED CONSTRUCTED: one Potion of Heroism added; the blindness still withholds."""
        policy, board = setup(with_heroism(board_raw()))
        self.assertTrue(fear_cover.fear_covered(policy, board))
        self.assertEqual(threat_tiers.assess(policy, board).t2_withheld, ("blind-spell",))
        policy, board = setup(with_heroism(board_raw()), abilities=frozenset({"resist_blind"}))
        self.assertEqual(threat_tiers.assess(policy, board).tier, threat_tiers.T2)

    def test_running_heroism_or_berserk_covers_the_fear(self):
        for bar in (("heroism",), ("berserk",), ("resist_fear",)):
            policy, board = setup(status_bar=bar)
            self.assertTrue(fear_cover.fear_covered(policy, board), bar)
        policy, board = setup(status_bar=("haste",))
        self.assertFalse(fear_cover.fear_covered(policy, board))
        self.assertFalse(fear_cover.blind_covered(board))

    def test_a_held_t2_drops_to_t1_at_once_when_withheld(self):
        """The hold (「境に余裕を持たせる」) does not keep a T2 over a withheld reading."""
        policy, covered = setup(abilities=COVERED)
        hostiles = threat_tiers.engagement(policy, covered)
        self.assertEqual(threat_tiers.tiered(policy, covered, hostiles).tier, threat_tiers.T2)
        bare = replace(covered, player=replace(covered.player,
                                               abilities=covered.player.abilities - COVERED))
        result = threat_tiers.tiered(policy, bare, threat_tiers.engagement(policy, bare))
        self.assertEqual(result.tier, threat_tiers.T1)
        self.assertEqual(threat_tiers.decided_sides(policy, bare, hostiles),
                         [{"index": WYRM_INDEX, "tier": "T1", "leave": True}])

    def test_spectator_shows_why(self):
        policy, board = setup()
        result = threat_tiers.tiered(policy, board, threat_tiers.engagement(policy, board))
        judgement = spectator_threat.monster_judgement(result, WYRM_INDEX)
        self.assertEqual(judgement["t2_withheld"], ["fear-spell", "blind-spell"])
        facts = threat_tiers.facts(policy, board)
        self.assertEqual(spectator_threat.engagement_judgement(facts)["t2_withheld"],
                         ["fear-spell", "blind-spell"])


if __name__ == "__main__":
    unittest.main()
