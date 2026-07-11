import unittest

from hengbot.model import (
    STORE_GENERAL,
    SV_FLASK_OIL,
    SV_LITE_LANTERN,
    SV_LITE_TORCH,
    TVAL_FLASK,
    TVAL_LITE,
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
    REST_MACRO,
    DOOR_OPEN_LIMIT,
    RUBBLE_DIG_LIMIT,
    STORE_STUCK_LIMIT,
)


def store_item(letter, tval, sval, *, price=100, count=1, name="wares"):
    return StoreItem(letter=letter, name=name, count=count, tval=tval, sval=sval, price=price)


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
    )


def player(y, x, *, hp=20, max_hp=20, level=1, food=5000, food_type=0, gold=0, afraid=False, confused=False, blind=False, poisoned=False, cut=False):
    return PlayerState(
        Position(y, x),
        hp=hp,
        max_hp=max_hp,
        mp=0,
        max_mp=0,
        level=level,
        food=food,
        gold=gold,
        food_type=food_type,
        afraid=afraid,
        confused=confused,
        blind=blind,
        poisoned=poisoned,
        cut=cut,
    )


def item(slot, tval, sval, *, aware=True, count=1, name="item", charges=0):
    return InventoryItem(
        slot=slot, name=name, count=count, tval=tval, sval=sval, aware=aware, known=aware, charges=charges
    )


def hostile(index, y, x, *, hp=10, max_hp=10, distance=1, asleep=False, speed=110):
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

    def test_finishes_weak_lone_enemy_instead_of_fleeing(self):
        # Low HP, but the only threat is a lone adjacent enemy we can kill in a
        # hit or two (hp 36 <= 0.4 * 150). Fleeing a faster/ranged monster is
        # fatal, so stand and strike it (east, onto it) rather than run west.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 11): grid(10, 11, monster=True),
        }
        snap = Snapshot(player(10, 10, hp=20, max_hp=150), grids, [hostile(1, 10, 11, hp=36)])
        self.assertEqual(HengbotPolicy().choose_key(snap), "6")

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
        torch_eq = InventoryItem("f", "torch", 1, TVAL_LITE, SV_LITE_TORCH, True, True)
        lantern_inv = InventoryItem("e", "lantern", 1, TVAL_LITE, SV_LITE_LANTERN, True, True)
        snap = Snapshot(player(10, 10), grids, [], inventory=[lantern_inv], equipment=[torch_eq])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "we")
        self.assertEqual(pol.last_reason, "wield-light")


class RubbleTest(unittest.TestCase):
    def test_tunnels_through_rubble_frontier(self):
        # A pile of rubble to the east caps the passage; it is the only frontier,
        # so the bot digs into it with 'T'+direction rather than treating it as a
        # wall (which would strand it).
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
        torch = item("e", 39, 0, name="torch", count=5)
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


class DescendTest(unittest.TestCase):
    def test_moves_toward_downstairs(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, downstairs=True),
        }
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), "6")

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


if __name__ == "__main__":
    unittest.main()
