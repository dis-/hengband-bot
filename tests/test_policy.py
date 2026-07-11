import unittest

from hengbot.model import (
    DUNGEON_ANGBAND,
    DUNGEON_YEEK_CAVE,
    PLAYER_CLASS_WARRIOR,
    STORE_ALCHEMIST,
    STORE_ARMOURY,
    STORE_BLACK,
    STORE_GENERAL,
    STORE_HOME,
    STORE_TEMPLE,
    SV_DIGGING_SHOVEL,
    SV_FLASK_OIL,
    SV_LITE_LANTERN,
    SV_LITE_TORCH,
    SV_SCROLL_WORD_OF_RECALL,
    SV_SCROLL_DETECT_TREASURE,
    SV_SCROLL_IDENTIFY,
    SV_SCROLL_STAR_IDENTIFY,
    SV_SCROLL_TELEPORT,
    SV_STAFF_IDENTIFY,
    TVAL_DIGGING,
    TVAL_FLASK,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_RING,
    TVAL_SCROLL,
    TVAL_STAFF,
    GridState,
    InventoryItem,
    MonsterState,
    PlayerState,
    Position,
    Snapshot,
    StoreItem,
    StoreState,
)
from hengbot.policy import (
    HengbotPolicy,
    LIVELOCK_LIMIT,
    PACK_CAPACITY,
    REST_MACRO,
    STUCK_WINDOW,
    DOOR_OPEN_LIMIT,
    RUBBLE_DIG_LIMIT,
    STORE_STUCK_LIMIT,
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
    entrance_dungeon_id=-1,
    building_type=-1,
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
        can_dig=known and rubble,
        has_gold=known and gold,
        entrance_dungeon_id=entrance_dungeon_id,
        building_type=building_type,
    )


def player(y, x, *, hp=20, max_hp=20, mp=0, max_mp=0, level=1, food=12000, food_type=0, gold=0, word_recall=0, afraid=False, confused=False, blind=False, poisoned=False, cut=False, class_id=-1):
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
    is_broken=False,
    to_h=0,
    to_d=0,
    to_a=0,
    ac=0,
    pval=0,
    known_flags=frozenset(),
):
    if known is None:
        known = aware
    return InventoryItem(
        slot=slot, name=name, count=count, tval=tval, sval=sval, aware=aware,
        known=known, fully_known=fully_known, charges=charges, fuel=fuel,
        is_equipment=is_equipment, is_ego=is_ego, is_artifact=is_artifact,
        is_cursed=is_cursed, is_broken=is_broken, to_h=to_h, to_d=to_d,
        to_a=to_a, ac=ac, pval=pval, known_flags=known_flags
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
    )


