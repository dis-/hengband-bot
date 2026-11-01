"""D57 follow-up (#47, owner 2026-11-01 「life85は無抵抗で攻撃を受け続けているのも気になる。」).

n1-c life-085 (Lv18 zombie Magic-Eater, 迷宮11階): from turn 1445339 the
worn unidentified 真鍮のランタン {並, Q34} was drained dark by
『スーパー・グレート・シルバー・ゼリー』 (race 1273, speed +10, EAT_LITE), which
stayed beside the player.  With the D57 fixes on main the jelly is on the
board and the five flasks refill the lamp.  Two roots remain once the oil is
gone (the jelly drains a refill within about two turns):

* the dark walk (``_dark_locomotion_key``) is consulted above the combat
  rungs and stepped away from the adjacent jelly, which followed and touched
  on (recorded: twenty ``dark:backtrack`` / ``no-wait:least-visited`` steps,
  HP 215 -> 80);
* the carried 長持ちの真鍮のランタン (identified, 15000 turns of fuel) was never
  worn: ``_light_to_wield`` only replaces a worn light whose fuel it knows is
  low, and the drained lantern was unidentified (its fuel hidden) although
  the player saw it no longer light them.

Fixture: tests/fixtures/death-n1c-085-1101.json.gz (the D57 extraction).
Every decision is the public ``choose_key``; posted keys go through the
production executor port (test_n1c_deaths_1101_recorded.PostedDeathKey).
DECLARED RECONSTRUCTED: the staff record and the lamp memory as in
test_n1c_deaths_1101_recorded.  DECLARED CONSTRUCTED: the oil flasks (all
poured) and, for the walk case, the spare lantern are taken out of the pack.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot.model import parse_snapshot
from tests import test_n1c_deaths_1101_recorded as d57


TVAL_LIGHT, TVAL_FLASK = 39, 77
FIRST_LIT, DARK_TURN = 1445315, d57.DARK_TURN


def without(raw, *tvals):
    raw = copy.deepcopy(raw)
    raw["inventory"] = [item for item in raw["inventory"] if item["tval"] not in tvals]
    return raw


class Life085PassiveRecordedTest(d57.PostedDeathKey):
    def dark_answer(self, *tvals):
        rows = [without(raw, *tvals) for raw in d57.boards(d57.CASE_085, FIRST_LIT, DARK_TURN)]
        raw, key, reason = self.drive(d57.lamp_policy(), rows)[-1]
        self.assertEqual(raw["turn"], DARK_TURN)
        return raw, key, reason

    def test_recorded_rows(self):
        rows = d57.recorded(d57.CASE_085)
        self.assertEqual(rows[DARK_TURN], ("dark:no-recovery:dark:backtrack", "7"))
        dark = next(raw for raw in d57.CASE_085["boards"] if raw["turn"] == DARK_TURN)
        board = parse_snapshot(copy.deepcopy(dark), d57.new_policy(d57.CASE_085)._monrace_knowledge)
        spare = [item for item in board.inventory if item.is_light]
        self.assertEqual([(item.is_lantern, item.known, item.fuel) for item in spare],
                         [(True, True, 15000)])
        worn = next(item for item in board.equipment if item.is_light)
        self.assertTrue(worn.is_lantern and not worn.known)
        self.assertEqual(board.light_radius, 0)
        self.assertEqual([(m["race_id"], m["y"], m["x"]) for m in dark["visible_monsters"]],
                         [(d57.JELLY, 12, 4)])
        self.assertEqual((dark["player"]["y"], dark["player"]["x"]), (13, 4))

    def test_without_light_the_adjacent_jelly_is_fought_not_walked_from(self):
        _raw, key, reason = self.dark_answer(TVAL_FLASK, TVAL_LIGHT)
        # Unfixed: ('7', 'dark:no-recovery:dark:backtrack'), a step away.
        self.assertNotIn("dark:backtrack", reason)
        self.assertEqual(key[-1], "8", (key, reason))  # the jelly is north

    def test_the_drained_lantern_gives_way_to_the_carried_fueled_lantern(self):
        raw, key, reason = self.dark_answer(TVAL_FLASK)
        spare = next(item for item in raw["inventory"] if item["tval"] == TVAL_LIGHT)
        # Unfixed: no recovery (the walk, or the attack once the walk yields).
        self.assertEqual((key, reason), ("w" + spare["slot"], "wield-light"))

    def test_control_with_oil_the_lamp_is_refilled(self):
        _raw, key, reason = self.dark_answer()
        self.assertEqual((key, reason), ("\\Fa", "refill-light"))


if __name__ == "__main__":
    unittest.main()
