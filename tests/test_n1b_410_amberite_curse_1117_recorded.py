"""The Amberites' blood curse: *Destruction* without resist curse, a prepared kill with it, recorded.

Owner 2026-11-17 (verbatim): 「魔法防御上昇の装備がないときは破壊で消す。倒すときは視界とその回りに
起きた敵が他にいなくてHPが十分のとき、加速して耐性の薬を使用して倒す。」

Recorded: tests/fixtures/n1b-410-amberite-1117.pkl.xz (tests/extract_n1b_410_amberite_1117_fixture.py):
n1-b life-410's Angband 80F board of decision #17762 (game turn 6,734,839, HP 1153/1153, hasted,
no resist_curse, the absorbed *Destruction* at 98%): アンバーの狂気の夢想家『ブランド』 awake two cells
away at 1200/5000, a sleeping グレート・ドラコリスク three away.  Live, the bot fired a Rocket
(``mB39``, ``ranged:magic-eater-device``) there and on #17763 (Brand 450/5000, the dracolisk
awake), which killed Brand; the blood curse made the player a statue and it died paralysed.

DECLARED CONSTRUCTED (each test says which): ``resist_curse`` added to the player's abilities
(the resist-curse path); the status bar given the five Resistance elements; the speed field shown
plain (haste off); the HP lowered to 500 (below the low-HP line, 853 at 1153); the absorbed
*Destruction*'s charges emptied with the player recalling (so the means-spent Recall rung does
not answer first and the use is gone).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import lzma
import pickle
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import amberite_curse, destruction_use, haste_read, resist_potion
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-410-amberite-1117.pkl.xz"
CASE = pickle.loads(lzma.decompress(FIXTURE.read_bytes()))
BRAND = 773
RESIST_CURSE = {"equipment": True, "permanent": False, "temporary": False}
BAR = [{"key": element.bar} for element in resist_potion.ELEMENTS]


def restored(which="board", *, curse=False, bar=False, plain_speed=False, hp=None,
             no_destruction=False):
    policy = restore_checkpoint_bytes(HengbotPolicy, CASE["checkpoint"])
    board = copy.deepcopy(CASE[which])
    player = board["player"]
    if curse:
        player["ability_sources"]["resist_curse"] = dict(RESIST_CURSE)
    if bar:
        player["status_bar"] = copy.deepcopy(BAR)
    if plain_speed:
        player["speed_display"] = dict(player["speed_display"], color="white")
    if hp is not None:
        player["hp"] = hp
    if no_destruction:
        player["recalling"] = True
        lists = policy._me_device_lists
        turn, rows = lists["staff"]
        emptied = tuple(dict(row, current=0) if row["name"] == "*破壊*" else row for row in rows)
        assert emptied != rows
        policy._me_device_lists = dict(lists, staff=(turn, emptied))
    return policy, parse_snapshot(board, policy._monrace_knowledge)


def brand(snapshot):
    return next(m for m in snapshot.visible_monsters if m.race_id == BRAND)


class RecordedBoardTest(unittest.TestCase):

    def test_the_recorded_board(self):
        policy, snapshot = restored()
        self.assertEqual(snapshot.turn, CASE["decision"]["turn"])
        self.assertEqual(snapshot.dungeon_level, 80)
        self.assertFalse(amberite_curse.resists_curse(snapshot))
        self.assertTrue(amberite_curse.is_amberite(policy, brand(snapshot)))
        self.assertFalse(brand(snapshot).asleep)
        self.assertTrue(destruction_use.holds_means(policy, snapshot))

    def test_destruction_instead_of_the_rocket(self):
        """#17762: no resist curse, *Destruction* usable: it is used, the Rocket is not fired."""
        for which in ("board", "next_board"):
            with self.subTest(which):
                policy, snapshot = restored(which)
                key = policy.choose_key(snapshot)
                self.assertNotEqual(key, CASE["decision"]["key"])
                # Owner 2026-11-17 「王族をT1扱い」: the T1 rules' *Destruction* (amberite-t1 tests).
                self.assertTrue(policy.last_reason.startswith(destruction_use.REASON),
                                policy.last_reason)
                self.assertEqual(amberite_curse.struck(policy, snapshot, key), [])

    def test_no_strike_without_destruction(self):
        """CONSTRUCTED: the means gone (charges emptied, recalling): nothing strikes Brand."""
        policy, snapshot = restored(no_destruction=True)
        self.assertFalse(destruction_use.holds_means(policy, snapshot))
        key = policy.choose_key(snapshot)
        self.assertEqual(amberite_curse.struck(policy, snapshot, key), [])
        # Since the T1 reading (owner 2026-11-17) the T1 leave answers before any strike is
        # decided; the gate itself is tested below on the decided Rocket.
        self.assertEqual(policy.last_reason, "no-wait:flee")

    def test_the_gate_refuses_the_rocket_without_destruction(self):
        """CONSTRUCTED as above; the gate asked directly with the recorded Rocket."""
        policy, snapshot = restored(no_destruction=True)
        policy.choose_key(snapshot)
        policy.last_reason = CASE["decision"]["reason"]
        key = amberite_curse.after_ladder(policy, snapshot, CASE["decision"]["key"])
        self.assertEqual(amberite_curse.struck(policy, snapshot, key), [])
        self.assertIn(policy.last_reason, {"threat:avoid-engagement", amberite_curse.HOLD_REASON})
        self.assertEqual(amberite_curse.report(policy)["verdict"], amberite_curse.NO_RESIST_CURSE)


