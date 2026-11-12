"""Quest 25 on n1-c life-178 (2026-11-09 07:37:32-07:37:38): the death to Raal's Tome, recorded.

The process restarted at 07:27 on the Q25 floor, in the tome phase (phase 6 of the plan, battle
record phase 5).  It posted 5227 keys and none was a ``b`` (browse) or an ``m`` (cast): the
absorbed-power lists live in the process only (me_device_attacks.observe_lists) and the periodic
refresh waits for a safe filler, so every absorbed power was unknown.  From [5,5] the tome [9,8]
is not in view (floor/line-of-sight.cpp los: the walls [6,5][7,5][8,5]), the strongest attack the
phase knew was the bow, and it shot arrows at the unseen tome (half the hit chance, shoot.cpp)
while the tome's breaths took the Healing potions; it died at decision 5226.  With the lists the
same boards fire the absorbed ドラゴンの火炎 (fire breath 200, the tome HURT_FIRE) at the grid.

The boards are the decision-tail's 47 (decisions 5180-5226); each test replays them from 5180 by
one policy through the public ``choose_key``, the battle carried by the real record (the process's
own record at the death, its turn moved to the first board: DECLARED CONSTRUCTED, the battle was in
the tome phase over the whole window and its record changed only in its ``observed`` board).  A
list the policy asks for (``b`` + kind) arrives, when the test says so, on the next board as the
executor's read of the screen (``_magic_eater_power_list``, the town-arrival lists of the life,
the counts of the death dump): DECLARED CONSTRUCTED, the recorded boards were never browsed.
The process was hungry from decision 5194 on; the meal rule merged since (quest_find_exit
``steps_aside_for_food``, n1-c life-178's hold) eats on the first hungry board without a hostile
near, and once the policy has posted that meal the later boards read 「normal」 (DECLARED
CONSTRUCTED: the meal's effect; the recorded process never ate).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import me_capability, me_device_attacks, me_powers_refresh, quest25_battle as battle, quest_room_sweep, threat_tiers
from hengbot.model import SV_ROD_HEALING
from hengbot.policy_constants import REST_MACRO
from hengbot.model import _parse_items, parse_snapshot
from tests.support import q25_house as q25


with gzip.open(Path(__file__).with_name("fixtures") / "n1c-178-q25-death-1109.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

FIRST = 5180
LETTER_KIND = {letter: kind for kind, letter in me_powers_refresh.KIND_LETTER.items()}
BREATH = "mB0@9,8"
MEAL_REASONS = {"survival:mana-absorb", "survival:eat"}          # ドラゴンの火炎 (wand sval 26, letter '0') at the tome's grid


def lists(changes=None):
    found = {kind: (turn, [dict(row) for row in rows]) for kind, (turn, rows) in CASE["lists"].items()}
    for (kind, name), fields in (changes or {}).items():
        for row in found[kind][1]:
            if row["name"] == name:
                row.update(fields)
    return found


def new_policy(first, record):
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    first = copy.deepcopy(first)
    policy.prime(parse_snapshot(first, policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(CASE["skill"]), turn=first["turn"],
        player=dict(CASE["skill"]["player"], level=first["player"]["level"])))
    policy.consume_home_knowledge(tuple(_parse_items(CASE["home"]["knowledge"]["items"], protocol=3)))
    policy._q25_battle_record_path = record
    policy._me_power_resume_reads = True   # as the CLI sets it (cli.py, beside the record path)
    return policy


def replay(*, answer_lists=None, edit=None, probe=None, through=None):
    """{sequence: (key, reason)} of the window replayed by one policy.  ``answer_lists``: the
    lists a browse the policy posts is answered with on the next board; ``edit(sequence, raw)``
    changes a board (declared by its test)."""
    answers = {}
    boards = CASE["boards"]
    with TemporaryDirectory() as directory:
        record = Path(directory) / "q25-battle.json"
        record.write_text(json.dumps(dict(CASE["battle"], turn=boards[0]["turn"], board=None)),
                          encoding="utf-8")
        policy = new_policy(boards[0], record)
        browsed = None
        fed = False
        for raw, row in zip(boards, CASE["recorded"]):
            if through is not None and row["sequence"] > through:
                break
            raw = copy.deepcopy(raw)
            if browsed is not None and answer_lists is not None:
                raw["_magic_eater_power_list"] = {"kind": browsed,
                                                  "rows": answer_lists[browsed][1]}
            if fed and raw["player"].get("food_state") == "hungry":
                raw["player"]["food_state"] = "normal"
            if edit is not None:
                edit(row["sequence"], raw)
            snapshot = parse_snapshot(raw, policy._monrace_knowledge)
            if probe is not None:
                probe(policy, snapshot, row["sequence"])
            key = str(policy.choose_key(snapshot))
            answers[row["sequence"]] = (key, policy.last_reason)
            browsed = LETTER_KIND.get(key[1:]) if key[:1] == "b" and len(key) == 2 else None
            fed = fed or policy.last_reason in MEAL_REASONS
            policy.confirm_key_posted(key)
    return answers


def recorded(sequence):
    for raw, row in zip(CASE["boards"], CASE["recorded"]):
        if row["sequence"] == sequence:
            return raw, row
    raise KeyError(sequence)


class RecordingTest(unittest.TestCase):

    def test_the_process_never_read_a_list_and_shot_arrows_from_5_5(self):
        keys = CASE["process_keys"]
        self.assertEqual(len(keys), 5227)
        self.assertEqual([key for key in keys if key[:1] in {"b", "m"}], [])
        shots = [row for raw, row in zip(CASE["boards"], CASE["recorded"])
                 if (raw["player"]["y"], raw["player"]["x"]) == (5, 5) and row["key"].startswith("f")]
        self.assertEqual(len(shots), 9)
        self.assertTrue(all(row["key"].endswith("*p3332t5\x1b") for row in shots))
        for raw, _ in (recorded(row["sequence"]) for row in shots):
            self.assertFalse(any(monster["race_id"] == 557 for monster in raw["visible_monsters"]))


class ResumeReadsTheListsTest(unittest.TestCase):
    """Owner 2026-11-09 item 5 and the correction 「指定の範囲攻撃を使わず弓を勝手に使った不具合が第一」."""

    def test_a_restarted_process_reads_each_list_first(self):
        answers = replay(through=FIRST + 3)
        self.assertEqual([answers[FIRST + n] for n in range(3)],
                         [("bA", me_powers_refresh.REFRESH_REASON), ("bB", me_powers_refresh.REFRESH_REASON),
                          ("bC", me_powers_refresh.REFRESH_REASON)])

    def test_with_the_lists_read_the_tome_takes_the_breath_not_the_bow(self):
        answers = replay(answer_lists=lists(), through=5191)
        fired = {sequence: key for sequence, (key, _) in answers.items() if sequence > FIRST + 2}
        self.assertEqual([key for key in fired.values() if key.startswith("f")], [])
        self.assertEqual(answers[5186][0], BREATH)



class OutOfTheFireTest(unittest.TestCase):
    """Owner 2026-11-09 (the correction's second) 「一歩で安全圏に移動して休息できるのに愚かにも戦闘を
    継続したこと」, the formation's 「傷ついて敵がいなければ射線の外まで歩いて休む」: the lists read, so the
    tome phase's own plan (the breath from the near stands) is not the withdrawal of Q1."""

    def test_damaged_out_of_the_fire_it_rests_before_walking_in(self):
        answers = replay(answer_lists=lists())
        # [6,2] at HP 161 of 503, before the Recall (after it, decision 5221 walks to the stair:
        # RecallReadStopsThePhaseTest); recorded: '9' into [5,3].
        self.assertEqual(recorded(5201)[1]["key"], "9")
        self.assertEqual(answers[5201], (REST_MACRO, battle.FIRE_REST_REASON))

    def test_damaged_in_the_fire_one_step_takes_it_out(self):
        answers = replay(answer_lists=lists())
        # [5,3] at HP 43: the tome's breath reaches it, [5,2] beside does not.
        self.assertEqual(answers[5224], ("4", battle.OUT_OF_FIRE_REASON))


class UnseenTomeTest(unittest.TestCase):
    """Owner 2026-11-09 Q1 「1に加え、倒しきれなければ下がる。生存を優先させたはず」: no arrow at the
    unseen tome; the grid-aimed attack, else a cell that sees it; and, damaged, a plan that cannot
    kill it within the quest's kill horizon withdraws out of the fire to rest."""

    def test_without_an_area_attack_no_arrow_flies_at_the_unseen_tome(self):
        answers = replay()
        self.assertEqual([where for where, (key, _) in answers.items() if key.startswith("f")], [])
        # Damaged (HP 415 of 503) with only the bow: out of the fire.
        self.assertEqual(answers[5183], ("7", battle.WITHDRAW_REASON))
        # At full HP: to [5,6], the nearest cell that sees the tome (los).
        self.assertEqual(answers[5186], ("6", battle.SIGHT_REASON))

    def test_with_the_breath_the_damaged_player_keeps_firing_within_the_horizon(self):
        answers = replay(answer_lists=lists())
        self.assertEqual(recorded(5187)[1]["hp"], 387)
        self.assertEqual(answers[5187][0], BREATH)



def lit_hall(sequence):
    """DECLARED CONSTRUCTED: board ``sequence`` draws the hall's [5,11]-[5,15] lit (F_LIT_STANDARD, a
    glowing floor in view: as the formation's Light scroll at [5,3] would light the hall,
    spells-lite.cpp lite_room); the recorded hall was dark (the player's light only)."""
    def edit(at, raw):
        if at == sequence:
            grid_map = raw["grid_map"]
            grid_map["palette"].append([1, 0, 416, 1])       # floor, F_LIT_STANDARD, known
            grid_map["runs"].append([5, 11, 5, len(grid_map["palette"]) - 1])
    return edit


class LitHallSightTest(unittest.TestCase):
    """Owner 2026-11-09 「照らされた所も入れる」: a glowing grid in the player's line is seen out to
    MAX_PLAYER_SIGHT, not only within his light (floor/geometry.cpp player_can_see_bold:
    CAVE_LITE, else CAVE_VIEW and CAVE_GLOW without CAVE_MNDK).  Decision 5186: [5,5], full HP,
    no list read (the bow only), light radius 5; the cells within 5 of the tome [9,8] that see it
    are reached by '6' ([5,6]).  With the hall lit, [4,5] (distance 6, its line to [9,8] clear)
    sees it too."""

    def test_dark_hall_the_light_radius(self):
        answers = replay(through=5186)
        self.assertEqual(answers[5186], ("6", battle.SIGHT_REASON))

    def test_lit_hall_a_cell_beyond_the_light_sees_the_tome(self):
        answers = replay(edit=lit_hall(5186), through=5186)
        self.assertEqual(answers[5186], ("8", battle.SIGHT_REASON))


def frost_only():
    """DECLARED CONSTRUCTED: the life's lists with Disintegrate, Dragon's Flame and Dragon's Breath
    spent (count 0): the strongest attack at the tome's grid is Dragon's Frost, about 16 a turn."""
    return lists({("wand", me_device_attacks.POWERS[("wand", sval)].names[0]): {"current": 0}
                  for sval in (25, 26, 28)})


def tome_shown(sequence, health, bar=None):
    """DECLARED CONSTRUCTED: board ``sequence`` shows the tome on [9,8] (the record of decision
    5208 where it was seen) at ``health``; ``bar``: the health bar tracking it at that length."""
    shown = copy.deepcopy(next(monster for monster in recorded(5208)[0]["visible_monsters"]
                               if monster["race_id"] == 557))

    def edit(at, raw):
        if at == sequence:
            raw["visible_monsters"].append(dict(shown, health=health))
            if bar is not None:
                raw["health_bar"] = {"known": True, "index": shown["index"], "length": bar,
                                     "color": "orange"}
    return edit


class TomeSeenHealthTest(unittest.TestCase):
    """Owner 2026-11-09 「見えた傷の具合で見込む」: the tome's HP for the kill estimate is read from its
    displayed health when seen (the band, the health bar), the last seen while unseen, and the
    maximum 500 (50d10) if never seen.  Decision 5183: [5,5], HP 415 of 503 (damaged), the tome
    unseen; with Dragon's Frost alone (16 a turn) the quest's kill horizon (10 actions) holds
    against 120 HP (badly wounded) but not 500."""

    def test_never_seen_the_500_withdraws(self):
        estimate = {}

        def probe(policy, snapshot, sequence):
            if sequence == 5183:
                estimate["hp"] = battle._tome_hp(battle._ctx(policy, snapshot))

        answers = replay(answer_lists=frost_only(), probe=probe, through=5183)
        self.assertEqual(answers[5183], ("7", battle.WITHDRAW_REASON))
        self.assertEqual(estimate["hp"], 500.0)     # not the average 275

    def test_seen_badly_wounded_on_the_board_before_it_keeps_firing(self):
        answers = replay(answer_lists=frost_only(), edit=tome_shown(5182, "badly_wounded"), through=5183)
        self.assertEqual(answers[5183], ("mB1@9,8", "ranged:magic-eater-device"))

    def test_the_health_bar_narrows_the_band(self):
        # "wounded" reads 59% (295, past the horizon); the bar of length 2 reads 19% (95).
        wounded = replay(answer_lists=frost_only(), edit=tome_shown(5182, "wounded"), through=5183)
        self.assertEqual(wounded[5183], ("7", battle.WITHDRAW_REASON))
        barred = replay(answer_lists=frost_only(), edit=tome_shown(5182, "wounded", bar=2), through=5183)
        self.assertEqual(barred[5183], ("mB1@9,8", "ranged:magic-eater-device"))


class StartStairOutOfHealingTest(unittest.TestCase):
    """Owner 2026-11-04 (QUEST_25 ``exit_when_out_of_healing``) 「薬を使い切っていたら踏んで良い」:
    Healing used up, HP at the panic line, the start stair [13,1] within a few steps."""

    def test_decision_5216_walks_to_the_start_stair(self):
        raw, row = recorded(5216)
        self.assertEqual(((raw["player"]["y"], raw["player"]["x"]), row["hp"], row["key"]), ((11, 1), 81, "8"))
        answers = replay()
        for sequence in (5216, 5217, 5218, 5219):   # [11,1]..[8,1], 2 to 5 steps from [13,1]
            self.assertEqual(answers[sequence], ("2", quest_room_sweep.EXIT_WALK_REASON), sequence)



class RecallReadStopsThePhaseTest(unittest.TestCase):
    """Owner 2026-11-09 Q2 「段をやめ射線外で待つ」: 「段の動きをやめる。開始の階段へ行ければ踏み、
    行けなければ動かない敵の射線の外へ下がって発動を待つ。」  Recall was read at decision 5205."""

    def test_after_the_recall_the_walk_goes_to_the_start_stair_not_the_tome(self):
        answers = replay()
        for sequence, key in ((5220, "2"), (5221, "1"), (5223, "1")):   # [7,1], [6,2], [6,2]
            self.assertIn(recorded(sequence)[1]["key"], {"9"})            # recorded: toward [5,3]
            self.assertEqual(answers[sequence], (key, battle.RECALL_EXIT_WALK_REASON), sequence)
        # From the east room the walk round by the north corridor crosses no cell of the fire.
        self.assertEqual(answers[5209], ("8", battle.RECALL_EXIT_WALK_REASON))
        # In the fire with no cell out one step off: out by the least exposed walk.
        self.assertEqual(answers[5226], ("7", battle.RECALL_OUT_REASON))



HEALING = ("staff", "体力回復")


class AbsorbedHealingNoTeleportTest(unittest.TestCase):
    """Owner 2026-11-09 Q3 「成功率が80%以上なら体力回復は使っても良い。テレポートは許可しない」.
    The life's absorbed Healing showed 32% (4 charges); the 95% list is DECLARED CONSTRUCTED."""

    def test_at_32_percent_the_absorbed_healing_is_not_cast(self):
        answers = replay(answer_lists=lists())
        self.assertEqual(answers[5223], ("1", battle.RECALL_EXIT_WALK_REASON))

    def test_at_95_percent_it_is_cast_where_the_healing_potion_would_be_drunk(self):
        answers = replay(answer_lists=lists({HEALING: {"success": 95}}))
        # [6,2] at HP 43 of 503, no Healing potion, no Teleportation scroll: the heal line.
        self.assertEqual(answers[5223], ("mAs", battle.ABSORBED_HEAL_REASON))

    def test_the_absorbed_teleportation_is_not_cast_in_q25(self):
        # DECLARED CONSTRUCTED: the board of decision 5223 made blind, where a blind player casts
        # the absorbed Teleportation in place of the scroll (threat_tiers.blind_teleport_key).
        found = {}

        def blind(sequence, raw):
            if sequence == 5223:
                raw["player"]["status"]["blind"] = True

        def probe(policy, snapshot, sequence):
            if sequence == 5223:
                found["means"] = threat_tiers.blind_teleport_means(policy, snapshot)
                found["escapes"] = threat_tiers.escape_means(policy, snapshot, [])

        answers = replay(answer_lists=lists(), edit=blind, probe=probe, through=5223)
        self.assertIsNone(found["means"])
        self.assertNotIn("absorbed-teleport", found["escapes"])
        self.assertFalse(answers[5223][0].startswith("mA"), answers[5223])


class AbsorbedHealingBeforePotionTest(unittest.TestCase):
    """Owner 2026-11-09 「即死の危険がないときは薬より優先する」 and 「ロッドも同じ」: at the plan's heal
    line the absorbed Healing (success at least 80%) before the Healing potion, but at the instant
    death the potion first.  Decision 5184: [5,5], HP 291 of 503, a Healing potion carried; the
    recorded process drank it ('qc').  The 95% rows are DECLARED CONSTRUCTED (the life showed the
    staff's at 32% and had no rod of Healing)."""

    def test_the_staff_healing_comes_before_the_potion(self):
        self.assertEqual(recorded(5184)[1]["key"], "qc")
        answers = replay(answer_lists=lists({HEALING: {"success": 95}}), through=5184)
        self.assertEqual(answers[5184], ("mAs", battle.ABSORBED_HEAL_REASON))

    def test_at_32_percent_the_potion_is_drunk(self):
        answers = replay(answer_lists=lists(), through=5184)
        self.assertEqual(answers[5184], ("qc", "quest-strategy:heal"))

    def test_the_rod_healing_the_same(self):
        rod = lists()
        rod["rod"][1].append({"name": me_capability.names("rod", SV_ROD_HEALING)[0], "fail": 5,
                              "success": 95, "charging": 0, "max": 1})
        answers = replay(answer_lists=rod, through=5184)
        self.assertEqual(answers[5184], ("mCj", battle.ABSORBED_HEAL_REASON))

    def test_the_staff_healing_spent_the_rod_serves(self):
        rod = lists({HEALING: {"success": 95, "current": 0}})
        rod["rod"][1].append({"name": me_capability.names("rod", SV_ROD_HEALING)[0], "fail": 5,
                              "success": 95, "charging": 0, "max": 1})
        answers = replay(answer_lists=rod, through=5184)
        self.assertEqual(answers[5184], ("mCj", battle.ABSORBED_HEAL_REASON))

    def test_at_the_instant_death_the_potion_comes_first(self):
        # DECLARED CONSTRUCTED: decision 5184's HP set to 30 and 33.  The unseen loss the life
        # observed (32, threat_tiers unseen_correction) makes the next action lethal at 30, not at
        # 33.  The plan's escape answers the board then (the HP line's Teleportation), so the
        # rung itself is asked on the replayed policy and board.
        found = {}
        for hp in (30, 33):
            def edit(sequence, raw, hp=hp):
                if sequence == 5184:
                    raw["player"]["hp"] = hp

            def probe(policy, snapshot, sequence, hp=hp):
                if sequence == 5184:
                    found[hp] = (threat_tiers.instant_death(policy, snapshot).holds,
                                 battle._absorbed_heal(policy, snapshot, battle._profile(policy, snapshot)))

            replay(answer_lists=lists({HEALING: {"success": 95}}), edit=edit, probe=probe, through=5184)
        self.assertEqual(found, {30: (True, None), 33: (False, "mAs")})


if __name__ == "__main__":
    unittest.main()
