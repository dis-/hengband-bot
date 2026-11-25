"""n1-a life-537's death on Angband 50F (2026-11-26 02:04, Warrior Lv48, HP 1145).

What happened (tests/fixtures/n1a-537-angband50-1126.jsonl.gz, the floor from its arrival): after
the *Destruction* of the arrival the explore walked on, never once detecting traps; at (38,14)
(turn 4414701) it stepped '3' onto the unvisited (39,15), still CAVE_UNSAFE on the board
(``unsafe_rows``), and a dragon pack never sensed before (ヘル・ワイアーム, 古代万色ドラゴン,
『メガ・フレイム・ドラゴン』...) killed it from full HP before its next turn -- most likely a hidden
curse trap (grid/trap.cpp TY_CURSE, a group summon) or a teleport trap.

Owner 2026-11-26 「50F以降は全感知のロッドを持つ」 (deep_detection_rod): on 50F+ the Rod of
Detection is zapped before a step out of the trap-detected area, and waited for while it recharges.

Recorded: a fresh policy decides every recorded board of the floor from its arrival through the
public ``choose_key`` (tests/extract_n1a_537_deep_detection_1126_fixture.py).  DECLARED CONSTRUCTED:
the same boards with a Rod of Detection in the pack (letter j, after the Rod of Recall, the letters
behind it moved on by one), charged on every board (the recorded boards never show it charging),
and the last board with the rod charging.  The replay is open: a zap does not change the recorded
boards after it, so every later board with an undetected neighbour zaps again.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import gzip
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import deep_detection_rod
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-537-angband50-1126.jsonl.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    BOARDS = {raw["turn"]: raw for raw in map(json.loads, _stream)}
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

ARRIVAL = min(BOARDS)
LAST = max(BOARDS)  # (38,14), recorded '3' onto (39,15), then the death
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1), "7": (-1, -1),
         "8": (-1, 0), "9": (-1, 1)}
TVAL_ROD, SV_ROD_RECALL = 66, 3
COMBAT_REASONS = ("anaguma", "melee")


def _with_rod(raw, *, charging=False):
    """DECLARED CONSTRUCTED (module docstring): the board with a Rod of Detection in the pack."""
    inventory = raw["inventory"]
    after = next(index for index, item in enumerate(inventory)
                 if (item["tval"], item["sval"]) == (TVAL_ROD, SV_ROD_RECALL))
    rod = dict(inventory[after], sval=6, name="全感知のロッド", charges=99, pval=99,
               charging=charging, charging_count=1 if charging else 0)
    inventory = [*inventory[:after + 1], rod, *inventory[after + 1:]]
    for index, item in enumerate(inventory):
        item["slot"] = chr(ord("a") + index)
    raw["inventory"] = inventory
    return raw


def _cell(raw):
    return raw["player"]["y"], raw["player"]["x"]


def _unsafe(raw, cell):
    y, x = cell
    return bool(int(raw["grid_map"]["unsafe_rows"][y][x // 4], 16) >> (x % 4) & 1)


def _decide(policy, raw, previous):
    if previous is not None:
        raw["_completed_operation_owner"] = previous
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(policy.with_known_skill_exp(parse_snapshot(raw, MONRACE)))
    if key:
        policy.confirm_key_posted(key)
    return key, (policy.last_reason if key else None)


def _replay(rod: bool):
    """Every board of the floor decided; the policy as it meets the last board."""
    directory = TemporaryDirectory()
    policy = _policy(Path(directory.name), MONRACE)
    first = parse_snapshot(copy.deepcopy(BOARDS[ARRIVAL]), MONRACE)
    policy.prime(first)
    policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
    decided, previous, before_last = {}, None, None
    for turn in sorted(BOARDS):
        if turn == LAST:
            before_last = (copy.deepcopy(policy), previous)
        raw = copy.deepcopy(BOARDS[turn])
        if rod:
            raw = _with_rod(raw)
        key, previous = _decide(policy, raw, previous)
        decided[turn] = (_cell(BOARDS[turn]), key, previous)
    return directory, decided, before_last


class DeepDetectionRodRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plain_dir, cls.plain, _ = _replay(rod=False)
        cls.rod_dir, cls.rod, cls.before_last = _replay(rod=True)

    @classmethod
    def tearDownClass(cls):
        cls.plain_dir.cleanup()
        cls.rod_dir.cleanup()

    def test_the_recorded_step_onto_the_undetected_cell(self):
        cell, key, reason = self.plain[LAST]
        self.assertEqual((cell, key, reason), ((38, 14), "3", "explore"))
        self.assertTrue(_unsafe(BOARDS[LAST], (39, 15)))

    def test_with_the_rod_the_step_is_preceded_by_a_zap(self):
        cell, key, reason = self.rod[LAST]
        self.assertEqual((cell, reason), ((38, 14), deep_detection_rod.ZAP_REASON))
        self.assertEqual(key, "zj")  # the rod's letter

    def test_no_step_of_the_floor_enters_an_undetected_cell_while_the_rod_is_held(self):
        # The rung stands in the objectives layer: the combat layer's moves above it (the
        # anaguma's walk and steps into its dug pocket against a pack) and a melee blow (a key
        # of a direction, no step) are not its own.
        entered = []
        for turn, (cell, key, reason) in self.rod.items():
            if key in STEPS and not reason.startswith(COMBAT_REASONS):
                target = (cell[0] + STEPS[key][0], cell[1] + STEPS[key][1])
                if _unsafe(BOARDS[turn], target):
                    entered.append((turn, cell, key))
        self.assertEqual(entered, [])
        stepped = [turn for turn, (cell, key, reason) in self.plain.items()
                   if key in STEPS and not reason.startswith(COMBAT_REASONS)
                   and _unsafe(BOARDS[turn], (cell[0] + STEPS[key][0], cell[1] + STEPS[key][1]))]
        self.assertGreater(len(stepped), 100)  # recorded: the walk entered undetected cells

    def test_a_charging_rod_is_waited_for(self):
        policy, previous = copy.deepcopy(self.before_last[0]), self.before_last[1]
        key, reason = _decide(policy, _with_rod(copy.deepcopy(BOARDS[LAST]), charging=True), previous)
        self.assertEqual((key, reason), (f"R{deep_detection_rod.WAIT_PLAYER_TURNS}\r",
                                          deep_detection_rod.WAIT_REASON))

    def test_the_rod_is_kept_on_50f(self):
        policy = self.before_last[0]
        board = policy.with_known_skill_exp(parse_snapshot(_with_rod(copy.deepcopy(BOARDS[LAST])), MONRACE))
        rod = deep_detection_rod.carried(board)
        self.assertIsNotNone(rod)
        self.assertEqual(policy._retention_reservation_detail(board, rod),
                         (1, deep_detection_rod.RETENTION_BRANCH))


class DeepDetectionRodRevertProofTest(unittest.TestCase):
    def test_without_the_rung_the_rod_holder_steps_onto_the_undetected_cell(self):
        directory, _decided, (policy, previous) = _replay(rod=True)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(deep_detection_rod, "key", lambda policy, snapshot: None):
            key, reason = _decide(policy, _with_rod(copy.deepcopy(BOARDS[LAST])), previous)
        self.assertEqual((key, reason), ("3", "explore"))


if __name__ == "__main__":
    unittest.main()
