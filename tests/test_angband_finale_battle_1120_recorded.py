"""The 99F/100F battle (angband_finale_battle, owner 2026-11-20).

Owner, verbatim (the lines each test pins are quoted at the test, with the answers to the
report's questions of 2026-11-20: Q1 「召喚されたら HP に関係なく離れる」, Q2 「距離2以下」, Q3
「テレポート後の回復に使う。ただし取り込んだ体力回復の方が優先度は上。」, Q4 「99F・100Fでは指示の
条件だけで撃つ」, Q8 「町で、99F・100Fへ帰還する前に入れる」, Q10 「フロア全体を回る」): the arrival sweep with
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
* the quest's status changed for the success test; a summon line (mspell-summon.cpp's
  「がアンバーの王族を召喚した！」) on the summon test's board;
* the sweep's circles: area_mapping's record of a flash at the cells a test names, and their map
  taken as cast;
* the town recall test: the recorded board as a town board, Angband's recall depth 95 and the
  decided recall's reason;
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

from hengbot import angband_finale, angband_finale_battle as battle, finale_prep
from hengbot import area_mapping, destruction_use, me_powerful_activation
from hengbot.cli import _home_modal_continuation
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.me_device_attacks import POWERFUL_REASON
from hengbot.model import (
    AbilitySources, GridState, Position, game_distance, SV_POTION_STAR_HEALING, SV_WAND_STONE_TO_MUD, TVAL_POTION, TVAL_WAND,
    parse_snapshot,
)
from hengbot.policy_constants import REST_MACRO
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
        finale_prep.phase(self.policy).lifted = True  # DECLARED CONSTRUCTED: the phase's mark
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
        # Oberon within the circle behind rock (out of the line of fire: no leave for the crowd).
        rock = [self.at(dy, -8) for dy in (-1, 0, 1)] + [self.at(dy, -7) for dy in (-1, 0, 1)]
        board = self.board(recorded_monsters=True, oberon=self.at(0, -9), walls=rock, box=10)
        key, reason = decide(self.policy, board)
        self.assertTrue(reason.startswith(destruction_use.REASON + battle.SWEEP_SUFFIX), reason)

    def test_sweep_covers_the_whole_floor(self):
        """「フロア全体を回る」: no monster known, the arrival still destroys; then the next circle
        at least SWEEP_SPACING away, walked to; then the gaps; covered, the battle."""
        from hengbot import area_mapping
        board = self.board()
        key, reason = decide(self.policy, board)
        self.assertTrue(reason.startswith(destruction_use.REASON + battle.SWEEP_SUFFIX), reason)
        self.setUp()
        board = self.board(box=16)
        decide(self.policy, board)  # the floor's area-mapping record starts on this board

        def mapped():
            """DECLARED CONSTRUCTED: the circles' map already cast (周辺感知 after them)."""
            area_mapping._floor_memory(self.policy, board).destroyed_turn = None
        area_mapping.note_destruction(self.policy, board, self.here, 17, 13)
        mapped()
        key, reason = decide(self.policy, board)
        self.assertEqual(reason, battle.SWEEP_WALK_REASON)
        left = battle.uncovered(self.policy, board)
        self.assertTrue(left)
        self.assertTrue(all(game_distance(cell, self.here) > 13 for cell in left))
        # The next circle goes at least SWEEP_SPACING from this one while such a cell is left.
        goals = battle.sweep_goals(self.policy, board)
        self.assertTrue(goals)
        self.assertTrue(all(game_distance(cell, self.here) >= battle.SWEEP_SPACING for cell in goals))
        for cell in sorted(left, key=lambda cell: (cell.y, cell.x)):
            area_mapping.note_destruction(self.policy, board, cell, 17, 13)
        mapped()
        self.assertFalse(battle.uncovered(self.policy, board))
        decide(self.policy, board)
        self.assertEqual(battle.battle(self.policy, board).phase, battle.BATTLE)

    # -- 「対象が破壊範囲内にいないとき、対象以外のあらゆるモンスターを破壊で排除する。」 under the owner's
    # 2026-11-23 answers 「テレパシーに映らなければ破壊を使って良い」「普通の *破壊* だけにする」.

    def test_clear_only_with_the_target_beyond_telepathy(self):
        self.in_battle()
        far = self.board(oberon=self.at(0, 25), others=[self.at(0, 5)])
        key, reason = decide(self.policy, far)
        self.assertTrue(reason.startswith(destruction_use.REASON + battle.CLEAR_SUFFIX), reason)
        self.assertFalse(reason.endswith(destruction_use.POWERED_SUFFIX), reason)
        for distance in (10, 20):
            self.setUp()
            self.in_battle()
            shown = self.board(oberon=self.at(0, distance), others=[self.at(0, 5)])
            key, reason = decide(self.policy, shown)
            self.assertFalse(reason.startswith(destruction_use.REASON), reason)

    def test_no_powered_clear_when_only_it_reaches(self):
        self.in_battle()
        board = self.board(oberon=self.at(0, 25), others=[self.at(0, 16)])
        key, reason = decide(self.policy, board)
        self.assertFalse(reason.startswith(destruction_use.REASON + battle.CLEAR_SUFFIX), reason)
        self.assertFalse(key.startswith("U"), key)

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

    def test_the_rocket_with_another_awake(self):
        """Q4 「99F・100Fでは指示の条件だけで撃つ」: the Amberite gate's 「他に起きた敵がいない」 is not
        asked (another awake monster inside the circle, so no *Destruction* first, and behind rock,
        out of the line of fire, so no leave)."""
        self.in_battle()
        oberon = self.at(0, 4)
        hidden = self.at(0, -9)
        rock = [self.at(dy, -8) for dy in (-1, 0, 1)] + [self.at(dy, -7) for dy in (-1, 0, 1)]
        board = self.board(oberon=oberon, others=[hidden], walls=rock, box=10)
        key, reason = decide(self.policy, board)
        self.assertEqual(reason, POWERFUL_REASON)

    def test_no_rocket_below_800_after_the_cost(self):
        self.in_battle()
        oberon = self.at(0, 4)
        # Lv50: the cost is 10 + 40 / 2 = 30 at worst; 829 - 30 < 800.
        key, reason = decide(self.policy, self.board(oberon=oberon, hp=829))
        self.assertIn(reason, {battle.ABSORBED_HEAL_REASON, battle.HEAL_REASON})
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
        self.assertEqual(reason, battle.TELEPORT_REASON)  # Q2 「距離2以下」
        self.setUp()
        self.in_battle()
        key, reason = decide(self.policy, self.board(oberon=self.at(0, 3)))
        self.assertNotEqual(reason, battle.TELEPORT_REASON)

    def test_a_summon_teleports_at_any_hp(self):
        """Q1 「召喚されたら HP に関係なく離れる」 (a hit only below 800)."""
        self.in_battle()
        oberon = self.at(0, 6)
        summoned = replace(self.board(oberon=oberon), messages=("オベロンがアンバーの王族を召喚した！",))
        key, reason = decide(self.policy, summoned)
        self.assertEqual(reason, battle.TELEPORT_REASON)
        self.setUp()
        self.in_battle()
        decide(self.policy, self.board(oberon=oberon))
        key, reason = decide(self.policy, self.board(oberon=oberon, hp=801))
        self.assertNotEqual(reason, battle.TELEPORT_REASON)

    def test_target_and_another_in_the_line_of_fire(self):
        """「ターゲットとターゲット以外が同時に射線に入っているときは召喚直後でなくとも離脱する。」"""
        self.in_battle()
        oberon = self.at(0, 4)
        key, reason = decide(self.policy, self.board(oberon=oberon, others=[self.at(3, 3)]))
        self.assertEqual(reason, battle.TELEPORT_REASON)
        # Behind rock the other is out of the line: the fight goes on.
        self.setUp()
        self.in_battle()
        hidden = self.at(0, -9)
        rock = [self.at(dy, -8) for dy in (-1, 0, 1)] + [self.at(dy, -7) for dy in (-1, 0, 1)]
        board = self.board(oberon=oberon, others=[hidden], walls=rock, box=10)
        key, reason = decide(self.policy, board)
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
        # Owner 2026-11-21 (LOCKED) 「99F 100Fでの休憩は許可していない」: a deficit short of a
        # potion's 300 is not rested off; no rest of any owner answers on the floor.
        self.assertNotIn(reason, {battle.REST_REASON, "rest"})
        self.assertNotEqual(key, REST_MACRO)
        # Q3: a deficit of a potion's 300 or more is healed (the absorbed Healing first); the
        # drop to 600 is a hit below 800 (a teleport), the next board at 600 is no hit.
        key, reason = decide(self.policy, self.board(hp=600))
        self.assertEqual(reason, battle.TELEPORT_REASON)
        key, reason = decide(self.policy, self.board(hp=600))
        self.assertIn(reason, {battle.ABSORBED_HEAL_REASON, battle.HEAL_REASON})
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

    def test_no_other_rule_finds_a_recall_on_the_floor(self):
        """「帰還による離脱は成功時と魔力復活の薬を予定の倍以上使ったときのみ」: the expedition's 99F
        has its Word of Recall for the battle's two cases only; every other rule (n1-b life-411
        2026-11-21 09:02:18 deep-teleport:recall, 09:07:45 summoner:recall, 09:14:53
        esp-threat:leave-recall) finds none (finale_prep ``recall_closed``)."""
        self.in_battle()
        board = self.board()
        self.assertTrue(any(item.is_recall_scroll for item in board.inventory))
        self.assertIsNone(self.policy._find_recall_scroll(board))
        quests = dict(board.quests)
        quests[8] = replace(quests[8], status=2)
        done = replace(board, quests=quests)
        self.assertIsNotNone(self.policy._find_recall_scroll(done))  # the battle's own case
        # Out of the expedition (no cap lift) the floor is the climb's, and recalls as ever.
        finale_prep.phase(self.policy).lifted = False
        self.assertIsNotNone(self.policy._find_recall_scroll(board))

    def restoring_board(self, *, mushrooms=0):
        """DECLARED CONSTRUCTED: the battle's board after a teleport, INT drained, full HP; with
        ``mushrooms`` Mushrooms of Restoring carried (a copy of the Healing row)."""
        board = self.board()
        player = replace(board.player, drained_stats=("int",), hp=board.player.max_hp)
        inventory = list(board.inventory)
        if mushrooms:
            healing = next(item for item in inventory if item.tval == TVAL_POTION)
            inventory.append(replace(healing, slot="x", tval=angband_finale.RESTORING[0],
                                     sval=angband_finale.RESTORING[1], count=mushrooms,
                                     name="全復活のキノコ"))
        return replace(board, player=player, inventory=inventory)

    def absorb_restoration(self, charges):
        """DECLARED CONSTRUCTED: the absorbed Restoration (rod) in the record and the rod list."""
        from hengbot import me_capability
        from hengbot.me_absorbed_substitutes import RESTORATION
        kind, sval = RESTORATION
        record = me_capability.recorded(self.policy)
        record[me_capability.record_key(kind, sval)] = 10
        lists = dict(self.policy._me_device_lists)
        turn, rows = lists.get(kind, (0, []))
        rows = [row for row in rows if row.get("name") not in me_capability.names(kind, sval)]
        rows.append({"name": me_capability.names(kind, sval)[0], "current": charges, "max": 10,
                     "fail": 1, "success": 99, "letter": "z"})
        lists[kind] = (turn, rows)
        self.policy._me_device_lists = lists

    def browse_rods(self, board):
        """DECLARED CONSTRUCTED: the ``bC`` board: the recorded rod list displayed on this turn."""
        lists = dict(self.policy._me_device_lists)
        lists["rod"] = (board.turn, lists["rod"][1])
        self.policy._me_device_lists = lists

    def test_drained_stats_after_the_teleport(self):
        """「テレポート後の回復タイミングで能力値が減っていれば食べる。ただし取り込んだ全復活が残っている
        場合はそちらを優先する。」"""
        held = battle.battle(self.policy, self.recorded)
        held.phase = battle.RECOVER
        board = self.restoring_board(mushrooms=3)
        # Recorded: n1-b holds the absorbed Restoration, its rod list of turn 7813454 on the
        # board of 7814111.  The stale list is browsed first (no game time), once a turn.
        self.assertLess(self.policy._me_device_lists["rod"][0], board.turn)
        self.assertEqual(battle._recover_key(self.policy, board, held), "bC")
        self.assertEqual(self.policy.last_reason, "periodic:magic-eater-powers")
        unread = battle._recover_key(self.policy, board, held)  # the list never arrived
        self.assertTrue(unread.startswith("E"), unread)
        # The list of this turn shows its charge: it comes first.
        self.browse_rods(board)
        key = battle._recover_key(self.policy, board, held)
        self.assertEqual(self.policy.last_reason, battle.RESTORE_STATS_REASON + ":absorbed-power")
        self.assertTrue(key.startswith("m"), key)
        self.absorb_restoration(0)  # its charges spent (the list shows it empty)
        self.browse_rods(board)
        key = battle._recover_key(self.policy, board, held)
        self.assertEqual(self.policy.last_reason, battle.RESTORE_STATS_REASON)
        self.assertTrue(key.startswith("E"), key)  # the mushroom
        self.assertFalse(any((item.tval, item.sval) == angband_finale.RESTORING
                             for item in self.recorded.inventory))
        self.assertIsNone(battle._recover_key(self.policy, self.restoring_board(), held))  # none
        # Nothing drained: no restoring.
        held.phase = battle.RECOVER
        undrained = replace(board, player=replace(board.player, drained_stats=()))
        self.assertIsNone(battle._recover_key(self.policy, undrained, held))

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
        finale_prep.phase(policy).lifted = False
        self.assertIsNone(battle.key(policy, floor))  # not lifted: nothing
        finale_prep.phase(policy).lifted = True
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

    def test_small_floor_in_town_before_the_recall(self):
        """Q8 「町で、99F・100Fへ帰還する前に入れる」: in place of the town's recall to Angband."""
        policy = self.policy
        town = replace(self.floor(98), floor_key=(0, 0, 0), town_flag=True,
                       dungeon_recall_depths={**self.recorded.dungeon_recall_depths, 1: 95})
        policy.last_reason = "town:recall-to-angband"
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy._angband_finale_small_floor_key(town, "rfa")
        self.assertEqual((key, policy.last_reason),
                         (angband_finale.SMALL_FLOOR_MACRO, angband_finale.SMALL_FLOOR_REASON))
        policy.last_reason = "town:recall-to-yeek-cave"
        angband_finale.memory(policy).small_floor_pending = None
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(policy._angband_finale_small_floor_key(town, "rfy"), "rfy")

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
