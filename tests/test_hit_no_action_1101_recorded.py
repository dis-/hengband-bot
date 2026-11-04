"""#47 (owner 2026-11-01 「life85は無抵抗で攻撃を受け続けているのも気になる。他に不具合がないか確認。」).

The life085-passive-1101 audit left two survival paths that take hits
without a useful answer; both are built here from the recorded n1-c life-085
boards (Lv18 zombie Magic-Eater, 236 max HP, 迷宮11階; the jelly
『スーパー・グレート・シルバー・ゼリー』 @(8,6) touches the player @(9,6)).

* An unseen attacker hits in melee above the low-HP walk gate's threshold
  (118): the lethal-emergency ladder ended in a wait and the wait-while-damaged
  rewrite walked to the least-visited cell (``no-wait:least-visited``).  The
  counterattack of USER DECISION 2026-10-03 追加決定2 (「近接で敵の方向が分から
  なければランダムな方向に攻撃。」) answered only below the threshold.
* Afraid beside the jelly: the low-HP walk gate (and the other combat rungs)
  tried the ranged order (me_ranged_first) only inside their unafraid melee
  branch and waited (``emergency:wait``), although fear refuses melee only
  (cmd-attack.cpp:228; cmd-magiceat.cpp:492 checks confusion).

Fixture: tests/fixtures/death-n1c-085-1101.json.gz (the D57 extraction).
Every decision is the public ``choose_key``; posted keys go through the
production executor port (test_n1c_deaths_1101_recorded.PostedDeathKey).
DECLARED RECONSTRUCTED: the staff record and the lamp memory as in
test_n1c_deaths_1101_recorded.
DECLARED CONSTRUCTED: the oil flasks and the spare lantern are out of the pack
(as in test_life085_passive_recorded, so no light recovery answers first); for
the unseen case the jelly is out of the visible list and its name in the
messages is the game's hidden actor 「何か」 (monster-attack-player.cpp:298-304,
monster-describer.cpp), and the HP is 225 then 130 (one blow of 95 >= 40% of
the maximum, above the gate's threshold); for the afraid case the player's
status ``afraid`` is set on the recorded boards (recorded HP 80 then 71), as
each case states.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot.magic_eater import MISSILE_REASON
from hengbot.model import parse_snapshot
from tests import test_n1c_deaths_1101_recorded as d57


TVAL_LIGHT, TVAL_FLASK = 39, 77
JELLY_NAME = "『スーパー・グレート・シルバー・ゼリー』"
STRIKE_FROM, STRIKE_AT = 1445613, d57.JELLY_WAIT_TURN


def constructed(raw, *, hp=None, unseen=False, afraid=False):
    raw = copy.deepcopy(raw)
    raw["player"]["status"]["afraid"] = afraid
    raw["inventory"] = [item for item in raw["inventory"]
                        if item["tval"] not in (TVAL_LIGHT, TVAL_FLASK)]
    if hp is not None:
        raw["player"]["hp"] = hp
    if unseen:
        raw["visible_monsters"] = [m for m in raw["visible_monsters"]
                                   if m["race_id"] != d57.JELLY]
        raw["messages"] = [m.replace(JELLY_NAME, "何か") for m in raw["messages"]]
    return raw


class UnseenAttackerStrikeRecordedTest(d57.PostedDeathKey):
    """Hit by an attacker the player cannot see: strike back, do not walk."""

    def drive_unseen(self, hps, speed=True):
        rows = [constructed(raw, hp=hp, unseen=True)
                for raw, hp in zip(d57.boards(d57.CASE_085, STRIKE_FROM, STRIKE_AT), hps)]
        if not speed:  # DECLARED CONSTRUCTED: the Potions of Speed taken out of the pack
            for raw in rows:
                raw["inventory"] = [item for item in raw["inventory"]
                                    if item["name"] != d57.SPEED_POTION]
        policy = d57.lamp_policy()
        raw, key, reason = self.drive(policy, rows)[-1]
        self.assertEqual(raw["turn"], STRIKE_AT)
        return policy, raw, key, reason

    def test_constructed_board_is_an_unseen_melee_hit(self):
        self.assertEqual(d57.recorded(d57.CASE_085)[STRIKE_AT], ("emergency:wait", "5"))
        raw = constructed(next(r for r in d57.CASE_085["boards"] if r["turn"] == STRIKE_AT),
                          unseen=True)
        self.assertEqual(raw["visible_monsters"], [])
        self.assertIn("何かに触られた。", raw["messages"])
        board = parse_snapshot(raw, d57.new_policy(d57.CASE_085)._monrace_knowledge)
        self.assertEqual((board.player.blind, board.player.afraid), (False, False))
        self.assertEqual(board.light_radius, 0)  # the scrolls cannot be read

    def test_unseen_attacker_above_the_gate_threshold_is_struck_not_walked_from(self):
        policy, raw, key, reason = self.drive_unseen((225, 130))
        self.assertGreater(raw["player"]["hp"],
                           policy._low_hp_walk_threshold(raw["player"]["max_hp"]))
        # Unfixed: ('2', 'no-wait:least-visited'), a step away from the jelly.
        self.assertEqual(key[0], "+", (key, reason))
        self.assertTrue(reason.endswith("emergency:unseen-strike"), (key, reason))

    def test_control_below_the_gate_threshold_the_gate_strikes(self):
        # The recorded HP (80, 71).  The pack carries Speed: the dose comes first
        # (owner 2026-11-03 「必要なら加速や体力回復など危険度に応じて物資を使用すること」,
        # 8bef5c9db and 5947219765).
        _policy, _raw, key, reason = self.drive_unseen((80, 71))
        self.assertEqual(key[0], "q", (key, reason))
        self.assertTrue(reason.endswith("unseen:quaff-speed"), (key, reason))
        # Without it the low-HP walk gate strikes.
        _policy, _raw, key, reason = self.drive_unseen((80, 71), speed=False)
        self.assertEqual(key[0], "+", (key, reason))


class AfraidRangedAnswerRecordedTest(d57.PostedDeathKey):
    """Afraid beside the jelly: the ranged order answers, melee does not."""

    def drive_afraid(self, *, afraid=True):
        rows = [constructed(raw, afraid=afraid)
                for raw in d57.boards(d57.CASE_085, STRIKE_FROM, STRIKE_AT)]
        raw, key, reason = self.drive(d57.lamp_policy(), rows)[-1]
        self.assertEqual(raw["turn"], STRIKE_AT)
        return raw, key, reason

    def test_afraid_low_hp_gate_fires_at_the_adjacent_jelly(self):
        raw, key, reason = self.drive_afraid()
        self.assertTrue(raw["player"]["status"]["afraid"])
        self.assertEqual([(m["race_id"], m["y"], m["x"]) for m in raw["visible_monsters"]],
                         [(d57.JELLY, 8, 6)])
        # Unfixed: ('5', 'emergency:wait'), the recorded death's wait.
        self.assertEqual((key, reason), ("mBp8", MISSILE_REASON))

    def test_control_unafraid_the_jelly_is_answered_too(self):
        _raw, key, reason = self.drive_afraid(afraid=False)
        self.assertNotEqual(key, "5", reason)
        # An attack toward the jelly (north), or, since the dark walk yields to
        # an unafraid fight (survival_preemption, life085-passive-1101), the
        # lethal ladder's Speed potion before it -- as the D57 check accepts.
        self.assertTrue(key[-1] == "8" or reason.endswith("emergency:quaff-speed"),
                        (key, reason))


if __name__ == "__main__":
    unittest.main()
