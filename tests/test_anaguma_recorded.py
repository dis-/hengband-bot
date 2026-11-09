"""Anaguma (穴熊) on recorded pack boards (owner 2026-11-10, docs/anaguma-design.md).

Owner, verbatim: 「群れに対抗するための戦術を追加する。岩石溶解を用いて7方壁の窪みを作り待ち伏せする
方法である。後続から遠距離攻撃を受けないようにしておくとなお良い。穴熊と呼称する。」 and the answers of
the same day: 「動物の群れにはジグザグの通路を長めに取る。…最後の一匹は近寄ってこないのでこちらから
詰める動きが別途必要になる。」, 「4マス/2マスを基本とし、地形と岩石溶解の回数が許すなら8マスまで伸ばす」,
「魔道具術師の場合は自然回復するので残さなくて良い。それ以外なら1回残す。」, 「範囲→加速→出口まで追う
を基本的には採用するが、加速は魔道具術師など消耗品を使用しない場合に限定する」, 「50ゲームターン。待った後、
可能なら感知を使って状況を把握する。」.

Recorded boards (tests/extract_anaguma_fixture.py; the three rows before each board prime the
policy):

- ``anaguma-orcs-480-1104``: n1-a life-480 (warrior, Lv-high, 13 Stone to Mud charges), the Orc
  cave 19F, eleven cave orcs (FRIENDS, not ANIMAL) awake 18 cells away, turn 812748
  (captures/burst-1104/n1-a/life-480, snapshots-20261104-202421-d65643).
- ``anaguma-hounds-480-1104``: the same life on the Orc cave 19F, four shadow hounds (ANIMAL
  FRIENDS) 19 cells away, 14 charges, turn 797510 (snapshots-20261104-200905-80f516).
- ``anaguma-hounds-504-1110``: n1-a life-504, Angband 24F (random quest 41), air hounds in
  view and a wand of 2 charges, turn 878346 (captures/n1a-504-death-1110).
- ``anaguma-orcs-306-1104``: n1-b life-306, Angband 19F, arrived beside four cave orcs, turn
  4830521 (captures/stops-1104-morning/n1-b/life-306).

DECLARED RECONSTRUCTED: the captures keep no skill reply; the skill cache is filled as the
Q2 Tower test does.  DECLARED CONSTRUCTED (the successor boards of the dig and the hold): the
board after each key is the recorded board with that key's effect applied by the test -- a
melted cell turned to floor, the player moved one cell, the game turn advanced -- and, where
named, a pack member placed on a cell.  Every decision is the public ``choose_key`` of one
policy instance; nothing of the plan is assigned by the test.
"""

import tests  # noqa: F401 -- isolate runtime files

import copy
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import anaguma, anaguma_geometry as geo
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import DIRECTION_KEYS
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
SHA = {
    "anaguma-orcs-480-1104.jsonl.gz": "3d83700d96dfd2fdb594da661d725a80270612e5bb6ba9337e9f280e471a767e",
    "anaguma-hounds-480-1104.jsonl.gz": "811c8c9cf2a24e3c8ca51e3ad27d7795fe8f4279f4e0a3fcae505499fad23e60",
    "anaguma-hounds-504-1110.jsonl.gz": "52dbe0fb1e9f72567e398a4187cde85045613021633e042e88415e70a3452967",
    "anaguma-orcs-306-1104.jsonl.gz": "1fd4f485074686e76ea8318e93656a68461da3834847b582840ac59a792d0403",
}
CAVE_ORC = 126
SHADOW_HOUND = 272
STEP = {key: offset for offset, key in DIRECTION_KEYS.items()}


def rows(name):
    text = gzip.decompress((FIXTURES / name).read_bytes())
    assert hashlib.sha256(text).hexdigest() == SHA[name], name
    return [json.loads(line) for line in text.splitlines()]


class AnagumaRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def policy_on(self, name, adjust=lambda raw: raw):
        """The policy primed on the three rows before the board, and the board."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        boards = [parse_snapshot(adjust(copy.deepcopy(raw)), self.monrace) for raw in rows(name)]
        policy.prime(boards[0])
        # DECLARED RECONSTRUCTED: the capture keeps no skill reply.
        policy._skill_exp_cache = (0, 0, boards[0].player.level, policy._town_visit_epoch)
        for board in boards[:-1]:
            policy.choose_key(policy.with_known_skill_exp(board))
        return policy, boards[-1]

    def decide(self, policy, board):
        return policy.choose_key(policy.with_known_skill_exp(board))

    # -------------------------------------------------- constructed successors

    @staticmethod
    def moved(board, position, turns=1, *, reveal=False):
        """DECLARED CONSTRUCTED: one step; ``reveal`` (a step into a dug cell): the player's
        light shows the rock around it (a grid the board does not know beside the new cell is
        shown as the board's granite)."""
        player = replace(board.player, position=position)
        monsters = [replace(m, distance=position.distance_to(m.position)) for m in board.visible_monsters]
        rock = next(g for g in board.grids.values()
                    if g.known and g.wall and g.tunnel and not g.permanent and not g.has_gold)
        floor = next(g for g in board.grids.values() if g.known and g.passable and not g.trap)
        grids = dict(board.grids)
        here = board.player.position
        if here not in grids or not grids[here].known:
            grids[here] = replace(floor, position=here)  # the cell just left is floor
        for dy in ((-1, 0, 1) if reveal else ()):
            for dx in (-1, 0, 1):
                cell = Position(position.y + dy, position.x + dx)
                if cell not in grids or not grids[cell].known:
                    grids[cell] = replace(rock, position=cell)
        return replace(board, player=player, visible_monsters=monsters, grids=grids,
                       turn=board.turn + 10 * turns)

    @staticmethod
    def opened(board, cell):
        grids = dict(board.grids)
        grids[cell] = replace(grids[cell], passable=True, wall=False, tunnel=False, can_dig=False,
                              allows_los=True)
        return replace(board, grids=grids, turn=board.turn + 10)

    @staticmethod
    def placed(board, race, cells, *, seen=True):
        """DECLARED CONSTRUCTED: the pack of ``race`` on ``cells``, in view (``seen``) or
        detected; the rest of the pack is gone."""
        members = [m for m in (*board.visible_monsters, *board.detected_monsters) if m.race_id == race]
        moved = [replace(m, position=cell, distance=board.player.position.distance_to(cell), asleep=False,
                         perception="direct" if seen else "detected")
                 for m, cell in zip(members, cells)]
        visible = [m for m in board.visible_monsters if m.race_id != race]
        detected = [m for m in board.detected_monsters if m.race_id != race]
        if seen:
            visible += moved
        else:
            detected += moved
        return replace(board, visible_monsters=visible, detected_monsters=detected)

    def apply(self, board, key, reason):
        """The effect of one Anaguma key on the board (DECLARED CONSTRUCTED)."""
        plan = anaguma.plan(self.policy)
        if reason.startswith(anaguma.REASON_DIG):
            here = board.player.position
            target = next(cell for cell in plan.tunnel.cells
                          if not board.grid_at(cell).passable and here.distance_to(cell) <= 1)
            return self.opened(board, target)
        offset = STEP[key[-1]]
        return self.moved(board, Position(board.player.position.y + offset[0],
                                          board.player.position.x + offset[1]),
                          reveal=reason == anaguma.REASON_STEP)

    def dig_to_hold(self, board, limit=40):
        reasons = []
        for _ in range(limit):
            key = self.decide(self.policy, board)
            reasons.append(self.policy.last_reason)
            plan = anaguma.plan(self.policy)
            self.assertIsNotNone(plan, (reasons, getattr(self.policy, "_anaguma_last_release", None)))
            if plan.phase == "hold":
                return board, reasons, key
            self.assertTrue(self.policy.last_reason.startswith("anaguma:"), (key, reasons))
            board = self.apply(board, key, self.policy.last_reason)
        self.fail(reasons)

    # -------------------------------------------------- pins

    def test_orc_pack_at_a_distance_is_met_from_a_dug_pocket(self):
        self.policy, board = self.policy_on("anaguma-orcs-480-1104.jsonl.gz")
        orcs = [m for m in board.detected_monsters if m.race_id == CAVE_ORC and not m.asleep]
        self.assertGreaterEqual(len(orcs), 2)
        self.decide(self.policy, board)
        self.assertTrue(self.policy.last_reason.startswith("anaguma:"), self.policy.last_reason)
        plan = anaguma.plan(self.policy)
        self.assertFalse(plan.animal)
        self.assertEqual(plan.minimum, anaguma.OTHER_LENGTH)
        self.assertGreaterEqual(len(plan.tunnel.cells), plan.minimum)
        # The pack held still (DECLARED CONSTRUCTED): the dig runs to the base length and beyond.
        held, reasons, key = self.dig_to_hold(board)
        self.assertIn(anaguma.REASON_DIG, reasons)
        plan = anaguma.plan(self.policy)
        self.assertGreaterEqual(plan.length, anaguma.OTHER_LENGTH)
        self.assertTrue(geo.pocket_holds(held, plan.pocket, plan.mouth))
        self.assertEqual((key, self.policy.last_reason), ("5", anaguma.REASON_HOLD))
        # An orc steps onto the mouth: the blow goes to it, nowhere else.
        contact = self.placed(held, CAVE_ORC, [plan.mouth])
        key = self.decide(self.policy, contact)
        self.assertEqual(self.policy.last_reason, anaguma.REASON_MELEE)
        self.assertEqual(key[-1], DIRECTION_KEYS[(plan.mouth.y - plan.pocket.y,
                                                  plan.mouth.x - plan.pocket.x)])

    def test_animal_pack_digs_four_cells_and_closes_in_on_the_last_one(self):
        self.policy, board = self.policy_on("anaguma-hounds-480-1104.jsonl.gz")
        self.decide(self.policy, board)
        self.assertTrue(self.policy.last_reason.startswith("anaguma:"), self.policy.last_reason)
        plan = anaguma.plan(self.policy)
        self.assertTrue(plan.animal)
        self.assertEqual(plan.minimum, anaguma.ANIMAL_LENGTH)
        held, _reasons, _key = self.dig_to_hold(board)
        plan = anaguma.plan(self.policy)
        self.assertGreaterEqual(plan.length, anaguma.ANIMAL_LENGTH)
        # The last hound sits hidden on the next cell in line (design 1.7); 50 game turns pass
        # with no contact.  A warrior has no area attack, no detection here and no absorbed
        # Speed: it steps out to the mouth (「出口まで追う」).
        next_in_line = plan.cells[-3]
        lone = self.placed(held, SHADOW_HOUND, [next_in_line], seen=False)
        lone = replace(lone, turn=held.turn + anaguma.WAIT_GAME_TURNS)
        key = self.decide(self.policy, lone)
        self.assertEqual(self.policy.last_reason, anaguma.REASON_CLOSE_STEP,
                         (key, anaguma.plan(self.policy), getattr(self.policy, "_anaguma_last_release", None)))
        stepped = self.moved(lone, plan.mouth)
        self.decide(self.policy, stepped)
        self.assertEqual(self.policy.last_reason, anaguma.REASON_CLOSE_MELEE)

    def test_two_charges_dig_nothing_for_an_animal_pack(self):
        self.policy, board = self.policy_on("anaguma-hounds-504-1110.jsonl.gz")
        self.decide(self.policy, board)
        self.assertIsNone(anaguma.plan(self.policy))
        self.assertEqual(getattr(self.policy, "_anaguma_veto", None), "charges")
        self.assertFalse(self.policy.last_reason.startswith("anaguma:"))

    def test_a_warrior_keeps_one_charge(self):
        """「それ以外なら1回残す」: with 4 charges a warrior digs no 4-cell tunnel, with 5 it does.
        DECLARED CONSTRUCTED: the recorded wand's charges set on every row."""
        def charges(count):
            def adjust(raw):
                for item in raw["inventory"]:
                    if item["tval"] == 65 and item["sval"] == 6:
                        item["charges"] = item["pval"] = count
                return raw
            return adjust
        for count, digs in ((4, False), (5, True)):
            with self.subTest(charges=count):
                self.policy, board = self.policy_on("anaguma-hounds-480-1104.jsonl.gz", charges(count))
                self.decide(self.policy, board)
                self.assertEqual(anaguma.plan(self.policy) is not None, digs)
                if not digs:
                    self.assertEqual(getattr(self.policy, "_anaguma_veto", None), "charges")

    def test_arrival_beside_the_pack_digs_nothing(self):
        self.policy, board = self.policy_on("anaguma-orcs-306-1104.jsonl.gz")
        self.decide(self.policy, board)
        self.assertIsNone(anaguma.plan(self.policy))
        self.assertFalse(self.policy.last_reason.startswith("anaguma:"))


if __name__ == "__main__":
    unittest.main()