class CombatTest(unittest.TestCase):
    def test_attacks_adjacent_hostile(self):
        grids = {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11, monster=True)}
        snap = Snapshot(player(10, 10), grids, [hostile(1, 10, 11, hp=3)])
        self.assertEqual(HengbotPolicy().choose_key(snap), "6")

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
        snap = Snapshot(player(10, 10, hp=100, max_hp=100), grids, [summoner])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "4")
        self.assertEqual(pol.last_reason, "summoner:retreat")

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
        monsters = [
            hostile(1, 9, 10, hp=20),
            hostile(2, 10, 11, hp=20),
            hostile(3, 11, 10, hp=20),
        ]
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(Snapshot(player(10, 10, hp=175, max_hp=175), grids, monsters)), "<")
        self.assertEqual(pol.last_reason, "flee:stairs")

    def test_ignores_friendly_and_pet(self):
        friendly = MonsterState(1, Position(10, 11), hp=10, max_hp=10, distance=1, friendly=True, pet=False)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, downstairs=True),
        }
        # Should walk past the friendly toward the stairs, not attack it.
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [friendly])), "6")


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
        pol.choose_key(Snapshot(player(10, 10, hp=120, max_hp=200), grids, [], turn=1))
        key = pol.choose_key(Snapshot(player(10, 10, hp=95, max_hp=200), grids, [], turn=2))
        self.assertNotEqual(key, REST_MACRO)
        self.assertTrue(pol.last_reason.startswith("unseen"), pol.last_reason)

    def test_flees_to_upstairs_when_bleeding_unseen(self):
        grids = {Position(10, x): grid(10, x) for x in range(10, 14)}
        grids[Position(10, 14)] = grid(10, 14, upstairs=True)
        pol = HengbotPolicy()
        pol.choose_key(Snapshot(player(10, 10, hp=120, max_hp=200), grids, [], turn=1))
        key = pol.choose_key(Snapshot(player(10, 10, hp=95, max_hp=200), grids, [], turn=2))
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
        self.assertEqual(pol.choose_key(self._in_store(items)), "pb\r\ry")
        self.assertEqual(pol.last_reason, "shop:buy-lantern")

    def test_buys_oil_once_lantern_owned(self):
        items = [store_item("c", TVAL_FLASK, SV_FLASK_OIL, price=3)]
        inv = [InventoryItem("e", "lantern", 1, TVAL_LITE, SV_LITE_LANTERN, True, True)]
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(self._in_store(items, inv=inv)), "pc\r\ry")
        self.assertEqual(pol.last_reason, "shop:buy-oil")

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
        self.assertIn("pb\r\ry", keys)  # it did try to buy
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

    def test_breaks_out_of_short_store_approach_cycle(self):
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

        self.assertEqual(key, "8")
        self.assertEqual(pol.last_reason, "shop:approach")

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
        # so the bot digs into it with keymap-bypassed 'T'+direction rather than
        # treating it as a wall (which would strand it).
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, rubble=True),
        }
        snap = Snapshot(player(10, 10), grids, [], width=40, height=40)
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "\\T6")

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
        self.assertIn("\\T6", keys)
        self.assertIn((10, 11), pol._blocked_rubble)


