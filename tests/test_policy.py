import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import hengbot.policy as policy_module

from hengbot.town_maps import TownMap, parse_town_map
from hengbot.model import (
    DUNGEON_ANGBAND,
    DUNGEON_YEEK_CAVE,
    PLAYER_CLASS_WARRIOR,
    STORE_ALCHEMIST,
    STORE_ARMOURY,
    STORE_BLACK,
    STORE_GENERAL,
    STORE_HOME,
    STORE_MAGIC,
    STORE_TEMPLE,
    STORE_WEAPON,
    SV_DIGGING_SHOVEL,
    SV_FLASK_OIL,
    SV_LITE_LANTERN,
    SV_LITE_TORCH,
    SV_POTION_CURE_CRITICAL,
    SV_POTION_SPEED,
    SV_POTION_HEALING,
    SV_POTION_RESIST_COLD,
    SV_POTION_RESTORE_STR,
    SV_POTION_RESTORE_CON,
    SV_POTION_INC_STR,
    SV_POTION_AUGMENTATION,
    SV_POTION_SLEEP,
    SV_ROD_IDENTIFY,
    SV_ROD_LITE,
    SV_SCROLL_WORD_OF_RECALL,
    SV_SCROLL_REMOVE_CURSE,
    SV_SCROLL_STAR_REMOVE_CURSE,
    SV_SCROLL_DETECT_TREASURE,
    SV_SCROLL_HOLY_CHANT,
    SV_SCROLL_IDENTIFY,
    SV_SCROLL_STAR_IDENTIFY,
    SV_SCROLL_TELEPORT,
    SV_SCROLL_STAR_DESTRUCTION,
    SV_STAFF_DESTRUCTION,
    SV_STAFF_IDENTIFY,
    TVAL_BOTTLE,
    TVAL_ARROW,
    TVAL_CHEST,
    TVAL_SHOT,
    TVAL_BOW,
    SV_BOW_SLING,
    SV_BOW_SHORT,
    TVAL_DIGGING,
    TVAL_FLASK,
    TVAL_AMULET,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_CHAOS_BOOK,
    TVAL_LIFE_BOOK,
    TVAL_HISSATSU_BOOK,
    TVAL_POTION,
    TVAL_RING,
    TVAL_ROD,
    TVAL_SCROLL,
    TVAL_STAFF,
    TVAL_SWORD,
    TVAL_WAND,
    GridState,
    InventoryItem,
    MonsterState,
    PlayerState,
    Position,
    QuestState,
    Snapshot,
    StoreItem,
    StoreState,
    _parse_store,
)
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.equipment_optimizer import TR_TELEPORT
from hengbot.monrace_knowledge import (
    MonraceKnowledge, MonsterBlow, load_monrace_knowledge,
)
from hengbot.quest_knowledge import (
    QUEST_FLAG_ONCE, QUEST_TYPE_KILL_LEVEL, QuestBattlefield, QuestInfo,
    load_quest_knowledge,
)
from hengbot.quest_strategies import load_quest_strategies
from hengbot.projection_path import projection_path
from hengbot.policy import (
    HengbotPolicy,
    BUY_KEY,
    CHARACTER_DUMP_MACRO,
    DESTROY_FAIL_LIMIT,
    EMPTY_DIVE_LIMIT,
    OVEREXTEND_LOOT_MAX,
    RANGED_MAX_DISTANCE,
    UNUSED_DIVE_LIMIT,
    SELL_KEY,
    SELL_CONFIRM_SUFFIX,
    READ_KEY,
    STUCK_ESCAPE_LIMIT,
    TOWN_WANDER_LIMIT,
    STORE_RETRY_TURNS,
    STAFF_IDENTIFY_MIN_DEPTH,
    TELEPORT_RETURN_THRESHOLD,
    TELEPORT_SCROLL_DEEP_TARGET,
    STAFF_IDENTIFY_MAX_COUNT,
    IDENTIFY_PRESSURE_FREE_SLOTS,
    IDENTIFY_FAIL_LIMIT,
    IDENTIFY_CHARGE_FLOOR,
    IDENTIFY_PURCHASE_MAX,
    RECALL_MIN_DEPTH,
    SUPPLY_THRESHOLDS,
    RESUME_DESCENT_BLOCK_DECISIONS,
    DEEP_FUNDRAISING_DEPTH,
    DEEP_FUNDRAISING_DETECTION_RADIUS,
    DEEP_FUNDRAISING_SCROLLS_PER_RUN,
    FUNDRAISING_GOLD_TARGET,
    FUNDRAISING_KIT_RESERVE,
    FUNDRAISING_START_GOLD,
    FIXED_QUEST_LEVEL_MARGIN,
    QUEST_STATUS_COMPLETED,
    QUEST_STATUS_REWARDED,
    QUEST_STATUS_TAKEN,
    QUEST_STATUS_UNTAKEN,
    FOOD_MIN_SVAL,
    OIL_TARGET,
    AMMO_PURCHASE_TARGET,
    TORCH_THROW_TARGET,
    CHEST_SEARCH_BUDGET,
    CHEST_DISARM_BUDGET,
    CHEST_OPEN_BUDGET,
    LIVELOCK_LIMIT,
    LEAVE_STORE_KEY,
    MINING_RUNS_PER_SET,
    MINING_MIN_VIABLE_VEINS,
    MINING_ROUTE_REVISIT_LIMIT,
    MINING_NAVIGATION_REVISIT_LIMIT,
    MINING_STALL_LIMIT,
    MINING_SWEEP_HARD_LIMIT,
    MINING_SWEEP_NO_PROGRESS_LIMIT,
    MIN_FREE_PACK_SLOTS,
    HOME_BATCH_RESERVED_SLOTS,
    PACK_CAPACITY,
    REST_MACRO,
    RESTOCK_WAIT_MACRO,
    STUCK_WINDOW,
    DOOR_OPEN_LIMIT,
    RUBBLE_DIG_LIMIT,
    SEARCH_LIMIT,
    STORE_STUCK_LIMIT,
    SHOP_APPROACH_STUCK_LIMIT,
    TUNNEL_KEY,
    TR_NO_TELE,
    TOWN_CYCLE_WINDOW,
    TOWN_CYCLE_IGNORED_REASONS,
    TOWN_TRAVEL_STALL_LIMIT,
    TOWN_TRAVEL_TURN_STALL_LIMIT,
    TOWN_STOP_PASS_LIMIT,
    TownTravelProgress,
    TownNeed,
    TOWN_NO_PROGRESS_LIMIT,
    WAIT_KEY,
)


def store_item(letter, tval, sval, *, price=100, count=1, name="wares", **kwargs):
    return StoreItem(
        letter=letter,
        name=name,
        count=count,
        tval=tval,
        sval=sval,
        price=price,
        **kwargs,
    )


def grid(
    y,
    x,
    *,
    known=True,
    passable=True,
    monster=False,
    downstairs=False,
    upstairs=False,
    closed_door=False,
    open_door=False,
    unsafe=False,
    trap=False,
    objects=0,
    entrance=False,
    rubble=False,
    gold=False,
    can_dig=False,
    entrance_dungeon_id=-1,
    building_type=-1,
    has_quest_enter=False,
    has_quest_exit=False,
    quest_id=-1,
    building_special=-1,
):
    pos = Position(y, x)
    walkable = (passable and not closed_door and not rubble) or open_door
    return GridState(
        position=pos,
        known=known,
        passable=known and walkable,
        wall=known and not passable and not closed_door and not open_door and not rubble,
        has_monster=monster,
        has_down_stairs=downstairs,
        has_up_stairs=upstairs,
        unsafe=unsafe,
        is_closed_door=known and closed_door,
        is_door=known and (closed_door or open_door),
        trap=trap,
        object_count=objects,
        has_entrance=entrance,
        can_dig=known and (rubble or can_dig),
        has_gold=known and gold,
        entrance_dungeon_id=entrance_dungeon_id,
        building_type=building_type,
        has_quest_enter=known and has_quest_enter,
        has_quest_exit=known and has_quest_exit,
        quest_id=quest_id if known else -1,
        building_special=building_special if known else -1,
    )


def player(y, x, *, hp=20, max_hp=20, mp=0, max_mp=0, level=1, food=12000, food_type=0, gold=FUNDRAISING_START_GOLD, word_recall=0, afraid=False, confused=False, blind=False, poisoned=False, cut=False, class_id=-1, main_hand_blows=0, main_hand_to_h=0, main_hand_to_d=0, drained_stats=(), abilities=frozenset(), speed=110):
    if food < 500:
        food_state = "fainting"
    elif food < 1000:
        food_state = "weak"
    elif food < 2000:
        food_state = "hungry"
    elif food < 10000:
        food_state = "normal"
    elif food < 15000:
        food_state = "full"
    else:
        food_state = "gorged"
    return PlayerState(
        Position(y, x),
        hp=hp,
        max_hp=max_hp,
        mp=mp,
        max_mp=max_mp,
        level=level,
        food_state=food_state,
        gold=gold,
        recalling=word_recall > 0,
        food_type=food_type,
        afraid=afraid,
        confused=confused,
        blind=blind,
        poisoned=poisoned,
        cut=cut,
        class_id=class_id,
        main_hand_blows=main_hand_blows,
        main_hand_to_h=main_hand_to_h,
        main_hand_to_d=main_hand_to_d,
        drained_stats=drained_stats,
        abilities=abilities,
        speed=speed,
    )


def item(
    slot,
    tval,
    sval,
    *,
    aware=True,
    known=None,
    fully_known=False,
    count=1,
    name="item",
    charges=0,
    fuel=0,
    is_equipment=False,
    is_ego=False,
    is_artifact=False,
    is_cursed=False,
    inscription="",
    is_broken=False,
    is_bounty=False,
    to_h=0,
    to_d=0,
    to_a=0,
    ac=0,
    pval=0,
    known_flags=frozenset(),
    damage_dice_num=0,
    damage_dice_sides=0,
    pseudo_feeling="",
):
    if known is None:
        known = aware
    return InventoryItem(
        slot=slot, name=name, count=count, tval=tval, sval=sval, aware=aware,
        known=known, fully_known=fully_known, charges=charges, fuel=fuel,
        is_equipment=is_equipment, is_ego=is_ego, is_artifact=is_artifact,
        is_cursed=is_cursed, inscription=inscription, is_broken=is_broken,
        to_h=to_h, to_d=to_d,
        is_bounty=is_bounty,
        to_a=to_a, ac=ac, pval=pval, known_flags=known_flags,
        damage_dice_num=damage_dice_num,
        damage_dice_sides=damage_dice_sides,
        pseudo_feeling=pseudo_feeling,
    )


def hostile(
    index,
    y,
    x,
    *,
    hp=10,
    max_hp=10,
    distance=1,
    asleep=False,
    speed=110,
    can_summon=False,
    can_multiply=False,
    max_melee_damage=0,
    max_ranged_damage=0,
):
    return MonsterState(
        index=index,
        position=Position(y, x),
        hp=hp,
        max_hp=max_hp,
        distance=distance,
        friendly=False,
        pet=False,
        speed=speed,
        asleep=asleep,
        can_summon=can_summon,
        can_multiply=can_multiply,
        max_melee_damage=max_melee_damage,
        max_ranged_damage=max_ranged_damage,
    )


class CombatTest(unittest.TestCase):
    def test_attacks_adjacent_hostile(self):
        grids = {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11, monster=True)}
        snap = Snapshot(player(10, 10), grids, [hostile(1, 10, 11, hp=3)])
        self.assertEqual(HengbotPolicy().choose_key(snap), "6")

    def test_attacks_an_adjacent_hallucinated_monster(self):
        # A hallucinated monster arrives with unknown (sentinel) HP and no race;
        # the bot must still melee it rather than rest or wander into it.
        from hengbot.model import UNKNOWN_MONSTER_HP

        grids = {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11, monster=True)}
        mon = hostile(1, 10, 11, hp=UNKNOWN_MONSTER_HP, max_hp=UNKNOWN_MONSTER_HP)
        snap = Snapshot(player(10, 10, hp=100, max_hp=100), grids, [mon])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "6")
        self.assertEqual(pol.last_reason, "melee")

    def test_attacks_weakest_adjacent_first(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, monster=True),
            Position(10, 9): grid(10, 9, monster=True),
        }
        monsters = [hostile(1, 10, 11, hp=9), hostile(2, 10, 9, hp=2)]
        # The 2-hp monster to the west should be struck first.
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, monsters)), "4")

    def test_retreats_when_low_hp(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 11): grid(10, 11, monster=True),
        }
        snap = Snapshot(player(10, 10, hp=2, max_hp=20), grids, [hostile(1, 10, 11, hp=10)])
        self.assertEqual(HengbotPolicy().choose_key(snap), "4")

    def test_prioritizes_an_adjacent_summoner(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9, monster=True),
            Position(10, 11): grid(10, 11, monster=True),
        }
        monsters = [
            hostile(1, 10, 9, hp=100, max_hp=100, can_summon=True),
            hostile(2, 10, 11, hp=1, max_hp=10),
        ]
        self.assertEqual(
            HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, monsters)),
            "4",
        )

    def test_retreats_from_an_open_summoner_fight_to_a_corridor(self):
        grids = {}
        for y in range(9, 12):
            for x in range(9, 12):
                grids[Position(y, x)] = grid(y, x)
        grids[Position(9, 9)] = grid(9, 9, passable=False)
        grids[Position(11, 9)] = grid(11, 9, passable=False)
        grids[Position(10, 8)] = grid(10, 8)
        grids[Position(10, 7)] = grid(10, 7)
        grids[Position(10, 12)] = grid(10, 12)
        grids[Position(10, 13)] = grid(10, 13, monster=True)
        summoner = hostile(
            1, 10, 13, hp=80, max_hp=80, distance=3, can_summon=True
        )
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100), grids, [summoner],
            floor_key=(1, 5, 0),
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "4")
        self.assertEqual(pol.last_reason, "summoner:retreat")

    def test_does_not_retreat_from_a_sleeping_summoner(self):
        grids = {
            Position(y, x): grid(y, x)
            for y in range(9, 12)
            for x in range(7, 14)
        }
        grids[Position(9, 9)] = grid(9, 9, passable=False)
        grids[Position(11, 9)] = grid(11, 9, passable=False)
        grids[Position(10, 13)] = grid(10, 13, monster=True)
        summoner = hostile(
            1, 10, 13, hp=80, max_hp=80, distance=3,
            asleep=True, can_summon=True,
        )
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100), grids, [summoner],
            floor_key=(1, 5, 0),
        )
        pol = HengbotPolicy()

        key = pol.choose_key(snap)

        self.assertNotEqual(pol.last_reason, "summoner:retreat")
        self.assertNotEqual(key, "4")

    def test_sleeping_quest_summoner_does_not_flip_flop_with_loot(self):
        quest_info = QuestInfo(
            14, "Warg Problem", 5, 5, 2, dungeon=0,
            num_mon=16, monrace_id=257,
        )
        quest = QuestState(
            id=14, status=QUEST_STATUS_TAKEN, type=5, level=5,
            dungeon_id=0, r_idx=257, cur_num=11, num_mon=16, fixed=True,
        )
        policy = HengbotPolicy(quest_knowledge={14: quest_info})
        loot = Position(10, 9)
        position = Position(10, 10)
        positions = [position]
        reasons = []
        direction_delta = {
            "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
            "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
        }

        with (
            patch.object(policy, "_emergency_item", return_value=None),
            patch.object(policy, "_fixed_quest_key", return_value=None),
        ):
            for _ in range(3):
                monster_position = Position(10, 14)
                grids = {
                    Position(y, grid_x): grid(y, grid_x)
                    for y in range(9, 12)
                    for grid_x in range(9, 15)
                }
                grids[loot] = grid(loot.y, loot.x, objects=1)
                grids[monster_position] = grid(
                    monster_position.y, monster_position.x, monster=True
                )
                summoner = hostile(
                    1, monster_position.y, monster_position.x,
                    hp=80, max_hp=80,
                    distance=position.distance_to(monster_position),
                    asleep=True, can_summon=True,
                )
                snap = Snapshot(
                    player(position.y, position.x, hp=605, max_hp=605),
                    grids, [summoner],
                    floor_key=(0, 5, 14), quests={14: quest},
                )

                key = policy.choose_key(snap)
                reasons.append(policy.last_reason)
                self.assertIn(key, direction_delta)
                dy, dx = direction_delta[key]
                next_position = Position(position.y + dy, position.x + dx)
                self.assertLess(
                    next_position.distance_to(monster_position),
                    position.distance_to(monster_position),
                )
                position = next_position
                positions.append(position)

        self.assertNotIn("summoner:retreat", reasons)
        self.assertNotIn("seek-loot", reasons)
        self.assertEqual(len(set(positions)), len(positions))

    def test_flees_even_from_an_almost_dead_enemy_when_low_hp(self):
        # Coarse visible health is useful for target choice, but must not justify
        # continuing combat once the player has crossed the survival threshold.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 11): grid(10, 11, monster=True),
        }
        snap = Snapshot(player(10, 10, hp=20, max_hp=150), grids, [hostile(1, 10, 11, hp=36)])
        self.assertEqual(HengbotPolicy().choose_key(snap), "4")

    def test_still_flees_strong_lone_enemy(self):
        # Same low HP, but the lone enemy is too tough to finish (hp 100 > 60), so
        # the flee still triggers and we back away west.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 11): grid(10, 11, monster=True),
        }
        snap = Snapshot(player(10, 10, hp=20, max_hp=150), grids, [hostile(1, 10, 11, hp=100)])
        self.assertEqual(HengbotPolicy().choose_key(snap), "4")

    def test_still_flees_multiple_weak_enemies(self):
        # The finish-it exception is only for a single adjacent threat; two weak
        # enemies still trigger the low-HP flee.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9, monster=True),
            Position(10, 11): grid(10, 11, monster=True),
            Position(9, 10): grid(9, 10),
        }
        monsters = [hostile(1, 10, 11, hp=20), hostile(2, 10, 9, hp=20)]
        snap = Snapshot(player(10, 10, hp=20, max_hp=150), grids, monsters)
        # Flees rather than melee (two adjacent threats defeat the lone-enemy rule).
        pol = HengbotPolicy()
        pol.choose_key(snap)
        self.assertEqual(pol.last_reason, "flee")

    def test_immediately_ascends_when_surrounded_on_landing_stairs(self):
        # Live death on dl9: the bot arrived at full HP on an upstairs tile with
        # ten visible hostiles and several adjacent, but meleed until too hurt to
        # escape. A landing swarm must trigger an immediate retreat upstairs.
        grids = {
            Position(10, 10): grid(10, 10, upstairs=True),
            Position(9, 10): grid(9, 10, monster=True),
            Position(10, 11): grid(10, 11, monster=True),
            Position(11, 10): grid(11, 10, monster=True),
        }
        # Dangerous swarm (10/hit each): three adjacent carve ~120 over the
        # lookahead — past the flee threshold (0.6*175=105) but under a lethal
        # 175, so this is the swarm-flee path (not the emergency one) and the
        # landing must retreat upstairs.
        monsters = [
            hostile(1, 9, 10, hp=20, max_melee_damage=10),
            hostile(2, 10, 11, hp=20, max_melee_damage=10),
            hostile(3, 11, 10, hp=20, max_melee_damage=10),
        ]
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(Snapshot(player(10, 10, hp=175, max_hp=175), grids, monsters)), "<")
        self.assertEqual(pol.last_reason, "flee:stairs")

    def test_stays_and_fights_a_weak_landing_swarm_at_full_hp(self):
        # Regression for over-fleeing: a clvl20 warrior landed on dl9 amid three
        # adjacent but weak (lvl-9 Skaven-class, ~10/hit) hostiles and stair-scummed
        # away every descent. At full HP a swarm this soft is not worth fleeing —
        # its predicted damage is far below the threshold — so fight, don't ascend.
        grids = {
            Position(10, 10): grid(10, 10, upstairs=True),
            Position(9, 10): grid(9, 10, monster=True),
            Position(10, 11): grid(10, 11, monster=True),
            Position(11, 10): grid(11, 10, monster=True),
        }
        monsters = [
            hostile(1, 9, 10, hp=20, max_melee_damage=10, asleep=True),
            hostile(2, 10, 11, hp=20, max_melee_damage=10, asleep=True),
            hostile(3, 11, 10, hp=20, max_melee_damage=10, asleep=True),
        ]
        pol = HengbotPolicy()
        key = pol.choose_key(Snapshot(player(10, 10, hp=401, max_hp=401), grids, monsters))
        self.assertNotEqual(key, "<")
        self.assertNotIn("flee", pol.last_reason)

    def test_attacks_friendly_in_town(self):
        friendly = MonsterState(1, Position(10, 11), hp=10, max_hp=10, distance=1, friendly=True, pet=False)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, downstairs=True),
        }
        self.assertEqual(
            HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [friendly])),
            "+6y",
        )


class UnseenAttackerTest(unittest.TestCase):
    def _open_grids(self, cy, cx, extra=None):
        grids = {}
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                grids[Position(cy + dy, cx + dx)] = grid(cy + dy, cx + dx)
        for pos, g in (extra or {}).items():
            grids[pos] = g
        return grids

    def test_does_not_rest_while_bleeding_from_unseen(self):
        # No visible hostiles but HP fell between decisions → an unseen attacker;
        # resting would be fatal, so we must move instead.
        grids = self._open_grids(10, 10)
        pol = HengbotPolicy()
        pol.choose_key(
            Snapshot(player(10, 10, hp=120, max_hp=200), grids, [], turn=1, floor_key=(1, 5, 0))
        )
        key = pol.choose_key(
            Snapshot(player(10, 10, hp=95, max_hp=200), grids, [], turn=2, floor_key=(1, 5, 0))
        )
        self.assertNotEqual(key, REST_MACRO)
        self.assertTrue(pol.last_reason.startswith("unseen"), pol.last_reason)

    def test_flees_to_upstairs_when_bleeding_unseen(self):
        grids = {Position(10, x): grid(10, x) for x in range(10, 14)}
        grids[Position(10, 14)] = grid(10, 14, upstairs=True)
        pol = HengbotPolicy()
        pol.choose_key(
            Snapshot(player(10, 10, hp=120, max_hp=200), grids, [], turn=1, floor_key=(1, 5, 0))
        )
        key = pol.choose_key(
            Snapshot(player(10, 10, hp=95, max_hp=200), grids, [], turn=2, floor_key=(1, 5, 0))
        )
        self.assertEqual(key, "6")  # step east toward the up stairs
        self.assertEqual(pol.last_reason, "unseen:flee-stairs")

    def test_still_rests_when_hp_not_dropping(self):
        # HP steady/rising with no hostiles is the normal heal-up case.
        grids = self._open_grids(10, 10)
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(Snapshot(player(10, 10, hp=60, max_hp=200), grids, [], turn=1)), REST_MACRO)
        # HP went up (rest is working) → keep resting.
        self.assertEqual(pol.choose_key(Snapshot(player(10, 10, hp=75, max_hp=200), grids, [], turn=2)), REST_MACRO)


class ShoppingTest(unittest.TestCase):
    def _in_store(self, items, *, gold=1000, inv=None, eq=None):
        grids = {Position(10, 10): grid(10, 10)}
        return Snapshot(
            player(10, 10, gold=gold),
            grids,
            [],
            inventory=inv or [],
            equipment=eq or [],
            store=StoreState(store_type=STORE_GENERAL, items=items),
        )

    def test_buys_lantern_first(self):
        items = [
            store_item("a", TVAL_LITE, SV_LITE_TORCH, price=1),
            store_item("b", TVAL_LITE, SV_LITE_LANTERN, price=120),
            store_item("c", TVAL_FLASK, SV_FLASK_OIL, price=3),
        ]
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(self._in_store(items)), "pb\r")
        self.assertEqual(pol.last_reason, "shop:buy-lantern")

    def test_buys_oil_once_lantern_owned(self):
        items = [store_item("c", TVAL_FLASK, SV_FLASK_OIL, price=3, count=42)]
        inv = [InventoryItem("e", "lantern", 1, TVAL_LITE, SV_LITE_LANTERN, True, True)]
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(self._in_store(items, inv=inv)), "pc5\r\r")
        self.assertEqual(pol.last_reason, "shop:buy-oil")

    def test_does_not_sell_only_lantern_while_empty_torch_is_equipped(self):
        lantern = item(
            "d", TVAL_LITE, SV_LITE_LANTERN, name="brass lantern", fuel=7500
        )
        empty_torch = item(
            "light",
            TVAL_LITE,
            SV_LITE_TORCH,
            name="empty torch",
            fuel=0,
            is_equipment=True,
        )
        snap = self._in_store([], inv=[lantern], eq=[empty_torch])

        self.assertIsNone(HengbotPolicy()._find_light_sale(snap))

    def test_sells_lantern_only_when_working_lantern_is_already_equipped(self):
        spare = item(
            "d", TVAL_LITE, SV_LITE_LANTERN, name="spare lantern", fuel=7500
        )
        equipped = item(
            "light",
            TVAL_LITE,
            SV_LITE_LANTERN,
            name="equipped lantern",
            fuel=5000,
            is_equipment=True,
        )
        snap = self._in_store([], inv=[spare], eq=[equipped])

        self.assertEqual(HengbotPolicy()._find_light_sale(snap), spare)

    def test_leaves_when_done(self):
        items = [store_item("c", TVAL_FLASK, SV_FLASK_OIL, price=3)]
        # Own a lantern and plenty of oil already → nothing to buy → leave.
        inv = [
            InventoryItem("e", "lantern", 1, TVAL_LITE, SV_LITE_LANTERN, True, True),
            InventoryItem("f", "oil", 9, TVAL_FLASK, SV_FLASK_OIL, True, True),
        ]
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(self._in_store(items, inv=inv)), "\x1b")
        self.assertEqual(pol.last_reason, "shop:leave")

    def test_leaves_store_when_purchase_never_registers(self):
        # The buy never takes effect (gold stays put), so after STORE_STUCK_LIMIT
        # identical attempts the bot bails out instead of hammering the macro — a
        # store has no loop-detector or stall exit to save it otherwise.
        items = [store_item("b", TVAL_LITE, SV_LITE_LANTERN, price=120)]
        pol = HengbotPolicy()
        snap = self._in_store(items, gold=1000)  # gold never drops between calls
        keys = [pol.choose_key(snap) for _ in range(STORE_STUCK_LIMIT + 1)]
        self.assertIn("pb\r", keys)  # it did try to buy
        self.assertIn("\x1b", keys)  # and eventually gave up and left
        self.assertTrue(pol._shopping_abandoned)
        self.assertIn(STORE_GENERAL, pol._town_store_attempted)

    def test_gives_up_when_lantern_unaffordable(self):
        items = [store_item("b", TVAL_LITE, SV_LITE_LANTERN, price=500)]
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(self._in_store(items, gold=50)), "\x1b")
        self.assertTrue(pol._shopping_abandoned)

    def test_approaches_general_store_in_town(self):
        # Town (dungeon 0, level 0), gold, no lantern, a store tile to the east.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12),
        }
        grids[Position(10, 12)] = GridState(
            position=Position(10, 12), known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_GENERAL,
        )
        snap = Snapshot(player(10, 10, gold=1000), grids, [], floor_key=(0, 0, 0))
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "6")
        self.assertEqual(pol.last_reason, "shop:approach")

    def test_uses_native_travel_for_a_distant_town_store(self):
        walkable = frozenset(Position(10, x) for x in range(1, 16))
        town_map = TownMap(
            name="T",
            width=20,
            height=20,
            walkable=walkable,
            stores={STORE_GENERAL: Position(10, 15)},
        )
        grids = {Position(10, x): grid(10, x) for x in range(1, 16)}
        grids[Position(10, 15)] = GridState(
            position=Position(10, 15), known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_GENERAL,
        )
        snap = Snapshot(
            player(10, 1, gold=1000), grids, [], floor_key=(0, 0, 0),
            width=20, height=20, town_flag=True,
            inventory=[item("a", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )

        pol = HengbotPolicy(town_map=town_map)
        self.assertEqual(pol.choose_key(snap), "wa")
        self.assertEqual(pol.last_reason, "wield-light")
        snap = replace(
            snap,
            inventory=[],
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )
        self.assertEqual(pol.choose_key(snap), "\x1b`n!.")
        self.assertEqual(pol.last_reason, "shop:travel")

    def test_distant_store_without_any_light_walks(self):
        walkable = frozenset(Position(10, x) for x in range(1, 16))
        goal = Position(10, 15)
        town_map = TownMap(
            name="T", width=20, height=20, walkable=walkable,
            stores={STORE_GENERAL: goal},
        )
        grids = {Position(10, x): grid(10, x) for x in range(1, 16)}
        grids[goal] = replace(grid(10, 15), store_number=STORE_GENERAL)
        snap = Snapshot(
            player(10, 1, gold=1000), grids, [], floor_key=(0, 0, 0),
            width=20, height=20, town_flag=True,
        )

        pol = HengbotPolicy(town_map=town_map)
        self.assertEqual(pol.choose_key(snap), "6")
        self.assertEqual(pol.last_reason, "shop:approach")
        self.assertIsNone(pol._town_travel_state)

    def test_interrupted_town_travel_retries_then_falls_back(self):
        walkable = frozenset(Position(10, x) for x in range(1, 16))
        goal = Position(10, 15)
        town_map = TownMap(
            name="T", width=20, height=20, walkable=walkable,
            stores={STORE_GENERAL: goal},
        )
        grids = {Position(10, x): grid(10, x) for x in range(1, 16)}
        grids[goal] = GridState(
            position=goal, known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_GENERAL,
        )
        first = Snapshot(
            player(10, 1, gold=1000), grids, [], floor_key=(0, 0, 0),
            width=20, height=20, town_flag=True, turn=1,
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )
        interrupted = Snapshot(
            player(10, 5, gold=1000), grids, [], floor_key=(0, 0, 0),
            width=20, height=20, town_flag=True, turn=2,
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )

        pol = HengbotPolicy(town_map=town_map)
        self.assertEqual(pol.choose_key(first), "\x1b`n!.")
        # Interrupted mid-route but CLOSER than before: travel again instead of
        # walking the remaining ten tiles one decision each.
        self.assertEqual(pol.choose_key(interrupted), "\x1b`n!.")
        self.assertEqual(pol.last_reason, "shop:travel")
        # No progress across two more issues: give the goal back to walking.
        for _ in range(TOWN_TRAVEL_STALL_LIMIT - 1):
            self.assertEqual(pol.choose_key(interrupted), "\x1b`n!.")
        self.assertEqual(
            pol.choose_key(interrupted),
            "6",
        )
        self.assertEqual(pol.last_reason, "shop:approach")
        self.assertEqual(pol.choose_key(interrupted), "6")

    def test_eats_before_distant_town_travel(self):
        walkable = frozenset(Position(10, x) for x in range(1, 16))
        town_map = TownMap(
            name="T", width=20, height=20, walkable=walkable,
            stores={STORE_GENERAL: Position(10, 15)},
        )
        grids = {Position(10, x): grid(10, x) for x in range(1, 16)}
        ration = InventoryItem(
            "a", "ration", 1, TVAL_FOOD, FOOD_MIN_SVAL, True, True
        )
        snap = Snapshot(
            player(10, 1, food=1500, gold=1000), grids, [],
            floor_key=(0, 0, 0), inventory=[ration],
            width=20, height=20, town_flag=True,
        )

        pol = HengbotPolicy(town_map=town_map)
        self.assertEqual(pol.choose_key(snap), "Ea")
        self.assertEqual(pol.last_reason, "town:eat-before-travel")

    def test_breaks_out_when_store_approach_move_is_rejected(self):
        grids = {
            Position(9, 10): grid(9, 10),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): GridState(
                position=Position(10, 12), known=True, passable=True, wall=False,
                has_monster=False, has_down_stairs=False, has_up_stairs=False,
                unsafe=False, store_number=STORE_GENERAL,
            ),
        }
        snap = Snapshot(player(10, 10, gold=1000), grids, [], floor_key=(0, 0, 0))
        pol = HengbotPolicy()

        keys = [pol.choose_key(snap) for _ in range(LIVELOCK_LIMIT + 1)]

        self.assertEqual(keys[-1], "8")
        self.assertEqual(pol.last_reason, "breakout")

    def test_store_approach_paths_to_the_store_even_when_oscillating(self):
        # Regression: the old oscillation-breakout returned _least_visited_neighbor
        # (a step toward unexplored tiles), which in a fully-known town marched the
        # bot to the map edge and across into the open wilderness (a fatal Cyclops
        # run). Store-approach must now always path straight to the store instead.
        grids = {
            Position(9, 10): grid(9, 10),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): GridState(
                position=Position(10, 12), known=True, passable=True, wall=False,
                has_monster=False, has_down_stairs=False, has_up_stairs=False,
                unsafe=False, store_number=STORE_GENERAL,
            ),
        }
        pol = HengbotPolicy()
        key = ""
        for index in range(STUCK_WINDOW + 1):
            x = 10 if index % 2 == 0 else 11
            snap = Snapshot(player(10, x, gold=1000), grids, [], floor_key=(0, 0, 0))
            key = pol.choose_key(snap)

        self.assertEqual(key, "6")  # east, toward the store at (10,12) — never "8"
        self.assertEqual(pol.last_reason, "shop:approach")

    def test_store_approach_failure_does_not_block_later_shopping(self):
        # If the approach keeps oscillating WITHOUT arriving for long enough (a truly
        # unreachable entrance), abandon shopping this visit before the loop guard
        # stops the bot — set _shopping_stuck rather than bounce forever.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): GridState(
                position=Position(10, 12), known=True, passable=True, wall=False,
                has_monster=False, has_down_stairs=False, has_up_stairs=False,
                unsafe=False, store_number=STORE_GENERAL,
            ),
        }
        pol = HengbotPolicy()
        for index in range(SHOP_APPROACH_STUCK_LIMIT + STUCK_WINDOW + 2):
            x = 10 if index % 2 == 0 else 11
            snap = Snapshot(player(10, x, gold=1000), grids, [], floor_key=(0, 0, 0))
            pol.choose_key(snap)
        self.assertFalse(pol._shopping_stuck)
        self.assertIn(STORE_GENERAL, pol._town_store_attempted)

    def test_no_approach_without_gold(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }
        grids[Position(10, 11)] = GridState(
            position=Position(10, 11), known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_GENERAL,
        )
        snap = Snapshot(player(10, 10, gold=0), grids, [], floor_key=(0, 0, 0))
        pol = HengbotPolicy()
        pol.choose_key(snap)
        self.assertNotEqual(pol.last_reason, "shop:approach")

    def test_upgrades_torch_to_lantern(self):
        grids = {Position(10, 10): grid(10, 10)}
        torch_eq = InventoryItem("f", "torch", 1, TVAL_LITE, SV_LITE_TORCH, True, True, fuel=1000)
        lantern_inv = InventoryItem("e", "lantern", 1, TVAL_LITE, SV_LITE_LANTERN, True, True, fuel=7500)
        snap = Snapshot(player(10, 10), grids, [], inventory=[lantern_inv], equipment=[torch_eq])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "we")
        self.assertEqual(pol.last_reason, "wield-light")


class RubbleTest(unittest.TestCase):
    def test_tunnels_through_rubble_frontier(self):
        # A pile of rubble to the east caps the passage; it is the only frontier,
        # so the bot digs into it with raw 'T'+direction rather than
        # treating it as a wall (which would strand it).
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, rubble=True),
        }
        snap = Snapshot(player(10, 10), grids, [], width=40, height=40)
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "T6")

    def test_gives_up_on_immovable_rubble(self):
        # Boxed by walls with only the (never-clearing) rubble to the east; after
        # RUBBLE_DIG_LIMIT digs it is abandoned so the bot doesn't grind forever.
        grids = {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11, rubble=True)}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if (dy, dx) == (0, 0) or (dy, dx) == (0, 1):
                    continue
                grids[Position(10 + dy, 10 + dx)] = grid(10 + dy, 10 + dx, passable=False)
        snap = Snapshot(player(10, 10), grids, [], width=40, height=40)
        pol = HengbotPolicy()
        # Enough turns for the stuck-spot searches plus RUBBLE_DIG_LIMIT digs.
        keys = [pol.choose_key(snap) for _ in range(RUBBLE_DIG_LIMIT + 20)]
        self.assertIn("T6", keys)
        self.assertIn((10, 11), pol._blocked_rubble)


class SearchTest(unittest.TestCase):
    def test_sweeps_room_perimeter_for_a_hidden_exit(self):
        grids = {}
        for y in range(9, 14):
            for x in range(9, 14):
                border = y in {9, 13} or x in {9, 13}
                grids[Position(y, x)] = grid(y, x, passable=not border)
        grids[Position(11, 11)] = grid(11, 11, upstairs=True)
        snap = Snapshot(
            player(11, 11), grids, [], floor_key=(2, 4, 0), width=30, height=30
        )
        pol = HengbotPolicy()
        pol._floor_key = snap.floor_key
        pol._build_grid_index(snap)
        pol._visit_counts.update(
            {Position(y, x): 1 for y in range(10, 13) for x in range(10, 13)}
        )

        pol.choose_key(snap)

        self.assertEqual(pol.last_reason, "seek-secret-wall")

    def _sealed_dead_end(self, floor_key):
        grids = {Position(10, 10): grid(10, 10)}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if (dy, dx) != (0, 0):
                    grids[Position(10 + dy, 10 + dx)] = grid(10 + dy, 10 + dx, passable=False)
        return Snapshot(player(10, 10), grids, [], floor_key=floor_key, width=40, height=40)

    def test_searches_a_sealed_dead_end(self):
        # Walled in with no reachable frontier IN A DUNGEON: the way on must be a
        # secret door, so once it recognises it is stuck the bot searches ('s').
        snap = self._sealed_dead_end((1, 5, 0))
        pol = HengbotPolicy()
        results = [(pol.choose_key(snap), pol.last_reason) for _ in range(14)]
        self.assertIn(("s", "search"), results)

    def test_never_searches_in_town(self):
        # Secret doors/passages do not exist in town, so 's' there is wasted
        # turns: the same sealed dead end on a town tile must NEVER search.
        snap = self._sealed_dead_end((0, 0, 0))  # (0,0) surface => town
        pol = HengbotPolicy()
        results = [(pol.choose_key(snap), pol.last_reason) for _ in range(14)]
        self.assertNotIn("search", [reason for _, reason in results])
        self.assertNotIn("s", [key for key, _ in results])


class WieldLightTest(unittest.TestCase):
    def test_wields_a_torch_when_nothing_is_lit(self):
        # The Half-Troll death: a stack of torches in the pack, none wielded, so it
        # walked in the dark and could not see the monster that killed it.
        grids = {Position(10, 10): grid(10, 10)}
        torch = item("e", 39, 0, name="torch", count=5, fuel=2500)
        snap = Snapshot(player(10, 10), grids, [], inventory=[torch], equipment=[])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "we")
        self.assertEqual(pol.last_reason, "wield-light")

    def test_does_not_wield_when_a_light_is_equipped(self):
        grids = {Position(10, 10): grid(10, 10)}
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[item("e", 39, 0)],
            equipment=[item("f", 39, 0)],
        )
        pol = HengbotPolicy()
        pol.choose_key(snap)
        self.assertNotEqual(pol.last_reason, "wield-light")

    def test_does_not_wield_when_no_light_carried(self):
        grids = {Position(10, 10): grid(10, 10)}
        snap = Snapshot(player(10, 10), grids, [], inventory=[item("a", 80, 32)], equipment=[])
        pol = HengbotPolicy()
        pol.choose_key(snap)
        self.assertNotEqual(pol.last_reason, "wield-light")

    def test_skips_an_expired_torch(self):
        grids = {Position(10, 10): grid(10, 10)}
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[
                item("a", TVAL_LITE, SV_LITE_TORCH),
                item("b", TVAL_LITE, SV_LITE_TORCH, fuel=2400),
            ],
        )
        self.assertEqual(HengbotPolicy().choose_key(snap), "wb")

    def test_refills_a_low_lantern_from_oil(self):
        grids = {Position(10, 10): grid(10, 10)}
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[item("b", TVAL_FLASK, SV_FLASK_OIL, name="oil", fuel=7500)],
            equipment=[item("f", TVAL_LITE, SV_LITE_LANTERN, name="lantern", fuel=900)],
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "\\Fb")
        self.assertEqual(pol.last_reason, "refill-light")

    def test_does_not_refill_a_full_lantern(self):
        grids = {Position(10, 10): grid(10, 10)}
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[item("b", TVAL_FLASK, SV_FLASK_OIL, name="oil", fuel=7500)],
            equipment=[item("f", TVAL_LITE, SV_LITE_LANTERN, name="lantern", fuel=5000)],
        )
        pol = HengbotPolicy()
        pol.choose_key(snap)
        self.assertNotEqual(pol.last_reason, "refill-light")

    def test_does_not_refill_an_unidentified_light(self):
        # An unidentified equipped light reports a redacted fuel of 0, which must
        # not be mistaken for empty — refilling it would waste a flask of oil on a
        # light that is very likely full.
        grids = {Position(10, 10): grid(10, 10)}
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[item("b", TVAL_FLASK, SV_FLASK_OIL, name="oil", fuel=7500)],
            equipment=[
                item("f", TVAL_LITE, SV_LITE_LANTERN, name="lantern", aware=False, fuel=0)
            ],
        )
        pol = HengbotPolicy()
        pol.choose_key(snap)
        self.assertNotEqual(pol.last_reason, "refill-light")


class DescendTest(unittest.TestCase):
    def test_moves_toward_downstairs(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, downstairs=True),
        }
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), "6")

    def test_clears_a_visible_monster_blocking_the_only_stair_route(self):
        # Live dl5 failure: west leads to the stairs, but a monster at x=34
        # blocks the one-cell corridor. Moving east hides it and makes the bot
        # turn west again, producing a permanent 4/6 visibility-edge loop.
        grids = {Position(24, x): grid(24, x) for x in range(30, 41)}
        grids[Position(25, 30)] = grid(25, 30, downstairs=True)
        grids[Position(24, 34)] = grid(24, 34, monster=True)
        grids[Position(24, 41)] = grid(24, 41, closed_door=True)
        for x in range(29, 43):
            grids[Position(23, x)] = grid(23, x, passable=False)
            if x != 30:
                grids[Position(25, x)] = grid(25, x, passable=False)
        grids[Position(24, 29)] = grid(24, 29, passable=False)
        grids[Position(24, 42)] = grid(24, 42, passable=False)

        monster = hostile(1, 24, 34, hp=24, max_hp=24, distance=3, speed=122)
        snap = Snapshot(
            player(24, 37, hp=99, max_hp=99), grids, [monster],
            floor_key=(1, 5, 0), width=80, height=200,
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "4")
        self.assertEqual(pol.last_reason, "clear-descent")

    def test_approaches_a_less_visited_frontier_near_unreachable_stairs(self):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(8, 13)
            for x in range(8, 16)
        }
        origin = Position(10, 10)
        near_frontier = Position(10, 11)
        fresh_frontier = Position(11, 10)
        grids[origin] = grid(origin.y, origin.x)
        grids[near_frontier] = grid(near_frontier.y, near_frontier.x)
        grids[fresh_frontier] = grid(fresh_frontier.y, fresh_frontier.x)
        grids[Position(10, 14)] = grid(10, 14, downstairs=True)
        del grids[Position(9, 12)]
        del grids[Position(12, 11)]

        policy = HengbotPolicy()
        policy._floor_key = (2, 12, 0)
        policy._visit_counts[near_frontier] = 3
        snapshot = Snapshot(
            player(origin.y, origin.x, food=12000),
            grids,
            [],
            floor_key=(2, 12, 0),
            width=30,
            height=30,
        )
        self.assertEqual(policy.choose_key(snapshot), "2")
        self.assertEqual(policy.last_reason, "approach-descent")

    def test_unreachable_stair_cycle_keeps_one_committed_target(self):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(7, 13)
            for x in range(7, 14)
        }
        origin = Position(10, 10)
        cycle = {
            origin,
            Position(10, 11),
            Position(11, 11),
            Position(11, 12),
        }
        escape = Position(10, 9)
        for position in cycle | {escape, Position(10, 8)}:
            grids[position] = grid(position.y, position.x)
        grids[Position(8, 12)] = grid(8, 12, downstairs=True)

        policy = HengbotPolicy()
        policy._floor_key = (2, 12, 0)
        policy._recent.extend(list(cycle) * 3)
        for position in cycle:
            policy._visit_counts[position] = 5
        snapshot = Snapshot(
            player(origin.y, origin.x, food=12000),
            grids,
            [],
            floor_key=(2, 12, 0),
            width=30,
            height=30,
        )
        policy.choose_key(snapshot)
        self.assertEqual(policy._nav_ledger.descent_target, Position(8, 12))
        self.assertNotEqual(policy.last_reason, "breakout:descent")

    def test_descends_when_standing_on_downstairs_and_healthy(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        snap = Snapshot(player(10, 10, hp=20, max_hp=20), grids, [])
        self.assertEqual(HengbotPolicy().choose_key(snap), ">")

    def test_descends_when_standing_on_expired_downstairs(self):
        position = Position(10, 10)
        grids = {position: grid(10, 10, downstairs=True)}
        snap = Snapshot(
            player(10, 10, hp=20, max_hp=20),
            grids,
            [],
            floor_key=(1, 8, 0),
        )
        policy = HengbotPolicy()
        policy._floor_key = snap.floor_key
        policy._nav_ledger.expire("descend", position)

        self.assertEqual(policy.choose_key(snap), ">")
        self.assertEqual(policy.last_reason, "descend")

    def test_rests_before_descending_when_hurt_then_descends(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        policy = HengbotPolicy()
        # A dungeon floor (not the town recover path).
        hurt = Snapshot(player(10, 10, hp=10, max_hp=100), grids, [], turn=1, floor_key=(1, 5, 0))
        self.assertEqual(policy.choose_key(hurt), REST_MACRO)  # heal up first
        healed = Snapshot(player(10, 10, hp=90, max_hp=100), grids, [], turn=2, floor_key=(1, 5, 0))
        self.assertEqual(policy.choose_key(healed), ">")

    def test_confirms_entry_on_a_dungeon_entrance(self):
        # A town/wilderness dungeon entrance first msg_print()s an entrance line
        # (a -more- prompt) then a [y/n] confirmation, so descent is the macro
        # ">\ry" (Return dismisses the -more-, y confirms), not a bare ">".
        grids = {Position(10, 10): grid(
            10, 10, entrance=True, entrance_dungeon_id=DUNGEON_YEEK_CAVE,
        )}
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), ">\ry")

    def test_bare_downstairs_needs_no_confirmation(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), ">")

    def test_seeks_a_dungeon_entrance(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(
                10, 12, entrance=True,
                entrance_dungeon_id=DUNGEON_YEEK_CAVE,
            ),
        }
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), "6")

    def test_does_not_dive_deeper_to_flee(self):
        # Desperate on a pure downstairs with a monster near: must NOT press ">"
        # (diving to escape leads somewhere worse and can ping-pong forever).
        grids = {
            Position(10, 10): grid(10, 10, downstairs=True),
            Position(10, 9): grid(10, 9),
            Position(10, 11): grid(10, 11, monster=True),
        }
        snap = Snapshot(player(10, 10, hp=5, max_hp=100), grids, [hostile(1, 10, 11, hp=20)])
        self.assertNotEqual(HengbotPolicy().choose_key(snap), ">")

    def test_does_not_immediately_return_after_fleeing_upstairs(self):
        policy = HengbotPolicy()
        safe_grids = {
            Position(13, 54): grid(13, 54, downstairs=True),
            Position(13, 53): grid(13, 53),
        }
        danger_grids = {
            Position(7, 16): grid(7, 16, upstairs=True),
            Position(6, 16): grid(6, 16, monster=True),
            Position(7, 17): grid(7, 17, monster=True),
            Position(8, 16): grid(8, 16, monster=True),
        }
        danger_monsters = [
            hostile(1, 6, 16, max_melee_damage=20),
            hostile(2, 7, 17, max_melee_damage=20),
            hostile(3, 8, 16, max_melee_damage=20),
        ]

        floor_nine = Snapshot(
            player(13, 54, hp=241, max_hp=241),
            safe_grids,
            [],
            turn=100,
            floor_key=(2, 9, 0),
        )
        floor_ten = Snapshot(
            player(7, 16, hp=241, max_hp=241),
            danger_grids,
            danger_monsters,
            turn=101,
            floor_key=(2, 10, 0),
        )
        returned = Snapshot(
            player(13, 54, hp=241, max_hp=241),
            safe_grids,
            [],
            turn=102,
            floor_key=(2, 9, 0),
        )

        self.assertEqual(policy.choose_key(floor_nine), ">")
        self.assertEqual(policy.choose_key(floor_ten), "<")
        self.assertNotEqual(policy.choose_key(returned), ">")

    def test_retries_descent_after_gaining_a_level(self):
        policy = HengbotPolicy()
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        policy._descent_blocked_at_level = 10
        snapshot = Snapshot(
            player(10, 10, level=11), grids, [], turn=300, floor_key=(2, 9, 0)
        )
        self.assertEqual(policy.choose_key(snapshot), ">")

    def test_prime_remembers_a_dangerous_landing_for_the_follow_process(self):
        policy = HengbotPolicy()
        danger_grids = {
            Position(7, 16): grid(7, 16, upstairs=True),
            Position(6, 16): grid(6, 16, monster=True),
            Position(7, 17): grid(7, 17, monster=True),
            Position(8, 16): grid(8, 16, monster=True),
        }
        initial = Snapshot(
            player(7, 16, hp=241, max_hp=241),
            danger_grids,
            [
                hostile(1, 6, 16, max_melee_damage=20),
                hostile(2, 7, 17, max_melee_damage=20),
                hostile(3, 8, 16, max_melee_damage=20),
            ],
            turn=100,
            floor_key=(2, 10, 0),
        )
        policy.prime(initial)

        safe_grids = {
            Position(13, 54): grid(13, 54, downstairs=True),
            Position(13, 53): grid(13, 53),
        }
        returned = Snapshot(
            player(13, 54, hp=241, max_hp=241),
            safe_grids,
            [],
            turn=101,
            floor_key=(2, 9, 0),
        )
        self.assertNotEqual(policy.choose_key(returned), ">")

    def test_does_not_rest_when_a_monster_is_in_sight(self):
        grids = {
            Position(10, 10): grid(10, 10, downstairs=True),
            Position(10, 12): grid(10, 12, monster=True),
        }
        snap = Snapshot(player(10, 10, hp=40, max_hp=100), grids, [hostile(1, 10, 12, distance=2)])
        self.assertNotEqual(HengbotPolicy().choose_key(snap), REST_MACRO)


class ExplorationTest(unittest.TestCase):
    def test_steps_onto_lit_but_unvisited_floor_before_finishing_exploration(self):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(9, 14)
        }
        grids[Position(10, 10)] = grid(10, 10)
        grids[Position(10, 11)] = grid(10, 11)
        grids[Position(10, 12)] = grid(10, 12)
        snap = Snapshot(
            player(10, 10), grids, [], floor_key=(2, 4, 0), width=30, height=30
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "explore")

    def test_moves_toward_in_radius_unknown(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12),
            Position(10, 13): grid(10, 13, known=False),
        }
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), "6")

    def test_explores_toward_radius_edge_instead_of_waiting(self):
        # Only the immediate row is known; tiles beyond are absent (past the view
        # radius). The old policy waited here forever; the new one walks outward.
        grids = {
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }
        key = HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, []))
        self.assertIn(key, {"4", "6"})
        self.assertNotEqual(key, "5")

    def test_opens_a_closed_door_in_the_way(self):
        # The room's only exit east is a closed door; the bot must OPEN it
        # ("o" + direction), not just walk into it (which may not open it).
        walls = {}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                walls[Position(10 + dy, 10 + dx)] = grid(10 + dy, 10 + dx, passable=False)
        walls[Position(10, 10)] = grid(10, 10)
        walls[Position(10, 11)] = grid(10, 11, closed_door=True)
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), walls, [])), "o6")

    def test_gives_up_on_a_door_that_will_not_open(self):
        # A closed door that never opens (jammed / hard lock) is abandoned after
        # DOOR_OPEN_LIMIT tries so the bot doesn't loop on it forever.
        walls = {}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                walls[Position(10 + dy, 10 + dx)] = grid(10 + dy, 10 + dx, passable=False)
        walls[Position(10, 10)] = grid(10, 10)
        walls[Position(10, 11)] = grid(10, 11, closed_door=True)
        snap = Snapshot(player(10, 10), walls, [], floor_key=(1, 5, 0), width=20, height=20)
        policy = HengbotPolicy()
        keys = [policy.choose_key(snap) for _ in range(DOOR_OPEN_LIMIT + 20)]
        self.assertEqual(keys[0], "o6")  # tries to open at first
        self.assertIn("s", keys)  # boxed in with a jammed door → searches for a secret way
        self.assertIn((10, 11), policy._blocked_doors)  # eventually abandons the door

    def test_opens_a_diagonal_closed_door(self):
        # Door interaction has no diagonal restriction.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),  # west floor
            Position(9, 9): grid(9, 9, closed_door=True),  # door NW, N of the west tile
        }
        for pos in [Position(9, 10), Position(9, 11), Position(10, 11), Position(11, 9), Position(11, 10), Position(11, 11)]:
            grids[pos] = grid(pos.y, pos.x, passable=False)
        key = HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, []))
        self.assertEqual(key, "o7")

    def test_moves_diagonally_into_an_open_door(self):
        # An open door is ordinary passable terrain for pathfinding.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(9, 10): grid(9, 10, passable=False),
            Position(9, 11): grid(9, 11, open_door=True),  # open door NE
        }
        for pos in [Position(9, 9), Position(10, 9), Position(10, 11), Position(11, 9), Position(11, 10), Position(11, 11)]:
            grids[pos] = grid(pos.y, pos.x, passable=False)
        key = HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, []))
        self.assertEqual(key, "9")

    def test_breaks_out_of_a_rejected_move_livelock(self):
        # Two floor exits border the unknown. If the chosen move never changes
        # the player's position (as a rejected move would), the livelock guard
        # eventually forces the other direction instead of repeating forever.
        grids = {
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }
        policy = HengbotPolicy()
        snap = Snapshot(player(10, 10), grids, [])
        keys = [policy.choose_key(snap) for _ in range(5)]
        # First choices are the same explore move; the last is a forced breakout
        # to the opposite direction.
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(keys[-1], "6" if keys[0] == "4" else "4")
        self.assertEqual(policy.last_reason, "breakout")

    def test_explores_open_area_without_oscillating(self):
        # A one-row corridor (walls above/below) with unknown at both far ends.
        # Committing to a frontier means the bot sweeps toward one end instead of
        # ping-ponging between two adjacent tiles.
        from hengbot.policy import DIRECTION_KEYS

        grids = {}
        for x in range(6, 18):
            grids[Position(10, x)] = grid(10, x)
            grids[Position(9, x)] = grid(9, x, passable=False)
            grids[Position(11, x)] = grid(11, x, passable=False)
        grids[Position(10, 5)] = grid(10, 5, known=False)
        grids[Position(10, 18)] = grid(10, 18, known=False)
        inv = {v: k for k, v in DIRECTION_KEYS.items()}

        policy = HengbotPolicy()
        pos = Position(10, 11)
        columns = []
        for turn in range(6):
            key = policy.choose_key(Snapshot(player(pos.y, pos.x), grids, [], turn=turn))
            self.assertIn(key, inv, f"expected a move at step {turn}, got {key!r}")
            dy, dx = inv[key]
            pos = Position(pos.y + dy, pos.x + dx)
            columns.append(pos.x)
        self.assertGreaterEqual(len(set(columns)), 4)  # swept, not oscillating

    def test_map_edge_void_is_not_a_frontier(self):
        # A sealed 2x2 pocket in the top-left map corner: every non-known
        # neighbour is either a wall or past the map edge (void). With bounds
        # known, none of that counts as unexplored, so the bot must not keep
        # "exploring" the perimeter.
        grids = {}
        for y in range(0, 2):
            for x in range(0, 2):
                grids[Position(y, x)] = grid(y, x)
        for pos in [Position(0, 2), Position(1, 2), Position(2, 0), Position(2, 1), Position(2, 2)]:
            grids[pos] = grid(pos.y, pos.x, passable=False)
        snap = Snapshot(player(0, 0), grids, [], width=10, height=10)
        policy = HengbotPolicy()
        policy._floor_key = snap.floor_key
        policy._visit_counts.update(
            {pos: 1 for pos, state in grids.items() if state.passable}
        )
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "explore")

    def test_boxed_in_with_no_options_waits(self):
        grids = {Position(10, 10): grid(10, 10)}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                grids[Position(10 + dy, 10 + dx)] = grid(10 + dy, 10 + dx, passable=False)
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), "5")


class AntiStuckTest(unittest.TestCase):
    def test_seeks_known_stairs_when_fully_explored(self):
        # A fully-known dead-end corridor (no frontier) with an upstairs known:
        # rather than freezing, head for the stairs to reach a fresh floor.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, upstairs=True),
        }
        # Wall off every other neighbour so there is no radius-edge frontier.
        for pos in [
            Position(9, 9), Position(9, 10), Position(9, 11), Position(9, 12), Position(9, 13),
            Position(11, 9), Position(11, 10), Position(11, 11), Position(11, 12), Position(11, 13),
            Position(10, 9), Position(10, 13),
        ]:
            grids[pos] = grid(pos.y, pos.x, passable=False)
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), "6")


# Item tvals used by the tests (see model.TVAL_*).
STAFF = 55
WAND = 65
POTION = 75
SCROLL = 70
FOOD = 80
FOOD_TYPE_MANA = 4


class ConsumableTest(unittest.TestCase):
    def _open_room(self):
        return {
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }

    def test_quaffs_healing_potion_when_hurt_in_a_fight(self):
        grids = self._open_room()
        inv = [item("c", POTION, 35)]  # Potion of Cure Serious Wounds
        threat = hostile(1, 10, 13, hp=30, max_hp=30, distance=3)  # a monster is near
        snap = Snapshot(player(10, 10, hp=20, max_hp=100), grids, [threat], inventory=inv)
        self.assertEqual(HengbotPolicy().choose_key(snap), "qc")

    def test_rests_instead_of_quaffing_when_safe(self):
        # Hurt but no enemy in sight: rest heals for free, so don't burn a potion.
        grids = self._open_room()
        inv = [item("c", POTION, 34)]
        snap = Snapshot(player(10, 10, hp=20, max_hp=100), grids, [], inventory=inv)
        self.assertEqual(HengbotPolicy().choose_key(snap), REST_MACRO)

    def test_does_not_rest_while_fainting_in_town(self):
        grids = self._open_room()
        snap = Snapshot(
            player(10, 10, hp=20, max_hp=100, food=100),
            grids,
            [],
            floor_key=(0, 0, 0),
        )
        self.assertNotEqual(HengbotPolicy().choose_key(snap), REST_MACRO)

    def test_ignores_unidentified_potion_when_hurt(self):
        grids = self._open_room()
        inv = [item("c", POTION, 34, aware=False)]  # unknown potion — don't gamble
        threat = hostile(1, 10, 13, hp=30, max_hp=30, distance=3)
        snap = Snapshot(player(10, 10, hp=20, max_hp=100), grids, [threat], inventory=inv)
        self.assertNotIn("q", HengbotPolicy().choose_key(snap))

    def test_reads_teleport_scroll_when_about_to_die(self):
        grids = {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11, monster=True)}
        inv = [item("d", SCROLL, 9)]  # Scroll of Teleport
        mon = hostile(1, 10, 11, hp=30, max_hp=30)
        snap = Snapshot(player(10, 10, hp=5, max_hp=100), grids, [mon], inventory=inv)
        self.assertEqual(HengbotPolicy().choose_key(snap), "rd")

    def test_eats_food_when_hungry_and_safe(self):
        grids = self._open_room()
        inv = [item("b", FOOD, 35)]  # Ration of Food
        snap = Snapshot(player(10, 10, food=100), grids, [], inventory=inv)
        self.assertEqual(HengbotPolicy().choose_key(snap), "Eb")

    def test_does_not_eat_when_well_fed(self):
        grids = self._open_room()
        inv = [item("b", FOOD, 35)]
        snap = Snapshot(player(10, 10, food=5000), grids, [], inventory=inv)
        self.assertNotIn("E", HengbotPolicy().choose_key(snap))

    def test_mana_race_eats_a_charged_staff_when_hungry(self):
        # A Zombie (food_type MANA) has no food but a staff with charges; it must
        # "eat" the staff to restore hunger, not starve.
        grids = self._open_room()
        inv = [item("d", STAFF, 0, charges=20)]
        snap = Snapshot(player(10, 10, food=100, food_type=FOOD_TYPE_MANA), grids, [], inventory=inv)
        self.assertEqual(HengbotPolicy().choose_key(snap), "Ed")

    def test_mana_race_ignores_a_depleted_staff(self):
        grids = self._open_room()
        inv = [item("d", STAFF, 0, charges=0)]  # no charges left → not edible
        snap = Snapshot(player(10, 10, food=100, food_type=FOOD_TYPE_MANA), grids, [], inventory=inv)
        self.assertNotIn("E", HengbotPolicy().choose_key(snap))

    def test_normal_race_does_not_eat_a_staff(self):
        grids = self._open_room()
        inv = [item("d", STAFF, 0, charges=20)]  # normal race can't eat devices
        snap = Snapshot(player(10, 10, food=100, food_type=0), grids, [], inventory=inv)
        self.assertNotIn("E", HengbotPolicy().choose_key(snap))


class ReturnToTownTest(unittest.TestCase):
    FLOOR = (1, 12, 0)

    def _pack(self, count):
        return [item(chr(ord("a") + i), TVAL_RING, 0) for i in range(count)]

    def _stairs(self):
        return {
            Position(10, 8): grid(10, 8, upstairs=True),
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
        }

    def test_reads_an_identified_recall_scroll_when_pack_is_full(self):
        inventory = self._pack(PACK_CAPACITY - 1)
        inventory.append(item("w", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL))
        snap = Snapshot(
            player(10, 10, food=12000),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=self.FLOOR,
            inventory=inventory,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "rw")
        self.assertEqual(policy.last_reason, "return:recall")

    def test_full_pack_without_recall_seeks_upstairs(self):
        snap = Snapshot(
            player(10, 10, food=6000),
            self._stairs(),
            [],
            floor_key=self.FLOOR,
            inventory=self._pack(PACK_CAPACITY),
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "4")
        self.assertEqual(policy.last_reason, "return:seek-upstairs")

    def test_return_ignores_a_nonadjacent_weak_enemy_and_keeps_seeking_upstairs(self):
        grids = self._stairs()
        grids[Position(10, 12)] = grid(10, 12, monster=True)
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100, food=6000),
            grids,
            [hostile(1, 10, 12, distance=2)],
            floor_key=self.FLOOR,
            inventory=self._pack(PACK_CAPACITY),
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "4")
        self.assertEqual(policy.last_reason, "return:seek-upstairs")

    def test_does_not_use_an_unaware_recall_scroll_from_an_old_snapshot(self):
        inventory = self._pack(PACK_CAPACITY - 1)
        inventory.append(
            item("w", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, aware=False)
        )
        snap = Snapshot(
            player(10, 10, food=6000),
            self._stairs(),
            [],
            floor_key=self.FLOOR,
            inventory=inventory,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "4")
        self.assertEqual(policy.last_reason, "return:seek-upstairs")

    def test_does_not_return_with_one_free_pack_slot(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        snap = Snapshot(
            player(10, 10, food=12000),
            grids,
            [],
            floor_key=self.FLOOR,
            inventory=self._pack(PACK_CAPACITY - 1),
        )

        self.assertEqual(HengbotPolicy().choose_key(snap), ">")

    def test_does_not_return_after_refill_reduces_oil_below_town_target(self):
        snap = Snapshot(
            player(
                10, 10, level=24, hp=413, max_hp=413,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=4, fuel=7500),
            ],
            equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=7000)],
        )
        policy = HengbotPolicy()

        self.assertFalse(policy._should_start_town_return(snap))

    def test_returns_when_equipped_light_is_empty_and_cannot_be_refilled(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),
                item("f", TVAL_FOOD, 35, count=5),
            ],
            equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=0)],
        )
        policy = HengbotPolicy()

        self.assertTrue(policy._should_start_town_return(snap))

    def test_refills_empty_lantern_instead_of_immediately_returning(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_ANGBAND, 1, 0),
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=6),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=3),
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=7500),
            ],
            equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=0)],
        )
        policy = HengbotPolicy()

        self.assertFalse(policy._should_start_town_return(snap))
        self.assertEqual(policy.choose_key(snap), "\\Fo")
        self.assertEqual(policy.last_reason, "refill-light")

    def test_latched_return_refills_empty_lantern_before_reading_recall(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(4, 18, 0),
            inventory=[
                item("f", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=8),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=7500),
            ],
            equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=0)],
        )
        policy = HengbotPolicy()
        policy._returning_to_town = True

        self.assertEqual(policy.choose_key(snap), "\\Fo")
        self.assertEqual(policy.last_reason, "refill-light")

    def test_return_mode_survives_an_opened_pack_slot_and_blocks_descent(self):
        policy = HengbotPolicy()
        full = Snapshot(
            player(10, 10, food=6000),
            self._stairs(),
            [],
            floor_key=self.FLOOR,
            inventory=self._pack(PACK_CAPACITY),
        )
        policy.choose_key(full)
        grids = self._stairs()
        grids[Position(10, 10)] = grid(10, 10, downstairs=True)
        opened = Snapshot(
            player(10, 10, food=6000),
            grids,
            [],
            floor_key=self.FLOOR,
            inventory=self._pack(1),
        )

        self.assertEqual(policy.choose_key(opened), "4")
        self.assertEqual(policy.last_reason, "return:seek-upstairs")

    def test_waits_safely_after_recall_has_started(self):
        snap = Snapshot(
            player(10, 10, food=6000, word_recall=12),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=self.FLOOR,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "5")
        self.assertEqual(policy.last_reason, "return:wait-recall")

    def test_low_food_without_supplies_uses_identified_recall(self):
        recall = item("h", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snap = Snapshot(
            player(10, 10, food=1500),  # "hungry" band: out of food, time to go home
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=self.FLOOR,
            inventory=[recall],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "rh")
        self.assertEqual(policy.last_reason, "return:recall")

    def test_food_in_pack_prevents_early_food_return(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        snap = Snapshot(
            player(10, 10, food=2500),
            grids,
            [],
            floor_key=self.FLOOR,
            inventory=[item("b", TVAL_FOOD, 35)],
        )

        self.assertEqual(HengbotPolicy().choose_key(snap), ">")

    def test_normal_food_band_without_supplies_no_longer_returns(self):
        # "normal" is a wide band with ample margin; a MANA character lives off its
        # identify-staff charges. Dropping below Full is no longer a reason to bail —
        # only actual hunger is (see test_hungry_without_supplies_starts_return).
        snap = Snapshot(
            player(10, 10, food=6000),
            self._stairs(),
            [],
            floor_key=self.FLOOR,
        )
        policy = HengbotPolicy()

        self.assertFalse(policy._should_start_town_return(snap))
        self.assertNotEqual(policy.choose_key(snap), "rh")

    def test_hungry_without_supplies_starts_return(self):
        # Once genuinely hungry (below the "normal" band) with nothing to eat, end
        # the run while there is still margin to reach town.
        snap = Snapshot(
            player(10, 10, food=1500),  # "hungry" band
            self._stairs(),
            [],
            floor_key=self.FLOOR,
        )
        self.assertTrue(HengbotPolicy()._should_start_town_return(snap))

    def test_full_food_band_without_supplies_can_continue(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        snap = Snapshot(
            player(10, 10, food=12000),
            grids,
            [],
            floor_key=self.FLOOR,
        )

        self.assertEqual(HengbotPolicy().choose_key(snap), ">")

    def test_full_pack_of_junk_destroys_overflow_to_reenter_the_dungeon(self):
        # A pack full of items no shop buys and the Home will not take (here,
        # non-wearable rings standing in for devices/junk) must NOT strand the
        # bot in town: with no sale/deposit/purchase possible it drops one so a
        # slot frees and descent unblocks, instead of waiting forever.
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        snap = Snapshot(
            player(10, 10, food=6000),
            grids,
            [],
            floor_key=(0, 0, 0),
            inventory=self._pack(PACK_CAPACITY),
        )

        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "01ka")
        self.assertEqual(pol.last_reason, "town:destroy-overflow")


class OverflowDisposalTest(unittest.TestCase):
    def _town(self, inventory):
        return Snapshot(
            player(10, 10, food=6000),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(0, 0, 0),
            inventory=inventory,
        )

    def test_destroys_a_device_but_never_the_recall_scroll(self):
        # Essentials (here the Word of Recall at slot 'a') are never the overflow
        # victim — the first non-essential device is dropped instead.
        recall = item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        staves = [
            item(chr(ord("b") + i), TVAL_STAFF, 3, name="staff")
            for i in range(PACK_CAPACITY - 1)
        ]
        pol = HengbotPolicy()
        key = pol.choose_key(self._town([recall] + staves))
        self.assertEqual(pol.last_reason, "town:destroy-overflow")
        self.assertEqual(key, "01kb")

    def test_destroys_junk_until_departure_free_slot_requirement_is_met(self):
        used = PACK_CAPACITY - MIN_FREE_PACK_SLOTS + 1
        staves = [
            item(chr(ord("a") + i), TVAL_STAFF, 3, name=f"staff-{i}")
            for i in range(used)
        ]

        pol = HengbotPolicy()
        key = pol.choose_key(self._town(staves))

        self.assertEqual(pol.last_reason, "town:destroy-overflow")
        self.assertEqual(key, "01ka")


    def test_preserves_equipment_and_unidentified_consumables(self):
        # Home-depositable equipment and alchemist-sellable unknown scrolls have
        # a town economic path, so the overflow valve leaves them for those
        # actions rather than dropping them on the ground.
        gear = [
            item(chr(ord("a") + i), TVAL_RING, 0, is_equipment=True)
            for i in range(12)
        ]
        unknown = [
            item(chr(ord("m") + i), TVAL_SCROLL, 3, aware=False) for i in range(11)
        ]
        pol = HengbotPolicy()
        key = pol.choose_key(self._town(gear + unknown))
        self.assertNotEqual(pol.last_reason, "town:destroy-overflow")
        self.assertNotIn("\\d", key)

    def test_full_pack_destroys_boldness_before_returning(self):
        inventory = [item("a", TVAL_POTION, 28, name="Boldness")]
        inventory.extend(
            item(chr(ord("b") + i), TVAL_RING, 0, name=f"keep-{i}")
            for i in range(PACK_CAPACITY - 1)
        )
        snap = Snapshot(
            player(10, 10, food=6000),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=inventory,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "01ka")
        self.assertEqual(policy.last_reason, "inventory:destroy-disposable-item")

    def test_full_pack_destroys_cure_light_wounds(self):
        inventory = [item("a", TVAL_POTION, 34, name="Cure Light Wounds")]
        inventory.extend(
            item(chr(ord("b") + i), TVAL_RING, 0, name=f"keep-{i}")
            for i in range(PACK_CAPACITY - 1)
        )
        snap = Snapshot(
            player(10, 10, food=6000),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=inventory,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "01ka")
        self.assertEqual(policy.last_reason, "inventory:destroy-disposable-item")

    def test_town_compacts_surplus_diggers_before_departure(self):
        # Live regression: Home batching left 21/23 slots occupied, including
        # three shovels and a pick. Shed weaker diggers before any town departure.
        inventory = [
            item("a", TVAL_DIGGING, 1, name="shovel-1"),
            item("b", TVAL_DIGGING, 1, name="shovel-2"),
            item("c", TVAL_DIGGING, 4, name="pick"),
        ]
        inventory.extend(
            item(chr(ord("d") + i), TVAL_STAFF, i, name=f"keep-{i}", charges=1)
            for i in range(18)
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "01ka")
        self.assertEqual(policy.last_reason, "inventory:destroy-disposable-item")

    def test_town_compacts_ammo_when_no_launcher_is_owned(self):
        ammo = item("a", TVAL_ARROW, 4, name="arrows", count=14)
        filler = [
            item(chr(ord("b") + i), TVAL_STAFF, i, charges=1)
            for i in range(18)
        ]
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[ammo, *filler],
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "014ka")
        self.assertEqual(policy.last_reason, "inventory:destroy-disposable-item")

    def test_town_preserves_ammo_when_a_launcher_is_owned(self):
        ammo = item("a", TVAL_ARROW, 4, name="arrows", count=14)
        bow = item("b", TVAL_BOW, 12, name="short bow", is_equipment=True)
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[ammo, bow],
        )

        self.assertIsNone(HengbotPolicy()._find_disposable_item(snap))

    def test_full_pack_destroys_new_disposable_items(self):
        cases = [
            item("a", TVAL_POTION, 11, name="Sleep"),
            item("a", TVAL_SCROLL, 30, name="Detect Invisible"),
            item("a", TVAL_LITE, SV_LITE_TORCH, name="empty torch", fuel=0),
            item("a", TVAL_BOTTLE, 1, name="Empty Bottle"),
        ]
        for disposable in cases:
            with self.subTest(item=disposable.name):
                filler = [
                    item(chr(ord("b") + i), TVAL_STAFF, i, name=f"filler-{i}")
                    for i in range(PACK_CAPACITY - 1)
                ]
                snap = Snapshot(
                    player(10, 10),
                    {Position(10, 10): grid(10, 10)},
                    [],
                    inventory=[disposable, *filler],
                )
                policy = HengbotPolicy()
                self.assertEqual(policy.choose_key(snap), "01ka")
                self.assertEqual(
                    policy.last_reason, "inventory:destroy-disposable-item"
                )

    def test_full_pack_force_destroys_an_entire_disposable_stack(self):
        disposable = item(
            "a", TVAL_POTION, 28, name="Boldness", count=3
        )
        filler = [
            item(chr(ord("b") + i), TVAL_RING, 0, name=f"keep-{i}")
            for i in range(PACK_CAPACITY - 1)
        ]
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[disposable, *filler],
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "03ka")
        self.assertEqual(policy.last_reason, "inventory:destroy-disposable-item")

    def test_full_pack_discards_average_or_cursed_pseudo_identified_items(self):
        for feeling in ("average", "cursed"):
            with self.subTest(feeling=feeling):
                disposable = item(
                    "a",
                    TVAL_RING,
                    0,
                    name=f"{feeling} ring",
                    pseudo_feeling=feeling,
                    is_equipment=True,
                )
                filler = [
                    item(chr(ord("b") + i), TVAL_STAFF, i, name=f"keep-{i}")
                    for i in range(PACK_CAPACITY - 1)
                ]
                snap = Snapshot(
                    player(10, 10),
                    {Position(10, 10): grid(10, 10)},
                    [],
                    inventory=[disposable, *filler],
                )

                policy = HengbotPolicy()
                self.assertEqual(policy.choose_key(snap), "01ka")
                self.assertEqual(
                    policy.last_reason, "inventory:destroy-disposable-item"
                )

    def test_full_pack_never_discards_a_bounty_from_pseudo_feeling(self):
        bounty = item(
            "a",
            TVAL_RING,
            0,
            pseudo_feeling="cursed",
            is_bounty=True,
        )
        filler = [
            item(chr(ord("b") + i), TVAL_STAFF, i, name=f"keep-{i}")
            for i in range(PACK_CAPACITY - 1)
        ]
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[bounty, *filler],
        )

        policy = HengbotPolicy()
        self.assertNotEqual(policy.choose_key(snap), "01ka")

    def test_does_not_destroy_unidentified_zero_fuel_torch(self):
        torch = item(
            "a", TVAL_LITE, SV_LITE_TORCH, name="unknown torch", known=False, fuel=0
        )
        filler = [
            item(chr(ord("b") + i), TVAL_STAFF, i, name=f"filler-{i}")
            for i in range(PACK_CAPACITY - 1)
        ]
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[torch, *filler],
        )
        self.assertNotEqual(HengbotPolicy().choose_key(snap), "01ka")


class StatusTest(unittest.TestCase):
    def test_flees_instead_of_meleeing_when_afraid(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 11): grid(10, 11, monster=True),
        }
        mon = hostile(1, 10, 11, hp=10)
        snap = Snapshot(player(10, 10, hp=20, max_hp=20, afraid=True), grids, [mon])
        # Cannot attack while afraid → step away west, never toward the monster (6).
        self.assertEqual(HengbotPolicy().choose_key(snap), "4")

    def test_waits_when_confused_and_safe(self):
        grids = self._grids_with_frontier()
        snap = Snapshot(player(10, 10, confused=True), grids, [])
        self.assertEqual(HengbotPolicy().choose_key(snap), "5")

    def _grids_with_frontier(self):
        return {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, known=False),
        }


class RestTest(unittest.TestCase):
    def _open_room(self):
        return {
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }

    def test_rests_to_recover_when_hurt_and_safe(self):
        snap = Snapshot(player(10, 10, hp=40, max_hp=100), self._open_room(), [])
        self.assertEqual(HengbotPolicy().choose_key(snap), REST_MACRO)

    def test_does_not_rest_while_bleeding(self):
        # A dungeon floor: these exercise the DUNGEON rest rules, not the town
        # recover-at-the-store behaviour (in_town is a distinct code path).
        snap = Snapshot(
            player(10, 10, hp=40, max_hp=100, poisoned=True),
            self._open_room(),
            [],
            floor_key=(1, 5, 0),
        )
        self.assertNotEqual(HengbotPolicy().choose_key(snap), REST_MACRO)

    def test_does_not_rest_when_healthy(self):
        snap = Snapshot(
            player(10, 10, hp=95, max_hp=100),
            self._open_room(),
            [],
            floor_key=(1, 5, 0),
        )
        self.assertNotEqual(HengbotPolicy().choose_key(snap), REST_MACRO)


class PickupTest(unittest.TestCase):
    def test_distant_weak_hostile_does_not_block_safe_loot(self):
        monster = hostile(1, 10, 13, distance=3, max_melee_damage=2)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, objects=1),
            Position(10, 12): grid(10, 12),
            Position(10, 13): grid(10, 13, monster=True),
        }
        policy = HengbotPolicy()

        snapshot = Snapshot(
            player(10, 10), grids, [monster], floor_key=(1, 5, 0)
        )
        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "seek-loot")

    def test_material_ranged_threat_blocks_loot(self):
        monster = hostile(1, 10, 13, distance=3, max_ranged_damage=100)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, objects=1),
            Position(10, 12): grid(10, 12),
            Position(10, 13): grid(10, 13, monster=True),
        }
        policy = HengbotPolicy()
        snapshot = Snapshot(player(10, 10, hp=500, max_hp=500), grids, [monster])

        policy.choose_key(snapshot)

        self.assertNotEqual(policy.last_reason, "seek-loot")
        self.assertEqual(policy.loot_state(snapshot)["blocker"], "material-threat")

    def test_multiplier_blocked_loot_stays_deferred_after_threat_leaves_view(self):
        floor_key = (DUNGEON_YEEK_CAVE, 3, 0)
        loot = Position(10, 12)
        policy = HengbotPolicy()
        safe = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                loot: grid(10, 12, objects=1),
                Position(11, 10): grid(11, 10),
            },
            [],
            floor_key=floor_key,
        )
        self.assertEqual(policy.choose_key(safe), "6")
        self.assertEqual(policy._loot_target, loot)

        multiplier = hostile(
            1, 13, 11, distance=2, can_multiply=True, max_melee_damage=1
        )
        blocked = Snapshot(
            player(10, 11),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                loot: grid(10, 12, objects=1),
                Position(11, 10): grid(11, 10),
                Position(13, 11): grid(13, 11, monster=True),
            },
            [multiplier],
            floor_key=floor_key,
        )
        policy._observe(blocked)
        self.assertIsNone(policy._normal_loot_key(blocked, [multiplier]))
        self.assertIn(loot, policy._deferred_loot)
        self.assertIsNone(policy._loot_target)

        hidden_again = Snapshot(
            player(10, 10),
            safe.grids,
            [],
            floor_key=floor_key,
        )
        policy.choose_key(hidden_again)

        self.assertNotEqual(policy.last_reason, "seek-loot")
        self.assertIsNone(policy._loot_target)
        self.assertEqual(policy.loot_state(hidden_again)["deferred"], [{"y": 10, "x": 12}])

    def test_routine_return_sweeps_nearby_safe_loot(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, objects=1),
        }
        snapshot = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        policy = HengbotPolicy()
        policy._returning_to_town = True
        policy._last_return_trigger = "recall-low"

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "return:seek-loot")

    def test_critical_return_does_not_detour_for_loot(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, objects=1),
        }
        snapshot = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        policy = HengbotPolicy()
        policy._returning_to_town = True
        policy._last_return_trigger = "food-hungry"

        self.assertEqual(policy.choose_key(snapshot), "rr")
        self.assertEqual(policy.last_reason, "return:recall")

    def test_steps_off_a_new_drop_to_trigger_autodestroy(self):
        grids = {
            Position(10, 10): grid(10, 10, objects=1),
            Position(10, 11): grid(10, 11, downstairs=True),
        }
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(Snapshot(player(10, 10), grids, [])), "6")
        self.assertEqual(policy.last_reason, "trigger-autodestroy")

    def test_picks_up_an_item_that_survived_stepping_onto_its_tile(self):
        grids = {
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10, objects=1),
        }
        policy = HengbotPolicy()
        policy._floor_key = (1, 1, 0)
        policy._last_position = Position(10, 9)

        self.assertEqual(
            policy.choose_key(
                Snapshot(player(10, 10), grids, [], floor_key=(1, 1, 0))
            ),
            "g",
        )
        self.assertEqual(policy.last_reason, "pickup")

    def test_selects_every_item_from_a_floor_pile(self):
        grids = {
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10, objects=3),
        }
        policy = HengbotPolicy()
        policy._floor_key = (1, 1, 0)
        policy._last_position = Position(10, 9)

        self.assertEqual(
            policy.choose_key(
                Snapshot(player(10, 10), grids, [], floor_key=(1, 1, 0))
            ),
            "gaaa",
        )
        self.assertEqual(policy.last_reason, "pickup")


class BountyCashoutTest(unittest.TestCase):
    def test_enters_hunter_office_and_redeems_bounty(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, building_type=13),
        }
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[item("a", 10, 1, name="wanted corpse", is_bounty=True)],
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "6cy\x1b")
        self.assertEqual(policy.last_reason, "bounty:cashout")

    def test_confirms_each_bounty_stack_in_one_office_visit(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, building_type=13),
        }
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[
                item("a", 10, 0, name="wanted skeleton", is_bounty=True),
                item("b", 10, 1, name="wanted corpse", is_bounty=True),
            ],
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "6cyy\x1b")
        self.assertEqual(policy.last_reason, "bounty:cashout")

    def test_standing_on_office_hops_off_to_reenter(self):
        # After a cash-out the bot is left standing ON the office tile. A path to
        # its own tile is empty, so the office used to read as "not found" and a
        # sticky town block stranded it forever. It must instead hop to a
        # neighbour so the next approach can walk back on and redeem the rest.
        grids = {
            Position(10, 10): grid(10, 10, building_type=13),  # bot is on the office
            Position(10, 11): grid(10, 11),  # a walkable tile to step off onto
        }
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[item("a", 10, 1, name="wanted", is_bounty=True)],
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertEqual(policy.last_reason, "bounty:step-off")
        self.assertIsNone(policy._town_blocked_reason)

    def test_unreachable_office_never_latches_a_town_block(self):
        # No office in view and no static map: cashing out is simply skipped this
        # turn (return None), never a sticky block that would outlive the bounty.
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[item("a", 10, 1, name="wanted", is_bounty=True)],
        )
        policy = HengbotPolicy()
        policy._observe(snap)
        self.assertIsNone(policy._bounty_cashout_key(snap))
        self.assertIsNone(policy._town_blocked_reason)

    def test_seeks_visible_loot_before_walking_to_a_store(self):
        grids = {
            Position(9, 10): grid(9, 10, objects=1),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): GridState(
                position=Position(10, 12), known=True, passable=True, wall=False,
                has_monster=False, has_down_stairs=False, has_up_stairs=False,
                unsafe=False, store_number=STORE_GENERAL,
            ),
        }
        snap = Snapshot(
            player(10, 10, gold=1000), grids, [], floor_key=(0, 0, 0)
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "8")
        self.assertEqual(policy.last_reason, "seek-loot")

    def test_seeks_loot_on_trap_undetected_grid(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, objects=1, unsafe=True),
        }
        snap = Snapshot(player(10, 10), grids, [])
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "seek-loot")

    def test_commits_to_loot_when_a_nearer_item_flickers_into_view(self):
        floor_key = (1, 3, 0)
        policy = HengbotPolicy()
        first = Snapshot(
            player(10, 10),
            {
                Position(10, x): grid(10, x, objects=1 if x == 15 else 0)
                for x in range(9, 16)
            },
            [],
            floor_key=floor_key,
        )
        self.assertEqual(policy.choose_key(first), "6")
        self.assertEqual(policy._loot_target, Position(10, 15))

        second = Snapshot(
            player(10, 11),
            {
                Position(10, 9): grid(10, 9, objects=1),
                Position(10, 11): grid(10, 11),
            },
            [],
            floor_key=floor_key,
        )

        self.assertEqual(policy.choose_key(second), "6")
        self.assertEqual(policy._loot_target, Position(10, 15))
        self.assertEqual(policy.last_reason, "seek-loot")

    def test_forgets_loot_after_autodestroy_removes_it(self):
        floor_key = (1, 3, 0)
        policy = HengbotPolicy()
        first = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, objects=1),
            },
            [],
            floor_key=floor_key,
        )
        self.assertEqual(policy.choose_key(first), "6")

        second = Snapshot(
            player(10, 11),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
            },
            [],
            floor_key=floor_key,
        )
        policy.choose_key(second)

        self.assertNotIn(Position(10, 11), policy._known_loot)
        self.assertIsNone(policy._loot_target)
        self.assertNotEqual(policy.last_reason, "seek-loot")


class FixedQuestTest(unittest.TestCase):
    QUEST_ID = 1

    def _quest(self, status: int) -> QuestState:
        return QuestState(
            id=self.QUEST_ID,
            name="Thieves Hideout",
            status=status,
            type=6,
            level=5,
            flags=6,
            fixed=True,
            has_reward=True,
            reward_baseitem_id=42,
        )

    def _town_map(self, *, reward=False) -> TownMap:
        walkable = {
            Position(y, x)
            for y in range(66)
            for x in range(198)
            if not reward or y == 27
        }
        return TownMap(
            name="Outpost",
            width=198,
            height=66,
            walkable=frozenset(walkable),
            quest_buildings={self.QUEST_ID: frozenset({Position(26, 98)})},
            quest_entrances={self.QUEST_ID: frozenset({Position(35, 177)})},
            reward_positions=frozenset({Position(27, 98)}),
        )

    def _town_snapshot(self, y, x, grids, status):
        return Snapshot(
            player(y, x, level=8, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(0, 0, 0),
            width=198,
            height=66,
            town_flag=True,
            town_id=0,
            town_index=1,
            quests={self.QUEST_ID: self._quest(status)},
        )

    def test_requests_allowed_fixed_quest_at_quest_building(self):
        grids = {
            Position(26, 97): grid(26, 97),
            Position(26, 98): grid(26, 98, building_type=1, building_special=1),
        }
        policy = HengbotPolicy(self._town_map())
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True

        key = policy.choose_key(self._town_snapshot(26, 97, grids, 0))

        self.assertEqual(key, "6q\x1b")
        self.assertEqual(policy.last_reason, "fixedquest:request")

    def test_ready_unoffered_q14_does_not_shadow_offered_q34(self):
        quests = {
            14: replace(self._quest(QUEST_STATUS_UNTAKEN), id=14, level=5),
            34: replace(self._quest(QUEST_STATUS_UNTAKEN), id=34, level=5),
        }
        snapshot = replace(
            self._town_snapshot(26, 97, {
                Position(26, 98): grid(
                    26, 98, building_type=1, building_special=1
                ),
                Position(30, 40): grid(
                    30, 40, building_type=1, building_special=34
                ),
            }, QUEST_STATUS_UNTAKEN),
            quests=quests,
        )
        policy = HengbotPolicy(self._town_map())
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True

        self.assertEqual(policy._fixed_quest_target(snapshot), 34)

    def test_q14_becomes_eligible_and_routes_when_castle_offers_it(self):
        policy, snapshot = self._q14_town_fixture(QUEST_STATUS_UNTAKEN)
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True

        self.assertEqual(policy._fixed_quest_target(snapshot), 14)
        self.assertEqual(policy._fixed_quest_key(snapshot, []), "6q\x1b")
        self.assertEqual(policy.last_reason, "fixedquest:request")

    def _win_quest_acceptance_fixture(self, extra_quests=()):
        knowledge = {
            1: QuestInfo(1, "Thieves Hideout", 6, 5, 6,
                         placed_monsters=((44, 1),)),
            8: QuestInfo(8, "Oberon", 1, 99, 0, dungeon=1,
                         max_num=1, monrace_id=860),
            9: QuestInfo(9, "Serpent of Chaos", 1, 100, 0, dungeon=1,
                         max_num=1, monrace_id=862),
            14: QuestInfo(14, "Warg Problem", 5, 5, 2, dungeon=0,
                          num_mon=16, monrace_id=257),
        }
        quests = {
            1: self._quest(QUEST_STATUS_UNTAKEN),
            8: QuestState(8, status=QUEST_STATUS_TAKEN, fixed=True),
            9: QuestState(9, status=QUEST_STATUS_TAKEN, fixed=True),
            **dict(extra_quests),
        }
        grids = {
            Position(26, 97): grid(26, 97),
            Position(26, 98): grid(
                26, 98, building_type=1, building_special=1
            ),
        }
        base = self._town_snapshot(26, 97, grids, QUEST_STATUS_UNTAKEN)
        snapshot = replace(
            base,
            player=replace(
                base.player, level=8, hp=1000, max_hp=1000,
                main_hand_blows=10, main_hand_to_d=100,
            ),
            equipment=[item(
                "main_hand", TVAL_SWORD, 1, is_equipment=True,
                damage_dice_num=10, damage_dice_sides=10,
            )],
            quests=quests,
        )
        policy = HengbotPolicy(
            self._town_map(), quest_knowledge=knowledge,
            monrace_knowledge={44: MonraceKnowledge(1, 110, False, False)},
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True
        return policy, snapshot

    def test_birth_taken_win_quests_do_not_block_ready_q1_acceptance(self):
        policy, snapshot = self._win_quest_acceptance_fixture()

        self.assertEqual(policy._fixed_quest_target(snapshot), 1)
        self.assertTrue(policy.fixed_quest_readiness_state()["verdict"])
        policy._fixed_quest_building_key = (
            lambda _snapshot, _quest_id, reason, **_kwargs: reason
        )
        self.assertEqual(
            policy._fixed_quest_key(snapshot, []), "fixedquest:request"
        )

    def test_real_taken_allowlist_quest_still_serializes_acceptance(self):
        q14 = QuestState(14, status=QUEST_STATUS_TAKEN, fixed=True)
        policy, snapshot = self._win_quest_acceptance_fixture({14: q14})

        self.assertEqual(policy._fixed_quest_target(snapshot), 14)
        self.assertIsNone(policy._fixed_quest_key(snapshot, []))

    def test_unsupported_taken_fixed_quest_still_blocks_acceptance(self):
        unsupported = QuestState(3, status=QUEST_STATUS_TAKEN, fixed=True)
        policy, snapshot = self._win_quest_acceptance_fixture({3: unsupported})

        self.assertIsNone(policy._fixed_quest_target(snapshot))
        self.assertIsNone(policy._fixed_quest_key(snapshot, []))

    def test_q2_is_entirely_absent_from_targeting_on_old_emitter_snapshot(self):
        snapshot = replace(
            self._town_snapshot(26, 97, {}, 0),
            quests={2: QuestState(2, status=0, fixed=True)},
            visited_town_ids=None,
        )
        policy = HengbotPolicy(self._town_map())
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        self.assertIsNone(policy._fixed_quest_target(snapshot))

    def test_q2_is_absent_from_targeting_until_telmora_was_visited(self):
        snapshot = replace(
            self._town_snapshot(26, 97, {}, 0),
            quests={2: QuestState(2, status=0, fixed=True)},
            visited_town_ids=(0,),
        )
        policy = HengbotPolicy(self._town_map())
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True

        self.assertIsNone(policy._fixed_quest_target(snapshot))

    def test_q2_telmora_visit_requires_exported_visited_town(self):
        snapshot = replace(
            self._town_snapshot(26, 97, {}, 0),
            player=replace(self._town_snapshot(26, 97, {}, 0).player, gold=2000),
            quests={2: QuestState(2, status=0, fixed=True)},
            visited_town_ids=(0, 1),
        )
        policy = HengbotPolicy(self._town_map())
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._town_teleport_key = lambda _snapshot, town_id: f"teleport:{town_id}"
        with patch.object(
            policy_module, "EXECUTABLE_QUEST_STRATEGY_IDS", frozenset({1, 2, 14, 34})
        ):
            self.assertEqual(
                policy._telmora_q2_travel_key(snapshot, snapshot.quests[2]),
                "teleport:1",
            )
        self.assertTrue(policy._telmora_q2_errand)

    def test_q2_acceptance_is_blocked_until_executor_exists(self):
        snapshot = replace(
            self._town_snapshot(26, 97, {}, QUEST_STATUS_UNTAKEN),
            quests={2: QuestState(2, status=QUEST_STATUS_UNTAKEN, fixed=True)},
            visited_town_ids=(0, 1),
        )
        policy = HengbotPolicy(self._town_map())
        policy._fixed_quest_target = lambda _snapshot: 2
        policy._telmora_q2_travel_key = lambda _snapshot, _quest: None
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._fixed_quest_building_key = (
            lambda *_args, **_kwargs: "fixedquest:request"
        )

        self.assertIsNone(policy._fixed_quest_key(snapshot, []))

    def _q14_town_fixture(self, status):
        quest = QuestState(
            14, status=status, type=QUEST_TYPE_KILL_LEVEL, level=5,
            dungeon_id=DUNGEON_YEEK_CAVE, fixed=True,
        )
        knowledge = {
            14: QuestInfo(
                14, "Warg Problem", QUEST_TYPE_KILL_LEVEL, 5, 2,
                dungeon=DUNGEON_YEEK_CAVE, max_num=1, monrace_id=257,
            )
        }
        town_map = TownMap(
            name="Outpost", width=198, height=66,
            walkable=frozenset(
                Position(y, x) for y in range(66) for x in range(198)
            ),
            quest_buildings={14: frozenset({Position(26, 98)})},
            quest_entrances={},
            reward_positions=frozenset({Position(27, 98)}),
        )
        grids = {
            Position(26, 97): grid(26, 97),
            Position(26, 98): grid(
                26, 98, building_type=1, building_special=14
            ),
        }
        snapshot = replace(
            self._town_snapshot(26, 97, grids, QUEST_STATUS_UNTAKEN),
            quests={14: quest},
        )
        policy = HengbotPolicy(town_map, quest_knowledge=knowledge)
        policy._build_grid_index(snapshot)
        return policy, snapshot

    def test_q14_untaken_requests_castle_acceptance_without_retargeting_dungeon(self):
        policy, snapshot = self._q14_town_fixture(QUEST_STATUS_UNTAKEN)
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._target_dungeon_id = 7

        self.assertEqual(policy._fixed_quest_key(snapshot, []), "6q\x1b")
        self.assertEqual(policy.last_reason, "fixedquest:request")
        self.assertEqual(policy._target_dungeon_id, 7)

    def test_q14_taken_targets_yeek_for_walk_in_descent(self):
        policy, snapshot = self._q14_town_fixture(QUEST_STATUS_TAKEN)
        policy._target_dungeon_id = 7

        self.assertIsNone(policy._fixed_quest_key(snapshot, []))
        self.assertEqual(policy._target_dungeon_id, DUNGEON_YEEK_CAVE)
        self.assertTrue(policy._taken_kill_quest_requires_walk_in(
            replace(snapshot, recall_depth=8)
        ))

    def test_q14_completed_claims_at_castle_and_latches_floor_reward(self):
        policy, snapshot = self._q14_town_fixture(QUEST_STATUS_COMPLETED)

        self.assertEqual(policy._fixed_quest_key(snapshot, []), "6q\x1b")
        self.assertEqual(policy.last_reason, "fixedquest:claim")
        self.assertEqual(policy._fixed_quest_reward_pending, 14)

    def test_q14_rewarded_collects_latched_floor_reward_and_clears_latch(self):
        policy, snapshot = self._q14_town_fixture(QUEST_STATUS_REWARDED)
        policy._fixed_quest_reward_pending = 14
        grids = {
            Position(27, 97): grid(27, 97),
            Position(27, 98): grid(27, 98, objects=1),
        }
        snapshot = replace(snapshot, player=player(27, 97), grids=grids)

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "fixedquest:reward-approach")

        policy._floor_key = (0, 0, 0)
        policy._last_position = Position(27, 97)
        pickup = replace(snapshot, player=player(27, 98))
        self.assertEqual(policy.choose_key(pickup), "g")
        self.assertEqual(policy.last_reason, "fixedquest:reward-pickup")

        policy._floor_key = (0, 0, 0)
        policy._last_position = Position(27, 98)
        empty = replace(
            pickup,
            grids={
                Position(27, 97): grid(27, 97),
                Position(27, 98): grid(27, 98),
            },
        )
        self.assertIsNone(policy._fixed_quest_key(empty, []))
        self.assertIsNone(policy._fixed_quest_reward_pending)
        self.assertEqual(policy.last_reason, "fixedquest:reward-complete")

    def test_q2_outbound_travel_is_blocked_until_executor_exists(self):
        snapshot = replace(
            self._town_snapshot(26, 97, {}, QUEST_STATUS_UNTAKEN),
            player=replace(self._town_snapshot(26, 97, {}, 0).player, gold=2000),
            quests={2: QuestState(2, status=QUEST_STATUS_UNTAKEN, fixed=True)},
            visited_town_ids=(0, 1),
        )
        policy = HengbotPolicy(self._town_map())
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._town_teleport_key = lambda _snapshot, town_id: f"teleport:{town_id}"

        self.assertIsNone(policy._telmora_q2_travel_key(snapshot, snapshot.quests[2]))
        self.assertFalse(policy._telmora_q2_errand)

    def test_telmora_stranding_recovery_stays_ungated(self):
        snapshot = replace(self._telmora_q2_snapshot(QUEST_STATUS_UNTAKEN), quests={})
        policy = HengbotPolicy(self._town_map())
        policy._town_teleport_key = (
            lambda _snapshot, town_id: "home" if town_id == 0 else None
        )

        self.assertEqual(policy._fixed_quest_key(snapshot, []), "home")

    def test_other_executable_building_quest_acceptance_stays_unchanged(self):
        for quest_id in (1, 34):
            with self.subTest(quest_id=quest_id):
                snapshot = replace(
                    self._town_snapshot(26, 97, {}, QUEST_STATUS_UNTAKEN),
                    quests={
                        quest_id: QuestState(
                            quest_id, status=QUEST_STATUS_UNTAKEN, fixed=True
                        )
                    },
                )
                policy = HengbotPolicy(self._town_map())
                policy._fixed_quest_target = lambda _snapshot, value=quest_id: value
                policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
                policy._fixed_quest_building_key = (
                    lambda *_args, **_kwargs: "fixedquest:request"
                )

                self.assertEqual(policy._fixed_quest_key(snapshot, []), "fixedquest:request")

    def test_enabling_q2_executor_restores_acceptance(self):
        snapshot = replace(
            self._telmora_q2_snapshot(QUEST_STATUS_UNTAKEN),
            visited_town_ids=(0, 1),
        )
        policy = HengbotPolicy(self._town_map())
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._fixed_quest_is_offered = lambda _snapshot, _quest_id: True
        policy._fixed_quest_building_key = (
            lambda *_args, **_kwargs: "fixedquest:request"
        )

        with patch.object(
            policy_module, "EXECUTABLE_QUEST_STRATEGY_IDS", frozenset({1, 2, 14, 34})
        ):
            self.assertEqual(policy._fixed_quest_key(snapshot, []), "fixedquest:request")

    def _telmora_q2_snapshot(self, status, *, gold=500):
        return replace(
            self._town_snapshot(26, 97, {}, 0),
            player=replace(self._town_snapshot(26, 97, {}, 0).player, gold=gold),
            town_id=1,
            quests={2: QuestState(2, status=status, fixed=True)},
            visited_town_ids=(0, 1),
        )

    def test_q2_return_trip_uses_errand_latch_after_claim(self):
        snapshot = self._telmora_q2_snapshot(QUEST_STATUS_REWARDED)
        policy = HengbotPolicy(self._town_map())
        policy._telmora_q2_errand = True
        policy.approved_quest_strategy = lambda _quest_id: None
        policy._town_teleport_key = lambda _snapshot, town_id: "a" if town_id == 0 else None

        self.assertEqual(policy._telmora_q2_travel_key(snapshot, snapshot.quests[2]), "a")

    def test_q2_approval_revocation_in_telmora_returns_home(self):
        snapshot = self._telmora_q2_snapshot(QUEST_STATUS_TAKEN)
        policy = HengbotPolicy(self._town_map())
        policy._telmora_q2_errand = True
        policy.approved_quest_strategy = lambda _quest_id: None
        policy._town_teleport_key = lambda _snapshot, town_id: "a" if town_id == 0 else None

        self.assertEqual(policy._fixed_quest_key(snapshot, []), "a")

    def test_q2_failure_in_telmora_returns_home(self):
        snapshot = self._telmora_q2_snapshot(5)
        policy = HengbotPolicy(self._town_map())
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._town_teleport_key = lambda _snapshot, town_id: "a" if town_id == 0 else None

        self.assertEqual(policy._fixed_quest_key(snapshot, []), "a")

    def test_q2_acceptance_in_telmora_requires_approval(self):
        snapshot = self._telmora_q2_snapshot(QUEST_STATUS_UNTAKEN)
        policy = HengbotPolicy(self._town_map())
        policy.approved_quest_strategy = lambda _quest_id: None
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._fixed_quest_building_key = lambda *_args, **_kwargs: "accept"

        self.assertIsNone(policy._fixed_quest_key(snapshot, []))

    def test_q2_return_trip_requires_teleport_fare(self):
        snapshot = self._telmora_q2_snapshot(QUEST_STATUS_REWARDED, gold=499)
        policy = HengbotPolicy(self._town_map())
        policy._telmora_q2_errand = True
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._town_teleport_key = lambda _snapshot, _town_id: "unexpected"

        self.assertIsNone(policy._telmora_q2_travel_key(snapshot, snapshot.quests[2]))

    def test_q2_outpost_inn_selects_telmora_with_letter_b(self):
        inn = Position(26, 98)
        town_map = self._town_map()
        town_map = replace(town_map, buildings={0: inn})
        snapshot = replace(
            self._town_snapshot(
                26, 97, {Position(26, 97): grid(26, 97, building_type=-1)}, 0
            ),
            visited_town_ids=(0, 1),
        )
        policy = HengbotPolicy(town_map)
        policy._build_grid_index(snapshot)
        self.assertEqual(policy._town_teleport_key(snapshot, 1), "6mb")

    def test_readiness_uses_static_level_plus_safety_margin(self):
        info = QuestInfo(18, "Water Cave", 4, 35, 6, placed_monsters=((44, 1),))
        harmless = MonraceKnowledge(1, 110, False, False)
        policy = HengbotPolicy(
            self._town_map(), quest_knowledge={18: info}, monrace_knowledge={44: harmless}
        )
        snapshot = replace(
            self._town_snapshot(26, 97, {Position(26, 97): grid(26, 97)}, 0),
            player=player(
                26, 97, level=info.level + FIXED_QUEST_LEVEL_MARGIN,
                hp=100, max_hp=100, main_hand_blows=4, main_hand_to_d=10,
            ),
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True,
                            damage_dice_num=2, damage_dice_sides=6)],
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True
        self.assertTrue(policy._fixed_quest_ready(snapshot, 18))
        too_early = replace(
            snapshot,
            player=replace(snapshot.player, level=snapshot.player.level - 1),
        )
        self.assertFalse(policy._fixed_quest_ready(too_early, 18))

    def test_fixed_quest_roster_threat_rejects_despite_level_floor(self):
        info = QuestInfo(18, "Water Cave", 4, 35, 6, placed_monsters=((44, 3),))
        threat = MonraceKnowledge(100, 110, False, False, max_melee_damage=50)
        policy = HengbotPolicy(
            self._town_map(), quest_knowledge={18: info}, monrace_knowledge={44: threat}
        )
        snapshot = replace(
            self._town_snapshot(26, 97, {Position(26, 97): grid(26, 97)}, 0),
            player=player(26, 97, level=38, hp=200, max_hp=200,
                          main_hand_blows=4, main_hand_to_d=20),
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True,
                            damage_dice_num=3, damage_dice_sides=6)],
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True

        self.assertFalse(policy._fixed_quest_ready(snapshot, 18))
        self.assertEqual(policy.fixed_quest_readiness_state()["reason"], "three-turn-threat")

    def test_fixed_quest_consumables_flip_borderline_readiness(self):
        info = QuestInfo(18, "Water Cave", 4, 35, 6, placed_monsters=((44, 1),))
        threat = MonraceKnowledge(100, 120, False, False, max_melee_damage=30)
        policy = HengbotPolicy(
            self._town_map(), quest_knowledge={18: info}, monrace_knowledge={44: threat}
        )
        base = replace(
            self._town_snapshot(26, 97, {Position(26, 97): grid(26, 97)}, 0),
            player=player(26, 97, level=38, hp=200, max_hp=200,
                          main_hand_blows=4, main_hand_to_d=20),
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True,
                            damage_dice_num=3, damage_dice_sides=6)],
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True
        self.assertFalse(policy._fixed_quest_ready(base, 18))

        stocked = replace(base, inventory=[
            item("s", TVAL_POTION, SV_POTION_SPEED),
            item("h", TVAL_POTION, SV_POTION_HEALING),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=2),
        ])
        self.assertTrue(policy._fixed_quest_ready(stocked, 18))
        state = policy.fixed_quest_readiness_state()
        self.assertEqual(state["hp_healing_budget"], 554)
        self.assertTrue(state["hasted"])
        self.assertTrue(state["verdict"])

    def test_fixed_quest_healing_budget_is_limited_to_three_quaffs(self):
        info = QuestInfo(18, "Water Cave", 4, 35, 6, placed_monsters=((44, 1),))
        harmless = MonraceKnowledge(1, 110, False, False)
        policy = HengbotPolicy(
            self._town_map(), quest_knowledge={18: info}, monrace_knowledge={44: harmless}
        )
        snapshot = replace(
            self._town_snapshot(26, 97, {Position(26, 97): grid(26, 97)}, 0),
            player=player(26, 97, level=38, hp=200, max_hp=200,
                          main_hand_blows=4, main_hand_to_d=20),
            inventory=[item("h", TVAL_POTION, SV_POTION_HEALING, count=99)],
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True,
                            damage_dice_num=3, damage_dice_sides=6)],
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True

        self.assertTrue(policy._fixed_quest_ready(snapshot, 18))
        self.assertEqual(policy.fixed_quest_readiness_state()["hp_healing_budget"], 1100)

    def test_kill_number_readiness_uses_q_line_roster(self):
        info = QuestInfo(14, "Warg Problem", 5, 5, 2, dungeon=0, num_mon=16, monrace_id=257)
        warg = MonraceKnowledge(14, 120, False, False, max_melee_damage=1)
        policy = HengbotPolicy(self._town_map(), quest_knowledge={14: info}, monrace_knowledge={257: warg})
        snapshot = replace(
            self._town_snapshot(26, 97, {Position(26, 97): grid(26, 97)}, 0),
            player=player(26, 97, level=8, hp=5000, max_hp=5000, main_hand_blows=4, main_hand_to_d=30),
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True, damage_dice_num=3, damage_dice_sides=6)],
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True
        self.assertTrue(policy._fixed_quest_ready(snapshot, 14))
        self.assertEqual(policy.fixed_quest_readiness_state()["roster_size"], 16)

    def test_active_kill_floor_locks_healthy_exit_but_allows_teleport(self):
        info = QuestInfo(14, "Warg Problem", 5, 5, 2, dungeon=0, num_mon=16, monrace_id=257)
        quest = QuestState(id=14, status=1, type=5, level=5, dungeon_id=0, r_idx=257, cur_num=3, num_mon=16, fixed=True)
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [], floor_key=(0, 5, 14), quests={14: quest},
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT), item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        policy = HengbotPolicy(quest_knowledge={14: info})
        self.assertTrue(policy._quest_floor_exit_locked(snap))
        self.assertTrue(policy._floor_navigation_exit_locked(snap))
        self.assertIsNone(policy._escape_by_stairs(snap))
        self.assertEqual(policy._escape_scroll(snap).slot, "t")
        self.assertIsNone(policy._return_to_town_key(snap, []))

        complete = replace(snap, quests={14: replace(quest, cur_num=16)})
        self.assertFalse(policy._quest_floor_exit_locked(complete))

    def test_dying_kill_quest_with_no_teleport_may_take_stairs(self):
        info = QuestInfo(14, "Warg Problem", 5, 5, 2, dungeon=0, num_mon=16, monrace_id=257)
        quest = QuestState(id=14, status=1, type=5, level=5, dungeon_id=0, r_idx=257, cur_num=3, num_mon=16, fixed=True)
        snap = Snapshot(
            player(10, 10, hp=10, max_hp=100),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [], floor_key=(0, 5, 14), quests={14: quest},
        )
        policy = HengbotPolicy(quest_knowledge={14: info})
        self.assertFalse(policy._quest_floor_exit_locked(snap))
        self.assertEqual(policy._escape_by_stairs(snap), "<")

    def test_non_once_kill_quest_releases_after_stuck_budget(self):
        info = QuestInfo(14, "Warg Problem", 5, 5, 2, dungeon=0, num_mon=16, monrace_id=257)
        quest = QuestState(id=14, status=1, type=5, level=5, dungeon_id=0, cur_num=15, num_mon=16, fixed=True)
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [], floor_key=(0, 5, 14), quests={14: quest},
        )
        policy = HengbotPolicy(quest_knowledge={14: info})
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT
        self.assertFalse(policy._quest_floor_exit_locked(snap))
        self.assertEqual(policy._escape_by_stairs(snap), "<")

    def test_once_kill_level_only_releases_when_dying_without_teleport(self):
        info = QuestInfo(28, "Royal Crypt", 1, 70, QUEST_FLAG_ONCE, dungeon=0, max_num=1, monrace_id=999)
        quest = QuestState(id=28, status=1, type=1, level=70, dungeon_id=0, cur_num=0, max_num=1, fixed=True)
        healthy = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [], floor_key=(0, 70, 28), quests={28: quest},
        )
        policy = HengbotPolicy(quest_knowledge={28: info})
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT
        self.assertTrue(policy._quest_floor_exit_locked(healthy))
        dying = replace(healthy, player=player(10, 10, hp=10, max_hp=100))
        self.assertTrue(policy._kill_quest_exit_would_fail(dying))
        self.assertFalse(policy._quest_floor_exit_locked(dying))
        self.assertEqual(policy._escape_by_stairs(dying), "<")

    def test_kill_level_completion_uses_max_num_not_nonzero_num_mon(self):
        info = QuestInfo(28, "Royal Crypt", 1, 70, QUEST_FLAG_ONCE, dungeon=0, num_mon=99, max_num=1, monrace_id=999)
        quest = QuestState(id=28, status=1, type=1, cur_num=1, max_num=1, num_mon=99)
        snap = Snapshot(player(10, 10), {}, [], floor_key=(0, 70, 28), quests={28: quest})
        self.assertIsNone(HengbotPolicy(quest_knowledge={28: info})._active_kill_quest_id(snap))

    def test_descent_guard_selects_kill_quest_in_current_dungeon(self):
        other = QuestInfo(14, "Other", 5, 3, 0, dungeon=1, num_mon=16)
        current = QuestInfo(28, "Current", 1, 5, 0, dungeon=2, max_num=1)
        quests = {
            14: QuestState(id=14, status=0),
            28: QuestState(id=28, status=0),
        }
        snap = Snapshot(
            player(10, 10, class_id=-1),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [], floor_key=(2, 5, 0), quests=quests,
        )
        policy = HengbotPolicy(quest_knowledge={14: other, 28: current})
        self.assertFalse(policy._is_descent_target(snap, snap.grids[Position(10, 10)]))

    def test_real_lib_fixed_quest_rosters_25_and_28_run_through_readiness(self):
        edit = Path(r"C:\hengband\lib\edit")
        quest_path = edit / "QuestDefinitionList.txt"
        monrace_path = edit / "MonraceDefinitions.jsonc"
        if not quest_path.is_file() or not monrace_path.is_file():
            self.skipTest("real Hengband lib/edit is not available")
        quests = load_quest_knowledge(quest_path)
        monraces = load_monrace_knowledge(monrace_path)
        policy = HengbotPolicy(
            self._town_map(), quest_knowledge=quests, monrace_knowledge=monraces
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True
        for quest_id in (25, 28):
            with self.subTest(quest_id=quest_id):
                snapshot = replace(
                    self._town_snapshot(26, 97, {Position(26, 97): grid(26, 97)}, 0),
                    player=player(
                        26, 97, level=quests[quest_id].level + FIXED_QUEST_LEVEL_MARGIN,
                        hp=100000, max_hp=100000, main_hand_blows=10,
                        main_hand_to_d=100000,
                    ),
                    equipment=[item(
                        "main_hand", TVAL_SWORD, 1, is_equipment=True,
                        damage_dice_num=10, damage_dice_sides=10,
                    )],
                )
                self.assertTrue(policy._fixed_quest_ready(snapshot, quest_id))

    def test_fixed_quest_quaffs_speed_once_on_first_engagement(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, monster=True),
        }
        snapshot = replace(
            self._town_snapshot(10, 10, grids, 1),
            player=player(10, 10, hp=100, max_hp=100, level=8,
                          main_hand_blows=2, main_hand_to_d=10),
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)],
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True,
                            damage_dice_num=2, damage_dice_sides=6)],
            visible_monsters=[hostile(1, 10, 11, hp=10, max_melee_damage=1)],
            floor_key=(0, 0, self.QUEST_ID),
            town_flag=False,
            town_id=-1,
        )
        policy = HengbotPolicy(self._town_map())

        self.assertEqual(policy.choose_key(snapshot), "qs")
        self.assertEqual(policy.last_reason, "quest:quaff-speed")
        self.assertNotEqual(policy.choose_key(snapshot), "qs")

        not_once = QuestInfo(1, "Thieves Hideout", 6, 5, 2)
        policy = HengbotPolicy(self._town_map(), quest_knowledge={1: not_once})
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        original = self._town_snapshot(
            26, 97, {Position(26, 97): grid(26, 97, building_special=1)}, 0
        )
        self.assertEqual(policy._fixed_quest_target(original), 1)

    def test_non_once_fixed_quest_allows_recoverable_floor_exit(self):
        info = QuestInfo(1, "Repeatable Hideout", 6, 5, 2)
        quest = self._quest(1)
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [], floor_key=(0, 1, 1), quests={1: quest},
        )
        policy = HengbotPolicy(quest_knowledge={1: info})
        policy._returning_to_town = True

        self.assertEqual(policy._active_fixed_quest_id(snap), 1)
        self.assertEqual(policy._return_to_town_key(snap, []), "<")
        self.assertEqual(policy.last_reason, "return:ascend")

    def test_selects_lowest_level_eligible_untaken_quest(self):
        quest18 = replace(self._quest(0), id=18, level=35)
        quest25 = replace(self._quest(0), id=25, level=48)
        knowledge = {
            18: QuestInfo(18, "Water Cave", 4, 35, 6),
            25: QuestInfo(25, "Haunted House", 6, 48, 6),
        }
        policy = HengbotPolicy(self._town_map(), quest_knowledge=knowledge)
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        snapshot = replace(
            self._town_snapshot(
                26, 97,
                {
                    Position(26, 98): grid(26, 98, building_special=18),
                    Position(30, 40): grid(30, 40, building_special=25),
                },
                0,
            ),
            quests={25: quest25, 18: quest18},
        )

        self.assertEqual(policy._fixed_quest_target(snapshot), 18)

    def test_existing_taken_kill_quest_is_selected_before_new_acceptance(self):
        quest14 = replace(self._quest(1), id=14, level=5, flags=2)
        quest18 = replace(self._quest(0), id=18, level=35)
        knowledge = {
            14: QuestInfo(14, "Warg Problem", 1, 5, 2),
            18: QuestInfo(18, "Water Cave", 4, 35, 6),
        }
        policy = HengbotPolicy(self._town_map(), quest_knowledge=knowledge)
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        snapshot = replace(
            self._town_snapshot(26, 97, {}, 0),
            quests={18: quest18, 14: quest14},
        )

        self.assertEqual(policy._fixed_quest_target(snapshot), 14)

    def test_generalized_castle_quest_claim_latches_shared_reward_tile(self):
        quest_id = 18
        quest = replace(self._quest(2), id=quest_id, level=35)
        town_map = replace(
            self._town_map(),
            quest_buildings={quest_id: frozenset({Position(26, 98)})},
        )
        grids = {
            Position(26, 97): grid(26, 97),
            Position(26, 98): grid(
                26, 98, building_type=1, building_special=quest_id
            ),
        }
        snapshot = replace(
            self._town_snapshot(26, 97, grids, 2),
            quests={quest_id: quest},
        )
        policy = HengbotPolicy(town_map)

        self.assertEqual(policy.choose_key(snapshot), "6q\x1b")
        self.assertEqual(policy.last_reason, "fixedquest:claim")
        self.assertEqual(policy._fixed_quest_reward_pending, quest_id)
        self.assertEqual(
            policy._fixed_quest_reward_positions(snapshot, quest_id),
            frozenset({Position(27, 98)}),
        )

    def test_enters_taken_fixed_quest_from_visible_entrance(self):
        grids = {
            Position(35, 176): grid(35, 176),
            Position(35, 177): grid(
                35, 177, has_quest_enter=True, quest_id=self.QUEST_ID
            ),
        }
        policy = HengbotPolicy(self._town_map())

        key = policy.choose_key(self._town_snapshot(35, 176, grids, 1))

        self.assertEqual(key, "6y")
        self.assertEqual(policy.last_reason, "fixedquest:enter")

    def test_taken_q1_approach_does_not_enter_dead_end_town_loop(self):
        origin = Position(26, 109)
        entrance = Position(35, 177)
        northeast_detour = {
            Position(25, x) for x in range(110, entrance.x + 1)
        } | {
            Position(y, entrance.x) for y in range(25, entrance.y + 1)
        }
        town_map = replace(
            self._town_map(),
            walkable=frozenset(northeast_detour),
        )
        grids = {
            origin: grid(origin.y, origin.x),
            Position(27, 110): grid(27, 110),
            entrance: grid(
                entrance.y,
                entrance.x,
                has_quest_enter=True,
                quest_id=self.QUEST_ID,
            ),
        }
        policy = HengbotPolicy(town_map)

        position = origin
        visited = {position}
        offsets = {
            "7": (-1, -1),
            "8": (-1, 0),
            "9": (-1, 1),
            "4": (0, -1),
            "6": (0, 1),
            "1": (1, -1),
            "2": (1, 0),
            "3": (1, 1),
        }
        for _ in range(120):
            key = policy.choose_key(
                self._town_snapshot(
                    position.y, position.x, grids, QUEST_STATUS_TAKEN
                )
            )
            if position == entrance:
                self.assertEqual(key, ">y")
                break
            dy, dx = offsets[key[0]]
            position = Position(position.y + dy, position.x + dx)
            self.assertNotIn(position, visited)
            visited.add(position)
        else:
            self.fail("quest entrance was not reached")

        self.assertEqual(position, entrance)

    def test_taken_q1_approach_prefers_viable_southeast_route(self):
        origin = Position(26, 109)
        entrance = Position(35, 177)
        northeast_detour = {
            Position(25, x) for x in range(110, entrance.x + 1)
        } | {
            Position(y, entrance.x) for y in range(25, entrance.y + 1)
        }
        southeast_route = {
            Position(y, 110) for y in range(27, entrance.y + 1)
        } | {
            Position(entrance.y, x) for x in range(110, entrance.x + 1)
        }
        town_map = replace(
            self._town_map(),
            walkable=frozenset(northeast_detour | southeast_route),
        )
        grids = {
            origin: grid(origin.y, origin.x),
            entrance: grid(
                entrance.y,
                entrance.x,
                has_quest_enter=True,
                quest_id=self.QUEST_ID,
            ),
        }
        policy = HengbotPolicy(town_map)

        key = policy.choose_key(
            self._town_snapshot(origin.y, origin.x, grids, QUEST_STATUS_TAKEN)
        )

        self.assertEqual(key, "3")
        self.assertEqual(policy.last_reason, "fixedquest:approach")

    def test_claims_completed_fixed_quest_and_latches_reward(self):
        grids = {
            Position(26, 97): grid(26, 97),
            Position(26, 98): grid(26, 98, building_type=1, building_special=1),
        }
        policy = HengbotPolicy(self._town_map())

        key = policy.choose_key(self._town_snapshot(26, 97, grids, 2))

        self.assertEqual(key, "6q\x1b")
        self.assertEqual(policy.last_reason, "fixedquest:claim")
        self.assertEqual(policy._fixed_quest_reward_pending, self.QUEST_ID)

    def test_completed_fixed_quest_floor_heads_for_upstairs(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(
                10, 11, upstairs=True, has_quest_exit=True, quest_id=self.QUEST_ID
            ),
        }
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(0, 1, self.QUEST_ID),
            quests={self.QUEST_ID: self._quest(2)},
        )
        policy = HengbotPolicy()

        key = policy.choose_key(snap)

        self.assertEqual(key, "6")
        self.assertEqual(policy.last_reason, "fixedquest:seek-exit")

    def test_pack_full_taken_quest_does_not_route_to_exit(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(
                10, 11, upstairs=True, has_quest_exit=True, quest_id=self.QUEST_ID
            ),
        }
        inventory = [item(chr(ord("a") + i), 1, i) for i in range(PACK_CAPACITY)]
        snap = Snapshot(
            player(10, 10),
            grids,
            inventory,
            floor_key=(0, 1, self.QUEST_ID),
            quests={self.QUEST_ID: self._quest(1)},
        )
        policy = HengbotPolicy()

        key = policy._return_to_town_key(snap, [])

        self.assertIsNone(key)
        self.assertFalse(policy._returning_to_town)

    def test_completed_quest_leaves_from_quest_exit(self):
        grids = {
            Position(10, 10): grid(
                10, 10, upstairs=True, has_quest_exit=True, quest_id=self.QUEST_ID
            )
        }
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(0, 1, self.QUEST_ID),
            quests={self.QUEST_ID: self._quest(2)},
        )
        policy = HengbotPolicy()

        key = policy.choose_key(snap)

        self.assertEqual(key, "<")
        self.assertEqual(policy.last_reason, "fixedquest:exit")

    def test_collects_pending_fixed_quest_reward_from_reward_tile(self):
        grids = {
            Position(27, 97): grid(27, 97),
            Position(27, 98): grid(27, 98, objects=1),
        }
        policy = HengbotPolicy(self._town_map(reward=True))
        policy._fixed_quest_reward_pending = self.QUEST_ID

        key = policy.choose_key(self._town_snapshot(27, 97, grids, 3))

        self.assertEqual(key, "6")
        self.assertEqual(policy.last_reason, "fixedquest:reward-approach")

        policy._floor_key = (0, 0, 0)
        policy._last_position = Position(27, 97)
        pickup = self._town_snapshot(27, 98, grids, 3)
        key = policy.choose_key(pickup)

        self.assertEqual(key, "g")
        self.assertEqual(policy.last_reason, "fixedquest:reward-pickup")

        policy._floor_key = (0, 0, 0)
        policy._last_position = Position(27, 98)
        empty_grids = {
            Position(27, 97): grid(27, 97),
            Position(27, 98): grid(27, 98),
        }
        empty = self._town_snapshot(27, 98, empty_grids, 3)
        self.assertIsNone(policy._fixed_quest_key(empty, []))
        self.assertIsNone(policy._fixed_quest_reward_pending)
        self.assertIsNone(policy._fixed_quest_key(empty, []))
        self.assertNotEqual(policy.last_reason, "fixedquest:reward-approach")

    def test_emergency_upstairs_reason_records_quest_failure(self):
        grids = {
            Position(10, 10): grid(
                10, 10, upstairs=True, has_quest_exit=True, quest_id=self.QUEST_ID
            ),
            Position(10, 11): grid(10, 11),
        }
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(0, 1, self.QUEST_ID),
            quests={self.QUEST_ID: self._quest(1)},
        )
        policy = HengbotPolicy()
        policy._emergency_escape_pending = True

        key = policy._emergency_item(snap, [])

        self.assertEqual(key, "<")
        self.assertEqual(policy.last_reason, "emergency:stairs-quest-fail")


class ApprovedQuestStrategyExecutionTest(unittest.TestCase):
    QUEST_ID = 1

    @classmethod
    def setUpClass(cls):
        cls.profiles = load_quest_strategies(Path("strategy/quests"))
        q1_terrain = {
            (y, x): ("wall" if y in {4, 9} or x in {0, 14} else "floor")
            for y in range(4, 10) for x in range(15)
        }
        q1_terrain.update({(5, 4): "door", (8, 4): "door", (8, 1): "exit"})
        cls.q1_battlefield = QuestBattlefield(
            terrain=q1_terrain, player_start=(8, 1), entrance=(8, 1), exit=(8, 1),
            searchable=((5, 4), (8, 4)),
        )
        cls.q34_battlefield = QuestBattlefield(monster_placements=(
            ((3, 13), 174), ((7, 15), 243), ((9, 11), 107), ((11, 9), 107),
        ))

    def _policy(self):
        stationary = MonraceKnowledge(
            10, 110, False, False, flags=frozenset({"NEVER_MOVE"})
        )
        mobile = MonraceKnowledge(10, 110, False, False)
        return HengbotPolicy(
            quest_strategies=self.profiles,
            quest_knowledge={
                1: QuestInfo(
                    1, "Thieves Hideout", 6, 5, 6,
                    battlefield=self.q1_battlefield,
                ),
                34: QuestInfo(
                    34, "Dump Witness", 6, 5, 6,
                    battlefield=self.q34_battlefield,
                )
            },
            monrace_knowledge={107: stationary, 243: stationary, 174: mobile},
        )

    def _quest(self, status):
        return QuestState(id=1, status=status, type=6, level=5, flags=6, fixed=True)

    def _force_snapshot(self, quest_id, *, hp, torches, speed=1, healing=2,
                        abilities=frozenset()):
        inventory = [
            item("t", TVAL_LITE, SV_LITE_TORCH, count=torches, fuel=5000),
            item("s", TVAL_POTION, SV_POTION_SPEED, count=speed),
            item("h", TVAL_POTION, SV_POTION_HEALING, count=healing),
        ]
        return Snapshot(
            player(1, 1, hp=hp, max_hp=hp, abilities=abilities),
            {Position(1, 1): grid(1, 1)}, [], inventory=inventory,
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True)],
            floor_key=(0, 0, quest_id),
        )

    def test_acceptance_base_tier_revert_proofs_each_component(self):
        policy = self._policy()
        profile = policy.approved_quest_strategy(1)
        self.assertIsNotNone(profile)
        base = self._force_snapshot(1, hp=36, torches=5)
        with patch("hengbot.policy.weapon_expected_dps", return_value=28):
            self.assertTrue(policy._approved_strategy_force_ready(base, profile))
            for changed in (
                replace(base, player=replace(base.player, hp=35, max_hp=35)),
                replace(base, inventory=[*base.inventory[:1], base.inventory[2]]),
                replace(base, inventory=[base.inventory[0], base.inventory[1],
                                         replace(base.inventory[2], count=1)]),
                replace(base, inventory=[replace(base.inventory[0], count=4),
                                         *base.inventory[1:]]),
            ):
                with self.subTest(changed=changed):
                    self.assertFalse(policy._approved_strategy_force_ready(changed, profile))
        with patch("hengbot.policy.weapon_expected_dps", return_value=27.99):
            self.assertFalse(policy._approved_strategy_force_ready(base, profile))
        resisted_profile = replace(
            profile, required_force={**profile.required_force, "resists": ["fire"]}
        )
        with patch("hengbot.policy.weapon_expected_dps", return_value=28):
            self.assertFalse(policy._approved_strategy_force_ready(base, resisted_profile))
            fire_ready = replace(
                base, player=replace(base.player, abilities=frozenset({"resist_fire"}))
            )
            self.assertTrue(policy._approved_strategy_force_ready(fire_ready, resisted_profile))

    def test_no_healing_tier_waives_potions_not_torches(self):
        policy = self._policy()
        profile = policy.approved_quest_strategy(1)
        no_potions = self._force_snapshot(1, hp=88, torches=5, speed=0, healing=0)
        no_potions = replace(no_potions, inventory=no_potions.inventory[:1])
        with patch("hengbot.policy.weapon_expected_dps", return_value=28):
            self.assertTrue(policy._approved_strategy_force_ready(no_potions, profile))
            short_ammo = replace(
                no_potions, inventory=[replace(no_potions.inventory[0], count=4)]
            )
            self.assertFalse(policy._approved_strategy_force_ready(short_ammo, profile))

    def test_acceptance_errand_reserves_and_routes_q34_torches(self):
        policy = self._policy()
        torches = item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=5000)
        quest = QuestState(id=34, status=0, fixed=True, level=5)
        snap = Snapshot(player(10, 10, class_id=PLAYER_CLASS_WARRIOR), {Position(10, 10): grid(10, 10, building_special=34)}, [],
                        floor_key=(0, 0, 0), town_flag=True, quests={34: quest},
                        inventory=[torches])
        self.assertEqual(policy._retention_reservation(snap, torches), 20)
        short = replace(snap, inventory=[replace(torches, count=19)])
        needs = policy._enumerate_town_needs(short)
        self.assertTrue(any(
            need.store_type == STORE_GENERAL and need.category == "quest-throwing-items"
            for need in needs
        ))

    def test_procurement_unions_carries_for_all_currently_offered_quests(self):
        policy = self._policy()
        quests = {
            quest_id: QuestState(
                id=quest_id, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5
            )
            for quest_id in (1, 34)
        }
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10, building_special=1),
                Position(10, 11): grid(10, 11, building_special=34),
            },
            [], floor_key=(0, 0, 0), town_flag=True, quests=quests,
        )

        strategy = policy._carry_procurement_strategy(snapshot)

        self.assertIsNotNone(strategy)
        self.assertEqual(strategy.required_force["throwing_items"]["lit_torch"], 20)
        self.assertEqual(strategy.required_force["speed_potions"], 1)
        self.assertEqual(strategy.required_force["heal_potions"], 2)
        torch = StoreItem(
            "a", "Torch", 99, TVAL_LITE, SV_LITE_TORCH,
            price=1, aware=True, known=True,
        )
        self.assertEqual(policy._purchase_quantity(snapshot, torch), 20)
        needs = policy._enumerate_town_needs(snapshot)
        self.assertIn(
            policy_module.TownNeed(STORE_GENERAL, "quest-throwing-items", "normal"),
            needs,
        )
        self.assertIn(
            policy_module.TownNeed(STORE_BLACK, "quest-speed", "normal"), needs
        )

    def test_completed_mining_rearms_normal_maintenance_restock(self):
        policy = self._policy()
        policy._deepest_level = 5
        policy._fundraising_mode = "mine"
        policy._mining_runs_completed = 1
        policy._planned_mining_runs = 1
        policy._town_restock_suppressed = True
        policy._town_errand_plan = policy_module.TownErrandPlan([STORE_HOME])
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=14000),
            {Position(10, 10): grid(10, 10, building_special=1)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            quests={1: self._quest(QUEST_STATUS_UNTAKEN)},
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=4),
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=4),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            ],
            equipment=[
                item("L", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, known=True),
                item("main_hand", TVAL_SWORD, 1, is_equipment=True),
            ],
        )

        with patch.object(policy, "_effective_mining_run_target", return_value=1):
            self.assertIsNone(policy._town_special_key(snapshot))

        self.assertIsNone(policy._fundraising_mode)
        self.assertFalse(policy._town_restock_suppressed)
        self.assertIsNone(policy._town_errand_plan)
        requirements = {
            entry["item"]: entry for entry in policy.procurement_requirements(snapshot)
        }
        self.assertEqual(requirements["Word of Recall scrolls"]["missing"], 1)
        self.assertEqual(requirements["Flasks of oil"]["missing"], 1)
        needs = policy._enumerate_town_needs(snapshot)
        self.assertIn(policy_module.TownNeed(STORE_GENERAL, "oil", "normal"), needs)
        self.assertIn(
            policy_module.TownNeed(STORE_BLACK, "quest-speed", "normal"), needs
        )
        self.assertIsNotNone(policy._next_required_store_type(snapshot))

    def test_force_ready_q34_retention_does_not_recurse_through_departure(self):
        policy = self._policy()
        snap = self._force_snapshot(34, hp=605, torches=20, speed=1, healing=25)
        snap = replace(
            snap,
            floor_key=(0, 0, 0),
            town_flag=True,
            quests={34: QuestState(id=34, status=0, fixed=True, level=5)},
        )
        torches = snap.inventory[0]

        # Model the live readiness tail directly: fixed-quest readiness reaches
        # departure readiness, which asks Home retention about the same pack.
        with patch.object(
            policy,
            "_fixed_quest_ready",
            side_effect=lambda current, _quest_id: policy._find_home_deposit(current) is None,
        ):
            self.assertEqual(policy._retention_reservation(snap, torches), 20)
            self.assertIsNone(policy._find_home_deposit(snap))

    def test_q34_carry_purchase_stops_at_existing_gold_reserve(self):
        policy = self._policy()
        torch = StoreItem(
            letter="a", name="Torch", count=20, tval=TVAL_LITE,
            sval=SV_LITE_TORCH, price=10, aware=True, known=True,
        )
        quest = QuestState(id=34, status=0, fixed=True, level=5)
        base = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=1000),
            {Position(10, 10): grid(10, 10, building_special=34)}, [], floor_key=(0, 0, 0),
            town_flag=True, quests={34: quest},
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, count=12, fuel=5000)],
            store=StoreState(STORE_GENERAL, [torch]),
        )
        reserve = policy._fundraising_kit_reserve(base)
        blocked = replace(
            base, player=replace(base.player, gold=reserve + torch.price - 1)
        )

        self.assertIsNone(policy._next_purchase(blocked))
        affordable = replace(
            base, player=replace(base.player, gold=reserve + torch.price * 8)
        )
        self.assertEqual(policy._next_purchase(affordable), torch)

    def test_q34_hold_priority_and_bee_last(self):
        policy = self._policy()
        grids = {Position(10, x): grid(10, x) for x in range(15, 21)}
        torch = item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=5000)
        cloaker = replace(hostile(1, 10, 18, distance=2), race_id=243)
        sword = replace(hostile(2, 10, 16, distance=4), race_id=107)
        sword2 = replace(hostile(4, 10, 17, distance=3), race_id=107)
        bee = replace(hostile(3, 3, 13, distance=14), race_id=174)
        snap = Snapshot(player(10, 20, hp=100, max_hp=100), grids,
                        [bee, sword, sword2, cloaker], inventory=[torch],
                        floor_key=(0, 1, 34))
        policy._fixed_quest_speed_attempted = True
        self.assertEqual(policy._approved_quest_strategy_key(snap, snap.visible_monsters, []), "vt4")
        self.assertEqual(policy.last_reason, "quest-strategy:throw-torch")
        # Once the cloaker is gone, the death sword owns the volley; the bee is last.
        self.assertEqual(policy._approved_quest_strategy_key(
            replace(snap, visible_monsters=[bee, sword, sword2]), [bee, sword, sword2], []
        ), "vt4")
        self.assertEqual(policy._approved_quest_strategy_key(
            replace(snap, visible_monsters=[bee, sword2]), [bee, sword2], []
        ), "vt4")

        # The real final target is at [3,13], behind the [2,13] door.  There is
        # no ray from the [10,20] hold, so the final phase must release the hold
        # and traverse the doorway instead of relying on a fake visible bee.
        approach_grids = {
            **{Position(y, 20): grid(y, 20) for y in range(1, 11)},
            **{Position(1, x): grid(1, x) for x in range(13, 21)},
            Position(2, 13): grid(2, 13, closed_door=True),
            Position(3, 13): grid(3, 13),
        }
        final_hidden = replace(snap, grids=approach_grids, visible_monsters=[])
        policy._build_grid_index(final_hidden)
        self.assertFalse(policy._has_line_of_fire(
            final_hidden, Position(10, 20), Position(3, 13)
        ))
        self.assertEqual(
            policy._approved_quest_strategy_key(final_hidden, [], []), "8"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:approach-final-target")

    def test_q34_never_move_blocker_is_thrown_at_and_never_meleed(self):
        policy = self._policy()
        torch = item("t", TVAL_LITE, SV_LITE_TORCH, fuel=5000)
        blocker = replace(hostile(1, 9, 20, distance=1), race_id=243)
        grids = {
            Position(10, 19): grid(10, 19), Position(10, 20): grid(10, 20),
            Position(9, 20): grid(9, 20, monster=True),
        }
        snap = Snapshot(
            player(10, 19), grids, [blocker], inventory=[torch], floor_key=(0, 1, 34)
        )
        policy._fixed_quest_speed_attempted = True
        policy._build_grid_index(snap)

        self.assertEqual(policy._approved_quest_strategy_key(snap, [blocker], [blocker]), "vt9")
        self.assertEqual(policy.last_reason, "quest-strategy:throw-never-move-blocker")

    def test_never_move_races_come_from_monrace_flags_not_quest_ids(self):
        profile = replace(self.profiles[1], priority_targets=(900, 901))
        stationary = MonraceKnowledge(
            10, 110, False, False, flags=frozenset({"NEVER_MOVE"})
        )
        mobile = MonraceKnowledge(10, 110, False, False)
        policy = HengbotPolicy(monrace_knowledge={900: stationary, 901: mobile})

        self.assertEqual(policy._quest_never_move_races(profile), {900})

    def test_q34_final_approach_keeps_starvation_gate_reachable(self):
        policy = self._policy()
        fixed = [
            replace(hostile(1, 7, 15), race_id=243),
            replace(hostile(2, 9, 11), race_id=107),
            replace(hostile(3, 11, 9), race_id=107),
        ]
        base = Snapshot(player(10, 20), {Position(10, 20): grid(10, 20)}, fixed,
                        floor_key=(0, 1, 34))
        policy._fixed_quest_speed_attempted = True
        policy._approved_quest_strategy_key(base, fixed, [])
        hungry = replace(
            base, player=player(10, 20, food=1500), visible_monsters=[],
            inventory=[item("f", TVAL_FOOD, FOOD)],
        )

        self.assertEqual(policy._approved_quest_strategy_key(hungry, [], []), "Ef")
        self.assertEqual(policy.last_reason, "survival:eat")

    def test_approved_quest_uses_profile_heal_threshold(self):
        policy = self._policy()
        threat = replace(hostile(1, 10, 21, distance=1), race_id=174)
        snap = Snapshot(
            player(10, 20, hp=54, max_hp=100),
            {Position(10, 20): grid(10, 20), Position(10, 21): grid(10, 21, monster=True)},
            [threat], inventory=[item("h", TVAL_POTION, SV_POTION_HEALING)],
            floor_key=(0, 1, 34),
        )
        policy._fixed_quest_speed_attempted = True

        self.assertEqual(policy.choose_key(snap), "qh")
        self.assertEqual(policy.last_reason, "item:heal")

    def test_q1_retakes_hold_and_throws_at_distance_two(self):
        policy = self._policy()
        grids = {Position(8, x): grid(8, x) for x in range(1, 6)}
        displaced = Snapshot(player(8, 2), grids, [], floor_key=(0, 1, 1))
        policy._build_grid_index(displaced)
        self.assertEqual(policy._approved_quest_strategy_key(displaced, [], []), "6")
        thief = replace(hostile(1, 8, 5, distance=2), race_id=150)
        at_hold = replace(displaced, player=player(8, 3), visible_monsters=[thief],
                          inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, fuel=5000)])
        policy._fixed_quest_speed_attempted = True
        self.assertEqual(policy._approved_quest_strategy_key(at_hold, [thief], []), "vt6")

    def test_q1_recovers_thrown_torch_before_retaking_hold(self):
        policy = self._policy()
        grids = {
            Position(8, 3): grid(8, 3),
            Position(8, 4): grid(8, 4),
            Position(8, 5): grid(8, 5, objects=1),
        }
        displaced = Snapshot(player(8, 4), grids, [], floor_key=(0, 5, 1))
        policy._build_grid_index(displaced)

        self.assertEqual(
            policy._approved_quest_strategy_key(displaced, [], []), "6"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:recover-torch")

    def test_q1_holds_position_between_visible_waves(self):
        policy = self._policy()
        at_hold = Snapshot(
            player(8, 3), {Position(8, 3): grid(8, 3)}, [], floor_key=(0, 5, 1)
        )
        policy._build_grid_index(at_hold)

        self.assertEqual(policy._approved_quest_strategy_key(at_hold, [], []), "5")
        self.assertEqual(policy.last_reason, "quest-strategy:hold")

    def test_completed_q1_leaves_hold_for_quest_exit(self):
        policy = self._policy()
        grids = {
            Position(8, 3): grid(8, 3),
            Position(8, 4): grid(8, 4, upstairs=True, has_quest_exit=True, quest_id=1),
        }
        completed = Snapshot(
            player(8, 3), grids, [], floor_key=(0, 5, 1),
            quests={1: QuestState(id=1, status=QUEST_STATUS_COMPLETED, fixed=True)},
        )

        self.assertEqual(policy.choose_key(completed), "4")
        self.assertEqual(policy.last_reason, "quest:exit:route")

    def test_conditional_speed_uses_live_three_turn_projection(self):
        policy = self._policy()
        monster = replace(hostile(1, 8, 5), race_id=150)
        snap = Snapshot(player(8, 3, hp=100, max_hp=100),
                        {Position(8, x): grid(8, x) for x in range(3, 6)}, [monster],
                        inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)],
                        floor_key=(0, 1, 1))
        with patch.object(policy, "threat_prediction", return_value={"operational_total": 49}):
            self.assertNotEqual(policy._approved_quest_strategy_key(snap, [monster], []), "qs")
        with patch.object(policy, "threat_prediction", return_value={"operational_total": 50}):
            self.assertEqual(policy._approved_quest_strategy_key(snap, [monster], []), "qs")

    def test_abort_allowed_leaves_at_threshold_but_once_profiles_do_not(self):
        upstairs = {Position(10, 10): grid(10, 10, upstairs=True)}
        q14 = Snapshot(player(10, 10, hp=30, max_hp=100), upstairs, [],
                       floor_key=(0, 5, 14))
        policy = self._policy()
        self.assertEqual(policy._approved_quest_strategy_key(q14, [], []), "<")
        self.assertEqual(policy.last_reason, "quest-strategy:abort")
        for quest_id in (1, 34):
            with self.subTest(quest_id=quest_id):
                snap = replace(q14, floor_key=(0, 1, quest_id))
                self.assertNotEqual(
                    self._policy()._approved_quest_strategy_key(snap, [], []), "<"
                )

    def test_flee_upstairs_reason_records_quest_failure(self):
        grids = {
            Position(10, 10): grid(
                10, 10, upstairs=True, has_quest_exit=True, quest_id=self.QUEST_ID
            ),
            Position(10, 11): grid(10, 11, monster=True),
        }
        snap = Snapshot(
            player(10, 10, hp=20, max_hp=150),
            grids,
            [hostile(1, 10, 11, hp=100)],
            floor_key=(0, 1, self.QUEST_ID),
            quests={self.QUEST_ID: self._quest(1)},
        )
        policy = HengbotPolicy()

        key = policy.choose_key(snap)

        self.assertEqual(key, "<")
        self.assertEqual(policy.last_reason, "flee:stairs-quest-fail")


class ProbeTest(unittest.TestCase):
    def _sole_frontier_snapshot(self):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(10, 14)
        }
        grids[Position(10, 10)] = grid(10, 10)
        grids[Position(10, 11)] = grid(10, 11)
        grids[Position(10, 12)] = grid(10, 12, upstairs=True)
        return Snapshot(
            player(10, 10), grids, [], width=30, height=30, floor_key=(2, 4, 0)
        )

    def test_probes_when_standing_on_the_only_remaining_frontier(self):
        policy = HengbotPolicy()
        snap = self._sole_frontier_snapshot()
        policy._floor_key = snap.floor_key
        policy._visit_counts.update(
            {Position(10, x): 1 for x in range(10, 13)}
        )

        self.assertEqual(policy.choose_key(snap), "4")
        self.assertEqual(policy.last_reason, "probe")

    def test_searches_last_frontier_after_unknown_edge_rejects_probes(self):
        policy = HengbotPolicy()
        snap = self._sole_frontier_snapshot()
        policy._floor_key = snap.floor_key
        policy._visit_counts.update(
            {Position(10, x): 1 for x in range(10, 13)}
        )
        policy._blocked_unknown.update({(9, 9), (10, 9), (11, 9)})

        self.assertEqual(policy.choose_key(snap), "s")
        self.assertEqual(policy.last_reason, "search")

    def test_probe_step_targets_orthogonal_unknown(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9, passable=False),
            Position(9, 10): grid(9, 10, passable=False),
            Position(11, 10): grid(11, 10, passable=False),
        }
        # (10,11) is absent (unknown) and in bounds → the probe target.
        snap = Snapshot(player(10, 10), grids, [], width=20, height=20)
        policy = HengbotPolicy()
        policy._build_grid_index(snap)
        self.assertEqual(policy._probe_unknown_step(snap), Position(10, 11))

    def test_probe_step_prefers_down_over_left_on_tie(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(9, 10): grid(9, 10, passable=False),
            Position(10, 11): grid(10, 11, passable=False),
        }
        snap = Snapshot(player(10, 10), grids, [], width=20, height=20)
        policy = HengbotPolicy()
        policy._build_grid_index(snap)

        self.assertEqual(policy._probe_unknown_step(snap), Position(11, 10))

    def test_probes_into_unknown_when_oscillating(self):
        # Boxed on three sides; the fourth (east) is an unexplored tile absent
        # from the snapshot. The pathfinder can't reach it, so once the bot is
        # seen to be circling, it probes east into the unknown to reveal it.
        grids = {Position(10, 10): grid(10, 10)}
        for pos in [Position(9, 9), Position(9, 10), Position(9, 11), Position(10, 9),
                    Position(11, 9), Position(11, 10), Position(11, 11)]:
            grids[pos] = grid(pos.y, pos.x, passable=False)
        snap = Snapshot(player(10, 10), grids, [], width=20, height=20)
        policy = HengbotPolicy()
        # Needs at least STUCK_WINDOW decisions before the oscillation is detected.
        results = [(policy.choose_key(snap), policy.last_reason) for _ in range(14)]
        probes = [key for key, reason in results if reason == "probe"]
        self.assertTrue(probes, f"expected a probe once oscillating; got {results}")
        self.assertEqual(probes[0], "6")

    def test_probes_diagonal_only_unknown_neighbor(self):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(9, 12)
            if (y, x) != (9, 11)
        }
        grids[Position(10, 10)] = grid(10, 10)
        snap = Snapshot(player(10, 10), grids, [], width=20, height=20)

        direct_policy = HengbotPolicy()
        direct_policy._build_grid_index(snap)
        self.assertEqual(
            direct_policy._probe_unknown_step(snap), Position(9, 11)
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "9")
        self.assertEqual(policy.last_reason, "probe")

    def test_probe_prefers_orthogonal_unknown_over_diagonal(self):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(9, 12)
            if (y, x) not in {(9, 11), (10, 11)}
        }
        grids[Position(10, 10)] = grid(10, 10)
        snap = Snapshot(player(10, 10), grids, [], width=20, height=20)
        policy = HengbotPolicy()
        policy._build_grid_index(snap)

        self.assertEqual(policy._probe_unknown_step(snap), Position(10, 11))

    def test_blocked_diagonal_unknown_stops_being_frontier(self):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(9, 12)
            if (y, x) != (9, 11)
        }
        origin = Position(10, 10)
        target = Position(9, 11)
        grids[origin] = grid(10, 10)
        snap = Snapshot(player(10, 10), grids, [], width=20, height=20)
        policy = HengbotPolicy()
        policy._build_grid_index(snap)

        for _ in range(policy_module.PROBE_LIMIT):
            self.assertEqual(policy._probe_unknown_step(snap), target)

        self.assertIn((target.y, target.x), policy._blocked_unknown)
        self.assertFalse(policy._is_frontier(snap, grids[origin]))

    def test_escapes_a_searched_pocket_by_least_visited_route(self):
        # The live dl1 loop had three heavily visited cells north/east and an
        # older corridor continuing south. Once probing/searching was exhausted,
        # repeatedly seeking a flickering frontier pulled the bot north again.
        floors = {
            Position(8, 153),
            Position(9, 152),
            Position(9, 153),
            Position(10, 152),
            Position(11, 152),
            Position(12, 152),
        }
        grids = {pos: grid(pos.y, pos.x) for pos in floors}
        for pos in floors:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    neighbor = Position(pos.y + dy, pos.x + dx)
                    if neighbor not in floors and neighbor not in grids:
                        grids[neighbor] = grid(neighbor.y, neighbor.x, passable=False)

        policy = HengbotPolicy()
        policy._floor_key = (2, 1, 0)
        policy._recent.extend(
            [Position(8, 153), Position(9, 152), Position(9, 153)] * 4
        )
        policy._visit_counts.update(
            {
                Position(8, 153): 13,
                Position(9, 152): 18,
                Position(9, 153): 10,
                Position(10, 152): 9,
                Position(11, 152): 7,
            }
        )
        policy._search_counts[(9, 152)] = 8

        snap = Snapshot(
            player(9, 152), grids, [], floor_key=(2, 1, 0), width=200, height=100
        )
        self.assertEqual(policy.choose_key(snap), "2")
        self.assertEqual(policy.last_reason, "breakout:seek-frontier")


class TownRestockTest(unittest.TestCase):
    def _in_general_store(
        self, items, *, gold=500, inv=None, food_type=0, level=1, class_id=-1
    ):
        grids = {Position(10, 10): grid(10, 10)}
        return Snapshot(
            player(
                10, 10, gold=gold, food_type=food_type,
                level=level, class_id=class_id,
            ),
            grids,
            [],
            floor_key=(0, 0, 0),
            inventory=inv or [],
            equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000)],
            store=StoreState(store_type=STORE_GENERAL, items=items),
        )

    def test_buys_rations_when_food_stock_is_low(self):
        wares = [
            store_item("e", TVAL_FLASK, SV_FLASK_OIL, price=3),
            store_item("b", TVAL_FOOD, 35, price=5, count=60),
        ]
        inv = [item("f", TVAL_FLASK, SV_FLASK_OIL, count=8, fuel=500)]  # oil stocked
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(self._in_general_store(wares, inv=inv)), "pb5\r\r")
        self.assertEqual(pol.last_reason, "shop:buy-food")

    def test_mana_race_does_not_buy_rations_as_food(self):
        wares = [store_item("b", TVAL_FOOD, 35, price=3, count=60)]
        snap = self._in_general_store(
            wares, inv=[], food_type=FOOD_TYPE_MANA,
            level=4, class_id=PLAYER_CLASS_WARRIOR,
        )
        pol = HengbotPolicy()

        self.assertEqual(pol._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(pol.last_reason, "shop:leave")

        # The same shortage is owned by the race-aware ledger and routes to the
        # Magic store, where charged devices are the only valid food purchase.
        town = replace(snap, store=None, town_flag=True)
        self.assertEqual(pol._supply_ledger(town, 1)["food"].stores, (STORE_MAGIC,))
        self.assertIn(
            TownNeed(STORE_MAGIC, "food", "normal"),
            pol._enumerate_town_needs(town),
        )

    def test_legacy_mana_character_does_not_buy_rations(self):
        wares = [store_item("b", TVAL_FOOD, 35, price=3, count=60)]
        snap = self._in_general_store(
            wares, inv=[], food_type=FOOD_TYPE_MANA, class_id=-1
        )

        policy = HengbotPolicy()
        self.assertIsNone(policy._next_purchase_unreserved(snap))
        town = replace(snap, store=None, town_flag=True)
        self.assertIn(
            STORE_MAGIC,
            [need.store_type for need in policy._enumerate_town_needs(town)],
        )

    def test_walks_to_the_store_for_a_food_restock(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): GridState(
                position=Position(10, 12), known=True, passable=True, wall=False,
                has_monster=False, has_down_stairs=False, has_up_stairs=False,
                unsafe=False, store_number=STORE_GENERAL,
            ),
        }
        snap = Snapshot(
            player(10, 10, gold=200),
            grids,
            [],
            floor_key=(0, 0, 0),
            equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000)],
        )
        pol = HengbotPolicy()
        pol._owns_lantern = lambda s: True  # lantern equipped, food count is 0
        self.assertEqual(pol.choose_key(snap), "6")
        self.assertEqual(pol.last_reason, "shop:approach")

    def test_town_arrival_clears_an_old_store_give_up(self):
        pol = HengbotPolicy()
        pol._shopping_abandoned = True
        dungeon = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [], floor_key=(2, 3, 0)
        )
        pol.choose_key(dungeon)
        town = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0)
        )
        pol.choose_key(town)
        self.assertFalse(pol._shopping_abandoned)


class DiggingToolRecognitionTest(unittest.TestCase):
    def test_recognizes_every_digging_sval_not_just_shovel_and_pick(self):
        # tval TV_DIGGING covers SV_SHOVEL..SV_MATTOCK (1..7); all dig, the sval
        # only sets power. Upgraded diggers must not read as "no digger".
        for sval in range(1, 8):  # shovel, gnomish/dwarven shovel, pick, ..., mattock
            self.assertTrue(
                item("a", TVAL_DIGGING, sval).is_digging_tool,
                f"digging sval {sval} not recognized",
            )
            self.assertTrue(
                store_item("a", TVAL_DIGGING, sval).is_digging_tool,
                f"store digging sval {sval} not recognized",
            )
        # A non-digging item is still rejected.
        self.assertFalse(item("a", TVAL_FOOD, 35).is_digging_tool)


class DescentBlockCooldownTest(unittest.TestCase):
    def test_exhausted_floor_ascent_blocks_immediate_redescent(self):
        deep_grids = {
            Position(y, x): grid(
                y,
                x,
                passable=(y, x) == (10, 10),
                upstairs=(y, x) == (10, 10),
            )
            for y in range(9, 12)
            for x in range(9, 12)
        }
        deep = Snapshot(
            player(10, 10), deep_grids, [], floor_key=(2, 4, 0), width=30, height=30
        )
        pol = HengbotPolicy()
        pol._floor_key = deep.floor_key
        pol._build_grid_index(deep)
        pol._wall_search_counts.update(
            {wall: SEARCH_LIMIT for wall in pol._remembered_wall_t}
        )

        self.assertEqual(pol.choose_key(deep), "<")
        self.assertEqual(pol.last_reason, "stuck:ascend")
        self.assertTrue(pol._descent_is_blocked(deep))

        shallow = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10, downstairs=True),
                Position(10, 11): grid(10, 11),
            },
            [],
            floor_key=(2, 3, 0),
            width=30,
            height=30,
        )

        self.assertNotEqual(pol.choose_key(shallow), ">")
        self.assertTrue(pol._descent_is_blocked(shallow))

    def test_prime_blocks_downstairs_after_a_resume_boundary(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(2, 3, 0),
        )
        pol = HengbotPolicy()

        pol.prime(snap)

        self.assertTrue(pol._descent_is_blocked(snap))
        self.assertEqual(
            pol._descent_block_countdown, RESUME_DESCENT_BLOCK_DECISIONS
        )

    def test_block_expires_after_the_cooldown_without_a_level_up(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        snap = Snapshot(player(10, 10, food=12000), grids, [], floor_key=(2, 3, 0))
        pol = HengbotPolicy()
        pol.choose_key(snap)  # establish state
        pol._defer_descent(snap)
        self.assertTrue(pol._descent_is_blocked(snap))
        pol._descent_block_countdown = 0
        self.assertFalse(pol._descent_is_blocked(snap))
        # And once expired it stays clear.
        self.assertFalse(pol._descent_is_blocked(snap))


class HiddenInfoFallbackTest(unittest.TestCase):
    def test_mana_race_eats_an_unidentified_wand(self):
        # The emitter hides charges until identified; the game lets MANA races
        # eat any wand/staff, so an unknown one must still be tried.
        grids = {Position(10, 10): grid(10, 10)}
        wand = item("d", 65, 0, aware=False)  # unknown wand, charges read as 0
        snap = Snapshot(
            player(10, 10, food=400, food_type=4), grids, [], inventory=[wand]
        )
        self.assertEqual(HengbotPolicy().choose_key(snap), "Ed")

    def test_wields_an_unidentified_light_rather_than_walking_dark(self):
        grids = {Position(10, 10): grid(10, 10)}
        torch = item("c", TVAL_LITE, SV_LITE_TORCH, aware=False)  # fuel hidden
        snap = Snapshot(player(10, 10), grids, [], inventory=[torch], equipment=[])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "wc")
        self.assertEqual(pol.last_reason, "wield-light")

    def test_chargeless_mana_race_needs_device_food_restock(self):
        snap = Snapshot(
            player(10, 10, food=400, food_type=4),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
        )
        self.assertTrue(HengbotPolicy()._needs_food_restock(snap))

    def test_mana_race_jerky_is_zero_food_and_does_not_suppress_return(self):
        jerky = item("a", TVAL_FOOD, 35, count=10, name="jerky")
        snap = Snapshot(
            player(10, 10, food=1500, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=[jerky],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._supply_ledger(snap, 2)["food"].count, 0)
        self.assertIsNone(policy._find_edible(snap))
        self.assertTrue(policy._should_start_town_return(snap))
        self.assertEqual(policy._last_return_trigger, "food-hungry")
        self.assertTrue(
            policy._is_disposable_item(jerky, food_type=FOOD_TYPE_MANA)
        )
        # Food is disposable for this race, but is not an Alchemist sale;
        # the town planner/shop path routes it to the General Store.
        self.assertIsNone(policy._find_low_level_sale(snap))

    def test_mana_race_fundraising_buys_device_charges_not_biscuits(self):
        biscuit = store_item("a", TVAL_FOOD, 35, price=1, name="biscuit")
        wand = store_item("b", TVAL_WAND, 1, price=80, name="wand", pval=15)
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        general = Snapshot(
            player(
                10,
                10,
                gold=500,
                class_id=PLAYER_CLASS_WARRIOR,
                food_type=FOOD_TYPE_MANA,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            store=StoreState(store_type=STORE_GENERAL, items=[biscuit]),
        )
        self.assertIsNone(policy._next_purchase(general))

        magic = replace(
            general, store=StoreState(store_type=STORE_MAGIC, items=[wand])
        )
        self.assertEqual(policy._next_purchase(magic), wand)
        self.assertEqual(policy.choose_key(magic), "pb\r")
        self.assertEqual(policy.last_reason, "shop:buy-device-food")

    def test_mana_race_with_low_device_charges_routes_to_magic_shop(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=500,
                class_id=PLAYER_CLASS_WARRIOR,
                food_type=FOOD_TYPE_MANA,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL),
                item("t", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE),
            ],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        self.assertEqual(policy._next_required_store_type(snap), STORE_MAGIC)

    def test_mana_food_purchase_slots_then_function_then_price(self):
        identify, cheap_fillers = _parse_store({
            "store_type": STORE_MAGIC,
            "items": [
                {"letter": "a", "name": "鑑定の杖 (20回分)", "count": 1,
                 "tval": TVAL_STAFF, "sval": SV_STAFF_IDENTIFY, "price": 500},
                {"letter": "b", "name": "謎の魔法棒 (5回分)", "count": 4,
                 "tval": TVAL_WAND, "sval": 1, "price": 100},
            ],
        }).items
        snap = Snapshot(
            player(
                10, 10, gold=500, food_type=FOOD_TYPE_MANA,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            store=StoreState(STORE_MAGIC, [identify, cheap_fillers]),
        )
        policy = HengbotPolicy()
        self.assertEqual(policy._next_purchase_unreserved(snap), identify)

        functional, filler, expensive, cheap = _parse_store({
            "store_type": STORE_MAGIC,
            "items": [
                {"letter": "c", "name": "鑑定の杖 (15回分)", "count": 1,
                 "tval": TVAL_STAFF, "sval": SV_STAFF_IDENTIFY, "price": 500},
                {"letter": "d", "name": "謎の杖 (15回分)", "count": 1,
                 "tval": TVAL_STAFF, "sval": 1, "price": 100},
                {"letter": "e", "name": "謎の杖 (15回分)", "count": 1,
                 "tval": TVAL_STAFF, "sval": 1, "price": 120},
                {"letter": "f", "name": "謎の杖 (15回分)", "count": 1,
                 "tval": TVAL_STAFF, "sval": 2, "price": 80},
            ],
        }).items
        tied = replace(snap, store=StoreState(STORE_MAGIC, [filler, functional]))
        self.assertEqual(policy._mana_food_purchase(tied), functional)

        price_tie = replace(snap, store=StoreState(STORE_MAGIC, [expensive, cheap]))
        self.assertEqual(policy._mana_food_purchase(price_tie), cheap)

    def test_mana_food_purchase_accepts_chargeless_store_name_at_nominal_one(self):
        device = _parse_store({
            "store_type": STORE_MAGIC,
            "items": [{"letter": "a", "name": "謎の魔法棒", "count": 1,
                       "tval": TVAL_WAND, "sval": 1, "price": 80}],
        }).items[0]
        snap = Snapshot(
            player(10, 10, gold=100, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)}, [],
            store=StoreState(STORE_MAGIC, [device]),
        )

        self.assertEqual(HengbotPolicy()._mana_food_purchase(snap), device)

    def test_mana_food_eating_preserves_function_then_survival_overrides(self):
        policy = HengbotPolicy()
        identify = item(
            "i", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=8, name="Identify"
        )
        filler = item("f", TVAL_STAFF, 1, charges=12, name="filler")

        hungry = Snapshot(
            player(10, 10, food=1500, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)}, [], inventory=[identify, filler],
        )
        self.assertEqual(policy._find_edible(hungry), filler)

        hungry_identify_only = replace(hungry, inventory=[identify])
        self.assertEqual(policy._find_edible(hungry_identify_only), identify)

        floor = replace(identify, charges=IDENTIFY_CHARGE_FLOOR)
        hungry_floor = replace(hungry, inventory=[floor])
        self.assertIsNone(policy._find_edible(hungry_floor))

        weak_floor = replace(
            hungry_floor,
            player=player(10, 10, food=750, food_type=FOOD_TYPE_MANA),
        )
        self.assertEqual(policy._find_edible(weak_floor), floor)
        fainting_floor = replace(
            hungry_floor,
            player=player(10, 10, food=400, food_type=FOOD_TYPE_MANA),
        )
        self.assertEqual(policy._find_edible(fainting_floor), floor)

    def test_identify_floor_and_hunger_return_use_same_edible_charge_count(self):
        policy = HengbotPolicy()
        floor = item(
            "i", TVAL_STAFF, SV_STAFF_IDENTIFY,
            charges=IDENTIFY_CHARGE_FLOOR, name="Identify",
        )
        hungry = Snapshot(
            player(10, 10, food=1500, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0), inventory=[floor],
        )
        self.assertEqual(policy._supply_ledger(hungry, 2)["food"].count, 0)
        self.assertTrue(policy._should_start_town_return(hungry))
        self.assertEqual(policy._last_return_trigger, "food-hungry")

        weak = replace(
            hungry,
            player=player(10, 10, food=750, food_type=FOOD_TYPE_MANA),
        )
        self.assertEqual(
            policy._supply_ledger(weak, 2)["food"].count,
            IDENTIFY_CHARGE_FLOOR,
        )
        self.assertFalse(policy._should_start_town_return(weak))

    def test_town_starvation_routes_to_food_store_before_other_errands(self):
        snap = Snapshot(
            player(10, 10, food=400, gold=15000, food_type=FOOD_TYPE_MANA),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): replace(
                    grid(10, 11), store_number=STORE_MAGIC
                ),
            },
            [],
            town_flag=True,
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "survival:shop-approach")

    def test_normal_race_food_restock_contract_is_unchanged(self):
        ration = item("a", TVAL_FOOD, 35)
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[ration] * 5,
        )
        self.assertFalse(HengbotPolicy()._needs_food_restock(snap))


class PredictiveEscapeTest(unittest.TestCase):
    def _line_snapshot(self, monster, *, hp=30, inventory=None, upstairs=False):
        grids = {
            Position(10, x): grid(
                10,
                x,
                monster=(x == monster.position.x),
                upstairs=(upstairs and x == 10),
            )
            for x in range(10, monster.position.x + 1)
        }
        return Snapshot(
            player(10, 10, hp=hp, max_hp=100),
            grids,
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=inventory or [],
        )

    def test_counts_melee_enemy_that_can_reach_within_three_turns(self):
        monster = hostile(
            1, 10, 12, distance=2, max_melee_damage=20
        )
        snap = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "rt")
        self.assertEqual(pol.last_reason, "emergency:teleport")

    def test_threat_prediction_records_per_monster_damage_breakdown(self):
        monster = replace(
            hostile(
                1,
                10,
                12,
                distance=2,
                max_melee_damage=20,
                max_ranged_damage=11,
            ),
            name="test orc",
            race_id=123,
        )
        snap = self._line_snapshot(monster)

        prediction = HengbotPolicy().threat_prediction(snap, [monster], turns=3)

        self.assertEqual(prediction["total"], 60)
        detail = prediction["monsters"][0]
        self.assertEqual(detail["name"], "test orc")
        self.assertEqual(detail["race_id"], 123)
        self.assertEqual(detail["actions"], 4)
        self.assertEqual(detail["path_distance"], 2)
        self.assertEqual(detail["melee_prediction"], 60)
        self.assertEqual(detail["ranged_prediction"], 44)
        self.assertEqual(detail["contribution"], 60)

    def test_threat_prediction_applies_ac_poison_resistance_and_hit_rate(self):
        monster = replace(
            hostile(
                1,
                10,
                11,
                distance=1,
                max_melee_damage=8,
                max_ranged_damage=98,
            ),
            name="Master yeek",
            race_id=224,
        )
        snap = self._line_snapshot(monster)
        snap = replace(
            snap,
            player=replace(
                snap.player,
                ac=100,
                abilities=frozenset({"resist_pois"}),
            ),
        )
        knowledge = MonraceKnowledge(
            max_hp=48,
            average_hp=30,
            speed=110,
            can_summon=False,
            friendly=False,
            level=12,
            max_melee_damage=8,
            max_ranged_damage=98,
            abilities=frozenset(
                {"BA_POIS", "BLINK", "CONF", "SLOW", "S_MONSTER"}
            ),
            blows=(MonsterBlow("HIT", "HURT", 1, 8),),
            spell_frequency=25,
        )

        prediction = HengbotPolicy(
            monrace_knowledge={224: knowledge}
        ).threat_prediction(snap, [monster], turns=3)

        detail = prediction["monsters"][0]
        self.assertEqual(detail["actions"], 4)
        self.assertEqual(detail["melee_prediction"], 20)
        self.assertEqual(detail["ranged_prediction"], 32)
        self.assertEqual(prediction["total"], 32)
        self.assertLess(prediction["expected_total"], prediction["total"])
        self.assertLess(detail["expected_melee_prediction"], 5)

    def test_cause_spell_participates_in_aggregate_operational_danger(self):
        monster = replace(
            hostile(
                1,
                10,
                12,
                distance=2,
                speed=115,
                max_melee_damage=19,
                max_ranged_damage=64,
            ),
            name="dark elven priest",
            race_id=226,
        )
        snap = self._line_snapshot(monster, hp=100)
        snap = replace(
            snap,
            player=replace(snap.player, ac=30, saving_skill=52),
        )
        knowledge = MonraceKnowledge(
            max_hp=70,
            average_hp=38,
            speed=115,
            can_summon=False,
            friendly=False,
            level=12,
            max_melee_damage=19,
            max_ranged_damage=64,
            abilities=frozenset(
                {"DARKNESS", "BLIND", "CAUSE_2", "MISSILE", "HEAL", "CONF"}
            ),
            blows=(
                MonsterBlow("HIT", "HURT", 1, 9),
                MonsterBlow("HIT", "HURT", 1, 10),
            ),
            spell_frequency=20,
        )
        policy = HengbotPolicy(monrace_knowledge={226: knowledge})

        prediction = policy.threat_prediction(snap, [monster], turns=3)

        detail = prediction["monsters"][0]
        self.assertEqual(prediction["total"], 384)
        self.assertEqual(prediction["operational_total"], 85)
        self.assertEqual(detail["melee_prediction"], 85)
        self.assertLess(detail["operational_ranged_prediction"], 85)
        self.assertGreater(
            detail["operational_ranged_probability_any_damage"], 0.0
        )
        self.assertFalse(detail["operational_ranged_floor_applied"])
        self.assertEqual(detail["cause_predictions"][0]["damage_p95"], 47)
        self.assertEqual(policy._predicted_damage(snap, [monster], 3), 85)

    def test_wall_blocks_melee_reach_and_ranged_line_of_fire(self):
        monster = hostile(
            1, 10, 12, distance=2, max_melee_damage=50, max_ranged_damage=50
        )
        snap = self._line_snapshot(monster)
        snap.grids[Position(10, 11)] = grid(10, 11, passable=False)
        pol = HengbotPolicy()
        self.assertEqual(pol._predicted_damage(snap, [monster], 3), 0)

    def test_ranged_damage_triggers_escape(self):
        monster = hostile(1, 10, 13, distance=3, max_ranged_damage=11)
        snap = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        self.assertEqual(HengbotPolicy().choose_key(snap), "rt")

    def test_upstairs_is_preferred_to_the_last_teleport_scroll(self):
        monster = hostile(1, 10, 11, max_melee_damage=20)
        snap = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=1)],
            upstairs=True,
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "<")
        self.assertEqual(pol.last_reason, "emergency:stairs")

    def test_phase_door_is_the_fallback_when_full_teleport_is_missing(self):
        monster = hostile(1, 10, 11, max_melee_damage=20)
        snap = self._line_snapshot(
            monster, inventory=[item("p", TVAL_SCROLL, 8)]
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "rp")
        self.assertEqual(pol.last_reason, "emergency:phase")

    def test_cures_blindness_then_retains_the_escape_decision(self):
        monster = hostile(1, 10, 11, max_melee_damage=20)
        potion = item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL)
        teleport = item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)
        pol = HengbotPolicy()
        first = self._line_snapshot(monster, inventory=[potion, teleport])
        first = Snapshot(
            player(10, 10, hp=30, max_hp=100, blind=True),
            first.grids,
            first.visible_monsters,
            floor_key=first.floor_key,
            inventory=first.inventory,
        )
        self.assertEqual(pol.choose_key(first), "qc")
        second = self._line_snapshot(monster, inventory=[teleport])
        self.assertEqual(pol.choose_key(second), "rt")

    def test_cure_critical_is_not_spent_as_low_hp_healing(self):
        monster = hostile(1, 10, 11)
        snap = self._line_snapshot(
            monster,
            hp=10,
            inventory=[item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL)],
        )
        pol = HengbotPolicy()
        self.assertNotEqual(pol.choose_key(snap), "qc")

    def test_low_hp_teleport_landing_starts_recall(self):
        monster = hostile(1, 10, 11, max_melee_damage=20)
        pol = HengbotPolicy()
        first = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        self.assertEqual(pol.choose_key(first), "rt")
        safe = Snapshot(
            player(20, 20, hp=30, max_hp=100),
            {Position(20, 20): grid(20, 20)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        self.assertEqual(pol.choose_key(safe), "rr")
        self.assertEqual(pol.last_reason, "return:recall")

    def test_healthy_first_teleport_landing_continues_dive(self):
        monster = hostile(1, 10, 11, max_melee_damage=20)
        pol = HengbotPolicy()
        first = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=2)],
        )
        self.assertEqual(pol.choose_key(first), "rt")
        safe = Snapshot(
            player(20, 20, hp=90, max_hp=100),
            {Position(20, 20): grid(20, 20)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=[
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),
            ],
        )
        self.assertNotEqual(pol.choose_key(safe), "rr")
        self.assertFalse(pol._returning_to_town)
        self.assertIsNone(pol._last_return_trigger)

    def test_second_emergency_escape_starts_return(self):
        monster = hostile(1, 10, 11, max_melee_damage=20)
        pol = HengbotPolicy()
        first = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3)],
        )
        self.assertEqual(pol.choose_key(first), "rt")
        safe = Snapshot(
            player(20, 20, hp=90, max_hp=100),
            {Position(20, 20): grid(20, 20)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=2)],
        )
        pol.choose_key(safe)
        second = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=2)],
        )
        self.assertEqual(pol.choose_key(second), "rt")
        self.assertTrue(pol._returning_to_town)

    def test_material_threat_after_teleport_starts_return(self):
        monster = hostile(1, 10, 11, max_melee_damage=20)
        pol = HengbotPolicy()
        first = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=2)],
        )
        self.assertEqual(pol.choose_key(first), "rt")
        multiplier = hostile(2, 20, 22, max_melee_damage=1, can_multiply=True)
        landing = Snapshot(
            player(20, 20, hp=90, max_hp=100),
            {
                Position(20, 20): grid(20, 20),
                Position(20, 21): grid(20, 21),
                Position(20, 22): grid(20, 22, monster=True),
            },
            [multiplier],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=[
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),
            ],
        )
        self.assertEqual(pol.choose_key(landing), "rr")
        self.assertEqual(pol._last_return_trigger, "emergency-material-threat")


class SummonerMeleeTest(unittest.TestCase):
    def test_teleports_from_adjacent_summoner_in_open_terrain(self):
        # Open terrain would normally trigger the retreat, but walking away from
        # an ALREADY-ADJACENT summoner just donates free hits — kill it.
        grids = {}
        for y in range(9, 12):
            for x in range(9, 12):
                grids[Position(y, x)] = grid(y, x)
        grids[Position(10, 11)] = grid(10, 11, monster=True)
        summoner = hostile(1, 10, 11, hp=40, max_hp=40, can_summon=True)
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            grids,
            [summoner],
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "rt")
        self.assertEqual(pol.last_reason, "emergency:teleport")


class TownAndFundraisingPolicyTest(unittest.TestCase):
    def _strict_supplies(self, *, recall=1, detection=0, teleport=1, critical=1):
        supplies = [
            item("f", TVAL_FOOD, 35, count=5),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=500),
        ]
        if recall:
            supplies.append(
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=recall)
            )
        if detection:
            supplies.append(
                item(
                    "d",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=detection,
                )
            )
        if teleport:
            supplies.append(
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=teleport)
            )
        if critical:
            supplies.append(
                item(
                    "c",
                    TVAL_POTION,
                    SV_POTION_CURE_CRITICAL,
                    count=critical,
                )
            )
        return supplies

    def test_fundraising_checks_home_for_digger_before_general_store(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(detection=5),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"

        self.assertEqual(pol._next_required_store_type(snap), STORE_HOME)
        pol._town_store_attempted[STORE_HOME] = 0
        self.assertEqual(pol._next_required_store_type(snap), STORE_GENERAL)
        pol._town_store_attempted[STORE_GENERAL] = 0
        self.assertIsNone(pol._next_required_store_type(snap))
        self.assertEqual(pol._fundraising_mode, "scavenge")

    def test_shallow_mana_fundraising_departs_when_device_food_is_unaffordable(self):
        snap = Snapshot(
            player(
                38,
                106,
                hp=217,
                max_hp=217,
                food=5000,
                food_type=FOOD_TYPE_MANA,
                gold=337,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(38, 106): grid(38, 106)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[item("e", TVAL_WAND, 15, charges=3)],
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    is_equipment=True,
                    fuel=5000,
                )
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"
        policy._town_store_attempted[STORE_MAGIC] = snap.turn

        self.assertFalse(policy._food_ready(snap))
        self.assertTrue(policy._fundraising_food_ready(snap))
        self.assertTrue(policy._fundraising_departure_ready(snap))
        self.assertNotEqual(policy._next_required_store_type(snap), STORE_MAGIC)
        self.assertIsNone(policy._town_blocked_reason)

    def test_fundraising_checks_home_before_buying_treasure_detection(self):
        snap = Snapshot(
            player(10, 10, gold=73, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(detection=0),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertEqual(policy._next_required_store_type(snap), STORE_HOME)

    def test_deep_recall_can_depart_below_preferred_stock_after_stores_fail(self):
        snap = Snapshot(
            player(10, 10, gold=73, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(recall=5, detection=0),
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
            recall_depth=13,
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
        )
        policy = HengbotPolicy()
        policy._deepest_level = 13
        policy._target_dungeon_id = DUNGEON_YEEK_CAVE
        policy._home_candidate_waiting = False
        policy._food_ready = lambda _snapshot: True
        policy._light_ready = lambda _snapshot: True
        policy._teleport_ready = lambda _snapshot: True
        policy._cure_critical_ready = lambda _snapshot: True
        policy._identify_staff_ready = lambda _snapshot: True
        policy._town_store_attempted.update(
            {STORE_TEMPLE: 0, STORE_ALCHEMIST: 0, STORE_BLACK: 0}
        )

        self.assertFalse(policy._recall_ready(snap))
        self.assertTrue(policy._recall_departure_ready(snap))
        self.assertNotIn(
            policy._next_required_store_type(snap),
            (STORE_TEMPLE, STORE_ALCHEMIST),
        )
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_unobtainable_deep_recall_does_not_block_departure(self):
        snap = Snapshot(
            player(10, 10, gold=73, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(recall=4, detection=0),
            equipment=[self._lantern()],
            recall_depth=13,
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
        )
        policy = HengbotPolicy()
        policy._deepest_level = 13
        policy._target_dungeon_id = DUNGEON_YEEK_CAVE
        policy._town_store_attempted.update({STORE_TEMPLE: 0, STORE_ALCHEMIST: 0})

        self.assertTrue(policy._recall_departure_ready(snap))
        self.assertEqual(policy._next_required_store_type(snap), STORE_HOME)
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_fundraising_withdraws_stored_detection_before_digger(self):
        inventory = self._strict_supplies(detection=0)
        store = StoreState(
            STORE_HOME,
            [
                store_item(
                    "a",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=25,
                ),
                store_item("b", TVAL_DIGGING, 1, name="shovel", is_equipment=True),
            ],
        )
        snap = Snapshot(
            player(10, 10, gold=73, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            store=store,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertEqual(policy._shop(snap), "pa5\r")
        self.assertEqual(policy.last_reason, "home:withdraw-treasure-detection")

        with_scrolls = replace(
            snap,
            inventory=[
                *inventory,
                item("z", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=5),
            ],
        )
        self.assertEqual(policy._shop(with_scrolls), "pb\r")
        self.assertEqual(policy.last_reason, "home:withdraw-digging-tool")

    def test_fundraising_empty_torch_waits_for_general_store_restock(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=1967,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10, entrance=True)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            turn=100,
            inventory=[
                *self._strict_supplies(recall=0, detection=5),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL),
            ],
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_TORCH,
                    fuel=0,
                    is_equipment=True,
                )
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        self.assertFalse(policy._fundraising_departure_ready(snap))
        self.assertEqual(policy._next_required_store_type(snap), STORE_GENERAL)

        policy._town_store_attempted[STORE_GENERAL] = 0
        self.assertIsNone(policy._next_required_store_type(snap))
        self.assertEqual(policy._town_special_key(snap), RESTOCK_WAIT_MACRO)
        self.assertEqual(policy.last_reason, "town:wait-restock")

    def test_fundraising_routes_one_flask_oil_shortage_to_general_store(self):
        snap = Snapshot(
            player(10, 10, gold=3374, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=OIL_TARGET - 1, fuel=500),
                item("d", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=3),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL),
            ],
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs = 3

        self.assertEqual(policy._next_required_store_type(snap), STORE_GENERAL)

    def test_fundraising_withdraws_best_digger_from_home_and_leaves(self):
        inventory = self._strict_supplies(detection=5)
        store = StoreState(
            STORE_HOME,
            [
                store_item("a", TVAL_DIGGING, 1, name="shovel", is_equipment=True),
                store_item("b", TVAL_DIGGING, 4, name="pick", is_equipment=True),
            ],
        )
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            store=store,
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"

        self.assertEqual(pol._shop(snap), "pb\r")
        self.assertEqual(pol.last_reason, "home:withdraw-digging-tool")

        with_pick = Snapshot(
            snap.player,
            snap.grids,
            [],
            floor_key=snap.floor_key,
            town_flag=True,
            inventory=[*inventory, item("z", TVAL_DIGGING, 4, name="pick")],
            store=store,
        )
        self.assertEqual(pol._shop(with_pick), "\x1b")
        self.assertEqual(pol.last_reason, "home:leave-with-digging-tool")

    def test_fundraising_leave_with_mining_supplies_latches_home(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): replace(
                    grid(10, 11), store_number=STORE_HOME
                ),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            turn=123,
            inventory=[
                *self._strict_supplies(detection=5),
                item("z", TVAL_DIGGING, 4, name="pick"),
            ],
            store=StoreState(STORE_HOME, []),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"

        self.assertEqual(pol._shop(snap), "\x1b")
        self.assertEqual(pol.last_reason, "home:leave-with-mining-supplies")
        self.assertEqual(pol._town_store_attempted[STORE_HOME], 123)

        outside = replace(snap, store=None)
        self.assertNotEqual(pol._next_required_store_type(outside), STORE_HOME)
        self.assertNotEqual(pol._shopping_approach_step(outside), Position(10, 11))

    def test_fundraising_does_not_revisit_home_for_unrelated_deposit(self):
        spare = item(
            "z",
            TVAL_RING,
            1,
            name="spare ring",
            known=True,
            is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): replace(
                    grid(10, 11), store_number=STORE_HOME
                ),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(detection=5),
                item("y", TVAL_DIGGING, 4, name="pick"),
                spare,
            ],
            equipment=[self._lantern()],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"

        self.assertIsNotNone(pol._find_home_deposit(snap))
        self.assertIsNone(pol._next_required_store_type(snap))

    def test_fundraising_searches_all_home_pages_for_digger(self):
        inventory = self._strict_supplies(detection=5)
        first_page = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            store=StoreState(
                STORE_HOME,
                [store_item("a", TVAL_RING, 1, name="ring", is_equipment=True)],
            ),
        )
        second_page = Snapshot(
            first_page.player,
            first_page.grids,
            [],
            floor_key=first_page.floor_key,
            town_flag=True,
            inventory=inventory,
            store=StoreState(
                STORE_HOME,
                [store_item("b", TVAL_DIGGING, 4, name="pick", is_equipment=True)],
            ),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"

        self.assertEqual(pol._shop(first_page), " ")
        self.assertEqual(pol.last_reason, "home:seek-digging-tool-page")
        self.assertEqual(pol._shop(second_page), "pb\r")
        self.assertEqual(pol.last_reason, "home:withdraw-digging-tool")

    def test_scavenge_mode_promotes_to_mine_when_home_tool_is_recovered(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(detection=5),
                item("z", TVAL_DIGGING, 4, name="pick"),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "scavenge"

        pol._town_special_key(snap)
        self.assertEqual(pol._fundraising_mode, "mine")

    def test_fundraising_buys_treasure_detection_before_identify(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        pol._identification_need = "normal"
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): GridState(
                    position=Position(10, 11),
                    known=True,
                    passable=True,
                    wall=False,
                    has_monster=False,
                    has_down_stairs=False,
                    has_up_stairs=False,
                    unsafe=False,
                    store_number=STORE_HOME,
                ),
            },
            [],
            inventory=[item("f", TVAL_FOOD, 35, count=5)],
            store=StoreState(
                STORE_ALCHEMIST,
                [
                    store_item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=20),
                    store_item("t", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, price=10),
                ],
            ),
        )
        purchase = pol._next_purchase(snap)
        self.assertIsNotNone(purchase)
        self.assertTrue(purchase.is_treasure_detection_scroll)

    def test_fundraising_routes_minimum_kit_before_dive_supplies(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        snap = Snapshot(
            player(10, 10, gold=FUNDRAISING_KIT_RESERVE, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[item("f", TVAL_FOOD, 35, count=9)],
        )

        self.assertEqual(pol._next_required_store_type(snap), STORE_HOME)
        pol._town_store_attempted[STORE_HOME] = 0
        self.assertEqual(pol._next_required_store_type(snap), STORE_GENERAL)
        pol._town_store_attempted[STORE_GENERAL] = 0
        self.assertEqual(pol._next_required_store_type(snap), STORE_ALCHEMIST)

    def test_tight_gold_skips_dive_supply_that_breaks_fundraising_reserve(self):
        pol = HengbotPolicy()
        pol._deepest_level = 10
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_KIT_RESERVE + 50,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
                item("f", TVAL_FOOD, 35, count=9),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            ],
            equipment=[item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=5000)],
            store=StoreState(
                STORE_ALCHEMIST,
                [store_item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, price=60)],
            ),
        )

        self.assertIsNone(pol._next_purchase(snap))
        self.assertGreaterEqual(snap.player.gold, FUNDRAISING_KIT_RESERVE)

    def test_owned_fundraising_kit_leaves_purchase_order_unchanged(self):
        pol = HengbotPolicy()
        pol._deepest_level = 10
        teleport = store_item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, price=100)
        snap = Snapshot(
            player(10, 10, gold=5000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL),
                item("x", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE),
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
                item("f", TVAL_FOOD, 35, count=9),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            ],
            equipment=[item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=5000)],
            store=StoreState(STORE_ALCHEMIST, [teleport]),
        )

        self.assertEqual(pol._next_purchase(snap), teleport)

    def test_reserve_never_blocks_fundraising_kit_purchase(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        digger = store_item(
            "d", TVAL_DIGGING, SV_DIGGING_SHOVEL, price=FUNDRAISING_KIT_RESERVE
        )
        snap = Snapshot(
            player(10, 10, gold=FUNDRAISING_KIT_RESERVE, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            store=StoreState(STORE_GENERAL, [digger]),
        )

        self.assertEqual(pol._next_purchase(snap), digger)

    def test_fundraising_does_not_buy_digger_with_one_withdrawable_from_home(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        home_digger = store_item(
            "h", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        pol._equipment_catalog.observe_home_page([home_digger])
        shop_digger = store_item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL, price=100)
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(detection=5),
            equipment=[item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=5000)],
            store=StoreState(STORE_GENERAL, [shop_digger]),
        )

        self.assertIsNone(pol._next_purchase(snap))

    def test_identify_errand_still_buys_departure_teleport_scrolls(self):
        # An identify errand must not short-circuit _next_purchase: while at the
        # Alchemist (which also sells teleport scrolls) the bot has to keep
        # stocking departure supplies. Otherwise the store is marked 'attempted'
        # after the identify visit and the bot, still short a teleport scroll,
        # can never become departure-ready and wanders the town instead.
        pol = HengbotPolicy()
        pol._identification_need = "normal"  # errand active
        pol._deepest_level = 10  # planned depth deep enough to require teleports
        snap = Snapshot(
            player(10, 10, gold=5000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, count=5),  # identify source in hand
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
                item("f", TVAL_FOOD, 35, count=9),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            ],
            equipment=[item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)],
            store=StoreState(
                STORE_ALCHEMIST,
                [
                    store_item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=20),
                    store_item("t", TVAL_SCROLL, 9, price=100),  # teleport scroll
                ],
            ),
        )
        purchase = pol._next_purchase(snap)
        self.assertIsNotNone(purchase)
        self.assertTrue(purchase.is_teleport_scroll)

    def test_alchemist_buys_low_value_potions(self):
        for sval in (28, 34):
            with self.subTest(sval=sval):
                snap = Snapshot(
                    player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                    {Position(10, 10): grid(10, 10)},
                    [],
                    inventory=[item("a", TVAL_POTION, sval)],
                    store=StoreState(store_type=STORE_ALCHEMIST, items=[]),
                )
                policy = HengbotPolicy()

                self.assertEqual(policy.choose_key(snap), "da\r")
                self.assertEqual(policy.last_reason, "shop:sell-low-value-consumable")

    def test_alchemist_buys_sleep_and_detect_invisible(self):
        for tval, sval in ((TVAL_POTION, 11), (TVAL_SCROLL, 30)):
            with self.subTest(tval=tval, sval=sval):
                snap = Snapshot(
                    player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                    {Position(10, 10): grid(10, 10)},
                    [],
                    inventory=[item("a", tval, sval)],
                    store=StoreState(store_type=STORE_ALCHEMIST, items=[]),
                )
                policy = HengbotPolicy()

                self.assertEqual(policy.choose_key(snap), "da\r")
                self.assertEqual(policy.last_reason, "shop:sell-low-value-consumable")

    def test_fundraising_seeks_digging_tool_before_identification_store(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        pol._identification_need = "normal"
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): GridState(
                    position=Position(10, 11),
                    known=True,
                    passable=True,
                    wall=False,
                    has_monster=False,
                    has_down_stairs=False,
                    has_up_stairs=False,
                    unsafe=False,
                    store_number=STORE_HOME,
                ),
            },
            [],
            inventory=[
                item("f", TVAL_FOOD, 35, count=5),
                item(
                    "t",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=MINING_RUNS_PER_SET,
                ),
            ],
        )
        self.assertEqual(pol._next_required_store_type(snap), STORE_HOME)
        pol._town_store_attempted[STORE_HOME] = 0
        self.assertEqual(pol._next_required_store_type(snap), STORE_GENERAL)

    def test_depth_two_requirements_are_reported(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[item("f", TVAL_FOOD, 35, count=5)],
            equipment=[item("l", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )
        policy = HengbotPolicy()
        policy._deepest_level = 1

        requirements = policy.procurement_requirements(snap)
        names = {entry["item"] for entry in requirements}

        self.assertIn("Brass lantern", names)
        self.assertIn("Flasks of oil", names)
        self.assertIn("Teleport scrolls", names)
        self.assertIn("Cure Critical Wounds potions", names)

    def test_town_restart_restores_depth_two_plan_for_developed_character(self):
        snap = Snapshot(
            player(10, 10, level=6, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
        )
        policy = HengbotPolicy()

        policy.prime(snap)

        names = {entry["item"] for entry in policy.procurement_requirements(snap)}
        self.assertIn("Brass lantern", names)
        self.assertIn("Teleport scrolls", names)
        self.assertIn("Cure Critical Wounds potions", names)

    def test_depth_two_departure_requires_all_new_supplies(self):
        policy = HengbotPolicy()
        policy._deepest_level = 1
        base = dict(
            player=player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids={Position(10, 10): grid(10, 10)},
            visible_monsters=[],
            floor_key=(0, 0, 0),
            equipment=[self._lantern()],
        )
        missing_healing = Snapshot(
            inventory=self._strict_supplies(recall=1, teleport=3), **base
        )
        complete = Snapshot(
            inventory=self._strict_supplies(recall=1, teleport=4, critical=4),
            **base,
        )

        self.assertFalse(policy._town_departure_ready(missing_healing))
        self.assertTrue(policy._town_departure_ready(complete))

    def test_depth_ten_procurement_requires_ten_cure_critical_potions(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(
                recall=3, teleport=15, critical=9
            ),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._deepest_level = 9

        critical = next(
            requirement
            for requirement in policy.procurement_requirements(snap)
            if requirement["item"] == "Cure Critical Wounds potions"
        )

        self.assertEqual(critical["target"], 10)
        self.assertEqual(critical["missing"], 1)

    def test_depth_ten_returns_at_one_cure_critical_but_not_two(self):
        def dungeon_snapshot(critical):
            return Snapshot(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                {Position(10, 10): grid(10, 10)},
                [],
                floor_key=(4, 10, 0),
                inventory=self._strict_supplies(
                    recall=4, teleport=15, critical=critical
                ),
                equipment=[self._lantern()],
            )

        policy = HengbotPolicy()
        self.assertFalse(policy._should_start_town_return(dungeon_snapshot(2)))
        self.assertTrue(policy._should_start_town_return(dungeon_snapshot(1)))
        self.assertEqual(policy._last_return_trigger, "cure-low")

    def test_ninth_floor_uses_deep_cure_return_reserve_for_next_depth(self):
        def floor_nine(critical):
            return Snapshot(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                {Position(10, 10): grid(10, 10, downstairs=True)},
                [],
                floor_key=(4, 9, 0),
                inventory=self._strict_supplies(
                    recall=4, teleport=15, critical=critical
                ),
                equipment=[self._lantern()],
            )

        policy = HengbotPolicy()
        self.assertTrue(policy._next_depth_supply_shortage(floor_nine(1)))
        self.assertFalse(policy._next_depth_supply_shortage(floor_nine(2)))

    def test_buys_cure_critical_for_depth_two(self):
        snap = Snapshot(
            player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=self._strict_supplies(recall=1, teleport=4),
            equipment=[self._lantern()],
            store=StoreState(
                store_type=STORE_TEMPLE,
                items=[
                    store_item(
                        "a",
                        TVAL_POTION,
                        SV_POTION_CURE_CRITICAL,
                        price=25,
                        count=20,
                    )
                ],
            ),
        )
        policy = HengbotPolicy()
        policy._deepest_level = 1

        self.assertEqual(policy.choose_key(snap), "pa3\r\r")
        self.assertEqual(policy.last_reason, "shop:buy-cure-critical")

    def test_does_not_descend_to_two_without_required_supplies(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()

        self.assertTrue(policy._descent_is_blocked(snap))

        key = policy.choose_key(snap)

        self.assertNotEqual(key, ">")
        self.assertTrue(policy.last_reason.startswith("return:"))

        ready = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=1, teleport=3, critical=3),
            equipment=[self._lantern()],
        )
        self.assertFalse(HengbotPolicy()._descent_is_blocked(ready))

    def test_returns_after_finding_stairs_when_next_depth_kit_is_short(self):
        # Recall is optional on 4F but its return reserve starts at 5F, so the
        # remembered downstairs is the event that makes this shortage actionable.
        inventory = self._strict_supplies(recall=3, teleport=3, critical=3)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(4, 4, 0),
            inventory=inventory,
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "rr")
        self.assertEqual(policy.last_reason, "return:recall")
        self.assertEqual(policy._last_return_trigger, "next-depth-kit")

    def _lantern(self):
        return item(
            "light",
            TVAL_LITE,
            SV_LITE_LANTERN,
            fuel=5000,
            is_equipment=True,
        )

    def test_buys_full_treasure_detection_shortage_from_a_large_stack(self):
        snap = Snapshot(
            player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
            store=StoreState(
                store_type=STORE_ALCHEMIST,
                items=[
                    store_item(
                        "a",
                        TVAL_SCROLL,
                        SV_SCROLL_DETECT_TREASURE,
                        price=25,
                        count=42,
                    )
                ],
            ),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertEqual(policy.choose_key(snap), "pa5\r\r")
        self.assertEqual(policy.last_reason, "shop:buy-treasure-detection")

    def test_procurement_requirements_show_only_current_shortages(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=self._strict_supplies(recall=1, detection=42),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        requirements = policy.procurement_requirements(snap)

        self.assertEqual([entry["item"] for entry in requirements], ["Digging tool"])

    def test_duplicate_unidentified_home_gear_is_not_skipped_by_a_processed_twin(self):
        # Two identical unidentified weapons share a (name, tval, sval) signature.
        # After one is processed, the other must still be found for processing —
        # the signature collision must not strand it in the Home.
        pol = HengbotPolicy()
        first = store_item(
            "a", 23, 5, name="a Long Sword", is_equipment=True, aware=False, known=False
        )
        twin = store_item(
            "b", 23, 5, name="a Long Sword", is_equipment=True, aware=False, known=False
        )
        pol._processed_home_items.add(pol._item_signature(first))
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            store=StoreState(store_type=STORE_HOME, items=[first, twin]),
        )
        self.assertIsNotNone(pol._find_home_candidate(snap))

    def test_processed_identified_home_gear_is_still_skipped(self):
        # An already-identified item that was processed must NOT be re-offered
        # (only unidentified duplicates bypass the processed set).
        pol = HengbotPolicy()
        known_gear = store_item(
            "a", 23, 5, name="a Long Sword (+1,+2)", is_equipment=True, aware=True, known=True
        )
        pol._processed_home_items.add(pol._item_signature(known_gear))
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            store=StoreState(store_type=STORE_HOME, items=[known_gear]),
        )
        self.assertIsNone(pol._find_home_candidate(snap))

    def test_home_ammunition_is_not_withdrawn_as_equipment(self):
        arrows = store_item(
            "a",
            TVAL_ARROW,
            1,
            name="Arrows",
            count=20,
            is_equipment=True,
            aware=True,
            known=False,
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            store=StoreState(store_type=STORE_HOME, items=[arrows]),
        )

        self.assertIsNone(HengbotPolicy()._find_home_candidate(snap))

    def test_withdrawing_home_inferior_weapon_reopens_weapon_sale_route(self):
        # Root cause of the town-departure self-stop: a second Home visit that
        # pulls a fresh spare-weapon batch after the Weapon Smith was already
        # visited this stay left STORE_WEAPON latched, so no sale trip was
        # scheduled and the pack clogged. Withdrawing must re-open the route.
        pol = HengbotPolicy()
        # Same town stay (matching floor_key) so the fresh-visit reset does not
        # clear _town_store_attempted for us — the withdrawal itself must evict it.
        pol._floor_key = (0, 0, 0)
        pol._town_store_attempted[STORE_WEAPON] = 0
        ego = item(
            "main_hand", 23, 1, name="an Ego Blade", is_equipment=True,
            is_ego=True, known=True,
        )
        spare = store_item(
            "a", 23, 1, name="a Dagger", is_equipment=True, aware=True, known=True,
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[],
            equipment=[ego],
            store=StoreState(store_type=STORE_HOME, items=[spare]),
        )

        self.assertIn(STORE_WEAPON, pol._town_store_attempted)
        pol.choose_key(snap)

        self.assertEqual(pol.last_reason, "home:withdraw-inferior-weapon")
        self.assertNotIn(STORE_WEAPON, pol._town_store_attempted)

    def test_home_inferior_weapon_pull_stops_at_the_batch_reserve(self):
        # An unguarded pull filled the pack to zero free every Home visit; a full
        # pack then blocks town departure. The pull must leave the batch reserve.
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        ego = item(
            "main_hand", 23, 1, name="an Ego Blade", is_equipment=True,
            is_ego=True, known=True,
        )
        # Fill the pack with sellable spare weapons down to exactly the reserve.
        # High-grade-equipped inferior spares are excluded from the deposit pass,
        # so they are inert filler here — only the withdraw guard can stop a pull.
        filler = [
            item(f"p{i}", 23, 1, name="a Dagger", is_equipment=True, known=True)
            for i in range(PACK_CAPACITY - HOME_BATCH_RESERVED_SLOTS)
        ]
        spare = store_item(
            "a", 23, 1, name="a Dagger", is_equipment=True, aware=True, known=True,
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=filler,
            equipment=[ego],
            store=StoreState(store_type=STORE_HOME, items=[spare]),
        )

        pol.choose_key(snap)

        self.assertNotEqual(pol.last_reason, "home:withdraw-inferior-weapon")

    def test_home_does_not_withdraw_a_spare_the_smith_refused(self):
        # A spare already refused by the Weapon Smith (unsellable) must not be
        # pulled again: no sale can clear it, so it would clog the pack.
        pol = HengbotPolicy()
        # Same town stay so the fresh-visit reset does not clear _unsellable_items.
        pol._floor_key = (0, 0, 0)
        ego = item(
            "main_hand", 23, 1, name="an Ego Blade", is_equipment=True,
            is_ego=True, known=True,
        )
        refused = store_item(
            "a", 23, 1, name="a Dagger", is_equipment=True, aware=True, known=True,
        )
        pol._unsellable_items.add((refused.name, refused.tval, refused.sval))
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[],
            equipment=[ego],
            store=StoreState(store_type=STORE_HOME, items=[refused]),
        )

        pol.choose_key(snap)

        self.assertNotEqual(pol.last_reason, "home:withdraw-inferior-weapon")

    def test_unsellable_inferior_weapon_can_shelve_back_home(self):
        # Fallback: once the smith has refused a spare, it is no longer held for
        # sale, so it must become depositable again — otherwise a pack of refused
        # spares blocks town departure forever.
        pol = HengbotPolicy()
        ego = item(
            "main_hand", 23, 1, name="an Ego Blade", is_equipment=True,
            is_ego=True, known=True,
        )
        refused = item(
            "b", 23, 1, name="a Dagger", is_equipment=True, known=True,
        )
        pol._unsellable_items.add((refused.name, refused.tval, refused.sval))
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[refused],
            equipment=[ego],
        )

        self.assertEqual(pol._find_home_deposit(snap), refused)

    def test_full_weapon_smith_is_latched_after_repeated_rejection(self):
        # A full store accepts the weapon type yet rejects the sale (no room).
        # After the stuck detector proves the rejection, the store must be latched
        # as sale-refused so the withdraw/route logic stops feeding it more.
        pol = HengbotPolicy()
        spare = item("k", 23, 1, name="a Dagger", is_equipment=True, known=True)
        stock = store_item("a", 23, 2, name="a Long Sword", price=50)
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[spare],
            store=StoreState(store_type=STORE_WEAPON, items=[stock]),
        )
        # Identical-snapshot calls simulate the store rejecting the sale
        # (pack/gold/turn never change). The first emits the sell; the second,
        # seeing the unchanged board, must LEAVE (Escape) rather than re-emit a
        # multi-key sell whose trailing keys would desync into the store command
        # loop after the "no room" message — and latch the store as full.
        first = pol._store_sell_key(
            snap, spare, "shop:sell-inferior-weapon",
            rejected_reason="shop:unsellable-weapon-leave",
        )
        second = pol._store_sell_key(
            snap, spare, "shop:sell-inferior-weapon",
            rejected_reason="shop:unsellable-weapon-leave",
        )
        self.assertNotEqual(first, LEAVE_STORE_KEY)
        self.assertEqual(second, LEAVE_STORE_KEY)
        self.assertIn(STORE_WEAPON, pol._store_sale_refused)

    def test_cross_turn_sell_rejection_is_latched_on_third_attempt(self):
        pol = HengbotPolicy()
        pile = item("j", TVAL_WAND, 1, name="wands", count=3, charges=9)

        def snapshot(turn, carried=pile):
            return Snapshot(
                player(10, 10),
                {Position(10, 10): grid(10, 10)},
                [],
                turn=turn,
                floor_key=(0, 0, 0),
                inventory=[carried],
                store=StoreState(store_type=STORE_MAGIC, items=[]),
            )

        self.assertEqual(pol._store_sell_key(snapshot(1), pile, "shop:sell-device"), "dj3\ry")
        self.assertEqual(pol._store_sell_key(snapshot(2), pile, "shop:sell-device"), "dj3\ry")
        self.assertEqual(
            pol._store_sell_key(
                snapshot(3), pile, "shop:sell-device",
                rejected_reason="shop:unsellable-device-leave",
            ),
            LEAVE_STORE_KEY,
        )
        self.assertEqual(pol.last_reason, "shop:unsellable-device-leave")
        self.assertIn(pol._item_signature(pile), pol._unsellable_items)
        self.assertIn(STORE_MAGIC, pol._store_sale_refused)

    def test_cross_turn_sell_attempts_reset_after_count_decreases(self):
        pol = HengbotPolicy()
        pile = item("j", TVAL_WAND, 1, name="wands", count=3, charges=9)
        reduced = replace(pile, count=2, charges=6)

        def snapshot(turn, carried):
            return Snapshot(
                player(10, 10),
                {Position(10, 10): grid(10, 10)},
                [],
                turn=turn,
                floor_key=(0, 0, 0),
                inventory=[carried],
                store=StoreState(store_type=STORE_MAGIC, items=[]),
            )

        self.assertNotEqual(
            pol._store_sell_key(snapshot(1, pile), pile, "shop:sell-device"),
            LEAVE_STORE_KEY,
        )
        self.assertNotEqual(
            pol._store_sell_key(snapshot(2, pile), pile, "shop:sell-device"),
            LEAVE_STORE_KEY,
        )
        self.assertEqual(
            pol._store_sell_key(snapshot(3, reduced), reduced, "shop:sell-device"),
            "dj2\ry",
        )
        self.assertNotEqual(
            pol._store_sell_key(snapshot(4, reduced), reduced, "shop:sell-device"),
            LEAVE_STORE_KEY,
        )
        self.assertEqual(
            pol._store_sell_key(snapshot(5, reduced), reduced, "shop:sell-device"),
            LEAVE_STORE_KEY,
        )

    def test_no_spare_withdrawal_while_weapon_smith_is_full(self):
        # Once the smith is full this visit, pulling more spares from Home only
        # churns futile trips to a store with no room — do not withdraw.
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._store_sale_refused.add(STORE_WEAPON)
        ego = item(
            "main_hand", 23, 1, name="an Ego Blade", is_equipment=True,
            is_ego=True, known=True,
        )
        spare = store_item(
            "a", 23, 1, name="a Dagger", is_equipment=True, aware=True, known=True,
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[],
            equipment=[ego],
            store=StoreState(store_type=STORE_HOME, items=[spare]),
        )

        pol.choose_key(snap)

        self.assertNotEqual(pol.last_reason, "home:withdraw-inferior-weapon")

    def test_full_smith_lets_inferior_spares_shelve_back(self):
        # Leftover spares stuck in the pack when the smith fills must become
        # depositable, or a pack of unsellable weapons stalls town departure.
        pol = HengbotPolicy()
        pol._store_sale_refused.add(STORE_WEAPON)
        ego = item(
            "main_hand", 23, 1, name="an Ego Blade", is_equipment=True,
            is_ego=True, known=True,
        )
        spare = item(
            "b", 23, 1, name="a Dagger", is_equipment=True, known=True,
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[spare],
            equipment=[ego],
        )

        self.assertEqual(pol._find_home_deposit(snap), spare)

    def test_withdrawn_home_candidate_is_not_immediately_deposited_again(self):
        withdrawn = item(
            "e", 23, 5, name="a Long Sword", is_equipment=True, aware=False
        )
        pol = HengbotPolicy()
        pol._home_pending_item = pol._item_signature(withdrawn)
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[withdrawn],
            store=StoreState(store_type=STORE_HOME, items=[]),
        )

        self.assertEqual(pol.choose_key(snap), "\x1b")
        self.assertEqual(pol.last_reason, "home:leave-with-item")

    def test_failed_home_withdrawal_is_deferred_instead_of_looping(self):
        candidate = store_item(
            "a", 23, 1, name="a Dagger", is_equipment=True, aware=True, known=False
        )
        pol = HengbotPolicy()
        pol._home_pending_item = pol._item_signature(candidate)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[],
            store=StoreState(store_type=STORE_HOME, items=[candidate]),
        )

        self.assertEqual(pol.choose_key(snap), "\x1b")
        self.assertEqual(pol.last_reason, "home:withdraw-failed-deferred")
        self.assertIsNone(pol._home_pending_item)
        self.assertIn(pol._item_signature(candidate), pol._deferred_home_items)

    def test_prime_restores_fundraising_from_multiple_detection_scrolls(self):
        snap = Snapshot(
            player(
                10,
                10,
                class_id=PLAYER_CLASS_WARRIOR,
                gold=FUNDRAISING_START_GOLD - 1,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[
                item(
                    "t",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=4,
                )
            ],
        )
        pol = HengbotPolicy()
        pol.prime(snap)
        self.assertEqual(pol._fundraising_mode, "prepare")

    def test_prime_does_not_restore_fundraising_when_gold_is_sufficient(self):
        snap = Snapshot(
            player(
                10,
                10,
                level=6,
                gold=FUNDRAISING_GOLD_TARGET,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[
                item(
                    "t",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=4,
                )
            ],
        )
        pol = HengbotPolicy()
        pol.prime(snap)
        self.assertIsNone(pol._fundraising_mode)

    def test_fundraising_uses_a_lower_restart_threshold(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_GOLD_TARGET - 1,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
        )
        policy = HengbotPolicy()
        self.assertFalse(policy._start_fundraising(snap))

        poor = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD - 1,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            snap.grids,
            [],
        )
        self.assertTrue(policy._start_fundraising(poor))

    def test_low_gold_itself_starts_fundraising_with_home_first(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD - 1,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._next_required_store_type(snap), STORE_HOME)
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_gold_at_start_threshold_does_not_start_fundraising(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()

        policy._next_required_store_type(snap)

        self.assertIsNone(policy._fundraising_mode)

    def test_repeated_fundraising_start_preserves_store_attempt_latch(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD - 1,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
        )
        policy = HengbotPolicy()
        self.assertTrue(policy._start_fundraising(snap))
        policy._town_store_attempted[STORE_HOME] = 123

        self.assertTrue(policy._start_fundraising(snap))

        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(policy._town_store_attempted[STORE_HOME], 123)

    def test_low_gold_identification_defer_still_starts_fundraising(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD - 1,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._identification_need = "full"
        policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn
        policy._conquest_target = lambda snapshot: 1

        policy._legacy_town_router_terminal(snap)

        self.assertIsNone(policy._identification_need)
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_restock_suppression_blocks_low_gold_trigger(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD - 1,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._town_restock_suppressed = True

        self.assertIsNone(policy._next_required_store_type(snap))
        self.assertIsNone(policy._fundraising_mode)

    def test_prime_restores_a_home_withdrawal_from_the_initial_snapshot(self):
        withdrawn = item(
            "e", 23, 5, name="a Long Sword", is_equipment=True, aware=False
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[withdrawn],
            store=StoreState(store_type=STORE_HOME, items=[]),
        )
        pol = HengbotPolicy()

        pol.prime(snap)

        self.assertEqual(pol.choose_key(snap), "\x1b")
        self.assertEqual(pol.last_reason, "home:leave-with-item")

    def test_prime_does_not_rebuild_known_equipment_as_a_trial_batch(self):
        gloves = item(
            "a", 31, 1, name="known gloves", known=True,
            fully_known=True, is_equipment=True,
        )
        boots = item(
            "b", 30, 1, name="known boots", known=True,
            fully_known=True, is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[gloves, boots],
        )
        pol = HengbotPolicy()

        pol.prime(snap)

        self.assertEqual(pol._home_pending_batch, [])
        self.assertTrue(pol._home_candidate_waiting)

    def test_recall_targets_follow_the_confirmed_depth_table(self):
        policy = HengbotPolicy()
        self.assertEqual(policy._recall_target(4), 1)
        self.assertEqual(policy._recall_target(5), 3)
        self.assertEqual(policy._recall_target(11), 6)
        self.assertEqual(policy._recall_target(16), 9)
        self.assertEqual(policy._recall_target(21), 10)

    def test_strict_town_routine_visits_temple_for_missing_recall(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): GridState(
                position=Position(10, 11),
                known=True,
                passable=True,
                wall=False,
                has_monster=False,
                has_down_stairs=False,
                has_up_stairs=False,
                unsafe=False,
                store_number=STORE_TEMPLE,
            ),
        }
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            grids,
            [],
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        # Keep this recall-routing test focused: an outstanding Home catalog
        # scan now correctly preempts the circuit under the Home-first rule.
        policy._equipment_catalog.home_scan_complete = True
        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "shop:approach")

    def test_buys_recall_scroll_until_target_is_met(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
            store=StoreState(
                store_type=STORE_TEMPLE,
                items=[
                    store_item(
                        "a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20
                    )
                ],
            ),
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "pa\r")
        self.assertEqual(policy.last_reason, "shop:buy-recall")

    def test_cycle_break_preserves_shallow_recall_purchase_errand(self):
        snap = Snapshot(
            player(10, 10, gold=3616, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._last_return_trigger = "recall-low"

        policy._break_town_cycle(snap)

        self.assertFalse(policy._town_restock_suppressed)
        self.assertEqual(policy._next_required_store_type(snap), STORE_TEMPLE)
        self.assertNotIn(STORE_TEMPLE, policy._town_store_attempted)
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)

    def test_unbuyable_recall_does_not_bounce_shallow_dive(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()

        ledger = policy._supply_ledger(snap, snap.dungeon_level)
        self.assertFalse(policy._ledger_return_shortages(ledger, snap.dungeon_level))
        self.assertFalse(policy._should_start_town_return(snap))

    def test_missing_recall_still_triggers_deep_return(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, RECALL_MIN_DEPTH, 0),
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()

        self.assertTrue(policy._should_start_town_return(snap))
        self.assertEqual(policy._last_return_trigger, "recall-low")

    def test_returns_when_recall_stock_falls_below_depth_target(self):
        grids = {Position(10, 10): grid(10, 10, upstairs=True)}
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
            inventory=self._strict_supplies(recall=2),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "<")
        self.assertEqual(policy.last_reason, "return:ascend")

    def test_fifth_floor_and_deeper_return_at_three_recall_scrolls(self):
        def dungeon_snapshot(recall):
            return Snapshot(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                {Position(10, 10): grid(10, 10)},
                [],
                floor_key=(DUNGEON_YEEK_CAVE, 11, 0),
                inventory=self._strict_supplies(
                    recall=recall, teleport=15, critical=10
                ),
                equipment=[self._lantern()],
            )

        policy = HengbotPolicy()
        self.assertFalse(policy._should_start_town_return(dungeon_snapshot(4)))
        self.assertTrue(policy._should_start_town_return(dungeon_snapshot(3)))
        self.assertEqual(policy._last_return_trigger, "recall-low")

    def test_town_prefers_fifth_recall_but_departs_after_shops_are_exhausted(self):
        snap = Snapshot(
            player(10, 10, gold=8599, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=100,
            inventory=self._strict_supplies(recall=3, teleport=4, critical=4),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._deepest_level = 4
        policy.prime(snap)

        self.assertEqual(policy._next_required_store_type(snap), STORE_TEMPLE)
        recall_requirement = next(
            requirement
            for requirement in policy.procurement_requirements(snap)
            if requirement["item"] == "Word of Recall scrolls"
        )
        self.assertEqual(recall_requirement["current"], 3)
        self.assertEqual(recall_requirement["target"], 5)

        policy._town_store_attempted.update(
            {STORE_TEMPLE: 0, STORE_ALCHEMIST: 0, STORE_BLACK: 0}
        )
        self.assertTrue(policy._recall_departure_ready(snap))
        self.assertIsNone(policy._next_required_store_type(snap))
        self.assertIsNone(policy._town_restock_wait_until)

    def test_deeper_stairs_do_not_restore_the_old_depth_based_recall_threshold(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 10, 0),
            inventory=self._strict_supplies(
                recall=4, teleport=15, critical=10
            ),
            equipment=[self._lantern()],
        )

        self.assertFalse(HengbotPolicy()._next_depth_supply_shortage(snap))

    def test_departs_instead_of_waiting_when_recall_is_unavailable(self):
        snap = Snapshot(
            player(10, 10, gold=8000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=100,
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._deepest_level = RECALL_MIN_DEPTH
        policy.prime(snap)
        policy._town_store_attempted.update({STORE_TEMPLE: 0, STORE_ALCHEMIST: 0})

        self.assertNotEqual(policy.choose_key(snap), RESTOCK_WAIT_MACRO)
        self.assertIn(STORE_TEMPLE, policy._town_store_attempted)

    def test_departs_instead_of_waiting_when_teleport_is_unavailable(self):
        snap = Snapshot(
            player(10, 10, gold=8000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=200,
            inventory=self._strict_supplies(recall=7, teleport=0, critical=3),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy.prime(snap)
        policy._deepest_level = 11
        policy._town_store_attempted[STORE_ALCHEMIST] = 0

        self.assertNotEqual(policy.choose_key(snap), RESTOCK_WAIT_MACRO)
        self.assertIn(STORE_ALCHEMIST, policy._town_store_attempted)

    def test_failed_alchemist_approach_allows_teleport_short_departure(self):
        snap = Snapshot(
            player(10, 10, gold=8000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=200,
            inventory=self._strict_supplies(recall=7, teleport=0, critical=3),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy.prime(snap)
        policy._deepest_level = 11
        policy._town_store_attempted[STORE_ALCHEMIST] = 0
        policy._shopping_stuck = True

        self.assertIsNone(policy._shopping_approach_step(snap))
        self.assertFalse(policy._shopping_stuck)
        self.assertIn(STORE_ALCHEMIST, policy._town_store_attempted)
        self.assertNotEqual(policy.choose_key(snap), RESTOCK_WAIT_MACRO)

    def test_waits_for_star_identify_restock_without_dropping_candidate(self):
        target = item(
            "a",
            23,
            1,
            name="ego sword",
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        snap = Snapshot(
            player(10, 10, gold=5000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=300,
            inventory=[*self._strict_supplies(recall=7), target],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy.prime(snap)
        signature = policy._item_signature(target)
        policy._home_pending_item = signature
        policy._identification_candidate = signature
        policy._identification_need = "full"
        policy._town_store_attempted[STORE_ALCHEMIST] = 0

        self.assertEqual(policy.choose_key(snap), RESTOCK_WAIT_MACRO)
        self.assertEqual(policy.last_reason, "town:wait-restock")
        self.assertEqual(policy._identification_need, "full")
        self.assertEqual(policy._home_pending_item, signature)
        self.assertNotIn(signature, policy._deferred_home_items)

        retry = replace(snap, turn=1300)
        self.assertEqual(policy._next_required_store_type(retry), STORE_ALCHEMIST)
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)

    def test_returns_home_after_buying_star_identify_for_stored_candidate(self):
        target = item(
            "a",
            23,
            1,
            name="ego sword",
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snap = Snapshot(
            player(10, 10, gold=3000, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): replace(
                    grid(10, 11, unsafe=False), store_number=STORE_HOME
                ),
            },
            [],
            turn=300,
            inventory=[*self._strict_supplies(recall=7), star_scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy.prime(snap)
        policy._identification_candidate = policy._item_signature(target)
        policy._identification_need = "full"
        policy._home_candidate_waiting = True
        policy._town_store_attempted[STORE_ALCHEMIST] = 0

        self.assertEqual(policy._next_required_store_type(snap), STORE_HOME)
        self.assertNotEqual(policy.choose_key(snap), RESTOCK_WAIT_MACRO)
        self.assertEqual(policy.last_reason, "shop:approach")

    def test_full_identify_errand_precedes_unrelated_home_deposit(self):
        target = item(
            "a",
            23,
            1,
            name="ego sword",
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        spare = item(
            "b", 36, 1, name="spare armour", known=True, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, gold=5000, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): GridState(
                    position=Position(10, 11),
                    known=True,
                    passable=True,
                    wall=False,
                    has_monster=False,
                    has_down_stairs=False,
                    has_up_stairs=False,
                    unsafe=False,
                    store_number=STORE_HOME,
                ),
            },
            [],
            inventory=[target, spare],
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)
        policy._identification_candidate = policy._item_signature(target)
        policy._identification_need = "full"

        self.assertEqual(policy._find_home_deposit(snap), spare)
        self.assertEqual(policy._next_required_store_type(snap), STORE_ALCHEMIST)

    def test_requires_five_free_slots_before_normal_departure(self):
        inventory = self._strict_supplies(recall=1)
        inventory.extend(
            item(chr(ord("a") + i), TVAL_FOOD, 35, name=f"extra-{i}")
            for i in range(16)
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=inventory,
            equipment=[self._lantern()],
        )
        self.assertFalse(HengbotPolicy()._town_departure_ready(snap))

    def test_mining_reads_one_detection_scroll_then_sweeps_visible_gold(self):
        grids = {
            Position(10, 10): grid(10, 10, upstairs=True),
            Position(10, 11): grid(10, 11, passable=False, rubble=True, gold=True),
            Position(20, 20): grid(20, 20, passable=False, gold=True),
            Position(21, 20): grid(21, 20, passable=False, gold=True),
            Position(22, 20): grid(22, 20, passable=False, gold=True),
            Position(23, 20): grid(23, 20, passable=False, gold=True),
        }
        tool = item(
            "main_hand",
            TVAL_DIGGING,
            SV_DIGGING_SHOVEL,
            is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=5),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        self.assertEqual(policy.choose_key(snap), "rd", policy.last_reason)
        self.assertEqual(policy.last_reason, "fundraise:detect-treasure")
        self.assertEqual(policy.choose_key(snap), "T6")
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")

    def test_mining_prefers_orthogonal_gold_over_blocked_diagonal_gold(self):
        grids = {
            Position(10, 10): grid(10, 10),
            # Insert the blocked diagonal first to reproduce the live dict order.
            Position(11, 9): grid(11, 9, passable=False, gold=True),
            Position(11, 10): grid(11, 10, passable=False, gold=True),
            Position(10, 9): grid(10, 9, passable=False),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=5),
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        self.assertEqual(policy.choose_key(snap), "T2")
        self.assertEqual(policy.last_reason, "fundraise:mine-treasure")

    def test_mining_leaves_when_equipped_torch_is_empty(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10, upstairs=True),
                Position(10, 11): grid(10, 11, passable=False, gold=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                *self._strict_supplies(recall=0, detection=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, name="oil", fuel=7500),
            ],
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                item("light", TVAL_LITE, SV_LITE_TORCH, fuel=0, is_equipment=True),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key

        self.assertEqual(policy.choose_key(snap), "<")
        self.assertEqual(policy.last_reason, "fundraise:ascend")

    def test_mining_returns_immediately_when_gold_target_is_reached(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_GOLD_TARGET,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=3),
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        self.assertEqual(policy.choose_key(snap), "<")
        self.assertEqual(policy.last_reason, "fundraise:ascend")

    def test_mining_collects_detected_treasure_after_gold_target_is_reached(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_GOLD_TARGET,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {
                Position(10, 10): grid(10, 10, upstairs=True),
                Position(10, 11): grid(10, 11, gold=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=3),
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key

        self.assertEqual(policy.choose_key(snap), "T6")
        self.assertEqual(policy.last_reason, "fundraise:mine-treasure")

    def _shallow_partial_mining_snapshot(self, detection):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(recall=1, detection=detection),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
            ],
            equipment=[self._lantern()],
        )

    def test_shallow_mining_uses_three_carried_scrolls_as_partial_campaign(self):
        snap = self._shallow_partial_mining_snapshot(3)
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertIsNone(policy._next_required_store_type(snap))
        self.assertEqual(policy._fundraising_mode, "mine")
        self.assertEqual(policy._planned_mining_runs, 3)
        self.assertEqual(policy._mining_detection_scroll_target(snap), 3)
        self.assertTrue(policy._fundraising_supplies_ready(snap))

    def test_shallow_mining_uses_one_carried_scroll_as_partial_campaign(self):
        snap = self._shallow_partial_mining_snapshot(1)
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertIsNone(policy._next_required_store_type(snap))
        self.assertEqual(policy._planned_mining_runs, 1)
        self.assertEqual(policy._mining_detection_scroll_target(snap), 1)

    def test_shallow_mining_with_zero_scrolls_still_shops(self):
        snap = self._shallow_partial_mining_snapshot(0)
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertEqual(policy._next_required_store_type(snap), STORE_HOME)
        self.assertIsNone(policy._planned_mining_runs)

    def test_completed_shallow_partial_campaign_restores_full_set_target(self):
        snap = self._shallow_partial_mining_snapshot(0)
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs = 3
        policy._mining_runs_completed = 3

        self.assertIsNone(policy._town_special_key(snap))
        self.assertIsNone(policy._planned_mining_runs)
        self.assertEqual(
            policy._mining_detection_scroll_target(snap), MINING_RUNS_PER_SET
        )

    def test_deep_fundraising_requires_a_large_batch_of_scrolls_and_recalls(self):
        snap = Snapshot(
            player(
                10,
                10,
                hp=413,
                max_hp=413,
                level=24,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            recall_depth=DEEP_FUNDRAISING_DEPTH,
            entered_dungeon_ids=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE),
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            yeek_cave_conquered=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertTrue(policy._deep_fundraising_eligible(snap))
        self.assertFalse(
            policy._deep_fundraising_eligible(
                replace(
                    snap,
                    player=player(
                        10,
                        10,
                        hp=249,
                        max_hp=249,
                        level=19,
                        class_id=PLAYER_CLASS_WARRIOR,
                    ),
                )
            )
        )
        self.assertEqual(
            policy._mining_detection_scroll_target(snap),
            MINING_RUNS_PER_SET * DEEP_FUNDRAISING_SCROLLS_PER_RUN,
        )
        self.assertEqual(
            policy._recall_required_target(snap),
            3 + 2 * MINING_RUNS_PER_SET,
        )
        self.assertGreaterEqual(
            FUNDRAISING_GOLD_TARGET - FUNDRAISING_START_GOLD, 10000
        )

    def _deep_fundraising_town_snapshot(
        self, *, detection=1, digger=True, gold=10000
    ):
        inventory = self._strict_supplies(recall=0, detection=detection)
        if digger:
            inventory.append(
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True)
            )
        return Snapshot(
            player(
                10,
                10,
                hp=413,
                max_hp=413,
                level=24,
                gold=gold,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
            recall_depth=DEEP_FUNDRAISING_DEPTH,
            entered_dungeon_ids=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE),
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            yeek_cave_conquered=True,
        )

    def test_blocked_deep_campaign_with_shallow_kit_falls_back_and_departs(self):
        snap = self._deep_fundraising_town_snapshot()
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs = MINING_RUNS_PER_SET

        self.assertIsNone(policy._town_special_key(snap))
        self.assertTrue(policy._shallow_fundraising_trip)
        self.assertEqual(policy._fundraising_mode, "mine")
        self.assertEqual(policy._planned_mining_runs, 1)
        self.assertFalse(policy._deep_fundraising_active(snap))
        self.assertTrue(policy._fundraising_departure_ready(snap))
        self.assertFalse(policy._descent_is_blocked(snap))

    def test_promoted_deep_campaign_with_live_shallow_kit_departs_immediately(self):
        # Live trace shape: Home completed the two-run detection batch, which
        # promoted prepare -> mine, but recall remained below the deep reserve.
        # A partly identified item is also still carried; that is a deep-trip
        # gate, not a reason to wait before a safe 1F mining departure.
        candidate = item(
            "e",
            31,
            1,
            name="partly known ego gloves",
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        snap = self._deep_fundraising_town_snapshot(detection=8, gold=10666)
        snap = replace(
            snap,
            inventory=[
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=2, fuel=500),
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5),
                item(
                    "d",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=8,
                ),
                item("p", TVAL_DIGGING, 6, is_equipment=True),
                candidate,
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._planned_mining_runs = 2

        policy._fundraising_mode = "mine"
        self.assertFalse(policy._fundraising_departure_ready(snap))
        policy._fundraising_mode = "prepare"
        self.assertIsNone(policy._town_special_key(snap))
        self.assertEqual(policy.last_reason, "fundraise:fallback-shallow")
        self.assertEqual(policy._fundraising_mode, "mine")
        self.assertTrue(policy._shallow_fundraising_trip)
        self.assertTrue(policy._fundraising_departure_ready(snap))
        self.assertNotEqual(policy._fundraising_mode, "scavenge")

    def test_abandoned_home_deposit_falls_back_to_shallow_mining(self):
        snap = self._deep_fundraising_town_snapshot()
        snap = replace(
            snap,
            inventory=[
                *self._strict_supplies(
                    recall=10,
                    detection=20,
                    teleport=15,
                    critical=10,
                ),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                item("q", TVAL_RING, 8, is_equipment=True, known=True),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs = MINING_RUNS_PER_SET
        policy._home_deposit_abandoned = True

        self.assertTrue(policy._fundraising_supplies_ready(snap))
        self.assertFalse(policy._fundraising_departure_ready(snap))
        self.assertIsNone(policy._town_special_key(snap))
        self.assertTrue(policy._shallow_fundraising_trip)
        self.assertTrue(policy._fundraising_departure_ready(snap))

    def test_blocked_deep_campaign_without_shallow_kit_still_scavenges(self):
        snap = self._deep_fundraising_town_snapshot(
            detection=0, digger=False, gold=0
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._town_cycle_pending = True

        self.assertEqual(policy._town_special_key(snap), WAIT_KEY)
        self.assertEqual(policy._fundraising_mode, "scavenge")
        self.assertFalse(policy._shallow_fundraising_trip)

    def test_shallow_fallback_cannot_promote_deep_while_restock_suppressed(self):
        snap = self._deep_fundraising_town_snapshot()
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._town_restock_suppressed = True

        self.assertIsNone(policy._town_special_key(snap))
        self.assertFalse(policy._deep_fundraising_active(snap))
        self.assertIsNone(policy._town_special_key(snap))
        self.assertTrue(policy._shallow_fundraising_trip)

    def test_deep_fundraising_recalls_to_yeek_cave_with_safe_supplies(self):
        inventory = self._strict_supplies(
            recall=13,
            detection=MINING_RUNS_PER_SET * DEEP_FUNDRAISING_SCROLLS_PER_RUN,
            teleport=15,
            critical=10,
        )
        inventory.append(
            item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True)
        )
        snap = Snapshot(
            player(
                10,
                10,
                hp=413,
                max_hp=413,
                level=24,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
            recall_depth=DEEP_FUNDRAISING_DEPTH,
            recall_dungeon_id=DUNGEON_ANGBAND,
            entered_dungeon_ids=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE),
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._char_dump_done_this_visit = True

        self.assertEqual(policy._town_special_key(snap), "rrb")
        self.assertEqual(policy.last_reason, "town:recall-to-yeek-cave-mining")

    def test_deep_fundraising_uses_the_affordable_partial_batch(self):
        snap = Snapshot(
            player(
                10,
                10,
                hp=413,
                max_hp=413,
                level=24,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(
                    recall=10, detection=20, teleport=15, critical=10
                ),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
            ],
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
            recall_depth=DEEP_FUNDRAISING_DEPTH,
            entered_dungeon_ids=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE),
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            yeek_cave_conquered=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertTrue(policy._activate_partial_deep_mining_plan(snap))
        self.assertEqual(policy._planned_mining_runs, 3)
        self.assertEqual(policy._mining_detection_scroll_target(snap), 12)
        self.assertEqual(policy._recall_required_target(snap), 9)
        self.assertTrue(policy._fundraising_supplies_ready(snap))
        self.assertNotIn(
            "mining-detection",
            [reason for _, reason in policy._enumerate_town_needs(snap)],
        )

        policy._planned_mining_runs = None
        policy._fundraising_mode = "mine"
        policy._char_dump_done_this_visit = True
        self.assertEqual(policy._town_special_key(snap), "rrb")
        self.assertEqual(policy._planned_mining_runs, 3)

    def test_partial_deep_batch_can_depart_below_preferred_teleport_stock(self):
        snap = Snapshot(
            player(
                10,
                10,
                hp=413,
                max_hp=413,
                level=24,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(
                    recall=10, detection=20, teleport=14, critical=10
                ),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
            ],
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
            recall_depth=DEEP_FUNDRAISING_DEPTH,
            entered_dungeon_ids=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE),
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            yeek_cave_conquered=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs = 3
        policy._deepest_level = DEEP_FUNDRAISING_DEPTH
        policy._char_dump_done_this_visit = True

        self.assertFalse(policy._teleport_ready(snap))
        self.assertTrue(policy._deep_fundraising_teleport_ready(snap))
        self.assertEqual(policy._town_special_key(snap), "rrb")
        self.assertEqual(policy.last_reason, "town:recall-to-yeek-cave-mining")

    def test_deep_fundraising_deposits_full_identification_candidate_first(self):
        candidate = item(
            "e",
            31,
            1,
            name="partly known ego gloves",
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        inventory = [
            *self._strict_supplies(
                recall=10, detection=20, teleport=15, critical=10
            ),
            candidate,
            item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
        ]
        snap = Snapshot(
            player(
                10,
                10,
                hp=413,
                max_hp=413,
                level=24,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): replace(
                    grid(10, 11), store_number=STORE_HOME
                ),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
            recall_depth=DEEP_FUNDRAISING_DEPTH,
            recall_dungeon_id=DUNGEON_ANGBAND,
            entered_dungeon_ids=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE),
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs = 3
        policy._char_dump_done_this_visit = True

        self.assertFalse(policy._fundraising_departure_ready(snap))
        self.assertEqual(policy._next_required_store_type(snap), STORE_HOME)
        policy._identification_need = "full"
        self.assertEqual(policy._next_required_store_type(snap), STORE_HOME)
        self.assertEqual(policy._town_special_key(snap), WAIT_KEY)
        self.assertEqual(policy.last_reason, "fundraise:departure-blocked")

        home = replace(
            snap,
            store=StoreState(store_type=STORE_HOME, items=[]),
        )
        self.assertEqual(policy.choose_key(home), "de\r")
        self.assertEqual(policy.last_reason, "home:deposit")

    def test_blocked_fundraising_steps_off_store_instead_of_reentering(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_ALCHEMIST
                ),
                Position(10, 11): grid(10, 11),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._fundraising_departure_ready = lambda snapshot: False
        policy._floor_t = {(10, 10), (10, 11)}

        self.assertEqual(policy._town_special_key(snap), "6")
        self.assertEqual(
            policy.last_reason, "fundraise:departure-blocked-step-off"
        )

    def test_known_distant_store_uses_native_travel_without_bfs_memory(self):
        home = Position(45, 123)
        snap = Snapshot(
            player(36, 90, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(36, 90): grid(36, 90),
                home: replace(grid(home.y, home.x), store_number=STORE_HOME),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda snapshot: STORE_HOME
        policy._build_grid_index(snap)

        step = policy._shopping_approach_step(snap)
        self.assertEqual(step, home)
        self.assertEqual(
            policy._shopping_approach_key(snap, step, "shop:travel"),
            "\x1b`n(.",
        )

    def test_recall_wait_steps_off_home_entrance(self):
        snap = Snapshot(
            player(
                10,
                10,
                hp=413,
                max_hp=413,
                level=24,
                class_id=PLAYER_CLASS_WARRIOR,
                word_recall=10,
            ),
            {
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_HOME
                ),
                Position(10, 11): grid(10, 11),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(
                    recall=10, detection=20, teleport=15, critical=10
                ),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
            ],
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
            recall_depth=DEEP_FUNDRAISING_DEPTH,
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
            entered_dungeon_ids=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE),
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            yeek_cave_conquered=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs = 3
        policy._char_dump_done_this_visit = True
        policy._floor_t = {(10, 10), (10, 11)}

        self.assertEqual(policy._town_special_key(snap), "6")
        self.assertEqual(policy.last_reason, "town:wait-recall-step-off")

    def test_deep_mining_does_not_chase_a_weak_evasive_hostile(self):
        monster = hostile(
            3,
            14,
            27,
            hp=18,
            max_hp=18,
            distance=1,
            max_melee_damage=2,
        )
        snap = Snapshot(
            player(
                13,
                26,
                hp=427,
                max_hp=427,
                level=25,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {
                Position(13, 26): grid(13, 26),
                Position(14, 26): grid(14, 26),
                Position(14, 27): grid(14, 27, monster=True),
            },
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, DEEP_FUNDRAISING_DEPTH, 0),
            inventory=self._strict_supplies(recall=9, detection=10),
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._build_grid_index(snap)

        self.assertIsNone(
            policy._fundraising_combat_equipment_key(snap, [monster])
        )

    def test_deep_mining_attacks_an_adjacent_material_hostile_diagonally(self):
        monster = hostile(
            3,
            14,
            14,
            hp=40,
            max_hp=40,
            distance=1,
            max_melee_damage=60,
            can_summon=True,
        )
        snap = Snapshot(
            player(
                15,
                15,
                hp=321,
                max_hp=427,
                level=25,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {
                Position(15, 15): grid(15, 15),
                Position(14, 14): grid(14, 14, monster=True),
            },
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, DEEP_FUNDRAISING_DEPTH, 0),
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._build_grid_index(snap)

        self.assertEqual(
            policy._fundraising_combat_equipment_key(snap, [monster]), "7"
        )
        self.assertEqual(policy.last_reason, "fundraise:clear-hostile")

    def test_deep_mining_does_not_chase_a_damaging_evasive_normal_hostile(self):
        monster = hostile(
            3,
            37,
            27,
            hp=40,
            max_hp=40,
            distance=1,
            max_melee_damage=60,
        )
        snap = Snapshot(
            player(
                38,
                26,
                hp=321,
                max_hp=427,
                level=25,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {
                Position(38, 26): grid(38, 26),
                Position(37, 27): grid(37, 27, monster=True),
            },
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, DEEP_FUNDRAISING_DEPTH, 0),
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._build_grid_index(snap)

        self.assertIsNone(
            policy._fundraising_combat_equipment_key(snap, [monster])
        )

    def test_deep_mining_keeps_pursuing_last_seen_multiplier_before_digging(self):
        monster = hostile(
            3,
            38,
            31,
            hp=20,
            max_hp=20,
            distance=5,
            can_multiply=True,
        )
        grids = {
            Position(38, x): grid(38, x, monster=x == 31)
            for x in range(26, 32)
        }
        seen = Snapshot(
            player(38, 26, hp=321, max_hp=427, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, DEEP_FUNDRAISING_DEPTH, 0),
            equipment=[item("main_hand", 23, 1, is_equipment=True), self._lantern()],
        )
        hidden = replace(
            seen,
            player=replace(seen.player, position=Position(38, 27)),
            visible_monsters=[],
            grids={Position(38, x): grid(38, x) for x in range(27, 32)},
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._build_grid_index(seen)

        self.assertEqual(
            policy._fundraising_combat_equipment_key(seen, [monster]), "6"
        )
        policy._build_grid_index(hidden)
        self.assertEqual(
            policy._fundraising_combat_equipment_key(hidden, []), "6"
        )
        self.assertEqual(
            policy.last_reason, "fundraise:pursue-last-material-hostile"
        )

    def test_deep_mining_redetects_after_leaving_previous_detection_radius(self):
        floor_key = (DUNGEON_YEEK_CAVE, DEEP_FUNDRAISING_DEPTH, 0)
        snap = Snapshot(
            player(
                10,
                10 + DEEP_FUNDRAISING_DETECTION_RADIUS + 1,
                hp=413,
                max_hp=413,
                level=24,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {
                Position(10, 10 + DEEP_FUNDRAISING_DETECTION_RADIUS + 1): grid(
                    10, 10 + DEEP_FUNDRAISING_DETECTION_RADIUS + 1
                )
            },
            [],
            floor_key=floor_key,
            inventory=self._strict_supplies(
                recall=5, detection=2, teleport=15, critical=10
            ),
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                self._lantern(),
            ],
            recall_depth=DEEP_FUNDRAISING_DEPTH,
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            yeek_cave_conquered=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = floor_key
        policy._mining_scroll_used_floor = floor_key
        policy._mining_detection_centers.append(Position(10, 10))

        self.assertEqual(policy.choose_key(snap), "rd")
        self.assertEqual(policy.last_reason, "fundraise:redetect-treasure")

    def test_deep_mining_explores_unknown_area_before_recalling(self):
        floor_key = (DUNGEON_YEEK_CAVE, DEEP_FUNDRAISING_DEPTH, 0)
        snap = Snapshot(
            player(
                10,
                10,
                hp=413,
                max_hp=413,
                level=24,
                gold=FUNDRAISING_GOLD_TARGET,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, known=False),
            },
            [],
            floor_key=floor_key,
            inventory=self._strict_supplies(
                recall=5, detection=1, teleport=15, critical=10
            ),
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                self._lantern(),
            ],
            recall_depth=DEEP_FUNDRAISING_DEPTH,
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            yeek_cave_conquered=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = floor_key
        policy._mining_scroll_used_floor = floor_key
        policy._mining_detection_centers.append(Position(10, 10))

        # The sweep phase owns pre-recall exploration now: the unknown area sits
        # inside the detected radius, so it is mapped before the floor is left.
        self.assertEqual(policy.choose_key(snap), "6", policy.last_reason)
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")

    def test_deep_mining_rearms_before_engaging_a_visible_hostile(self):
        floor_key = (DUNGEON_YEEK_CAVE, DEEP_FUNDRAISING_DEPTH, 0)
        monster = hostile(1, 10, 12, distance=2)
        snap = Snapshot(
            player(
                10,
                10,
                hp=413,
                max_hp=413,
                level=24,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, monster=True),
            },
            [monster],
            floor_key=floor_key,
            inventory=[item("p", 23, 1, is_equipment=True)],
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        # Digger in the main hand, sub hand free: `w` raises the "Dual wielding?"
        # prompt and the trailing n replaces the main hand (wield_slot suggests
        # the free sub hand for a weapon whenever only the main hand is occupied).
        self.assertEqual(
            policy._fundraising_combat_equipment_key(snap, [monster]), "wpn"
        )
        self.assertEqual(policy.last_reason, "fundraise:wield-combat-weapon")

    def test_fundraising_combat_restore_skips_pack_jewelry(self):
        monster = hostile(1, 10, 12, distance=2)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 12): grid(10, 12, monster=True),
            },
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, DEEP_FUNDRAISING_DEPTH, 0),
            inventory=[
                item("n", 45, 1, is_equipment=True, name="Rusty Ring"),
                item("o", 23, 1, is_equipment=True, name="Saber"),
            ],
            equipment=[
                item(
                    "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
                item("sub_hand", 23, 5, is_equipment=True, name="Main Gauche"),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        self.assertEqual(
            policy._fundraising_combat_equipment_key(snap, [monster]), "woa"
        )
        self.assertEqual(policy.last_reason, "fundraise:wield-combat-weapon")

    def test_deep_fundraising_does_not_rewield_digger_with_hostile_visible(self):
        monster = hostile(1, 10, 12, distance=2)
        snap = Snapshot(
            player(
                10, 10, level=24, hp=413, max_hp=413,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 12): grid(10, 12, monster=True),
            },
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, DEEP_FUNDRAISING_DEPTH, 0),
            inventory=self._strict_supplies(recall=5, detection=1)
            + [item("u", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True)],
            equipment=[
                item("main_hand", 23, 11, is_equipment=True, name="Saber"),
                self._lantern(),
            ],
            recall_depth=DEEP_FUNDRAISING_DEPTH,
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            yeek_cave_conquered=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        self.assertIsNone(policy._fundraising_key(snap, [monster]))
        self.assertNotEqual(policy.last_reason, "fundraise:wield-digging-tool")

    def test_deep_mining_recalls_only_after_the_floor_has_no_frontier(self):
        snap = Snapshot(
            player(
                10,
                10,
                hp=413,
                max_hp=413,
                level=24,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, DEEP_FUNDRAISING_DEPTH, 0),
            inventory=self._strict_supplies(recall=5),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._finish_mining_floor(snap), "rr")
        self.assertEqual(policy.last_reason, "fundraise:recall")

    def test_new_treasure_found_during_deep_exploration_resets_mining_stall(self):
        floor_key = (DUNGEON_YEEK_CAVE, DEEP_FUNDRAISING_DEPTH, 0)
        snap = Snapshot(
            player(
                10,
                10,
                hp=413,
                max_hp=413,
                level=24,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 12): grid(10, 12, passable=False, gold=True),
            },
            [],
            floor_key=floor_key,
        )
        policy = HengbotPolicy()
        policy._floor_key = floor_key
        policy._mining_stall_turns = MINING_STALL_LIMIT

        policy._observe(snap)

        self.assertEqual(policy._mining_stall_turns, 0)
        self.assertIn(Position(10, 12), policy._known_treasure)

    def test_mining_eats_when_hungry_before_continuing(self):
        tool = item(
            "main_hand",
            TVAL_DIGGING,
            SV_DIGGING_SHOVEL,
            is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, food=1500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=5),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        self.assertEqual(policy.choose_key(snap), "Ef")
        # The R1 survival gate now owns hunger-eating and runs before the
        # fundraising steps; the action (eat, same slot, same turn) is
        # unchanged, only the reason label moved.
        self.assertEqual(policy.last_reason, "survival:eat")

    def test_mining_collects_visible_item_after_detected_treasure_is_gone(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, objects=1),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:seek-loot")

    def test_mining_collects_nearest_unsafe_drop_before_adjacent_vein(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, passable=False, gold=True),
                Position(11, 10): grid(11, 10),
                Position(12, 10): grid(12, 10, objects=1, unsafe=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key

        self.assertEqual(policy.choose_key(snap), "2")
        self.assertEqual(policy.last_reason, "fundraise:seek-loot")

    def test_mining_keeps_tracking_unsafe_loot_when_it_leaves_view(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        inventory = self._strict_supplies(recall=0, detection=1)
        equipment = [tool, self._lantern()]
        floor_key = (DUNGEON_YEEK_CAVE, 1, 0)
        first = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(11, 10): grid(11, 10),
                Position(12, 10): grid(12, 10, objects=1, unsafe=True),
            },
            [],
            floor_key=floor_key,
            inventory=inventory,
            equipment=equipment,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = floor_key

        self.assertEqual(policy.choose_key(first), "2")
        self.assertEqual(policy._loot_target, Position(12, 10))

        hidden = Snapshot(
            player(11, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10, upstairs=True),
                Position(11, 10): grid(11, 10),
                # A FOUND floor object remains in the JSON map while outside
                # direct view; CAVE_UNSAFE only records trap-detection coverage.
                Position(12, 10): grid(12, 10, objects=1, unsafe=True),
            },
            [],
            floor_key=floor_key,
            inventory=inventory,
            equipment=equipment,
        )

        self.assertEqual(policy.choose_key(hidden), "2")
        self.assertEqual(policy.last_reason, "fundraise:seek-loot")
        self.assertEqual(policy._loot_target, Position(12, 10))

    def test_scavenging_collects_visible_item_before_exploring(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, objects=1),
                Position(11, 10): grid(11, 10),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:seek-loot")

    def test_scavenging_returns_at_gold_target_despite_stale_treasure_memory(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_GOLD_TARGET,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"
        policy._known_treasure = {Position(12, 12)}

        self.assertEqual(policy.choose_key(snap), "<")
        self.assertEqual(policy.last_reason, "fundraise:ascend")

    def test_town_restores_combat_weapon_after_mining(self):
        tool = item(
            "main_hand",
            TVAL_DIGGING,
            SV_DIGGING_SHOVEL,
            name="shovel",
            is_equipment=True,
        )
        sword = item("s", 23, 1, name="sword", is_equipment=True)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[sword, *self._strict_supplies(recall=1, detection=4)],
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._normal_weapon_name = "sword"
        # n answers the "Dual wielding?" prompt (sub hand free) with "replace
        # the main hand", swapping the digger out instead of dual-wielding.
        self.assertEqual(policy.choose_key(snap), "wsn")
        self.assertEqual(policy.last_reason, "town:restore-combat-weapon")

    def test_fundraising_descends_from_matching_static_entrance(self):
        entrance = Position(10, 10)
        town_map = TownMap(
            name="test",
            width=20,
            height=20,
            walkable=frozenset({entrance}),
            entrance=entrance,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {entrance: grid(
                10, 10, entrance=True,
                entrance_dungeon_id=DUNGEON_YEEK_CAVE,
            )},
            [],
            floor_key=(0, 0, 0),
            width=20,
            height=20,
            town_flag=True,
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy(town_map=town_map)
        policy._fundraising_mode = "scavenge"

        self.assertEqual(policy.choose_key(snap), ">\ry")
        self.assertEqual(policy.last_reason, "descend")

    def test_town_restores_a_weapon_even_when_the_name_is_unknown(self):
        # A fresh bot process that inherited an already-wielded pickaxe has no recorded
        # combat-weapon name, but must STILL swap the pickaxe out for a real weapon before
        # diving/recalling — otherwise it recalls on a feeble digger. Falls back to any
        # melee weapon in the pack.
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="shovel", is_equipment=True
        )
        sword = item("s", 23, 1, name="long sword", is_equipment=True)  # TV_SWORD
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[sword, *self._strict_supplies(recall=1, detection=4)],
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._normal_weapon_name = None  # unknown after a restart
        self.assertEqual(policy._town_restore_weapon_key(snap), "wsn")
        self.assertEqual(policy.last_reason, "town:restore-combat-weapon")

    def test_town_restore_weapon_is_a_noop_without_any_combat_weapon(self):
        # Digger equipped but no real weapon anywhere to restore: don't hang the town
        # routine WAITing for one that will never appear — return None and carry on.
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="shovel", is_equipment=True
        )
        armour = item("b", 36, 2, name="soft leather armour", is_equipment=True)  # not a weapon
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[armour, *self._strict_supplies(recall=1, detection=4)],
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._normal_weapon_name = None
        self.assertIsNone(policy._town_restore_weapon_key(snap))

    def _home_tile(self, y, x):
        return GridState(
            position=Position(y, x), known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_HOME,
        )

    def test_pre_recall_check_is_not_ready_on_a_pickaxe(self):
        # THE essential fix: a mining pickaxe in the main hand is not a combat weapon, so
        # the pre-recall check must report "not ready" (blocking the dive) until re-armed.
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="shovel", is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=list(self._strict_supplies(recall=1)),
            equipment=[tool, self._lantern()],
        )
        self.assertFalse(HengbotPolicy()._combat_weapon_ready(snap))

    def test_pre_recall_check_is_ready_with_a_real_weapon(self):
        sword = item("main_hand", 23, 1, name="long sword", is_equipment=True)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[],
            equipment=[sword, self._lantern()],
        )
        self.assertTrue(HengbotPolicy()._combat_weapon_ready(snap))

    def test_pre_recall_check_rejects_no_teleport_weapon(self):
        weapon = item(
            "main_hand",
            23,
            1,
            name="artifact scimitar",
            is_equipment=True,
            is_artifact=True,
            fully_known=True,
            known_flags=frozenset({TR_NO_TELE}),
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            equipment=[weapon, self._lantern()],
        )

        self.assertFalse(HengbotPolicy()._combat_weapon_ready(snap))

    def test_cancels_active_recall_before_disposing_no_teleport_weapon(self):
        weapon = item(
            "main_hand",
            23,
            1,
            is_equipment=True,
            is_artifact=True,
            fully_known=True,
            known_flags=frozenset({TR_NO_TELE}),
        )
        snap = Snapshot(
            player(10, 10, word_recall=10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=2),
            equipment=[weapon, self._lantern()],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "rr")
        self.assertEqual(policy.last_reason, "town:cancel-unsafe-recall")

    def test_town_replaces_no_teleport_weapon_from_pack(self):
        blocked = item(
            "main_hand",
            23,
            1,
            is_equipment=True,
            is_artifact=True,
            fully_known=True,
            known_flags=frozenset({TR_NO_TELE}),
        )
        safe = item("s", 23, 2, name="safe scimitar", is_equipment=True)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[safe],
            equipment=[blocked, self._lantern()],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._town_restore_weapon_key(snap), "ta")
        self.assertEqual(policy.last_reason, "town:remove-no-teleport-weapon")

        removed = replace(
            snap,
            inventory=[safe, replace(blocked, slot="b")],
            equipment=[self._lantern()],
        )
        self.assertEqual(policy._town_restore_weapon_key(removed), "ws")
        self.assertEqual(policy.last_reason, "town:replace-no-teleport-weapon")

    def test_town_resumes_no_teleport_rearm_after_bot_restart(self):
        blocked = item(
            "b",
            23,
            1,
            is_equipment=True,
            is_artifact=True,
            fully_known=True,
            known_flags=frozenset({TR_NO_TELE}),
        )
        safe = item("s", 23, 2, name="safe scimitar", is_equipment=True)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[blocked, safe],
            equipment=[self._lantern()],
        )
        restarted_policy = HengbotPolicy()

        self.assertEqual(restarted_policy._town_restore_weapon_key(snap), "ws")
        self.assertEqual(
            restarted_policy.last_reason, "town:replace-no-teleport-weapon"
        )

    def test_home_rearm_skips_no_teleport_weapon_and_withdraws_safe_one(self):
        blocked = item(
            "main_hand",
            23,
            1,
            is_equipment=True,
            is_artifact=True,
            fully_known=True,
            known_flags=frozenset({TR_NO_TELE}),
        )
        home = StoreState(
            STORE_HOME,
            [
                store_item(
                    "a", 23, 1, is_artifact=True, known_flags=frozenset({TR_NO_TELE})
                ),
                store_item("b", 23, 2, name="safe scimitar"),
            ],
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): self._home_tile(10, 10)},
            [],
            equipment=[blocked, self._lantern()],
            store=home,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._shop(snap), "pb\r")
        self.assertEqual(policy.last_reason, "home:withdraw-combat-weapon")

    def test_pre_recall_check_backstop_dives_when_no_weapon_can_be_found(self):
        # If we own no combat weapon at all, the check must eventually give up and dive on
        # the pickaxe rather than hang the bot in town forever.
        from hengbot.policy import WEAPON_BLOCK_LIMIT

        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="shovel", is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[],
            equipment=[tool, self._lantern()],
        )
        pol = HengbotPolicy()
        pol._weapon_block_streak = WEAPON_BLOCK_LIMIT
        self.assertTrue(pol._combat_weapon_ready(snap))

    def test_routes_to_home_to_re_arm_even_when_home_is_not_visible(self):
        # Pickaxe wielded, no weapon in the pack: route to the Home to withdraw the real
        # weapon before diving — even with NO Home tile in view (an unlit Home is absent
        # from the grids). _shopping_approach_step walks there via the static town map;
        # gating this on a visible Home left the character wandering the town unable to
        # re-arm (the stuck:wander the user hit).
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="shovel", is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},  # no Home tile visible
            [],
            inventory=list(self._strict_supplies(recall=1, detection=4)),
            equipment=[tool, self._lantern()],
        )
        pol = HengbotPolicy()
        self.assertFalse(pol._home_available(snap))  # Home not in view
        self.assertEqual(pol._next_required_store_type(snap), STORE_HOME)

    def test_home_rearm_withdraws_best_weapon_before_jewellery_processing(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            name="pick", is_equipment=True,
        )
        ring = store_item(
            "a", 45, 1, name="ego ring", is_equipment=True, is_ego=True,
        )
        sword = store_item(
            "b", 23, 1, name="plain sword", is_equipment=True,
            damage_dice_num=1, damage_dice_sides=6, to_d=3,
        )
        hammer = store_item(
            "c", 21, 12, name="Pattern hammer", is_equipment=True,
            is_ego=True, damage_dice_num=2, damage_dice_sides=5,
            to_h=16, to_d=9, pval=2,
        )
        home = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=list(self._strict_supplies(recall=1)),
            equipment=[tool, self._lantern()],
            store=StoreState(store_type=STORE_HOME, items=[ring, sword, hammer]),
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(home), "pc\r")
        self.assertEqual(policy.last_reason, "home:withdraw-combat-weapon")
        self.assertEqual(policy._home_pending_item, policy._item_signature(hammer))

    def test_home_rearm_pages_past_jewellery_to_find_weapon(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            name="pick", is_equipment=True,
        )
        base = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=list(self._strict_supplies(recall=1)),
            equipment=[tool, self._lantern()],
            store=StoreState(
                store_type=STORE_HOME,
                items=[store_item("a", 45, 1, name="ring", is_equipment=True)],
            ),
        )
        weapon_page = replace(
            base,
            store=StoreState(
                store_type=STORE_HOME,
                items=[
                    store_item(
                        "a", 21, 12, name="hammer", is_equipment=True,
                        is_ego=True, damage_dice_num=2, damage_dice_sides=5,
                    )
                ],
            ),
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(base), " ")
        self.assertEqual(policy.last_reason, "home:seek-combat-weapon-page")
        self.assertEqual(policy.choose_key(weapon_page), "pa\r")
        self.assertEqual(policy.last_reason, "home:withdraw-combat-weapon")

    def test_home_rearm_stops_after_wrapping_all_pages_without_weapon(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            name="pick", is_equipment=True,
        )
        home = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=list(self._strict_supplies(recall=1)),
            equipment=[tool, self._lantern()],
            store=StoreState(
                store_type=STORE_HOME,
                items=[store_item("a", 45, 1, name="ring", is_equipment=True)],
            ),
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(home), " ")
        self.assertEqual(policy.choose_key(home), "\x1b")
        self.assertEqual(policy.last_reason, "home:no-combat-weapon")
        self.assertTrue(policy._combat_weapon_ready(home))

    def test_scavenging_ignores_downstairs_and_returns_upstairs(self):
        grids = {
            Position(10, 10): GridState(
                position=Position(10, 10),
                known=True,
                passable=True,
                wall=False,
                has_monster=False,
                has_down_stairs=True,
                has_up_stairs=True,
                unsafe=False,
            )
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"
        self.assertEqual(policy.choose_key(snap), "<")
        self.assertEqual(policy.last_reason, "fundraise:ascend")

    def test_scavenging_keeps_moving_when_upstairs_route_is_unknown(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }
        for y in range(9, 12):
            for x in range(9, 13):
                pos = Position(y, x)
                if pos not in grids:
                    grids[pos] = grid(y, x, passable=False)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:scavenge")

    def test_mining_ignores_a_nearby_weakling_and_keeps_seeking_treasure(self):
        grids = {
            Position(10, 8): grid(10, 8, gold=True),
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, upstairs=True, monster=True),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [hostile(1, 10, 12, distance=2)],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key

        self.assertEqual(policy.choose_key(snap), "4")
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def test_mining_eliminates_a_visible_multiplier_before_treasure(self):
        grids = {
            Position(10, 8): grid(10, 8, gold=True),
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, upstairs=True, monster=True),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [hostile(1, 10, 12, distance=2, can_multiply=True)],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:eliminate-multiplier")

        hidden_snap = Snapshot(
            player(10, 11, class_id=PLAYER_CLASS_WARRIOR),
            {
                position: replace(cell, has_monster=False, monster_index=0)
                for position, cell in grids.items()
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=snap.inventory,
            equipment=snap.equipment,
        )
        self.assertEqual(policy.choose_key(hidden_snap), "6", policy.last_reason)
        self.assertEqual(
            policy.last_reason, "fundraise:eliminate-multiplier-last-seen"
        )

    def test_mining_keeps_tracking_treasure_when_its_display_flickers(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        first_grids = {
            Position(10, 8): grid(10, 8, upstairs=True),
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12),
            Position(10, 13): grid(10, 13, gold=True),
        }
        second_grids = dict(first_grids)
        second_grids[Position(10, 13)] = grid(10, 13)
        inventory = self._strict_supplies(recall=0, detection=1)
        equipment = [tool, self._lantern()]
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = (DUNGEON_YEEK_CAVE, 1, 0)

        first = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            first_grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=inventory,
            equipment=equipment,
        )
        second = Snapshot(
            player(10, 11, class_id=PLAYER_CLASS_WARRIOR),
            second_grids,
            [],
            floor_key=first.floor_key,
            inventory=inventory,
            equipment=equipment,
        )

        self.assertEqual(policy.choose_key(first), "6")
        self.assertEqual(policy.choose_key(second), "6")
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def test_mining_commits_to_treasure_when_a_nearer_vein_appears(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        inventory = self._strict_supplies(recall=0, detection=1)
        equipment = [tool, self._lantern()]
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = (DUNGEON_YEEK_CAVE, 1, 0)

        first_grids = {
            Position(10, x): grid(10, x, gold=x == 14)
            for x in range(9, 15)
        }
        first = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            first_grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=inventory,
            equipment=equipment,
        )
        self.assertEqual(policy.choose_key(first), "6")
        self.assertEqual(policy._treasure_target, Position(10, 14))

        second_grids = {
            Position(10, x): grid(10, x, gold=x in {9, 14})
            for x in range(9, 15)
        }
        second = Snapshot(
            player(10, 11, class_id=PLAYER_CLASS_WARRIOR),
            second_grids,
            [],
            floor_key=first.floor_key,
            inventory=inventory,
            equipment=equipment,
        )

        self.assertEqual(policy.choose_key(second), "6")
        self.assertEqual(policy._treasure_target, Position(10, 14))
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def test_mining_remembers_the_route_after_it_leaves_the_current_view(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        inventory = self._strict_supplies(recall=0, detection=1)
        equipment = [tool, self._lantern()]
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = (DUNGEON_YEEK_CAVE, 1, 0)

        first = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, x): grid(10, x, gold=x == 15)
                for x in range(10, 16)
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=inventory,
            equipment=equipment,
        )
        self.assertEqual(policy.choose_key(first), "6")

        second = Snapshot(
            player(10, 11, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 11): grid(10, 11),
                Position(10, 15): grid(10, 15, gold=True),
            },
            [],
            floor_key=first.floor_key,
            inventory=inventory,
            equipment=equipment,
        )

        self.assertEqual(policy.choose_key(second), "6")
        self.assertEqual(policy._treasure_target, Position(10, 15))
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def test_mining_sweeps_the_detected_area_before_chasing_veins(self):
        # Phase 1 of the two-phase design: unknown terrain inside the detected
        # radius is mapped FIRST, giving every cheap vein a walkable approach —
        # the old routine probed/tunnelled at one coordinate and left the rest.
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 14): grid(10, 14, gold=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key  # not a fresh floor: keep the centers
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertFalse(policy._mining_sweep_done)

    def test_mining_abandons_dry_floor_immediately_after_detection(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        base_grids = {
            Position(10, 10): grid(10, 10, upstairs=True),
            Position(10, 11): grid(10, 11),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            base_grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=80,
            height=80,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        self.assertTrue(policy.choose_key(snap).startswith(READ_KEY))
        revealed = dict(base_grids)
        revealed.update(
            {
                Position(20, 20): grid(20, 20, passable=False, gold=True),
                Position(30, 30): grid(30, 30, passable=False, gold=True),
            }
        )
        detected = replace(snap, grids=revealed)
        self.assertEqual(policy.choose_key(detected), "<")
        self.assertEqual(policy.last_reason, "fundraise:ascend")
        self.assertLessEqual(policy._mining_sweep_steps, 3)

    def test_mining_viability_gate_preserves_rich_unreachable_sweep(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        start = Position(10, 10)
        snap = Snapshot(
            player(start.y, start.x, class_id=PLAYER_CLASS_WARRIOR),
            {start: grid(start.y, start.x), Position(10, 11): grid(10, 11)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=80,
            height=80,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        self.assertTrue(policy.choose_key(snap).startswith(READ_KEY))

        revealed = dict(snap.grids)
        for index in range(MINING_MIN_VIABLE_VEINS):
            position = Position(30, 30 + index)
            revealed[position] = grid(
                position.y, position.x, passable=False, gold=True
            )
        detected = replace(snap, grids=revealed)
        with patch.object(
            policy, "_mining_sweep_step", return_value=Position(10, 11)
        ):
            policy.choose_key(detected)
            policy.choose_key(detected)

        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertGreaterEqual(policy._mining_sweep_steps, 2)
        self.assertFalse(policy._mining_sweep_done)

    def test_mining_oscillation_leaves_when_no_other_frontier_remains(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11)},
            [], floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=30, height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._recent.extend(
            [Position(10, 10), Position(10, 11)] * (STUCK_WINDOW // 2)
        )
        # The only frontier is the tile just left. It is blacklisted as view
        # flicker, and the existing evidence gate leaves because no unrelated
        # frontier remains.
        policy.choose_key(snap)
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs-explore")
        self.assertTrue(policy._mining_sweep_done)
        self.assertIn(Position(10, 11), policy._mining_swept_dead_targets)
        self.assertEqual(list(policy._recent), [])

    def test_long_mining_sweep_does_not_spend_collection_leash(self):
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = (DUNGEON_YEEK_CAVE, 1, 0)
        policy._mining_detection_centers.append(Position(10, 10))
        policy._mining_stall_turns = 7
        base = {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11)}
        with patch.object(policy, "_mining_sweep_step", return_value=Position(10, 11)):
            for index in range(MINING_STALL_LIMIT + 1):
                grids = dict(base)
                grids.update(
                    {Position(20 + n, 20): grid(20 + n, 20) for n in range(index)}
                )
                snap = Snapshot(
                    player(10, 10), grids, [],
                    floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=1000, height=1000,
                    inventory=self._strict_supplies(recall=0, detection=1),
                    equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
                )
                policy._build_grid_index(snap)
                policy._fundraising_key(snap, [])
                self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertEqual(policy._mining_stall_turns, 7)
        self.assertFalse(policy._mining_sweep_done)

        with patch.object(policy, "_mining_sweep_step", return_value=None), patch.object(
            policy, "_treasure_step", return_value=Position(10, 11)
        ):
            policy._fundraising_key(snap, [])
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def test_mining_sweep_latches_done_only_when_frontier_is_exhausted(self):
        snap = Snapshot(
            player(0, 0), {Position(0, 0): grid(0, 0)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=1, height=1,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(0, 0))
        policy._build_grid_index(snap)
        policy._fundraising_key(snap, [])
        self.assertTrue(policy._mining_sweep_done)

    def test_mining_sweep_no_progress_cutoff_latches_done(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11)},
            [], floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=30, height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._reset_mining_sweep_progress(snap)
        with patch.object(policy, "_mining_sweep_step", return_value=Position(10, 11)):
            for _ in range(MINING_SWEEP_NO_PROGRESS_LIMIT):
                policy._build_grid_index(snap)
                policy._fundraising_key(snap, [])
        self.assertTrue(policy._mining_sweep_done)
        self.assertEqual(policy._mining_sweep_steps, MINING_SWEEP_NO_PROGRESS_LIMIT)

    def test_known_terrain_approach_to_sweep_goal_is_progress(self):
        policy = HengbotPolicy()
        goal = Position(10, 50)
        policy._mining_sweep_goal = goal
        first = Snapshot(player(10, 10), {Position(10, 10): grid(10, 10)}, [])
        policy._reset_mining_sweep_progress(first)
        policy._mining_sweep_goal = goal
        for x in range(10, 41):
            snap = replace(first, player=player(10, x))
            policy._mining_sweep_goal = goal
            policy._record_mining_sweep_step(snap)
        self.assertEqual(policy._mining_sweep_steps, 31)
        self.assertFalse(policy._mining_sweep_done)
        self.assertEqual(policy._mining_sweep_no_progress, 0)

    def test_sweep_escape_blacklists_goal_without_resetting_bounds(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, x): grid(10, x) for x in range(10, 14)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=30, height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        bad, good = Position(10, 11), Position(10, 13)
        goals = [(bad, bad), (bad, bad), (good, good)]
        with patch.object(policy, "_nearest_goal_and_step", side_effect=goals):
            for _ in range(2):
                policy._recent.extend([Position(10, 10), bad] * (STUCK_WINDOW // 2))
                policy._build_grid_index(snap)
                policy._fundraising_key(snap, [])
        self.assertIn(bad, policy._mining_swept_dead_targets)
        self.assertEqual(policy._mining_sweep_goal, good)
        self.assertEqual(policy._mining_sweep_steps, 2)
        self.assertEqual(policy._mining_sweep_no_progress, 1)

    def test_sweep_frontier_predicate_excludes_blacklisted_goal(self):
        start = Position(10, 10)
        blacklisted = Position(10, 11)
        other_frontier = Position(11, 10)
        snap = Snapshot(
            player(start.y, start.x),
            {
                start: grid(start.y, start.x),
                blacklisted: grid(blacklisted.y, blacklisted.x),
                other_frontier: grid(other_frontier.y, other_frontier.x),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
        )
        policy = HengbotPolicy()
        policy._mining_detection_centers.append(start)
        policy._mining_swept_dead_targets.add(blacklisted)
        policy._build_grid_index(snap)

        self.assertTrue(policy._is_frontier(snap, snap.grids[blacklisted]))
        self.assertEqual(policy._mining_sweep_step(snap), other_frontier)
        self.assertEqual(policy._mining_sweep_goal, other_frontier)

    def test_sweep_blacklists_real_junction_flicker_pair_and_retargets(self):
        a = Position(30, 119)
        b = Position(29, 120)
        c = Position(30, 121)
        good = Position(28, 121)
        grids = {
            position: grid(position.y, position.x)
            for position in (a, b, c, good)
        }
        base = Snapshot(
            player(a.y, a.x), grids, [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=200, height=100,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[
                item(
                    "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = base.floor_key
        policy._mining_scroll_used_floor = base.floor_key
        policy._mining_detection_centers.append(a)

        # Real 06:09 shape: at A the goal is C with a first step to B; at B
        # the goal flickers back to A. The second escape must blacklist both
        # goals and select an unrelated frontier.
        goals = [(c, b), (a, a), (good, good)]
        with patch.object(policy, "_nearest_goal_and_step", side_effect=goals):
            policy._recent.extend([a, b] * (STUCK_WINDOW // 2))
            policy._build_grid_index(base)
            self.assertEqual(policy._fundraising_key(base, []), "9")
            # The replacement step is still inside A/B, so preserve the
            # oscillation evidence and reject another flickering goal on the
            # next decision instead of spending a fresh stuck window.
            self.assertTrue(policy._is_oscillating())

            at_b = replace(base, player=player(b.y, b.x))
            policy._recent.extend([a, b] * (STUCK_WINDOW // 2))
            policy._build_grid_index(at_b)
            policy._fundraising_key(at_b, [])

        self.assertTrue({a, c} <= policy._mining_swept_dead_targets)
        self.assertEqual(policy._mining_sweep_goal, good)
        self.assertLessEqual(len(policy._mining_sweep_escape_pairs), 3)
        self.assertFalse(policy._mining_sweep_done)

    def test_mining_collection_waits_for_honest_sweep_completion(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11, gold=True)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=30, height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._recent.extend([Position(10, 10), Position(10, 9)] * (STUCK_WINDOW // 2))
        with patch.object(policy, "_mining_sweep_step", return_value=Position(10, 9)):
            policy._fundraising_key(snap, [])
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertFalse(policy._mining_sweep_done)

    def test_mining_sweep_hard_cap_latches_done(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11)},
            [], floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=30, height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._mining_sweep_steps = MINING_SWEEP_HARD_LIMIT - 1
        policy._mining_sweep_revealed_grids = 1
        with patch.object(policy, "_mining_sweep_step", return_value=Position(10, 11)):
            policy._build_grid_index(snap)
            policy._fundraising_key(snap, [])
        self.assertTrue(policy._mining_sweep_done)
        self.assertEqual(policy._mining_sweep_steps, MINING_SWEEP_HARD_LIMIT)

    def test_tapped_out_without_new_reveals_finishes_the_floor(self):
        # The live 06:09 macro-cycle: the sweep honestly latched done, phase 2
        # found no distance-1 vein, and tapped-out resumed the exact sweep that
        # had just dead-ended (nothing had been dug, nothing newly revealed) —
        # bouncing the same junction until the cli loop guard killed the bot.
        # Without map growth past the at-done high-water mark, tapped-out must
        # LEAVE, not resume.
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[
                item(
                    "main_hand",
                    TVAL_DIGGING,
                    SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._mining_sweep_done = True
        policy._mining_grids_at_sweep_done = len(snap.grids)
        policy._build_grid_index(snap)

        key = policy._mining_tapped_out_key(snap)
        self.assertNotEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertEqual(policy._mining_stall_turns, MINING_STALL_LIMIT)
        self.assertTrue(policy._mining_sweep_done)
        self.assertIsNotNone(key)

    def test_tapped_out_resumes_after_digging_reveals_new_grids(self):
        # The legitimate resume: collection dug a vein and the map grew past
        # the at-done high-water mark — fresh frontiers may have been unsealed,
        # so the sweep restarts with reset counters.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12),
        }
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[
                item(
                    "main_hand",
                    TVAL_DIGGING,
                    SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._mining_sweep_done = True
        # done was latched when only two grids were known; the third grid is
        # the newly exposed floor from a dug vein.
        policy._mining_grids_at_sweep_done = 2
        policy._build_grid_index(snap)

        policy._mining_tapped_out_key(snap)
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertFalse(policy._mining_sweep_done)
        self.assertEqual(policy._mining_sweep_steps, 1)

    def test_tapped_out_uses_revealed_high_water_after_tiles_leave_view(self):
        base_grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }
        base = Snapshot(
            player(10, 10),
            base_grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[
                item(
                    "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = base.floor_key
        policy._mining_scroll_used_floor = base.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._mining_sweep_done = True
        policy._mining_grids_at_sweep_done = len(base_grids)

        expanded = replace(
            base,
            grids={
                **base_grids,
                Position(10, 12): grid(10, 12, gold=True),
            },
        )
        policy._fundraising_key(expanded, [])
        self.assertEqual(policy._mining_sweep_revealed_grids, 3)

        reduced = replace(base, grids=base_grids)
        policy._build_grid_index(reduced)
        policy._mining_tapped_out_key(reduced)
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertFalse(policy._mining_sweep_done)

    def test_tapped_out_sweep_resume_resets_hard_cap_progress(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11)},
            [], floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=30, height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._mining_sweep_done = True
        policy._mining_sweep_steps = MINING_SWEEP_HARD_LIMIT

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertFalse(policy._mining_sweep_done)
        self.assertEqual(policy._mining_sweep_steps, 1)

    def test_mining_walks_to_a_reachable_vein_and_digs_it_from_the_floor(self):
        # Phase 2: collection is walk + dig-the-adjacent-vein only.
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        grids = {Position(10, x): grid(10, x) for x in (10, 11, 12, 13)}
        grids[Position(10, 14)] = grid(
            10, 14, passable=False, gold=True, can_dig=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

        beside = replace(
            snap, player=player(10, 13, class_id=PLAYER_CLASS_WARRIOR)
        )
        digger = HengbotPolicy()
        digger._fundraising_mode = "mine"
        digger._mining_scroll_used_floor = snap.floor_key
        self.assertEqual(digger.choose_key(beside), TUNNEL_KEY + "6")
        self.assertEqual(digger.last_reason, "fundraise:mine-treasure")

    def test_mining_walks_to_a_diagonal_only_vein_approach_and_digs(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        treasure = Position(11, 12)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                treasure: grid(11, 12, passable=False, gold=True, can_dig=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=30, height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_sweep_done = True

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

        beside = replace(
            snap, player=player(10, 11, class_id=PLAYER_CLASS_WARRIOR)
        )
        self.assertEqual(policy.choose_key(beside), TUNNEL_KEY + "3")
        self.assertEqual(policy.last_reason, "fundraise:mine-treasure")

    def test_mining_never_tunnels_toward_a_vein_without_a_walkable_approach(self):
        # A vein with no walkable eight-direction approach is the EXPENSIVE kind the
        # user's design trades away: it must be left, not tunnelled at through
        # blank rock (the leash burn that used to strand the rest of the floor).
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        treasure = Position(12, 12)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 12): grid(10, 12),
                treasure: grid(
                    treasure.y, treasure.x, passable=False, gold=True, can_dig=True
                ),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._known_treasure = {treasure}
        policy._treasure_target = treasure
        policy._build_grid_index(snap)

        key = policy._fundraising_key(snap, [])
        self.assertNotEqual(key, TUNNEL_KEY + "3")
        self.assertNotEqual(policy.last_reason, "fundraise:tunnel-to-treasure")
        self.assertEqual(policy._mining_stall_turns, MINING_STALL_LIMIT)

    def test_mining_peels_a_vein_chain_via_the_opened_floor(self):
        # Digging a vein leaves floor behind, so the vein BEHIND it becomes the
        # next distance-1 target through that opening — clusters get collected
        # without ever digging blank rock.
        back = Position(10, 13)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12),  # the front vein, already dug out
            back: grid(10, 13, passable=False, gold=True, can_dig=True),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
        )
        policy = HengbotPolicy()
        policy._known_treasure = {back}
        policy._build_grid_index(snap)

        self.assertEqual(policy._treasure_step(snap), Position(10, 11))

    def test_mining_resumes_the_sweep_when_digging_opens_new_frontiers(self):
        # Peeling a vein chain can unseal a whole pocket: with no reachable vein
        # left but fresh in-radius frontiers, sweep again instead of leaving.
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._mining_sweep_done = True
        policy._build_grid_index(snap)

        policy._fundraising_key(snap, [])
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertFalse(policy._mining_sweep_done)

    def test_redetection_restarts_the_sweep_and_forgives_dropped_veins(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_sweep_done = True
        policy._drop_mining_vein(Position(10, 14))

        key = policy._fundraising_key(snap, [])
        self.assertEqual(policy.last_reason, "fundraise:detect-treasure")
        self.assertTrue(key.startswith(READ_KEY))
        self.assertFalse(policy._mining_sweep_done)
        self.assertEqual(policy._mining_dropped_veins, set())

    def test_mined_vein_counts_as_collected_when_its_gold_disappears(self):
        # Coverage telemetry: standing next to a formerly-golden grid whose gold
        # is gone means we collected it.
        vein = Position(10, 11)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10), vein: grid(10, 11)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy()
        policy._floor_key = snap.floor_key
        policy._known_treasure = {vein}
        policy.choose_key(snap)
        self.assertEqual(policy._mining_veins_collected, 1)
        self.assertNotIn(vein, policy._known_treasure)

    def test_fundraising_recalls_after_a_trap_door_drops_player_below_level_one(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"

        self.assertEqual(policy._fundraising_key(snap, []), "rr")
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy.last_reason, "return:recall")

    def test_mining_abandons_a_revisited_treasure_route_before_long_leash(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(9, 10): grid(9, 10, upstairs=True),
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 14): grid(10, 14, gold=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._known_treasure = {Position(10, 14)}
        policy._build_grid_index(snap)

        # Detection reveals coordinates, not routes. The sweep owns terrain
        # discovery now, so with nothing to sweep and no walkable approach the
        # floor is finished at once instead of probing blindly at the vein.
        self.assertEqual(policy._fundraising_key(snap, []), "8")
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs")
        self.assertEqual(policy._mining_stall_turns, MINING_STALL_LIMIT)

    def test_fundraising_upstairs_route_breaks_a_two_tile_cycle(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(9, 10): grid(9, 10),
            Position(8, 10): grid(8, 10, upstairs=True),
            Position(10, 11): grid(10, 11),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._recent.extend(
            [Position(10, 10), Position(9, 10)] * (STUCK_WINDOW // 2)
        )
        policy._visit_counts[Position(9, 10)] = STUCK_WINDOW
        policy._build_grid_index(snap)

        self.assertEqual(policy._leave_fundraising_floor(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs")

    def test_fundraising_upstairs_search_leash_recalls_from_level_one(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT
        policy._build_grid_index(snap)

        self.assertEqual(policy._leave_fundraising_floor(snap), "rr")
        self.assertEqual(policy.last_reason, "fundraise:recall-stuck")
        self.assertTrue(policy._returning_to_town)

    def test_fundraising_two_tile_sealed_pocket_tunnels_out(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }
        for y in range(9, 12):
            for x in range(9, 13):
                pos = Position(y, x)
                if pos not in grids:
                    grids[pos] = grid(y, x, passable=False, can_dig=True)
        grids[Position(10, 13)] = grid(
            10, 13, passable=False, can_dig=True, upstairs=True
        )
        snap = Snapshot(
            player(10, 11, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._recent.extend(
            [Position(10, 11), Position(10, 10)] * (STUCK_WINDOW // 2)
        )
        policy._visit_counts[Position(10, 10)] = STUCK_WINDOW
        policy._visit_counts[Position(10, 11)] = STUCK_WINDOW
        policy._search_counts[(10, 11)] = SEARCH_LIMIT
        policy._build_grid_index(snap)

        self.assertEqual(
            policy._leave_fundraising_floor(snap), TUNNEL_KEY + "6"
        )
        self.assertEqual(policy.last_reason, "fundraise:tunnel-out")

    def test_mining_abandons_route_even_when_target_churn_clears_target_counter(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(9, 10): grid(9, 10, upstairs=True),
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 14): grid(10, 14, gold=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._known_treasure = {Position(10, 14)}
        policy._build_grid_index(snap)

        for _ in range(MINING_NAVIGATION_REVISIT_LIMIT - 1):
            policy._fundraising_key(snap, [])
            policy._mining_route_visits.clear()
            policy._treasure_target = None

        self.assertEqual(policy._fundraising_key(snap, []), "8")
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs")
        self.assertEqual(policy._mining_stall_turns, MINING_STALL_LIMIT)
        self.assertEqual(policy._mining_stall_turns, MINING_STALL_LIMIT)

        moved = replace(snap, player=player(10, 11, class_id=PLAYER_CLASS_WARRIOR))
        policy._build_grid_index(moved)
        self.assertEqual(policy._fundraising_key(moved, []), "7")
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs")

    def test_mining_retargets_after_a_walkable_treasure_route_stalls(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        east = Position(10, 14)
        south = Position(14, 10)
        grids = {
            Position(10, 10): grid(10, 10),
            east: grid(east.y, east.x, gold=True),
            south: grid(south.y, south.x, gold=True),
        }
        for x in range(11, 14):
            grids[Position(10, x)] = grid(10, x)
        for y in range(11, 14):
            grids[Position(y, 10)] = grid(y, 10)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._known_treasure = {east, south}
        policy._build_grid_index(snap)

        for _ in range(MINING_ROUTE_REVISIT_LIMIT - 1):
            self.assertEqual(policy._fundraising_key(snap, []), "6")
            self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

        self.assertEqual(policy._fundraising_key(snap, []), "2")
        self.assertNotIn(east, policy._known_treasure)
        self.assertIn(south, policy._known_treasure)
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")
        self.assertLess(policy._mining_stall_turns, MINING_STALL_LIMIT)

    def test_mining_clears_shared_route_visits_when_selecting_next_treasure(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        treasure = Position(10, 14)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12),
                Position(10, 13): grid(10, 13),
                treasure: grid(treasure.y, treasure.x, gold=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._known_treasure = {treasure}
        policy._mining_route_visits[snap.player.position] = (
            MINING_ROUTE_REVISIT_LIMIT - 1
        )
        policy._build_grid_index(snap)

        self.assertEqual(policy._fundraising_key(snap, []), "6")
        self.assertIn(treasure, policy._known_treasure)
        self.assertEqual(policy._treasure_target, treasure)
        self.assertEqual(policy._mining_route_visits[snap.player.position], 1)
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def test_mining_retargets_instead_of_leaving_floor_on_oscillation(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        east = Position(10, 14)
        south = Position(14, 10)
        grids = {
            Position(10, 10): grid(10, 10),
            east: grid(east.y, east.x, gold=True),
            south: grid(south.y, south.x, gold=True),
        }
        for x in range(11, 14):
            grids[Position(10, x)] = grid(10, x)
        for y in range(11, 14):
            grids[Position(y, 10)] = grid(y, 10)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._known_treasure = {east, south}
        policy._treasure_target = east
        policy._recent.extend(
            [Position(10, 10), Position(10, 11)] * (STUCK_WINDOW // 2)
        )
        policy._build_grid_index(snap)

        self.assertEqual(policy._fundraising_key(snap, []), "2")
        self.assertNotIn(east, policy._known_treasure)
        self.assertIn(south, policy._known_treasure)
        self.assertEqual(policy._treasure_target, south)
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def test_mining_leaves_after_retargeting_repeats_in_same_local_loop(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        targets = [Position(10, 14), Position(14, 10), Position(10, 6)]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(9, 10): grid(9, 10, upstairs=True),
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(11, 10): grid(11, 10),
                Position(10, 9): grid(10, 9),
                **{target: grid(target.y, target.x, gold=True) for target in targets},
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._build_grid_index(snap)

        for index, target in enumerate(targets):
            policy._known_treasure = set(targets[index:])
            policy._treasure_target = target
            policy._recent.extend(
                [Position(10, 10), Position(10, 11)] * (STUCK_WINDOW // 2)
            )
            key = policy._fundraising_key(snap, [])

        self.assertEqual(key, "8")
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs")
        self.assertEqual(policy._mining_stall_turns, MINING_STALL_LIMIT)

    def test_prime_restores_scavenging_mode_after_bot_restart(self):
        shovel = item(
            "h", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=1),
            equipment=[shovel, self._lantern()],
        )
        policy = HengbotPolicy()

        policy.prime(snap)

        self.assertEqual(policy._fundraising_mode, "scavenge")

    def test_prime_does_not_start_fundraising_for_a_carried_digger(self):
        shovel = item(
            "h", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[shovel, *self._strict_supplies(recall=1)],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()

        policy.prime(snap)

        self.assertIsNone(policy._fundraising_mode)

    def test_prime_restores_mining_when_digger_and_detection_scroll_are_carried(self):
        shovel = item(
            "h", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[shovel, *self._strict_supplies(recall=1, detection=1)],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()

        policy.prime(snap)

        self.assertEqual(policy._fundraising_mode, "mine")

    def test_conquest_collects_visible_drop_before_returning(self):
        grids = {Position(10, 10): grid(10, 10, upstairs=True, objects=1)}
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 13, 0),
            inventory=self._strict_supplies(recall=10),
            equipment=[self._lantern()],
            yeek_cave_conquered=True,
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
        )
        policy = HengbotPolicy()
        before = replace(snap, yeek_cave_conquered=False, conquered_dungeon_ids=())
        policy._observe(before)
        self.assertEqual(policy.choose_key(snap), "g")
        self.assertEqual(policy.last_reason, "victory:pickup")

        empty = Snapshot(
            snap.player,
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [],
            floor_key=snap.floor_key,
            inventory=snap.inventory,
            equipment=snap.equipment,
            yeek_cave_conquered=True,
        )
        self.assertEqual(policy.choose_key(empty), "<")
        self.assertEqual(policy.last_reason, "return:ascend")

    def test_conquest_collects_every_item_from_a_floor_pile(self):
        grids = {Position(10, 10): grid(10, 10, upstairs=True, objects=2)}
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 13, 0),
            inventory=self._strict_supplies(recall=10),
            equipment=[self._lantern()],
            yeek_cave_conquered=True,
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
        )

        policy = HengbotPolicy()
        before = replace(snap, yeek_cave_conquered=False, conquered_dungeon_ids=())
        policy._observe(before)
        self.assertEqual(policy.choose_key(snap), "gaa")
        self.assertEqual(policy.last_reason, "victory:pickup")

    def test_conquest_runs_normal_town_routine_then_listens_for_rumor(self):
        supplies = self._strict_supplies(recall=1)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, building_type=0),
        }
        snap = Snapshot(
            player(10, 10, gold=2500, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            inventory=supplies,
            equipment=[self._lantern()],
            yeek_cave_conquered=True,
        )
        policy = HengbotPolicy()
        # Adjacent inn one step east: walk on and read a full batch of rumors in
        # this single visit (2500g - 300 reserve = 2200 affordable, capped at 200
        # reads), then leave. Unlocking Angband recall takes ~200 medium rumors.
        self.assertEqual(policy.choose_key(snap), "6" + "u\r" * 200 + "\x1b")
        self.assertEqual(policy.last_reason, "town:rumor-batch")

    def test_rumor_batch_size_adapts_to_affordable_gold(self):
        # Only 900g on hand: keep the 300g reserve and read (900-300)/10 = 60.
        supplies = self._strict_supplies(recall=1)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, building_type=0),
        }
        snap = Snapshot(
            player(10, 10, gold=900, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            inventory=supplies,
            equipment=[self._lantern()],
            yeek_cave_conquered=True,
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "6" + "u\r" * 60 + "\x1b")
        self.assertEqual(policy.last_reason, "town:rumor-batch")

    def test_rumor_needs_funds_when_too_poor_for_a_batch(self):
        # Below the reserve+one-read floor, mine for gold instead of a token visit.
        supplies = self._strict_supplies(recall=1)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, building_type=0),
        }
        snap = Snapshot(
            player(10, 10, gold=20, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            inventory=supplies,
            equipment=[self._lantern()],
            yeek_cave_conquered=True,
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), WAIT_KEY)
        self.assertEqual(policy.last_reason, "town:rumor-needs-funds")

    def test_walks_to_a_distant_inn_before_sending_the_rumor_macro(self):
        # The inn is two tiles east; the first step does NOT land on it, so the
        # rumor keys must NOT ride along (they would leak into the town command
        # loop and the inn would never be entered).
        supplies = self._strict_supplies(recall=1)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, building_type=0),
        }
        snap = Snapshot(
            player(10, 10, gold=2500, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            inventory=supplies,
            equipment=[self._lantern()],
            yeek_cave_conquered=True,
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "town:rumor")

    def test_standing_on_inn_does_not_latch_inn_not_found_block(self):
        # Regression for the town "5-loop": when already standing on the inn tile
        # (a path-to-self is empty), the old code latched a sticky inn-not-found
        # WAIT and froze forever. The fix falls through instead, so the block is
        # never set and the run can continue (recall / dive again).
        supplies = self._strict_supplies(recall=1)
        snap = Snapshot(
            player(10, 10, gold=2500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, building_type=0)},
            [],
            inventory=supplies,
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
            yeek_cave_conquered=True,
        )
        policy = HengbotPolicy()
        policy._rumor_unlock_pending = True
        policy._deepest_level = RECALL_MIN_DEPTH
        policy._town_special_key(snap)
        self.assertNotEqual(policy._town_blocked_reason, "inn-not-found")
        self.assertNotEqual(policy.last_reason, "town:blocked:inn-not-found")

    def test_angband_departure_uses_recall_and_keeps_return_stock(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=2),
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_ANGBAND,
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )
        policy = HengbotPolicy()
        policy._char_dump_done_this_visit = True  # past the pre-dive dump
        self.assertEqual(policy.choose_key(snap), "rra")
        self.assertEqual(policy.last_reason, "town:recall-to-angband")

    def test_town_recall_selects_the_target_from_entered_dungeon_order(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            # Departure consumes one scroll; five leaves four in the dungeon,
            # safely above the deep-return threshold of three.
            inventory=self._strict_supplies(recall=5, teleport=4, critical=4),
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
            entered_dungeon_ids=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE),
        )
        policy = HengbotPolicy()
        policy._deepest_level = RECALL_MIN_DEPTH
        policy._char_dump_done_this_visit = True  # past the pre-dive dump

        self.assertEqual(policy._town_special_key(snap), "rrb")
        self.assertEqual(policy.last_reason, "town:recall-to-yeek-cave")

    def test_recall_selection_falls_back_to_current_destination(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            recall_dungeon_id=4,
            entered_dungeon_ids=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE),
        )

        self.assertEqual(HengbotPolicy._recall_selection_key(snap, 4), "a")

    def test_yeek_recall_departure_keeps_dungeon_reserve_after_use(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=3, teleport=3, critical=3),
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
        )
        policy = HengbotPolicy()
        policy._deepest_level = RECALL_MIN_DEPTH

        # planned depth 6 -> _recall_target 3, +1 for the departure recall, +1
        # more so arrival (target - 1) still clears RECALL_RETURN_THRESHOLD.
        self.assertEqual(policy._recall_required_target(snap), 5)
        self.assertFalse(policy._recall_ready(snap))
        self.assertIsNone(policy._town_special_key(snap))

    def test_angband_recall_purchase_target_covers_min_depth_band_arrival(self):
        # Regression: depths 5-10 all share _recall_target==3. Buying only
        # target+1==4 for departure left exactly 3 on arrival after the entry
        # recall was consumed -- equal to RECALL_RETURN_THRESHOLD, so the bot
        # "recall-low" returned (and separately judged itself short of
        # _next_depth_supply_shortage's next-depth minimum) the instant a dive
        # began. Buying one more so target==5 leaves 4 on arrival, clearing
        # both.
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            angband_recall_unlocked=True,
        )
        policy = HengbotPolicy()
        policy._target_dungeon_id = DUNGEON_ANGBAND
        for planned_depth in (RECALL_MIN_DEPTH, 10):  # both ends of the 5-10 band
            policy._deepest_level = planned_depth - 1
            self.assertEqual(policy._recall_target(planned_depth), 3)
            self.assertEqual(policy._recall_required_target(snap), 5)

    def test_recall_arrival_at_min_depth_band_clears_both_thresholds(self):
        # Simulated post-entry counts for the fix above: the new purchase amount
        # (5) leaves 4 recall scrolls on arrival at depths 5-10, which must NOT
        # trigger either an immediate return-to-town or a next-depth restock
        # demand; one fewer (3, the old broken arrival count) must trigger both.
        def arrival(count):
            return Snapshot(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                {Position(10, 10): grid(10, 10)},
                [],
                floor_key=(DUNGEON_YEEK_CAVE, RECALL_MIN_DEPTH, 0),
                inventory=self._strict_supplies(
                    recall=count, teleport=15, critical=10
                ),
                equipment=[self._lantern()],
            )

        policy = HengbotPolicy()
        stocked = arrival(4)
        low = arrival(3)
        self.assertFalse(policy._ledger_return_shortages(
            policy._supply_ledger(stocked, stocked.dungeon_level), stocked.dungeon_level
        ))
        self.assertFalse(policy._next_depth_supply_shortage(stocked))
        self.assertTrue(policy._ledger_return_shortages(
            policy._supply_ledger(low, low.dungeon_level), low.dungeon_level
        ))
        self.assertTrue(policy._next_depth_supply_shortage(low))

    def test_home_receives_equipment_before_other_town_work(self):
        gear = item(
            "a", 23, 1, name="unknown sword", aware=False, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[gear, *self._strict_supplies(recall=1)],
            equipment=[self._lantern()],
            store=StoreState(store_type=STORE_HOME, items=[]),
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "da\r")
        self.assertEqual(policy.last_reason, "home:deposit")

    def test_home_withdraws_one_unknown_item_then_identifies_it(self):
        identify_scroll = item(
            "i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify"
        )
        home = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[identify_scroll, *self._strict_supplies(recall=1)],
            equipment=[self._lantern()],
            store=StoreState(
                store_type=STORE_HOME,
                items=[
                    store_item(
                        "a",
                        23,
                        -1,
                        name="unknown sword",
                        aware=False,
                        known=False,
                        fully_known=False,
                        is_equipment=True,
                    )
                ],
            ),
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(home), "pa\r")
        self.assertEqual(policy.last_reason, "home:batch-withdraw")

        withdrawn = item(
            "a",
            23,
            -1,
            name="unknown sword",
            aware=False,
            known=False,
            is_equipment=True,
        )
        town = Snapshot(
            home.player,
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[withdrawn, identify_scroll, *self._strict_supplies(recall=1)],
            equipment=home.equipment,
        )
        self.assertEqual(policy.choose_key(town), "ria")
        self.assertEqual(policy.last_reason, "identify:normal")

    def test_home_skips_average_pseudo_identified_equipment_for_occupied_slot(self):
        average = store_item(
            "a",
            23,
            1,
            name="average sword",
            known=False,
            fully_known=False,
            is_equipment=True,
            pseudo_feeling="average",
        )
        home = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[
                self._lantern(),
                item("main_hand", 23, 2, is_equipment=True),
            ],
            store=StoreState(store_type=STORE_HOME, items=[average]),
        )
        policy = HengbotPolicy()

        self.assertNotEqual(policy.choose_key(home), "pa\r")
        self.assertIsNone(policy._identification_need)

    def test_home_processing_pages_past_a_page_without_candidates(self):
        occupied_average = store_item(
            "a",
            23,
            1,
            name="average sword",
            known=False,
            fully_known=False,
            is_equipment=True,
            pseudo_feeling="average",
        )
        later_gloves = store_item(
            "a",
            31,
            1,
            name="unknown gloves",
            known=False,
            fully_known=False,
            is_equipment=True,
            pseudo_feeling="average",
        )
        base = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[
                self._lantern(),
                item("main_hand", 23, 2, is_equipment=True),
            ],
            store=StoreState(store_type=STORE_HOME, items=[occupied_average]),
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(base), " ")
        self.assertEqual(policy.last_reason, "home:seek-processing-page")
        town = replace(
            base,
            grids={
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            store=None,
        )
        self.assertFalse(policy._town_departure_ready(town))

        later_page = replace(
            base,
            store=StoreState(store_type=STORE_HOME, items=[later_gloves]),
        )
        self.assertEqual(policy.choose_key(later_page), " ")
        self.assertEqual(policy.last_reason, "home:seek-processing-page")

    def test_home_processing_completes_only_after_page_wraps(self):
        average = store_item(
            "a",
            23,
            1,
            name="average sword",
            known=False,
            fully_known=False,
            is_equipment=True,
            pseudo_feeling="average",
        )
        home = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[
                self._lantern(),
                item("main_hand", 23, 2, is_equipment=True),
            ],
            store=StoreState(store_type=STORE_HOME, items=[average]),
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(home), " ")
        self.assertTrue(policy._home_candidate_waiting)
        self.assertEqual(policy.choose_key(home), "\x1b")
        self.assertEqual(policy.last_reason, "home:processing-complete")
        self.assertFalse(policy._home_candidate_waiting)

    def test_home_catalog_does_not_wrap_after_non_page_action(self):
        average = store_item(
            "a", 23, 1, name="average sword", known=False,
            fully_known=False, is_equipment=True, pseudo_feeling="average",
        )
        full_page = [average] + [
            store_item(
                chr(ord("a") + index), 23, index,
                name=f"average sword {index}", known=False,
                fully_known=False, is_equipment=True,
                pseudo_feeling="average",
            )
            for index in range(1, 12)
        ]
        home = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern(), item("main_hand", 23, 2, is_equipment=True)],
            store=StoreState(store_type=STORE_HOME, items=full_page),
        )
        policy = HengbotPolicy()

        policy.choose_key(home)
        policy.last_reason = "home:withdraw-processing-item"
        policy.choose_key(home)

        self.assertFalse(policy._equipment_catalog.home_scan_complete)

    def test_home_scans_known_candidates_without_withdrawing_them(self):
        gloves = store_item(
            "a", 31, 1, name="known gloves", known=True,
            fully_known=True, is_equipment=True,
        )
        boots = store_item(
            "b", 30, 1, name="known boots", known=True,
            fully_known=True, is_equipment=True,
        )
        supplies = self._strict_supplies(recall=1)
        first_page = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=supplies,
            equipment=[self._lantern()],
            store=StoreState(store_type=STORE_HOME, items=[gloves, boots]),
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(first_page), " ")
        self.assertEqual(policy.last_reason, "home:seek-processing-page")
        self.assertEqual(policy._home_pending_batch, [])

    def test_home_batch_keeps_three_pack_slots_free(self):
        filler = [
            item(chr(ord("a") + i), TVAL_STAFF, i, charges=1, name=f"staff-{i}")
            for i in range(19)
        ]
        gloves = store_item(
            "a", 31, 1, name="known gloves", known=True,
            fully_known=True, is_equipment=True,
        )
        boots = store_item(
            "b", 30, 1, name="known boots", known=True,
            fully_known=True, is_equipment=True,
        )
        home = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=filler,
            equipment=[self._lantern()],
            store=StoreState(store_type=STORE_HOME, items=[gloves, boots]),
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(home), " ")
        self.assertEqual(policy.last_reason, "home:seek-processing-page")
        self.assertEqual(policy._home_pending_batch, [])

    def test_home_batch_identification_does_not_trial_known_candidates(self):
        gloves = item(
            "a", 31, 1, name="known gloves", known=True,
            fully_known=True, is_equipment=True,
        )
        boots = item(
            "b", 30, 1, name="known boots", known=True,
            fully_known=True, is_equipment=True,
        )
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=[gloves, boots],
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._home_pending_batch = [
            policy._item_signature(gloves),
            policy._item_signature(boots),
        ]
        policy._home_candidate_waiting = False

        self.assertIsNone(policy._town_item_processing_key(town))
        self.assertEqual(policy.last_reason, "identify:batch-complete")
        self.assertFalse(policy._home_pending_batch)
        self.assertFalse(policy._home_batch_review_items)

    def test_pending_home_batch_blocks_town_departure(self):
        gloves = item(
            "a", 31, 1, name="known gloves", known=True,
            fully_known=True, is_equipment=True,
        )
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._home_candidate_waiting = False
        # Departure now requires a duplicate-preserving full Home scan. This
        # direct private-method test bypasses choose_key(), so mark the empty
        # Home's single page as observed and wrapped explicitly.
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_departure_ready = lambda snapshot: True
        self.assertTrue(policy._town_departure_ready(town))

        policy._equipment_departure_ready = lambda snapshot: False
        self.assertFalse(policy._town_departure_ready(town))
        policy._equipment_departure_ready = lambda snapshot: True
        policy._home_pending_batch = [policy._item_signature(gloves)]
        self.assertFalse(policy._town_departure_ready(town))

    def test_invalidated_home_catalog_routes_back_for_rescan(self):
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._home_candidate_waiting = False
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)

        self.assertFalse(policy._equipment_catalog.home_scan_complete)
        self.assertEqual(policy._next_required_store_type(town), STORE_HOME)
        policy._shopping_stuck = True
        policy._shopping_approach_step(town)
        self.assertFalse(policy._shopping_stuck)

    def test_complete_home_scan_routes_back_to_incomplete_item_page(self):
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
            town_flag=True,
        )
        incomplete_ego = store_item(
            "a", 31, 1, name="partly known ego gloves", known=True,
            fully_known=False, is_equipment=True, is_ego=True,
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([incomplete_ego])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([incomplete_ego])

        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        self.assertEqual(policy._next_required_store_type(town), STORE_HOME)

    def test_complete_home_scan_does_not_route_to_deferred_incomplete_item(self):
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
            town_flag=True,
        )
        incomplete = store_item(
            "a", 23, 4, name="unidentified dagger", known=False,
            fully_known=False, is_equipment=True,
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._deferred_home_items.add(policy._item_signature(incomplete))
        policy._home_candidate_waiting = False

        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        self.assertFalse(policy._has_actionable_incomplete_home_item())
        self.assertNotEqual(policy._next_required_store_type(town), STORE_HOME)

    def test_deferred_home_item_does_not_block_equipment_departure(self):
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
            town_flag=True,
        )
        incomplete = store_item(
            "a", 19, 1, name="unidentified bow", known=False,
            fully_known=False, is_equipment=True,
        )
        policy = HengbotPolicy()
        policy._home_candidate_waiting = False
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._deferred_home_items.add(policy._item_signature(incomplete))

        preparation = policy._prepare_equipment_optimization(town)

        self.assertIsNotNone(preparation)
        self.assertNotIn("incomplete-equipment-catalog", preparation.blockers)

    def _ready_home_town(self, *, gold=0):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=gold),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
            town_flag=True,
        )

    def test_processed_incomplete_home_item_is_not_actionable(self):
        # An incomplete Home item routes back to the Home only until a processing
        # pass burns it into _processed_home_items. After that _find_home_candidate
        # skips it, so _has_actionable_incomplete_home_item must agree — otherwise
        # home:processing-complete is reported while routing still insists on the
        # Home, looping the visit (or masking the real departure block).
        town = self._ready_home_town(gold=FUNDRAISING_START_GOLD)
        incomplete = store_item(
            "a", 31, 1, name="partly known ego gloves", known=True,
            fully_known=False, is_equipment=True, is_ego=True,
        )
        policy = HengbotPolicy()
        # Isolate the actionable-incomplete routing from the separate
        # _home_candidate_waiting route (mirrors the deferred-item test above).
        policy._home_candidate_waiting = False
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([incomplete])

        self.assertTrue(policy._has_actionable_incomplete_home_item())
        self.assertEqual(policy._next_required_store_type(town), STORE_HOME)

        policy._processed_home_items.add(policy._item_signature(incomplete))
        self.assertFalse(policy._has_actionable_incomplete_home_item())
        self.assertNotEqual(policy._next_required_store_type(town), STORE_HOME)

    def test_deferred_home_item_is_rearmed_by_a_mining_return(self):
        # A Home candidate deferred during a town stay must be offered again once
        # a completed Yeek Cave mining run establishes the retry boundary.
        candidate = store_item(
            "a", 23, 4, name="unidentified blade", is_equipment=True,
            aware=True, known=False,
        )
        pol = HengbotPolicy()
        signature = pol._item_signature(candidate)
        pol._deferred_home_items.add(signature)
        home = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            store=StoreState(store_type=STORE_HOME, items=[candidate]),
        )
        self.assertIsNone(pol._find_home_candidate(home))

        pol._floor_key = (DUNGEON_YEEK_CAVE, DEEP_FUNDRAISING_DEPTH, 0)
        pol._fundraising_mode = "mine"
        pol._observe(self._ready_home_town())

        self.assertNotIn(signature, pol._deferred_home_items)
        self.assertIsNotNone(pol._find_home_candidate(home))

    def test_mining_return_reclears_processed_home_items(self):
        # An ego item needing *full* identification is burned into
        # _processed_home_items after one pass and thereafter skipped forever
        # (its signature never changes until it is actually *fully* identified).
        # The mining-return retry boundary must clear that cache so the item is
        # offered for a fresh identification attempt.
        candidate = store_item(
            "a", 31, 1, name="ego gloves", is_equipment=True, aware=True,
            known=True, fully_known=False, is_ego=True,
        )
        pol = HengbotPolicy()
        signature = pol._item_signature(candidate)
        pol._processed_home_items.add(signature)
        home = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            store=StoreState(store_type=STORE_HOME, items=[candidate]),
        )
        self.assertIsNone(pol._find_home_candidate(home))

        pol._floor_key = (DUNGEON_YEEK_CAVE, DEEP_FUNDRAISING_DEPTH, 0)
        pol._fundraising_mode = "mine"
        pol._observe(self._ready_home_town())

        self.assertNotIn(signature, pol._processed_home_items)
        self.assertIsNotNone(pol._find_home_candidate(home))

    def test_processed_home_deadlock_enters_fundraising_not_wander(self):
        # The 2026-07-15 incident shape: the optimizer is blocked by an incomplete
        # catalog whose sole blocking item is Home gear already burned into
        # _processed_home_items (so no store route and no identify errand targets
        # it), gold sits above the auto-fundraise floor but below the target, and
        # the policy would otherwise fall through to endless stuck:wander. The
        # identification fundraising driver must instead enter mining to reach the
        # retry boundary.
        self.assertGreater(5894, FUNDRAISING_START_GOLD)
        self.assertLess(5894, FUNDRAISING_GOLD_TARGET)
        town = self._ready_home_town(gold=5894)
        incomplete = store_item(
            "a", 23, 4, name="ego blade", known=True, fully_known=False,
            is_equipment=True, is_ego=True,
        )
        policy = HengbotPolicy()
        policy._home_candidate_waiting = False
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._processed_home_items.add(policy._item_signature(incomplete))
        home_owned = next(
            owned for owned in policy._equipment_catalog.items
            if owned.origin == "home"
        )
        # Stub the optimizer preparation to the incident's blocker shape; the
        # real optimizer is exercised elsewhere. The driver must read the blocker
        # and the blocking item's origin/signature to decide recoverability.
        policy._prepare_equipment_optimization = lambda snapshot: SimpleNamespace(
            blockers=("incomplete-equipment-catalog",),
            result=SimpleNamespace(
                incomplete_item_ids=frozenset({home_owned.id})
            ),
        )

        # The stranded item is non-actionable: no Home route masks the deadlock,
        # and the ordinary gold-floor fundraiser refuses at this gold level.
        self.assertFalse(policy._has_actionable_incomplete_home_item())
        self.assertFalse(policy._start_fundraising(town))
        # The driver converts the block into a productive fundraising entry.
        self.assertTrue(policy._start_identification_fundraising(town))
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_identification_fundraising_ignores_a_non_home_blocker(self):
        # An equipped/pack unidentified item (mining does NOT re-arm it) must not
        # trigger the identification fundraiser: doing so would loop mining
        # forever without ever clearing the block.
        town = self._ready_home_town(gold=5894)
        policy = HengbotPolicy()
        policy._home_candidate_waiting = False
        equipped_owned = SimpleNamespace(id="equipped:x:0", origin="equipped")
        policy._equipment_catalog = SimpleNamespace(items=(equipped_owned,))
        policy._prepare_equipment_optimization = lambda snapshot: SimpleNamespace(
            blockers=("incomplete-equipment-catalog",),
            result=SimpleNamespace(
                incomplete_item_ids=frozenset({equipped_owned.id})
            ),
        )
        self.assertFalse(policy._start_identification_fundraising(town))
        self.assertIsNone(policy._fundraising_mode)

    def test_non_mining_town_arrival_preserves_processed_home_items(self):
        # The identification retry boundary is a completed MINING trip only. A
        # plain dive-and-return (here from Angband) must not re-scan every stored
        # item, so _processed_home_items is deliberately preserved on that arrival
        # even though the deferred sets are re-armed by the fresh-town reset.
        candidate = store_item(
            "a", 31, 1, name="ego gloves", is_equipment=True, known=True,
            fully_known=False, is_ego=True,
        )
        pol = HengbotPolicy()
        signature = pol._item_signature(candidate)
        pol._processed_home_items.add(signature)
        pol._deferred_home_items.add(signature)
        pol._floor_key = (DUNGEON_ANGBAND, 20, 0)
        pol._fundraising_mode = None

        pol._observe(self._ready_home_town())

        self.assertIn(signature, pol._processed_home_items)
        self.assertNotIn(signature, pol._deferred_home_items)

    def test_home_batch_never_selects_a_per_item_armour_upgrade(self):
        weaker = item(
            "a", 31, 1, name="weaker gloves", known=True,
            fully_known=True, is_equipment=True, ac=1, to_a=1,
        )
        stronger = item(
            "b", 31, 2, name="stronger gloves", known=True,
            fully_known=True, is_equipment=True, ac=2, to_a=4,
        )
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[weaker, stronger],
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._home_pending_batch = [
            policy._item_signature(weaker),
            policy._item_signature(stronger),
        ]

        self.assertIsNone(policy._town_item_processing_key(town))
        self.assertNotEqual(policy.last_reason, "equipment:equip-best-batch-armour")

    def test_home_does_not_trial_average_gloves_even_when_slot_is_empty(self):
        gloves = store_item(
            "a",
            31,
            1,
            name="leather gloves",
            known=False,
            fully_known=False,
            is_equipment=True,
            pseudo_feeling="average",
        )
        home = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
            store=StoreState(store_type=STORE_HOME, items=[gloves]),
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(home), " ")
        self.assertEqual(policy.last_reason, "home:seek-processing-page")

    def test_withdrawn_average_equipment_does_not_consume_identify(self):
        target = item(
            "a",
            23,
            1,
            name="average sword",
            known=False,
            is_equipment=True,
            pseudo_feeling="average",
        )
        identify_scroll = item(
            "i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, identify_scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)

        self.assertNotEqual(policy.choose_key(snap), "ria")
        self.assertNotEqual(policy.last_reason, "identify:normal")

    def test_identification_prefers_charged_staff_over_scroll(self):
        target = item(
            "a", 23, -1, aware=False, known=False, is_equipment=True
        )
        staff = item(
            "u", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=2, name="staff"
        )
        scroll = item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="scroll")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, staff, scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)
        # Original-keyset use-staff u, then staff slot u and target slot a.
        self.assertEqual(policy.choose_key(snap), "uua")
        self.assertEqual(policy.last_reason, "identify:normal")

    def test_identifies_an_unknown_wand_in_town(self):
        wand = item("a", TVAL_WAND, -1, aware=False, known=False, name="unknown wand")
        scroll = item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[wand, scroll],
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "ria")
        self.assertEqual(policy.last_reason, "identify:device")

    def test_identifies_wanted_unknown_jewelry_directly_from_pack_in_town(self):
        ring = item(
            "a",
            TVAL_RING,
            -1,
            name="unknown ring",
            aware=False,
            known=False,
            is_equipment=True,
        )
        staff = item(
            "u", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=2, name="staff"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[ring, staff],
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "uua")
        self.assertEqual(policy.last_reason, "identify:normal")

    def test_defers_unknown_device_when_identification_is_unavailable(self):
        wand = item("a", TVAL_WAND, -1, aware=False, known=False, name="unknown wand")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[wand],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        policy._town_store_attempted[STORE_ALCHEMIST] = 0

        policy.choose_key(snap)
        self.assertIn(policy._item_signature(wand), policy._deferred_device_items)
        self.assertNotEqual(policy._next_required_store_type(snap), STORE_ALCHEMIST)

    def test_magic_shop_sells_nonessential_devices(self):
        for device in (
            item("a", TVAL_WAND, 1, charges=8, name="wand"),
            item("a", TVAL_STAFF, 1, charges=8, name="staff"),
        ):
            with self.subTest(tval=device.tval):
                snap = Snapshot(
                    player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                    {Position(10, 10): grid(10, 10)},
                    [],
                    inventory=[device],
                    store=StoreState(store_type=STORE_MAGIC, items=[]),
                    town_flag=True,
                )
                policy = HengbotPolicy()
                self.assertEqual(policy.choose_key(snap), "da\r")
                self.assertEqual(policy.last_reason, "shop:sell-device")

    def test_magic_shop_sells_device_pile_with_quantity_and_confirmation(self):
        device = item(
            "j", TVAL_WAND, 1, charges=9, count=3, name="pile of wands"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[device],
            store=StoreState(store_type=STORE_MAGIC, items=[]),
            town_flag=True,
        )

        self.assertEqual(HengbotPolicy().choose_key(snap), "dj3\ry")

    def test_single_device_sale_has_no_trailing_yes(self):
        device = item("j", TVAL_WAND, 1, charges=3, name="wand")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[device],
            store=StoreState(store_type=STORE_MAGIC, items=[]),
            town_flag=True,
        )

        self.assertEqual(HengbotPolicy().choose_key(snap), "dj\r")

    def test_pile_sale_quantity_is_capped_by_retention_surplus(self):
        pile = item("j", TVAL_FOOD, FOOD_MIN_SVAL, count=3, name="rations")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[pile],
            store=StoreState(store_type=STORE_GENERAL, items=[]),
            town_flag=True,
        )
        policy = HengbotPolicy()

        with patch.object(policy, "_retention_reservation", return_value=1):
            self.assertEqual(
                policy._store_sell_key(snap, pile, "shop:sell-food"),
                "dj2\ry",
            )

    def test_batch_sale_inscribes_then_sells_by_stable_tags(self):
        candidates = [
            item("x", TVAL_WAND, 1, count=1, name="one"),
            item("y", TVAL_WAND, 2, count=4, name="four"),
            item("z", TVAL_WAND, 3, count=2, name="two"),
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=candidates,
            store=StoreState(store_type=STORE_MAGIC, items=[]), town_flag=True,
        )
        policy = HengbotPolicy()
        with patch.object(policy, "_current_store_sale_candidates", return_value=candidates), patch.object(
            policy, "_retention_surplus", side_effect=lambda snapshot, target: target.count
        ):
            self.assertEqual(policy._batch_sell_key(snap), "{x@0\r{y@1\r{z@2\r")
            self.assertEqual(policy._batch_sell_key(snap), "d0\rd199\ryd299\ry")

    def test_batch_sale_reuses_an_existing_exact_tag(self):
        candidates = [
            replace(item("x", TVAL_WAND, 1, name="one"), inscription="{@0}"),
            item("y", TVAL_WAND, 2, name="two"),
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=candidates,
            store=StoreState(store_type=STORE_MAGIC, items=[]), town_flag=True,
        )
        policy = HengbotPolicy()
        with patch.object(policy, "_current_store_sale_candidates", return_value=candidates), patch.object(
            policy, "_retention_surplus", return_value=1
        ):
            self.assertEqual(policy._batch_sell_key(snap), "{y@1\r")

    def test_batch_straggler_advances_attempt_and_does_not_rebatch(self):
        candidates = [
            item("x", TVAL_WAND, 1, name="one"),
            item("y", TVAL_WAND, 2, name="two"),
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=candidates,
            store=StoreState(store_type=STORE_MAGIC, items=[]), town_flag=True,
        )
        policy = HengbotPolicy()
        with patch.object(policy, "_current_store_sale_candidates", return_value=candidates), patch.object(
            policy, "_retention_surplus", return_value=1
        ):
            policy._batch_sell_key(snap)
            policy._batch_sell_key(snap)
            remaining = replace(snap, inventory=[candidates[1]])
            self.assertIsNone(policy._batch_sell_key(remaining))
            self.assertEqual(policy._store_sell_attempt[0], policy._item_signature(candidates[1]))
            self.assertIn(STORE_MAGIC, policy._batch_sell_attempted)
            self.assertIsNone(policy._batch_sell_key(remaining))

    def test_nonpositive_surplus_sells_the_whole_offered_pile(self):
        pile = item("j", TVAL_WAND, 1, count=3, name="pile")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=[pile],
            store=StoreState(store_type=STORE_MAGIC, items=[]), town_flag=True,
        )
        policy = HengbotPolicy()
        with patch.object(policy, "_retention_surplus", return_value=0):
            self.assertEqual(policy._store_sell_key(snap, pile, "shop:sell"), "dj3\ry")

    def test_keeps_useful_devices(self):
        devices = [
            item("a", TVAL_WAND, 3, charges=2, name="Teleport Away"),
            item("b", TVAL_WAND, 6, charges=2, name="Stone to Mud"),
            item("c", TVAL_STAFF, 5, charges=2, name="Identify"),
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=devices,
            store=StoreState(store_type=STORE_MAGIC, items=[]),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertIsNone(policy._find_device_sale(snap))

    def test_mana_race_keeps_highest_charge_wand_and_sells_other_devices(self):
        devices = [
            item("a", TVAL_WAND, 1, charges=3, name="small wand"),
            item("b", TVAL_WAND, 2, charges=9, name="large wand"),
            item("c", TVAL_STAFF, 1, charges=20, name="staff"),
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=devices,
            store=StoreState(store_type=STORE_MAGIC, items=[]),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._device_food_reserve_slot(snap), "b")
        self.assertEqual(policy._find_device_sale(snap).slot, "a")

    def test_mana_race_keeps_highest_staff_only_without_wands(self):
        devices = [
            item("a", TVAL_STAFF, 1, charges=3, name="small staff"),
            item("b", TVAL_STAFF, 2, charges=9, name="large staff"),
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=devices,
            store=StoreState(store_type=STORE_MAGIC, items=[]),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._device_food_reserve_slot(snap), "b")
        self.assertEqual(policy._find_device_sale(snap).slot, "a")

    def test_ego_item_requires_star_identify_after_normal_identification(self):
        target = item(
            "a",
            23,
            1,
            name="ego sword",
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, star_scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)
        self.assertEqual(policy.choose_key(snap), "rsa")
        self.assertEqual(policy.last_reason, "identify:full")

    def test_known_cursed_ego_skips_star_identify(self):
        target = item(
            "a", 23, 1, name="cursed ego sword", known=True,
            fully_known=False, is_equipment=True, is_ego=True, is_cursed=True,
        )
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, star_scroll],
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)

        self.assertIsNone(policy._town_item_processing_key(snap))

    def test_known_cursed_ego_is_selected_for_sale(self):
        target = item(
            "a", 23, 1, name="cursed ego sword", known=True,
            fully_known=False, is_equipment=True, is_ego=True, is_cursed=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target],
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._find_low_level_sale(snap), target)

    def test_cursed_artifact_still_requires_star_identify(self):
        target = item(
            "a", 23, 1, name="cursed artifact sword", known=True,
            fully_known=False, is_equipment=True, is_artifact=True, is_cursed=True,
        )
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, star_scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)

        self.assertEqual(policy.choose_key(snap), "rsa")
        self.assertEqual(policy.last_reason, "identify:full")

    def test_pseudo_cursed_unknown_item_still_gets_basic_identify(self):
        target = item(
            "a", 23, 1, name="cursed-feeling sword", known=False,
            fully_known=False, is_equipment=True, pseudo_feeling="cursed",
        )
        scroll = item("s", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="identify")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)

        self.assertEqual(policy.choose_key(snap), "rsa")
        self.assertEqual(policy.last_reason, "identify:normal")

    def test_dragon_helm_requires_star_identify_for_random_resistance(self):
        target = item(
            "a",
            32,
            7,
            name="dragon helm",
            known=True,
            fully_known=False,
            is_equipment=True,
        )
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, star_scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)

        self.assertEqual(policy.choose_key(snap), "rsa")
        self.assertEqual(policy.last_reason, "identify:full")

    def test_equipped_dragon_helm_is_fully_identified_in_place(self):
        helm = item(
            "head",
            32,
            7,
            name="dragon helm",
            known=True,
            fully_known=False,
            is_equipment=True,
        )
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[star_scroll],
            equipment=[helm, self._lantern()],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "rs/j")
        self.assertEqual(policy.last_reason, "identify:full-equipped")

    def test_equipped_unidentified_weapon_is_identified_in_place(self):
        # Regression for the 2026-07-15 incident: the live deadlock's dominant
        # optimizer blocker was an EQUIPPED, unidentified (known=False) Bastard
        # Sword (pseudo_feeling "good"). The equipment optimizer counts a worn
        # known=False item as identification_incomplete unless it is merely
        # pseudo "average", but _town_equipped_identification_key required
        # known=True (full-ID only) -- no town handler would touch this item,
        # so the bot held an Identify scroll it never applied.
        weapon = item(
            "main_hand",
            23,
            1,
            name="unidentified sword",
            known=False,
            pseudo_feeling="good",
            is_equipment=True,
        )
        scroll = item("s", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="identify")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[scroll],
            equipment=[weapon, self._lantern()],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "rs/a")
        self.assertEqual(policy.last_reason, "identify:normal-equipped")

    def test_equipped_unidentified_weapon_without_source_routes_to_buy_identify(self):
        # The incident state: a worn, unidentified weapon and no identify
        # source in the pack. The decision must not fall through to town
        # wander -- it registers the need (mirroring the known=True/full-ID
        # path) so the existing buy-identify errand routes to the Alchemist.
        weapon = item(
            "main_hand",
            23,
            1,
            name="unidentified sword",
            known=False,
            pseudo_feeling="good",
            is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[],
            equipment=[weapon, self._lantern()],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertIsNone(policy._town_equipped_identification_key(snap))
        self.assertEqual(policy._identification_need, "normal")
        self.assertEqual(
            policy._identification_candidate, policy._item_signature(weapon)
        )
        self.assertEqual(policy._next_required_store_type(snap), STORE_ALCHEMIST)

    def test_identified_ego_is_tracked_after_scroll_shifts_its_slot(self):
        unknown_signature = ("unknown war hammer", 22, 12)
        target = item(
            "k",
            22,
            12,
            name="ego war hammer",
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        shifted_into_old_slot = item(
            "l", 20, 1, name="shovel", is_equipment=True
        )
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, shifted_into_old_slot, star_scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = unknown_signature
        policy._home_pending_slot = "l"

        self.assertEqual(policy.choose_key(snap), "rsk")
        self.assertEqual(policy.last_reason, "identify:full")
        self.assertEqual(policy._home_pending_slot, "k")

    def test_buys_missing_star_identify_before_processing_ego(self):
        target = item(
            "a",
            23,
            1,
            name="ego sword",
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        snap = Snapshot(
            player(10, 10, gold=5000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target],
            equipment=[self._lantern()],
            store=StoreState(
                store_type=STORE_ALCHEMIST,
                items=[
                    store_item(
                        "b",
                        TVAL_SCROLL,
                        SV_SCROLL_STAR_IDENTIFY,
                        price=500,
                    )
                ],
            ),
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)
        policy._identification_need = "full"
        self.assertEqual(policy.choose_key(snap), "pb\r")
        self.assertEqual(policy.last_reason, "shop:buy-star-identify")

    def test_complete_armour_waits_for_global_loadout_optimization(self):
        current = item(
            "body",
            36,
            1,
            name="old armour",
            fully_known=True,
            is_equipment=True,
            ac=5,
            to_a=2,
            known_flags=frozenset({10}),
        )
        candidate = item(
            "a",
            37,
            1,
            name="new armour",
            fully_known=True,
            is_equipment=True,
            ac=8,
            to_a=3,
            known_flags=frozenset({10, 11}),
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[candidate],
            equipment=[current, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(candidate)
        self.assertIsNone(policy._town_item_processing_key(snap))
        self.assertIsNone(policy._home_pending_item)
        self.assertNotEqual(policy.last_reason, "equipment:equip-dominating-upgrade")

    def test_legacy_armour_comparison_does_not_bypass_r1_catalog_proof(self):
        superior = item(
            "body",
            36,
            1,
            fully_known=True,
            is_equipment=True,
            ac=10,
            to_a=5,
            known_flags=frozenset({10}),
        )
        inferior = item(
            "a", 37, 1, known=True, is_equipment=True, ac=5, to_a=1
        )
        protected = item(
            "b",
            37,
            1,
            known=True,
            fully_known=True,
            is_equipment=True,
            is_artifact=True,
            ac=1,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[inferior, protected],
            equipment=[superior, self._lantern()],
        )
        policy = HengbotPolicy()
        self.assertFalse(policy._is_disposable_dominated_armour(snap, inferior))
        self.assertFalse(policy._is_disposable_dominated_armour(snap, protected))

    def test_weapon_is_not_disposed_by_armour_dominance_rule(self):
        superior = item(
            "main_hand", 23, 1, known=True, is_equipment=True, pval=2
        )
        inferior = item("a", 23, 2, known=True, is_equipment=True)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[inferior],
            equipment=[superior, self._lantern()],
        )

        self.assertFalse(
            HengbotPolicy()._is_disposable_dominated_armour(snap, inferior)
        )

    def test_pseudo_average_armour_is_never_disposable(self):
        superior = item(
            "body", 37, 1, known=True, fully_known=True,
            is_equipment=True, ac=5, to_a=3,
        )
        same_base = item(
            "a", 37, 1, known=False, is_equipment=True,
            pseudo_feeling="average",
        )
        different_base = replace(same_base, slot="b", sval=2)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[same_base, different_base],
            equipment=[superior, self._lantern()],
        )
        policy = HengbotPolicy()

        self.assertFalse(
            policy._is_disposable_dominated_armour(snap, same_base)
        )
        self.assertFalse(
            policy._is_disposable_dominated_armour(snap, different_base)
        )

    def test_withdraws_dominated_mundane_armour_from_home_for_sale(self):
        superior = store_item(
            "a", 37, 1, name="superior armour", known=True,
            fully_known=True, is_equipment=True, ac=10, to_a=5,
        )
        inferior = store_item(
            "b", 37, 1, name="inferior armour", known=True,
            fully_known=True, is_equipment=True, ac=5, to_a=1,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            equipment=[self._lantern()],
            store=StoreState(store_type=STORE_HOME, items=[superior, inferior]),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.observe_home_page(snap.store.items)
        policy._home_disposal_pass = True

        self.assertEqual(policy.choose_key(snap), "pb\r")
        self.assertEqual(policy.last_reason, "home:withdraw-dominated")
        self.assertEqual(
            policy._pending_disposal_item, policy._item_signature(inferior)
        )

        withdrawn = item(
            "c", 37, 1, name="inferior armour", known=True,
            fully_known=True, is_equipment=True, ac=5, to_a=1,
        )
        after = replace(snap, inventory=[withdrawn], store=replace(snap.store, items=[superior]))
        self.assertEqual(policy.choose_key(after), "\x1b")
        self.assertEqual(policy.last_reason, "home:leave-with-dominated")

    def test_sells_dominated_armour_at_armoury(self):
        inferior = item("a", 37, 1, known=True, is_equipment=True, ac=1)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[inferior],
            equipment=[self._lantern()],
            store=StoreState(store_type=STORE_ARMOURY, items=[]),
        )
        policy = HengbotPolicy()
        policy._pending_disposal_slot = "a"
        policy._pending_disposal_item = policy._item_signature(inferior)
        self.assertEqual(policy.choose_key(snap), "da\r")
        self.assertEqual(policy.last_reason, "equipment:sell-dominated")

    def test_destroys_dominated_armour_after_armoury_refuses(self):
        inferior = item("a", 37, 1, known=True, is_equipment=True, ac=1)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[inferior],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._pending_disposal_slot = "a"
        policy._pending_disposal_item = policy._item_signature(inferior)
        policy._disposal_store_attempts.add(STORE_ARMOURY)
        self.assertEqual(policy.choose_key(snap), "01ka")
        self.assertEqual(
            policy.last_reason, "equipment:destroy-unsellable-dominated"
        )


class TownMapNightRoutingTest(unittest.TestCase):
    def _outpost(self):
        from hengbot.town_maps import find_outpost_map, parse_town_map

        path = find_outpost_map(Path(__file__).resolve().parent.parent)
        if path is None:
            self.skipTest("Outpost map not found")
        return parse_town_map(path)

    def _night_snapshot(self, town_map):
        # Night in the Outpost: only the player's small light radius and the
        # REMEMBER-marked store entrances are emitted; the long route between is
        # dark (absent from the snapshot).
        grids = {}
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                p = Position(31 + dy, 150 + dx)
                grids[p] = grid(p.y, p.x)
        for store_type, pos in town_map.stores.items():
            grids[pos] = GridState(
                position=pos, known=True, passable=True, wall=False,
                has_monster=False, has_down_stairs=False, has_up_stairs=False,
                unsafe=False, store_number=store_type,
            )
        return Snapshot(
            player(31, 150, hp=139, max_hp=139, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(0, 0, 0),
            width=town_map.width,
            height=town_map.height,
            town_flag=True,
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)
            ],
        )

    def test_static_map_lets_the_bot_route_to_a_store_at_night(self):
        town_map = self._outpost()
        snap = self._night_snapshot(town_map)
        # Without the static map the dark gap is un-routable → it explores/wanders.
        without = HengbotPolicy(town_map=None)
        without.choose_key(snap)
        self.assertNotEqual(without.last_reason, "shop:approach")
        # With it, the bot uses the store landmark for native travel.
        with_map = HengbotPolicy(town_map=town_map)
        self.assertEqual(with_map.choose_key(snap), "\x1b`n(.")
        self.assertEqual(with_map.last_reason, "shop:travel")


class WildernessSafetyTest(unittest.TestCase):
    def _wild_grids(self):
        return {Position(10, x): grid(10, x) for x in range(8, 13)}

    def test_open_wilderness_detected_from_the_town_flag(self):
        snap = Snapshot(
            player(10, 10), self._wild_grids(), [], floor_key=(0, 0, 0), town_flag=False
        )
        self.assertFalse(snap.in_town)
        self.assertTrue(snap.on_open_wilderness)

    def test_town_flag_true_is_in_town_not_wilderness(self):
        snap = Snapshot(
            player(10, 10), self._wild_grids(), [], floor_key=(0, 0, 0), town_flag=True
        )
        self.assertTrue(snap.in_town)
        self.assertFalse(snap.on_open_wilderness)

    def test_town_pathfinding_rejects_an_ordinary_border_exit(self):
        grids = {
            Position(y, x): grid(y, x)
            for y in range(3)
            for x in range(1, 4)
        }
        snap = Snapshot(
            player(1, 2),
            grids,
            [],
            floor_key=(0, 0, 0),
            width=5,
            height=5,
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snap)

        self.assertNotIn(Position(0, 1), policy._walkable_neighbors(snap, snap.player.position))

    def test_town_pathfinding_allows_a_border_dungeon_entrance(self):
        grids = {
            Position(1, 2): grid(1, 2),
            Position(0, 1): grid(0, 1, entrance=True),
        }
        snap = Snapshot(
            player(1, 2),
            grids,
            [],
            floor_key=(0, 0, 0),
            width=5,
            height=5,
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snap)

        self.assertIn(Position(0, 1), policy._walkable_neighbors(snap, snap.player.position))

    def test_legacy_snapshot_without_flag_uses_the_surface_heuristic(self):
        # town_flag None (older emitter) → the (0,0) surface is treated as town.
        snap = Snapshot(player(10, 10), self._wild_grids(), [], floor_key=(0, 0, 0))
        self.assertTrue(snap.in_town)
        self.assertFalse(snap.on_open_wilderness)

    def test_flees_a_wilderness_monster_instead_of_fighting(self):
        grids = self._wild_grids()
        grids[Position(10, 11)] = grid(10, 11, monster=True)
        mon = hostile(1, 10, 11, hp=40, max_hp=40)
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            grids,
            [mon],
            floor_key=(0, 0, 0),
            town_flag=False,
        )
        pol = HengbotPolicy()
        key = pol.choose_key(snap)
        self.assertEqual(pol.last_reason, "wilderness:flee")
        self.assertNotEqual(key, "6")  # never step east INTO the adjacent monster

    def test_recalls_off_the_wilderness_when_safe(self):
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            self._wild_grids(),
            [],
            floor_key=(0, 0, 0),
            town_flag=False,
            inventory=[recall],
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "rr")  # read Word of Recall at slot r
        self.assertEqual(pol.last_reason, "wilderness:recall")

    def test_town_wander_never_steps_onto_the_border_ring(self):
        # A small walled town; from an interior tile the least-visited-neighbour
        # wander must pick an interior tile, never a border tile (which would exit
        # into the open wilderness).
        grids = {}
        for y in range(0, 5):
            for x in range(0, 7):
                grids[Position(y, x)] = grid(y, x)
        snap = Snapshot(
            player(2, 1), grids, [], floor_key=(0, 0, 0), width=7, height=5, town_flag=True
        )
        pol = HengbotPolicy()
        pol._build_grid_index(snap)
        pol._observe(snap)
        step = pol._least_visited_neighbor(snap)
        self.assertIsNotNone(step)
        self.assertFalse(
            pol._on_town_border(snap, step), f"wandered onto border tile {step}"
        )

    def test_on_town_border_only_flags_the_ring_in_a_town(self):
        grids = {Position(0, 0): grid(0, 0)}
        town = Snapshot(
            player(2, 2), grids, [], floor_key=(0, 0, 0), width=7, height=5, town_flag=True
        )
        pol = HengbotPolicy()
        self.assertTrue(pol._on_town_border(town, Position(0, 3)))  # top edge
        self.assertTrue(pol._on_town_border(town, Position(4, 3)))  # bottom edge
        self.assertTrue(pol._on_town_border(town, Position(2, 6)))  # right edge
        self.assertFalse(pol._on_town_border(town, Position(2, 3)))  # interior
        # Not a town → the ring is not special (dungeons have their own walls).
        dungeon = Snapshot(
            player(2, 2), grids, [], floor_key=(1, 5, 0), width=7, height=5
        )
        self.assertFalse(pol._on_town_border(dungeon, Position(0, 3)))

    def test_does_not_shop_or_explore_on_the_wilderness(self):
        # A store tile is visible but we are on an open wilderness tile, not the
        # town — survival overrides the town shopping routine.
        grids = self._wild_grids()
        grids[Position(10, 12)] = GridState(
            position=Position(10, 12), known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_GENERAL,
        )
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100, gold=1000),
            grids,
            [],
            floor_key=(0, 0, 0),
            town_flag=False,
        )
        pol = HengbotPolicy()
        pol.choose_key(snap)
        self.assertTrue(pol.last_reason.startswith("wilderness"), pol.last_reason)



class TownRecallReturnTest(unittest.TestCase):
    def _ready_town(
        self, deepest, target, recall_dungeon, angband_unlocked=False, recall_depth=0
    ):
        inv = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
            item("t", TVAL_SCROLL, 9, count=9),  # teleport
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            item("c", TVAL_POTION, 36, count=9),  # cure critical
        ]
        snap = Snapshot(
            player(10, 10, hp=255, max_hp=255, gold=2000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            width=198,
            height=66,
            town_flag=True,
            inventory=inv,
            equipment=[item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)],
            recall_dungeon_id=recall_dungeon,
            recall_depth=recall_depth,
            angband_recall_unlocked=angband_unlocked,
        )
        pol = HengbotPolicy()
        pol._deepest_level = deepest
        pol._target_dungeon_id = target
        pol._char_dump_done_this_visit = True  # past the pre-dive dump for recall tests
        return pol, snap

    def test_writes_a_character_dump_before_the_first_recall_of_a_visit(self):
        pol, snap = self._ready_town(8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True)
        pol._char_dump_done_this_visit = False  # a fresh town visit
        self.assertEqual(pol._town_special_key(snap), CHARACTER_DUMP_MACRO)
        self.assertEqual(pol.last_reason, "town:character-dump")
        # Dump written -> the very next decision commits to the recall.
        self.assertEqual(pol._town_special_key(snap), "rra")
        self.assertEqual(pol.last_reason, "town:recall-to-angband")

    def test_periodic_dump_waits_for_quiet_exploration_and_emits_once(self):
        pol = HengbotPolicy()
        quiet = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 5, 0),
        )
        pol.request_character_dump()
        pol.last_reason = "melee"
        self.assertEqual(pol._periodic_character_dump_key(quiet, "6"), "6")
        pol.last_reason = "explore"
        self.assertEqual(
            pol._periodic_character_dump_key(quiet, "6"), CHARACTER_DUMP_MACRO
        )
        pol.last_reason = "explore"
        self.assertEqual(pol._periodic_character_dump_key(quiet, "6"), "6")

    def test_periodic_dump_never_emits_in_store_or_adjacent_combat(self):
        enemy = hostile(1, 10, 11)
        combat = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, monster=True),
            },
            [enemy],
            floor_key=(1, 5, 0),
        )
        town = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )[1]
        store = replace(town, store=StoreState(STORE_GENERAL, []))
        for snapshot in (combat, store):
            pol = HengbotPolicy()
            pol.request_character_dump()
            pol.last_reason = "explore"
            self.assertEqual(pol._periodic_character_dump_key(snapshot, "6"), "6")

    def test_recall_depth_seeds_deepest_after_restart(self):
        # A restart zeroes the in-memory watermark. The save-backed recall depth
        # (emitted every snapshot) must restore it, or the resumed bot forgets it
        # has been to 5F and walks in from the entrance instead of recalling.
        pol, snap = self._ready_town(
            0, DUNGEON_YEEK_CAVE, DUNGEON_YEEK_CAVE, recall_depth=RECALL_MIN_DEPTH
        )
        pol._observe(snap)
        self.assertGreaterEqual(pol._deepest_level, RECALL_MIN_DEPTH)
        self.assertEqual(pol._town_special_key(snap), "rra")
        self.assertEqual(pol.last_reason, "town:recall-to-yeek-cave")

    def test_recall_depth_only_raises_never_lowers_watermark(self):
        # recall_depth seeds via max(): a deeper in-session watermark still wins,
        # so a stale/smaller recall_depth never demotes a genuinely deep run.
        pol, snap = self._ready_town(
            8, DUNGEON_YEEK_CAVE, DUNGEON_YEEK_CAVE, recall_depth=3
        )
        pol._observe(snap)
        self.assertEqual(pol._deepest_level, 8)

    def test_recalls_into_a_deep_yeek_cave_run(self):
        pol, snap = self._ready_town(RECALL_MIN_DEPTH, DUNGEON_YEEK_CAVE, DUNGEON_YEEK_CAVE)
        self.assertEqual(pol._town_special_key(snap), "rra")
        self.assertEqual(pol.last_reason, "town:recall-to-yeek-cave")

    def test_shallow_run_walks_to_the_entrance_not_recall(self):
        pol, snap = self._ready_town(RECALL_MIN_DEPTH - 1, DUNGEON_YEEK_CAVE, DUNGEON_YEEK_CAVE)
        self.assertIsNone(pol._town_special_key(snap))

    def test_recalls_to_angband_once_unlocked(self):
        pol, snap = self._ready_town(8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True)
        self.assertEqual(pol._town_special_key(snap), "rra")
        self.assertEqual(pol.last_reason, "town:recall-to-angband")

    def test_departure_block_telemetry_names_failed_gate_and_values(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        pol._town_departure_ready = lambda _snapshot: False

        self.assertIsNone(pol._town_special_key(snap))
        block = pol.departure_block_state()
        self.assertEqual(block["gate"], "town_departure_ready")
        self.assertIn("town_departure_ready", block["failed"])
        self.assertFalse(block["values"]["town_departure_ready"])
        self.assertEqual(
            block["values"]["free_pack_slots"], PACK_CAPACITY - len(snap.inventory)
        )

    def test_inert_home_identification_latch_is_cleared_before_recall(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        pol._home_pending_item = ("stale", 23, 99)
        pol._identification_need = "stale-home-item"
        pol._identification_candidate = ("stale", 23, 99)
        pol._home_candidate_waiting = False

        self.assertEqual(
            pol._town_special_key(snap), "rra",
            (pol.last_reason, pol.departure_block_state()),
        )
        self.assertIsNone(pol._home_pending_item)
        self.assertIsNone(pol._identification_need)

    def test_active_home_latch_is_retained_and_blocks_recall(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        pending = replace(
            item("b", 23, 8, known=True, is_equipment=True, name="pending sword"),
            damage_dice_num=2, damage_dice_sides=5, weight=80,
        )
        snap = replace(snap, inventory=[*snap.inventory, pending])
        signature = pol._item_signature(pending)
        pol._home_pending_item = signature

        self.assertNotEqual(pol._town_special_key(snap), "rra")
        self.assertEqual(pol._home_pending_item, signature)

    def test_fundraising_keeps_walking_to_mine_level_one(self):
        pol, snap = self._ready_town(8, DUNGEON_YEEK_CAVE, DUNGEON_YEEK_CAVE)
        pol._fundraising_mode = "mine"
        self.assertNotEqual(pol._town_special_key(snap), "rr")

    def test_deep_run_drops_the_town_entrance_as_a_descent_goal(self):
        entrance = GridState(
            position=Position(10, 10), known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, has_entrance=True, entrance_dungeon_id=DUNGEON_YEEK_CAVE,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): entrance}, [], floor_key=(0, 0, 0), town_flag=True,
        )
        pol = HengbotPolicy()
        pol._target_dungeon_id = DUNGEON_YEEK_CAVE
        pol._deepest_level = RECALL_MIN_DEPTH
        self.assertFalse(pol._is_descent_target(snap, entrance))  # deep -> recall
        pol._deepest_level = RECALL_MIN_DEPTH - 1
        self.assertTrue(pol._is_descent_target(snap, entrance))  # shallow -> walk

    @staticmethod
    def _q14(status):
        info = QuestInfo(
            14, "Warg Problem", 1, 5, 2, dungeon=DUNGEON_YEEK_CAVE,
            max_num=1, monrace_id=257,
        )
        quest = QuestState(
            id=14, status=status, type=1, level=5,
            dungeon_id=DUNGEON_YEEK_CAVE, fixed=True,
        )
        return info, quest

    def _q14_floor(self, status, depth):
        info, quest = self._q14(status)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [], floor_key=(DUNGEON_YEEK_CAVE, depth, 0),
            quests={14: quest}, entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
        )
        return HengbotPolicy(quest_knowledge={14: info}), snap

    def _exhausted_q14_floor(self, status, depth, *, cur_num=14):
        info, quest = self._q14(status)
        info = replace(info, max_num=16)
        quest = replace(quest, cur_num=cur_num, max_num=16)
        here = grid(10, 10, upstairs=True, downstairs=True)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): here}, [],
            floor_key=(DUNGEON_YEEK_CAVE, depth, 0), quests={14: quest},
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
        )
        pol = HengbotPolicy(quest_knowledge={14: info})
        pol._explore_step = lambda _snapshot: None
        pol._is_frontier = lambda *_args: False
        return pol, snap

    def test_q14_completed_in_dungeon_reads_recall_to_claim(self):
        policy, snapshot = self._q14_floor(QUEST_STATUS_COMPLETED, 5)
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snapshot = replace(snapshot, inventory=[recall])

        self.assertEqual(policy.choose_key(snapshot), "rr")
        self.assertEqual(policy.last_reason, "fixedquest:claim:return")

    def test_q14_completed_in_dungeon_fights_adjacent_hostile_before_recall(self):
        policy, snapshot = self._q14_floor(QUEST_STATUS_COMPLETED, 5)
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        hostile = MonsterState(
            1, Position(10, 11), 1, 1, 1, False, False, race_id=257,
        )
        snapshot = replace(
            snapshot,
            inventory=[recall],
            grids={
                **snapshot.grids,
                Position(10, 11): grid(10, 11, monster=True),
            },
            visible_monsters=[hostile],
        )

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "melee")

    def test_q14_completed_in_dungeon_without_recall_steers_upstairs(self):
        policy, snapshot = self._q14_floor(QUEST_STATUS_COMPLETED, 5)
        snapshot = replace(
            snapshot,
            grids={Position(10, 10): grid(10, 10, upstairs=True, downstairs=True)},
        )

        self.assertEqual(policy.choose_key(snapshot), "<")
        self.assertEqual(policy.last_reason, "fixedquest:claim:return")

    def test_q14_completed_in_dungeon_waits_for_pending_recall(self):
        policy, snapshot = self._q14_floor(QUEST_STATUS_COMPLETED, 5)
        snapshot = replace(snapshot, player=replace(snapshot.player, recalling=True))

        self.assertEqual(policy.choose_key(snapshot), "5")
        self.assertEqual(policy.last_reason, "return:wait-recall")

    def test_taken_q14_exhausted_floor_regenerates_up_instead_of_descending(self):
        pol, snap = self._exhausted_q14_floor(QUEST_STATUS_TAKEN, 5)
        self.assertEqual(pol.choose_key(snap), "<")
        self.assertEqual(pol.last_reason, "quest:regen:ascend")

    def test_untaken_q14_exhausted_floor_preserves_old_descend_fallback(self):
        pol, snap = self._exhausted_q14_floor(QUEST_STATUS_UNTAKEN, 8)
        pol._fixed_quest_key = lambda *_args: None
        snap = replace(snap, player=replace(snap.player, class_id=-1))
        self.assertEqual(pol.choose_key(snap), ">")
        self.assertEqual(pol.last_reason, "descend")

    def test_taken_q14_overshoot_recovers_up_across_multiple_floors(self):
        pol, snap = self._exhausted_q14_floor(QUEST_STATUS_TAKEN, 9)
        for depth in (9, 8, 7, 6):
            current = replace(snap, floor_key=(DUNGEON_YEEK_CAVE, depth, 0))
            self.assertFalse(
                pol._is_descent_target(
                    current, current.grid_at(current.player.position)
                )
            )
            self.assertEqual(pol.choose_key(current), "<")
            self.assertEqual(pol.last_reason, "quest:regen:ascend")
        objective = replace(snap, floor_key=(DUNGEON_YEEK_CAVE, 5, 0))
        self.assertFalse(pol._kill_quest_descent_allowed(objective))

    def test_taken_q14_regeneration_returns_down_then_resumes_hunt(self):
        pol, floor5 = self._exhausted_q14_floor(QUEST_STATUS_TAKEN, 5)
        self.assertEqual(pol.choose_key(floor5), "<")
        floor4 = replace(floor5, floor_key=(DUNGEON_YEEK_CAVE, 4, 0))
        self.assertEqual(pol.choose_key(floor4), ">")
        self.assertEqual(pol.last_reason, "quest:regen:descend")
        target = MonsterState(
            1, Position(10, 11), 1, 1, 1, False, False, race_id=257,
        )
        fresh = replace(
            floor5,
            grids={
                Position(10, 10): grid(10, 10, upstairs=True, downstairs=True),
                Position(10, 11): grid(10, 11, monster=True),
            },
            visible_monsters=[target],
        )
        self.assertNotIn(pol.choose_key(fresh), {"<", ">"})
        self.assertIn(pol.last_reason, {"melee", "ranged", "hunt"})

    def test_taken_q14_regeneration_stops_after_three_zero_kill_rounds(self):
        pol, floor5 = self._exhausted_q14_floor(QUEST_STATUS_TAKEN, 5)
        self.assertEqual(pol.choose_key(floor5), "<")
        for round_number in range(3):
            floor4 = replace(floor5, floor_key=(DUNGEON_YEEK_CAVE, 4, 0))
            self.assertEqual(pol.choose_key(floor4), ">")
            result = pol.choose_key(floor5)
            if round_number < 2:
                self.assertEqual(result, "<")
            else:
                self.assertEqual(result, "5")
                self.assertEqual(pol.last_reason, "quest:regen:exhausted")
        for _ in range(3):
            self.assertEqual(pol.choose_key(floor5), "5")
            self.assertEqual(pol.last_reason, "quest:regen:exhausted")

    def test_completed_q14_descent_predicates_and_regeneration_are_inert(self):
        completed, snap = self._exhausted_q14_floor(QUEST_STATUS_COMPLETED, 5)
        rewarded, baseline = self._exhausted_q14_floor(QUEST_STATUS_REWARDED, 5)
        completed._fixed_quest_key = lambda *_args: None

        self.assertTrue(completed._kill_quest_descent_allowed(snap))
        self.assertIsNone(completed._kill_quest_floor_recovery_key(snap))
        self.assertIsNone(completed._start_kill_quest_regeneration(snap))
        self.assertEqual(completed.choose_key(snap), rewarded.choose_key(baseline))

    def test_untaken_q14_below_objective_does_not_veto_descent(self):
        pol, snap = self._q14_floor(QUEST_STATUS_UNTAKEN, 8)
        self.assertTrue(pol._is_descent_target(snap, snap.grid_at(Position(10, 10))))

    def test_untaken_q14_shallow_steering_still_descends(self):
        pol, snap = self._q14_floor(QUEST_STATUS_UNTAKEN, 3)
        self.assertTrue(pol._is_descent_target(snap, snap.grid_at(Position(10, 10))))

    def test_taken_q14_objective_floor_vetoes_overshoot(self):
        pol, snap = self._q14_floor(QUEST_STATUS_TAKEN, 5)
        self.assertFalse(pol._is_descent_target(snap, snap.grid_at(Position(10, 10))))

    def test_rewarded_q14_does_not_veto_descent(self):
        pol, snap = self._q14_floor(QUEST_STATUS_REWARDED, 5)
        self.assertTrue(pol._is_descent_target(snap, snap.grid_at(Position(10, 10))))

    def test_taken_q14_deep_recall_uses_walk_in_entry(self):
        pol, snap = self._ready_town(
            8, DUNGEON_YEEK_CAVE, DUNGEON_YEEK_CAVE, recall_depth=8,
        )
        info, quest = self._q14(QUEST_STATUS_TAKEN)
        pol._quest_knowledge = {14: info}
        snap = replace(snap, quests={14: quest})
        entrance = GridState(
            position=Position(10, 11), known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, has_entrance=True,
            entrance_dungeon_id=DUNGEON_YEEK_CAVE,
        )

        self.assertIsNone(pol._town_special_key(snap))
        self.assertTrue(pol._is_descent_target(snap, entrance))
        at_entrance = replace(
            snap,
            player=replace(snap.player, position=entrance.position),
            grids={entrance.position: entrance},
        )
        self.assertEqual(pol.choose_key(at_entrance), ">\ry")
        self.assertEqual(pol.last_reason, "descend")



class OverExtensionDungeonSwitchTest(unittest.TestCase):
    # Angband is recommended for clvl 30+. A clvl-23 warrior dives it, collects
    # nothing (everything out-damages/out-runs it), and emergency-teleports out.
    # After a run of such empty dives the bot must recall into the deepest
    # already-unlocked dungeon its level can actually loot instead.
    ALL_ENTERED = (DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE, 3, 4, 7, 14)
    # Resistances covering the 20-25F (conf/fire) and 26-30F (pois/cold/elec/acid)
    # bands, so the Mountain (25F entry) counts as resistance-safe for these tests.
    MOUNTAIN_SAFE = frozenset(
        {"resist_conf", "resist_fire", "resist_pois", "resist_cold",
         "resist_elec", "resist_acid"}
    )

    def _dk(self):
        return {
            DUNGEON_ANGBAND: DungeonInfo(DUNGEON_ANGBAND, "Angband", 1, 127, 30),
            DUNGEON_YEEK_CAVE: DungeonInfo(DUNGEON_YEEK_CAVE, "Galgals", 1, 13, 1),
            3: DungeonInfo(3, "Orc Cave", 10, 22, 5),
            4: DungeonInfo(4, "Labyrinth", 10, 18, 1),
            7: DungeonInfo(7, "Forest", 15, 32, 5),
            14: DungeonInfo(14, "Mountain", 25, 45, 20),
        }

    def _policy(self):
        return HengbotPolicy(dungeon_knowledge=self._dk())

    # All conquerable-within-limit dungeons marked conquered, so the conquest-target
    # override stays out of the way and these tests isolate the over-extension switch.
    ALL_CONQUERED = (3, 4, 7, 14)

    def _town(
        self, *, clvl=23, recall_depth=26, entered=None, abilities=None,
        conquered=None, angband_unlocked=True,
    ):
        return Snapshot(
            player(10, 10, hp=255, max_hp=255, level=clvl, class_id=PLAYER_CLASS_WARRIOR,
                   abilities=self.MOUNTAIN_SAFE if abilities is None else abilities),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            recall_dungeon_id=DUNGEON_ANGBAND,
            recall_depth=recall_depth,
            entered_dungeon_ids=self.ALL_ENTERED if entered is None else entered,
            conquered_dungeon_ids=(
                self.ALL_CONQUERED if conquered is None else conquered
            ),
            angband_recall_unlocked=angband_unlocked,
        )

    def _dungeon(
        self, dungeon_id, level, *, clvl=23, recall_depth=26, abilities=None,
        conquered=None, angband_unlocked=True,
    ):
        return Snapshot(
            player(10, 10, hp=255, max_hp=255, level=clvl, class_id=PLAYER_CLASS_WARRIOR,
                   abilities=self.MOUNTAIN_SAFE if abilities is None else abilities),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(dungeon_id, level, 0),
            recall_dungeon_id=DUNGEON_ANGBAND,
            recall_depth=recall_depth,
            entered_dungeon_ids=self.ALL_ENTERED,
            conquered_dungeon_ids=(
                self.ALL_CONQUERED if conquered is None else conquered
            ),
            angband_recall_unlocked=angband_unlocked,
        )

    def _run_dive(
        self, pol, *, loot=0, emergencies=0, dungeon_id=DUNGEON_ANGBAND, level=26,
        clvl=23, recall_depth=26, abilities=None, conquered=None,
        angband_unlocked=True,
    ):
        dung = self._dungeon(
            dungeon_id, level, clvl=clvl, recall_depth=recall_depth,
            abilities=abilities, conquered=conquered,
            angband_unlocked=angband_unlocked,
        )
        pol.last_reason = "descend"
        pol._observe(dung)  # prev=town -> dive begins
        for _ in range(loot):
            pol.last_reason = "victory:pickup"
            pol._observe(dung)  # counts a pickup
        for _ in range(emergencies):
            pol.last_reason = "emergency:teleport"
            pol._observe(dung)  # counts an emergency escape
        pol.last_reason = "town:return"
        pol._observe(self._town(
            clvl=clvl, recall_depth=recall_depth, abilities=abilities,
            conquered=conquered, angband_unlocked=angband_unlocked,
        ))  # dive ends

    # An over-extended dive mirrors the real telemetry: one trivial pickup and a
    # run of emergency teleports that drain the escape kit.
    OVEREXTENDED = dict(loot=1, emergencies=3)

    # --- _pick_alternate_dungeon ------------------------------------------
    def test_picks_deepest_level_appropriate_shallower_dungeon(self):
        pol = self._policy()
        pol._last_overextended_depth = 26
        snap = self._town()
        # clvl 23: Mountain (25, minPLv 20) is the deepest we still qualify for.
        self.assertEqual(pol._pick_alternate_dungeon(snap), 14)

    def test_skips_a_dungeon_whose_entry_needs_a_missing_resistance(self):
        # The character lacks confusion resistance, so the Mountain (25F entry needs
        # it) is NOT resistance-safe — steer to a sub-20F dungeon with no requirement
        # (Forest 15F) rather than repeating the swarmed, zero-loot Mountain dive.
        pol = self._policy()
        pol._last_overextended_depth = 26
        snap = self._town(abilities=frozenset({"resist_fire", "resist_pois"}))  # no conf
        self.assertEqual(pol._pick_alternate_dungeon(snap), 7)  # Forest, not Mountain

    def test_steps_down_when_the_alternate_also_over_extends(self):
        pol = self._policy()
        pol._last_overextended_depth = 25  # Mountain came up empty too
        self.assertEqual(pol._pick_alternate_dungeon(self._town()), 7)  # Forest 15

    def test_never_re_picks_the_alternate_it_is_leaving(self):
        # Even if the bot descended past Mountain's entrance before giving up (so
        # the recorded depth exceeds Mountain's own minDepth), switching away from
        # Mountain must step DOWN, never back into Mountain.
        pol = self._policy()
        pol._alternate_dungeon = 14  # currently in Mountain, over-extended
        pol._last_overextended_depth = 30  # reached L30 there before bailing
        self.assertEqual(pol._pick_alternate_dungeon(self._town()), 7)  # Forest, not Mountain

    def test_skips_dungeons_above_the_characters_recommended_level(self):
        pol = self._policy()
        pol._last_overextended_depth = 26
        snap = self._town(clvl=3)  # too weak for Mountain(20), Orc(5), Forest(5)
        self.assertEqual(pol._pick_alternate_dungeon(snap), 4)  # Labyrinth minPLv 1

    def test_never_switches_to_angband_or_the_yeek_cave(self):
        pol = self._policy()
        pol._last_overextended_depth = 200
        # Only Angband and the fundraising Yeek Cave are unlocked -> no fallback.
        snap = self._town(entered=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE))
        self.assertIsNone(pol._pick_alternate_dungeon(snap))

    # --- _observe dive accounting -----------------------------------------
    def test_switches_after_a_run_of_over_extended_dives(self):
        pol = self._policy()
        for _ in range(EMPTY_DIVE_LIMIT):
            self._run_dive(pol, **self.OVEREXTENDED)
        self.assertEqual(pol._alternate_dungeon, 14)
        self.assertEqual(pol._target_dungeon_id, 14)

    def test_a_productive_dive_resets_the_streak(self):
        pol = self._policy()
        self._run_dive(pol, **self.OVEREXTENDED)
        self._run_dive(pol, **self.OVEREXTENDED)
        self._run_dive(pol, loot=3)  # a real haul resets the counter
        self.assertEqual(pol._target_empty_dives, 0)
        self._run_dive(pol, **self.OVEREXTENDED)
        self.assertIsNone(pol._alternate_dungeon)  # streak restarted, no switch yet

    def test_conquest_target_is_demoted_after_over_extended_dives(self):
        pol = self._policy()
        pol._target_dungeon_id = 7
        pol._conquest_committed = 7
        abilities = self.MOUNTAIN_SAFE | {"resist_chaos"}
        conquered = (3, 4, 14)

        for _ in range(EMPTY_DIVE_LIMIT):
            self._run_dive(
                pol, dungeon_id=7, level=32, recall_depth=32,
                abilities=abilities, conquered=conquered,
                angband_unlocked=False, **self.OVEREXTENDED,
            )

        self.assertEqual(pol._alternate_dungeon, 14)
        self.assertEqual(pol._target_dungeon_id, 14)
        self.assertIsNone(pol._conquest_committed)

    def test_conquest_target_can_return_after_alternate_period(self):
        pol = self._policy()
        pol._alternate_dungeon = 14
        pol._target_dungeon_id = 14
        abilities = self.MOUNTAIN_SAFE | {"resist_chaos"}
        snap = self._town(
            clvl=30, recall_depth=32, abilities=abilities,
            conquered=(3, 4, 14), angband_unlocked=False,
        )

        with patch.object(pol, "_guardian_fight_viable", return_value=True):
            pol._observe(snap)

        self.assertIsNone(pol._alternate_dungeon)
        self.assertEqual(pol._conquest_committed, 7)
        self.assertEqual(pol._target_dungeon_id, 7)

    def test_productive_conquest_dive_resets_streak_without_unlatching(self):
        pol = self._policy()
        pol._target_dungeon_id = 7
        pol._conquest_committed = 7
        pol._target_empty_dives = EMPTY_DIVE_LIMIT - 1
        abilities = self.MOUNTAIN_SAFE | {"resist_chaos"}

        self._run_dive(
            pol, dungeon_id=7, level=32, recall_depth=32,
            loot=OVEREXTEND_LOOT_MAX + 1, abilities=abilities,
            conquered=(3, 4, 14), angband_unlocked=False,
        )

        self.assertEqual(pol._target_empty_dives, 0)
        self.assertEqual(pol._conquest_committed, 7)
        self.assertIsNone(pol._alternate_dungeon)

    def test_a_dangerous_but_looted_dive_is_not_over_extended(self):
        # Bailing out repeatedly is fine as long as the pack came back full — that
        # is a hot dungeon we can still farm, not one too deep to loot.
        pol = self._policy()
        for _ in range(EMPTY_DIVE_LIMIT):
            self._run_dive(pol, loot=4, emergencies=3)
        self.assertEqual(pol._target_empty_dives, 0)
        self.assertIsNone(pol._alternate_dungeon)

    def test_a_quiet_empty_dive_without_danger_is_not_over_extended(self):
        # Zero loot but zero danger just means we found nothing — the character is
        # not out of its depth, so do not abandon the dungeon over bad luck.
        pol = self._policy()
        for _ in range(EMPTY_DIVE_LIMIT):
            self._run_dive(pol, loot=0, emergencies=0)
        self.assertEqual(pol._target_empty_dives, 0)
        self.assertIsNone(pol._alternate_dungeon)

    def test_a_single_emergency_does_not_flag_a_dive(self):
        pol = self._policy()
        for _ in range(EMPTY_DIVE_LIMIT):
            self._run_dive(pol, loot=0, emergencies=1)  # one escape is just a scare
        self.assertEqual(pol._target_empty_dives, 0)
        self.assertIsNone(pol._alternate_dungeon)

    def test_a_mild_unproductive_dive_holds_the_streak(self):
        # Live turn ~1213k: after two clearly over-extended dives, a 0-loot dive with
        # a single emergency must NOT reset the streak to zero (weak evidence), or
        # the switch could never accumulate; it holds until the next bad dive tips it.
        pol = self._policy()
        self._run_dive(pol, **self.OVEREXTENDED)      # streak 1
        self._run_dive(pol, **self.OVEREXTENDED)      # streak 2
        self._run_dive(pol, loot=0, emergencies=1)    # mild: HOLD at 2
        self.assertEqual(pol._target_empty_dives, 2)
        self.assertIsNone(pol._alternate_dungeon)
        self._run_dive(pol, **self.OVEREXTENDED)      # streak 3 -> switch
        self.assertEqual(pol._alternate_dungeon, 14)

    def test_only_a_profitable_dive_clears_the_streak(self):
        pol = self._policy()
        self._run_dive(pol, **self.OVEREXTENDED)      # streak 1
        self._run_dive(pol, loot=0, emergencies=0)    # quiet empty: HOLD at 1
        self.assertEqual(pol._target_empty_dives, 1)
        self._run_dive(pol, loot=5)                   # real haul: clears to 0
        self.assertEqual(pol._target_empty_dives, 0)

    def test_fundraising_yeek_cave_dives_do_not_count(self):
        pol = self._policy()
        pol._fundraising_mode = "mine"
        for _ in range(EMPTY_DIVE_LIMIT + 1):
            self._run_dive(pol, dungeon_id=DUNGEON_YEEK_CAVE, level=1, **self.OVEREXTENDED)
        self.assertEqual(pol._target_empty_dives, 0)
        self.assertIsNone(pol._alternate_dungeon)

    def test_returns_to_angband_once_strong_enough(self):
        pol = self._policy()
        pol._alternate_dungeon = 14
        pol._last_overextended_depth = 26
        pol._observe(self._town(clvl=30))  # reached Angband's recommended level
        self.assertIsNone(pol._alternate_dungeon)
        self.assertEqual(pol._target_dungeon_id, DUNGEON_ANGBAND)

    def test_stays_switched_while_still_under_levelled(self):
        pol = self._policy()
        pol._alternate_dungeon = 14
        pol._observe(self._town(clvl=29))  # one short of Angband's level
        self.assertEqual(pol._alternate_dungeon, 14)
        self.assertEqual(pol._target_dungeon_id, 14)

    # --- recall wiring ----------------------------------------------------
    def test_recall_targets_the_alternate_dungeon(self):
        inv = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=25),
            item("t", TVAL_SCROLL, 9, count=25),  # 10F+ kit wants a deep teleport stock
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            item("c", TVAL_POTION, 36, count=10),
            item("s", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=20),  # 25F run needs it
        ]
        snap = Snapshot(
            player(10, 10, hp=255, max_hp=255, level=23, gold=2000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            width=198,
            height=66,
            town_flag=True,
            inventory=inv,
            equipment=[item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)],
            recall_dungeon_id=14,
            recall_depth=25,
            entered_dungeon_ids=self.ALL_ENTERED,
            angband_recall_unlocked=True,
        )
        pol = self._policy()
        pol._deepest_level = 25
        pol._alternate_dungeon = 14
        pol._target_dungeon_id = 14
        pol._char_dump_done_this_visit = True  # past the pre-dive dump
        # Mountain is index 5 in ALL_ENTERED -> selection letter 'f'.
        self.assertEqual(pol._town_special_key(snap), "rrf")
        self.assertEqual(pol.last_reason, "town:recall-to-alt-dungeon")

    def test_alternate_dungeon_recall_keeps_dungeon_reserve_after_use(self):
        snap = self._town(clvl=23)
        snap = replace(
            snap,
            recall_dungeon_id=14,
            recall_depth=25,
            entered_dungeon_ids=self.ALL_ENTERED,
        )
        pol = self._policy()
        pol._deepest_level = 25
        pol._alternate_dungeon = 14
        pol._target_dungeon_id = 14

        reserve = pol._recall_target(pol._planned_depth())
        self.assertEqual(pol._recall_required_target(snap), reserve + 1)

    def test_alternate_dungeon_recall_never_bypasses_free_slot_requirement(self):
        inv = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=25),
            item("t", TVAL_SCROLL, 9, count=25),
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            item("c", TVAL_POTION, 36, count=9),
            item("s", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=20),
        ]
        inv.extend(
            item(chr(ord("a") + i), TVAL_STAFF, 20 + i, charges=1)
            for i in range(15)
        )
        snap = Snapshot(
            player(10, 10, hp=255, max_hp=255, level=23, gold=2000,
                   class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            width=198,
            height=66,
            town_flag=True,
            inventory=inv,
            equipment=[item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000,
                            is_equipment=True)],
            recall_dungeon_id=14,
            recall_depth=25,
            entered_dungeon_ids=self.ALL_ENTERED,
            angband_recall_unlocked=True,
        )
        pol = self._policy()
        pol._deepest_level = 25
        pol._alternate_dungeon = 14
        pol._target_dungeon_id = 14
        pol._char_dump_done_this_visit = True
        pol._shopping_stuck = True

        self.assertIsNone(pol._town_special_key(snap))
        self.assertNotEqual(pol.last_reason, "town:recall-to-alt-dungeon")



class EmergencyRecallEscapeTest(unittest.TestCase):
    def _swarm(self, inventory):
        grids = {}
        for y in range(9, 12):
            for x in range(43, 46):
                grids[Position(y, x)] = grid(y, x, monster=not (y == 10 and x == 44))
        adj = [(9, 43), (9, 44), (9, 45), (10, 43), (10, 45), (11, 43), (11, 44), (11, 45)]
        hostiles = [
            MonsterState(
                index=i, position=Position(y, x), hp=200, max_hp=200, distance=1,
                friendly=False, pet=False, speed=120, max_melee_damage=40,
            )
            for i, (y, x) in enumerate(adj, 1)
        ]
        return Snapshot(
            player(10, 44, hp=134, max_hp=255, class_id=PLAYER_CLASS_WARRIOR),
            grids, hostiles, floor_key=(2, 11, 0), width=100, height=100,
            inventory=inventory,
        )

    def test_recalls_when_teleport_scrolls_are_exhausted(self):
        # The dl11 swarm death: teleport/phase gone, seek-upstairs/wait had no
        # exit. Now it reads Word of Recall to start the escape home instead.
        snap = self._swarm([item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5)])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "rr")
        self.assertEqual(pol.last_reason, "emergency:recall")

    def test_prefers_teleport_over_recall_when_a_teleport_is_available(self):
        snap = self._swarm([
            item("t", TVAL_SCROLL, 9, count=3),  # teleport
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5),
        ])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "rt")
        self.assertEqual(pol.last_reason, "emergency:teleport")



class TownFrontierTest(unittest.TestCase):
    def _lone_town(self, town_map):
        snap = Snapshot(
            player(2, 2, class_id=PLAYER_CLASS_WARRIOR),
            {Position(2, 2): grid(2, 2)},
            [],
            floor_key=(0, 0, 0),
            width=7,
            height=5,
            town_flag=True,
        )
        pol = HengbotPolicy(town_map=town_map)
        pol._build_grid_index(snap)
        pol._observe(snap)
        return pol, snap

    def test_static_town_map_leaves_no_frontier_to_explore(self):
        # Night: unlit WALL tiles are absent from the emitted map, so a walkable
        # town tile borders 'unknown' walls. With the fixed town map loaded and
        # matching this floor, the whole town is known and nothing reads as a
        # frontier — the bot must not 'explore' the town aimlessly.
        tm = TownMap(name="T", width=7, height=5, walkable=frozenset({Position(2, 2), Position(2, 3)}))
        pol, snap = self._lone_town(tm)
        self.assertTrue(pol._town_map_active(snap))
        self.assertFalse(pol._is_frontier(snap, snap.grids[Position(2, 2)]))

    def test_static_town_map_disables_explore_sweep(self):
        # _plan_explore_path also picks any unvisited known-passable tile as a
        # sweep goal. The town map merges every walkable tile into the floor
        # set, so those unvisited tiles would send the bot wandering the town.
        # _explore_step must short-circuit to None when the static map is
        # active — the frontier guard alone does not cover the sweep goal.
        tm = TownMap(name="T", width=7, height=5, walkable=frozenset({Position(2, 2), Position(2, 3)}))
        pol, snap = self._lone_town(tm)
        self.assertTrue(pol._town_map_active(snap))
        self.assertIsNone(pol._explore_step(snap))

    def test_without_the_map_the_same_tile_is_a_frontier(self):
        # Proves the static map is what removes the frontier: absent it, the lone
        # tile's unlit neighbours are unknown and it DOES read as a frontier.
        pol, snap = self._lone_town(None)
        self.assertFalse(pol._town_map_active(snap))
        self.assertTrue(pol._is_frontier(snap, snap.grids[Position(2, 2)]))


class RememberedFrontierTest(unittest.TestCase):
    def test_routes_to_reachable_frontier_after_it_leaves_view(self):
        remembered_grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(10, 13)
        }
        corridor = [Position(10, 10), Position(10, 11), Position(10, 12)]
        for pos in corridor:
            remembered_grids[pos] = grid(pos.y, pos.x)
        first = Snapshot(
            player(10, 12),
            remembered_grids,
            [],
            floor_key=(1, 12, 43),
            width=40,
            height=40,
        )
        current = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(9, 10): grid(9, 10, passable=False),
                Position(11, 10): grid(11, 10, passable=False),
            },
            [],
            floor_key=(1, 12, 43),
            width=40,
            height=40,
        )
        pol = HengbotPolicy()
        pol._build_grid_index(first)
        pol._build_grid_index(current)
        for pos in corridor:
            pol._visit_counts[pos] = 1

        self.assertEqual(pol._explore_step(current), Position(10, 11))

    def test_oscillation_routes_to_remembered_frontier_before_local_wander(self):
        remembered_grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(8, 13)
        }
        west = Position(10, 9)
        start = Position(10, 10)
        east = Position(10, 11)
        frontier = Position(10, 12)
        corridor = [west, start, east, frontier]
        for pos in corridor:
            remembered_grids[pos] = grid(pos.y, pos.x)
        first = Snapshot(
            player(frontier.y, frontier.x),
            remembered_grids,
            [],
            floor_key=(1, 12, 43),
            width=40,
            height=40,
        )
        current = Snapshot(
            player(start.y, start.x, food=12000),
            {
                start: grid(start.y, start.x),
                west: grid(west.y, west.x),
                east: grid(east.y, east.x),
                Position(9, 10): grid(9, 10, passable=False),
                Position(11, 10): grid(11, 10, passable=False),
            },
            [],
            floor_key=(1, 12, 43),
            width=40,
            height=40,
        )
        pol = HengbotPolicy()
        pol._build_grid_index(first)
        pol._floor_key = first.floor_key
        pol._recent.extend([west, start] * (STUCK_WINDOW // 2))
        pol._search_counts[(start.y, start.x)] = SEARCH_LIMIT
        pol._visit_counts[west] = 1
        pol._visit_counts[start] = 2
        pol._visit_counts[east] = 5
        pol._visit_counts[frontier] = 2

        self.assertEqual(pol.choose_key(current), "6")
        self.assertEqual(pol.last_reason, "breakout:seek-frontier")


class TownNightNavigationTest(unittest.TestCase):
    """Night in a static town: only the player's own tile is lit, so every other
    town tile (stores, the '>' entrance) is dark and absent from the emitted
    grids. The bot must still route to those goals using the town map's
    remembered positions rather than stalling / wandering until dawn.
    """

    def _night_town(self, town_map, py=2, px=1):
        snap = Snapshot(
            player(py, px, class_id=PLAYER_CLASS_WARRIOR),
            {Position(py, px): grid(py, px)},  # only our own tile is emitted
            [],
            floor_key=(0, 0, 0),
            width=7,
            height=5,
            town_flag=True,
        )
        pol = HengbotPolicy(town_map=town_map)
        pol._build_grid_index(snap)
        pol._observe(snap)
        return pol, snap

    def _corridor(self):
        # A straight east-west corridor on row y=2 from x=1..5.
        return frozenset(Position(2, x) for x in range(1, 6))

    def test_goal_step_routes_across_unlit_tiles(self):
        tm = TownMap(name="T", width=7, height=5, walkable=self._corridor())
        pol, snap = self._night_town(tm)
        # Goal (2,5) is dark (not in grids) yet the corridor is remembered.
        self.assertEqual(pol._town_map_goal_step(snap, Position(2, 5)), Position(2, 2))

    def test_goal_step_none_when_already_on_target(self):
        tm = TownMap(name="T", width=7, height=5, walkable=self._corridor())
        pol, snap = self._night_town(tm, px=5)
        self.assertIsNone(pol._town_map_goal_step(snap, Position(2, 5)))

    def test_shallow_run_does_not_route_to_unverified_night_entrance(self):
        tm = TownMap(
            name="T", width=7, height=5, walkable=self._corridor(), entrance=Position(2, 5)
        )
        pol, snap = self._night_town(tm)
        pol._deepest_level = 1  # below RECALL_MIN_DEPTH -> descend on foot
        # The static map remembers only the coordinate, not its dungeon ID.  Do
        # not commit a foot-entry route until live metadata verifies the target.
        pol._descent_is_blocked = lambda _snap: False
        self.assertIsNone(pol._descent_step(snap))
        self.assertIsNone(pol._nav_ledger.descent_target)

    def test_deep_run_does_not_route_to_entrance(self):
        # Past the recall threshold the bot returns by Word of Recall from
        # anywhere in town, so it must NOT trudge to the entrance even when it is
        # otherwise ready to descend.
        tm = TownMap(
            name="T", width=7, height=5, walkable=self._corridor(), entrance=Position(2, 5)
        )
        pol, snap = self._night_town(tm)
        pol._deepest_level = RECALL_MIN_DEPTH + 1
        pol._descent_is_blocked = lambda _snap: False
        self.assertIsNone(pol._town_map_descent_entrance(snap))
        self.assertIsNone(pol._descent_step(snap))

    def test_undersupplied_bot_is_still_blocked_from_the_entrance(self):
        # The night entrance route must not bypass the supply gate: an empty pack
        # (not departure-ready) still yields no descent step, so the bot shops
        # first instead of diving under-equipped.
        tm = TownMap(
            name="T", width=7, height=5, walkable=self._corridor(), entrance=Position(2, 5)
        )
        pol, snap = self._night_town(tm)
        pol._deepest_level = 1
        self.assertTrue(pol._descent_is_blocked(snap))
        self.assertIsNone(pol._descent_step(snap))

    def test_shop_approach_uses_town_map_store_at_night(self):
        tm = TownMap(
            name="T",
            width=7,
            height=5,
            walkable=self._corridor(),
            stores={STORE_GENERAL: Position(2, 5)},
        )
        pol, snap = self._night_town(tm)
        step = pol._town_map_goal_step(snap, tm.store_position(STORE_GENERAL))
        self.assertEqual(step, Position(2, 2))

    def test_parse_records_dungeon_entrance(self):
        import tempfile

        text = "\n".join(
            [
                "N:test",
                "D:#####",
                "D:#1.>#",  # store '1' at (1,1), floor, entrance '>' at (1,3)
                "D:#####",
            ]
        )
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(text)
            path = Path(fh.name)
        try:
            tm = parse_town_map(path)
        finally:
            path.unlink()
        self.assertEqual(tm.entrance, Position(1, 3))
        self.assertIn(Position(1, 3), tm.walkable)  # '>' is walkable too
        self.assertEqual(tm.stores[STORE_GENERAL], Position(1, 1))


class IdentifyStaffTest(unittest.TestCase):
    """A Staff of Identify is required in the departure kit for 10F+, and while
    the pack is filling the bot identifies unknowns so junk can be judged/shed.
    """

    def _staff(self, charges=20):
        return item(
            "s", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=charges, name="Staff of Identify"
        )

    def _town(self, deepest, inventory=None):
        pol = HengbotPolicy()
        pol._deepest_level = deepest
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory or [],
        )
        return pol, snap

    def test_staff_required_for_deep_departure(self):
        pol, snap = self._town(STAFF_IDENTIFY_MIN_DEPTH)  # planned depth >= 10
        self.assertFalse(pol._identify_staff_ready(snap))
        pol2, snap2 = self._town(STAFF_IDENTIFY_MIN_DEPTH, inventory=[self._staff()])
        self.assertTrue(pol2._identify_staff_ready(snap2))

    def test_staff_not_required_when_shallow(self):
        pol, snap = self._town(3)  # planned depth 4 < 10
        self.assertTrue(pol._identify_staff_ready(snap))

    def test_depleted_staff_is_not_ready(self):
        pol, snap = self._town(STAFF_IDENTIFY_MIN_DEPTH, inventory=[self._staff(charges=0)])
        self.assertFalse(pol._identify_staff_ready(snap))

    def test_deep_departure_buys_staff_at_magic_shop(self):
        # Fully supplied except the staff → _next_purchase at the Magic shop must
        # pick the Staff of Identify.
        inv = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
            item("t", TVAL_SCROLL, 9, count=15),  # teleport (deep target is 15)
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
        ]
        snap = Snapshot(
            player(10, 10, gold=5000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=inv,
            equipment=[item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)],
            store=StoreState(
                STORE_MAGIC,
                [store_item("z", TVAL_STAFF, SV_STAFF_IDENTIFY, price=500)],
            ),
        )
        pol = HengbotPolicy()
        pol._deepest_level = STAFF_IDENTIFY_MIN_DEPTH
        purchase = pol._next_purchase(snap)
        self.assertIsNotNone(purchase)
        self.assertEqual((purchase.tval, purchase.sval), (TVAL_STAFF, SV_STAFF_IDENTIFY))

    def _pressured_pack(self, *extra):
        # 18 aware wand filler + the extras = a nearly-full pack (<= free slots).
        filler = [
            item(chr(ord("a") + i), TVAL_WAND, i, name=f"filler-{i}")
            for i in range(PACK_CAPACITY - IDENTIFY_PRESSURE_FREE_SLOTS - len(extra))
        ]
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 12, 0),  # deep in the dungeon
            inventory=[*filler, *extra],
        )

    def test_pack_pressure_identifies_unknown_with_staff(self):
        staff = self._staff()
        unknown = item("t", TVAL_POTION, 3, aware=False, name="murky potion")
        snap = self._pressured_pack(staff, unknown)
        pol = HengbotPolicy()
        # Original-keyset use-staff u + staff slot s + target slot t.
        self.assertEqual(pol._pack_pressure_identify_key(snap), "ust")
        self.assertEqual(pol.last_reason, "identify:pack-pressure")

    def test_pack_pressure_identifies_aware_but_unknown_equipment(self):
        # Awareness identifies the base kind (Leather Gloves), not the individual
        # item's bonuses. It still needs Identify before the bot can keep or shed it.
        staff = self._staff()
        gloves = item(
            "t", 31, 1, aware=True, known=False,
            is_equipment=True, name="Leather Gloves",
        )
        snap = self._pressured_pack(staff, gloves)

        pol = HengbotPolicy()
        self.assertEqual(pol._pack_pressure_identify_key(snap), "ust")
        self.assertEqual(pol.last_reason, "identify:pack-pressure")

    def test_pack_pressure_skips_ammunition_and_identifies_real_equipment(self):
        staff = self._staff()
        arrows = item(
            "t", TVAL_ARROW, 1, count=20, aware=False, known=False,
            is_equipment=True, name="Arrows",
        )
        gloves = item(
            "u", 31, 1, aware=True, known=False,
            is_equipment=True, name="Leather Gloves",
        )
        snap = self._pressured_pack(staff, arrows, gloves)

        pol = HengbotPolicy()
        self.assertEqual(pol._pack_pressure_identify_key(snap), "usu")
        self.assertEqual(pol.last_reason, "identify:pack-pressure")

    def test_pack_pressure_does_not_identify_ammunition(self):
        staff = self._staff()
        arrows = item(
            "t", TVAL_ARROW, 1, count=20, aware=False, known=False,
            is_equipment=True, name="Arrows",
        )
        snap = self._pressured_pack(staff, arrows)

        self.assertIsNone(HengbotPolicy()._pack_pressure_identify_key(snap))

    def test_stalled_identify_abandons_target_after_retries(self):
        # If the identify never lands (unknown count stays put), the target is
        # abandoned after the retry budget instead of looping on it forever.
        staff = self._staff()
        unknown = item("t", TVAL_POTION, 3, aware=False, name="murky")
        snap = self._pressured_pack(staff, unknown)
        pol = HengbotPolicy()
        results = [pol._pack_pressure_identify_key(snap) for _ in range(IDENTIFY_FAIL_LIMIT + 2)]
        self.assertEqual(results[0], "ust")
        self.assertIsNone(results[-1])
        self.assertIn(pol._item_signature(unknown), pol._unidentifiable_sigs)

    def test_no_identify_when_pack_has_room(self):
        staff = self._staff()
        unknown = item("t", TVAL_POTION, 3, aware=False)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 12, 0),
            inventory=[staff, unknown],  # only 2 items → lots of free slots
        )
        self.assertIsNone(HengbotPolicy()._pack_pressure_identify_key(snap))

    def test_unidentified_mushroom_is_not_identified(self):
        # Food is shed rather than identified, so a mushroom is never the target.
        staff = self._staff()
        mushroom = item("t", TVAL_FOOD, 5, aware=False, name="mushroom")
        snap = self._pressured_pack(staff, mushroom)
        self.assertIsNone(HengbotPolicy()._pack_pressure_identify_key(snap))

    def test_drained_identify_staff_becomes_sellable(self):
        # A depleted Staff of Identify can no longer identify, so it stops being a
        # "useful device" and the Magic-shop device-sale offloads it; a charged
        # one is still kept.
        pol = HengbotPolicy()
        drained = item("s", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=0, name="drained")
        self.assertFalse(pol._is_useful_device(drained))
        self.assertTrue(
            pol._is_useful_device(item("t", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=3))
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[drained],
        )
        sale = pol._find_device_sale(snap)
        self.assertIsNotNone(sale)
        self.assertEqual(sale.slot, "s")

    def test_identify_staffs_above_five_sell_lowest_charge_first(self):
        pol = HengbotPolicy()
        staffs = [
            item(
                chr(ord("a") + index),
                TVAL_STAFF,
                SV_STAFF_IDENTIFY,
                charges=charges,
                name="Staff of Identify",
            )
            for index, charges in enumerate([20, 18, 16, 14, 12, 3])
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=staffs,
        )

        self.assertEqual(STAFF_IDENTIFY_MAX_COUNT, 5)
        self.assertEqual(pol._find_device_sale(snap).slot, "f")
        self.assertIsNone(pol._find_device_sale(replace(snap, inventory=staffs[:5])))

    def test_stacked_identify_staff_count_is_capped(self):
        pol = HengbotPolicy()
        stack = item(
            "s",
            TVAL_STAFF,
            SV_STAFF_IDENTIFY,
            count=6,
            charges=60,
            name="Staff of Identify",
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[stack],
        )

        self.assertEqual(pol._find_device_sale(snap).slot, "s")

    def test_mana_food_reserve_keeps_highest_charge_identify_staff(self):
        pol = HengbotPolicy()
        staffs = [
            item(
                chr(ord("a") + index),
                TVAL_STAFF,
                SV_STAFF_IDENTIFY,
                charges=charges,
                name="Staff of Identify",
            )
            for index, charges in enumerate([30, 20, 18, 16, 14, 2])
        ]
        snap = Snapshot(
            player(
                10,
                10,
                class_id=PLAYER_CLASS_WARRIOR,
                food_type=FOOD_TYPE_MANA,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=staffs,
        )

        self.assertEqual(pol._device_food_reserve_slot(snap), "a")
        self.assertEqual(pol._find_device_sale(snap).slot, "f")

    def test_no_identify_in_town(self):
        # Town has its own identify errands; the pressure path is dungeon-only.
        staff = self._staff()
        unknown = item("t", TVAL_POTION, 3, aware=False)
        filler = [
            item(chr(ord("a") + i), TVAL_WAND, i)
            for i in range(PACK_CAPACITY - IDENTIFY_PRESSURE_FREE_SLOTS - 2)
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[*filler, staff, unknown],
        )
        self.assertIsNone(HengbotPolicy()._pack_pressure_identify_key(snap))


class RemoveCurseTest(unittest.TestCase):
    """Town prep reads a Remove Curse scroll when a cursed item is worn (and buys
    one at the Temple when none is carried)."""

    def _town(self, equipment, inventory=None):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory or [],
            equipment=equipment,
        )

    def test_reads_remove_curse_when_cursed_and_scrolled(self):
        cursed = item("a", 23, 0, is_equipment=True, is_cursed=True, name="cursed")
        scroll = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, name="remove curse")
        pol = HengbotPolicy()
        self.assertEqual(pol._town_remove_curse_key(self._town([cursed], [scroll])), "rs")
        self.assertEqual(pol.last_reason, "town:remove-curse")

    def test_no_remove_curse_without_cursed_equipment(self):
        plain = item("a", 23, 0, is_equipment=True, name="plain")
        scroll = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)
        self.assertIsNone(HengbotPolicy()._town_remove_curse_key(self._town([plain], [scroll])))

    def test_no_remove_curse_without_scroll(self):
        cursed = item("a", 23, 0, is_equipment=True, is_cursed=True)
        self.assertIsNone(HengbotPolicy()._town_remove_curse_key(self._town([cursed], [])))

    def test_blind_defers_remove_curse(self):
        cursed = item("a", 23, 0, is_equipment=True, is_cursed=True)
        scroll = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, blind=True),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[scroll],
            equipment=[cursed],
        )
        self.assertIsNone(HengbotPolicy()._town_remove_curse_key(snap))

    def test_buys_remove_curse_at_temple_when_cursed(self):
        inv = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
            item("t", TVAL_SCROLL, 9, count=9),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=9),
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
        ]
        snap = Snapshot(
            player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=inv,
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("w", 23, 0, is_equipment=True, is_cursed=True, name="cursed"),
            ],
            store=StoreState(
                STORE_TEMPLE,
                [store_item("z", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, price=100)],
            ),
        )
        purchase = HengbotPolicy()._next_purchase(snap)
        self.assertIsNotNone(purchase)
        self.assertEqual(purchase.sval, SV_SCROLL_REMOVE_CURSE)

    def test_unchanged_normal_read_latches_and_marks_heavy_curse(self):
        cursed = item(
            "main_ring", 23, 0, is_equipment=True, is_cursed=True,
            known=True, name="incident cursed ring", inscription="keep",
        )
        normal = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, name="remove curse")
        policy = HengbotPolicy()
        snapshot = self._town([cursed], [normal])
        self.assertEqual(policy._town_remove_curse_key(snapshot), "rs")
        policy._observe(self._town([cursed], []))

        self.assertIsNone(policy._town_remove_curse_key(self._town([cursed], [normal])))
        self.assertEqual(
            policy._heavy_curse_inscription_key(self._town([cursed])),
            "{/d HEAVY_CURSE\r",
        )
        self.assertIsNone(policy._heavy_curse_inscription_key(self._town([cursed])))
        needs = policy._enumerate_town_needs(self._town([cursed], []))
        self.assertNotIn(TownNeed(STORE_TEMPLE, "remove-curse", "normal"), needs)

    def test_inscription_authority_survives_restart_without_normal_read(self):
        cursed = item(
            "main_ring", 23, 0, is_equipment=True, is_cursed=True,
            inscription="keep HEAVY_CURSE", name="incident cursed ring",
        )
        normal = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)
        policy = HengbotPolicy()
        self.assertTrue(policy._curse_unremovable(cursed))
        self.assertIsNone(policy._town_remove_curse_key(self._town([cursed], [normal])))
        self.assertFalse(policy._remove_curse_unchanged)

    def test_star_remove_curse_loot_is_used_for_heavy_latch(self):
        cursed = item(
            "a", 23, 0, is_equipment=True, is_cursed=True,
            known=True, name="incident cursed ring",
        )
        normal = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, name="remove curse")
        star = item("t", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, name="star remove curse")
        policy = HengbotPolicy()
        for _attempt in range(2):
            policy._town_remove_curse_key(self._town([cursed], [normal]))
            policy._observe(self._town([cursed], []))

        policy._observe(self._town([cursed], [star]))
        self.assertEqual(policy._town_remove_curse_key(self._town([cursed], [star])), "rt")

    def test_heavy_curse_buys_stocked_star_scroll_then_reads_it(self):
        cursed = item(
            "a", 23, 0, is_equipment=True, is_cursed=True,
            known=True, name="incident cursed ring",
        )
        policy = HengbotPolicy()
        signature = policy._item_signature(cursed)
        policy._heavy_cursed_items.add(signature)
        supplies = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
            item("t", TVAL_SCROLL, 9, count=15),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
        ]
        temple = replace(
            self._town([
                item("L", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                cursed,
            ], supplies),
            player=player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            store=StoreState(
                STORE_TEMPLE,
                [store_item("z", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, price=500)],
            ),
        )
        self.assertIn(
            TownNeed(STORE_TEMPLE, "star-remove-curse", "normal"),
            policy._enumerate_town_needs(temple),
        )
        self.assertEqual(policy._next_purchase(temple).sval, SV_SCROLL_STAR_REMOVE_CURSE)

        star = item("t", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, name="star remove curse")
        self.assertEqual(policy._town_remove_curse_key(self._town([cursed], [star])), "rt")
        uncursed = replace(cursed, is_cursed=False)
        policy._observe(self._town([uncursed], []))
        self.assertNotIn(signature, policy._heavy_cursed_items)

    def test_heavy_curse_missing_star_scroll_never_creates_temple_wait(self):
        cursed = item(
            "a", 23, 0, is_equipment=True, is_cursed=True,
            known=True, name="incident cursed ring",
        )
        policy = HengbotPolicy()
        policy._heavy_cursed_items.add(policy._item_signature(cursed))
        temple = replace(
            self._town([cursed]),
            player=player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            store=StoreState(STORE_TEMPLE, []),
        )
        self.assertFalse(any(
            need.category in {"remove-curse", "star-remove-curse"}
            for need in policy._enumerate_town_needs(temple)
        ))
        self.assertIsNone(policy._next_purchase(temple))
        policy._town_store_attempted[STORE_TEMPLE] = temple.turn
        self.assertIsNone(policy._retry_after_store_restock(temple, (STORE_TEMPLE,)))

    def test_heavy_curse_optimizer_blocker_does_not_block_departure(self):
        cursed = item(
            "a", 23, 0, is_equipment=True, is_cursed=True,
            known=True, name="incident cursed ring",
        )
        policy = HengbotPolicy()
        policy._heavy_cursed_items.add(policy._item_signature(cursed))
        blocked = SimpleNamespace(
            blockers=("cursed-equipped:equipped:ring:0",),
            transaction=None,
            ready=False,
        )
        policy._prepare_equipment_optimization = lambda _snapshot: blocked

        self.assertTrue(policy._equipment_departure_ready(self._town([cursed])))

    def test_unactionable_curse_optimizer_blocker_does_not_block_departure(self):
        cursed = item("main_ring", 23, 0, is_equipment=True, is_cursed=True)
        policy = HengbotPolicy()
        policy._town_store_attempted[STORE_TEMPLE] = 0
        blocked = SimpleNamespace(
            blockers=("cursed-equipped:equipped:ring:0",),
            transaction=None,
            ready=False,
        )
        policy._prepare_equipment_optimization = lambda _snapshot: blocked
        self.assertTrue(policy._equipment_departure_ready(self._town([cursed])))

    def test_actionable_normal_scroll_keeps_departure_blocked(self):
        cursed = item("main_ring", 23, 0, is_equipment=True, is_cursed=True)
        normal = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)
        policy = HengbotPolicy()
        blocked = SimpleNamespace(
            blockers=("cursed-equipped:equipped:ring:0",),
            transaction=None,
            ready=False,
        )
        policy._prepare_equipment_optimization = lambda _snapshot: blocked
        self.assertFalse(
            policy._equipment_departure_ready(self._town([cursed], [normal]))
        )

    def test_interrupted_normal_read_does_not_advance_heavy_latch(self):
        cursed = item("a", 23, 0, is_equipment=True, is_cursed=True, name="cursed")
        normal = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, name="remove curse")
        policy = HengbotPolicy()
        snapshot = self._town([cursed], [normal])
        self.assertEqual(policy._town_remove_curse_key(snapshot), "rs")
        policy._observe(snapshot)
        self.assertFalse(policy._remove_curse_unchanged)

class HighValueBookSaleTest(unittest.TestCase):
    def _town(self, inventory, store=None):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            store=store,
        )

    def test_only_third_and_fourth_books_are_high_value_sales(self):
        policy = HengbotPolicy()
        second = item("a", TVAL_CHAOS_BOOK, 1, name="Chaos book 2")
        third = item("b", TVAL_CHAOS_BOOK, 2, name="Chaos book 3")
        fourth = item("c", TVAL_CHAOS_BOOK, 3, name="Chaos book 4")

        self.assertFalse(policy._is_high_value_book(second))
        self.assertTrue(policy._is_high_value_book(third))
        self.assertTrue(policy._is_high_value_book(fourth))
        self.assertEqual(policy._find_book_sale(self._town([second, third])).slot, "b")
        self.assertTrue(policy._has_town_economic_path(third))

    def test_routes_books_to_a_store_that_buys_their_realm(self):
        cases = (
            (TVAL_CHAOS_BOOK, STORE_MAGIC),
            (TVAL_LIFE_BOOK, STORE_TEMPLE),
            (TVAL_HISSATSU_BOOK, STORE_WEAPON),
        )
        for tval, store_type in cases:
            with self.subTest(tval=tval):
                # Each case represents a fresh town visit; a live circuit never
                # abandons its current still-needed stop for a new mid-visit need.
                policy = HengbotPolicy()
                book = item("b", tval, 2, name="valuable book")
                self.assertEqual(
                    policy._next_required_store_type(self._town([book])), store_type
                )

    def test_sells_high_value_book_in_one_store_visit(self):
        book = item("b", TVAL_CHAOS_BOOK, 3, name="Chaos book 4")
        snapshot = self._town([book], StoreState(STORE_MAGIC, []))
        policy = HengbotPolicy()

        self.assertEqual(policy._shop(snapshot), SELL_KEY + "b" + SELL_CONFIRM_SUFFIX)
        self.assertEqual(policy.last_reason, "shop:sell-high-value-book")

    def test_withdraws_an_old_high_value_book_from_home_for_sale(self):
        book = store_item("c", TVAL_CHAOS_BOOK, 2, name="Chaos book 3")
        snapshot = self._town([], StoreState(STORE_HOME, [book]))
        policy = HengbotPolicy()

        self.assertEqual(policy._shop(snapshot), BUY_KEY + "c\r")
        self.assertEqual(policy.last_reason, "home:withdraw-book-sale")

    def test_leaves_home_with_withdrawn_book_instead_of_redepositing_it(self):
        book = item("b", TVAL_CHAOS_BOOK, 3, name="Chaos book 4")
        snapshot = self._town([book], StoreState(STORE_HOME, []))
        policy = HengbotPolicy()

        self.assertEqual(policy._shop(snapshot), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:leave-with-book-sale")


class UniqueCombatConsumableTest(unittest.TestCase):
    def _snapshot(
        self,
        *,
        hp=120,
        max_hp=200,
        speed=110,
        monster_hp=180,
        monster_speed=120,
        monster_level=1,
        blow_sides=10,
        inventory=None,
    ):
        monster = replace(
            hostile(
                1,
                10,
                11,
                hp=monster_hp,
                max_hp=monster_hp,
                speed=monster_speed,
                max_melee_damage=blow_sides,
            ),
            race_id=9001,
            name="test unique",
            level=monster_level,
        )
        snapshot = Snapshot(
            replace(
                player(
                    10,
                    10,
                    hp=hp,
                    max_hp=max_hp,
                    main_hand_blows=5,
                    main_hand_to_h=10,
                    main_hand_to_d=10,
                ),
                speed=speed,
            ),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, monster=True),
            },
            [monster],
            inventory=inventory or [],
            equipment=[
                item(
                    "main_hand",
                    23,
                    0,
                    is_equipment=True,
                    damage_dice_num=2,
                    damage_dice_sides=6,
                )
            ],
        )
        knowledge = MonraceKnowledge(
            max_hp=monster_hp,
            average_hp=monster_hp,
            speed=monster_speed,
            can_summon=False,
            friendly=False,
            level=monster_level,
            flags=frozenset({"UNIQUE"}),
            blows=(MonsterBlow("HIT", "HURT", 1, blow_sides),),
        )
        return snapshot, monster, knowledge

    def test_quaffs_speed_only_when_it_materially_improves_a_viable_unique_fight(self):
        snapshot, _, knowledge = self._snapshot(
            monster_level=30,
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED, count=2)]
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertEqual(policy.choose_key(snapshot), "qs")
        self.assertEqual(policy.last_reason, "unique:quaff-speed")

        hasted = replace(snapshot, player=replace(snapshot.player, speed=120))
        self.assertEqual(policy.choose_key(hasted), "6")
        self.assertEqual(policy.last_reason, "melee")

        expired = replace(
            snapshot,
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)],
        )
        self.assertEqual(policy.choose_key(expired), "qs")
        self.assertEqual(policy.last_reason, "unique:quaff-speed")

    def test_multiple_healing_potions_can_be_committed_to_one_unique_fight(self):
        inventory = [
            item("h", TVAL_POTION, SV_POTION_HEALING, count=2),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
        ]
        snapshot, monster, knowledge = self._snapshot(
            hp=80,
            monster_hp=300,
            monster_speed=110,
            blow_sides=41,
            inventory=inventory,
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        plan = policy._unique_fight_projection(
            snapshot,
            [monster],
            monster,
            player_speed=110,
        )

        self.assertIsNotNone(plan)
        self.assertEqual(plan["healing_uses"], 2)
        self.assertEqual(policy.choose_key(snapshot), "qh")
        self.assertEqual(policy.last_reason, "unique:quaff-healing")

        continued = replace(
            snapshot,
            visible_monsters=[replace(monster, hp=150, max_hp=300)],
            inventory=[
                item("h", TVAL_POTION, SV_POTION_HEALING),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )
        self.assertEqual(policy.choose_key(continued), "qh")
        self.assertEqual(policy.last_reason, "unique:quaff-healing")

    def test_full_hp_unique_fight_quaffs_speed_before_reserved_healing(self):
        snapshot, _, knowledge = self._snapshot(
            hp=200,
            max_hp=200,
            monster_hp=300,
            monster_speed=125,
            blow_sides=41,
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("h", TVAL_POTION, SV_POTION_HEALING, count=3),
            ],
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertEqual(policy.choose_key(snapshot), "qs")
        self.assertEqual(policy.last_reason, "unique:quaff-speed")

    def test_does_not_spend_speed_when_unique_fight_is_not_viable(self):
        snapshot, _, knowledge = self._snapshot(
            hp=80,
            monster_hp=500,
            blow_sides=50,
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertEqual(policy.choose_key(snapshot), "rt")
        self.assertEqual(policy.last_reason, "emergency:teleport")

    def test_does_not_spend_rare_potions_on_an_ordinary_monster(self):
        snapshot, _, knowledge = self._snapshot(
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)]
        )
        policy = HengbotPolicy(
            monrace_knowledge={9001: replace(knowledge, flags=frozenset())}
        )

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "melee")

    def test_summoning_unique_may_use_speed_in_a_choke_point(self):
        snapshot, monster, knowledge = self._snapshot(
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)]
        )
        snapshot = replace(
            snapshot,
            visible_monsters=[replace(monster, can_summon=True)],
        )
        policy = HengbotPolicy(
            monrace_knowledge={9001: replace(knowledge, can_summon=True)}
        )

        self.assertEqual(policy.choose_key(snapshot), "qs")
        self.assertEqual(policy.last_reason, "unique:quaff-speed")

    def test_summoning_unique_in_open_terrain_escapes_without_spending_speed(self):
        snapshot, monster, knowledge = self._snapshot(
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ]
        )
        open_room = {
            Position(y, x): grid(y, x, monster=(y, x) == (10, 11))
            for y in range(9, 12)
            for x in range(9, 12)
        }
        snapshot = replace(
            snapshot,
            grids=open_room,
            visible_monsters=[replace(monster, can_summon=True)],
        )
        policy = HengbotPolicy(
            monrace_knowledge={9001: replace(knowledge, can_summon=True)}
        )

        self.assertEqual(policy.choose_key(snapshot), "rt")
        self.assertEqual(policy.last_reason, "emergency:teleport")


class OptionalBlackMarketPotionTest(unittest.TestCase):
    def _supplies(self):
        return [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL),
            item("f", TVAL_FOOD, 35, count=5),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=500),
        ]

    def _town(self, *, inventory=None, store=None, gold=10000):
        return Snapshot(
            player(10, 10, gold=gold, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory if inventory is not None else self._supplies(),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
            store=store,
        )

    def test_black_market_is_checked_once_per_town_visit(self):
        policy = HengbotPolicy()
        snapshot = self._town()

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_BLACK)
        policy._town_store_attempted[STORE_BLACK] = 0
        self.assertIsNone(policy._next_required_store_type(snapshot))

    def test_existing_stockpile_does_not_cap_black_market_purchases(self):
        inventory = [
            *self._supplies(),
            item("s", TVAL_POTION, SV_POTION_SPEED, count=20),
            item("h", TVAL_POTION, SV_POTION_HEALING, count=20),
        ]
        wares = [
            store_item("a", TVAL_POTION, SV_POTION_SPEED, price=1000, count=5),
            store_item("b", TVAL_POTION, SV_POTION_HEALING, price=1000, count=5),
        ]
        policy = HengbotPolicy()
        town = self._town(
            inventory=inventory,
            store=StoreState(STORE_BLACK, wares),
            gold=10000,
        )

        self.assertEqual(policy._next_required_store_type(replace(town, store=None)), STORE_BLACK)
        purchase = policy._next_purchase(town)
        self.assertIsNotNone(purchase)
        self.assertEqual(policy._purchase_quantity(town, purchase), 1)

    def test_buys_one_speed_then_one_healing_when_affordable(self):
        wares = [
            store_item("a", TVAL_POTION, SV_POTION_SPEED, price=5000),
            store_item("b", TVAL_POTION, SV_POTION_HEALING, price=6000),
        ]
        policy = HengbotPolicy()
        first = self._town(store=StoreState(STORE_BLACK, wares), gold=10000)
        self.assertEqual(policy._next_purchase(first).sval, SV_POTION_SPEED)

        second = self._town(
            inventory=[
                *self._supplies(),
                item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL),
                item("t", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE),
                item("s", TVAL_POTION, SV_POTION_SPEED),
            ],
            store=StoreState(STORE_BLACK, wares),
            gold=6000,
        )
        self.assertEqual(policy._next_purchase(second).sval, SV_POTION_HEALING)

    def test_keeps_buying_the_remaining_type_until_funds_or_stock_run_out(self):
        policy = HengbotPolicy()
        stocked = self._town(
            inventory=[
                *self._supplies(),
                item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL),
                item("t", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE),
                item("s", TVAL_POTION, SV_POTION_SPEED, count=3),
                item("h", TVAL_POTION, SV_POTION_HEALING, count=2),
            ],
            store=StoreState(
                STORE_BLACK,
                [store_item("b", TVAL_POTION, SV_POTION_HEALING, price=500, count=4)],
            ),
            gold=500,
        )
        self.assertEqual(policy._next_purchase(stocked).sval, SV_POTION_HEALING)

        out_of_funds = replace(stocked, player=replace(stocked.player, gold=499))
        self.assertIsNone(policy._next_purchase(out_of_funds))

    def test_unaffordable_stock_does_not_block_departure(self):
        policy = HengbotPolicy()
        snapshot = self._town(
            store=StoreState(
                STORE_BLACK,
                [store_item("a", TVAL_POTION, SV_POTION_SPEED, price=5000)],
            ),
            gold=4999,
        )

        self.assertIsNone(policy._next_purchase(snapshot))
        policy._town_store_attempted[STORE_BLACK] = 0
        self.assertIsNone(policy._next_required_store_type(snapshot))


class IdentifyPurchaseBatchingTest(unittest.TestCase):
    """A Home identification batch can surface several items needing Identify
    or *Identify* at once. Buying only one scroll per store trip discovered
    each further need only after a fresh Home round trip (measured: a single
    town stay spent 4 separate Alchemist visits on one Home batch).
    _purchase_quantity now covers the whole outstanding tier in one purchase
    instead (see _outstanding_identification_count), still capped and still
    gated by the ordinary affordability check."""

    def _town(self, *, inventory, gold=100000, store=None):
        return Snapshot(
            player(10, 10, gold=gold, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            equipment=[
                item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)
            ],
            store=store,
        )

    def test_star_identify_quantity_matches_outstanding_full_targets(self):
        # 3 known ego weapons in the pack, each still missing its full traits.
        pack = [
            item(
                letter, 23, sval, name=f"ego {letter}", is_equipment=True,
                is_ego=True, known=True, fully_known=False,
            )
            for letter, sval in (("a", 1), ("b", 2), ("c", 3))
        ]
        store = StoreState(
            STORE_ALCHEMIST,
            [store_item("s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, price=500, count=99)],
        )
        town = self._town(inventory=pack, store=store)
        policy = HengbotPolicy()
        # The bot only walks into the Alchemist for this once an earlier town
        # decision (_town_item_processing_key et al.) already found a target
        # and requested this tier -- reproduce that precondition directly.
        policy._identification_need = "full"

        purchase = policy._next_purchase(town)
        self.assertIsNotNone(purchase)
        self.assertEqual(policy._purchase_quantity(town, purchase), 3)

    def test_identify_quantity_stays_one_when_nothing_outstanding(self):
        store = StoreState(
            STORE_ALCHEMIST,
            [store_item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=20, count=99)],
        )
        town = self._town(inventory=[], store=store)
        policy = HengbotPolicy()

        self.assertEqual(policy._purchase_quantity(town, town.store.items[0]), 1)

    def test_identify_quantity_is_capped(self):
        pack = [
            item(
                chr(ord("a") + i), 30 + (i % 4), 1, name=f"unknown {i}",
                is_equipment=True, known=False, pseudo_feeling="good",
            )
            for i in range(7)
        ]
        store = StoreState(
            STORE_ALCHEMIST,
            [store_item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=20, count=99)],
        )
        town = self._town(inventory=pack, store=store)
        policy = HengbotPolicy()

        self.assertEqual(
            policy._purchase_quantity(town, town.store.items[0]), IDENTIFY_PURCHASE_MAX
        )

    def test_identify_quantity_still_respects_affordability(self):
        pack = [
            item(
                chr(ord("a") + i), 30, 1, name=f"unknown {i}",
                is_equipment=True, known=False, pseudo_feeling="good",
            )
            for i in range(3)
        ]
        store = StoreState(
            STORE_ALCHEMIST,
            [store_item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=100, count=99)],
        )
        # 3 outstanding, but 250g only affords 2 scrolls at 100g each.
        town = self._town(inventory=pack, gold=250, store=store)
        policy = HengbotPolicy()

        self.assertEqual(policy._purchase_quantity(town, town.store.items[0]), 2)

    def test_outstanding_count_combines_pack_and_home_and_splits_by_tier(self):
        pack_normal = item(
            "a", 30, 1, name="unknown boots", is_equipment=True,
            known=False, pseudo_feeling="good",
        )
        pack_full = item(
            "b", 23, 1, name="ego blade", is_equipment=True,
            is_ego=True, known=True, fully_known=False,
        )
        home_normal = store_item(
            "c", 31, 1, name="unknown gloves", is_equipment=True,
            known=False, pseudo_feeling="good",
        )
        home_full = store_item(
            "d", 36, 1, name="ego mail", is_equipment=True,
            is_ego=True, known=True, fully_known=False,
        )
        policy = HengbotPolicy()
        town = self._town(inventory=[pack_normal, pack_full])
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([home_normal, home_full])
        policy._equipment_catalog.observe_home_page([])

        self.assertEqual(policy._outstanding_identification_count(town, full=False), 2)
        self.assertEqual(policy._outstanding_identification_count(town, full=True), 2)

    def test_outstanding_count_skips_deferred_and_processed_home_items(self):
        # Mirrors _has_actionable_incomplete_home_item exactly: a deferred item
        # is skipped regardless of tier, and a *known* item only needing full
        # identification is skipped once cached in _processed_home_items (an
        # unidentified twin is never skipped that way -- see that function).
        deferred = store_item(
            "a", 31, 1, name="deferred gloves", is_equipment=True,
            known=False, pseudo_feeling="good",
        )
        processed = store_item(
            "b", 36, 1, name="processed mail", is_equipment=True,
            is_ego=True, known=True, fully_known=False,
        )
        policy = HengbotPolicy()
        town = self._town(inventory=[])
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([deferred, processed])
        policy._equipment_catalog.observe_home_page([])
        policy._deferred_home_items.add(policy._item_signature(deferred))
        policy._processed_home_items.add(policy._item_signature(processed))

        self.assertEqual(policy._outstanding_identification_count(town, full=False), 0)
        self.assertEqual(policy._outstanding_identification_count(town, full=True), 0)

    def test_outstanding_count_excludes_lights_and_diggers_from_the_pack(self):
        # prime()'s batch-population scan never queues lights/diggers (they are
        # not processed by the identify errand this visit), so an unidentified
        # one sitting in the pack must not inflate the purchase quantity.
        unidentified_lantern = item(
            "a", TVAL_LITE, SV_LITE_LANTERN, name="lantern", is_equipment=True,
            known=False, pseudo_feeling="good",
        )
        unidentified_digger = item(
            "b", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="shovel", is_equipment=True,
            known=False, pseudo_feeling="good",
        )
        policy = HengbotPolicy()
        town = self._town(inventory=[unidentified_lantern, unidentified_digger])

        self.assertEqual(policy._outstanding_identification_count(town, full=False), 0)


class WeaponSaleTest(unittest.TestCase):
    """Once an excellent+ (ego/artifact) weapon is wielded, good/average spare
    weapons are sold at the Weapon Smith instead of hoarded in the Home."""

    def _ego(self):
        return item("main_hand", 23, 0, is_equipment=True, is_ego=True, known=True, name="ego")

    def _inferior(self, slot="b", pseudo="good"):
        return item(slot, 23, 0, is_equipment=True, known=True, pseudo_feeling=pseudo, name="spare")

    def _town(self, inventory, equipment, store=None):
        return Snapshot(
            replace(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                stat_cur=(18, 10, 10, 18), stat_use=(18, 10, 10, 18),
                melee_skill=60, two_weapon_skill=4000,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            equipment=equipment,
            store=store,
        )

    def test_high_grade_and_inferior_classification(self):
        pol = HengbotPolicy()
        self.assertTrue(pol._weapon_is_high_grade(self._ego()))
        self.assertTrue(
            pol._weapon_is_high_grade(item("a", 23, 0, known=True, pseudo_feeling="excellent"))
        )
        self.assertFalse(pol._weapon_is_high_grade(self._inferior()))
        self.assertTrue(pol._weapon_is_inferior(self._inferior("b", "good")))
        self.assertTrue(pol._weapon_is_inferior(self._inferior("b", "average")))
        self.assertFalse(pol._weapon_is_inferior(self._ego()))
        self.assertFalse(
            pol._weapon_is_inferior(item("d", TVAL_DIGGING, 1, known=True, pseudo_feeling="good"))
        )
        # An *identified* plain weapon carries no pseudo_feeling, yet a mundane
        # +0,+0 spare is exactly "上質以下" and must be sold. (Live bug: Short/Broad
        # Sword, known:true, pseudo:"" were never being flagged.)
        self.assertTrue(pol._weapon_is_inferior(item("b", 23, 0, known=True, name="mundane")))
        # Still unidentified and unsensed -> do NOT blind-sell (could be an ego).
        self.assertFalse(pol._weapon_is_inferior(item("b", 23, 0, known=False)))
        # Unidentified but pseudo-sensed good/average is safe to sell.
        self.assertTrue(
            pol._weapon_is_inferior(item("b", 23, 0, known=False, pseudo_feeling="average"))
        )
        # A known ego spare is high-grade and kept even without full ID.
        self.assertFalse(pol._weapon_is_inferior(item("b", 23, 0, known=True, is_ego=True)))

    def test_sale_target_only_with_high_grade_wielded(self):
        pol = HengbotPolicy()
        inf = self._inferior()
        self.assertEqual(pol._find_weapon_sale(self._town([inf], [self._ego()])).slot, "b")
        plain = item("main_hand", 23, 0, is_equipment=True, known=True, pseudo_feeling="good")
        self.assertIsNone(pol._find_weapon_sale(self._town([inf], [plain])))

    def test_higher_dps_plain_spare_is_not_sold_beside_ego_weapon(self):
        pol = HengbotPolicy()
        wielded = replace(
            self._ego(), damage_dice_num=1, damage_dice_sides=4, weight=50
        )
        spare = replace(
            self._inferior(), damage_dice_num=2, damage_dice_sides=6,
            to_h=5, to_d=7, weight=50,
        )
        town = self._town([spare], [wielded])
        town = replace(
            town,
            player=replace(
                town.player, level=27, stat_cur=(68, 10, 10, 68),
                stat_use=(68, 10, 10, 68), melee_skill=80,
                two_weapon_skill=4000,
            ),
        )

        self.assertIsNone(pol._find_weapon_sale(town))

    def test_sells_no_teleport_artifact_after_replacement(self):
        policy = HengbotPolicy()
        blocked = item(
            "b",
            23,
            1,
            name="artifact scimitar",
            is_equipment=True,
            is_artifact=True,
            fully_known=True,
            known_flags=frozenset({TR_NO_TELE}),
        )
        safe = self._ego()
        town = self._town([blocked], [safe])

        self.assertEqual(policy._find_weapon_sale(town).slot, "b")
        self.assertEqual(policy._next_required_store_type(town), STORE_WEAPON)
        shop = self._town([blocked], [safe], store=StoreState(STORE_WEAPON, []))
        self.assertEqual(policy._shop(shop), SELL_KEY + "b" + SELL_CONFIRM_SUFFIX)
        self.assertEqual(policy.last_reason, "shop:sell-no-teleport-weapon")

    def test_inferior_spare_not_deposited_when_high_grade(self):
        pol = HengbotPolicy()
        inf = self._inferior()
        self.assertIsNone(pol._find_home_deposit(self._town([inf], [self._ego()])))
        plain = item("main_hand", 23, 0, is_equipment=True, known=True, pseudo_feeling="good")
        self.assertIsNotNone(pol._find_home_deposit(self._town([inf], [plain])))

    def test_high_grade_spare_is_not_deposited_before_optimizer_compares_it(self):
        pol = HengbotPolicy()
        spare = item(
            "b", 23, 8, is_equipment=True, is_ego=True, known=True,
            name="ego spare",
        )

        self.assertIsNone(pol._find_home_deposit(self._town([spare], [self._ego()])))

    def test_high_grade_weapon_is_protected_when_only_digger_is_equipped(self):
        pol = HengbotPolicy()
        spare = item(
            "b", 23, 8, is_equipment=True, is_ego=True, known=True,
            name="rearm weapon",
        )
        digger = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            is_equipment=True, known=True, name="Shovel",
        )

        self.assertIsNone(pol._find_home_deposit(self._town([spare], [digger])))

    def test_good_non_ego_spare_is_not_deposited_before_loadout_search(self):
        # A spare with a real +to-hit bonus but no ego/artifact/excellent-pseudo
        # sense is "good_weapon" (see _home_deposit_candidate) yet not "high
        # grade" (see _weapon_is_high_grade) -- the gap the OLD unconditional
        # good_weapon protection left with NO disposal path at all: not shelved
        # (good_weapon blocked it outright), and _find_home_deposit's own
        # high-grade fallback only ever rescued the narrower is_ego/is_artifact/
        # excellent-pseudo subset, so a plain masterwork spare rode in the pack
        # forever. Once a real weapon is wielded it is no longer needed for
        # re-arm and becomes ordinary spare_equipment.
        pol = HengbotPolicy()
        real_sword = item(
            "main_hand", 23, 0, is_equipment=True, known=True, name="sword"
        )
        spare = item(
            "b", 23, 0, is_equipment=True, known=True, to_h=5,
            name="masterwork spare",
        )

        self.assertIsNone(pol._find_home_deposit(self._town([spare], [real_sword])))

    def test_good_non_ego_spare_is_protected_while_digger_is_equipped(self):
        pol = HengbotPolicy()
        spare = item(
            "b", 23, 0, is_equipment=True, known=True, to_h=5,
            name="masterwork spare",
        )
        digger = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            is_equipment=True, known=True, name="Shovel",
        )

        self.assertIsNone(pol._find_home_deposit(self._town([spare], [digger])))

    def test_good_non_ego_spare_is_protected_with_nothing_wielded(self):
        pol = HengbotPolicy()
        spare = item(
            "b", 23, 0, is_equipment=True, known=True, to_h=5,
            name="masterwork spare",
        )

        self.assertIsNone(pol._find_home_deposit(self._town([spare], [])))

    def test_active_recall_is_not_cancelled_to_strand_uncompared_weapon(self):
        pol = HengbotPolicy()
        recall = item(
            "r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
            count=2, known=True, name="Word of Recall",
        )
        spare = item(
            "b", 23, 8, is_equipment=True, is_ego=True, known=True,
            name="ego spare",
        )
        snap = self._town([recall, spare], [self._ego()])
        snap = replace(snap, player=replace(snap.player, recalling=True))

        self.assertIsNone(pol._find_home_deposit(snap))
        self.assertIsNone(pol._town_cancel_unsafe_recall_key(snap))

    def test_active_recall_is_not_cancelled_only_because_scroll_was_consumed(self):
        pol = HengbotPolicy()
        recall = item(
            "r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
            count=1, known=True, name="Word of Recall",
        )
        snap = self._town([recall], [self._ego()])
        snap = replace(snap, player=replace(snap.player, recalling=True))

        self.assertIsNone(pol._town_cancel_unsafe_recall_key(snap))

    def test_routes_to_and_sells_at_weapon_smith(self):
        pol = HengbotPolicy()
        inf = self._inferior()
        self.assertEqual(
            pol._next_required_store_type(self._town([inf], [self._ego()])), STORE_WEAPON
        )
        snap = self._town([inf], [self._ego()], store=StoreState(STORE_WEAPON, []))
        self.assertEqual(pol._shop(snap), SELL_KEY + "b" + SELL_CONFIRM_SUFFIX)
        self.assertEqual(pol.last_reason, "shop:sell-inferior-weapon")

    def test_withdraws_stored_inferior_weapon_to_sell(self):
        pol = HengbotPolicy()
        home = StoreState(
            STORE_HOME,
            [store_item("z", 23, 0, price=0, name="spare", pseudo_feeling="good")],
        )
        snap = self._town([], [self._ego()], store=home)
        key = pol._shop(snap)
        self.assertEqual(pol.last_reason, "home:withdraw-inferior-weapon")
        self.assertTrue(key.startswith("pz"))  # BUY_KEY p + letter z

    def test_identified_mundane_spare_routes_and_sells(self):
        # Regression for the live miss: the character wielded an ego War Hammer but
        # kept an identified Short Sword (+0,+0) and Broad Sword (+0,+0) that carry
        # no pseudo_feeling, so they were never routed to the Weapon Smith.
        pol = HengbotPolicy()
        short = item("n", 23, 8, known=True, name="short sword")
        broad = item("o", 23, 16, known=True, name="broad sword")
        equip = [self._ego()]
        self.assertEqual(pol._find_weapon_sale(self._town([short, broad], equip)).slot, "n")
        self.assertEqual(
            pol._next_required_store_type(self._town([short, broad], equip)), STORE_WEAPON
        )
        snap = self._town([short, broad], equip, store=StoreState(STORE_WEAPON, []))
        self.assertEqual(pol._shop(snap), "{n@0\r{o@1\r")
        self.assertEqual(pol.last_reason, "shop:batch-inscribe")



class ItemShedListTest(unittest.TestCase):
    """User-flagged always-shed items — Resist Cold potion, Holy Chant scroll and
    Rod of Light — are sold in town (alchemist / magic shop) and destroyed when
    the pack is full, while useful lookalikes are kept."""

    def _snap(self, inventory):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 3, 0),
            inventory=inventory,
        )

    def test_disposable_flags(self):
        pol = HengbotPolicy()
        self.assertTrue(pol._is_disposable_item(item("b", TVAL_POTION, SV_POTION_RESIST_COLD)))
        self.assertTrue(pol._is_disposable_item(item("b", TVAL_SCROLL, SV_SCROLL_HOLY_CHANT)))
        self.assertTrue(pol._is_disposable_item(item("b", TVAL_ROD, SV_ROD_LITE)))
        # Useful lookalikes stay.
        self.assertFalse(pol._is_disposable_item(item("b", TVAL_POTION, SV_POTION_CURE_CRITICAL)))
        self.assertFalse(pol._is_disposable_item(item("b", TVAL_ROD, SV_ROD_IDENTIFY)))

    def test_alchemist_sells_potion_and_scroll(self):
        pol = HengbotPolicy()
        self.assertEqual(
            pol._find_low_level_sale(self._snap([item("b", TVAL_POTION, SV_POTION_RESIST_COLD)])).slot,
            "b",
        )
        self.assertEqual(
            pol._find_low_level_sale(self._snap([item("b", TVAL_SCROLL, SV_SCROLL_HOLY_CHANT)])).slot,
            "b",
        )

    def test_magic_shop_sells_light_rod_but_keeps_identify_rod(self):
        pol = HengbotPolicy()
        snap = self._snap(
            [
                item("b", TVAL_ROD, SV_ROD_IDENTIFY),  # useful -> kept
                item("c", TVAL_ROD, SV_ROD_LITE),      # redundant -> sold
            ]
        )
        sale = pol._find_device_sale(snap)
        self.assertIsNotNone(sale)
        self.assertEqual(sale.slot, "c")


class MiningGearHomeStorageTest(unittest.TestCase):
    """Treasure Detection scrolls and digging tools ride along only while
    fundraising (mining level 1); on a normal diving run they are stashed at
    home rather than hauled down as dead weight."""

    def test_deposited_when_not_fundraising(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = None
        self.assertTrue(
            pol._home_deposit_candidate(item("b", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE))
        )
        self.assertTrue(
            pol._home_deposit_candidate(item("b", TVAL_DIGGING, SV_DIGGING_SHOVEL))
        )

    def test_kept_while_fundraising(self):
        pol = HengbotPolicy()
        for mode in ("prepare", "mine", "scavenge"):
            pol._fundraising_mode = mode
            self.assertFalse(
                pol._home_deposit_candidate(item("b", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE)),
                f"treasure scroll should be kept in {mode}",
            )
            self.assertFalse(
                pol._home_deposit_candidate(item("b", TVAL_DIGGING, SV_DIGGING_SHOVEL)),
                f"digger should be kept in {mode}",
            )


class StuckEscapeTest(unittest.TestCase):
    """A dungeon floor whose stairs are walled off must not trap the bot: after
    enough consecutive last-resort wanders it Word-of-Recalls out. The streak is
    counted in _observe and reset by any other action or by reaching town."""

    def _dungeon(self):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 11, 0),
        )

    def _town(self):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )

    def test_streak_counts_the_whole_stuck_family(self):
        # Not just stuck:wander — searching for secret ways and breaking out of a
        # visited pocket count too, so a floor that mixes them still escapes.
        pol = HengbotPolicy()
        d = self._dungeon()
        for reason in ("stuck:wander", "search", "seek-secret-wall", "breakout:least-visited"):
            pol.last_reason = reason
            pol._observe(d)
        self.assertEqual(pol._stuck_escape_streak, 4)

    def test_streak_held_through_upkeep_between_searches(self):
        # Relighting / resting between searches must not reset the streak, or a
        # walled-off floor never accumulates enough to escape.
        pol = HengbotPolicy()
        d = self._dungeon()
        pol.last_reason = "search"; pol._observe(d)
        pol.last_reason = "refill-light"; pol._observe(d)
        pol.last_reason = "search"; pol._observe(d)
        self.assertEqual(pol._stuck_escape_streak, 2)

    def test_streak_resets_on_a_productive_action(self):
        pol = HengbotPolicy()
        pol._stuck_escape_streak = 7
        pol.last_reason = "explore"
        pol._observe(self._dungeon())
        self.assertEqual(pol._stuck_escape_streak, 0)

    def test_streak_resets_in_town(self):
        pol = HengbotPolicy()
        pol._stuck_escape_streak = 7
        pol.last_reason = "stuck:wander"
        pol._observe(self._town())
        self.assertEqual(pol._stuck_escape_streak, 0)

    def test_fundraise_digs_toward_upstairs_instead_of_teleporting(self):
        # Bouncing toward walled-off up-stairs while leaving a fundraising floor no
        # longer burns a Teleport scroll — the miner digs toward the stairs instead.
        teleport = item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=5)
        grids = {
            Position(10, 10): grid(10, 10),  # player
            Position(10, 11): grid(10, 11, passable=False, can_dig=True),  # rock toward stairs
            Position(10, 12): grid(10, 12, passable=False, upstairs=True, can_dig=True),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            inventory=[teleport],
            floor_key=(2, 1, 0),
        )
        pol = HengbotPolicy()
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT
        self.assertEqual(pol._leave_fundraising_floor(snap), TUNNEL_KEY + "6")
        self.assertEqual(pol.last_reason, "fundraise:tunnel-out")

    def test_stuck_digs_through_known_vein_to_downstairs_before_recall(self):
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        digger = item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True)
        sword = item("main_hand", 23, 1, name="Broad Sword", is_equipment=True)
        snap = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, passable=False, can_dig=True),
                Position(10, 12): grid(10, 12, downstairs=True),
            },
            [],
            inventory=[recall, digger],
            equipment=[sword],
            floor_key=(2, 8, 0),
        )
        pol = HengbotPolicy()
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        self.assertEqual(pol.choose_key(snap), "wdn")
        self.assertEqual(pol.last_reason, "breakout:wield-digging-tool")

        digging = replace(
            snap,
            inventory=[recall, replace(sword, slot="a")],
            equipment=[replace(digger, slot="main_hand")],
        )
        self.assertEqual(pol.choose_key(digging), TUNNEL_KEY + "6")
        self.assertEqual(pol.last_reason, "breakout:dig-to-stairs")

        opened = replace(
            digging,
            grids={
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, downstairs=True),
            },
        )
        self.assertEqual(pol.choose_key(opened), "wan")
        self.assertEqual(pol.last_reason, "breakout:restore-combat-weapon")

    def test_stuck_recall_escape_without_digging_tool(self):
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snap = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, passable=False, can_dig=True),
                Position(10, 12): grid(10, 12, downstairs=True),
            },
            [],
            inventory=[recall],
            floor_key=(2, 8, 0),
        )
        pol = HengbotPolicy()
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        self.assertEqual(pol.choose_key(snap), READ_KEY + "r")
        self.assertEqual(pol.last_reason, "stuck:recall-escape")

    def test_stuck_uses_walkable_downstairs_route_without_tunnelling(self):
        digger = item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True)
        snap = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, downstairs=True),
            },
            [],
            inventory=[digger],
            floor_key=(2, 8, 0),
        )
        pol = HengbotPolicy()
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        self.assertEqual(pol.choose_key(snap), "6")
        self.assertIn(pol.last_reason, {"seek-downstairs", "approach-descent"})
        self.assertFalse(pol.last_reason.startswith("breakout:dig"))

    def test_forgetting_maze_does_not_recall_on_stuck_streak(self):
        maze = DungeonInfo(
            4, "Labyrinth", 10, 18, 1,
            flags=frozenset({"MAZE", "FORGET"}),
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(4, 10, 0),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        pol = HengbotPolicy(dungeon_knowledge={4: maze})
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        key = pol.choose_key(snap)

        self.assertNotEqual(key, "rr")
        self.assertNotEqual(pol.last_reason, "stuck:recall-escape")

    def test_active_random_quest_does_not_recall_on_stuck_streak(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 6, 40),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        pol = HengbotPolicy()
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        key = pol.choose_key(snap)

        self.assertNotEqual(key, "rr")
        self.assertNotEqual(pol.last_reason, "stuck:recall-escape")

    def test_forgetting_maze_routes_to_a_remembered_downstairs(self):
        maze = DungeonInfo(
            4, "Labyrinth", 10, 18, 1,
            flags=frozenset({"MAZE", "FORGET"}),
        )
        visible = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, downstairs=True),
            },
            [],
            floor_key=(4, 10, 0),
        )
        forgotten = replace(
            visible,
            grids={
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
            },
        )
        pol = HengbotPolicy(dungeon_knowledge={4: maze})
        pol._build_grid_index(visible)
        pol._build_grid_index(forgotten)

        self.assertEqual(pol._descent_step(forgotten), Position(10, 11))
        self.assertEqual(pol.last_reason, "seek-downstairs")

    def test_forgetting_maze_moves_instead_of_searching_each_corridor_tile(self):
        maze = DungeonInfo(
            4, "Labyrinth", 10, 18, 1,
            flags=frozenset({"MAZE", "FORGET"}),
        )
        center = Position(10, 10)
        east = Position(10, 11)
        grids = {center: grid(10, 10), east: grid(10, 11)}
        for dy, dx in (
            (-1, -1), (-1, 0), (-1, 1),
            (0, -1), (0, 1),
            (1, -1), (1, 0), (1, 1),
        ):
            pos = Position(10 + dy, 10 + dx)
            if pos not in grids:
                grids[pos] = grid(pos.y, pos.x, passable=False)
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(4, 18, 0),
        )
        pol = HengbotPolicy(dungeon_knowledge={4: maze})
        pol._recent.extend([center] * STUCK_WINDOW)
        pol._should_start_town_return = lambda _snapshot: False
        pol._return_to_town_key = lambda _snapshot, _hostiles: None

        self.assertEqual(pol.choose_key(snap), "6")
        self.assertNotEqual(pol.last_reason, "search")
        self.assertEqual(pol._search_counts[center.y, center.x], 0)


class TownWanderCircuitBreakerTest(unittest.TestCase):
    """A town-only mirror of StuckEscapeTest: town positions vary across most
    of the map, so cli's position-based loop guard never catches a bot that is
    only ever wandering (a live logic deadlock paced town for 2 real hours
    before anyone noticed — see jsonlog/codex-stuck-investigation-2026-07-15.md).
    After TOWN_WANDER_LIMIT consecutive non-productive-wander decisions in
    town, enter the bounded town-cycle repair path so the first offense forces
    departure and a repeated failure stops the bot visibly."""

    def _dungeon(self):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 11, 0),
        )

    def _town(self):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )

    def test_streak_counts_both_wander_reasons_in_town(self):
        pol = HengbotPolicy()
        t = self._town()
        for reason in ("stuck:wander", "breakout:least-visited"):
            pol.last_reason = reason
            pol._observe(t)
        self.assertEqual(pol._town_wander_streak, 2)
        self.assertIsNone(pol._town_blocked_reason)

    def test_sixty_consecutive_wanders_force_departure_cycle_break(self):
        pol = HengbotPolicy()
        t = self._town()
        for _ in range(TOWN_WANDER_LIMIT):
            pol.last_reason = "stuck:wander"
            pol._observe(t)
        self.assertEqual(pol._town_wander_streak, TOWN_WANDER_LIMIT)
        self.assertTrue(pol._town_cycle_pending)
        self.assertEqual(pol._town_special_key(t), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:cycle-break")
        self.assertTrue(pol._town_restock_suppressed)
        self.assertIsNone(pol._next_required_store_type(t))

    def test_cycle_break_resets_generic_no_progress_debt_before_entrance_walk(self):
        pol = HengbotPolicy()
        t = self._town()
        for step in range(TOWN_WANDER_LIMIT):
            pol.last_reason = "stuck:wander"
            pol._observe(
                replace(t, player=replace(t.player, position=Position(10, 10 + step)))
            )

        self.assertTrue(pol._town_cycle_pending)
        self.assertEqual(pol._town_special_key(t), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:cycle-break")

        # The live entrance leg needed exactly the residual 96 - 60 decisions.
        # They are productive locomotion and must not be mistaken for a second
        # offense merely because the first detector's counter was retained.
        for step in range(TOWN_NO_PROGRESS_LIMIT - TOWN_WANDER_LIMIT):
            pol.last_reason = "seek-downstairs"
            pol._observe(
                replace(t, player=replace(t.player, position=Position(10, 70 + step)))
            )

        self.assertFalse(pol._town_cycle_pending)
        self.assertIsNone(pol._town_blocked_reason)
        self.assertEqual(
            pol._town_no_progress_count,
            TOWN_NO_PROGRESS_LIMIT - TOWN_WANDER_LIMIT,
        )

    def test_second_wander_limit_after_break_stops_visibly(self):
        pol = HengbotPolicy()
        t = self._town()
        pol._town_cycle_breaks = 1
        for _ in range(TOWN_WANDER_LIMIT):
            pol.last_reason = "stuck:wander"
            pol._observe(t)
        self.assertEqual(pol._town_special_key(t), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:blocked:repetition")

    def test_productive_decision_at_fifty_nine_resets_the_streak(self):
        pol = HengbotPolicy()
        t = self._town()
        for _ in range(TOWN_WANDER_LIMIT - 1):
            pol.last_reason = "stuck:wander"
            pol._observe(t)
        self.assertEqual(pol._town_wander_streak, TOWN_WANDER_LIMIT - 1)

        pol.last_reason = "shop:approach"  # any ordinary, productive reason
        pol._observe(t)

        self.assertEqual(pol._town_wander_streak, 0)
        self.assertIsNone(pol._town_blocked_reason)

    def test_never_fires_in_a_dungeon(self):
        pol = HengbotPolicy()
        d = self._dungeon()
        for _ in range(TOWN_WANDER_LIMIT + 5):
            pol.last_reason = "stuck:wander"
            pol._observe(d)
        self.assertEqual(pol._town_wander_streak, 0)
        self.assertIsNone(pol._town_blocked_reason)

    def test_streak_and_latch_reset_on_floor_change(self):
        pol = HengbotPolicy()
        t = self._town()
        for _ in range(TOWN_WANDER_LIMIT):
            pol.last_reason = "stuck:wander"
            pol._observe(t)
        self.assertTrue(pol._town_cycle_pending)

        pol.last_reason = "descend"
        pol._observe(self._dungeon())

        self.assertEqual(pol._town_wander_streak, 0)
        self.assertIsNone(pol._town_blocked_reason)
        self.assertFalse(pol._town_cycle_pending)


class StoreAttemptExpiryTest(unittest.TestCase):
    """A store visited once with nothing to buy/sell latches into
    _town_store_attempted (a dict of store_type -> the game turn it was
    latched at) for the rest of the town stay. The only OTHER reset is the
    fresh-town-visit reset in _observe, which never runs if the bot never
    departs -- during the 2026-07-15 incident's 2-hour town stay, supplies
    (oil, teleport scrolls) kept draining with no store ever re-attempted.
    Each latch now also expires on its own schedule during ordinary in-town
    _observe ticks, independent of any floor change."""

    def _town(self, turn):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            turn=turn,
        )

    def _already_in_town_policy(self):
        # Prime _floor_key to (0, 0, 0) so the fresh-town-visit reset (a
        # SEPARATE mechanism, exercised by its own test below) does not also
        # clear _town_store_attempted and confound what is being isolated here.
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        return pol

    def test_latch_is_still_skipped_just_before_the_retry_window(self):
        pol = self._already_in_town_policy()
        pol._town_store_attempted[STORE_GENERAL] = 1000

        pol._observe(self._town(1000 + STORE_RETRY_TURNS - 1))  # T+4999

        self.assertIn(STORE_GENERAL, pol._town_store_attempted)

    def test_latch_expires_just_after_the_retry_window(self):
        pol = self._already_in_town_policy()
        pol._town_store_attempted[STORE_GENERAL] = 1000

        pol._observe(self._town(1000 + STORE_RETRY_TURNS + 1))  # T+5001

        self.assertNotIn(STORE_GENERAL, pol._town_store_attempted)

    def test_only_the_individually_expired_store_is_dropped(self):
        pol = self._already_in_town_policy()
        pol._town_store_attempted[STORE_GENERAL] = 1000
        pol._town_store_attempted[STORE_ALCHEMIST] = 1000 + STORE_RETRY_TURNS

        pol._observe(self._town(1000 + STORE_RETRY_TURNS + 1))

        self.assertNotIn(STORE_GENERAL, pol._town_store_attempted)
        self.assertIn(STORE_ALCHEMIST, pol._town_store_attempted)

    def test_fresh_town_visit_still_clears_every_latch(self):
        pol = HengbotPolicy()
        pol._town_store_attempted[STORE_GENERAL] = 1000
        pol._town_store_attempted[STORE_ALCHEMIST] = 1000
        pol._floor_key = (1, 5, 0)  # was in the dungeon last observation

        pol._observe(self._town(1050))  # arriving back at town: a floor change

        self.assertEqual(pol._town_store_attempted, {})


class StatRestoreTest(unittest.TestCase):
    """Drained-stat recovery: quaff a carried Restore-* potion when safe, and when
    none is carried route to the Alchemist and buy the matching potion."""

    def _snap(self, *, inventory=(), store=None, drained=(), hostiles=()):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=2000, drained_stats=drained),
            {Position(10, 10): grid(10, 10)},
            list(hostiles),
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inventory),
            store=store,
        )

    def test_quaffs_a_carried_restore_potion_for_the_drained_stat(self):
        inv = [
            item("a", TVAL_POTION, SV_POTION_RESTORE_CON, name="Restore Con"),
            item("b", TVAL_POTION, SV_POTION_RESTORE_STR, name="Restore Str"),
        ]
        pol = HengbotPolicy()
        snap = self._snap(inventory=inv, drained=("str",))
        self.assertEqual(pol._stat_restore_quaff_key(snap, []), "qb")
        self.assertEqual(pol.last_reason, "restore:quaff-str")

    def test_no_quaff_while_hostiles_are_present(self):
        inv = [item("b", TVAL_POTION, SV_POTION_RESTORE_STR)]
        hostile = MonsterState(
            index=1, position=Position(9, 10), hp=10, max_hp=10, distance=1,
            friendly=False, pet=False, speed=110,
        )
        pol = HengbotPolicy()
        snap = self._snap(inventory=inv, drained=("str",), hostiles=[hostile])
        self.assertIsNone(pol._stat_restore_quaff_key(snap, [hostile]))

    def test_ignores_unaware_restore_potions(self):
        # Fair-play: an unidentified potion has no emitted sval, so it is not yet
        # actionable even if it happens to be a restore potion.
        inv = [item("b", TVAL_POTION, SV_POTION_RESTORE_STR, aware=False)]
        pol = HengbotPolicy()
        snap = self._snap(inventory=inv, drained=("str",))
        self.assertIsNone(pol._stat_restore_quaff_key(snap, []))

    def test_needs_restore_routes_to_the_alchemist(self):
        pol = HengbotPolicy()
        snap = self._snap(drained=("con",))
        self.assertTrue(pol._needs_stat_restore(snap))
        # Poverty now activates fundraising before ordinary stat restoration,
        # securing the income kit at Home first; the restore errand remains in
        # the same batched plan.
        self.assertEqual(pol._next_required_store_type(snap), STORE_HOME)
        self.assertIn(STORE_ALCHEMIST, pol._town_errand_plan.stops)

    def test_carrying_the_potion_removes_the_alchemist_errand(self):
        inv = [item("a", TVAL_POTION, SV_POTION_RESTORE_CON)]
        pol = HengbotPolicy()
        snap = self._snap(inventory=inv, drained=("con",))
        self.assertFalse(pol._needs_stat_restore(snap))

    def test_buys_the_matching_restore_potion_at_the_alchemist(self):
        store = StoreState(
            store_type=STORE_ALCHEMIST,
            items=[
                store_item("h", TVAL_POTION, SV_POTION_RESTORE_STR, price=300, name="Restore Str"),
                store_item("i", TVAL_POTION, SV_POTION_RESTORE_CON, price=300, name="Restore Con"),
            ],
        )
        pol = HengbotPolicy()
        snap = self._snap(store=store, drained=("con",))
        bought = pol._restore_potion_purchase(snap)
        self.assertIsNotNone(bought)
        self.assertEqual(bought.sval, SV_POTION_RESTORE_CON)

    def test_does_not_rebuy_a_restore_potion_already_carried(self):
        store = StoreState(
            store_type=STORE_ALCHEMIST,
            items=[store_item("i", TVAL_POTION, SV_POTION_RESTORE_CON, price=300)],
        )
        inv = [item("a", TVAL_POTION, SV_POTION_RESTORE_CON)]
        pol = HengbotPolicy()
        snap = self._snap(inventory=inv, store=store, drained=("con",))
        self.assertIsNone(pol._restore_potion_purchase(snap))


class ArmorDominanceTest(unittest.TestCase):
    """Armour is ranked by DEFENSE (base AC + magic AC), never vetoed by the to-hit
    penalty that heavier armour carries."""

    def test_higher_ac_dominates_despite_a_worse_to_hit(self):
        heavy = item("k", 36, 4, ac=16, to_a=7, to_h=-2)     # Heavy Chain [16,+7] = 23
        leather = item("l", 36, 2, ac=11, to_a=-5, to_h=-1)  # Leather Scale [11,-5] = 6
        self.assertTrue(HengbotPolicy()._equipment_dominates(heavy, leather))
        self.assertFalse(HengbotPolicy()._equipment_dominates(leather, heavy))


class StatGainTest(unittest.TestCase):
    """Permanent stat-gain potions (Strength ... Augmentation) are drunk on sight."""

    def _snap(self, inventory, hostiles=()):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            list(hostiles),
            floor_key=(DUNGEON_YEEK_CAVE, 3, 0),
            inventory=list(inventory),
        )

    def test_quaffs_a_strength_potion_on_sight(self):
        inv = [item("k", TVAL_POTION, SV_POTION_INC_STR, name="Strength")]
        pol = HengbotPolicy()
        self.assertEqual(pol._stat_gain_quaff_key(self._snap(inv), []), "qk")
        self.assertEqual(pol.last_reason, "stat-gain:quaff")

    def test_quaffs_augmentation(self):
        inv = [item("k", TVAL_POTION, SV_POTION_AUGMENTATION)]
        self.assertEqual(HengbotPolicy()._stat_gain_quaff_key(self._snap(inv), []), "qk")

    def test_no_quaff_with_hostiles(self):
        inv = [item("k", TVAL_POTION, SV_POTION_INC_STR)]
        h = MonsterState(index=1, position=Position(9, 10), hp=5, max_hp=5, distance=1,
                         friendly=False, pet=False, speed=110)
        self.assertIsNone(HengbotPolicy()._stat_gain_quaff_key(self._snap(inv, [h]), [h]))

    def test_ignores_unaware_gain_potion(self):
        inv = [item("k", TVAL_POTION, SV_POTION_INC_STR, aware=False)]
        self.assertIsNone(HengbotPolicy()._stat_gain_quaff_key(self._snap(inv), []))

    def test_gain_potion_is_drunk_through_the_full_decision(self):
        inv = [item("k", TVAL_POTION, SV_POTION_INC_STR)]
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(self._snap(inv)), "qk")
        self.assertEqual(pol.last_reason, "stat-gain:quaff")


class IdleItemDepositTest(unittest.TestCase):
    """An identified non-consumable item carried unused through UNUSED_DIVE_LIMIT
    whole dives becomes a Home-deposit candidate; using it (its carried count drops)
    resets that, and consumables / devices / survival kit are never idle-stashed."""

    JUNK_TVAL = 2  # empty bottle: aware, non-consumable, non-equipment dead weight

    def _dungeon(self, inv):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=list(inv),
        )

    def _town(self, inv):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inv),
        )

    def _dive(self, pol, start_inv, end_inv=None):
        # town -> dungeon(begin) -> dungeon(step) -> town(end). A lower count in
        # end_inv than start_inv reads as the item being used (consumed) this dive.
        end_inv = start_inv if end_inv is None else end_inv
        pol._track_idle_items(self._dungeon(start_inv), (0, 0, 0))  # dive begins
        pol._track_idle_items(self._dungeon(end_inv), (DUNGEON_YEEK_CAVE, 1, 0))  # step
        pol._track_idle_items(self._town(end_inv), (DUNGEON_YEEK_CAVE, 1, 0))  # dive ends

    def test_unused_item_becomes_a_deposit_candidate_after_the_limit(self):
        pol = HengbotPolicy()
        junk = item("k", self.JUNK_TVAL, 0, name="empty bottle")
        for _ in range(UNUSED_DIVE_LIMIT - 1):
            self._dive(pol, [junk])
        self.assertFalse(pol._home_deposit_candidate(junk))  # not idle long enough yet
        self._dive(pol, [junk])  # reaches UNUSED_DIVE_LIMIT
        self.assertTrue(pol._home_deposit_candidate(junk))

    def test_using_the_item_resets_the_idle_count(self):
        pol = HengbotPolicy()
        junk2 = item("k", self.JUNK_TVAL, 0, count=2, name="empty bottle")
        junk1 = item("k", self.JUNK_TVAL, 0, count=1, name="empty bottle")
        self._dive(pol, [junk2])  # idle 1
        self._dive(pol, [junk2])  # idle 2
        self._dive(pol, [junk2], end_inv=[junk1])  # consumed one -> used -> reset
        self.assertEqual(pol._item_idle_dives.get(("empty bottle", self.JUNK_TVAL, 0)), 0)
        self.assertFalse(pol._home_deposit_candidate(junk2))

    def test_survival_kit_and_charged_devices_stay_but_low_use_is_stashed(self):
        # Narrowed protection: the survival kit and a CHARGED device stay; low-use
        # identified consumables (a resist / cure-light potion, an enchant / light
        # scroll) go once idle — the items the user flagged that were wrongly kept.
        pol = HengbotPolicy()
        protected = [
            item("c", TVAL_STAFF, 5, charges=9, name="Identify"),  # charged device
            item("d", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, name="Recall"),  # survival
        ]
        low_use = [
            item("a", TVAL_POTION, 34, name="Cure Light"),  # non-essential potion
            item("b", TVAL_SCROLL, 24, name="Light"),       # non-essential scroll
        ]
        for _ in range(UNUSED_DIVE_LIMIT + 1):
            self._dive(pol, protected + low_use)
        for it in protected:
            self.assertFalse(pol._home_deposit_candidate(it), it.name)
        for it in low_use:
            self.assertTrue(pol._home_deposit_candidate(it), it.name)

    def test_a_depleted_wand_is_stashed_immediately(self):
        # 0-charge wand = pure junk (no utility, no MANA charge-food) -> deposit at
        # once, without waiting out the idle counter.
        dead_wand = item("k", TVAL_WAND, 0, charges=0, name="Magic Missile (0)")
        self.assertTrue(HengbotPolicy()._home_deposit_candidate(dead_wand))

    def test_surplus_digging_tools_are_stashed_keeping_one(self):
        # Fundraising needs ONE digger; the rest are dead weight (the 5-slot haul the
        # user saw). Keep the best, stash the others.
        pol = HengbotPolicy()
        diggers = [
            item("a", TVAL_DIGGING, 1, name="Shovel"),
            item("b", TVAL_DIGGING, 4, name="Pick"),
            item("c", TVAL_DIGGING, 7, name="Mattock"),  # highest sval -> the keeper
        ]
        snap = self._town(diggers)
        surplus = [it for it in diggers if pol._is_surplus_digging_tool(snap, it)]
        self.assertEqual({it.slot for it in surplus}, {"a", "b"})  # keep "c"
        self.assertFalse(pol._is_surplus_digging_tool(snap, diggers[2]))

    def test_surplus_diggers_keep_dwarven_shovel_over_plain_pick(self):
        pol = HengbotPolicy()
        dwarven_shovel = item(
            "a", TVAL_DIGGING, 3, name="Dwarven Shovel", pval=3
        )
        plain_pick = item("b", TVAL_DIGGING, 4, name="Pick", pval=1)
        snap = self._town([dwarven_shovel, plain_pick])

        self.assertFalse(pol._is_surplus_digging_tool(snap, dwarven_shovel))
        self.assertTrue(pol._is_surplus_digging_tool(snap, plain_pick))

    def test_surplus_diggers_prefer_ego_when_digging_power_is_equal(self):
        pol = HengbotPolicy()
        ego_shovel = item(
            "a", TVAL_DIGGING, 1, name="Shovel of Digging", pval=3, is_ego=True
        )
        dwarven_shovel = item(
            "b", TVAL_DIGGING, 3, name="Dwarven Shovel", pval=3
        )
        snap = self._town([ego_shovel, dwarven_shovel])

        self.assertFalse(pol._is_surplus_digging_tool(snap, ego_shovel))
        self.assertTrue(pol._is_surplus_digging_tool(snap, dwarven_shovel))


class ResistanceDepthGateTest(unittest.TestCase):
    """The depth-requirement table (AGENTS.md) gates descent and steers equipment:
    never descend into a band whose mandatory resistances the character lacks, and
    prefer jewelry that closes a required-resistance gap."""

    def _at(self, depth, abilities, inventory=(), equipment=(), speed=110):
        return Snapshot(
            player(
                10, 10, class_id=PLAYER_CLASS_WARRIOR,
                abilities=frozenset(abilities), speed=speed,
            ),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(DUNGEON_ANGBAND, depth, 0),
            inventory=list(inventory),
            equipment=list(equipment),
        )

    def test_blocks_descent_without_the_required_resistance(self):
        snap = self._at(24, set())  # 24F -> 25F needs confusion + fire
        self.assertFalse(
            HengbotPolicy()._is_descent_target(snap, snap.grids[Position(10, 10)])
        )

    def test_allows_descent_once_the_requirement_is_met(self):
        snap = self._at(24, {"resist_conf", "resist_fire"})
        self.assertTrue(
            HengbotPolicy()._is_descent_target(snap, snap.grids[Position(10, 10)])
        )

    def test_shallow_floors_need_no_resistance(self):
        snap = self._at(5, set())
        self.assertTrue(
            HengbotPolicy()._is_descent_target(snap, snap.grids[Position(10, 10)])
        )

    def test_reports_the_missing_abilities_for_a_band(self):
        snap = self._at(30, {"resist_pois"})  # 26-30F needs pois+cold+elec+acid
        self.assertEqual(
            HengbotPolicy()._missing_required_abilities(snap, 30),
            frozenset({"resist_cold", "resist_elec", "resist_acid"}),
        )

    def test_50f_also_requires_a_destruction_method(self):
        # AGENTS.md: from 50F a usable *Destruction* method is mandatory on top
        # of the resistance table; it is not a player.abilities flag.
        abilities = {"resist_chaos", "resist_neth", "telepathy"}
        snap = self._at(49, abilities)  # 49F -> 50F
        self.assertEqual(
            HengbotPolicy()._missing_required_abilities(snap, 50),
            frozenset({"destruction"}),
        )
        self.assertFalse(
            HengbotPolicy()._is_descent_target(snap, snap.grids[Position(10, 10)])
        )

    def test_destruction_scroll_or_charged_staff_satisfies_the_50f_gate(self):
        abilities = {"resist_chaos", "resist_neth", "telepathy"}
        scroll = self._at(
            49, abilities,
            inventory=[item("s", TVAL_SCROLL, SV_SCROLL_STAR_DESTRUCTION)],
        )
        self.assertEqual(
            HengbotPolicy()._missing_required_abilities(scroll, 50), frozenset()
        )
        self.assertTrue(
            HengbotPolicy()._is_descent_target(scroll, scroll.grids[Position(10, 10)])
        )
        charged = self._at(
            49, abilities,
            inventory=[item("u", TVAL_STAFF, SV_STAFF_DESTRUCTION, charges=2)],
        )
        self.assertEqual(
            HengbotPolicy()._missing_required_abilities(charged, 50), frozenset()
        )
        empty_staff = self._at(
            49, abilities,
            inventory=[item("u", TVAL_STAFF, SV_STAFF_DESTRUCTION, charges=0)],
        )
        self.assertEqual(
            HengbotPolicy()._missing_required_abilities(empty_staff, 50),
            frozenset({"destruction"}),
        )

    def test_81f_also_requires_speed_plus_25(self):
        abilities = {"resist_chaos", "resist_neth", "telepathy"}
        kit = [item("s", TVAL_SCROLL, SV_SCROLL_STAR_DESTRUCTION)]
        slow = self._at(80, abilities, inventory=kit)  # base speed 110
        self.assertEqual(
            HengbotPolicy()._missing_required_abilities(slow, 81),
            frozenset({"speed+25"}),
        )
        fast = self._at(80, abilities, inventory=kit, speed=135)
        self.assertEqual(
            HengbotPolicy()._missing_required_abilities(fast, 81), frozenset()
        )


class WieldHandSuffixTest(unittest.TestCase):
    """do_cmd_wield raises a different prompt depending on hand occupancy: both
    hands full -> "Equip which hand?" (equipment letter a/b); exactly one hand
    holding something -> "Dual wielding? [y/n]" (y = free hand, n = replace the
    occupied one). The wield macro must answer exactly the prompt that will
    appear, or the key stream stalls at the prompt until a nudge Escape."""

    @staticmethod
    def _snap(equipment):
        return Snapshot(
            player(10, 10),
            {},
            [],
            floor_key=(DUNGEON_ANGBAND, 5, 0),
            inventory=[],
            equipment=equipment,
        )

    @staticmethod
    def _weapon(slot):
        return item(
            slot, TVAL_SWORD, 4, is_equipment=True,
            damage_dice_num=1, damage_dice_sides=6,
        )

    @staticmethod
    def _shield(slot):
        return item(slot, 34, 3, is_equipment=True)  # TV_SHIELD

    def test_both_hands_full_answers_the_which_hand_prompt(self):
        snap = self._snap([self._weapon("main_hand"), self._shield("sub_hand")])
        self.assertEqual(HengbotPolicy._wield_hand_suffix(snap, "main_hand"), "a")
        self.assertEqual(HengbotPolicy._wield_hand_suffix(snap, "sub_hand"), "b")

    def test_occupied_main_with_free_sub_answers_the_dual_wield_prompt(self):
        snap = self._snap([self._weapon("main_hand")])
        self.assertEqual(HengbotPolicy._wield_hand_suffix(snap, "main_hand"), "n")
        self.assertEqual(HengbotPolicy._wield_hand_suffix(snap, "sub_hand"), "y")

    def test_sub_hand_weapon_with_free_main_answers_the_dual_wield_prompt(self):
        snap = self._snap([self._weapon("sub_hand")])
        self.assertEqual(HengbotPolicy._wield_hand_suffix(snap, "main_hand"), "y")
        self.assertEqual(HengbotPolicy._wield_hand_suffix(snap, "sub_hand"), "n")

    def test_free_hands_or_a_lone_shield_raise_no_prompt(self):
        self.assertEqual(
            HengbotPolicy._wield_hand_suffix(self._snap([]), "main_hand"), ""
        )
        lone_shield = self._snap([self._shield("sub_hand")])
        self.assertEqual(
            HengbotPolicy._wield_hand_suffix(lone_shield, "main_hand"), ""
        )


class ThreatPredictionMemoTest(unittest.TestCase):
    """One decision asks for the same threat prediction up to six times (the
    emergency/return gates plus the decision-log telemetry); the memo must hand
    back the identical result instead of paying the aggregate-p95 convolution
    again, and must never carry a result across snapshots."""

    @staticmethod
    def _snap(threat):
        return Snapshot(
            player(10, 10),
            {},
            [threat],
            floor_key=(DUNGEON_ANGBAND, 30, 0),
            inventory=[],
            equipment=[],
        )

    def test_repeat_calls_for_one_snapshot_reuse_the_result(self):
        threat = hostile(
            1, 10, 12, hp=30, max_hp=30, distance=2,
            max_melee_damage=10, max_ranged_damage=6,
        )
        snap = self._snap(threat)
        pol = HengbotPolicy()
        first = pol.threat_prediction(snap, [threat])
        self.assertIs(pol.threat_prediction(snap, [threat]), first)
        # A different horizon is a different prediction, not a memo hit.
        self.assertIsNot(pol.threat_prediction(snap, [threat], turns=1), first)

    def test_a_new_snapshot_is_recomputed(self):
        threat = hostile(1, 10, 12, hp=30, max_hp=30, distance=2, max_melee_damage=10)
        one = self._snap(threat)
        two = self._snap(threat)
        pol = HengbotPolicy()
        self.assertIsNot(
            pol.threat_prediction(one, [threat]),
            pol.threat_prediction(two, [threat]),
        )


class AggregateRangedCacheTest(unittest.TestCase):
    """_aggregate_ranged_percentile keys the expensive convolution on its actual
    inputs, so an unchanged engagement (same race, actions, distance, player
    profile) is computed once and reused ACROSS decisions. player_hp is in the
    key only for HAND_DOOM races; for everyone else an HP change must still
    hit the cache (the standoff/kite case the cache exists for)."""

    KNOWLEDGE = MonraceKnowledge(
        max_hp=48,
        average_hp=30,
        speed=110,
        can_summon=False,
        friendly=False,
        level=12,
        max_melee_damage=8,
        max_ranged_damage=98,
        abilities=frozenset({"BA_POIS", "BLINK", "CONF", "SLOW", "S_MONSTER"}),
        spell_frequency=25,
    )
    DOOM_KNOWLEDGE = MonraceKnowledge(
        max_hp=200,
        average_hp=150,
        speed=110,
        can_summon=False,
        friendly=False,
        level=40,
        max_melee_damage=8,
        max_ranged_damage=90,
        abilities=frozenset({"HAND_DOOM"}),
        spell_frequency=25,
    )

    @staticmethod
    def _monster(x=12, distance=2):
        return replace(
            hostile(
                1, 10, x, distance=distance,
                max_melee_damage=8, max_ranged_damage=98,
            ),
            race_id=224,
        )

    @staticmethod
    def _snap(monster, hp=30):
        grids = {
            Position(10, x): grid(10, x, monster=(x == monster.position.x))
            for x in range(10, monster.position.x + 1)
        }
        return Snapshot(
            player(10, 10, hp=hp, max_hp=100),
            grids,
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=[],
        )

    def _count_aggregate_calls(self, pol, engagements):
        from unittest import mock

        from hengbot.monster_ranged_evaluator import (
            aggregate_ranged_damage_percentile as real_aggregate,
        )

        with mock.patch(
            "hengbot.policy.aggregate_ranged_damage_percentile",
            wraps=real_aggregate,
        ) as agg:
            for snap, monster in engagements:
                pol.threat_prediction(snap, [monster])
        return agg.call_count

    def test_identical_engagement_across_snapshots_computes_once(self):
        pol = HengbotPolicy(monrace_knowledge={224: self.KNOWLEDGE})
        first, second = self._monster(), self._monster()
        hurt = self._monster()
        calls = self._count_aggregate_calls(
            pol,
            [
                (self._snap(first), first),
                (self._snap(second), second),
                # Player HP changed but the race has no HAND_DOOM: still a hit.
                (self._snap(hurt, hp=15), hurt),
            ],
        )
        self.assertEqual(calls, 1)

    def test_distance_change_recomputes(self):
        pol = HengbotPolicy(monrace_knowledge={224: self.KNOWLEDGE})
        near, far = self._monster(), self._monster(x=14, distance=4)
        calls = self._count_aggregate_calls(
            pol, [(self._snap(near), near), (self._snap(far), far)]
        )
        self.assertEqual(calls, 2)

    def test_hand_of_doom_keys_on_player_hp(self):
        pol = HengbotPolicy(monrace_knowledge={224: self.DOOM_KNOWLEDGE})
        healthy, hurt = self._monster(), self._monster()
        calls = self._count_aggregate_calls(
            pol,
            [(self._snap(healthy, hp=90), healthy), (self._snap(hurt, hp=45), hurt)],
        )
        self.assertEqual(calls, 2)


class ScavengeStoreLatchTest(unittest.TestCase):
    """Leaving the Alchemist with nothing to sell used to flip scavenge->prepare
    AND blanket-clear _town_store_attempted. With unchanged gold the router then
    re-picked the same out-of-stock stores — an Alchemist<->Magic native-travel
    ping-pong the loop guard cannot see (store snapshots reset it and travel
    keeps the position changing). The latches may only be re-checked when the
    scavenge pass actually raised gold."""

    def _alchemist_snapshot(self, gold):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=gold),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[],
            equipment=[],
            store=StoreState(store_type=STORE_ALCHEMIST, items=[]),
        )

    def _scavenging_policy(self, entry_gold):
        pol = HengbotPolicy()
        pol._fundraising_mode = "scavenge"
        pol._scavenge_entry_gold = entry_gold
        pol._town_store_attempted = {STORE_ALCHEMIST: 100, STORE_GENERAL: 100}
        return pol

    def test_no_sale_keeps_the_store_latches(self):
        pol = self._scavenging_policy(entry_gold=376)
        key = pol._shop(self._alchemist_snapshot(gold=376))
        self.assertEqual(key, LEAVE_STORE_KEY)
        self.assertEqual(pol._fundraising_mode, "prepare")
        self.assertIn(STORE_GENERAL, pol._town_store_attempted)

    def test_raised_gold_rechecks_the_stores(self):
        pol = self._scavenging_policy(entry_gold=376)
        pol._shop(self._alchemist_snapshot(gold=900))
        self.assertEqual(pol._fundraising_mode, "prepare")
        self.assertNotIn(STORE_GENERAL, pol._town_store_attempted)


class HomeVisitOwnershipTest(unittest.TestCase):
    """Inside Home, an active equipment-transaction session must run BEFORE the
    dominated-disposal leave. The disposal Esc used to preempt the session, whose
    town-side dispatcher then walked straight back in — an in/out bounce at the
    Home door that the harness loop guard cannot see (store snapshots reset it)."""

    def _home_snapshot(self, inventory):
        return Snapshot(
            player(45, 123),
            {Position(45, 123): grid(45, 123)},
            [],
            floor_key=(0, 0, 0),
            inventory=inventory,
            equipment=[],
            store=StoreState(store_type=STORE_HOME, items=[]),
        )

    @staticmethod
    def _dominated(pol, snap, item_obj):
        pol._pending_disposal_item = pol._item_signature(item_obj)
        pol._pending_disposal_slot = item_obj.slot
        return pol

    def test_active_home_transaction_preempts_the_disposal_leave(self):
        from unittest import mock

        sword = item("d", TVAL_SWORD, 4, is_equipment=True, name="old sword")
        snap = self._home_snapshot([sword])
        pol = self._dominated(HengbotPolicy(), snap, sword)
        with mock.patch.object(
            pol, "_equipment_transaction_home_key", return_value="dj"
        ):
            self.assertEqual(pol._shop(snap), "dj")

    def test_disposal_leave_resumes_once_the_session_is_done(self):
        sword = item("d", TVAL_SWORD, 4, is_equipment=True, name="old sword")
        snap = self._home_snapshot([sword])
        pol = self._dominated(HengbotPolicy(), snap, sword)
        # No session at all: _equipment_transaction_home_key returns None.
        key = pol._shop(snap)
        self.assertEqual(pol.last_reason, "home:leave-with-dominated")
        self.assertEqual(key, LEAVE_STORE_KEY)


class TownCycleDetectorTest(unittest.TestCase):
    """User directive: auto-detect and repair town repetition loops as a CLASS.
    Every observed shape (Home-door bounce, store-to-store travel ping-pong)
    collapses to a handful of (reason, position) signatures with zero
    gold/pack/equipment progress — while staying invisible to the cell-based
    loop guard (store snapshots reset it; travel keeps the position moving)."""

    @staticmethod
    def _town_snap(y=34, x=94, gold=100):
        return Snapshot(
            player(y, x, class_id=PLAYER_CLASS_WARRIOR, gold=gold),
            {Position(y, x): grid(y, x)},
            [],
            floor_key=(0, 0, 0),
            inventory=[],
            equipment=[],
        )

    @staticmethod
    def _prime_cycle(pol):
        cycle = [
            ("shop:travel", 37, 91),
            ("shop:approach", 31, 77),
            ("shop:leave", 31, 77),
            ("shop:travel", 31, 77),
            ("shop:approach", 37, 91),
            ("shop:leave", 37, 91),
        ]
        for i in range(TOWN_CYCLE_WINDOW):
            pol._town_signature_history.append(cycle[i % len(cycle)])

    def test_cycle_detected_over_a_full_window(self):
        pol = HengbotPolicy()
        self._prime_cycle(pol)
        self.assertTrue(pol._town_cycle_detected())

    def test_varied_town_activity_is_not_a_cycle(self):
        pol = HengbotPolicy()
        for i in range(TOWN_CYCLE_WINDOW):
            pol._town_signature_history.append(("shop:approach", 30, i))
        self.assertFalse(pol._town_cycle_detected())

    def test_varied_three_store_carousel_hits_no_progress_limit(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        reasons = ["shop:travel", "shop:approach", "shop:leave"]
        stores = [(37, 91), (31, 77), (30, 49)]
        for step in range(TOWN_NO_PROGRESS_LIMIT):
            y, base_x = stores[(step // 3) % len(stores)]
            # Position jitter keeps the old distinct-signature detector false.
            x = base_x + step
            pol.last_reason = reasons[step % len(reasons)]
            pol._observe(self._town_snap(y=y, x=x, gold=102))
        self.assertTrue(pol._town_cycle_pending)
        departure = replace(
            self._town_snap(gold=102),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
        )
        self.assertEqual(pol._town_special_key(departure), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:cycle-break")
        self.assertTrue(pol._town_restock_suppressed)
        self.assertIsNone(pol._town_special_key(departure))

    def test_progress_resets_no_progress_count(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        for step in range(TOWN_NO_PROGRESS_LIMIT - 1):
            pol.last_reason = "shop:travel"
            pol._observe(self._town_snap(y=30, x=step, gold=102))
        self.assertEqual(pol._town_no_progress_count, TOWN_NO_PROGRESS_LIMIT - 1)
        pol.last_reason = "shop:travel"
        pol._observe(self._town_snap(y=30, x=200, gold=103))
        self.assertFalse(pol._town_cycle_pending)
        self.assertEqual(pol._town_no_progress_count, 1)

    def test_restock_timer_unlatches_each_store_only_once_per_visit(self):
        pol = HengbotPolicy()
        snap = self._town_snap(gold=102)
        pol._town_store_attempted[STORE_ALCHEMIST] = 0

        self.assertIsNone(pol._retry_after_store_restock(snap, (STORE_ALCHEMIST,)))
        expiry = replace(snap, turn=pol._town_restock_wait_until)
        self.assertEqual(
            pol._retry_after_store_restock(expiry, (STORE_ALCHEMIST,)),
            STORE_ALCHEMIST,
        )
        pol._town_store_attempted[STORE_ALCHEMIST] = expiry.turn
        self.assertIsNone(pol._retry_after_store_restock(expiry, (STORE_ALCHEMIST,)))
        second_expiry = replace(expiry, turn=pol._town_restock_wait_until)
        self.assertIsNone(
            pol._retry_after_store_restock(second_expiry, (STORE_ALCHEMIST,))
        )
        self.assertIn(STORE_ALCHEMIST, pol._town_store_attempted)
        self.assertIsNotNone(pol._town_restock_wait_until)

    def test_live_pingpong_shape_trips_through_observe(self):
        # The exact live shape: travel/approach/leave alternating between the
        # Alchemist and Temple door tiles, gold frozen.
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        positions = [(37, 91), (31, 77)]
        reasons = ["shop:travel", "shop:approach", "shop:leave"]
        steps = 0
        while not pol._town_cycle_pending and steps < TOWN_CYCLE_WINDOW + 12:
            y, x = positions[(steps // 3) % 2]
            pol.last_reason = reasons[steps % 3]
            pol._observe(self._town_snap(y=y, x=x))
            steps += 1
        self.assertTrue(pol._town_cycle_pending)

    def test_home_plan_owned_page_cycle_does_not_trip_repetition_guard(self):
        # 18:41 replay shape: store-loop and main-loop snapshots reported the
        # bounded Home page owner alternately, without inventory/gold changes.
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        reasons = ("home:seek-processing-page", "home:processing-complete")
        for step in range(TOWN_NO_PROGRESS_LIMIT * 2):
            pol.last_reason = reasons[step % len(reasons)]
            pol._observe(self._town_snap())

        self.assertFalse(pol._town_cycle_pending)
        self.assertEqual(pol._town_no_progress_count, 0)
        self.assertEqual(list(pol._town_signature_history), [])

    def test_blocked_home_replay_leaves_then_waits_only_outside(self):
        # A real store snapshot is followed by one interleaved main-loop town
        # snapshot on the Home tile. Both must emit ESC; only the subsequent
        # outside snapshot may emit raw WAIT (key 5).
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        town = self._town_snap()
        position = town.player.position
        store_grid = replace(town.grids[position], store_number=STORE_HOME)
        home = replace(
            town,
            grids={position: store_grid},
            store=StoreState(store_type=STORE_HOME, items=[]),
            town_flag=False,
        )
        interleaved = replace(
            town,
            grids={position: store_grid},
            town_flag=True,
        )

        keys = [pol.choose_key(home), pol.choose_key(interleaved)]
        outside = self._town_snap(y=34, x=95)
        keys.append(pol._town_special_key(outside))

        self.assertEqual(keys, [LEAVE_STORE_KEY, LEAVE_STORE_KEY, WAIT_KEY])
        self.assertNotIn(WAIT_KEY, keys[:2])
        self.assertEqual(pol.last_reason, "town:blocked:repetition")

    def test_blocked_latch_outside_store_still_waits(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        self.assertEqual(pol._town_special_key(self._town_snap()), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:blocked:repetition")

    def test_nine_cell_resupply_carousel_hits_no_progress_limit(self):
        # Exact class of the live failure: unaffordable shopping approaches
        # advance through several town cells, with breakout decisions adding
        # enough distinct signatures to evade the compact-cycle detector, then
        # reaches the no-progress fallback.
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        cells = [
            (34, 94),
            (34, 95),
            (33, 96),
            (32, 97),
            (31, 98),
            (30, 98),
            (29, 99),
            (28, 100),
            (27, 101),
        ]
        steps = 0
        while not pol._town_cycle_pending and steps < TOWN_NO_PROGRESS_LIMIT:
            y, x = cells[(steps // 4) % len(cells)]
            pol.last_reason = (
                "breakout:least-visited" if steps % 6 == 5 else "shop:approach"
            )
            pol._observe(self._town_snap(y=y, x=x, gold=111))
            steps += 1

        self.assertTrue(pol._town_cycle_pending)
        self.assertEqual(steps, TOWN_NO_PROGRESS_LIMIT)

    def test_progress_resets_the_window(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._town_progress_marker = (100, 0, 0)
        self._prime_cycle(pol)
        pol.last_reason = "shop:travel"
        pol._observe(self._town_snap(gold=900))  # gold rose: not a cycle
        self.assertFalse(pol._town_cycle_pending)
        self.assertLessEqual(len(pol._town_signature_history), 1)

    def test_first_detection_breaks_the_cycle_and_latches_stores(self):
        pol = HengbotPolicy()
        pol._town_cycle_pending = True
        key = pol._town_special_key(self._town_snap(gold=FUNDRAISING_START_GOLD))
        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:cycle-break")
        self.assertIn(STORE_ALCHEMIST, pol._town_store_attempted)
        self.assertIn(STORE_HOME, pol._town_store_attempted)
        self.assertTrue(pol._shopping_stuck)
        self.assertIsNone(pol._town_blocked_reason)

    def test_pending_cycle_preempts_shopping_approach_in_decide(self):
        # The live carousel always had another shopping approach available.
        # A pending repair must run before that early return or cycle-break is
        # scheduled by _observe but never emitted.
        from unittest import mock

        pol = HengbotPolicy()
        pol._town_cycle_pending = True
        snap = self._town_snap(gold=FUNDRAISING_START_GOLD)
        with mock.patch.object(
            pol, "_shopping_approach_step", return_value=Position(1, 1)
        ):
            self.assertEqual(pol._decide(snap), WAIT_KEY)

        self.assertEqual(pol.last_reason, "town:cycle-break")
        self.assertTrue(pol._town_restock_suppressed)

    def test_second_detection_stops_visibly(self):
        pol = HengbotPolicy()
        pol._town_cycle_pending = True
        snap = self._town_snap()
        pol._town_special_key(snap)
        pol._town_cycle_pending = True
        key = pol._town_special_key(snap)
        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:blocked:repetition")
        self.assertEqual(pol._town_blocked_reason, "repetition")

    def test_cycle_break_suppresses_restock_waits_for_the_visit(self):
        # Without this the retry path starts a fresh in-town wait, un-latches
        # the stores when it expires, and the cycle resumes (observed live).
        pol = HengbotPolicy()
        pol._town_cycle_pending = True
        snap = self._town_snap()
        pol._town_special_key(snap)
        self.assertTrue(pol._town_restock_suppressed)
        self.assertIsNone(
            pol._retry_after_store_restock(snap, (STORE_ALCHEMIST,))
        )
        self.assertIsNone(pol._town_restock_wait_until)
        # And the town ladder no longer waits for restock either.
        pol._town_restock_wait_until = snap.turn + 1000
        key = pol._town_special_key(snap)
        self.assertNotEqual(pol.last_reason, "town:wait-restock")

    def test_post_break_visit_routes_to_no_store_at_all(self):
        # The choke point: after a cycle break the router yields NOTHING for the
        # rest of the visit, whatever errand branch would otherwise fire —
        # chasing individual un-gated branches left a new fuel line each time.
        from unittest import mock

        pol = HengbotPolicy()
        pol._town_cycle_pending = True
        snap = self._town_snap()
        pol._town_special_key(snap)  # first break: suppression latched
        with mock.patch.object(
            pol,
            "_find_weapon_sale",
            return_value=item("w", TVAL_SWORD, 4, is_equipment=True),
        ):
            self.assertIsNone(pol._next_required_store_type(snap))

    def test_prepare_cycle_break_enters_scavenge_for_departure(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        pol._town_cycle_pending = True
        snap = replace(
            self._town_snap(gold=102),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
        )

        self.assertEqual(pol._town_special_key(snap), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:cycle-break")
        self.assertEqual(pol._fundraising_mode, "scavenge")
        self.assertEqual(pol._scavenge_entry_gold, 102)

    def test_blocked_mining_cycle_break_falls_back_to_scavenge(self):
        from unittest import mock

        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._town_cycle_pending = True
        snap = replace(
            self._town_snap(gold=508),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
        )

        with mock.patch.object(
            pol, "_fundraising_departure_ready", return_value=False
        ), mock.patch.object(pol, "_fundraising_supplies_ready", return_value=True):
            self.assertEqual(pol._town_special_key(snap), WAIT_KEY)
            self.assertEqual(pol.last_reason, "town:cycle-break")
            self.assertEqual(pol._fundraising_mode, "scavenge")
            self.assertIsNone(pol._town_special_key(snap))

        self.assertEqual(pol.last_reason, "town:cycle-break")
        self.assertEqual(pol._fundraising_mode, "scavenge")

    def test_low_gold_cycle_break_starts_scavenge_and_avoids_immediate_return(self):
        pol = HengbotPolicy()
        town = replace(
            self._town_snap(gold=102),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
        )

        pol._break_town_cycle(town)

        self.assertEqual(pol._fundraising_mode, "scavenge")
        self.assertEqual(pol._scavenge_entry_gold, 102)
        yeek_one = replace(
            town,
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            town_flag=False,
            inventory=[],
        )
        self.assertFalse(pol._should_start_town_return(yeek_one))
        self.assertIsNone(pol._last_return_trigger)

    def test_broke_but_lit_fundraiser_leaves_after_first_cycle_offense(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        pol._town_cycle_pending = True
        snap = replace(
            self._town_snap(gold=0),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
        )

        self.assertEqual(pol._town_special_key(snap), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:cycle-break")
        self.assertIsNone(pol._town_special_key(snap))
        self.assertIsNone(pol._town_blocked_reason)

    def test_first_cycle_offense_stops_visibly_when_departure_has_no_light(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        pol._town_cycle_pending = True

        self.assertEqual(pol._town_special_key(self._town_snap(gold=0)), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:blocked:departure-no-light")
        self.assertEqual(pol._town_blocked_reason, "departure-no-light")

    def test_mine_cycle_first_offense_stops_visibly_when_light_died(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._town_cycle_pending = True

        self.assertEqual(pol._town_special_key(self._town_snap(gold=0)), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:blocked:departure-no-light")
        self.assertEqual(pol._town_blocked_reason, "departure-no-light")

    def test_scavenge_cycle_break_still_recovers_before_departure(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "scavenge"
        pol._town_restock_suppressed = True
        snap = replace(
            self._town_snap(),
            player=player(34, 94, hp=9, max_hp=10, class_id=PLAYER_CLASS_WARRIOR),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
        )

        self.assertEqual(pol._town_special_key(snap), REST_MACRO)
        self.assertEqual(pol.last_reason, "town:recover")

    def test_departure_blocked_reason_remains_cycle_detectable(self):
        self.assertNotIn("fundraise:departure-blocked", TOWN_CYCLE_IGNORED_REASONS)

    def test_bounded_entrance_travel_is_not_a_generic_town_cycle(self):
        self.assertIn("town:travel-entrance", TOWN_CYCLE_IGNORED_REASONS)

    def test_departure_only_mode_without_light_keeps_entrance_blocked(self):
        pol = HengbotPolicy()
        pol._town_restock_suppressed = True

        self.assertTrue(pol._descent_is_blocked(self._town_snap()))

    def test_cycle_break_bypasses_procurement_gate_and_exposes_entrance(self):
        from types import SimpleNamespace

        pol = HengbotPolicy()
        pol._town_cycle_pending = True
        snap = replace(
            self._town_snap(),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
        )
        pol._town_special_key(snap)
        pol._town_map = SimpleNamespace(entrance=Position(34, 120))
        pol._town_map_active = lambda _snapshot: True
        pol._target_dungeon_id = DUNGEON_YEEK_CAVE
        snap = replace(
            snap,
            grids={
                **snap.grids,
                Position(34, 120): grid(
                    34, 120, entrance=True,
                    entrance_dungeon_id=DUNGEON_YEEK_CAVE,
                ),
            },
        )

        self.assertFalse(pol._descent_is_blocked(snap))
        self.assertEqual(
            pol._town_map_descent_entrance(snap), Position(34, 120)
        )

    def test_cycle_break_does_not_commit_non_target_foot_entrance(self):
        from types import SimpleNamespace

        entrance = Position(34, 120)
        pol = HengbotPolicy()
        pol._town_restock_suppressed = True
        pol._target_dungeon_id = DUNGEON_ANGBAND
        pol._town_map = SimpleNamespace(entrance=entrance, walkable=frozenset({entrance}))
        pol._town_map_active = lambda _snapshot: True
        pol._descent_is_blocked = lambda _snapshot: False
        # Live 05:13 shape: the untaken town-based kill quest made the old
        # quest-depth early return accept every descent before entrance ID was
        # checked.  Since the entrance is also down_stairs, the router committed
        # Yeek while over-extension still targeted Angband.
        pol._quest_knowledge = {
            34: QuestInfo(
                34, "Arena kill", QUEST_TYPE_KILL_LEVEL, 34, 0,
                dungeon=0, max_num=1, monrace_id=1,
            )
        }
        snap = replace(
            self._town_snap(),
            quests={
                34: QuestState(
                    34, status=QUEST_STATUS_UNTAKEN,
                    type=QUEST_TYPE_KILL_LEVEL, level=34,
                    dungeon_id=0, fixed=True,
                )
            },
            grids={
                Position(34, 94): grid(34, 94),
                entrance: grid(
                    34, 120, downstairs=True, entrance=True,
                    entrance_dungeon_id=DUNGEON_YEEK_CAVE,
                ),
            },
        )

        self.assertIsNone(pol._town_map_descent_entrance(snap))
        self.assertIsNone(pol._descent_step(snap))
        self.assertIsNone(pol._nav_ledger.descent_target)

    def test_cycle_break_cannot_descend_from_non_target_entrance_underfoot(self):
        """Reproduce turns 2058602-2059139 after travel reached Yeek's gate.

        The route producer is stubbed as already committed so this remains a
        final step-5 regression: reverting the on-tile target check emits >\ry.
        """
        from types import SimpleNamespace

        entrance = Position(34, 120)
        pol = HengbotPolicy()
        pol._town_restock_suppressed = True
        pol._target_dungeon_id = DUNGEON_ANGBAND
        pol._town_map = SimpleNamespace(
            entrance=entrance, walkable=frozenset({entrance})
        )
        pol._town_map_active = lambda _snapshot: True
        pol._town_map_descent_entrance = lambda _snapshot: entrance
        pol._descent_is_blocked = lambda _snapshot: False
        pol._quest_knowledge = {
            34: QuestInfo(
                34, "Arena kill", QUEST_TYPE_KILL_LEVEL, 34, 0,
                dungeon=0, max_num=1, monrace_id=1,
            )
        }
        snap = replace(
            self._town_snap(y=entrance.y, x=entrance.x),
            quests={
                34: QuestState(
                    34, status=QUEST_STATUS_UNTAKEN,
                    type=QUEST_TYPE_KILL_LEVEL, level=34,
                    dungeon_id=0, fixed=True,
                )
            },
            grids={entrance: grid(
                entrance.y, entrance.x, downstairs=True, entrance=True,
                entrance_dungeon_id=DUNGEON_YEEK_CAVE,
            )},
        )

        key = pol.choose_key(snap)

        self.assertNotEqual(key, ">\ry")
        self.assertNotEqual(pol.last_reason, "descend")

    def test_kill_quest_still_allows_matching_mining_entrance(self):
        entrance = Position(31, 150)
        pol = HengbotPolicy()
        pol._target_dungeon_id = DUNGEON_ANGBAND
        pol._fundraising_mode = "mine"
        pol._quest_knowledge = {
            34: QuestInfo(
                34, "Arena kill", QUEST_TYPE_KILL_LEVEL, 34, 0,
                dungeon=0, max_num=1, monrace_id=1,
            )
        }
        snap = replace(
            self._town_snap(y=entrance.y, x=entrance.x),
            quests={
                34: QuestState(
                    34, status=QUEST_STATUS_UNTAKEN,
                    type=QUEST_TYPE_KILL_LEVEL, level=34,
                    dungeon_id=0, fixed=True,
                )
            },
            grids={entrance: grid(
                entrance.y, entrance.x, downstairs=True, entrance=True,
                entrance_dungeon_id=DUNGEON_YEEK_CAVE,
            )},
        )

        self.assertTrue(pol._is_descent_target(snap, snap.grids[entrance]))

    def test_sale_routes_honor_the_store_latches(self):
        # An unsellable candidate re-routed the bot to the sale store forever,
        # immune even to the cycle break (the sale routes skipped the latches).
        from unittest import mock

        pol = HengbotPolicy()
        pol._town_store_attempted[STORE_WEAPON] = 100
        snap = self._town_snap()
        with mock.patch.object(
            pol,
            "_find_weapon_sale",
            return_value=item("w", TVAL_SWORD, 4, is_equipment=True),
        ):
            self.assertNotEqual(pol._next_required_store_type(snap), STORE_WEAPON)


class TownTravelProgressTest(unittest.TestCase):
    GOAL = Position(10, 20)

    def test_progress_resets_both_counters(self):
        progress = TownTravelProgress(self.GOAL, 10, 3, 4, 7)
        self.assertEqual(progress.record(9, 8), "reissue")
        self.assertEqual(
            progress,
            TownTravelProgress(self.GOAL, 9, 0, 0, 8),
        )

    def test_new_turn_resets_same_turn_stalls_and_reissues(self):
        progress = TownTravelProgress(self.GOAL, 10, 3, 4, 7)
        self.assertEqual(progress.record(10, 8), "reissue")
        self.assertEqual(
            (progress.stalls, progress.turn_stalls, progress.last_turn),
            (0, 5, 8),
        )

    def test_new_turn_limit_falls_back(self):
        progress = TownTravelProgress(
            self.GOAL, 10, 3, TOWN_TRAVEL_TURN_STALL_LIMIT - 1, 7
        )
        self.assertEqual(progress.record(10, 8), "fallback")
        self.assertEqual(
            (progress.stalls, progress.turn_stalls, progress.last_turn),
            (0, TOWN_TRAVEL_TURN_STALL_LIMIT, 8),
        )

    def test_same_turn_increments_stalls_and_reissues(self):
        progress = TownTravelProgress(self.GOAL, 10, 3, 4, 7)
        self.assertEqual(progress.record(10, 7), "reissue")
        self.assertEqual(
            (progress.stalls, progress.turn_stalls, progress.last_turn),
            (4, 4, 7),
        )

    def test_same_turn_limit_falls_back(self):
        progress = TownTravelProgress(
            self.GOAL, 10, TOWN_TRAVEL_STALL_LIMIT - 1, 4, 7
        )
        self.assertEqual(progress.record(10, 7), "fallback")
        self.assertEqual(progress.stalls, TOWN_TRAVEL_STALL_LIMIT)


class StoreTravelRetryTest(unittest.TestCase):
    """Store/Home travel used to be one-shot: any interruption latched a walking
    fallback and the rest of the leg went one decision per tile. It now shares
    the progress-based gate with the entrance leg — re-issue while getting
    closer, walk only after TOWN_TRAVEL_STALL_LIMIT no-progress issues."""

    @staticmethod
    def _snap(x, turn=0, *, goal_remembered=True):
        grids = {Position(34, x): grid(34, x)}
        if goal_remembered:
            grids[Position(34, 130)] = grid(34, 130)
        return Snapshot(
            player(34, x),
            grids,
            [],
            floor_key=(0, 0, 0),
            turn=turn,
            inventory=[],
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )

    @staticmethod
    def _approach(pol, snap):
        pol._shopping_approach_goal = Position(34, 130)
        pol._shopping_approach_store_type = 4
        return pol._shopping_approach_key(snap, Position(34, 95), "shop:travel")

    def test_travel_reissues_after_progress(self):
        pol = HengbotPolicy()
        self.assertEqual(self._approach(pol, self._snap(94)), "\x1b`n%.")
        # Interrupted mid-route but closer than before: travel again.
        self.assertEqual(self._approach(pol, self._snap(110)), "\x1b`n%.")

    def test_unremembered_static_store_goal_walks_without_recording_issue(self):
        pol = HengbotPolicy()
        snap = self._snap(94, goal_remembered=False)
        pol.last_reason = "shop:approach"

        self.assertEqual(self._approach(pol, snap), "6")
        self.assertEqual(pol.last_reason, "shop:approach")
        self.assertIsNone(pol._town_travel_state)

    def test_store_travel_engages_after_walk_reveals_goal(self):
        pol = HengbotPolicy()
        self.assertEqual(
            self._approach(pol, self._snap(94, goal_remembered=False)), "6"
        )
        self.assertIsNone(pol._town_travel_state)

        self.assertEqual(self._approach(pol, self._snap(95)), "\x1b`n%.")
        self.assertEqual(pol.last_reason, "shop:travel")

    def test_no_progress_twice_falls_back_to_walking(self):
        pol = HengbotPolicy()
        snap = self._snap(94, turn=1)
        for _ in range(TOWN_TRAVEL_STALL_LIMIT):
            self.assertEqual(self._approach(pol, snap), "\x1b`n%.")
        self.assertNotEqual(self._approach(pol, snap), "\x1b`n%.")
        self.assertEqual(pol._town_travel_fallback, Position(34, 130))

    def test_input_latency_gets_several_reissues_before_fallback(self):
        pol = HengbotPolicy()
        snap = self._snap(94, turn=7)

        for _ in range(5):
            self.assertEqual(self._approach(pol, snap), "\x1b`n%.")

        self.assertIsNone(pol._town_travel_fallback)
        self.assertEqual(pol._town_travel_state[2], 4)

    def test_consumed_turn_resets_stalls_even_without_distance_gain(self):
        pol = HengbotPolicy()
        snap = self._snap(94, turn=7)
        for _ in range(5):
            self.assertEqual(self._approach(pol, snap), "\x1b`n%.")

        detour = self._snap(94, turn=8)
        self.assertEqual(self._approach(pol, detour), "\x1b`n%.")
        self.assertEqual(pol._town_travel_state[2], 0)

    def test_consumed_turns_without_distance_progress_eventually_fall_back(self):
        pol = HengbotPolicy()
        for turn in range(1, TOWN_TRAVEL_TURN_STALL_LIMIT + 1):
            self.assertEqual(
                self._approach(pol, self._snap(94, turn=turn)), "\x1b`n%."
            )

        self.assertNotEqual(
            self._approach(
                pol,
                self._snap(94, turn=TOWN_TRAVEL_TURN_STALL_LIMIT + 1),
            ),
            "\x1b`n%.",
        )


class RangedAttackTest(unittest.TestCase):
    """Direction-key firing at ray-aligned hostiles (no targeting UI)."""

    def _snap(self, *, monsters, inventory=(), equipment=(), player_kw=None):
        grids = {
            Position(y, x): grid(y, x)
            for y in range(8, 14)
            for x in range(8, 22)
        }
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, **(player_kw or {})),
            grids,
            list(monsters),
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            width=30,
            height=30,
            inventory=list(inventory),
            equipment=[
                item("a", TVAL_SWORD, 17, name="sword", is_equipment=True),
                self._lantern(),
                *equipment,
            ],
        )

    @staticmethod
    def _lantern():
        return item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)

    @staticmethod
    def _sling():
        return item("b", TVAL_BOW, SV_BOW_SLING, name="sling", is_equipment=True)

    @staticmethod
    def _shots(count=20):
        return item("s", TVAL_SHOT, 1, name="iron shots", count=count)

    def test_fires_matching_ammo_at_ray_aligned_hostile(self):
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "fs6")
        self.assertEqual(policy.last_reason, "ranged:fire")

    def test_fires_along_a_diagonal_ray(self):
        snap = self._snap(
            monsters=[hostile(1, 13, 13, distance=3)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "fs3")
        self.assertEqual(policy.last_reason, "ranged:fire")

    def test_adjacent_hostile_stays_melee(self):
        snap = self._snap(
            monsters=[hostile(1, 10, 11, distance=1)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertEqual(policy.last_reason, "melee")

    def test_off_axis_hostile_uses_game_targeting(self):
        snap = self._snap(
            monsters=[hostile(1, 11, 14, distance=4)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "fs*t5\x1b")
        self.assertEqual(policy.last_reason, "ranged:fire-target")

    def test_blocked_ray_uses_game_targeting(self):
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        blocked = dict(snap.grids)
        blocked[Position(10, 12)] = grid(10, 12, passable=False)
        snap = replace(snap, grids=blocked)
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "fs*t5\x1b")
        self.assertEqual(policy.last_reason, "ranged:fire-target")

    def test_wall_corner_uses_single_grid_offset_aim(self):
        snap = self._snap(
            monsters=[hostile(1, 7, 2, distance=8)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        grids = {
            Position(y, x): grid(y, x)
            for y in range(1, 15)
            for x in range(1, 15)
        }
        grids[Position(7, 3)] = grid(7, 3, passable=False)
        snap = replace(snap, grids=grids)
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "fs*p777444444t")
        self.assertEqual(policy.last_reason, "ranged:fire-offset")

    def test_offset_aim_does_not_depend_on_nearest_targetable_monster(self):
        snap = self._snap(
            monsters=[
                hostile(1, 7, 2, distance=8),
                hostile(2, 10, 13, distance=3),
            ],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        grids = dict(snap.grids)
        grids[Position(7, 3)] = grid(7, 3, passable=False)
        snap = replace(snap, grids=grids)
        policy = HengbotPolicy()

        self.assertEqual(
            policy._offset_fire_aim(snap, snap.visible_monsters[0]), Position(7, 1)
        )

    def test_near_side_neighbor_does_not_validate_as_offset_aim(self):
        snap = self._snap(
            monsters=[hostile(1, 2, 5, distance=8)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        grids = dict(snap.grids)
        grids[Position(4, 6)] = grid(4, 6, passable=False)
        snap = replace(snap, grids=grids)
        policy = HengbotPolicy()

        near_side = Position(3, 6)
        through_path = projection_path(
            snap.player.position,
            near_side,
            RANGED_MAX_DISTANCE,
            lambda pos: pos == Position(4, 6),
            through=True,
        )
        self.assertLess(
            through_path.index(near_side),
            through_path.index(snap.visible_monsters[0].position),
        )
        self.assertNotEqual(
            policy._offset_fire_aim(snap, snap.visible_monsters[0]), near_side
        )

    def test_no_projectable_monster_still_uses_player_origin_offset(self):
        snap = self._snap(
            monsters=[hostile(1, 7, 2, distance=8)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        grids = dict(snap.grids)
        grids[Position(7, 3)] = grid(7, 3, passable=False)
        snap = replace(snap, grids=grids)

        self.assertEqual(HengbotPolicy().choose_key(snap), "fs*p777444444t")

    def test_failed_targeting_is_skipped_until_player_moves(self):
        snap = self._snap(
            monsters=[hostile(1, 11, 14, distance=4)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()

        attempts = [policy.choose_key(snap) for _ in range(4)]
        self.assertEqual(attempts[:3], ["fs*t5\x1b"] * 3)
        self.assertNotEqual(attempts[3], "fs*t5\x1b")

        moved = replace(snap, player=replace(snap.player, position=Position(10, 11)))
        self.assertEqual(policy.choose_key(moved), "fs*t5\x1b")

        policy = HengbotPolicy()
        progressing = snap
        for count in range(20, 15, -1):
            progressing = replace(progressing, inventory=[self._shots(count)])
            self.assertEqual(policy.choose_key(progressing), "fs*t5\x1b")

    def test_failed_offset_targeting_is_skipped_after_three_attempts(self):
        snap = self._snap(
            monsters=[hostile(1, 7, 2, distance=8)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        grids = dict(snap.grids)
        grids[Position(7, 3)] = grid(7, 3, passable=False)
        snap = replace(snap, grids=grids)
        policy = HengbotPolicy()

        attempts = [policy.choose_key(snap) for _ in range(4)]
        self.assertEqual(attempts[:3], ["fs*p777444444t"] * 3)
        self.assertNotEqual(attempts[3], "fs*p777444444t")

    def test_aligned_hostile_is_preferred_when_off_axis_is_also_visible(self):
        snap = self._snap(
            monsters=[
                hostile(1, 11, 12, distance=2),
                hostile(2, 10, 15, distance=5),
            ],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "fs6")
        self.assertEqual(policy.last_reason, "ranged:fire")

    def test_distant_off_axis_sleeper_is_left_asleep(self):
        snap = self._snap(
            monsters=[hostile(1, 12, 18, distance=8, asleep=True)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "ranged:fire-target")

    def test_shot_targets_first_body_on_ray(self):
        snap = self._snap(
            monsters=[
                hostile(1, 10, 15, distance=5),
                hostile(2, 10, 12, distance=2),
            ],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        key = policy.choose_key(snap)
        self.assertEqual(policy.last_reason, "ranged:fire")
        self.assertEqual(key, "fs6")

    def test_distant_sleeper_is_left_asleep(self):
        snap = self._snap(
            monsters=[hostile(1, 10, 18, distance=8, asleep=True)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "ranged:fire")

    def test_afraid_player_still_fires(self):
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[self._shots()],
            equipment=[self._sling()],
            player_kw={"afraid": True},
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "fs6")
        self.assertEqual(policy.last_reason, "ranged:fire")

    def test_confused_player_does_not_fire(self):
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[self._shots()],
            equipment=[self._sling()],
            player_kw={"confused": True},
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "ranged:fire")

    def test_mismatched_ammo_falls_back_to_oil_throw(self):
        arrows = item("s", TVAL_ARROW, 1, name="arrows", count=16)
        oil = item("o", TVAL_FLASK, 0, name="flask of oil", count=OIL_TARGET + 3)
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[arrows, oil],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "vo6")
        self.assertEqual(policy.last_reason, "ranged:throw-oil")

    def test_early_floor_throws_cheap_torches(self):
        torch = item("t", TVAL_LITE, SV_LITE_TORCH, name="torch", count=8)
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[torch],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "vt6")
        self.assertEqual(policy.last_reason, "ranged:throw-torch")

    def test_deep_floor_does_not_throw_torches(self):
        torch = item("t", TVAL_LITE, SV_LITE_TORCH, name="torch", count=8)
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[torch],
        )
        snap = replace(snap, floor_key=(DUNGEON_YEEK_CAVE, 11, 0))
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "ranged:throw-torch")

    def test_potions_are_never_thrown(self):
        potions = item(
            "p", TVAL_POTION, SV_POTION_CURE_CRITICAL, name="potion", count=9
        )
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[potions],
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertFalse(policy.last_reason.startswith("ranged:"))

    def test_torch_restock_for_shallow_plans(self):
        torch_ware = StoreItem("f", "torch", 99, TVAL_LITE, SV_LITE_TORCH, price=1)
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[*self._strict_supplies_for_ammo()],
            equipment=[self._lantern()],
            store=StoreState(STORE_GENERAL, [torch_ware]),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        selected = policy._next_purchase(snap)
        self.assertIsNotNone(selected)
        self.assertEqual(
            (selected.tval, selected.sval), (TVAL_LITE, SV_LITE_TORCH)
        )
        self.assertEqual(
            policy._purchase_quantity(snap, selected), TORCH_THROW_TARGET
        )

    def test_pack_equipment_kind_torches_count_and_buy_as_one_batch(self):
        torch_ware = StoreItem("f", "torch", 99, TVAL_LITE, SV_LITE_TORCH, price=3)
        carried = item(
            "f", TVAL_LITE, SV_LITE_TORCH, name="inscribed torches",
            count=4, fuel=2500, is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            inventory=[carried, *self._strict_supplies_for_ammo()],
            equipment=[self._lantern()],
            store=StoreState(STORE_GENERAL, [torch_ware]),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        self.assertEqual(policy._count_throwing_torches(snap), 4)
        self.assertEqual(policy._shop(snap), "pf6\r\r")

    def test_money_spent_without_torch_progress_leaves_within_bound(self):
        torch_ware = StoreItem("f", "torch", 99, TVAL_LITE, SV_LITE_TORCH, price=3)
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        keys = []
        for attempt in range(STORE_STUCK_LIMIT + 1):
            snap = Snapshot(
                player(10, 10, gold=500 - 3 * attempt, class_id=PLAYER_CLASS_WARRIOR),
                {Position(10, 10): grid(10, 10)}, [],
                floor_key=(0, 0, 0), town_flag=True,
                inventory=[*self._strict_supplies_for_ammo()],
                equipment=[self._lantern()],
                store=StoreState(STORE_GENERAL, [torch_ware]),
            )
            keys.append(policy._shop(snap))
        self.assertEqual(keys[-1], LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "shop:defective-target-leave")

    def test_normal_torch_restock_progress_stops_at_target(self):
        torch_ware = StoreItem("f", "torch", 99, TVAL_LITE, SV_LITE_TORCH, price=3)
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        for count in range(TORCH_THROW_TARGET):
            carried = item(
                "f", TVAL_LITE, SV_LITE_TORCH, count=count + 1,
                fuel=2500, is_equipment=True,
            )
            snap = Snapshot(
                player(10, 10, gold=500 - 3 * count, class_id=PLAYER_CLASS_WARRIOR),
                {Position(10, 10): grid(10, 10)}, [],
                floor_key=(0, 0, 0), town_flag=True,
                inventory=[carried, *self._strict_supplies_for_ammo()],
                equipment=[self._lantern()],
                store=StoreState(STORE_GENERAL, [torch_ware]),
            )
            key = policy._shop(snap)
        self.assertNotEqual(policy.last_reason, "shop:defective-target-leave")
        self.assertNotEqual(policy.last_reason, "shop:buy-torch")

    def test_sells_48_inscribed_torches_down_to_target(self):
        torches = item(
            "f", TVAL_LITE, SV_LITE_TORCH,
            name="torches {@v0=g}", count=48, fuel=2500, is_equipment=True,
        )
        lantern = item("g", TVAL_LITE, SV_LITE_LANTERN, name="lantern", fuel=7500)
        equipped_torch = item(
            "light", TVAL_LITE, SV_LITE_TORCH,
            name="wield backup torch", fuel=2384, is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            inventory=[torches, lantern], equipment=[equipped_torch],
            store=StoreState(STORE_GENERAL, []),
        )
        policy = HengbotPolicy()
        self.assertEqual(policy._shop(snap), "df38\ry")
        self.assertEqual(policy.last_reason, "shop:sell-surplus-torches")

    def test_oil_reserve_is_never_thrown(self):
        oil = item("o", TVAL_FLASK, 0, name="flask of oil", count=OIL_TARGET)
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[oil],
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "ranged:throw-oil")

    def test_town_depth_uses_shallowest_supply_threshold(self):
        policy = HengbotPolicy()

        self.assertEqual(policy._supply_threshold("oil", "return", 0), 0)
        self.assertEqual(
            policy._supply_threshold("oil", "departure", 0), OIL_TARGET
        )

    def test_ammo_purchase_at_weapon_smith(self):
        shots = StoreItem("d", "iron shot", 99, TVAL_SHOT, 1, price=1)
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[*self._strict_supplies_for_ammo()],
            equipment=[self._sling(), self._lantern()],
            store=StoreState(STORE_WEAPON, [shots]),
        )
        policy = HengbotPolicy()
        selected = policy._next_purchase(snap)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.tval, TVAL_SHOT)
        self.assertEqual(
            policy._purchase_quantity(snap, selected), AMMO_PURCHASE_TARGET
        )

    def test_missing_27_arrows_are_bought_in_one_prompt_complete_macro(self):
        arrows = StoreItem("j", "arrows", 99, TVAL_ARROW, 1, price=1)
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [], floor_key=(0, 0, 0), town_flag=True,
            inventory=[
                *self._strict_supplies_for_ammo(),
                item("a", TVAL_ARROW, 1, name="arrows", count=3),
            ],
            equipment=[
                item("b", TVAL_BOW, SV_BOW_SHORT, name="short bow", is_equipment=True),
                self._lantern(),
            ],
            store=StoreState(STORE_WEAPON, [arrows]),
        )

        key = HengbotPolicy()._shop(snap)

        # purchase-order.cpp consumes: item letter; quantity digits + Return;
        # DEFAULT_Y confirmation Return. Nothing remains for the store loop.
        self.assertEqual(key, "pj27\r\r")
        self.assertEqual(key[2:], "27\r\r")

    def test_stale_sale_candidate_emits_no_sell_letter_or_prompt_tail(self):
        stale = item("o", TVAL_SWORD, 1, name="club", is_equipment=True, known=True)
        replacement = item(
            "o", TVAL_SWORD, 2, name="dagger", is_equipment=True, known=True
        )
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [], floor_key=(0, 0, 0), town_flag=True,
            inventory=[replacement],
            store=StoreState(STORE_WEAPON, []),
        )
        policy = HengbotPolicy()

        key = policy._store_sell_key(snap, stale, "shop:sell-inferior-weapon")

        self.assertEqual(key, LEAVE_STORE_KEY)
        self.assertFalse(key.startswith(SELL_KEY))

    @staticmethod
    def _strict_supplies_for_ammo():
        return [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=6),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=12),
            item("f", TVAL_FOOD, FOOD_MIN_SVAL, count=5),
            item("o", TVAL_FLASK, 0, count=OIL_TARGET),
            item("z", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
            item("v", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=5),
        ]


class ChestProcessingTest(unittest.TestCase):
    """Drop → step beside → search → disarm → open, on fixed key budgets."""

    def _snap(self, *, inventory=(), grids=None, player_pos=(10, 10)):
        base = grids or {
            Position(y, x): grid(y, x) for y in range(9, 12) for x in range(9, 13)
        }
        return Snapshot(
            player(
                *player_pos, hp=50, max_hp=50, class_id=PLAYER_CLASS_WARRIOR
            ),
            base,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            width=30,
            height=30,
            inventory=list(inventory),
            equipment=[
                item("a", TVAL_SWORD, 17, name="sword", is_equipment=True),
                item(
                    "l", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True
                ),
            ],
        )

    def test_full_pipeline_runs_on_budgets(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest")
        snap = self._snap(inventory=[chest])
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "dc")
        self.assertEqual(policy.last_reason, "chest:drop")

        # The chest now sits under the player (the tile reports an object);
        # step off, then work it from the adjacent tile.
        dropped_grids = dict(snap.grids)
        dropped_grids[Position(10, 10)] = grid(10, 10, objects=1)
        dropped = replace(snap, inventory=[], grids=dropped_grids)
        key = policy.choose_key(dropped)
        self.assertEqual(policy.last_reason, "chest:step-off")

        beside = replace(
            dropped,
            player=player(
                10, 11, hp=50, max_hp=50, class_id=PLAYER_CLASS_WARRIOR
            ),
        )
        chest_grids = dict(beside.grids)
        chest_grids[Position(10, 10)] = grid(10, 10, objects=1)
        beside = replace(beside, grids=chest_grids)

        for _ in range(CHEST_SEARCH_BUDGET):
            self.assertEqual(policy.choose_key(beside), "s")
            self.assertEqual(policy.last_reason, "chest:search")
        for _ in range(CHEST_DISARM_BUDGET):
            self.assertEqual(policy.choose_key(beside), "D4")
            self.assertEqual(policy.last_reason, "chest:disarm")
        for _ in range(CHEST_OPEN_BUDGET):
            self.assertEqual(policy.choose_key(beside), "o4")
            self.assertEqual(policy.last_reason, "chest:open")

        # Budgets exhausted: the pipeline abandons and normal behavior resumes.
        policy.choose_key(beside)
        self.assertFalse(policy.last_reason.startswith("chest:"))
        self.assertIsNone(policy._chest_position)

    def test_looted_chest_tile_ends_the_pipeline(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest")
        snap = self._snap(inventory=[chest])
        policy = HengbotPolicy()
        policy.choose_key(snap)  # drop at (10,10)

        emptied = replace(
            snap,
            inventory=[],
            player=player(
                10, 11, hp=50, max_hp=50, class_id=PLAYER_CLASS_WARRIOR
            ),
        )
        policy.choose_key(emptied)
        self.assertFalse(policy.last_reason.startswith("chest:"))
        self.assertIsNone(policy._chest_position)

    def test_empty_chest_is_not_processed(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest (empty)")
        snap = self._snap(inventory=[chest])
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "chest:drop")

    def test_hostiles_defer_the_pipeline(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest")
        snap = self._snap(inventory=[chest])
        snap = replace(
            snap, visible_monsters=[hostile(1, 11, 11, distance=1)]
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertFalse(policy.last_reason.startswith("chest:"))

    def test_low_hp_defers_the_drop(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest")
        snap = self._snap(inventory=[chest])
        snap = replace(
            snap,
            player=player(
                10, 10, hp=20, max_hp=50, class_id=PLAYER_CLASS_WARRIOR
            ),
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "chest:drop")


class TownTravelerCombatPriorityTest(unittest.TestCase):
    GOAL = Position(10, 30)

    @staticmethod
    def _snapshot(*, monster_pos=Position(10, 13), include_monster=True, width=40, height=20):
        grids = {
            Position(10, x): grid(10, x, monster=include_monster and x == monster_pos.x)
            for x in range(10, 31)
        }
        if monster_pos.y != 10 or monster_pos.x not in range(10, 31):
            grids[monster_pos] = grid(
                monster_pos.y, monster_pos.x, monster=include_monster
            )
        monsters = (
            [hostile(1, monster_pos.y, monster_pos.x, distance=3)]
            if include_monster
            else []
        )
        return Snapshot(
            player(10, 10),
            grids,
            monsters,
            floor_key=(0, 0, 0),
            width=width,
            height=height,
            town_flag=True,
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )

    def _approach(self, policy, snapshot):
        policy._shopping_approach_goal = self.GOAL
        policy._shopping_approach_store_type = STORE_GENERAL
        policy._build_grid_index(snapshot)
        return policy._shopping_approach_key(
            snapshot, Position(10, 11), "shop:travel"
        )

    def test_visible_hostile_preempts_town_travel(self):
        policy = HengbotPolicy()

        key = self._approach(policy, self._snapshot())

        self.assertEqual(key, "6")
        self.assertEqual(policy.last_reason, "town:kill-mob-approach")
        self.assertNotEqual(key, "\x1b`n!.")

    def test_adjacent_friendly_is_attacked_with_alter_and_inline_confirmation(self):
        policy = HengbotPolicy()
        snapshot = replace(
            self._snapshot(monster_pos=Position(10, 11)),
            visible_monsters=[
                MonsterState(
                    1, Position(10, 11), hp=10, max_hp=10, distance=1,
                    friendly=True, pet=False,
                )
            ],
        )

        key = self._approach(policy, snapshot)

        self.assertEqual(key, "+6y")
        self.assertEqual(policy.last_reason, "town:kill-mob-friendly")
        self.assertNotEqual(key, "6")

    def test_visible_friendly_is_approached_despite_multiple_hostiles(self):
        policy = HengbotPolicy()
        snapshot = self._snapshot(monster_pos=Position(10, 13))
        snapshot = replace(
            snapshot,
            visible_monsters=[
                hostile(1, 10, 13, distance=3),
                hostile(2, 10, 14, distance=4),
                MonsterState(
                    3, Position(11, 13), hp=10, max_hp=10, distance=3,
                    friendly=True, pet=False,
                ),
            ],
            grids={
                **snapshot.grids,
                Position(10, 14): grid(10, 14, monster=True),
                Position(11, 13): grid(11, 13, monster=True),
            },
        )

        self.assertEqual(self._approach(policy, snapshot), "6")
        self.assertEqual(policy.last_reason, "town:kill-mob-approach")

    def test_visible_friendly_is_engaged_without_range_or_strength_gate(self):
        for monster_pos, distance, max_hp, speed in (
            (Position(10, 13), 3, 10, 110),
            (Position(10, 11), 1, 101, 121),
        ):
            with self.subTest(monster_pos=monster_pos):
                policy = HengbotPolicy()
                snapshot = replace(
                    self._snapshot(monster_pos=monster_pos),
                    visible_monsters=[
                        MonsterState(
                            1, monster_pos, hp=max_hp, max_hp=max_hp,
                            distance=distance, friendly=True, pet=False,
                            speed=speed,
                        )
                    ],
                )

                key = self._approach(policy, snapshot)
                if distance == 1:
                    self.assertEqual(key, "+6y")
                    self.assertEqual(policy.last_reason, "town:kill-mob-friendly")
                else:
                    self.assertEqual(key, "6")
                    self.assertEqual(policy.last_reason, "town:kill-mob-approach")

    def test_pet_is_not_engaged_and_town_travel_proceeds(self):
        policy = HengbotPolicy()
        snapshot = replace(
            self._snapshot(monster_pos=Position(10, 13)),
            visible_monsters=[
                MonsterState(
                    1, Position(10, 13), hp=10, max_hp=10, distance=3,
                    friendly=True, pet=True,
                )
            ],
        )

        self.assertEqual(self._approach(policy, snapshot), "\x1b`n!.")
        self.assertEqual(policy.last_reason, "shop:travel")

    def test_unreachable_hostile_falls_through_to_town_travel(self):
        policy = HengbotPolicy()
        snapshot = self._snapshot()
        snapshot = replace(
            snapshot,
            grids={
                Position(10, 10): grid(10, 10),
                Position(10, 13): grid(10, 13, monster=True),
                self.GOAL: grid(self.GOAL.y, self.GOAL.x),
            },
        )

        self.assertEqual(self._approach(policy, snapshot), "\x1b`n!.")
        self.assertEqual(policy.last_reason, "shop:travel")

    def test_adjacent_hostile_remains_owned_by_melee(self):
        policy = HengbotPolicy()
        snapshot = replace(
            self._snapshot(monster_pos=Position(10, 11)),
            visible_monsters=[hostile(1, 10, 11, distance=1)],
        )

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "melee")

    def test_border_hostile_does_not_pull_hunt_onto_border(self):
        policy = HengbotPolicy()
        monster_pos = Position(0, 3)
        grids = {
            Position(y, 3): grid(y, 3, monster=y == 0)
            for y in range(5)
        }
        snapshot = Snapshot(
            player(2, 3),
            grids,
            [hostile(1, 0, 3, distance=2)],
            floor_key=(0, 0, 0),
            width=7,
            height=5,
            town_flag=True,
        )
        policy._build_grid_index(snapshot)

        key = policy._town_clear_traveler_key(snapshot, self.GOAL)

        self.assertEqual(key, "8")
        self.assertEqual(policy.last_reason, "town:kill-mob-approach")
        self.assertFalse(policy._on_town_border(snapshot, Position(1, 3)))

    def test_hunt_interlude_preserves_travel_progress_and_then_resumes(self):
        policy = HengbotPolicy()
        clear = self._snapshot(include_monster=False)
        self.assertEqual(self._approach(policy, clear), "\x1b`n!.")
        travel_state = policy._town_travel_state

        self.assertEqual(self._approach(policy, self._snapshot()), "6")
        self.assertEqual(policy._town_travel_state, travel_state)

        resumed = replace(clear, player=player(10, 11))
        self.assertEqual(self._approach(policy, resumed), "\x1b`n!.")
        self.assertEqual(policy.last_reason, "shop:travel")


class EntranceTravelTest(unittest.TestCase):
    """The surface walk to the dungeon entrance costs one bot decision per tile
    on foot; _entrance_travel_key rides Hengband's native travel instead
    (`n>. — the selector's > jump matches the entrance's STAIRS+DOWN_STAIRS
    terrain) and falls back to BFS walking only after issues that bring no
    progress. The bot never accepts castle quests, so > cannot land on a
    quest entrance."""

    GOAL = Position(34, 120)

    @staticmethod
    def _surface_snap(x=94, turn=0, *, goal_remembered=True):
        grids = {Position(34, x): grid(34, x)}
        if goal_remembered:
            grids[EntranceTravelTest.GOAL] = grid(
                EntranceTravelTest.GOAL.y, EntranceTravelTest.GOAL.x,
                entrance=True, entrance_dungeon_id=DUNGEON_YEEK_CAVE,
            )
        return Snapshot(
            player(34, x),
            grids,
            [],
            floor_key=(0, 0, 0),
            turn=turn,
            inventory=[],
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )

    def _travel(self, pol, snap, goal=GOAL):
        pol._target_dungeon_id = DUNGEON_YEEK_CAVE
        pol.last_reason = "seek-downstairs"
        return pol._entrance_travel_key(snap, goal)

    def test_non_target_surface_goal_does_not_travel(self):
        pol = HengbotPolicy()
        snap = self._surface_snap()
        pol._target_dungeon_id = DUNGEON_ANGBAND
        pol.last_reason = "seek-downstairs"

        self.assertIsNone(pol._entrance_travel_key(snap, self.GOAL))
        self.assertIsNone(pol._town_travel_state)

    def test_far_surface_goal_travels(self):
        pol = HengbotPolicy()
        key = self._travel(pol, self._surface_snap())
        self.assertEqual(key, "\x1b`n>.")
        self.assertEqual(pol.last_reason, "town:travel-entrance")

    def test_surface_goal_without_equipped_light_walks_instead(self):
        pol = HengbotPolicy()
        snap = replace(self._surface_snap(), equipment=[])

        self.assertIsNone(self._travel(pol, snap))
        self.assertEqual(pol.last_reason, "seek-downstairs")
        self.assertIsNone(pol._town_travel_state)

    def test_unremembered_entrance_goal_does_not_issue_or_record_travel(self):
        pol = HengbotPolicy()
        snap = self._surface_snap(goal_remembered=False)

        self.assertIsNone(self._travel(pol, snap))
        self.assertEqual(pol.last_reason, "seek-downstairs")
        self.assertIsNone(pol._town_travel_state)

    def test_progress_reissues_travel_after_an_interruption(self):
        pol = HengbotPolicy()
        self.assertEqual(self._travel(pol, self._surface_snap(x=94)), "\x1b`n>.")
        # Interrupted mid-route but closer than before: travel again.
        self.assertEqual(self._travel(pol, self._surface_snap(x=110)), "\x1b`n>.")

    def test_no_progress_latches_a_walking_fallback(self):
        pol = HengbotPolicy()
        snap = self._surface_snap(turn=1)
        self.assertEqual(self._travel(pol, snap), "\x1b`n>.")
        # Rejected route: allow a bounded set of retries for Windows input
        # latency, then give the goal back to BFS walking.
        for _ in range(TOWN_TRAVEL_STALL_LIMIT - 1):
            self.assertEqual(self._travel(pol, snap), "\x1b`n>.")
        self.assertIsNone(self._travel(pol, snap))
        self.assertIsNone(self._travel(pol, snap))

    def test_dungeon_floors_never_travel(self):
        pol = HengbotPolicy()
        snap = Snapshot(
            player(34, 94),
            {},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 3, 0),
            inventory=[],
            equipment=[],
        )
        self.assertIsNone(self._travel(pol, snap))

    def test_adjacent_goal_walks(self):
        pol = HengbotPolicy()
        self.assertIsNone(self._travel(pol, self._surface_snap(x=118)))

    def test_floor_change_clears_the_fallback_latch(self):
        pol = HengbotPolicy()
        snap = self._surface_snap(turn=1)
        self._travel(pol, snap)
        for _ in range(TOWN_TRAVEL_STALL_LIMIT - 1):
            self._travel(pol, snap)
        self.assertIsNone(self._travel(pol, snap))  # latched
        pol._floor_key = snap.floor_key  # as if _observe had seen the surface
        dungeon = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[],
            equipment=[],
        )
        pol.choose_key(dungeon)  # _observe sees the floor change and resets
        self.assertIsNone(pol._town_travel_fallback)


class EquipmentOptimizationDestructionWiringTest(unittest.TestCase):
    """prepare_warrior_optimization must receive the character's ACTUAL
    *Destruction* availability. The fail-closed False stub made
    _meets_static_requirements reject every 50F+ loadout, so a warrior already
    carrying the scroll could never become departure-ready (a town deadlock)."""

    @staticmethod
    def _town_snapshot(inventory):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=inventory,
            equipment=[],
        )

    @staticmethod
    def _captured_has_destruction(snap):
        from unittest import mock

        pol = HengbotPolicy()
        with mock.patch(
            "hengbot.policy.prepare_warrior_optimization",
            return_value=mock.Mock(ready=False),
        ) as prepare:
            pol._prepare_equipment_optimization(snap)
        return prepare.call_args.kwargs["has_destruction"]

    def test_carried_destruction_scroll_reaches_the_optimizer(self):
        snap = self._town_snapshot(
            [item("s", TVAL_SCROLL, SV_SCROLL_STAR_DESTRUCTION)]
        )
        self.assertTrue(self._captured_has_destruction(snap))

    def test_without_a_destruction_source_the_optimizer_stays_fail_closed(self):
        snap = self._town_snapshot([])
        self.assertFalse(self._captured_has_destruction(snap))

    def test_reserved_throwing_torch_is_not_a_loadout_candidate(self):
        from unittest import mock

        torch = item(
            "a", TVAL_LITE, SV_LITE_TORCH, name="lit torch",
            known=True, fully_known=True, is_equipment=True, fuel=5000,
        )
        snap = self._town_snapshot([torch])
        pol = HengbotPolicy()
        pol._equipment_catalog.refresh_carried(snap.inventory, snap.equipment)
        with mock.patch(
            "hengbot.policy.prepare_warrior_optimization",
            return_value=mock.Mock(ready=False),
        ) as prepare:
            pol._prepare_equipment_optimization(snap)

        torch_id = next(
            owned.id for owned in pol._equipment_catalog.items
            if owned.item.is_torch
        )
        self.assertIn(
            torch_id, prepare.call_args.kwargs["search_excluded_item_ids"]
        )


class ResistanceGapReturnTest(unittest.TestCase):
    """_is_descent_target only ever gates the NEXT floor (dungeon_level + 1); nothing
    previously caught the character already standing somewhere its CURRENT gear no
    longer covers -- e.g. recall landing at the save-backed deepest floor after a
    resistance-granting item was swapped/stashed, or an amulet swap mid-dive dropping
    a required resistance. _should_start_town_return now retreats for that gap too."""

    def _at(self, depth, abilities):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, abilities=frozenset(abilities)),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(DUNGEON_ANGBAND, depth, 0),
            inventory=[
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=500),
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=6),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            ],
            equipment=[
                item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
            ],
        )

    def test_missing_current_depth_ability_starts_a_return(self):
        # 26F needs pois+cold+elec+acid (see DEPTH_ABILITY_REQUIREMENTS); a bare
        # character standing there already (not merely about to descend into it)
        # has none of them.
        snap = self._at(26, set())
        policy = HengbotPolicy()

        self.assertTrue(policy._should_start_town_return(snap))
        self.assertEqual(policy._last_return_trigger, "resist-gap")

    def test_fully_resisted_current_depth_does_not_return(self):
        snap = self._at(26, {"resist_pois", "resist_cold", "resist_elec", "resist_acid"})

        self.assertFalse(HengbotPolicy()._should_start_town_return(snap))

    def test_shallow_floor_below_the_table_does_not_return(self):
        # 13F is below the table's first (20-25F) band, so a character with zero
        # abilities is unaffected -- and since Yeek Cave mining never goes deeper
        # than 13F, fundraising is naturally exempt too without a special case.
        snap = self._at(13, set())

        self.assertFalse(HengbotPolicy()._should_start_town_return(snap))


class JewelryKeepingTest(unittest.TestCase):
    """Found rings / amulets stay in the pack for identify-and-wear instead of being
    stashed at Home unidentified (why the character reached depth with a bare neck)."""

    def _home(self, inventory, equipment=()):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inventory),
            equipment=list(equipment),
        )

    def test_keeps_an_unidentified_amulet_out_of_the_home_deposit(self):
        amulet = item("k", TVAL_AMULET, 4, aware=False, known=False, is_equipment=True)
        snap = self._home([amulet])
        pol = HengbotPolicy()
        self.assertTrue(pol._is_wanted_jewelry(snap, amulet))
        self.assertIsNone(pol._find_home_deposit(snap))

    def test_keeps_a_beneficial_amulet_for_the_empty_neck(self):
        amulet = item("k", TVAL_AMULET, 4, known_flags=frozenset({50, 86}), is_equipment=True)
        self.assertTrue(HengbotPolicy()._is_wanted_jewelry(self._home([amulet]), amulet))

    def test_stashes_a_spare_amulet_when_the_neck_is_occupied(self):
        worn = item("neck", TVAL_AMULET, 2, is_equipment=True, known_flags=frozenset({50}))
        spare = item("k", TVAL_AMULET, 4, known_flags=frozenset({86}), is_equipment=True)
        snap = self._home([spare], equipment=[worn])
        pol = HengbotPolicy()
        self.assertFalse(pol._is_wanted_jewelry(snap, spare))
        self.assertEqual(pol._find_home_deposit(snap), spare)


class FundraisingStuckEscapeTest(unittest.TestCase):
    """A mining pocket sealed by walls (no reachable up-stairs, nothing to explore,
    no walkable neighbour) must ESCAPE rather than WAIT forever — the exact hang that
    tripped the loop guard on Yeek Cave L1 and stopped the bot."""

    def _walled_in(self, inventory, *, can_dig=False, upstairs_at=None):
        grids = {}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                pos = Position(10 + dy, 10 + dx)
                center = dy == 0 and dx == 0
                grids[pos] = grid(
                    10 + dy, 10 + dx, passable=center, can_dig=can_dig and not center
                )
        if upstairs_at is not None:
            grids[upstairs_at] = grid(
                upstairs_at.y, upstairs_at.x, passable=False, upstairs=True, can_dig=True
            )
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=list(inventory),
        )

    def test_digs_out_of_a_sealed_pocket_toward_the_upstairs(self):
        # A mining pocket walled off from the up-stairs: the miner DIGS out toward the
        # known up-stairs rather than spending a scarce Teleport scroll to relocate.
        snap = self._walled_in(
            [item("t", TVAL_SCROLL, 9, count=3)],  # teleport, must stay untouched
            can_dig=True,
            upstairs_at=Position(10, 12),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        self.assertEqual(pol._leave_fundraising_floor(snap), TUNNEL_KEY + "6")  # dig east
        self.assertEqual(pol.last_reason, "fundraise:tunnel-out")

    def test_digs_out_when_sealed_without_spending_recall(self):
        # Same pocket, only a Word of Recall on hand: still dig out — Recall is a
        # survival/return resource, not an unstick tool.
        snap = self._walled_in(
            [item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
            can_dig=True,
            upstairs_at=Position(10, 12),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        self.assertEqual(pol._leave_fundraising_floor(snap), TUNNEL_KEY + "6")
        self.assertEqual(pol.last_reason, "fundraise:tunnel-out")

    def test_waits_only_when_truly_boxed_in_by_permanent_rock(self):
        # No diggable wall, no reachable stairs, no remembered floor: nothing safe to
        # do but WAIT. Crucially it still does NOT read a Teleport/Recall scroll.
        snap = self._walled_in([item("t", TVAL_SCROLL, 9, count=3)])  # non-diggable walls
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        self.assertEqual(pol._leave_fundraising_floor(snap), WAIT_KEY)
        self.assertEqual(pol.last_reason, "fundraise:upstairs-not-found")

    def test_oscillating_route_drops_the_vein_without_teleporting(self):
        # Bouncing between two tiles seeking a walled-off vein must neither read
        # a scarce Teleport scroll NOR start digging blank rock at it: the vein
        # is dropped (it is not distance-1) and the run moves on — the coverage
        # design trades the expensive vein for reliably finishing the cheap ones.
        from collections import deque

        grids = {
            Position(12, 126): grid(12, 126),  # player tile (passable)
            Position(13, 126): grid(13, 126),  # oscillation partner
            Position(12, 127): grid(12, 127, passable=False, can_dig=True),  # rock toward vein
            Position(12, 129): grid(12, 129, passable=False, gold=True, can_dig=True),  # vein
        }
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("t", TVAL_SCROLL, 9, count=3)],  # teleport, must stay untouched
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("d", 20, 1, is_equipment=True),  # a digging tool (TV_DIGGING)
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key  # already detected: skip re-read
        pol._known_treasure = {Position(12, 129)}
        pol._treasure_target = Position(12, 129)
        pol._recent = deque(
            [Position(12, 126), Position(13, 126)] * 5, maxlen=STUCK_WINDOW
        )
        key = pol._fundraising_key(snap, [])
        self.assertNotEqual(key, "rt")  # the teleport scroll stays in the kit
        self.assertNotEqual(pol.last_reason, "fundraise:tunnel-to-treasure")
        self.assertIn(Position(12, 129), pol._mining_dropped_veins)
        self.assertEqual(pol._mining_veins_dropped, 1)

    def test_gives_up_when_oscillating_with_nothing_diggable(self):
        # Oscillating with NO vein tunnellable toward and none reachable on foot: leave
        # (climb out) rather than dig or read a Teleport scroll. It must NOT walk
        # (seek-treasure) while bouncing, nor spend any scroll.
        from collections import deque

        grids = {Position(12, 126): grid(12, 126), Position(13, 126): grid(13, 126)}
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("t", TVAL_SCROLL, 9, count=3)],  # teleport, must stay untouched
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("d", 20, 1, is_equipment=True),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        pol._known_treasure = {Position(9, 126)}  # vein exists but no diggable neighbour
        pol._recent = deque(
            [Position(12, 126), Position(13, 126)] * 5, maxlen=STUCK_WINDOW
        )
        key = pol._fundraising_key(snap, [])
        self.assertFalse(key.startswith(READ_KEY))  # no teleport / no scroll
        self.assertNotIn(
            pol.last_reason,
            {
                "fundraise:teleport-unstick",
                "fundraise:tunnel-to-treasure",  # nothing diggable
                "fundraise:seek-treasure",  # must not walk while bouncing
            },
        )

    def test_spent_leash_finishes_the_floor_without_tunneling(self):
        # The safety leash still bounds a degenerate run, and even then the exit
        # never falls back to digging blank rock toward a far vein.
        from collections import deque
        from hengbot.policy import MINING_STALL_LIMIT

        grids = {
            Position(12, 126): grid(12, 126),
            Position(13, 126): grid(13, 126),
            Position(12, 127): grid(12, 127, passable=False, can_dig=True),  # rock toward vein
            Position(12, 129): grid(12, 129, passable=False, gold=True, can_dig=True),  # vein
        }
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("t", TVAL_SCROLL, 9, count=3)],
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("d", 20, 1, is_equipment=True),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        pol._known_treasure = {Position(12, 129)}
        pol._recent = deque(
            [Position(12, 126), Position(13, 126)] * 5, maxlen=STUCK_WINDOW
        )
        pol._mining_stall_turns = MINING_STALL_LIMIT
        key = pol._fundraising_key(snap, [])
        self.assertNotEqual(key, TUNNEL_KEY + "6")
        self.assertNotEqual(pol.last_reason, "fundraise:tunnel-to-treasure")
        # And the exit never re-reads a detection scroll either.
        key = pol._fundraising_key(snap, [])
        self.assertFalse(key.startswith(READ_KEY))
        self.assertNotEqual(pol.last_reason, "fundraise:tunnel-to-treasure")

    def test_spent_leash_still_digs_one_adjacent_gold_vein(self):
        from hengbot.policy import MINING_STALL_LIMIT

        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(
                    10, 11, passable=False, gold=True, can_dig=True
                ),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            equipment=[
                item(
                    "g", TVAL_LITE, SV_LITE_LANTERN,
                    fuel=5000, is_equipment=True,
                ),
                item("d", 20, 1, is_equipment=True),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        pol._mining_sweep_done = True
        pol._mining_stall_turns = MINING_STALL_LIMIT

        self.assertEqual(pol._fundraising_key(snap, []), TUNNEL_KEY + "6")
        self.assertEqual(pol.last_reason, "fundraise:mine-treasure")
        self.assertEqual(pol._mining_stall_turns, 0)

    def test_leash_expiry_leaves_toward_upstairs_without_reading_a_scroll(self):
        # With the leash already spent and no gold in reach, the miner heads out (digging
        # toward the up-stairs here) rather than re-reading a detection scroll or teleporting.
        from hengbot.policy import MINING_STALL_LIMIT

        grids = {
            Position(10, 10): grid(10, 10),  # player
            Position(10, 11): grid(10, 11, passable=False, can_dig=True),  # rock toward stairs
            Position(10, 12): grid(10, 12, passable=False, upstairs=True, can_dig=True),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                item("t", TVAL_SCROLL, 9, count=3),  # teleport, must stay untouched
                item("s", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=3),  # detection, unused
            ],
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("d", 20, 1, is_equipment=True),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key  # already detected this floor
        pol._mining_stall_turns = MINING_STALL_LIMIT  # leash spent
        key = pol._fundraising_key(snap, [])
        self.assertEqual(key, TUNNEL_KEY + "6")  # digging OUT toward the up-stairs
        self.assertEqual(pol.last_reason, "fundraise:tunnel-out")
        self.assertFalse(key.startswith(READ_KEY))  # neither detect-treasure nor teleport

    def test_walled_vein_is_left_instead_of_tunneled_at(self):
        # Coverage design: a vein with no walkable approach is the EXPENSIVE
        # kind — blank-rock digging burned the leash and stranded the rest of
        # the floor. It is left behind (never tunnelled at, never a reason to
        # read a scroll); the cheap veins elsewhere get the time instead.
        grids = {
            Position(12, 126): grid(12, 126),  # player (its only known tile is walled in)
            Position(12, 127): grid(12, 127, passable=False, can_dig=True),  # rock toward vein
            Position(12, 129): grid(12, 129, passable=False, gold=True, can_dig=True),  # vein
        }
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("t", TVAL_SCROLL, 9, count=3)],  # teleport, must stay untouched
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("d", 20, 1, is_equipment=True),  # digger equipped
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        pol._known_treasure = {Position(12, 129)}
        # NOT oscillating (empty history) and no walkable approach to the vein.
        self.assertFalse(pol._is_oscillating())
        key = pol._fundraising_key(snap, [])
        self.assertNotEqual(key, TUNNEL_KEY + "6")
        self.assertNotEqual(pol.last_reason, "fundraise:tunnel-to-treasure")
        self.assertEqual(pol._mining_stall_turns, MINING_STALL_LIMIT)

    def test_wields_digger_answering_the_which_hand_prompt_with_a_shield_on(self):
        # With BOTH hands full (weapon + shield) wielding a digging tool opens an
        # "Equip which hand?" prompt (cmd-equipment.cpp:190). The bare `w`+slot leaves
        # that prompt open and loops forever (the loop that stopped the bot at Yeek
        # Cave). The wield must answer 'a' (main hand) so it actually takes.
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            {Position(12, 126): grid(12, 126), Position(13, 126): grid(13, 126)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("t", TVAL_SCROLL, 9, count=3), item("j", 20, 4)],  # teleport + digger
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("main_hand", 23, 1, is_equipment=True, name="Broad Sword"),
                item("sub_hand", 34, 2, is_equipment=True, name="Small metal shield"),  # TV_SHIELD
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        self.assertEqual(pol._fundraising_key(snap, []), "wja")
        self.assertEqual(pol.last_reason, "fundraise:wield-digging-tool")
        self.assertEqual(pol._normal_weapon_name, "Broad Sword")  # remembered to re-wield

    def test_wields_digger_with_a_dual_wield_answer_when_a_hand_is_free(self):
        # Only the main hand occupied: wield_slot suggests the free sub hand, so
        # the game asks "Dual wielding? [y/n]" (not "which hand?"); n replaces
        # the main-hand weapon with the digger instead of dual-wielding.
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            {Position(12, 126): grid(12, 126), Position(13, 126): grid(13, 126)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("t", TVAL_SCROLL, 9, count=3), item("j", 20, 4)],  # teleport + digger
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("main_hand", 23, 1, is_equipment=True, name="Broad Sword"),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        self.assertEqual(pol._fundraising_key(snap, []), "wjn")
        self.assertEqual(pol.last_reason, "fundraise:wield-digging-tool")

    def test_gives_up_mining_when_the_weapon_will_not_swap_for_the_digger(self):
        # A truly stuck / cursed main weapon that never yields to the digging-tool wield
        # (even after answering the which-hand prompt) must not re-issue "wield" forever
        # (the loop that stopped the bot) — after DIGGER_WIELD_LIMIT attempts, abandon.
        from hengbot.policy import DIGGER_WIELD_LIMIT

        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            {Position(12, 126): grid(12, 126), Position(13, 126): grid(13, 126)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("t", TVAL_SCROLL, 9, count=3), item("j", 20, 4)],  # teleport + digger
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("main_hand", 23, 1, is_equipment=True, name="Cursed Hammer"),
                item("sub_hand", 34, 2, is_equipment=True, name="Small metal shield"),  # TV_SHIELD
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        keys = [pol._fundraising_key(snap, []) for _ in range(DIGGER_WIELD_LIMIT)]
        self.assertTrue(all(k == "wja" for k in keys[:-1]))  # kept trying, then...
        self.assertNotEqual(pol.last_reason, "fundraise:wield-digging-tool")  # gave up
        self.assertIsNone(pol._fundraising_mode)  # mining abandoned


class DeepKitTest(unittest.TestCase):
    """10F+ departure kit and teleport-return strategy: carry 15 teleport scrolls
    and >=20 total identify charges, and head home only at the low teleport
    reserve (3) rather than the moment the big buffer dips."""

    def _pol(self, deepest):
        pol = HengbotPolicy()
        pol._deepest_level = deepest
        return pol

    def _dungeon(self, level, inventory):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, level, 0),
            inventory=inventory,
        )

    def _tp(self, count):
        return [item("t", TVAL_SCROLL, 9, count=count)]  # teleport sval 9

    def test_teleport_target_scales_with_depth(self):
        snap = self._dungeon(1, [])
        self.assertEqual(self._pol(3)._teleport_target(snap), 3)     # planned 4
        self.assertEqual(self._pol(10)._teleport_target(snap), 15)   # planned 11

    def test_deep_teleport_ready_needs_fifteen(self):
        pol = self._pol(10)
        self.assertFalse(pol._teleport_ready(self._dungeon(11, self._tp(10))))
        self.assertTrue(pol._teleport_ready(self._dungeon(11, self._tp(15))))

    def test_deep_return_only_at_low_reserve(self):
        pol = self._pol(10)
        # below the 15 target but above the reserve -> keep exploring, do not thrash
        stocked = self._dungeon(11, self._tp(10))
        low = self._dungeon(11, self._tp(3))
        stocked_teleport = pol._supply_ledger(stocked, stocked.dungeon_level)["teleport"]
        low_teleport = pol._supply_ledger(low, low.dungeon_level)["teleport"]
        self.assertFalse(pol._ledger_return_shortages(
            {"teleport": stocked_teleport}, stocked.dungeon_level
        ))
        self.assertTrue(pol._ledger_return_shortages(
            {"teleport": low_teleport}, low.dungeon_level
        ))

    def test_shallow_return_uses_plain_below_target(self):
        pol = self._pol(3)  # planned 4, target 3
        low = self._dungeon(4, self._tp(2))
        stocked = self._dungeon(4, self._tp(3))
        low_teleport = pol._supply_ledger(low, low.dungeon_level)["teleport"]
        stocked_teleport = pol._supply_ledger(stocked, stocked.dungeon_level)["teleport"]
        self.assertTrue(pol._ledger_return_shortages(
            {"teleport": low_teleport}, low.dungeon_level
        ))
        self.assertFalse(pol._ledger_return_shortages(
            {"teleport": stocked_teleport}, stocked.dungeon_level
        ))

    def test_deep_staff_needs_twenty_total_charges(self):
        pol = self._pol(10)
        one = [item("n", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=12)]
        two = [
            item("n", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=12),
            item("m", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=10),
        ]
        self.assertFalse(pol._identify_staff_ready(self._dungeon(11, one)))  # 12 < 20
        self.assertTrue(pol._identify_staff_ready(self._dungeon(11, two)))   # 22 >= 20
        self.assertEqual(pol._total_identify_staff_charges(self._dungeon(11, two)), 22)

class StoreSellGateTest(unittest.TestCase):
    def _store(self, inventory, store_type, *, turn=758358):
        return Snapshot(
            player(
                10, 10, class_id=PLAYER_CLASS_WARRIOR,
                food_type=4, gold=1000,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            turn=turn,
            inventory=list(inventory),
            store=StoreState(store_type, []),
        )

    def test_2139_replay_unaccepted_alchemist_food_emits_no_sell_or_tail(self):
        mana_food = item("a", TVAL_FOOD, 1, name="Ration of Food", known=True)
        snap = self._store([mana_food], STORE_ALCHEMIST)
        policy = HengbotPolicy()

        keys = [policy._shop(snap) for _ in range(3)]

        self.assertEqual(keys, [LEAVE_STORE_KEY] * 3)
        self.assertTrue(all("d" not in key and "\r" not in key and "y" not in key for key in keys))
        self.assertNotIn(policy._item_signature(mana_food), policy._unsellable_items)

    def test_mana_race_food_is_sold_at_general_store(self):
        mana_food = item("a", TVAL_FOOD, 1, name="Ration of Food", known=True)
        policy = HengbotPolicy()

        self.assertEqual(
            policy._shop(self._store([mana_food], STORE_GENERAL)),
            "da\r",
        )
        self.assertEqual(policy.last_reason, "shop:sell-mana-race-food")

    def test_unsellable_latch_clears_on_next_town_visit(self):
        potion = item("a", TVAL_POTION, SV_POTION_RESIST_COLD)
        policy = HengbotPolicy()
        policy._unsellable_items.add(policy._item_signature(potion))
        policy._floor_key = (1, 5, 0)

        policy._observe(self._store([potion], STORE_ALCHEMIST))

        self.assertNotIn(policy._item_signature(potion), policy._unsellable_items)

    def test_same_turn_unchanged_sale_latches_after_one_emitted_attempt(self):
        potion = item("a", TVAL_POTION, SV_POTION_RESIST_COLD)
        snap = self._store([potion], STORE_ALCHEMIST)
        policy = HengbotPolicy()

        # One emit whose board is unchanged proves the sale was rejected (a
        # genuine duplicate snapshot only re-fires after the retry delay, by which
        # time the game has processed the key). Leave instead of re-emitting the
        # multi-key sell — a second emit lands its trailing keys in the store
        # command loop after the "no room" message (the observed desync).
        self.assertEqual(policy._shop(snap), "da\r")
        self.assertEqual(policy._shop(snap), LEAVE_STORE_KEY)
        self.assertIn(policy._item_signature(potion), policy._unsellable_items)

    def test_changed_turn_latches_only_after_three_attempts(self):
        potion = item("a", TVAL_POTION, SV_POTION_RESIST_COLD)
        policy = HengbotPolicy()

        for turn in range(2):
            self.assertEqual(
                policy._shop(self._store([potion], STORE_ALCHEMIST, turn=turn)),
                "da\r",
            )
        self.assertEqual(
            policy._shop(self._store([potion], STORE_ALCHEMIST, turn=2)),
            LEAVE_STORE_KEY,
        )
        self.assertIn(policy._item_signature(potion), policy._unsellable_items)


class RetentionAuthorityTest(unittest.TestCase):
    def _town(self, inventory, *, store=None, gold=FUNDRAISING_START_GOLD):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=gold),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inventory),
            store=store,
        )

    def test_replay_just_bought_detection_and_planned_shovel_stay_in_pack(self):
        detection = item(
            "h", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
            name="Scroll of Treasure Detection",
        )
        shovel = item("k", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="Shovel", pval=1)
        snap = self._town([detection, shovel], store=StoreState(STORE_HOME, []))
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._town_visit_purchases.add(policy._item_signature(detection))

        self.assertEqual(policy._retention_reservation(snap, detection), 1)
        self.assertEqual(policy._retention_reservation(snap, shovel), 1)
        self.assertIsNone(policy._find_home_deposit(snap))

    def test_town_cycle_planned_yeek_mining_keeps_last_detection_scroll(self):
        """21:38 replay: Home runs before the low-gold errand starts mining."""
        detection = item(
            "h", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
            name="Scroll of Treasure Detection",
        )
        snap = self._town(
            [detection], store=StoreState(STORE_HOME, []), gold=2999
        )
        policy = HengbotPolicy()
        self.assertIsNone(policy._fundraising_mode)

        self.assertEqual(policy._retention_reservation(snap, detection), 1)
        self.assertIsNone(policy._find_home_deposit(snap))
        self.assertEqual(policy._next_required_store_type(snap), STORE_HOME)
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_ten_torches_are_reserved_and_real_surplus_deposits_once(self):
        torches = item(
            "j", TVAL_LITE, SV_LITE_TORCH,
            count=14, name="Wooden Torches", fuel=5000,
        )
        snap = self._town([torches], store=StoreState(STORE_HOME, []))
        policy = HengbotPolicy()

        self.assertEqual(policy._retention_reservation(snap, torches), 10)
        self.assertEqual(policy._retention_surplus(snap, torches), 4)
        self.assertEqual(policy._find_home_deposit(snap), torches)
        self.assertEqual(policy._home_deposit_key(snap, torches), "dj4\r")

    def test_same_visit_purchase_guard_clears_on_floor_change(self):
        detection = item(
            "h", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
            name="Scroll of Treasure Detection",
        )
        policy = HengbotPolicy()
        policy._town_visit_purchases.add(policy._item_signature(detection))
        town = self._town([detection])
        policy._floor_key = town.floor_key
        self.assertEqual(policy._retention_reservation(town, detection), 1)

        dungeon = replace(town, floor_key=(1, 1, 0), town_flag=False)
        policy._observe(dungeon)
        self.assertFalse(policy._town_visit_purchases)


class HomeFullLatchTest(unittest.TestCase):
    """A full Home must not latch a sticky town block: the deposit just stops for
    the visit and other errands proceed (mirrors the bounty-office fix)."""

    def _town_snap(self, inventory):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
        )

    def test_full_home_latch_stops_deposits_without_sticky_block(self):
        gear = item("a", TVAL_RING, 0, is_equipment=True, known=True, name="ring")
        pol = HengbotPolicy()
        snap = self._town_snap([gear])
        self.assertIsNotNone(pol._find_home_deposit(snap))  # normally depositable
        pol._home_full = True
        self.assertIsNone(pol._find_home_deposit(snap))     # latch stops it
        self.assertIsNone(pol._town_blocked_reason)          # never a sticky block

    def test_dungeon_clears_home_full_latch(self):
        pol = HengbotPolicy()
        pol._home_full = True
        pol._observe(
            Snapshot(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                {Position(10, 10): grid(10, 10)},
                [],
                floor_key=(1, 5, 0),
            )
        )
        self.assertFalse(pol._home_full)

    def test_rejected_deposit_stops_all_deposits_for_the_town_visit(self):
        ring = item("k", TVAL_RING, 39, is_equipment=True, known=True)
        amulet = item("l", TVAL_AMULET, 4, is_equipment=True, known=True)
        snap = replace(
            self._town_snap([ring, amulet]),
            store=StoreState(STORE_HOME, []),
        )
        pol = HengbotPolicy()

        keys = [pol._shop(snap) for _ in range(STORE_STUCK_LIMIT + 1)]

        self.assertEqual(keys[-1], LEAVE_STORE_KEY)
        self.assertEqual(pol.last_reason, "home:deposit-rejected")
        self.assertFalse(pol._home_full)
        self.assertTrue(pol._home_deposit_abandoned)
        self.assertIn(pol._item_signature(ring), pol._home_rejected_deposits)
        self.assertIsNone(pol._find_home_deposit(snap))

    def test_arrow_home_deposit_enters_full_stack_quantity(self):
        arrows = item("m", TVAL_ARROW, 5, count=9, name="animal slayer arrows")
        snap = replace(
            self._town_snap([arrows]),
            store=StoreState(STORE_HOME, []),
        )
        pol = HengbotPolicy()

        self.assertEqual(pol._home_deposit_key(snap, arrows), "dm9\r")
        self.assertEqual(pol.last_reason, "home:deposit")

    def test_partial_arrow_stack_progress_does_not_count_as_rejection(self):
        pol = HengbotPolicy()

        for count in range(9, 2, -1):
            arrows = item("m", TVAL_ARROW, 5, count=count, name="animal slayer arrows")
            snap = replace(
                self._town_snap([arrows]),
                store=StoreState(STORE_HOME, []),
            )
            self.assertEqual(pol._home_deposit_key(snap, arrows), f"dm{count}\r")

        self.assertEqual(pol.last_reason, "home:deposit")
        self.assertFalse(pol._home_deposit_abandoned)
        self.assertEqual(pol._store_sell_stuck_count, 0)


class GlobalEquipmentOptimizationOwnershipTest(unittest.TestCase):
    def _town(self, *, inventory=(), equipment=(), store=None):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inventory),
            equipment=list(equipment),
            store=store,
        )

    def test_inscribes_pack_random_teleport_item_in_town(self):
        mask = item(
            "a", 32, 5, name="Terror Mask", known=True, fully_known=True,
            is_equipment=True, is_artifact=True,
            known_flags=frozenset({TR_TELEPORT}),
        )
        policy = HengbotPolicy()

        key = policy._town_random_teleport_suppression_key(
            self._town(inventory=(mask,))
        )

        self.assertEqual(key, "{a.\r")
        self.assertEqual(policy.last_reason, "equipment:suppress-random-teleport")

    def test_withdraws_home_random_teleport_item_before_inscribing(self):
        mask = store_item(
            "b", 32, 5, name="Terror Mask", known=True, fully_known=True,
            is_equipment=True, is_artifact=True,
            known_flags=frozenset({TR_TELEPORT}),
        )
        policy = HengbotPolicy()

        key = policy._town_random_teleport_suppression_key(
            self._town(store=StoreState(STORE_HOME, [mask]))
        )

        self.assertEqual(key, "pb\r")
        self.assertEqual(
            policy.last_reason, "home:withdraw-random-teleport-for-inscription"
        )

    def test_leaves_store_before_inscribing_carried_item(self):
        mask = item(
            "a", 32, 5, name="Terror Mask", known=True, fully_known=True,
            is_equipment=True, known_flags=frozenset({TR_TELEPORT}),
        )
        policy = HengbotPolicy()

        key = policy._town_random_teleport_suppression_key(
            self._town(
                inventory=(mask,),
                store=StoreState(STORE_HOME, []),
            )
        )

        self.assertEqual(key, LEAVE_STORE_KEY)

    def test_inscribes_equipped_random_teleport_item(self):
        mask = item(
            "head", 32, 5, name="Terror Mask", known=True, fully_known=True,
            is_equipment=True, known_flags=frozenset({TR_TELEPORT}),
        )
        policy = HengbotPolicy()

        key = policy._town_random_teleport_suppression_key(
            self._town(equipment=(mask,))
        )

        self.assertEqual(key, "{/j.\r")

    def test_cursed_random_teleport_item_is_not_inscribed(self):
        mask = item(
            "a", 32, 5, name="Cursed Terror Mask", known=True,
            fully_known=True, is_equipment=True, is_cursed=True,
            known_flags=frozenset({TR_TELEPORT}),
        )
        self.assertIsNone(
            HengbotPolicy()._town_random_teleport_suppression_key(
                self._town(inventory=(mask,))
            )
        )

    def test_already_suppressed_home_item_is_not_withdrawn_again(self):
        mask = store_item(
            "b", 32, 5, name="Terror Mask {.}", known=True,
            fully_known=True, is_equipment=True, is_artifact=True,
            known_flags=frozenset({TR_TELEPORT}),
        )
        self.assertIsNone(
            HengbotPolicy()._town_random_teleport_suppression_key(
                self._town(store=StoreState(STORE_HOME, [mask]))
            )
        )

    def test_home_processing_withdraws_only_incomplete_equipment(self):
        complete = store_item(
            "a", 23, 1, name="known sword", aware=True, known=True,
            fully_known=True, is_equipment=True,
        )
        incomplete = store_item(
            "b", 23, 2, name="unknown sword", aware=False, known=False,
            is_equipment=True,
        )
        snap = self._town(store=StoreState(STORE_HOME, [complete, incomplete]))

        candidate = HengbotPolicy()._find_home_candidate(snap)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.name, "unknown sword")

    def test_prime_queues_only_equipment_needing_identification(self):
        complete = item(
            "a", 23, 1, name="known sword", known=True, fully_known=True,
            is_equipment=True,
        )
        incomplete = item(
            "b", 23, 2, name="unknown sword", aware=False, known=False,
            is_equipment=True,
        )
        policy = HengbotPolicy()

        policy.prime(self._town(inventory=(complete, incomplete)))

        self.assertEqual(
            policy._home_pending_batch,
            [policy._item_signature(incomplete)],
        )

    def test_optimizer_preserves_inferior_pack_weapon_for_smith_sale(self):
        policy = HengbotPolicy()
        spare = item(
            "b", 23, 0, name="mundane spare", known=True, fully_known=True,
            is_equipment=True,
        )
        snap = self._town(inventory=(spare,), equipment=(
            item(
                "main_hand", 23, 8, name="ego weapon", known=True,
                fully_known=True, is_equipment=True, is_ego=True,
            ),
        ))
        policy._equipment_catalog.refresh_carried(snap.inventory, snap.equipment)
        captured = {}

        def fake_prepare(*args, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(ready=False, transaction=None)

        with patch("hengbot.policy.prepare_warrior_optimization", fake_prepare):
            policy._prepare_equipment_optimization(snap)

        spare_id = next(
            owned.id for owned in policy._equipment_catalog.items
            if owned.origin == "pack"
        )
        self.assertIn(spare_id, captured["preserve_pack_item_ids"])


class FullPackDisposalTest(unittest.TestCase):
    """Full-pack disposal: destroy keys must fire in the original keyset, progress must be
    verified, and an item the game refuses to destroy
    must be abandoned rather than looped on forever.
    """

    def _full_pack(self, *disposables):
        # Charged staves so the inert filler is not itself disposable (a drained
        # 0-charge staff now IS), which would otherwise be picked before the target.
        filler = [
            item(chr(ord("a") + i), TVAL_STAFF, i, name=f"filler-{i}", charges=5)
            for i in range(PACK_CAPACITY - len(disposables))
        ]
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 5, 0),  # in the dungeon, where disposal happens
            inventory=[*filler, *disposables],
        )

    def test_zero_fuel_torch_destroyed_with_original_destroy_key(self):
        torch = item("q", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=0)
        pol = HengbotPolicy()
        # Original destroy = k; "01" forces it (no confirmation prompt) and
        # destroys the whole stack with no movement/confirmation keys leaking.
        self.assertEqual(pol._full_pack_destroy_key(self._full_pack(torch)), "01kq")

    def test_stacked_disposable_destroys_whole_stack_via_command_arg(self):
        potions = item("q", TVAL_POTION, SV_POTION_SLEEP, name="sleep", count=4)
        pol = HengbotPolicy()
        self.assertEqual(pol._full_pack_destroy_key(self._full_pack(potions)), "04kq")

    def test_empty_chests_are_disposable_junk(self):
        policy = HengbotPolicy()
        for name in (
            "small wooden chest (empty)",
            "小さな木の箱 (空)",
            "壊れた鉄の箱",
        ):
            with self.subTest(name=name):
                chest = item("q", TVAL_CHEST, 1, name=name)
                self.assertTrue(policy._is_disposable_item(chest))
                self.assertEqual(
                    policy._full_pack_destroy_key(self._full_pack(chest)), "01kq"
                )
                policy._destroy_watch = None

    def test_unidentified_mushroom_is_disposable_but_food_ration_is_kept(self):
        pol = HengbotPolicy()
        # Unidentified mushroom (unaware food): a poison gamble worth nothing.
        mushroom = item("q", TVAL_FOOD, 5, name="mushroom", aware=False)
        self.assertTrue(pol._is_disposable_item(mushroom))
        # A known ration nourishes and must be kept; an identified mushroom may be
        # beneficial, so only UNidentified food is shed.
        self.assertFalse(pol._is_disposable_item(item("r", TVAL_FOOD, 35, name="ration")))
        self.assertFalse(
            pol._is_disposable_item(item("s", TVAL_FOOD, 5, name="known mushroom"))
        )

    def test_unchanged_pack_marks_item_undestroyable_and_gives_up(self):
        torch = item("q", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=0)
        snap = self._full_pack(torch)
        pol = HengbotPolicy()
        # Re-deciding on an unchanged pack means the destroy never took. After the
        # retry budget the item is abandoned and None lets return-to-town take over.
        results = [pol._full_pack_destroy_key(snap) for _ in range(DESTROY_FAIL_LIMIT + 2)]
        self.assertEqual(results[0], "01kq")
        self.assertIsNone(results[-1])
        self.assertIn(pol._item_signature(torch), pol._undestroyable_sigs)

    def test_next_disposable_tried_once_first_is_undestroyable(self):
        torch = item("q", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=0)
        bottle = item("r", TVAL_BOTTLE, 1, name="bottle")
        pol = HengbotPolicy()
        pol._undestroyable_sigs.add(pol._item_signature(torch))
        # The torch is skipped; the empty bottle is the next disposable target.
        self.assertEqual(
            pol._full_pack_destroy_key(self._full_pack(torch, bottle)), "01kr"
        )

    def test_all_undestroyable_returns_none_for_town_return(self):
        torch = item("q", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=0)
        pol = HengbotPolicy()
        pol._undestroyable_sigs.add(pol._item_signature(torch))
        self.assertIsNone(pol._full_pack_destroy_key(self._full_pack(torch)))

    def test_bounty_item_is_never_disposed(self):
        # A wanted (bounty) item is worth gold at the Hunter's Office even if its
        # pseudo-feeling reads 'average', so it must not be destroyed.
        bounty = replace(
            item("q", TVAL_POTION, 28, name="wanted", pseudo_feeling="average"),
            is_bounty=True,
        )
        pol = HengbotPolicy()
        self.assertFalse(pol._is_disposable_item(bounty))
        self.assertIsNone(pol._full_pack_destroy_key(self._full_pack(bounty)))

    def test_undestroyable_cleared_on_town_arrival(self):
        torch = item("q", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=0)
        pol = HengbotPolicy()
        pol._undestroyable_sigs.add(pol._item_signature(torch))
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        pol._observe(town)
        self.assertEqual(pol._undestroyable_sigs, set())


class DungeonConquestTest(unittest.TestCase):
    """Priority goal: clear an unconquered dungeon whose bottom is within the
    resistance limit for the final guardian's gear, and collect that drop before
    recalling out."""

    def _dk(self):
        return {
            1: DungeonInfo(1, "Angband", 1, 127, 30),
            2: DungeonInfo(2, "Galgals", 1, 13, 1),
            3: DungeonInfo(3, "Orc Cave", 10, 22, 5),
            4: DungeonInfo(4, "Labyrinth", 10, 18, 1),
            7: DungeonInfo(7, "Forest", 15, 32, 5),
            14: DungeonInfo(14, "Mountain", 25, 45, 20),
        }

    def _policy(self):
        return HengbotPolicy(dungeon_knowledge=self._dk())

    def _snap(self, abilities, *, conquered=(), clvl=26):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=clvl,
                   abilities=frozenset(abilities)),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            entered_dungeon_ids=(1, 2, 3, 4, 7, 14),
            conquered_dungeon_ids=conquered,
            angband_recall_unlocked=True,
        )

    ALL_2530 = frozenset(
        {"resist_conf", "resist_fire", "resist_pois", "resist_cold",
         "resist_elec", "resist_acid"}
    )

    @staticmethod
    def _minotaur_knowledge():
        return MonraceKnowledge(
            max_hp=330,
            average_hp=330,
            speed=125,
            can_summon=False,
            friendly=False,
            level=18,
            max_melee_damage=126,
            flags=frozenset({"UNIQUE"}),
            blows=(
                MonsterBlow("BUTT", "HURT", 6, 6),
                MonsterBlow("BUTT", "HURT", 6, 6),
                MonsterBlow("BUTT", "HURT", 3, 6),
                MonsterBlow("BUTT", "HURT", 3, 6),
            ),
        )

    def _minotaur_snapshot(self, healing_count):
        snapshot = self._snap(self.ALL_2530, conquered=(3,), clvl=23)
        return replace(
            snapshot,
            player=replace(
                snapshot.player,
                hp=400,
                max_hp=400,
                speed=110,
                ac=43,
                main_hand_blows=5,
                main_hand_to_h=21,
                main_hand_to_d=8,
            ),
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("h", TVAL_POTION, SV_POTION_HEALING, count=healing_count),
            ],
            equipment=[
                item(
                    "main_hand",
                    23,
                    20,
                    is_equipment=True,
                    damage_dice_num=3,
                    damage_dice_sides=4,
                )
            ],
        )

    def _guardian_policy(self):
        knowledge = self._dk()
        knowledge[4] = replace(knowledge[4], guardian_id=1034)
        return HengbotPolicy(
            dungeon_knowledge=knowledge,
            monrace_knowledge={1034: self._minotaur_knowledge()},
        )

    def _yeek_guardian_policy(self):
        knowledge = self._dk()
        knowledge[2] = replace(knowledge[2], guardian_id=237)
        guardian = replace(
            self._minotaur_knowledge(),
            max_hp=180,
            average_hp=180,
            speed=120,
            can_summon=True,
            max_melee_damage=26,
            blows=(MonsterBlow("HIT", "HURT", 2, 6),),
        )
        return HengbotPolicy(
            dungeon_knowledge=knowledge,
            monrace_knowledge={237: guardian},
        )

    def _launchable_yeek_snapshot(self, *, recall_count=10):
        snapshot = replace(
            self._minotaur_snapshot(1),
            player=replace(self._minotaur_snapshot(1).player, gold=130),
            entered_dungeon_ids=(1, 2),
            angband_recall_unlocked=True,
        )
        return replace(
            snapshot,
            inventory=[
                *snapshot.inventory,
                item(
                    "r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
                    count=recall_count,
                ),
                item("f", TVAL_FOOD, FOOD_MIN_SVAL, count=10),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=10),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=20),
                item(
                    "c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10
                ),
                item(
                    "i", TVAL_STAFF, SV_STAFF_IDENTIFY,
                    charges=20,
                ),
            ],
            equipment=[
                *snapshot.equipment,
                item(
                    "light", TVAL_LITE, SV_LITE_LANTERN,
                    fuel=5000, is_equipment=True,
                ),
            ],
        )

    def test_resistance_limit_without_confusion_stops_below_20(self):
        self.assertEqual(self._policy()._resistance_depth_limit(self._snap({"resist_fire"})), 19)

    def test_resistance_limit_covers_the_bands_the_char_can_pass(self):
        # conf+fire (20-25F) but nothing for 26-30F -> limit 25.
        pol = self._policy()
        self.assertEqual(
            pol._resistance_depth_limit(self._snap({"resist_conf", "resist_fire"})), 25
        )

    def test_targets_deepest_conquerable_unconquered_dungeon(self):
        # limit 30 -> Orc Cave (maxDepth 22) is the deepest clearable; Forest(32) /
        # Mountain(45) exceed the resistance limit.
        self.assertEqual(self._policy()._conquest_target(self._snap(self.ALL_2530)), 3)

    def test_steps_to_the_next_after_the_deepest_is_conquered(self):
        pol = self._policy()
        self.assertEqual(pol._conquest_target(self._snap(self.ALL_2530, conquered=(3,))), 4)

    def test_does_not_target_labyrinth_without_a_viable_guardian_kit(self):
        policy = self._guardian_policy()

        self.assertIsNone(policy._conquest_target(self._minotaur_snapshot(1)))
        self.assertEqual(policy._conquest_target(self._minotaur_snapshot(5)), 4)

    def test_targets_beatable_yeek_guardian_even_after_angband_is_unlocked(self):
        policy = self._yeek_guardian_policy()
        snapshot = replace(
            self._minotaur_snapshot(1),
            entered_dungeon_ids=(1, 2),
            angband_recall_unlocked=True,
        )

        self.assertTrue(policy._guardian_fight_viable(snapshot, policy._dungeon_knowledge[2]))
        self.assertEqual(policy._conquest_target(snapshot), 2)

        policy._observe(snapshot)
        self.assertEqual(policy._target_dungeon_id, 2)

    def test_launchable_beatable_guardian_cancels_fundraising_latch(self):
        policy = self._yeek_guardian_policy()
        policy._fundraising_mode = "scavenge"
        snapshot = replace(
            self._minotaur_snapshot(1),
            entered_dungeon_ids=(1, 2),
            angband_recall_unlocked=True,
        )
        policy._town_departure_ready = lambda _snapshot: True
        policy._combat_weapon_ready = lambda _snapshot: True

        policy._observe(snapshot)

        self.assertEqual(policy._target_dungeon_id, 2)
        self.assertIsNone(policy._fundraising_mode)

    def test_blocked_poor_conquest_observe_decide_alternation_is_stable(self):
        policy = self._yeek_guardian_policy()
        snapshot = self._launchable_yeek_snapshot(recall_count=0)
        policy._fundraising_supplies_ready = lambda _snapshot: False
        policy._observe(snapshot)
        self.assertEqual(policy._conquest_target(snapshot), 2)
        self.assertFalse(policy._conquest_departure_ready(snapshot))
        policy._identification_need = "full"
        policy._start_fundraising(snapshot)
        policy._town_store_attempted[STORE_HOME] = 77

        reasons = []
        for offset in range(8):
            fresh = replace(snapshot, turn=snapshot.turn + offset)
            policy.choose_key(fresh)
            reasons.append(policy.last_reason)
            self.assertEqual(policy._fundraising_mode, "prepare")

        self.assertEqual(policy._town_store_attempted[STORE_HOME], 77)
        self.assertNotIn("home:need-full-identify", reasons)

    def test_blocked_conquest_clears_fundraising_once_when_departure_becomes_ready(self):
        policy = self._yeek_guardian_policy()
        blocked = self._launchable_yeek_snapshot(recall_count=0)
        ready = self._launchable_yeek_snapshot()

        policy._observe(blocked)
        policy._start_fundraising(blocked)
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertIsNone(policy._fundraising_cleared_for_conquest)

        policy._observe(ready)
        self.assertIsNone(policy._fundraising_mode)
        self.assertEqual(policy._fundraising_cleared_for_conquest, 2)

        policy._start_fundraising(ready)
        policy._observe(replace(ready, turn=ready.turn + 1))
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(policy._fundraising_cleared_for_conquest, 2)

    def test_beatable_guardian_defers_unavailable_full_identification(self):
        policy = self._yeek_guardian_policy()
        candidate = item(
            "c",
            45,
            1,
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        snapshot = replace(
            self._minotaur_snapshot(1),
            player=replace(self._minotaur_snapshot(1).player, gold=625),
            inventory=[*self._minotaur_snapshot(1).inventory, candidate],
        )
        signature = policy._item_signature(candidate)

        policy._observe(snapshot)
        policy._identification_need = "full"
        policy._identification_candidate = signature
        policy._town_store_attempted[STORE_ALCHEMIST] = 0

        # Exercise the terminal identification branch directly: the top-level
        # router's new poverty source otherwise activates fundraising before
        # this already-in-flight defer can be serviced.
        next_store = policy._legacy_town_router_terminal(snapshot)

        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)
        self.assertIsNone(policy._identification_need)
        self.assertIn(signature, policy._deferred_home_items)
        self.assertNotEqual(next_store, STORE_ALCHEMIST)

    def test_multiplier_guardian_is_not_selected_for_conquest(self):
        policy = self._yeek_guardian_policy()
        policy._monrace_knowledge[237] = replace(
            policy._monrace_knowledge[237], can_multiply=True
        )
        snapshot = replace(
            self._minotaur_snapshot(5),
            entered_dungeon_ids=(1, 2),
        )

        self.assertIsNone(policy._conquest_target(snapshot))

    def test_beatable_summoning_guardian_teleports_to_reposition_without_returning(self):
        policy = self._yeek_guardian_policy()
        guardian = replace(
            hostile(
                1,
                10,
                13,
                hp=180,
                max_hp=180,
                distance=3,
                can_summon=True,
            ),
            race_id=237,
        )
        grids = {
            Position(y, x): grid(y, x, monster=(y, x) == (10, 13))
            for y in range(8, 13)
            for x in range(8, 15)
        }
        snapshot = replace(
            self._minotaur_snapshot(1),
            floor_key=(2, 13, 0),
            town_flag=False,
            grids=grids,
            visible_monsters=[guardian],
            entered_dungeon_ids=(1, 2),
            inventory=[
                *self._minotaur_snapshot(1).inventory,
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )
        policy._target_dungeon_id = 2

        self.assertEqual(policy.choose_key(snapshot), "rt")
        self.assertEqual(policy.last_reason, "guardian:teleport-to-cover")
        self.assertEqual(policy._last_return_trigger, "guardian-reposition")
        self.assertFalse(policy._returning_to_town)

    def test_returns_from_penultimate_floor_when_guardian_kit_is_insufficient(self):
        policy = self._guardian_policy()
        snapshot = replace(
            self._minotaur_snapshot(1),
            floor_key=(4, 17, 0),
            town_flag=False,
            grids={Position(10, 10): grid(10, 10, downstairs=True)},
        )
        downstairs = snapshot.grid_at(snapshot.player.position)

        self.assertTrue(policy._guardian_descent_blocked(snapshot))
        self.assertTrue(policy._should_start_town_return(snapshot))
        self.assertEqual(policy._last_return_trigger, "guardian-kit-insufficient")
        self.assertFalse(policy._is_descent_target(snapshot, downstairs))

    def test_no_target_when_all_reachable_dungeons_are_conquered(self):
        pol = self._policy()
        self.assertIsNone(pol._conquest_target(self._snap(self.ALL_2530, conquered=(3, 4))))

    def test_observe_latches_the_loot_phase_on_a_fresh_conquest(self):
        pol = self._policy()
        before = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=26),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(4, 18, 0),
            entered_dungeon_ids=(1, 2, 4),
            conquered_dungeon_ids=(),
            angband_recall_unlocked=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=26),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(4, 18, 0),  # standing in the Labyrinth, just conquered
            entered_dungeon_ids=(1, 2, 4),
            conquered_dungeon_ids=(4,),
            angband_recall_unlocked=True,
        )
        pol._observe(before)
        pol._observe(snap)
        self.assertEqual(pol._victory_loot_dungeon, 4)

    def test_resume_on_conquered_yeek_floor_does_not_rearm_victory_return(self):
        pol = self._policy()
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=26),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 13, 0),
            entered_dungeon_ids=(1, DUNGEON_YEEK_CAVE),
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )

        pol._observe(snap)

        self.assertFalse(pol._yeek_victory_loot)
        self.assertTrue(pol._yeek_conquest_processed)

    def test_conquest_loot_sweeps_the_floor_before_returning(self):
        pol = self._policy()
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=26),
            {Position(10, 10): grid(10, 10, objects=1)},  # guardian drop underfoot
            [],
            floor_key=(4, 18, 0),
            inventory=[],
        )
        pol._victory_loot_dungeon = 4
        pol._position_changed = True
        self.assertEqual(pol._conquest_loot_key(snap), "g")
        self.assertEqual(pol.last_reason, "conquest:pickup")

    def test_yeek_victory_full_pack_discards_junk_before_more_loot(self):
        pol = self._policy()
        junk = item("a", TVAL_FOOD, 1, aware=False, known=False, name="mushroom")
        essentials = [
            item(
                chr(ord("b") + index),
                TVAL_SCROLL,
                SV_SCROLL_TELEPORT,
                name="Teleport",
            )
            for index in range(PACK_CAPACITY - 1)
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=26),
            {Position(10, 10): grid(10, 10, objects=1)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 13, 0),
            inventory=[junk, *essentials],
        )
        pol._yeek_victory_loot = True

        self.assertEqual(pol._victory_loot_key(snap), "01ka")
        self.assertEqual(pol.last_reason, "inventory:destroy-disposable-item")

    def test_conquest_loot_returns_once_the_floor_is_clean(self):
        pol = self._policy()
        recall = item(
            "a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, name="Word of Recall"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=26),
            {Position(10, 10): grid(10, 10)},  # nothing left to grab
            [],
            floor_key=(4, 18, 0),
            inventory=[recall],
        )
        pol._victory_loot_dungeon = 4
        self.assertEqual(pol._conquest_loot_key(snap), "ra")
        self.assertIsNone(pol._victory_loot_dungeon)
        self.assertTrue(pol._returning_to_town)
        self.assertEqual(pol._last_return_trigger, "conquest-complete")
        self.assertEqual(pol.last_reason, "return:recall")

    def test_latch_survives_a_speed_potion_disappearing_from_the_pack(self):
        # _guardian_fight_viable's fallback branch treats the Labyrinth Minotaur
        # fight as viable only while a Speed potion is held (see the
        # SV_POTION_SPEED check in _guardian_fight_viable): at healing=5 the base
        # (unboosted) projection fails and only the +speed retry succeeds
        # (empirically: viable with the potion in the pack, not viable without
        # it, healing held fixed). Without a latch, drinking or stashing that
        # potion would revert the conquest target on the very next observe, and
        # re-buying it would flip it back -- the recall destination churning on
        # nothing but consumable possession.
        policy = self._guardian_policy()
        with_speed = self._minotaur_snapshot(5)
        self.assertEqual(policy._conquest_target(with_speed), 4)

        without_speed = replace(
            with_speed,
            inventory=[it for it in with_speed.inventory if it.slot != "s"],
        )
        self.assertEqual(policy._conquest_target(without_speed), 4)

    def test_unlatches_once_the_dungeon_is_conquered(self):
        policy = self._guardian_policy()
        with_speed = self._minotaur_snapshot(5)
        self.assertEqual(policy._conquest_target(with_speed), 4)

        conquered = replace(with_speed, conquered_dungeon_ids=(3, 4))
        self.assertIsNone(policy._conquest_target(conquered))
        self.assertIsNone(policy._conquest_committed)

    def test_unlatches_when_the_resistance_limit_drops_below_its_max_depth(self):
        policy = self._policy()
        # Labyrinth (4) is already done, so Orc Cave (3, max_depth 22) is the
        # only dungeon within the resistance limit (30) and becomes committed.
        committed_snap = self._snap(self.ALL_2530, conquered=(4,))
        self.assertEqual(policy._conquest_target(committed_snap), 3)

        # Losing conf/fire resistance drops the limit to 19: Orc Cave's
        # max_depth (22) now exceeds it -- a hard unviability, not a consumable
        # change -- and Labyrinth is already conquered, so nothing is left to
        # fall back to.
        regressed = self._snap(set(), conquered=(4,))
        self.assertIsNone(policy._conquest_target(regressed))
        self.assertIsNone(policy._conquest_committed)


class TownErrandPlanTest(unittest.TestCase):
    def _snapshot(self, *, turn=100, width=20, height=20):
        return Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            width=width,
            height=height,
            turn=turn,
        )

    def _policy(self, needs, town_map=None):
        policy = HengbotPolicy(town_map=town_map)
        policy._enumerate_town_needs = lambda snapshot: list(needs)
        policy._legacy_town_router_terminal = lambda snapshot: None
        return policy

    def test_multi_errand_circuit_is_home_first_and_nearest_neighbor(self):
        stores = {
            STORE_HOME: Position(10, 9),
            STORE_GENERAL: Position(10, 5),
            STORE_ALCHEMIST: Position(10, 12),
            STORE_TEMPLE: Position(10, 16),
            STORE_BLACK: Position(15, 16),
        }
        town_map = TownMap("Outpost", 20, 20, frozenset(), stores)
        needs = [
            TownNeed(STORE_HOME, "deposit", "home-first"),
            TownNeed(STORE_ALCHEMIST, "teleport", "normal"),
            TownNeed(STORE_TEMPLE, "cure", "normal"),
            TownNeed(STORE_GENERAL, "oil", "normal"),
            TownNeed(STORE_BLACK, "black", "normal"),
        ]
        policy = self._policy(needs, town_map)
        snapshot = self._snapshot()

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertEqual(
            policy._town_errand_plan.stops,
            [STORE_HOME, STORE_ALCHEMIST, STORE_TEMPLE, STORE_BLACK, STORE_GENERAL],
        )
        self.assertEqual(len(policy._town_errand_plan.stops), len(set(policy._town_errand_plan.stops)))

    def test_identification_source_precedes_single_withdrawal_home(self):
        needs = [
            TownNeed(STORE_ALCHEMIST, "identification-source", "before-withdrawal"),
            TownNeed(STORE_HOME, "identification-withdrawal", "post-alchemist-home"),
        ]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_ALCHEMIST)
        self.assertEqual(policy._town_errand_plan.stops, [STORE_ALCHEMIST, STORE_HOME])
        self.assertLessEqual(policy._town_errand_plan.stops.count(STORE_HOME), 2)

    def test_latched_stop_skips_and_expired_latch_can_replan(self):
        needs = [TownNeed(STORE_ALCHEMIST, "teleport", "normal")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._town_store_attempted[STORE_ALCHEMIST] = snapshot.turn
        self.assertIsNone(policy._next_required_store_type(snapshot))
        policy._town_store_attempted.pop(STORE_ALCHEMIST)
        self.assertEqual(policy._next_required_store_type(replace(snapshot, turn=200)), STORE_ALCHEMIST)

    def test_mid_visit_need_is_inserted_after_current_stop(self):
        active = [TownNeed(STORE_GENERAL, "oil", "normal")]
        policy = self._policy(active)
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)
        active.append(TownNeed(STORE_ALCHEMIST, "teleport", "normal"))
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)
        self.assertEqual(policy._town_errand_plan.stops, [STORE_GENERAL, STORE_ALCHEMIST])
        self.assertEqual(policy._town_errand_plan.inserted_this_visit, [STORE_ALCHEMIST])

    def test_enumeration_is_pure_and_terminal_ready_builds_no_plan(self):
        policy = HengbotPolicy()
        snapshot = self._snapshot()
        watched = (
            policy._fundraising_mode,
            policy._planned_mining_runs,
            dict(policy._town_store_attempted),
            policy._town_blocked_reason,
            policy._town_restock_wait_until,
        )
        first = policy._enumerate_town_needs(snapshot)
        second = policy._enumerate_town_needs(snapshot)
        self.assertEqual(first, second)
        self.assertEqual(
            watched,
            (
                policy._fundraising_mode,
                policy._planned_mining_runs,
                dict(policy._town_store_attempted),
                policy._town_blocked_reason,
                policy._town_restock_wait_until,
            ),
        )
        empty = self._policy([])
        self.assertIsNone(empty._next_required_store_type(snapshot))
        self.assertIsNone(empty._town_errand_plan)

    def test_cycle_break_and_restock_suppression_clear_plan(self):
        policy = self._policy([TownNeed(STORE_GENERAL, "oil", "normal")])
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)
        policy._break_town_cycle(snapshot)
        self.assertIsNone(policy._town_errand_plan)
        self.assertIsNone(policy._next_required_store_type(snapshot))

    def test_completed_stop_is_not_reacquired_from_live_needs(self):
        needs = [TownNeed(STORE_HOME, "equipment-catalog", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)

        policy._report_town_stop_pass(
            snapshot, STORE_HOME, goal_satisfied=True
        )

        self.assertIsNone(policy._next_required_store_type(snapshot))
        self.assertEqual(policy._town_errand_plan.completed_this_visit, [STORE_HOME])

    def test_unsatisfied_stop_blocks_after_three_completed_passes(self):
        needs = [
            TownNeed(STORE_HOME, "equipment-catalog", "home-first"),
            TownNeed(STORE_GENERAL, "food", "normal"),
        ]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)

        for _ in range(TOWN_STOP_PASS_LIMIT):
            policy._report_town_stop_pass(
                snapshot, STORE_HOME, goal_satisfied=False
            )

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)
        self.assertEqual(policy._town_errand_plan.blocked_this_visit, [STORE_HOME])

    def test_logged_single_page_home_episode_advances_within_two_decisions(self):
        needs = [
            TownNeed(STORE_HOME, "equipment-catalog", "home-first"),
            TownNeed(STORE_GENERAL, "food", "normal"),
        ]
        policy = self._policy(needs)
        town = self._snapshot(turn=131482)
        self.assertEqual(policy._next_required_store_type(town), STORE_HOME)
        page = [
            store_item(
                chr(ord("a") + index), TVAL_FOOD, index,
                name=f"stored item {index}", price=0,
            )
            for index in range(10)
        ]
        home = replace(
            town,
            store=StoreState(store_type=STORE_HOME, items=page),
            town_flag=False,
        )

        policy._equipment_catalog.observe_home_page(page, allow_wrap=False)
        self.assertEqual(policy._shop(home), " ")
        self.assertEqual(policy.last_reason, "home:seek-processing-page")
        processing_complete_key = policy._shop(home)
        self.assertTrue(processing_complete_key)
        self.assertEqual(processing_complete_key, LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:processing-complete")
        self.assertEqual(policy._next_required_store_type(town), STORE_GENERAL)

    def test_full_single_page_wrap_survives_interleaved_town_snapshot(self):
        needs = [TownNeed(STORE_HOME, "equipment-catalog", "home-first")]
        policy = self._policy(needs)
        town = self._snapshot(turn=512170)
        page = [
            store_item(
                chr(ord("a") + index), TVAL_FOOD, index,
                name=f"stored item {index}", price=0,
            )
            for index in range(12)
        ]
        home = replace(
            town,
            store=StoreState(store_type=STORE_HOME, items=page),
            town_flag=False,
        )

        policy._equipment_catalog.observe_home_page(page, allow_wrap=False)
        self.assertEqual(policy._shop(home), " ")
        self.assertFalse(policy._equipment_catalog.home_scan_complete)
        policy._home_page_advance_pending = True
        policy.choose_key(town)  # main-loop snapshot interleaved with store redraw
        self.assertTrue(policy._home_page_advance_pending)
        policy.choose_key(home)
        self.assertTrue(policy._equipment_catalog.home_scan_complete)

    def test_transaction_home_override_is_blocked_by_same_three_pass_owner(self):
        needs = [TownNeed(STORE_GENERAL, "food", "normal")]
        policy = self._policy(needs)
        snapshot = self._snapshot(turn=512170)
        policy._equipment_transaction_session = SimpleNamespace(
            executable=True,
            required_context="home",
            pending_action=None,
            current_action=None,
        )

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        for _ in range(TOWN_STOP_PASS_LIMIT):
            policy._report_town_stop_pass(
                snapshot, STORE_HOME, goal_satisfied=False
            )

        self.assertIsNone(policy._equipment_transaction_session)
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)
        self.assertIn(STORE_HOME, policy._town_store_attempted)

    def test_transaction_deposit_then_withdraw_keeps_home_owner_between_visits(self):
        policy = self._policy([])
        snapshot = self._snapshot(turn=512170)
        session = SimpleNamespace(
            executable=True,
            required_context="home",
            pending_action=None,
            current_action=None,
        )
        policy._equipment_transaction_session = session

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        session.required_context = "outside_home"  # deposit confirmed; equip next
        policy._report_town_stop_pass(snapshot, STORE_HOME, goal_satisfied=False)
        session.required_context = "home"  # later withdrawal in the same transaction

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertEqual(policy._town_errand_plan.current_stop_passes, 1)


class SupplyLedgerInvariantTest(unittest.TestCase):
    def _snapshot(self, depth, inventory=(), *, gold=500, store=None):
        return Snapshot(
            player(10, 10, gold=gold, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, depth, 0),
            inventory=list(inventory),
            equipment=[item("L", TVAL_LITE, SV_LITE_LANTERN, fuel=7000)],
            store=store,
        )

    def test_ledger_threshold_bands_and_store_map(self):
        policy = HengbotPolicy()
        shallow = policy._supply_ledger(self._snapshot(4), 4)
        deep = policy._supply_ledger(self._snapshot(11), 11)
        self.assertEqual(shallow["teleport"].required_return, 3)
        self.assertEqual(deep["teleport"].required_return, 4)
        self.assertEqual(deep["teleport"].required_departure, 15)
        self.assertEqual(deep["cure"].required_departure, 10)
        self.assertEqual(shallow["recall"].stores, (STORE_TEMPLE, STORE_ALCHEMIST))
        self.assertEqual(shallow["food"].stores, (STORE_GENERAL,))

    def test_incident_refill_is_charged_before_oil_departure_accounting(self):
        fixture = Path("tests/fixtures/oil_remove_curse_carousel_20260718.jsonl")
        incident = fixture.read_text(encoding="utf-8")
        self.assertIn('"reason": "shop:buy-oil"', incident)
        self.assertIn('"reason": "refill-light"', incident)
        self.assertIn('"reason": "town:wait-restock"', incident)

        policy = HengbotPolicy()
        policy._deepest_level = 1
        low_lantern = replace(
            self._snapshot(0, [
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=500),
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5),
                item("f", TVAL_FOOD, 35, count=5),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            ]),
            floor_key=(0, 0, 0), town_flag=True,
            equipment=[item("L", TVAL_LITE, SV_LITE_LANTERN, fuel=1000, known=True)],
        )
        status = policy._supply_ledger(low_lantern, policy._planned_depth())["oil"]
        self.assertEqual(status.count, 4)
        requirements = {
            entry["item"]: entry for entry in policy.procurement_requirements(low_lantern)
        }
        self.assertEqual(requirements["Flasks of oil"]["missing"], 1)
        self.assertIn(
            TownNeed(STORE_GENERAL, "oil", "normal"),
            policy._enumerate_town_needs(low_lantern),
        )

        policy._last_return_trigger = "recall-low"
        policy._break_town_cycle(low_lantern)
        self.assertFalse(policy._town_restock_suppressed)
        self.assertNotIn(STORE_GENERAL, policy._town_store_attempted)

    def test_every_departure_threshold_exceeds_return_threshold(self):
        for kind, phases in SUPPLY_THRESHOLDS.items():
            band_starts = sorted({
                depth for bands in phases.values() for depth, _value in bands
            })
            for depth in band_starts:
                with self.subTest(kind=kind, depth=depth):
                    required_return = HengbotPolicy._supply_threshold(
                        kind, "return", depth
                    )
                    required_departure = HengbotPolicy._supply_threshold(
                        kind, "departure", depth
                    )
                    self.assertGreater(required_departure, required_return)

    def test_corrected_recall_stock_does_not_latch_return_on_5f_arrival(self):
        policy = HengbotPolicy()
        policy._deepest_level = RECALL_MIN_DEPTH
        arrival = self._snapshot(RECALL_MIN_DEPTH, [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            item("f", TVAL_FOOD, 35, count=5),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=5),
        ])

        ledger = policy._supply_ledger(arrival, arrival.dungeon_level)
        self.assertEqual(ledger["recall"].required_departure, 5)
        self.assertFalse(policy._ledger_return_shortages(ledger, arrival.dungeon_level))
        self.assertFalse(policy._should_start_town_return(arrival))
        self.assertNotEqual(policy._last_return_trigger, "recall-low")

    def test_obtainable_uses_latch_live_stock_and_affordability(self):
        policy = HengbotPolicy()
        shelf = StoreState(
            store_type=STORE_ALCHEMIST,
            items=[store_item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, price=60)],
        )
        self.assertTrue(policy._supply_ledger(self._snapshot(4, store=shelf), 4)["teleport"].obtainable)
        self.assertFalse(policy._supply_ledger(self._snapshot(4, gold=10, store=shelf), 4)["teleport"].obtainable)
        empty = replace(self._snapshot(4, store=shelf), store=replace(shelf, items=[]))
        self.assertFalse(policy._supply_ledger(empty, 4)["teleport"].obtainable)
        policy._town_store_attempted[STORE_ALCHEMIST] = 0
        self.assertFalse(policy._supply_ledger(self._snapshot(4), 4)["teleport"].obtainable)

    def test_empty_current_supplier_keeps_unchecked_alternative_obtainable(self):
        policy = HengbotPolicy()
        alchemist = StoreState(store_type=STORE_ALCHEMIST, items=[])
        snapshot = self._snapshot(4, store=alchemist)

        self.assertTrue(policy._supply_ledger(snapshot, 4)["recall"].obtainable)
        needs = policy._enumerate_town_needs(replace(snapshot, town_flag=True))
        self.assertIn(TownNeed(STORE_TEMPLE, "recall", "normal"), needs)

    def test_teleport_uses_planned_depth_at_nine_ten_boundary(self):
        policy = HengbotPolicy()
        policy._deepest_level = STAFF_IDENTIFY_MIN_DEPTH - 1
        floor_nine = self._snapshot(STAFF_IDENTIFY_MIN_DEPTH - 1)

        status = policy._supply_ledger(floor_nine, floor_nine.dungeon_level)["teleport"]
        self.assertEqual(status.required_return, TELEPORT_RETURN_THRESHOLD + 1)
        self.assertEqual(status.required_departure, TELEPORT_SCROLL_DEEP_TARGET)

    def test_unobtainable_shallow_teleport_departs_without_return_bounce(self):
        supplies = [
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=2),
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=4),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=4),
            item("f", TVAL_FOOD, 35, count=5),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=5),
        ]
        policy = HengbotPolicy()
        policy._deepest_level = 3
        policy._town_store_attempted[STORE_ALCHEMIST] = 0
        dungeon = self._snapshot(4, supplies)
        ledger = policy._supply_ledger(dungeon, dungeon.dungeon_level)
        self.assertFalse(policy._ledger_return_shortages(ledger, dungeon.dungeon_level))
        self.assertFalse(policy._should_start_town_return(dungeon))
        town = replace(dungeon, floor_key=(0, 0, 0), town_flag=True)
        self.assertTrue(policy._ledger_departure_shortages(policy._supply_ledger(town, 4)) == [])

    def test_obtainable_teleport_is_purchased_before_departure(self):
        policy = HengbotPolicy()
        policy._deepest_level = 3
        policy._equipment_catalog.home_scan_complete = True
        town = replace(
            self._snapshot(0, [
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=4),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=3),
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=5),
            ]),
            town_flag=True,
        )
        ledger = policy._supply_ledger(town, 4)
        self.assertIn("teleport", [s.kind for s in policy._ledger_departure_shortages(ledger)])
        self.assertIn(
            TownNeed(STORE_ALCHEMIST, "teleport", "normal"),
            policy._enumerate_town_needs(town),
        )
        self.assertTrue(policy._descent_is_blocked(town))

    def test_deep_unobtainable_teleport_still_returns(self):
        policy = HengbotPolicy()
        policy._town_store_attempted[STORE_ALCHEMIST] = 0
        dungeon = self._snapshot(11, [item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3)])
        ledger = policy._supply_ledger(dungeon, dungeon.dungeon_level)
        self.assertTrue(policy._ledger_return_shortages(ledger, dungeon.dungeon_level))

    def test_next_depth_uses_return_threshold_not_departure_target(self):
        policy = HengbotPolicy()
        policy._deepest_level = 12
        policy._town_store_attempted[STORE_ALCHEMIST] = 0

        enough = self._snapshot(12, [
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=5),
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=2),
        ])
        low = replace(enough, inventory=[
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3),
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=2),
        ])

        self.assertFalse(policy._next_depth_supply_shortage(enough))
        self.assertTrue(policy._next_depth_supply_shortage(low))

    def test_mana_food_purchase_restores_device_redundancy(self):
        policy = HengbotPolicy()
        staff = store_item("s", TVAL_STAFF, 1, price=100, pval=20, count=10)
        town = replace(
            self._snapshot(0, gold=1000, store=StoreState(STORE_MAGIC, [staff])),
            player=replace(
                self._snapshot(0).player, gold=1000, food_type=FOOD_TYPE_MANA
            ),
            town_flag=True,
        )

        self.assertEqual(policy._purchase_quantity(town, staff), 2)

    def test_cycle_break_pins_every_obtainable_supply_supplier(self):
        policy = HengbotPolicy()
        policy._last_return_trigger = "teleport-low"
        town = replace(self._snapshot(0), town_flag=True)
        policy._break_town_cycle(town)
        self.assertIsNotNone(policy._town_errand_plan)
        self.assertIn(STORE_ALCHEMIST, policy._town_errand_plan.stops)
        self.assertIn(STORE_GENERAL, policy._town_errand_plan.stops)
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)


if __name__ == "__main__":
    unittest.main()
