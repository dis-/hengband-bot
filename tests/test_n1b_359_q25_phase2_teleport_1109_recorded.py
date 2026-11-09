"""Quest 25 phase 2 on n1-b life-359 (2026-11-09 14:23:55-14:24:03): Teleportation on stragglers, recorded.

Owner 2026-11-09 「Q25の段階2でテレポートする様子が見られた。理由を確認」.  On [5,1], firing the
absorbed balls at the Ipsissimus pen [7,17], the process read Teleportation at decision 833
(HP 384 of 506) and again at decision 927 (HP 510 of 512), reason ``quest25:teleport``.  In view
were three shadow demons (665) and a spectre (508): the wall-passers the phase-1 stand left alive
(the roster's 9 and 2, the kills read 2 and 1), not reinforcements.  The phase read any
non-Ipsissimus in view as a summons, and with the material threat (three turns of every visible
hostile at half the HP or more: 267 of 384, 261 of 510) it teleported.

The owner's rules (strategy/quests/QUEST_25.jsonc phase2): the summons -- 「召喚を受けた場合、脅威度と
こちらの攻撃手段によって対応を変える。貫通可能な攻撃かつ脅威度が高くない場合は先にイプシシマスを倒し増援を
断つ。」「それ以外の場合はテレポートで仕切り直す。接敵する前に移動できるならなるべく隘路に陣取る」, the threat
read as the 11-05 summon rule (「見えている敵の3ターンの想定被害が今の HP の半分以上なら高い」); the
stragglers -- 「イプシシマスとの戦闘中に出会った残党は無視する。イプシシマスを全て倒すかテレポートさせた
あとで対処。」 (owner 2026-11-09 again: 「無視して囲いを撃つ」), fought later on [5,1] 「[5,1]で倒す。遠近は問わない。」.
The wall-passers' wait was doubled the same day (「待つターンを倍にしてみる」, ``WallPasserWaitTest``).

The boards are the visit's 287 decided boards from the floor entry (decision 642) through 927;
each test replays them from 642 by one policy through the public ``choose_key``, the battle begun
by the real producer on the entry board (no record: the visit's first decision).  A list the policy
asks for (``b`` + kind) arrives on the next board as the executor's read of the screen
(``_magic_eater_power_list``) with the lists the process held at its town arrival (14:22:33, the
same process): DECLARED CONSTRUCTED, the charges of the recorded reads are not in the capture.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import dataclasses
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import me_powers_refresh, quest25_battle as battle, quest25_geometry as geo
from hengbot.model import _parse_items, parse_snapshot
from hengbot.policy_constants import SKILL_KNOWLEDGE_MACRO
from tests import test_q25_haunted_house as q25


with gzip.open(Path(__file__).with_name("fixtures") / "n1b-359-q25-phase2-teleport-1109.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

LETTER_KIND = {letter: kind for kind, letter in me_powers_refresh.KIND_LETTER.items()}
FIRST_TELEPORT, SECOND_TELEPORT = 833, 927


def new_policy(first, record):
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    first = copy.deepcopy(first)
    policy.prime(parse_snapshot(first, policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(CASE["skill"]), turn=first["turn"],
        player=dict(CASE["skill"]["player"], level=first["player"]["level"])))
    policy.consume_home_knowledge(tuple(_parse_items(CASE["home"]["knowledge"]["items"], protocol=3)))
    # DECLARED CONSTRUCTED: the lists this same process held at its town arrival (14:22:33), the
    # checkpoint's own ``_me_device_lists``; the process carried them in memory into the visit.
    policy._me_device_lists = {kind: (turn, tuple(rows)) for kind, (turn, rows) in CASE["lists"].items()}
    policy._q25_battle_record_path = record
    return policy


# The wall-passers' wait the recorded process ran (owner 2026-11-06 「50回来なければ終える」, doubled
# 2026-11-09 「待つターンを倍にしてみる」).
RECORDED_WALL_PASSER_WAIT = 50


def recorded_wait_phases():
    """PHASES with the wall-passers' wait the recorded process ran: DECLARED WALL, the boards after
    decision 805 were decided in the Ipsissimus phase the 50-action wait began there."""
    return tuple(dataclasses.replace(phase, wait_limit=RECORDED_WALL_PASSER_WAIT)
                 if phase.name == "wall-passers" else phase for phase in battle.PHASES)


def replay(*, edit=None, probe=None, through=None, recorded_wait=False, observed=()):
    """{sequence: (key, reason)} of the visit replayed by one policy; ``edit(sequence, raw)``
    changes a board (declared by its test), ``probe(policy, snapshot, sequence)`` reads one;
    ``recorded_wait``: the wall-passers' phase ends as the recorded process's did; ``observed``: the
    sequences only observed (``quest25_battle.observe_board``: kill lines, arrivals), not decided."""
    if recorded_wait:
        with patch.object(battle, "PHASES", recorded_wait_phases()):
            return replay(edit=edit, probe=probe, through=through, observed=observed)
    answers = {}
    with TemporaryDirectory() as directory:
        record = Path(directory) / "q25-battle.json"
        policy = new_policy(CASE["boards"][0], record)
        browsed = None
        skill_asked = False
        for raw, row in zip(CASE["boards"], CASE["recorded"]):
            if through is not None and row["sequence"] > through:
                break
            raw = copy.deepcopy(raw)
            if browsed is not None:
                raw["_magic_eater_power_list"] = {"kind": browsed, "rows": CASE["lists"][browsed][1]}
            if edit is not None:
                edit(row["sequence"], raw)
            if skill_asked:
                # The ~f list the policy asked for arrives as the CLI delivers it (cli.py).
                policy.consume_skill_knowledge(dict(
                    copy.deepcopy(CASE["skill"]), turn=raw["turn"],
                    player=dict(CASE["skill"]["player"], level=raw["player"]["level"])))
            snapshot = policy.with_known_skill_exp(parse_snapshot(raw, policy._monrace_knowledge))
            if probe is not None:
                probe(policy, snapshot, row["sequence"])
            if row["sequence"] in observed:
                battle.observe_board(policy, snapshot)
                # The recorded process's own ~f there is answered as the CLI answered it.
                skill_asked, browsed = row["key"].startswith("~f"), None
                continue
            key = str(policy.choose_key(snapshot))
            answers[row["sequence"]] = (key, policy.last_reason)
            skill_asked = key == SKILL_KNOWLEDGE_MACRO
            browsed = LETTER_KIND.get(key[1:]) if key[:1] == "b" and len(key) == 2 else None
            policy.confirm_key_posted(key)
    return answers


def recorded(sequence):
    for raw, row in zip(CASE["boards"], CASE["recorded"]):
        if row["sequence"] == sequence:
            return raw, row
    raise KeyError(sequence)


def in_view(raw):
    return sorted(monster["race_id"] for monster in raw["visible_monsters"] if not monster.get("pet"))


class RecordingTest(unittest.TestCase):

    def test_the_process_teleported_twice_on_5_1_among_wall_passers(self):
        for sequence, key, hp in ((FIRST_TELEPORT, "ri", 384), (SECOND_TELEPORT, "rh", 510)):
            raw, row = recorded(sequence)
            self.assertEqual((row["reason"], row["key"], row["hp"]), (battle.TELEPORT_REASON, key, hp))
            self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (5, 1))
            self.assertEqual(in_view(raw), [geo.SPECTRE, geo.SHADOW, geo.SHADOW, geo.SHADOW])


class PhaseTest(unittest.TestCase):
    """Which phase ran at 14:24: the wall-passers' phase ended at decision 805 after 50 quiet
    actions on [7,1] with 5 shadow demons and 1 spectre of the roster alive (kills 4 and 1), so the
    Ipsissimus phase held both boards; those six came to [5,1] later."""

    def test_the_ipsissimus_phase_held_both_boards_with_the_wall_passers_left(self):
        seen = {}

        def probe(policy, snapshot, sequence):
            ctx = battle._ctx(policy, snapshot)
            seen[sequence] = (battle.PHASES[ctx.battle.phase].name, ctx.kills(geo.SHADOW), ctx.kills(geo.SPECTRE))

        replay(probe=probe, recorded_wait=True, observed=range(816, SECOND_TELEPORT))
        self.assertEqual(seen[805], ("wall-passers", 4, 1))
        self.assertEqual(seen[806], ("ipsissimus", 4, 1))
        self.assertEqual(seen[FIRST_TELEPORT], ("ipsissimus", 4, 1))
        self.assertEqual(seen[SECOND_TELEPORT], ("ipsissimus", 4, 1))


class WallPasserWaitTest(unittest.TestCase):
    """Owner 2026-11-09 「待つターンを倍にしてみる」: the wall-passers' wait on [7,1] is 100 player
    actions without a new arrival.  The recorded process ended it at decision 805 after 50."""

    def test_decision_805_no_longer_ends_the_stage_and_the_spectre_is_met_in_it(self):
        seen = {}

        def probe(policy, snapshot, sequence):
            ctx = battle._ctx(policy, snapshot)
            seen[sequence] = (battle.PHASES[ctx.battle.phase].name, ctx.battle.quiet)

        answers = replay(probe=probe, through=813)
        self.assertEqual(recorded(805)[1]["key"], "bC")   # the Ipsissimus phase's recharge reads
        self.assertEqual(answers[805], ("5", battle.HOLD_REASON))
        self.assertEqual(seen[806], ("wall-passers", 50))
        # The spectre that came at decision 813 (14:24:00) arrives with the stage still running.
        self.assertEqual(in_view(recorded(813)[0]), [geo.SPECTRE])
        self.assertEqual(seen[813][0], "wall-passers")


class StragglersNoTeleportTest(unittest.TestCase):
    """Owner 2026-11-09 「ここでテレポートすると以降の段取りが全て崩れるので逃走回数は最小にしたい。」 and
    「無視して囲いを撃つ」: the wall-passers left alive are no summons; with them in view, even beside
    the player, the ball stays on the pen [7,17], no Teleportation.  The phase as recorded
    (``recorded_wait``)."""

    def assert_pen_shot(self, answer, sequence):
        key, reason = answer
        self.assertNotEqual(reason, battle.TELEPORT_REASON, sequence)
        self.assertTrue(key.startswith("mB") and key.endswith("@7,17"), (sequence, key))
        self.assertEqual(reason, "ranged:magic-eater-device", sequence)

    def test_833_keeps_the_ball_on_the_pen(self):
        answers = replay(recorded_wait=True, through=FIRST_TELEPORT)
        self.assert_pen_shot(answers[FIRST_TELEPORT], FIRST_TELEPORT)
        self.assertEqual([sequence for sequence, (_, reason) in answers.items()
                          if reason == battle.TELEPORT_REASON], [])

    def test_927_keeps_the_ball_on_the_pen(self):
        # DECLARED WALL: from the first shot at the pen (816) to 926 the boards are the recorded
        # process's (its fire, its teleport and walk back), which the fixed policy's keys did not
        # make: they are observed (kill lines, arrivals), not decided, so no shot of the replay is
        # answered by a board it did not make.
        answers = replay(recorded_wait=True, observed=range(816, SECOND_TELEPORT))
        self.assert_pen_shot(answers[SECOND_TELEPORT], SECOND_TELEPORT)

    def test_a_summons_with_a_low_threat_keeps_the_ball_on_the_pen(self):
        # Decision 815: 「何かが魔法でアンデッドの強敵を召喚した！」 brought the skeleton kobold (91);
        # on 816 at full HP the ball goes to [7,17] as recorded.
        raw, row = recorded(816)
        self.assertEqual(in_view(raw), [91, geo.SPECTRE])
        self.assertEqual(replay(through=816, recorded_wait=True)[816], (row["key"], row["reason"]))


class HighThreatSummonsTeleportsTest(unittest.TestCase):
    """「それ以外の場合はテレポートで仕切り直す」: a summons with the threat high (the 11-05 reading,
    three turns of every visible hostile at half the HP or more: 267 of 384 here) still teleports.
    DECLARED CONSTRUCTED: board 833 also carries a summon cast line, so the shadow demon first seen
    on it (index 12) arrives as a summons."""

    def test_the_summoned_shadow_demon_on_833_teleports(self):
        def edit(sequence, raw):
            if sequence == FIRST_TELEPORT:
                raw["messages"] = ["何かは魔法で混沌の宮廷から悪魔を召喚した！", *raw["messages"]]

        answers = replay(edit=edit, through=FIRST_TELEPORT, recorded_wait=True)
        self.assertEqual(answers[FIRST_TELEPORT], ("ri", battle.TELEPORT_REASON))


def spent(kind):
    """DECLARED CONSTRUCTED: the executor's read of ``kind``'s list with every power spent (a wand's
    count 0, a rod's every charge charging); the recorded lists were full."""
    rows = [dict(row) for row in CASE["lists"][kind][1]]
    for row in rows:
        if "current" in row:
            row["current"] = 0
        else:
            row["charging"] = row["max"]
    return {"kind": kind, "rows": rows}


class UnseenPenNoArrowTest(unittest.TestCase):
    """Owner 2026-11-09 「Q25 の全部の段に広げる」: 「見えない時は矢を撃たない。マスを狙う範囲の攻撃（取り込んだ
    ボール・ブレスなど）で削り、無ければ相手が見えるマスへ移って撃つ。」 on the pen too.  On [5,1] the pen
    [7,17] is not in view (no telepathy, no evil ESP shown); the recorded process burst its absorbed
    balls there (decisions 816-832).  With the wand list read spent on 816 and the rod list on 817
    (the real reads, ``_magic_eater_power_list``), the crossbow and its bolts are left."""

    def test_spent_balls_walk_to_a_cell_that_sees_the_pen_not_the_bolt(self):
        def edit(sequence, raw):
            if sequence in (816, 817):
                raw["_magic_eater_power_list"] = spent({816: "wand", 817: "rod"}[sequence])

        answers = replay(edit=edit, through=820, recorded_wait=True)
        self.assertEqual(answers[816][0], "mC1@7,17")           # the rod's ball, still charged
        for sequence in (817, 818, 819, 820):
            raw, row = recorded(sequence)
            self.assertEqual(((raw["player"]["y"], raw["player"]["x"]), row["key"]), ((5, 1), "mB1@7,17"))
            self.assertEqual(answers[sequence], ("6", battle.SIGHT_REASON), sequence)


if __name__ == "__main__":
    unittest.main()
