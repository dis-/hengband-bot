"""n1-a life-514 (Half-Giant Warrior Lv46, HP 1168, Angband 49F) died 2026-11-12 11:54:51.

Recorded: tests/fixtures/n1a-514-death-1112.json.gz (tests/extract_n1a_514_death_1112_fixture.py).
Every decision is the public ``choose_key`` of one fresh policy fed the recorded rows in order
(boards, the skill-knowledge and character rows between them); one pass serves every pin.

1. あつくもえるてき (race 1295, Lv59, NEVER_MOVE, BA_FIRE / BR_FIRE 1_IN_3, speed +20) lay
   asleep at (16,41), distance 10-11.  Its line to the player crossed grids the board had never
   shown, which ``_has_line_of_fire`` read as walls, so ``threat_prediction`` predicted 0 even
   once it was awake, although projectable() reached (its fire balls hit the player).  The
   engagement read T3 (a reward race), its free damage 518.7 was the warrior's melee although it
   could not come to the player, and the bot shot it awake (11284347, 11284361
   ``ranged:fire-target``) and took 1168 -> 714 in fire balls before the emergency teleport.
   Now an awake monster's unknown grids are open (owner 2026-11-08 「未知のマスを壁と見ない」;
   a sleeper casts nothing until it wakes, and opening a sleeper's unknown grids made the
   floor's fifteen sleeping 巨大首なし a lethal swarm on arrival), a monster that cannot come
   beside the player but reaches it at range is fought by ranged means only (threat_projection
   ``free_attack``), and the ranged rung does not wake a sleeper into an engagement that reads
   T1 awake (policy_combat ``_sleeper_not_to_wake``; owner 2026-11-09 C 「T1では撃たず離れる」,
   2026-11-07 「眠っている敵でも強い敵からは離れる」).
2. The teleport landed beside 風の女王『アリエル』 (race 687, AURA_ELEC, FORCE_MAXHP, speed +20).
   The T3 against her was judged by the bow (198 a turn: melee scored 0 for her aura) while the
   melee rung struck her (486 a turn), 「電撃をくらった！」 on every blow (player-attack.cpp:568
   touch_zap_player, player-damage.cpp:611-641).  Now the tiers count the blow a class that
   melees strikes and its cost (attack_expectation ``aura_self_damage``); the Magic-Eater keeps
   its 「触ると害のある敵は近接から外す」 score.
3. The survival rungs on her boards (owner 2026-11-12 「物資の使用は生存判定に任せる。HPが減った
   なら使うべきは回復テレポート破壊だったのではないのか？」): no *Destruction* was held (owner
   2026-11-04: a staff or an absorbed power; the warrior carried neither); the last Healing
   potions were drunk at 521 and 431 and Teleportation read at 429.  That teleport landed in the
   fire monster's view, on the floor item 1 no longer wakes it on.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import attack_expectation, destruction_use, threat_tiers
from hengbot.exploration_ledger import ExplorationLedger
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.protocol import ProtocolSchemaError
from tests.support.recorded import skill
from tests.test_n1b_348_stops_1108_recorded import knowledge

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-514-death-1112.json.gz"
FLAME, ARIEL = 1295, 687


def case():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


CASE = case()


def recorded():
    """{(turn, nth decision of that turn): (key, reason)} of the live decisions."""
    rows, seen = {}, {}
    for row in CASE["decisions"]:
        nth = seen[row["turn"]] = seen.get(row["turn"], -1) + 1
        rows[(row["turn"], nth)] = (row["key"], row["reason"])
    return rows


def _decide(policy, races, raw):
    try:
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), races))
    except ProtocolSchemaError:
        skill(policy, raw)  # the periodic ~f skill list the live game answered
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), races))
    key = "" if key is None else str(key)
    if key:
        policy.confirm_key_posted(key)
    return key


def replay(probes):
    """One fresh policy fed every recorded row; ``probes`` maps (turn, nth board of that turn)
    to a function of (policy, snapshot) run right after that board's decision.  Returns
    {(turn, nth): (key, reason, the probe's value)}."""
    races = knowledge(CASE)
    policy = HengbotPolicy(monrace_knowledge=races)
    boards = [row for row in CASE["rows"] if row.get("type") == "player_turn"]
    first = copy.deepcopy(boards[0])
    board = parse_snapshot(first, races)
    ledger = ExplorationLedger(None)
    ledger.bind(board)
    policy._exploration_ledger = ledger
    policy.prime(board)
    skill(policy, first)
    seen, out = {}, {}
    for raw in CASE["rows"]:
        kind = raw.get("type")
        if kind == "knowledge":
            policy.consume_skill_knowledge(raw)
            continue
        if kind == "character":
            policy.observe_character_snapshot(raw.get("character"), envelope=raw)
            continue
        number = seen[raw["turn"]] = seen.get(raw["turn"], -1) + 1
        key = _decide(policy, races, raw)
        probe = probes.get((raw["turn"], number))
        if probe is not None:
            out[(raw["turn"], number)] = (key, policy.last_reason, probe(
                policy, parse_snapshot(copy.deepcopy(raw), races)))
    missing = set(probes) - set(out)
    if missing:
        raise AssertionError(f"boards {sorted(missing)} not recorded")
    return out


def monster(snapshot, race):
    return next(each for each in snapshot.visible_monsters if each.race_id == race)


def _flame_far(policy, snapshot):
    """11284337: the sleeping flame at distance 11, its line over never-shown grids."""
    flame = monster(snapshot, FLAME)
    awake = replace(flame, asleep=False)
    here = snapshot.player.position
    return {
        "distance": flame.distance, "asleep": flame.asleep,
        "line": policy._has_line_of_fire(snapshot, flame.position, here,
                                         remembered=policy._remembered_grids),
        "projects": policy._may_project(snapshot, flame.position, here),
        "asleep_total": policy.threat_prediction(snapshot, [flame])["total"],
        "awake_total": policy.threat_prediction(snapshot, [awake])["total"],
    }


def _flame_shot(policy, snapshot):
    """11284347: the board of the live first shot (the flame asleep at distance 10)."""
    flame = monster(snapshot, FLAME)
    awake = replace(flame, asleep=False)
    return {
        "not_to_wake": policy._sleeper_not_to_wake(snapshot, flame),
        "free_awake": threat_tiers.free_attack(policy, snapshot, awake),
        "melee": attack_expectation.melee(policy, snapshot, awake),
    }


def _tier(policy, snapshot):
    result = threat_tiers.tiered(policy, snapshot, threat_tiers.engagement(policy, snapshot))
    return {"tier": result.tier, "free": dict(result.free_damage),
            "self": dict(result.free_self_damage), "instant_death": result.instant_death}


def _ariel(policy, snapshot):
    ariel = monster(snapshot, ARIEL)
    return {**_tier(policy, snapshot), "index": ariel.index,
            "aura": attack_expectation.aura_self_damage(policy, snapshot, ariel),
            "blows": snapshot.player.main_hand_blows,
            "melee_scored": attack_expectation.melee(policy, snapshot, ariel),
            "melee_struck": attack_expectation.melee(policy, snapshot, ariel, through_aura=True),
            "destruction": destruction_use.holds_means(policy, snapshot)}


FLAME_FAR, FLAME_SHOT, FLAME_WOKEN = (11284337, 0), (11284347, 0), (11284352, 0)
FIRE_1062, FIRE_714 = (11284361, 0), (11284379, 0)
HEAL_521, HEAL_431 = (11284403, 0), (11284415, 0)
MELEE = ((11284426, 0), (11284437, 0), (11284450, 0))
TELEPORT_429 = (11284461, 0)


class N1a514DeathRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probes = {FLAME_FAR: _flame_far, FLAME_SHOT: _flame_shot, FLAME_WOKEN: _tier,
                  FIRE_1062: _tier, FIRE_714: _tier, HEAL_521: _ariel, HEAL_431: _ariel,
                  TELEPORT_429: _ariel, **{board: _ariel for board in MELEE}}
        cls.boards = replay(probes)
        cls.live = recorded()

    def test_recorded_scene(self):
        self.assertEqual(self.live[FLAME_SHOT], ("fn*t5\x1b", "ranged:fire-target"))
        self.assertEqual(self.live[FIRE_1062], ("fn*t5\x1b", "ranged:fire-target"))
        self.assertEqual(self.live[FIRE_714], ("re", "emergency:teleport"))
        self.assertEqual(self.live[HEAL_431], ("qc", "item:heal"))
        for board in MELEE:
            self.assertEqual(self.live[board], ("1", "melee"))
        self.assertEqual(self.live[TELEPORT_429], ("rd", "emergency:teleport"))
        far = self.boards[FLAME_FAR][2]
        self.assertEqual((far["distance"], far["asleep"]), (11, True))
        # The board knows no line (never-shown grids); projectable() over them reaches.
        self.assertFalse(far["line"])
        self.assertTrue(far["projects"])

    def test_an_awake_caster_reaches_over_unknown_grids(self):
        """Fix 1 (owner 2026-11-08 「未知のマスを壁と見ない」), for an awake monster."""
        far = self.boards[FLAME_FAR][2]
        self.assertGreater(far["awake_total"], 0)
        self.assertEqual(far["asleep_total"], 0)  # a sleeper casts nothing until it wakes
        # The board after the live shot (the flame awake): T1, not the live T3.
        self.assertEqual(self.boards[FLAME_WOKEN][2]["tier"], threat_tiers.T1)

    def test_a_caster_that_cannot_come_is_not_meleed_for_free(self):
        """Fix 2: the never-moving flame reaches the player at range; its free damage is the
        bow's (230.5), not the warrior's melee (518.7 live)."""
        shot = self.boards[FLAME_SHOT][2]
        damage, cost = shot["free_awake"]
        self.assertGreater(shot["melee"], damage)
        self.assertAlmostEqual(damage, 230.53, places=1)
        self.assertEqual(cost, 0.0)

    def test_the_sleeping_flame_is_not_shot_awake(self):
        """Owner 2026-11-09 C 「T1では撃たず離れる」 / 2026-11-07 「眠っている敵でも強い敵からは
        離れる」: woken, the engagement reads T1, so the sleeper is not shot."""
        key, reason, shot = self.boards[FLAME_SHOT]
        self.assertTrue(shot["not_to_wake"])
        self.assertFalse(key.startswith("f"), (key, reason))
        self.assertFalse(reason.startswith("ranged:"), reason)

    def test_once_woken_the_fire_is_left(self):
        """Had the shot been fired: the board after it and the 1062-HP board read the
        Teleportation scroll instead of the live second shot."""
        for board in (FLAME_WOKEN, FIRE_1062):
            key, reason, facts = self.boards[board]
            self.assertEqual(facts["tier"], threat_tiers.T1)
            self.assertEqual(key, "re", (board, reason))

    def test_the_melee_struck_at_an_aura_counts_with_its_cost(self):
        """Fix 3: the tiers count the blow the melee rung strikes at 風の女王『アリエル』 (AURA_ELEC)
        and the 「電撃をくらった！」 each blow costs: Dice(1 + 44/26, 1 + 44/17) = 2d3 through
        elec_dam at the resistance's rate 34 (player-damage.cpp:618,
        player-status-resist.cpp:95-125), one HP a blow on average, seven blows."""
        for board in MELEE:
            key, reason, facts = self.boards[board]
            self.assertEqual((key, reason), ("1", "melee"))
            index = facts["index"]
            self.assertEqual(facts["melee_scored"], 0.0)  # the Magic-Eater's score, unchanged
            self.assertGreater(facts["melee_struck"], 400)
            self.assertAlmostEqual(facts["free"][index], facts["melee_struck"])
            self.assertEqual(facts["blows"], 7)
            self.assertAlmostEqual(facts["aura"], 7.0)
            self.assertAlmostEqual(facts["self"][index], 7.0)
            self.assertEqual(facts["tier"], threat_tiers.T3)

    def test_the_survival_rungs_on_ariels_boards(self):
        """Owner 2026-11-12 「HPが減ったなら使うべきは回復テレポート破壊」: no *Destruction* was
        held (owner 2026-11-04: a staff or an absorbed power, neither carried); the heals at
        521 and 431 and the Teleportation at 429 are the survival rungs' answers."""
        for board in (HEAL_521, HEAL_431, TELEPORT_429, *MELEE):
            self.assertFalse(self.boards[board][2]["destruction"])
        self.assertEqual(self.boards[HEAL_521][:2], ("qc", "item:heal"))
        self.assertEqual(self.boards[HEAL_431][:2], ("qc", "item:heal"))
        self.assertEqual(self.boards[TELEPORT_429][:2], ("rd", "emergency:teleport"))


if __name__ == "__main__":
    unittest.main()