class ResistCursePathTest(unittest.TestCase):
    """CONSTRUCTED: ``resist_curse`` worn.  The dracolisk sleeps on #17762's board."""

    def test_resistance_potion_before_the_strike(self):
        policy, snapshot = restored(curse=True)
        key = policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, amberite_curse.RESIST_REASON)
        self.assertTrue(key.startswith("q"), key)
        self.assertEqual(amberite_curse.report(policy)["verdict"], amberite_curse.RESISTANCE)

    def test_haste_before_the_strike(self):
        policy, snapshot = restored(curse=True, bar=True, plain_speed=True)
        key = policy.choose_key(snapshot)
        # The Magic-Eater's own FIGHT occasion (me_powers.fight_key, an earlier filter) casts the
        # absorbed Speed in the unhasted strike's place already; the gate's dose is the same.
        self.assertTrue(policy.last_reason.startswith(
            (amberite_curse.HASTE_REASON, "me-power:fight-unhasted:speed")), policy.last_reason)
        self.assertEqual(amberite_curse.struck(policy, snapshot, key), [])

    def test_the_gate_hastes_an_unhasted_strike(self):
        """The gate alone, on the decided strike (the FIGHT filter left out by asking the gate
        directly with the Rocket the ladder decides on the hasted board)."""
        policy, snapshot = restored(curse=True, bar=True, plain_speed=True)
        haste_read.observe(policy, snapshot)  # the plain field: neither haste nor slowness
        self.assertFalse(haste_read.hasted(policy, snapshot))
        policy.last_reason = CASE["decision"]["reason"]
        key = amberite_curse.after_ladder(policy, snapshot, CASE["decision"]["key"])
        self.assertTrue(policy.last_reason.startswith(amberite_curse.HASTE_REASON), policy.last_reason)
        self.assertEqual(amberite_curse.report(policy)["verdict"], amberite_curse.HASTE)
        self.assertNotEqual(key, CASE["decision"]["key"])

    def test_the_prepared_strike_is_sent(self):
        policy, snapshot = restored(curse=True, bar=True)
        self.assertTrue(resist_potion.covered(snapshot.player))
        key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason), (CASE["decision"]["key"], CASE["decision"]["reason"]))
        self.assertEqual(amberite_curse.report(policy)["verdict"], amberite_curse.PERMITTED)

    def test_another_awake_enemy_refuses_the_strike(self):
        """#17763's board: the dracolisk is awake.  Since owner 2026-11-18 「条件がそろうまで
        *破壊* で消す」 the T1 rules' *Destruction* answers before any strike is decided
        (tests/test_amberite_unmet_destruction_1118_recorded.py)."""
        policy, snapshot = restored("next_board", curse=True, bar=True)
        key = policy.choose_key(snapshot)
        self.assertEqual(amberite_curse.struck(policy, snapshot, key), [])
        self.assertTrue(policy.last_reason.startswith(destruction_use.REASON), policy.last_reason)

    def test_low_hp_refuses_the_strike(self):
        policy, snapshot = restored(curse=True, bar=True, hp=500)
        self.assertLess(500, policy._low_hp_walk_threshold(snapshot.player.max_hp))
        key = policy.choose_key(snapshot)
        self.assertEqual(amberite_curse.struck(policy, snapshot, key), [])
        report = amberite_curse.report(policy)
        if report is not None:  # a survival rung may answer the low HP before any strike
            self.assertEqual(report["verdict"], amberite_curse.HP_LOW)


class GateReaderTest(unittest.TestCase):
    """``struck`` on the recorded board, per decided key and reason."""

    def test_reader(self):
        policy, snapshot = restored()
        target = brand(snapshot)
        cases = [
            ("mB39", "ranged:magic-eater-device", [target.index]),
            ("mB39", "summoner:ranged-kill", [target.index]),
            ("v1", "ranged:throw-torch", [target.index]),
            ("R" + chr(13), "rest", []),
            ("q1", "resist-potion:quaff", []),
            ("q1", "oneshot-breath:quaff", []),   # a word rule's attack row: no strike
        ]
        for key, reason, expected in cases:
            with self.subTest(key=key, reason=reason):
                policy.last_reason = reason
                self.assertEqual([m.index for m in amberite_curse.struck(policy, snapshot, key)],
                                 expected)
        # Brand two cells away: no step reaches it.
        for key in "12346789":
            policy.last_reason = "explore"
            self.assertEqual(amberite_curse.struck(policy, snapshot, key), [])

    def test_step_into_an_adjacent_amberite(self):
        """CONSTRUCTED: Brand's state moved from (7, 72) to (8, 71), beside the player at (9, 70)
        (the reader alone: the board's grids still show it at (7, 72))."""
        policy, snapshot = restored()
        index = snapshot.visible_monsters.index(brand(snapshot))
        snapshot.visible_monsters[index] = replace(brand(snapshot), position=Position(8, 71),
                                                   distance=1)
        for reason in ("melee", "hunt", "explore"):
            policy.last_reason = reason
            self.assertEqual([m.race_id for m in amberite_curse.struck(policy, snapshot, "9")], [BRAND])
            self.assertEqual(amberite_curse.struck(policy, snapshot, "6"), [])


if __name__ == "__main__":
    unittest.main()
