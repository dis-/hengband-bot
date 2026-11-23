"""The last boards of n1-b life-416's death on Angband 100F choose the teleport (2026-11-24 05:24),
and the walk before them keeps out of the Tarrasque's line of fire (owner 2026-11-24).

Owner 2026-11-20 (verbatim) 「召喚または攻撃を受けてHPが800を下回ったとき、または対象が距離2より近づいた
ときテレポートの巻物で離脱する。」 and (verbatim) 「ターゲットとターゲット以外が同時に射線に入っているときは
召喚直後でなくとも離脱する。」  n1-b life-416 at (9,26), the Serpent of Chaos (9,42-44) and the Tarrasque
(9,39-40) in view on row 9, no Teleportation scroll left (the absorbed Staff of Teleportation in hand):

* 4781291 HP 83 (999 before: the Tarrasque's cold and disenchantment breaths): *Healing* -> 1078.
* 4781293-4781297: Stone to Mud east from the stand, three times; the beam reached both
  (「『タラスク』はダメージを受けていない。」「『混沌のサーペント』はダメージを受けていない。」).
* 4781299 HP 210: *Healing*.  4781302 HP 537 (the Tarrasque's cold breath in the same turn), no
  teleport (the board read no HP drop, 210 -> 537): Stone to Mud.  4781304: Stone to Mud, dead.

Fixture finale-serpent-death-n1b-416-1124 (tests/extract_finale_serpent_death_1124_fixture.py): the
whole 100F floor, turns 4775263-4781304 (2724 boards), replayed open-loop (tests/support/finale_416:
DECLARED RECONSTRUCTED device lists and expedition mark).  DECLARED: the expedition's Restore Mana
count is held at 0 on every board -- the open-loop replay counts each of its own quaffs, the
recorded boards never show them drunk, and the count would read the recall of 「魔力復活の薬を予定の倍
以上使ったとき」 (the recorded run had used 13).  With that, the replay of the old code chooses the
recorded keys of the last boards (star-healing, three melts, star-healing, melt, melt).
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot import angband_finale, angband_finale_battle
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

FIXTURE = "finale-serpent-death-n1b-416-1124.jsonl.gz"
SENSED_LINE = 4781286  # seq 1212: at (10,24), the Tarrasque known by telepathy alone at (9,40)
INTO_LINE = 4781288  # seq 1214: at (9,25), the Serpent unseen, the Tarrasque in view at (9,40)
FIRST_HEAL = 4781291
IN_VIEW = 4781293   # HP 1078, both in view on row 9, a stale remembered wall at (9,38)-(9,39)
REHEALED = 4781302   # HP 537 after *Healing* at 210 and the Tarrasque's breath in that turn
END = 4781304


class FinaleSerpentDeathRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.attacked = {}
        previous = []

        def prepare(policy, board):
            angband_finale.memory(policy).restore_mana_used = 0
            held = getattr(policy, angband_finale_battle.MEMORY, None)
            if previous and held is not None:
                cls.attacked[previous[-1]] = held.attacked
            previous.append(board.turn)

        rows = finale_416.drive(finale_416.boards(FIXTURE), monrace, prepare=prepare)
        cls.rows = {row[0]: row for row in rows if row[0] >= FIRST_HEAL - 20}

    def test_the_approach_does_not_step_into_the_sensed_tarrasque_line(self):
        # The same rule for the Tarrasque known by telepathy alone: the memory's stale walls at
        # (9,38)-(9,39) (the board no longer shows them) do not close its line to (9,25), so the
        # recorded '9' from (10,24) into it is not stepped.
        row = self.rows[SENSED_LINE]
        self.assertEqual(row[1], (10, 24), self.rows)
        self.assertNotEqual(row[2], "9", self.rows)

    def test_the_approach_does_not_step_into_the_tarrasque_line(self):
        # Owner 2026-11-24 (verbatim) 「射線を通す近づき方をしたのが悪い。射線を通さないように近づくないし
        # 待つのがただしい」: the recorded walk stepped '6' along row 9 into the Tarrasque's line (its
        # breaths: 999 -> 83).  The walk keeps out of it (here (9,25) is in it: out of the line).
        row = self.rows[INTO_LINE]
        self.assertEqual(row[1], (9, 25), self.rows)
        self.assertNotEqual(row[2], "6", self.rows)
        self.assertEqual(row[3], angband_finale_battle.OUT_OF_LINE_REASON, self.rows)

    def test_the_first_star_healing_is_kept(self):
        # HP 83 after a hit: the *Healing* line (below 400) answers first, as recorded.
        self.assertEqual(self.rows[FIRST_HEAL][3], angband_finale_battle.STAR_HEAL_REASON,
                         self.rows)

    def test_below_800_after_the_healing_turn_teleports(self):
        # 210 -> *Healing* -> 537: this board shows no HP drop, the attack below 800 still holds.
        row = self.rows[REHEALED]
        self.assertFalse(self.attacked[REHEALED], self.rows)
        self.assertTrue(row[3].startswith(angband_finale_battle.TELEPORT_REASON), self.rows)

    def test_target_and_another_in_view_on_the_line_teleport(self):
        # 「ターゲットとターゲット以外が同時に射線に入っているとき」: the Serpent and the Tarrasque in
        # view on row 9 (the game's line of sight); the memory's walls between are stale.
        self.assertTrue(self.rows[IN_VIEW][3].startswith(angband_finale_battle.TELEPORT_REASON),
                        self.rows)

    def test_no_stone_to_mud_while_both_breathe_on_the_line(self):
        melts = [row for turn, row in self.rows.items() if IN_VIEW <= turn <= END
                 and row[3].startswith(angband_finale_battle.MELT_REASON)]
        self.assertEqual(melts, [], self.rows)


if __name__ == "__main__":
    unittest.main()
