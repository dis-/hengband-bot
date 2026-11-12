"""n1-a life-514 (Half-Giant Warrior Lv46, HP 1168, Angband 49F, 2026-11-12 11:54): the T3 melee.

Recorded: tests/fixtures/n1a-514-t3-survival-1112.json.gz
(tests/extract_n1a_514_t3_survival_1112_fixture.py).  The teleport of 11284379 landed beside
風の女王『アリエル』 (race 687, speed +20, 1_IN_5: BA_COLD, BA_ELEC, BO_ELEC).  The engagement
read T3 (3-turn p95 192, next action 99) while the boards lost 274 in one turn; the warrior
drank its last Healing potions at 521 and 431 and then meleed her at 722, 681 and 623
(11284426, 11284437, 11284450), read Teleportation at 429 and died on the next landing.

Owner 2026-11-12 (「物資の使用は生存判定に任せる。HPが減ったなら使うべきは回復テレポート破壊だった
のではないのか？」) and the coordinator's items:

D. The spell probability (monster_ranged_evaluator.ability_selection_probabilities): the game
   tries a spell on randint1(100) <= freq_spell per move (monster-processor.cpp:554); no_inate
   removes the innate abilities (mspell-attack.cpp:45-52), so a spell-only caster casts on every
   attempt; a non-innate spell then fails on 25 - (rlev + 3) / 4 percent (mspell-attack.cpp:
   183-192).  Ariel read about 8% a move; the game's 20% x 0.86 = 17.2% now.  On the recorded
   boards she reads T1 and the melee boards leave.
A. The projection missed (threat_tiers ``_projection_missed``): the HP lost over the last three
   boards above the projection over three turns re-reads the tier from the observed damage,
   ignoring the held side.  DECLARED CONSTRUCTED: Ariel at 1_IN_20 (spell_frequency 5), so the
   projection still reads T3 and only the observed loss turns it.
B. The T3 band on the side the projection survives (owner 「死なない側に置き直す」): entered at a
   free margin of the reserve, left below 0.  DECLARED CONSTRUCTED readings on the recorded
   board (``decided`` / ``held_tier``).
C. The low-HP escape also before a melee blow (owner 「殴り合いにも効かせる」): below the low-HP
   line with a faster, summoning or TELE_TO monster awake in view, *Destruction*, then
   Teleportation, then Recall.  DECLARED CONSTRUCTED: Ariel at 1_IN_20 (T3) on 11284450.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import threat_tiers
from hengbot.exploration_ledger import ExplorationLedger
from hengbot.model import parse_snapshot
from hengbot.monster_ranged_evaluator import (
    SpellSelectionContext,
    ability_selection_probabilities,
    ranged_action_distribution,
)
from hengbot.policy import HengbotPolicy
from hengbot.protocol import ProtocolSchemaError
from tests.support.recorded import skill
from tests.test_n1b_348_stops_1108_recorded import knowledge

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-514-t3-survival-1112.json.gz"
SHA256 = "652f9ecb418f1361fc2be85fef9b0698f842d87143127ea68e2634771aee66a9"
ARIEL = 687
LANDED, HEAL_521, HEAL_431 = 11284390, 11284403, 11284415
MELEE = (11284426, 11284437, 11284450)
LEAVES = ("flee:scroll", "emergency:teleport")


def setUpModule():
    global CASE
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SHA256
    CASE = json.loads(gzip.decompress(raw))


def races(spell_frequency=None):
    known = knowledge(CASE)
    if spell_frequency is not None:
        known[ARIEL] = replace(known[ARIEL], spell_frequency=spell_frequency)
    return known


def board(turn):
    return next(row for row in CASE["rows"]
                if row.get("type") == "player_turn" and row["turn"] == turn)


def replay(known):
    """One fresh policy fed every recorded row; {turn: (key, reason, reading)} from the
    landing on, the reading being the engagement's (``tiered``) after the decision."""
    policy = HengbotPolicy(monrace_knowledge=known)
    boards = [row for row in CASE["rows"] if row.get("type") == "player_turn"]
    first = parse_snapshot(copy.deepcopy(boards[0]), known)
    ledger = ExplorationLedger(None)
    ledger.bind(first)
    policy._exploration_ledger = ledger
    policy.prime(first)
    skill(policy, boards[0])
    out = {}
    for raw in CASE["rows"]:
        kind = raw.get("type")
        if kind == "knowledge":
            policy.consume_skill_knowledge(raw)
            continue
        if kind == "character":
            policy.observe_character_snapshot(raw.get("character"), envelope=raw)
            continue
        try:
            snapshot = parse_snapshot(copy.deepcopy(raw), known)
            key = policy.choose_key(snapshot)
        except ProtocolSchemaError:
            skill(policy, raw)
            snapshot = parse_snapshot(copy.deepcopy(raw), known)
            key = policy.choose_key(snapshot)
        key = "" if key is None else str(key)
        reason = policy.last_reason
        if key:
            policy.confirm_key_posted(key)
        if raw["turn"] >= LANDED:
            hostiles = threat_tiers.engagement(policy, snapshot)
            reading = threat_tiers.tiered(policy, snapshot, hostiles) if hostiles else None
            out[raw["turn"]] = (key, reason, reading)
    return out


def fresh(known, turn):
    raw = board(turn)
    policy = HengbotPolicy(monrace_knowledge=known)
    policy.prime(parse_snapshot(copy.deepcopy(raw), known))
    skill(policy, raw)
    return policy, parse_snapshot(copy.deepcopy(raw), known)