class SearchTest(unittest.TestCase):
    def test_searches_a_sealed_dead_end(self):
        # Walled in on every side with no reachable frontier: the way on must be a
        # secret door, so once it recognises it is stuck the bot searches ('s').
        grids = {Position(10, 10): grid(10, 10)}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if (dy, dx) != (0, 0):
                    grids[Position(10 + dy, 10 + dx)] = grid(10 + dy, 10 + dx, passable=False)
        snap = Snapshot(player(10, 10), grids, [], width=40, height=40)
        pol = HengbotPolicy()
        results = [(pol.choose_key(snap), pol.last_reason) for _ in range(14)]
        self.assertIn(("s", "search"), results)


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
        snap = Snapshot(player(24, 37, hp=99, max_hp=99), grids, [monster], width=80, height=200)
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

    def test_breaks_out_of_an_unreachable_stair_approach_cycle(self):
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
        self.assertEqual(policy.choose_key(snapshot), "4")
        self.assertEqual(policy.last_reason, "breakout:descent")

    def test_descends_when_standing_on_downstairs_and_healthy(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        snap = Snapshot(player(10, 10, hp=20, max_hp=20), grids, [])
        self.assertEqual(HengbotPolicy().choose_key(snap), ">")

    def test_rests_before_descending_when_hurt_then_descends(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        policy = HengbotPolicy()
        hurt = Snapshot(player(10, 10, hp=10, max_hp=100), grids, [], turn=1)
        self.assertEqual(policy.choose_key(hurt), REST_MACRO)  # heal up first
        healed = Snapshot(player(10, 10, hp=90, max_hp=100), grids, [], turn=2)
        self.assertEqual(policy.choose_key(healed), ">")

    def test_confirms_entry_on_a_dungeon_entrance(self):
        # A town/wilderness dungeon entrance first msg_print()s an entrance line
        # (a -more- prompt) then a [y/n] confirmation, so descent is the macro
        # ">\ry" (Return dismisses the -more-, y confirms), not a bare ">".
        grids = {Position(10, 10): grid(10, 10, entrance=True)}
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), ">\ry")

    def test_bare_downstairs_needs_no_confirmation(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), ">")

    def test_seeks_a_dungeon_entrance(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, entrance=True),
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
            hostile(1, 6, 16),
            hostile(2, 7, 17),
            hostile(3, 8, 16),
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
            [hostile(1, 6, 16), hostile(2, 7, 17), hostile(3, 8, 16)],
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
        snap = Snapshot(player(10, 10), walls, [], width=20, height=20)
        policy = HengbotPolicy()
        keys = [policy.choose_key(snap) for _ in range(DOOR_OPEN_LIMIT + 20)]
        self.assertEqual(keys[0], "o6")  # tries to open at first
        self.assertIn("s", keys)  # boxed in with a jammed door → searches for a secret way
        self.assertIn((10, 11), policy._blocked_doors)  # eventually abandons the door

    def test_never_moves_diagonally_into_a_closed_door(self):
        # A closed door sits NW of the player (diagonal); the game rejects a
        # diagonal open, so the bot must approach it orthogonally via the west
        # floor tile, i.e. step west (4), never 7.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),  # west floor
            Position(9, 9): grid(9, 9, closed_door=True),  # door NW, N of the west tile
        }
        for pos in [Position(9, 10), Position(9, 11), Position(10, 11), Position(11, 9), Position(11, 10), Position(11, 11)]:
            grids[pos] = grid(pos.y, pos.x, passable=False)
        key = HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, []))
        self.assertEqual(key, "4")

    def test_never_moves_diagonally_into_an_open_door(self):
        # An OPEN door sits NE of the player. Hengband rejects diagonal movement
        # onto/through a doorway just like a closed one, so the bot must approach
        # orthogonally (step north), never 9. This was the dl7 oscillation cause.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(9, 10): grid(9, 10),  # north floor
            Position(9, 11): grid(9, 11, open_door=True),  # open door NE
        }
        for pos in [Position(9, 9), Position(10, 9), Position(10, 11), Position(11, 9), Position(11, 10), Position(11, 11)]:
            grids[pos] = grid(pos.y, pos.x, passable=False)
        key = HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, []))
        self.assertEqual(key, "8")

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
        policy = HengbotPolicy()
        key = policy.choose_key(Snapshot(player(0, 0), grids, [], width=10, height=10))
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
        inv = [item("c", POTION, 34)]  # Potion of Cure Light Wounds
        threat = hostile(1, 10, 13, hp=30, max_hp=30, distance=3)  # a monster is near
        snap = Snapshot(player(10, 10, hp=20, max_hp=100), grids, [threat], inventory=inv)
        self.assertEqual(HengbotPolicy().choose_key(snap), "qc")

    def test_rests_instead_of_quaffing_when_safe(self):
        # Hurt but no enemy in sight: rest heals for free, so don't burn a potion.
        grids = self._open_room()
        inv = [item("c", POTION, 34)]
        snap = Snapshot(player(10, 10, hp=20, max_hp=100), grids, [], inventory=inv)
        self.assertEqual(HengbotPolicy().choose_key(snap), REST_MACRO)

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
            player(10, 10, food=2500),
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

    def test_normal_food_band_without_supplies_starts_return(self):
        snap = Snapshot(
            player(10, 10, food=6000),
            self._stairs(),
            [],
            floor_key=self.FLOOR,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "4")
        self.assertEqual(policy.last_reason, "return:seek-upstairs")

    def test_full_food_band_without_supplies_can_continue(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        snap = Snapshot(
            player(10, 10, food=12000),
            grids,
            [],
            floor_key=self.FLOOR,
        )

        self.assertEqual(HengbotPolicy().choose_key(snap), ">")

    def test_full_pack_of_junk_drops_overflow_to_reenter_the_dungeon(self):
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
        self.assertEqual(pol.choose_key(snap), "\\da\r")
        self.assertEqual(pol.last_reason, "town:drop-overflow")


class OverflowDropTest(unittest.TestCase):
    def _town(self, inventory):
        return Snapshot(
            player(10, 10, food=6000),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(0, 0, 0),
            inventory=inventory,
        )

    def test_drops_a_device_but_never_the_recall_scroll(self):
        # Essentials (here the Word of Recall at slot 'a') are never the overflow
        # victim — the first non-essential device is dropped instead.
        recall = item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        staves = [
            item(chr(ord("b") + i), TVAL_STAFF, 3, name="staff")
            for i in range(PACK_CAPACITY - 1)
        ]
        pol = HengbotPolicy()
        key = pol.choose_key(self._town([recall] + staves))
        self.assertEqual(pol.last_reason, "town:drop-overflow")
        self.assertEqual(key, "\\db\r")

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
        self.assertNotEqual(pol.last_reason, "town:drop-overflow")
        self.assertNotIn("\\d", key)


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
        snap = Snapshot(player(10, 10, hp=40, max_hp=100, poisoned=True), self._open_room(), [])
        self.assertNotEqual(HengbotPolicy().choose_key(snap), REST_MACRO)

    def test_does_not_rest_when_healthy(self):
        snap = Snapshot(player(10, 10, hp=95, max_hp=100), self._open_room(), [])
        self.assertNotEqual(HengbotPolicy().choose_key(snap), REST_MACRO)


class PickupTest(unittest.TestCase):
    def test_picks_up_loot_on_current_tile(self):
        grids = {
            Position(10, 10): grid(10, 10, objects=1),
            Position(10, 11): grid(10, 11, downstairs=True),
        }
        # Even with stairs adjacent, grab the loot underfoot first.
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), "g")

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

    def test_does_not_seek_unsafe_loot(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, objects=1, unsafe=True),
        }
        snap = Snapshot(player(10, 10), grids, [])
        policy = HengbotPolicy()

        policy.choose_key(snap)

        self.assertNotEqual(policy.last_reason, "seek-loot")


