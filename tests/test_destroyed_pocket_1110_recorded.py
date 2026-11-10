"""n1-b life-367, Mountain 50F, 2026-11-10 20:54: the pocket of its own *Destruction*.

The bot used its absorbed *Destruction* at (58,30) (decision 11842), mapped the circle
(11843, 周辺感知), then searched the walls of a 28-cell pocket 60 times and read Recall at
629/629 HP (11905 stuck:recall-escape).  17 of the 41 dives from 46F on ended that way.
The pocket's floor is grass, which a magic mapping leaves blank, so ``sealed_region`` read
the blank cells as unknown ground that leads on and the Stone to Mud rule (owner
2026-11-05 「*破壊*後全方位壁なら岩石溶解で脱出すれば良い」) never ran, with a wand of 96
charges in the pack.  Every straight line from the pocket ends at the Mountain's permanent
peaks, so the way out is the melt route (two walls).

Owner 2026-11-04 on what follows a *Destruction*: 「治して階の探索を続ける。破壊の回数だけでは帰還
しない」.

Recorded (tests/extract_destroyed_pocket_1110_fixture.py): the boards of decisions 11842
(*Destruction*), 11843 (map-area) and 11844 (live: me-power:before-secret-search), every one
through the public choose_key, each board carrying the previous decision's completed owner
as the CLI adds it.
DECLARED CONSTRUCTED: the absorbed power list (the live process had read it; the capture does
not carry it); the skill-exp list (test_sealed_pocket_quest_1105's); the pack without the
wand, or without the wand and the scrolls; the board after a refused or landed read (the
recorded board again, ten game turns later).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run
from recorded_junk_scope import install_past_destroyed_junk

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import destruction_use, mapped_area
from hengbot.me_device_attacks import observe_lists
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy
from tests.test_me_device_attacks import power_list, row
from tests.test_sealed_pocket_quest_1105_recorded import _pin as _sealed_pin

FIXTURE = Path(__file__).with_name("fixtures") / "destroyed-pocket-1110.json.xz"
USE_TURN, FLASH_TURN, MAPPED_TURN = 5332475, 5332483, 5332490
CENTRE = Position(58, 30)  # the player at the use
WAND = (65, 6)            # j) 岩石溶解の魔法棒 (96回分)
TELEPORT_SCROLL = (70, 9)  # f) テレポートの巻物
RECALL_SCROLL = (70, 11)   # g) 帰還の詔の巻物
POCKET = {(56, 29), (57, 29), (58, 24), (58, 30), (59, 23), (59, 31), (60, 23), (60, 24),
          (60, 25), (60, 27), (60, 29), (60, 30), (61, 23), (61, 25), (61, 27), (61, 28),
          (61, 31), (62, 24), (62, 25), (62, 26), (62, 27), (62, 30), (63, 26), (63, 27),
          (63, 28), (63, 29), (64, 26), (64, 27)}
_undo_past_junk = None


def setUpModule():
    global _undo_past_junk
    _undo_past_junk = install_past_destroyed_junk()


def tearDownModule():
    _undo_past_junk()


def _boards():
    rows = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
    return {json.loads(line)["turn"]: json.loads(line) for line in rows}


def _without(raw, *kinds):
    raw = copy.deepcopy(raw)
    raw["inventory"] = [item for item in raw["inventory"] if (item["tval"], item["sval"]) not in kinds]
    for slot, item in zip("abcdefghijklmnopqrstuvwxyz", raw["inventory"]):
        item["slot"] = slot
    return raw


class DestroyedPocketRecordedTest(unittest.TestCase):
    def setUp(self):
        self.boards = _boards()
        self.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def drive(self, *removed):
        """The recorded *Destruction* and its map through choose_key: (policy, mapped raw)."""
        boards = {turn: _without(raw, *removed) for turn, raw in self.boards.items()}
        use = boards[USE_TURN]
        policy = _policy(self.root, self.monrace)
        board = parse_snapshot(use, self.monrace)
        policy.prime(board)
        skill = next(json.loads(line) for line in _sealed_pin()["lines"] if '"skill_exp"' in line)
        policy.consume_skill_knowledge({**skill, "player": {"level": board.player.level}})
        listed = dict(copy.deepcopy(use), turn=USE_TURN - 1, _magic_eater_power_list=power_list(
            "staff", row("*破壊*", 5, current=3, count=3), row("周辺感知", 5, current=3, count=3),
            row("ドア/階段感知", 5, current=3, count=3)))
        observe_lists(policy, parse_snapshot(listed, self.monrace))
        self.assertEqual(self.choose(policy, use), ("mA3", "emergency:destruction:absorbed-power"))
        self.assertEqual(self.choose(policy, boards[FLASH_TURN], policy.last_reason),
                         ("mAj", "me-power:after-destruction:map-area"))
        return policy, boards[MAPPED_TURN]

    def choose(self, policy, raw, previous=None):
        raw = copy.deepcopy(raw)
        if previous is not None:
            raw["_completed_operation_owner"] = previous
        board = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
        return policy.choose_key(board), policy.last_reason

    def later(self, raw, turns=10):
        return dict(copy.deepcopy(raw), turn=raw["turn"] + turns, messages=[])

    def test_the_pocket_is_melted_out_along_the_route(self):
        """Live: me-power:before-secret-search, then 60 searches and Recall.  Every line ends
        at permanent rock, so the route's first step is walked toward its first wall."""
        policy, raw = self.drive()
        key, reason = self.choose(policy, raw, policy.last_reason)
        self.assertEqual(reason, "livelock:stone-to-mud")
        self.assertEqual(key, "7")

    def test_without_the_wand_teleportation_comes_before_any_search(self):
        policy, raw = self.drive(WAND)
        self.assertEqual(self.choose(policy, raw, policy.last_reason),
                         ("rf", "stuck:destroyed-circle-teleport"))

    def test_a_second_seal_in_the_same_circle_reads_recall_last(self):
        """The Teleportation read once for this circle (the next board: the read refused, ten
        turns on), the circle's last means is Recall."""
        policy, raw = self.drive(WAND)
        self.choose(policy, raw, policy.last_reason)
        self.assertEqual(self.choose(policy, self.later(raw)),
                         ("rg", "stuck:destroyed-circle-recall"))

    def test_the_circle_walls_are_never_searched(self):
        """No wand, no scroll: nothing leaves the pocket, and its walls (granite, quartz and
        magma that destroy_area just made) are not searched for secret doors."""
        policy, raw = self.drive(WAND, TELEPORT_SCROLL, RECALL_SCROLL)
        reasons = []
        for step in range(12):
            reasons.append(self.choose(policy, self.later(raw, 10 * (step + 1)), policy.last_reason)[1])
        self.assertNotIn("seek-secret-wall", reasons)
        board = parse_snapshot(raw, self.monrace)
        circle = mapped_area.disc_cells(board, CENTRE, destruction_use.GUARANTEED_RADIUS)
        for cell in POCKET:
            # Only the floor's outer permanent wall (y 65) is left beside the pocket.
            walls = policy._undersearched_walls(Position(*cell))
            self.assertEqual(set(walls) & circle, set(), cell)


if __name__ == "__main__":
    unittest.main()