class SpellProbabilityTest(unittest.TestCase):
    """D."""

    def test_ariel_casts_on_one_move_in_five_less_her_failures(self):
        ariel = races()[ARIEL]
        selection = ability_selection_probabilities(ariel, SpellSelectionContext(distance=1))
        self.assertAlmostEqual(sum(selection.values()), 1.0, places=6)
        per_action, _ = ranged_action_distribution(ariel, selection_probabilities=selection)
        # 20% x (1 - (25 - (44 + 3) // 4) / 100) = 0.2 x 0.86
        self.assertAlmostEqual(1.0 - per_action[0], 0.172, places=6)


class RecordedBoardsTest(unittest.TestCase):
    """D on the recorded boards: Ariel reads T1 and no melee board strikes her."""

    @classmethod
    def setUpClass(cls):
        cls.boards = replay(races())

    def test_the_live_scene(self):
        live = {row["turn"]: (row["key"], row["reason"]) for row in CASE["decisions"]}
        for turn in MELEE:
            self.assertEqual(live[turn], ("1", "melee"))

    def test_the_melee_boards_leave(self):
        for turn in MELEE:
            key, reason, reading = self.boards[turn]
            self.assertIn(reason, LEAVES, turn)
            self.assertTrue(key.startswith("r"), (turn, key))
            self.assertNotEqual(reading.tier, threat_tiers.T3, turn)  # T1, or T2 not entered

    def test_the_heals_stay_first(self):
        for turn in (HEAL_521, HEAL_431):
            self.assertEqual(self.boards[turn][1], "item:heal")


class ProjectionMissedTest(unittest.TestCase):
    """A (DECLARED CONSTRUCTED: Ariel at 1_IN_20)."""

    @classmethod
    def setUpClass(cls):
        cls.boards = replay(races(spell_frequency=5))

    def test_the_landing_starts_the_count_over(self):
        # The fire balls before the teleport are another engagement's: no miss on landing.
        key, reason, reading = self.boards[LANDED]
        self.assertEqual(reading.tier, threat_tiers.T3)
        self.assertIsNone(reading.projection_missed)
        self.assertEqual(reason, "ranged:fire")

    def test_the_missed_projection_reads_t1_and_the_melee_board_leaves(self):
        key, reason, reading = self.boards[MELEE[0]]
        self.assertEqual(reading.tier, threat_tiers.T1)
        self.assertEqual(reading.raw_tier, threat_tiers.T3)
        observed, projected = reading.projection_missed
        self.assertEqual(observed, 274)  # 705 -> 431 over the three boards before
        self.assertGreater(observed, projected)
        self.assertEqual((key, reason), ("rd", "flee:scroll"))
        self.assertTrue(all(self.boards[turn][1] in LEAVES for turn in MELEE))


class SafeSideBandTest(unittest.TestCase):
    """B (DECLARED CONSTRUCTED readings on the recorded board 11284426)."""

    def reading(self, policy, snapshot, **fields):
        raw = threat_tiers.assess(policy, snapshot, threat_tiers.engagement(policy, snapshot))
        return replace(raw, instant_death=False, t2_withheld=(), **fields)

    def test_a_first_t3_reading_inside_the_reserve_is_not_entered(self):
        policy, snapshot = fresh(races(spell_frequency=5), MELEE[0])
        hostiles = threat_tiers.engagement(policy, snapshot)
        raw = self.reading(policy, snapshot, tier=threat_tiers.T3, free_margin=50, reserve=117)
        self.assertEqual(threat_tiers.decided(policy, snapshot, hostiles, raw).tier,
                         threat_tiers.T2)
        policy, snapshot = fresh(races(spell_frequency=5), MELEE[0])
        raw = self.reading(policy, snapshot, tier=threat_tiers.T3, free_margin=117, reserve=117)
        self.assertEqual(threat_tiers.decided(policy, snapshot, hostiles, raw).tier,
                         threat_tiers.T3)

    def test_a_held_t3_is_left_below_zero(self):
        policy, snapshot = fresh(races(spell_frequency=5), MELEE[0])
        raw = self.reading(policy, snapshot, tier=threat_tiers.T2, free_margin=-5, reserve=117,
                           supply_margin=60)
        self.assertEqual(threat_tiers.held_tier(threat_tiers.T3, raw, worse_as_read=False,
                                                mates_in_view=True), threat_tiers.T2)
        # In [0, reserve) a held T3 stays, as before (the band's width kept).
        raw = self.reading(policy, snapshot, tier=threat_tiers.T3, free_margin=10, reserve=117)
        self.assertEqual(threat_tiers.held_tier(threat_tiers.T3, raw, worse_as_read=False,
                                                mates_in_view=True), threat_tiers.T3)


class LowHpMeleeEscapeTest(unittest.TestCase):
    """C (DECLARED CONSTRUCTED: Ariel at 1_IN_20, so the board reads T3)."""

    def test_the_blow_at_low_hp_gives_way_to_the_teleport(self):
        policy, snapshot = fresh(races(spell_frequency=5), MELEE[2])
        hostiles = threat_tiers.engagement(policy, snapshot)
        self.assertEqual(threat_tiers.tiered(policy, snapshot, hostiles).tier, threat_tiers.T3)
        self.assertEqual(policy._low_hp_walk_gate_active(snapshot), (True, True))  # 623 < 868
        policy.last_reason = "melee"
        self.assertEqual(policy._low_hp_walk_gate(snapshot, "1"), "rd")
        self.assertEqual(policy.last_reason, "emergency:teleport")

    def test_above_the_line_the_blow_stands(self):
        known = races(spell_frequency=5)
        policy, snapshot = fresh(known, MELEE[2])
        high = replace(snapshot, player=replace(snapshot.player, hp=900))
        policy.last_reason = "melee"
        self.assertEqual(policy._low_hp_walk_gate(high, "1"), "1")


if __name__ == "__main__":
    unittest.main()