class ProbeTest(unittest.TestCase):
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
        self.assertEqual(policy.last_reason, "breakout:least-visited")


class TownRestockTest(unittest.TestCase):
    def _in_general_store(self, items, *, gold=500, inv=None):
        grids = {Position(10, 10): grid(10, 10)}
        return Snapshot(
            player(10, 10, gold=gold),
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
        self.assertEqual(pol.choose_key(self._in_general_store(wares, inv=inv)), "pb\r\ry")
        self.assertEqual(pol.last_reason, "shop:buy-food")

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

    def test_mana_race_does_not_restock_rations(self):
        # MANA races sate hunger from device charges, not rations, so the food
        # restock must stay off for them (buying rations would just burn gold).
        snap = Snapshot(
            player(10, 10, food=400, food_type=4),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
        )
        self.assertFalse(HengbotPolicy()._needs_food_restock(snap))


class SummonerMeleeTest(unittest.TestCase):
    def test_fights_an_adjacent_summoner_instead_of_retreating(self):
        # Open terrain would normally trigger the retreat, but walking away from
        # an ALREADY-ADJACENT summoner just donates free hits — kill it.
        grids = {}
        for y in range(9, 12):
            for x in range(9, 12):
                grids[Position(y, x)] = grid(y, x)
        grids[Position(10, 11)] = grid(10, 11, monster=True)
        summoner = hostile(1, 10, 11, hp=40, max_hp=40, can_summon=True)
        snap = Snapshot(player(10, 10, hp=100, max_hp=100), grids, [summoner])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "6")
        self.assertEqual(pol.last_reason, "melee")


