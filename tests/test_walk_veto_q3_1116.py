"""Four walkers keep off the walks' whole veto, as the explore (owner 2026-11-15, review Q3).

Owner 「全部読ませる」: the kill-all patrol's hunt (kill_all_patrol ``_toward``), the quest target
search (quest_target_search ``_avoided``), the oscillation break (policy_navigation
``_break_positional_oscillation``) and the unknown probe (``_probe_unknown_step``) read the
walks' one veto (``policy._walk_veto``: the engagement retreats' cells, the left cells, the
routes' engagement veto, an unseen attacker's area).  Before, the hunt read the left cells only,
the search all but the unseen attacker's area, the break and the probe none of them.

Recorded boards, DECLARED CONSTRUCTED: the cell each walker took on the recorded board is put in
the engagement retreats' cells (``_engagement_avoid_cells``, a part of the veto none of the four
read before), and the walker is asked again on the same board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import kill_all_patrol, quest_target_search, walk_vetoes
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests import test_n1c_208_q25_patrol_1115_recorded as patrol
from tests.support.recorded import EDIT, _policy, skill

FIXTURES = Path(__file__).with_name("fixtures")
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")


def _boards(path: Path) -> list[dict]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line.startswith("{"):
                continue
            row = json.loads(line)
            if "player" in row and "floor" in row:
                rows.append(row)
            else:
                board = next((row[key] for key in ("state", "board", "snapshot")
                              if isinstance(row.get(key), dict) and "player" in row[key]), None)
                if board is not None:
                    rows.append(board)
    return rows


class OscillationBreakTest(unittest.TestCase):
    """tests/fixtures/detected-pack-flee-loop-20261023-state.jsonl.gz: the 29th board, where the
    break answers ('8' from (17,15), seek-loot having gone '1', '7')."""

    BOARDS = _boards(FIXTURES / "detected-pack-flee-loop-20261023-state.jsonl.gz")

    def decide(self, veto_step: bool):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), MONRACE)
        rows = []
        for raw in self.BOARDS:
            snapshot = parse_snapshot(copy.deepcopy(raw), MONRACE)
            if len(rows) == 28 and veto_step:
                policy._engagement_avoid_cells.add(Position(16, 15))
            skill(policy, raw)
            key = policy.choose_key(snapshot)
            rows.append((snapshot.player.position, key, policy.last_reason))
            if key:
                policy.confirm_key_posted(key)
            if len(rows) == 29:
                return rows

    def test_the_recorded_break(self):
        self.assertEqual(self.decide(False)[-1], (Position(17, 15), "8", "nav:break-oscillation"))

    def test_the_break_keeps_off_the_veto(self):
        self.assertEqual(self.decide(True)[-1], (Position(17, 15), "9", "nav:break-oscillation"))


class PatrolHuntTest(unittest.TestCase):
    """n1-c life-208 (Q25): the board where the quylthulg came into view; the hunt's walk."""

    def test_the_hunt_walk_keeps_off_the_veto(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = patrol.new_policy(Path(directory.name), "loop", patrol.lists())
        turn = patrol.QUYL_IN_VIEW[0]
        for raw in patrol.boards("loop"):
            if raw["turn"] >= turn:
                break
            patrol.decide(policy, raw)
        snapshot = parse_snapshot(patrol.board("loop", turn), policy._monrace_knowledge)
        target = snapshot.visible_monsters[0].position

        def beside(cell):
            return max(abs(cell[0] - target.y), abs(cell[1] - target.x)) <= 1

        self.assertEqual(kill_all_patrol._toward(policy, snapshot, beside), Position(7, 19))
        policy._engagement_avoid_cells.add(Position(7, 19))
        self.assertEqual(kill_all_patrol._toward(policy, snapshot, beside), Position(7, 20))


class UnknownProbeTest(unittest.TestCase):
    """tests/fixtures/abilities-depth34-landed-dungeon.json: the landing board's probe."""

    def test_the_probe_keeps_off_the_veto(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        raw = json.loads((FIXTURES / "abilities-depth34-landed-dungeon.json").read_text(encoding="utf-8"))
        snapshot = parse_snapshot(copy.deepcopy(raw), MONRACE)
        policy = _policy(Path(directory.name), MONRACE)
        first = policy._probe_unknown_step(snapshot)
        self.assertEqual(first, Position(17, 106))
        policy._probe_counts.clear()
        policy._engagement_avoid_cells.add(first)
        second = policy._probe_unknown_step(snapshot)
        self.assertNotEqual(second, first)
        self.assertNotIn(second, policy._walk_veto(snapshot))


class QuestTargetSearchTest(unittest.TestCase):
    def test_the_search_reads_the_walks_whole_veto(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        raw = json.loads((FIXTURES / "abilities-depth34-landed-dungeon.json").read_text(encoding="utf-8"))
        snapshot = parse_snapshot(copy.deepcopy(raw), MONRACE)
        policy = _policy(Path(directory.name), MONRACE)
        policy._unseen_attack_area_veto = lambda board: frozenset({Position(1, 1)})
        avoided = quest_target_search._avoided(policy, snapshot)
        self.assertEqual(avoided, walk_vetoes.walk(policy, snapshot))
        self.assertIn(Position(1, 1), avoided)


if __name__ == "__main__":
    unittest.main()
