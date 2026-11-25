"""The 99F/100F battle keeps the board: no generic rung answers on its floor (n1-c life-221,
Angband 100F, 2026-11-24 07:18, owner-halt loop-detected).

Owner (verbatim): 「99F 100Fはサーチ禁止」, 「長期戦になる99F 100Fにおいて無駄な行動は許されない」,
「可能なら相手の移動後に射線が通るようにして、先手を取ること」.  n1-c life-221 on Angband 100F (Oberon
already killed): the Serpent of Chaos shown by telepathy 3 cells away (fighting Yog-Sothoth), no stand
open and no nearer cell to close in to (STAND_MIN_DISTANCE 3); the battle answered None and
the generic explore, breakout:seek-frontier and livelock:stone-to-mud answered, alternating with
the battle's own approach between (40,52) and (41,51) until the loop detector stopped the run.

Fixture finale-stand-pingpong-n1c-221-1124: every player_turn board of that 100F floor from the
arrival to the fourth halt (turns 6257708-6266122, 3555 boards: the livelock-exhausted capture's
snapshot ring 20261124-071625 and current up to 6261238, then the 08:51 capture's current ring to
6264262, the 09:55 capture's from the restart to 6264762, then the 10:30 capture's (livelock-
exhausted) from the second restart;
``_same`` rows as tests/support/finale_416.boards expands them),
replayed open-loop (tests/support/finale_416: DECLARED RECONSTRUCTED device lists and expedition
mark; DECLARED: the expedition's Restore Mana count held at 0, as the open-loop replay counts its
own quaffs; and the Stone to Mud uses counted per wall, sealed_pocket ``worn_out``, and the battle's
last melt, ``Battle.melt_aim`` (so no melt is read as one that changed nothing), cleared on every
board, as the open-loop replay's melts never change the recorded boards).

Owner 2026-11-24 (verbatim) 「周辺感知で状況を確認する。今回の場合は永久岩に阻まれていたので回り込む必要が
あった。」: the player stood inside a vault of permanent rock (x 49-61), the Serpent beyond its west
wall; the stands of its rays all lay outside.  The battle now takes the way around the permanent
rock (walking, melting granite) to a stand instead of stepping west against the wall.

The second halt (2026-11-24 08:51:57, stationary:exhausted:angband-finale:hold): at (29,60), the
Serpent at (29,48) with a Cyberdemon (a strong non-target) beside it, the three stands south of
the Serpent (42-44,48) were out of every non-target's line, but every walker's veto (policy
``_walk_veto``: 1156 cells of the strong monsters' engagement areas) left no way to them and the
battle held 120 boards.  The battle's walks now keep off only the left cells (``_battle_veto``);
the owner's rule for the non-targets on 99F/100F is their line of fire.
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot import angband_finale, angband_finale_battle, sealed_pocket
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

FIXTURE = "finale-stand-pingpong-n1c-221-1124.jsonl.gz"
RESTART = 2768   # the boards before the 09:54 restart (the second halt's last board, 6264262)
RESTART_2 = 2988  # the boards before the 10:2x restart (the third halt's last board, 6264762)
PINGPONG = (6266083, 6266122)  # the fourth halt's alternation (10:30:21-22)
FROM = 6261100   # the last minute before the first halt: the Serpent 3-6 cells away
FIRST_HALT = 6261238
HELD = 6263495   # the second halt's hold at (29,60) began here (to 6264262)
GENERIC = ("explore", "breakout:", "livelock:", "stuck:", "quest-search:")


class FinaleHoldLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

        reports = {}
        seen = []

        def prepare(policy, board):
            angband_finale.memory(policy).restore_mana_used = 0
            sealed_pocket._memory(policy, board).uses.clear()
            held = getattr(policy, angband_finale_battle.MEMORY, None)
            if held is not None:
                held.melt_aim = None  # as the uses: the replay's melts change nothing
                if (held.phase == angband_finale_battle.RECOVER
                        and policy.last_reason == angband_finale_battle.ABSORBED_HEAL_REASON):
                    # DECLARED: the recovery's heal to the full HP (owner 2026-11-26) lands; the
                    # open-loop boards never show it, so the replay ends the recovery as the
                    # closed loop's next board would.
                    held.phase = angband_finale_battle.BATTLE
            if len(seen) in (RESTART, RESTART_2):
                # DECLARED: the 09:54 and 10:2x restarts -- the policy's map memory (the remembered grids
                # merged under the board, ``_with_grid_memory``) is not kept by a restart.
                policy._remembered_grids = {}
                policy._remembered_grid_signatures = {}
                policy._remembered_grid_sources = {}
            seen.append(board.turn)
            reports.setdefault(board.turn, angband_finale_battle.report(policy))

        rows = finale_416.drive(finale_416.boards(FIXTURE), monrace, prepare=prepare)
        cls.rows = [row for row in rows if FROM <= row[0] <= FIRST_HALT]
        cls.held = [row for row in rows[:RESTART] if row[0] >= HELD]
        cls.restarted = rows[RESTART:RESTART_2]
        cls.pingpong = [row for row in rows[RESTART_2:] if PINGPONG[0] <= row[0] <= PINGPONG[1]]
        cls.reports = reports

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

    def test_the_way_to_the_stands_south_of_the_serpent_is_taken(self):
        # The first boards of the recorded hold: the way around ('8', north out of the cell
        # toward (44,48)).  The replay is open-loop -- the recorded boards never show the step
        # made -- so only the boards before the walk's own refusal of a step that never lands
        # are pinned (past them the replay's own refusals hold it, up to the bound).
        first = self.held[:10]
        self.assertTrue(all(row[1] == (29, 60) for row in first), first)
        self.assertTrue(all(row[3].startswith(("angband-finale:stand-walk", "angband-finale:melt"))
                            for row in first), first)

    def test_the_record_names_the_shunned_and_why_no_stand(self):
        battle = self.reports[HELD]["battle"]
        self.assertIn("shunned", battle)
        self.assertIn("no_stand", battle)
        self.assertTrue(any(entry[0] == "サイバーデーモン" for entry in battle["shunned"]), battle)

    def test_after_the_restart_the_map_then_the_way_not_the_hold(self):
        # n1-c life-221 2026-11-24 09:55 (stationary:exhausted again): after the restart the
        # board showed no stand on any ray (no_stand "rays=0 ... reach=4") and the battle held 213
        # boards.  Owner 2026-11-24 「周辺感知で状況を確認する。…回り込む必要があった。」: the map once
        # on the cell, then the way toward the rays' unshown cells.
        # The replay is open-loop: the map's result never shows on the recorded boards, and the
        # restart's first boards repeat one game turn (the walk reads a step that did not land), so
        # holds stay between; what is pinned is the map, then the way.
        first = self.restarted[:20]
        mapped = next((n for n, row in enumerate(first) if "map-area" in (row[3] or "")), None)
        self.assertIsNotNone(mapped, first)
        self.assertTrue(any((row[3] or "").startswith(("angband-finale:stand-walk",
                                                         "angband-finale:melt"))
                            for row in first[mapped:]), first)

    def test_the_held_stand_owns_the_walk_while_the_target_is_unseen(self):
        # n1-c life-221 2026-11-24 10:30 (loop-detected): the stand (35,52) walk stepped '1' from
        # (26,32) to (27,31), 21 cells from the Serpent (beyond telepathy's 20), and the walk to
        # its last-seen cell stepped '9' back; the two walkers took turns.  The stand keeps the
        # walk: no angband-finale:approach on those boards.
        approach = [row for row in self.pingpong if row[3] == "angband-finale:approach"]
        self.assertEqual(approach, [], self.pingpong)
        unseen = [row for row in self.pingpong if row[6] is None]
        self.assertTrue(unseen, self.pingpong)
        self.assertTrue(all(row[3].startswith(("angband-finale:stand-walk", "angband-finale:melt",
                                               "angband-finale:hold"))
                            for row in unseen), unseen)


if __name__ == "__main__":
    unittest.main()
