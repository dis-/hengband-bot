"""Recorded replay of the owner's answers to summons (2026-11-04), n1-a life-475 (城49階).

Source: tests/fixtures/summon-response-n1a-475-1104.json.gz
(tests/extract_summon_response_1104_fixture.py).  Each span starts its own policy, so
the floor visit's count starts at the span's first board; a test says when it edits a
board (DECLARED CONSTRUCTED).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import summon_response
from hengbot.model import parse_snapshot
from tests import test_n1c_deaths_1101_recorded as d57
from tests.test_me_nokey_1031_recorded import PostedKey


FIXTURE = Path(__file__).with_name("fixtures") / "summon-response-n1a-475-1104.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

WORSHIPPER_SPAN = (2033705, 2033737)
LAST_FIGHT_SPAN = (2038849, 2039200)
WORSHIPPER = "悪魔崇拝者"
# 悪魔崇拝者 casts for the third time in view, its summoned monster beside the player.
CASTER_PAST_THE_ADJACENT = 2033730
# <ナーグル>の疫病人間 casts behind the bodies around the player.
CASTER_BEHIND_BODIES = 2038996
BOOK_MESSAGE = "Lv1 自然の魔法書[野性の召喚]を自動破壊します。"


def boards_of(span):
    return [copy.deepcopy(raw) for raw in CASE["boards"] if span[0] <= raw["turn"] <= span[1]]


def replay(span, *, until, change=None, between=None):
    """The policy and answer on the board of ``until``; ``change`` edits that board."""
    boards = boards_of(span)
    policy = d57.loops.new_policy(dict(CASE, boards=boards), CASE["skill"], monraces=CASE["monraces"])
    for raw in boards:
        if raw["turn"] == until and change is not None:
            change(raw)
        key = d57.loops.decide(policy, raw)
        if raw["turn"] == until:
            return policy, raw, key
        policy.confirm_key_posted(key)
    raise AssertionError(until)


def aimed_monster(raw, key):
    """The monster on the cell the ``*p<digits>t`` cursor of a shot names."""
    cursor = key[key.index("p") + 1:key.index("t")]
    y, x = raw["player"]["y"], raw["player"]["x"]
    for digit in cursor:
        y += {"7": -1, "8": -1, "9": -1, "1": 1, "2": 1, "3": 1}.get(digit, 0)
        x += {"7": -1, "4": -1, "1": -1, "9": 1, "6": 1, "3": 1}.get(digit, 0)
    return next(m for m in raw["visible_monsters"] if (m["y"], m["x"]) == (y, x))


class RecognitionTest(unittest.TestCase):
    def casters(self, message):
        return [summon.caster for summon in summon_response.summons_of(message)]

    def test_the_game_strings_in_both_languages(self):
        for message, caster in (
                ("『ウートガルザ・ロキ』が魔法で手下を召喚した。", "『ウートガルザ・ロキ』"),
                ("悪魔崇拝者は魔法で混沌の宮廷から悪魔を召喚した！", "悪魔崇拝者"),
                ("何かが魔法でアリを召喚した。", "何か"),
                ("The Illusionist magically summons help!", "The Illusionist"),
                ("It magically summons a demon from the Courts of Chaos!", "It")):
            self.assertEqual(self.casters(message), [caster], message)
        self.assertFalse(summon_response.summons_of("何かが魔法でアリを召喚した。")[0].seen)

    def test_the_repeat_counter_counts_each_cast(self):
        self.assertEqual(self.casters("何かが魔法で仲間を召喚した！ <x2>"), ["何か", "何か"])

    def test_items_and_the_players_own_summons_are_no_cast(self):
        for message in (BOOK_MESSAGE, "Lv1 トランプの魔法書[召喚と奇術]を自動破壊します。",
                        "仲間を召喚した。", "You summon help.", "何かが何かをつぶやいた。"):
            self.assertEqual(self.casters(message), [], message)


class CasterShotTest(PostedKey):
    def test_the_caster_is_aimed_past_the_summoned_monster_beside_the_player(self):
        policy, raw, key = replay(WORSHIPPER_SPAN, until=CASTER_PAST_THE_ADJACENT)
        here = raw["player"]
        self.assertTrue(any(max(abs(m["y"] - here["y"]), abs(m["x"] - here["x"])) <= 1
                            for m in raw["visible_monsters"]))
        self.assertEqual(policy.last_reason, summon_response.CASTER_SHOT_REASON)
        self.assertEqual(aimed_monster(raw, key)["name"], WORSHIPPER)
        self.post(policy, raw, key)

    def test_a_blocked_bolt_path_falls_through(self):
        policy, _raw, _key = replay(LAST_FIGHT_SPAN, until=CASTER_BEHIND_BODIES)
        self.assertNotEqual(policy.last_reason, summon_response.CASTER_SHOT_REASON)

    def test_blindness_and_confusion_refuse_the_shot(self):
        # DECLARED CONSTRUCTED: the recorded board with the status set.
        for status in ("blind", "confused"):
            def change(raw, status=status):
                raw["player"]["status"][status] = True
            policy, _raw, key = replay(WORSHIPPER_SPAN, until=CASTER_PAST_THE_ADJACENT, change=change)
            self.assertNotEqual(policy.last_reason, summon_response.CASTER_SHOT_REASON, status)
            self.assertFalse(key.startswith("f"), status)

    def test_fear_does_not_refuse_the_shot(self):
        # DECLARED CONSTRUCTED: the recorded board with fear set.
        def change(raw):
            raw["player"]["status"]["afraid"] = True
        policy, raw, key = replay(WORSHIPPER_SPAN, until=CASTER_PAST_THE_ADJACENT, change=change)
        self.assertEqual(policy.last_reason, summon_response.CASTER_SHOT_REASON)
        self.assertEqual(aimed_monster(raw, key)["name"], WORSHIPPER)

    def test_a_magic_eater_device_counts(self):
        # DECLARED CONSTRUCTED: a Magic-Eater with its Magic Missile; the caster stands
        # two cells away on a clear ray, the summoned monster beside the player elsewhere.
        def change(raw):
            raw["player"]["class_id"] = 16
            raw["magic_eater_wand_charges"] = 5
            here = raw["player"]
            caster = next(m for m in raw["visible_monsters"] if m["name"] == WORSHIPPER)
            caster["y"], caster["x"] = self.clear_cell_two_away(raw)
            caster["index"] = 9999  # off the grid map, so the exported cell is its position
            self.assertEqual(max(abs(caster["y"] - here["y"]), abs(caster["x"] - here["x"])), 2)
        policy, _raw, key = replay(WORSHIPPER_SPAN, until=CASTER_PAST_THE_ADJACENT, change=change)
        self.assertEqual(key[:3], "mBp", policy.last_reason)

    @staticmethod
    def clear_cell_two_away(raw):
        board = parse_snapshot(copy.deepcopy(raw), d57.loops.new_policy(CASE, CASE["skill"], monraces=CASE["monraces"])._monrace_knowledge)
        here = board.player.position
        occupied = {(m["y"], m["x"]) for m in raw["visible_monsters"] if m["name"] != WORSHIPPER}
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            cells = [type(here)(here.y + dy * i, here.x + dx * i) for i in (1, 2)]
            if all(board.grid_at(cell) is not None and board.grid_at(cell).passable
                   and (cell.y, cell.x) not in occupied for cell in cells):
                return cells[1].y, cells[1].x
        raise AssertionError("no clear ray")


if __name__ == "__main__":
    unittest.main()
