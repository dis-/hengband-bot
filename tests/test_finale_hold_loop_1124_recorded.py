"""The 99F/100F battle keeps the board: no generic rung answers on its floor (n1-c life-221,
Angband 100F, 2026-11-24 07:18, owner-halt loop-detected).

Owner (verbatim): 「99F 100Fはサーチ禁止」, 「長期戦になる99F 100Fにおいて無駄な行動は許されない」,
「可能なら相手の移動後に射線が通るようにして、先手を取ること」.  n1-c life-221 on Angband 100F (Oberon
already killed): the Serpent of Chaos shown by telepathy 3 cells away (fighting Yog-Sothoth), no stand
open and no nearer cell to close in to (STAND_MIN_DISTANCE 3); the battle answered None and
the generic explore, breakout:seek-frontier and livelock:stone-to-mud answered, alternating with
the battle's own approach between (40,52) and (41,51) until the loop detector stopped the run.

Fixture finale-hold-loop-n1c-221-1124: every player_turn board of that 100F floor from the arrival
(turns 6257708-6261238, 1494 boards, from the livelock-exhausted capture's snapshot ring
20261124-071625 and current; ``_same`` rows as tests/support/finale_416.boards expands them),
replayed open-loop (tests/support/finale_416: DECLARED RECONSTRUCTED device lists and expedition
mark; DECLARED: the expedition's Restore Mana count held at 0, as the open-loop replay counts its
own quaffs; and the Stone to Mud uses counted per wall, sealed_pocket ``worn_out``, cleared on every
board, as the open-loop replay's melts never change the recorded boards).

Owner 2026-11-24 (verbatim) 「周辺感知で状況を確認する。今回の場合は永久岩に阻まれていたので回り込む必要が
あった。」: the player stood inside a vault of permanent rock (x 49-61), the Serpent beyond its west
wall; the stands of its rays all lay outside.  The battle now takes the way around the permanent
rock (walking, melting granite) to a stand instead of stepping west against the wall.
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot import angband_finale, sealed_pocket
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

FIXTURE = "finale-hold-loop-n1c-221-1124.jsonl.gz"
FROM = 6261100   # the last minute before the halt: the Serpent 3-6 cells away
GENERIC = ("explore", "breakout:", "livelock:", "stuck:", "quest-search:")


class FinaleHoldLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

        def prepare(policy, board):
            angband_finale.memory(policy).restore_mana_used = 0
            sealed_pocket._memory(policy, board).uses.clear()

        rows = finale_416.drive(finale_416.boards(FIXTURE), monrace, prepare=prepare)
        cls.rows = [row for row in rows if row[0] >= FROM]

    def test_no_generic_rung_answers_while_the_target_is_shown(self):
        generic = [row for row in self.rows
                   if row[6] is not None and (row[3] or "").startswith(GENERIC)]
        self.assertEqual(generic, [], self.rows)

    def test_every_board_is_answered_by_the_battle(self):
        foreign = [row for row in self.rows if row[6] is not None
                   and not (row[3] or "").startswith(("angband-finale", "ranged:magic-eater",
                                                       "emergency:destruction:angband-finale",
                                                       "me-power:after-destruction"))]
        self.assertEqual(foreign, [], self.rows)

    def test_the_way_around_the_permanent_rock_not_west_against_it(self):
        # (40,52) / (41,51): the recorded run alternated '1' / '4' / '7' west against the vault's
        # permanent wall with the generic explore stepping back; the battle walks around instead.
        west = [row for row in self.rows if row[0] >= 6261200 and row[1] in ((40, 52), (41, 51))
                and row[2] in ("1", "4", "7")]
        self.assertEqual(west, [], self.rows)
        self.assertEqual([row for row in self.rows if row[0] >= 6261200
                          and row[3] == "angband-finale:hold"], [], self.rows)


if __name__ == "__main__":
    unittest.main()
