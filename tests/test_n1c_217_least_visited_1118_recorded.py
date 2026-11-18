"""n1-c life-217's loop stop on Orc cave 20F (2026-11-18 15:09, build bot-9a3390b4e).

Live (Magic-Eater Lv26, no resist_conf, a Teleportation scroll carried): 混沌の獣人 (race 318:
a CONFUSE blow, TPORT, no RES_TELE, MonraceDefinitions.jsonc) came beside the player at (28,118).
The status-threat rung (ladder_combat) took one retreat step ('9', status-threat:retreat); the
beastman followed.  Beside it the rung found no retreat step, and the scroll is no escape there:
``teleport_player`` brings every awake TPORT monster of the 3x3 along
(spell-kind/spells-teleport.cpp, teleport_follower), so ``_escape_scroll`` answered None (owner
2026-11-09 「*破壊*>テレポートアウェイ>戦闘」).  The rung then answered WAIT (status-threat:wait),
which the damaged-wait rewrite (policy_combat ``_forbid_wait_while_damaged``) refused and
replaced by its least-visited step: '2' to (28,118) and '8' back to (27,118), the beastman beside
the player on every board, a Cure Critical Wounds drunk whenever its blow confused, until the
loop detector stopped the bot.

Fixes:
- the rung answers the rest of the owner's order beside a follower, as the emergency ladder does:
  Teleport Other at it, then the fight (``status-threat:cornered-attack``);
- the pingpong guard (owner 2026-11-13 part 2) reads the decision's emitted key: it read the
  ladder's WAIT (``_break_livelock``'s ``_last_move_key``), so every rewritten step looked like no
  walk and the alternation was never seen.

Recorded: tests/fixtures/n1c-217-least-visited-1118.jsonl.gz
(tests/extract_n1c_217_least_visited_1118_fixture.py), the boards of player turns 1194146-1194267
and the decision recorded on each, replayed through the public choose_key.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import ladder_combat, pingpong_guard
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-least-visited-1118.jsonl.gz"
FIXTURE_SHA256 = "51d788a0e038c7b683340c76bd4247fee1a66ff3f500ae687acc8d2424c79bcf"
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
BEASTMAN = 318
RETREAT = 1194156      # status-threat:retreat '9' to (27,118); the beastman follows
FIRST_REWRITE = 1194170
GUARD_WINDOW = 1194212  # the second round trip of the rewritten steps
ESCALATION = 1194267    # the same pair again on the floor


def _rows():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


ROWS = _rows()


def replay():
    """[(turn, board, key, reason, pingpong report)] decided through choose_key."""
    out = []
    with TemporaryDirectory() as directory:
        policy = _policy(Path(directory), MONRACE)
        policy._skill_exp_request_key = lambda snapshot: None
        for row in ROWS:
            snapshot = parse_snapshot(copy.deepcopy(row["board"]), MONRACE)
            key = policy.choose_key(snapshot)
            out.append((row["board"]["turn"], snapshot, str(key), policy.last_reason,
                        pingpong_guard.report(policy)))
            policy.confirm_key_posted(key)
    return out


def recorded(turn):
    row = next(row for row in ROWS if row["board"]["turn"] == turn)["decision"]
    return row["key"], row["reason"]


class TheRecordingTest(unittest.TestCase):

    def test_the_boards(self):
        self.assertEqual(len(ROWS), 13)
        knowledge = MONRACE[BEASTMAN]
        self.assertIn("CONFUSE", [blow.effect for blow in knowledge.blows])
        self.assertIn("TPORT", knowledge.abilities)
        self.assertNotIn("RES_TELE", knowledge.flags)
        board = ROWS[-1]["board"]
        self.assertFalse(board["player"]["ability_sources"]["resist_conf"]["equipment"])
        self.assertIn("テレポートの巻物", [item["name"] for item in board["inventory"]])
        self.assertEqual(recorded(RETREAT), ("9", "status-threat:retreat"))
        rewritten = [recorded(row["board"]["turn"]) for row in ROWS
                     if row["board"]["turn"] >= FIRST_REWRITE]
        self.assertEqual({reason for _key, reason in rewritten},
                         {"no-wait:least-visited", "item:cure-critical"})
        self.assertEqual({key for key, reason in rewritten if reason == "no-wait:least-visited"},
                         {"2", "8"})


class TheFollowerIsFoughtTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rows = replay()

    def test_the_replay_matches_the_record_until_the_wait(self):
        for turn, _board, key, reason, _report in self.rows:
            if turn >= FIRST_REWRITE:
                break
            self.assertEqual((key, reason), recorded(turn), turn)

    def test_beside_the_follower_the_rung_strikes_it(self):
        struck = 0
        for turn, board, key, reason, _report in self.rows:
            if turn < FIRST_REWRITE:
                continue
            if recorded(turn)[1] == "item:cure-critical":
                self.assertEqual((key, reason), recorded(turn), turn)  # confused: cured first
                continue
            beastman = next(monster for monster in board.visible_monsters
                            if monster.race_id == BEASTMAN)
            here = board.player.position
            self.assertLessEqual(here.distance_to(beastman.position), 1, turn)
            self.assertEqual(reason, "status-threat:cornered-attack", turn)
            offset = (beastman.position.y - here.y, beastman.position.x - here.x)
            self.assertEqual(pingpong_guard.WALK_OFFSETS[key], offset, turn)
            struck += 1
        self.assertEqual(struck, 9)


class TheGuardSeesTheRewrittenWalkTest(unittest.TestCase):
    """DECLARED CONSTRUCTED: the rung's answers beside a follower are taken out (the live build's
    rung), so the rewritten least-visited steps alternate as recorded."""

    @classmethod
    def setUpClass(cls):
        without = types.SimpleNamespace(followers=lambda policy, snapshot: [],
                                        away_key=lambda *args, **kwargs: None)
        with mock.patch.object(ladder_combat, "teleport_follower", without, create=True):
            cls.rows = replay()

    def test_the_alternation_is_read_and_escalated(self):
        reports = {turn: report for turn, _board, _key, _reason, report in self.rows}
        label = "no-wait:least-visited/no-wait:least-visited"
        self.assertEqual(reports[GUARD_WINDOW], f"{pingpong_guard.EVENT}:{label}")
        self.assertEqual(reports[ESCALATION], f"{pingpong_guard.ESCALATE_EVENT}:{label}")
        for turn, _board, key, reason, _report in self.rows:
            if turn < ESCALATION:
                self.assertEqual((key, reason), recorded(turn), turn)
        # The escalation's livelock leave answers in place of the walk (no new leave).
        _turn, _board, key, reason, _report = self.rows[-1]
        self.assertTrue(reason.startswith("livelock:"), reason)
        self.assertNotEqual(key, recorded(ESCALATION)[0])


if __name__ == "__main__":
    unittest.main()
