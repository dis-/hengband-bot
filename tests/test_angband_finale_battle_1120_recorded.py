"""The 99F/100F battle (angband_finale_battle, owner 2026-11-20).

Owner, verbatim (the lines each test pins are quoted at the test): the arrival sweep with
*Destruction*, the target allowed in it; haste and the Resistance potion; the Stone to Mud line from
as far as possible, its last wall kept for the target's own move; the powered Rocket only with 800 HP
left after its cost; *Healing* below 400 after a hit; Teleportation below 800 after a hit or a summon
or with the target closer than 2; *Destruction* (powered when needed) of the others while the target
is outside the circle; the map after it; the recovery after a teleport; the walk to the last-seen
cell; Recall on success or with twice the Restore Mana target used, and only then.

Recorded: n1-b life-411's Angband 99F arrival board (tests/fixtures/n1b-411-angband-cap-1119,
2026-11-19, Lv50 Magic-Eater, 1103 HP, absorbed *Destruction* at 96%, 8 Rockets; Oberon's quest 8
TAKEN) with 37 sleeping monsters around the player, and the town-arrival policy of that fixture.

DECLARED CONSTRUCTED:
* the readiness latch set (angband_finale ``Memory.ready``), as a ready town board leaves it;
* ``board``: the recorded board with its monsters replaced by those a test names (Oberon, race 860,
  at full HP; "others": copies of a recorded ゴブリン row moved), the cells around the player opened
  and in view in a box of the half-size asked (and walls on the cells a test names), the HP asked
  (the previous board's HP for a hit), the haste shown (the speed field yellow) and the Resistance
  shown (the five opposition keys on the status bar) unless a test says not;
* the pack: a *Healing* stack, and a Wand of Stone to Mud (5 charges) for the stand test;
* the quest's status changed for the success test;
* the small-floor tests: the recorded board at the level asked (98F, 99F), and as a town board
  (floor key, depth and the town flag changed).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, angband_finale_battle as battle
from hengbot import area_mapping, destruction_use, me_powerful_activation
from hengbot.cli import _home_modal_continuation
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.me_device_attacks import POWERFUL_REASON
from hengbot.model import (
    AbilitySources, GridState, Position, SV_POTION_STAR_HEALING, SV_WAND_STONE_TO_MUD, TVAL_POTION, TVAL_WAND,
    parse_snapshot,
)
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-angband-cap-1119"
OBERON = 860
OPPOSITION = ("resist_acid", "resist_elec", "resist_fire", "resist_cold", "resist_pois")


def decide(policy, board):
    """One decision through the policy's entry (the board observed, then the ladder)."""
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


class AngbandFinaleBattleRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.arrival, _, _ = load(FIXTURE, Path(cls.scratch.name))
        cls.raw = json.loads(lzma.decompress((FIXTURE / "angband-99f-board.json.xz").read_bytes()))

    @classmethod
    def tearDownClass(cls):
        cls.arrival._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def setUp(self):
        self.policy = copy.deepcopy(self.arrival)
        angband_finale.memory(self.policy).ready = True  # DECLARED CONSTRUCTED: the latch
        # DECLARED CONSTRUCTED: a fresh arrival (the recorded visit's *Destruction* mapped).
        self.policy.__dict__.pop(area_mapping.MEMORY, None)
        self.recorded = parse_snapshot(copy.deepcopy(self.raw), self.policy._monrace_knowledge)
        self.here = self.recorded.player.position

    # -- the constructed boards ----------------------------------------------------------

    def at(self, dy, dx):
        return Position(self.here.y + dy, self.here.x + dx)

    def monster(self, race, cell, index):
        template = self.recorded.visible_monsters[1]
        name = "オベロン" if race == OBERON else template.name
        knowledge = self.policy._monrace_knowledge.get(race)
        hp = getattr(knowledge, "max_hp", 10000) if race == OBERON else template.hp
        return replace(template, index=index, race_id=race, position=cell, asleep=False, hp=hp,
                       max_hp=hp, name=name, distance=max(abs(cell.y - self.here.y),
                                                          abs(cell.x - self.here.x)))

    def board(self, *, oberon=None, others=(), recorded_monsters=False, box=4, walls=(),
              opened=(), hp=None, hasted=True, covered=True, pack=()):
        board = self.recorded
        grids = dict(board.grids)
        for dy in range(-box, box + 1):
            for dx in range(-box, box + 1):
                cell = self.at(dy, dx)
                base = grids.get(cell) or GridState(cell, True, True, False, False, False, False, False)
                grids[cell] = replace(base, known=True, passable=True, wall=False, can_dig=False,
                                      permanent=False, is_closed_door=False, is_door=False,
                                      trap=False, marked=True, in_view=True, lit=True,
                                      has_up_stairs=False, has_down_stairs=False)
        for cell in opened:
            base = grids.get(cell) or GridState(cell, True, True, False, False, False, False, False)
            grids[cell] = replace(base, known=True, passable=True, wall=False, can_dig=False,
                                  permanent=False, in_view=True, allows_los=True)
        for cell in walls:
            base = grids.get(cell) or GridState(cell, True, False, True, False, False, False, False)
            grids[cell] = replace(base, known=True, passable=False, wall=True, can_dig=True,
                                  permanent=False, in_view=True, allows_los=False)
        monsters = list(board.visible_monsters) if recorded_monsters else []
        if oberon is not None:
            monsters.append(self.monster(OBERON, oberon, 900))
        monsters += [self.monster(544, cell, 901 + n) for n, cell in enumerate(others)]
        # As the readiness requires (angband_finale): resist curse worn.
        sources = {name: board.player.ability_sources[name] for name in board.player.ability_sources}
        sources["resist_curse"] = frozenset({"equipment"})
        player = replace(board.player, abilities=board.player.abilities | {"resist_curse"},
                         ability_sources=AbilitySources(sources))
        if hp is not None:
            player = replace(player, hp=hp)
        if hasted:
            player = replace(player, speed_display=(player.speed, "+35", "yellow", False))
        player = replace(player, status_bar=tuple(OPPOSITION) if covered else ())
        healing = next(item for item in board.inventory if item.tval == TVAL_POTION)
        inventory = list(board.inventory)
        for slot, kind in pack:
            if kind == "star":
                inventory.append(replace(healing, slot=slot, sval=SV_POTION_STAR_HEALING, count=15,
                                         name="*体力回復*の薬"))
            elif kind == "mud":
                inventory.append(replace(healing, slot=slot, tval=TVAL_WAND, sval=SV_WAND_STONE_TO_MUD,
                                         count=1, charges=5, pval=5, name="岩石溶解の魔法棒"))
        return replace(board, grids=grids, visible_monsters=monsters, detected_monsters=[],
                       player=player, inventory=inventory)

    def in_battle(self):
        """Past the arrival sweep (its own tests below)."""
        battle.battle(self.policy, self.recorded).phase = battle.BATTLE

    # -- 「降りたらフロアを破壊しながら一巡し、対象以外のモンスターを極力減らす。この作業時のみ対象を巻き込んでも良い。」

    def test_sweep_destroys_on_arrival(self):
        key, reason = decide(self.policy, self.board(recorded_monsters=True))
        self.assertTrue(key)
        self.assertTrue(reason.startswith(destruction_use.REASON + battle.SWEEP_SUFFIX), reason)

    def test_sweep_takes_the_target_in(self):
        board = self.board(recorded_monsters=True, oberon=self.at(0, 4))
        key, reason = decide(self.policy, board)
        self.assertTrue(reason.startswith(destruction_use.REASON + battle.SWEEP_SUFFIX), reason)

    def test_sweep_ends_without_others(self):
        board = self.board(oberon=self.at(0, 30))
        decide(self.policy, board)
        self.assertEqual(battle.battle(self.policy, board).phase, battle.BATTLE)

    # -- 「対象が破壊範囲内にいないとき、対象以外のあらゆるモンスターを破壊で排除する。必要なら強力発動で範囲を広げる。」

    def test_clear_only_with_the_target_outside(self):
        self.in_battle()
        far = self.board(oberon=self.at(0, 20), others=[self.at(0, 5)])
        key, reason = decide(self.policy, far)
        self.assertTrue(reason.startswith(destruction_use.REASON + battle.CLEAR_SUFFIX), reason)
        self.setUp()
        self.in_battle()
        near = self.board(oberon=self.at(0, 10), others=[self.at(0, 5)])
        key, reason = decide(self.policy, near)
        self.assertFalse(reason.startswith(destruction_use.REASON), reason)

    def test_clear_powered_when_only_it_reaches(self):
        self.in_battle()
        board = self.board(oberon=self.at(0, 25), others=[self.at(0, 16)])
        key, reason = decide(self.policy, board)
        self.assertEqual(reason, destruction_use.REASON + battle.CLEAR_SUFFIX
                         + destruction_use.POWERED_SUFFIX)
        self.assertTrue(key.startswith("U"), key)

    # -- 「加速し耐性の薬を飲み」 / 「コストを払った後にHPが800ポイント残ることを確認して強力発動ロケットで攻撃する。」

    def test_haste_resistance_then_the_powered_rocket(self):
        self.in_battle()
        oberon = self.at(0, 4)
        key, reason = decide(self.policy, self.board(oberon=oberon, hasted=False))
        self.assertTrue(reason.startswith(battle.HASTE_REASON), reason)
        key, reason = decide(self.policy, self.board(oberon=oberon, covered=False))
        self.assertEqual(reason, battle.RESIST_REASON)
        key, reason = decide(self.policy, self.board(oberon=oberon))
        self.assertEqual(reason, POWERFUL_REASON)
        self.assertEqual(key, me_powerful_activation.racial_key("wand", 29) + f"@{oberon.y},{oberon.x}")

    def test_no_rocket_below_800_after_the_cost(self):
        self.in_battle()
        oberon = self.at(0, 4)
        # Lv50: the cost is 10 + 40 / 2 = 30 at worst; 829 - 30 < 800.
        key, reason = decide(self.policy, self.board(oberon=oberon, hp=829))
        self.assertEqual(reason, battle.HEAL_REASON)
        key, reason = decide(self.policy, self.board(oberon=oberon, hp=830))
        self.assertEqual(reason, POWERFUL_REASON)

    # -- 「攻撃を受けてHPが400を下回った時は*体力回復*の薬で回復する。」
    # -- 「召喚または攻撃を受けてHPが800を下回ったとき、または対象が距離2より近づいたときテレポートの巻物で離脱する。」

    def test_teleport_when_close(self):
        self.in_battle()
        key, reason = decide(self.policy, self.board(oberon=self.at(0, 1)))
        self.assertEqual(reason, battle.TELEPORT_REASON)
        self.assertEqual(battle.battle(self.policy, self.recorded).phase, battle.RECOVER)
        self.setUp()
        self.in_battle()
        key, reason = decide(self.policy, self.board(oberon=self.at(0, 2)))
        self.assertNotEqual(reason, battle.TELEPORT_REASON)

    def test_hit_below_800_teleports_and_below_400_heals(self):
        self.in_battle()
        oberon = self.at(0, 6)
        decide(self.policy, self.board(oberon=oberon))
        key, reason = decide(self.policy, self.board(oberon=oberon, hp=799))
        self.assertEqual(reason, battle.TELEPORT_REASON)
        self.setUp()
        self.in_battle()
        decide(self.policy, self.board(oberon=oberon, pack=[("x", "star")]))
        key, reason = decide(self.policy, self.board(oberon=oberon, hp=399, pack=[("x", "star")]))
        self.assertEqual(reason, battle.STAR_HEAL_REASON)
        # No hit (the same HP as the board before): neither.
        key, reason = decide(self.policy, self.board(oberon=oberon, hp=399, pack=[("x", "star")]))
        self.assertNotIn(reason, {battle.STAR_HEAL_REASON, battle.TELEPORT_REASON})

    # -- 「テレポートによる離脱後、安全が確保できたらHPや取り込み魔法道具回数を必要に応じて回復。」
    # -- 「回復できたら最後に対象をみた座標に向かって移動。」

    def test_recover_then_walk_to_the_last_seen_cell(self):
        self.in_battle()
        decide(self.policy, self.board(oberon=self.at(0, 1)))  # the teleport; Oberon seen there
        held = battle.battle(self.policy, self.recorded)
        self.assertEqual((held.phase, held.last_seen), (battle.RECOVER, (self.here.y, self.here.x + 1)))
        key, reason = decide(self.policy, self.board(hp=900))
        self.assertIn(reason, {battle.REST_REASON, battle.RESTORE_MANA_REASON})
        key, reason = decide(self.policy, self.board())
        self.assertNotEqual(held.phase, battle.RECOVER)
        held.last_seen = (self.here.y, self.here.x + 3)
        key, reason = decide(self.policy, self.board())
        self.assertEqual(reason, battle.APPROACH_REASON)

    # -- 「なるべく距離をとって相対するように岩石溶解を使って射線を通す。可能なら相手の移動後に射線が通るようにして、先手を取ること。」

    def test_the_stone_to_mud_stand(self):
        self.in_battle()
        oberon = self.at(0, 10)
        walls = [self.at(0, dx) for dx in range(5, 10)]
        board = self.board(oberon=oberon, walls=walls, pack=[("z", "mud")])
        key, reason = decide(self.policy, board)
        self.assertEqual(reason, battle.STAND_WALK_REASON)
        stand = battle.battle(self.policy, board).stand
        # The farthest reachable open cell on a ray of Oberon the five walls (and the Wand's five
        # charges) let a line through: west on Oberon's row, beyond the player's 10.
        self.assertEqual((stand.aim, stand.step, stand.cell[0]), ((oberon.y, oberon.x), (0, -1), oberon.y))
        self.assertGreater(stand.distance, 10)
        self.assertEqual(stand.distance, oberon.x - stand.cell[1])
        at_stand = replace(board, player=replace(board.player, position=Position(*stand.cell)))
        key, reason = decide(self.policy, at_stand)
        self.assertEqual(reason, battle.MELT_REASON)
        # One wall left with Oberon on the ray: kept, the target's move opens the line.
        last = self.board(oberon=oberon, walls=walls[-1:], opened=walls[:-1], pack=[("z", "mud")])
        last = replace(last, player=replace(last.player, position=Position(*stand.cell)))
        key, reason = decide(self.policy, last)
        self.assertEqual(reason, battle.HOLD_REASON)
        # Oberon steps off the ray behind rock (no line to it either): the last wall is melted, and
        # its next step onto the ray will be the move that opens the line.
        rock = [self.at(dy, dx) for dy in (1, 2, 3) for dx in (7, 8, 9)]
        moved = self.board(oberon=self.at(3, 10), walls=walls[-1:] + rock, opened=walls[:-1],
                           pack=[("z", "mud")])
        moved = replace(moved, player=replace(moved.player, position=Position(*stand.cell)))
        key, reason = decide(self.policy, moved)
        self.assertEqual(reason, battle.MELT_REASON)

    # -- 「帰還による離脱は成功時と魔力復活の薬を予定の倍以上使ったときのみ。」

    def test_recall_only_on_success_or_overspent(self):
        self.in_battle()
        board = self.board()
        self.assertFalse(battle.recall_permitted(self.policy, board))
        self.assertFalse(self.policy._quest_floor_exit_locked(board) is False
                         and battle.recall_permitted(self.policy, board))
        quests = dict(board.quests)
        quests[8] = replace(quests[8], status=2)
        done = replace(board, quests=quests)
        self.assertTrue(battle.recall_permitted(self.policy, done))
        key, reason = decide(self.policy, done)
        self.assertEqual(reason, battle.RECALL_REASON)
        self.setUp()
        self.in_battle()
        goal = angband_finale.restore_mana_goal(self.policy, board)
        angband_finale.memory(self.policy).restore_mana_used = 2 * goal - 1
        self.assertFalse(battle.recall_permitted(self.policy, board))
        angband_finale.memory(self.policy).restore_mana_used = 2 * goal
        self.assertTrue(battle.recall_permitted(self.policy, board))
        key, reason = decide(self.policy, board)
        self.assertEqual(reason, battle.RECALL_REASON)

    def test_restore_mana_uses_are_counted_on_the_floor(self):
        mana = replace(self.recorded.inventory[0], slot="y", tval=TVAL_POTION, sval=40, count=10)
        floor = replace(self.recorded, inventory=[*self.recorded.inventory, mana])
        angband_finale.observe(self.policy, floor)
        fewer = replace(floor, inventory=[*self.recorded.inventory, replace(mana, count=7)])
        angband_finale.observe(self.policy, fewer)
        self.assertEqual(angband_finale.memory(self.policy).restore_mana_used, 3)

    # -- 「99F/100Fに降りる前に常に小さめのフロアを選択するオプションを有効にする。」

    def floor(self, level):
        raw = copy.deepcopy(self.raw)
        raw["floor"] = {**raw["floor"], "level": level}
        return parse_snapshot(raw, self.policy._monrace_knowledge)

    def test_small_floor_before_the_descent(self):
        policy = self.policy
        floor = self.floor(98)
        angband_finale.memory(policy).ready = False
        self.assertIsNone(battle.key(policy, floor))  # not lifted: nothing
        angband_finale.memory(policy).ready = True
        town = replace(floor, floor_key=(0, 0, 0), town_flag=True)
        self.assertIsNone(battle._small_floor(policy, town))  # never in town
        self.assertIsNone(battle._small_floor(policy, self.floor(99)))  # too late
        key = battle.key(policy, floor)
        self.assertEqual((key, policy.last_reason),
                         ('"Y:always_small_floor\r', angband_finale.SMALL_FLOOR_REASON))
        later = replace(floor, turn=floor.turn + 1)
        angband_finale.observe(policy, later)
        self.assertTrue(angband_finale.memory(policy).small_floor_set)
        self.assertNotEqual(battle.key(policy, later), angband_finale.SMALL_FLOOR_MACRO)

    def test_the_executor_answers_the_pref_prompt(self):
        first, steps = _home_modal_continuation(self.floor(98), angband_finale.SMALL_FLOOR_MACRO,
                                                angband_finale.SMALL_FLOOR_REASON)
        self.assertEqual(first, '"')
        self.assertEqual([(set(step.kinds), step.keys) for step in steps],
                         [({ScreenKind.PREF_COMMAND}, "Y:always_small_floor\r")])
        for prompt in ("設定変更コマンド: ", "Pref: "):
            screen = {"lines": [prompt] + [""] * 23, "width": 80, "height": 24}
            self.assertEqual(classify_screen(screen).kind, ScreenKind.PREF_COMMAND)


if __name__ == "__main__":
    unittest.main()