class TownAndFundraisingPolicyTest(unittest.TestCase):
    def _strict_supplies(self, *, recall=1, detection=0, teleport=0):
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
        return supplies

    def _lantern(self):
        return item(
            "light",
            TVAL_LITE,
            SV_LITE_LANTERN,
            fuel=5000,
            is_equipment=True,
        )

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
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
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
        self.assertEqual(policy.choose_key(snap), "pa\r\ry")
        self.assertEqual(policy.last_reason, "shop:buy-recall")

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

    def test_mining_reads_one_detection_scroll_then_tunnels_visible_gold(self):
        grids = {
            Position(10, 10): grid(10, 10, upstairs=True),
            Position(10, 11): grid(10, 11, passable=False, rubble=True, gold=True),
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
        self.assertEqual(policy.choose_key(snap), "rd")
        self.assertEqual(policy.last_reason, "fundraise:detect-treasure")
        self.assertEqual(policy.choose_key(snap), "\\T6")
        self.assertEqual(policy.last_reason, "fundraise:mine-treasure")

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
        self.assertEqual(policy.last_reason, "fundraise:eat")

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
        self.assertEqual(policy.choose_key(snap), "ws")
        self.assertEqual(policy.last_reason, "town:restore-combat-weapon")

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
        )
        policy = HengbotPolicy()
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

    def test_conquest_runs_normal_town_routine_then_listens_for_rumor(self):
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
        self.assertEqual(policy.choose_key(snap), "6u\r\r\x1b")
        self.assertEqual(policy.last_reason, "town:rumor")

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
            player(10, 10, gold=20, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            inventory=supplies,
            equipment=[self._lantern()],
            yeek_cave_conquered=True,
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "town:rumor")

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
        self.assertEqual(policy.choose_key(snap), "rr")
        self.assertEqual(policy.last_reason, "town:recall-to-angband")

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
        self.assertEqual(policy.last_reason, "home:withdraw-for-processing")

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
        self.assertEqual(policy.choose_key(snap), "uua")
        self.assertEqual(policy.last_reason, "identify:normal")

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
        self.assertEqual(policy.choose_key(snap), "pb\r\ry")
        self.assertEqual(policy.last_reason, "shop:buy-star-identify")

    def test_equips_only_a_complete_dominating_armour_upgrade(self):
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
        self.assertEqual(policy.choose_key(snap), "wa")
        self.assertEqual(policy.last_reason, "equipment:equip-dominating-upgrade")

    def test_does_not_equip_armour_that_trades_resistance_for_ac(self):
        current = item(
            "body",
            36,
            1,
            fully_known=True,
            is_equipment=True,
            ac=5,
            known_flags=frozenset({10}),
        )
        candidate = item(
            "a",
            37,
            1,
            fully_known=True,
            is_equipment=True,
            ac=20,
            known_flags=frozenset(),
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[candidate],
            equipment=[current, self._lantern()],
        )
        self.assertIsNone(HengbotPolicy()._safe_equipment_upgrade_key(snap, candidate))

    def test_does_not_auto_equip_weapon_without_attack_rate_evaluation(self):
        current = item(
            "main_hand", 23, 1, fully_known=True, is_equipment=True, to_d=1
        )
        candidate = item(
            "a", 23, 2, fully_known=True, is_equipment=True, to_d=20
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[candidate],
            equipment=[current, self._lantern()],
        )
        self.assertIsNone(HengbotPolicy()._safe_equipment_upgrade_key(snap, candidate))

    def test_only_mundane_fully_dominated_armour_is_disposable(self):
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
        self.assertTrue(policy._is_disposable_dominated_armour(snap, inferior))
        self.assertFalse(policy._is_disposable_dominated_armour(snap, protected))

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
        self.assertEqual(policy.choose_key(snap), "da\r\ry")
        self.assertEqual(policy.last_reason, "equipment:sell-dominated")

    def test_destroys_dominated_armour_only_after_both_stores_refuse(self):
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
        policy._disposal_store_attempts.update({STORE_ARMOURY, STORE_BLACK})
        self.assertEqual(policy.choose_key(snap), "ka\r\ry")
        self.assertEqual(
            policy.last_reason, "equipment:destroy-unsellable-dominated"
        )


if __name__ == "__main__":
    unittest.main()
