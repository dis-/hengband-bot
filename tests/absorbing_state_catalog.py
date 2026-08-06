"""Seed catalogue for the six absorbing-state incident families.

Modelled physics: numeric movement changes position; stepping onto, or WAITing
on, a store/building entrance opens it; Escape leaves it; Home SPACE changes
page (with an incident-selectable swallowed-redraw fault); ``p<letter>`` removes
stock, debits gold, and adds the item to the pack.  Numeric rests advance their
requested game turns, and ``C`` queues the emitter's character payload for the
next decision. Recall/dungeon-entry macros change floor. Menu internals, combat
damage, monsters, and the contents chosen by store restocking are not modelled.
"""

from __future__ import annotations

from dataclasses import replace

import hengbot.policy as policy_module
from hengbot.model import Position, Snapshot, StoreState
from hengbot.model import STORE_HOME, TVAL_POTION
from hengbot.policy import HengbotPolicy, LEAVE_STORE_KEY, WAIT_KEY
from hengbot.policy import CHARACTER_DUMP_MACRO

from absorbing_state_harness import AbsorbingState
import test_policy as fixture


HOME_PAGE_SINGLE_PAGE_MESSAGES = ("これで全部です。", "Entire inventory is shown.")


MOVES = {
    "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
    "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
}


class TownWorld:
    def __init__(self, snapshot: Snapshot, *, entrance=STORE_HOME, stock=(),
                 page_size=12, swallow_space=False, version_reply=False,
                 blocked_movement=False, purchases_succeed=True):
        self.base = snapshot
        self.position = snapshot.player.position
        self.visited_positions = {self.position}
        disclosed = next(
            ((position, state.store_number) for position, state in snapshot.grids.items()
             if state.store_number >= 0),
            (self.position, entrance),
        )
        self.entrance, self.entrance_type = disclosed
        self.inside = snapshot.store is not None
        self.stock = list(stock)
        self.inventory = list(snapshot.inventory)
        self.gold = snapshot.player.gold
        self.page_size = page_size
        self.top = 0
        self.swallow_space = swallow_space
        self.version_reply = version_reply
        self.blocked_movement = blocked_movement
        self.purchases_succeed = purchases_succeed
        self.entries = int(self.inside)
        self.exits = 0
        self.depth = snapshot.dungeon_level
        self.blocked_streak = 0
        self.last_key = ""
        self.turn = snapshot.turn
        self.pending_events = []
        self.character_events_delivered = 0

    def snapshot(self, decision: int) -> Snapshot:
        grids = dict(self.base.grids)
        entrance_grid = grids.get(self.entrance, fixture.grid(self.entrance.y, self.entrance.x))
        grids[self.entrance] = replace(entrance_grid, store_number=self.entrance_type)
        visible = self.stock[self.top:self.top + self.page_size]
        visible = [replace(ware, letter=chr(ord("a") + n)) for n, ware in enumerate(visible)]
        if self.version_reply and self.last_key == "V":
            messages = ("Hengband 3.0",)
        elif self.inside and self.last_key == " " and len(self.stock) <= self.page_size:
            messages = (HOME_PAGE_SINGLE_PAGE_MESSAGES[0],)
        else:
            messages = ()
        return replace(
            self.base,
            turn=self.turn,
            player=replace(self.base.player, position=self.position, gold=self.gold),
            grids=grids,
            inventory=list(self.inventory),
            store=StoreState(self.entrance_type, visible) if self.inside else None,
            messages=messages,
            floor_key=(self.base.floor_key[0], self.depth, self.base.floor_key[2]),
        )

    def apply(self, key: str) -> None:
        self.last_key = key
        if key == CHARACTER_DUMP_MACRO:
            self.pending_events.append({"mutations": [], "characteristics": []})
            return
        if key.startswith("R") and key.endswith("\r") and key[1:-1].isdigit():
            self.turn += int(key[1:-1])
            return
        if self.inside:
            if key == LEAVE_STORE_KEY:
                self.inside = False
                self.top = 0
                self.exits += 1
                return
            if key == " ":
                if not self.swallow_space:
                    self.top += self.page_size
                    if self.top >= len(self.stock):
                        self.top = 0
                return
            purchase = key.find("p")
            if purchase >= 0 and purchase + 1 < len(key):
                page = key[:purchase].count(" ")
                letter = key[purchase + 1]
                index = page * self.page_size + ord(letter) - ord("a")
                if self.purchases_succeed and 0 <= index < len(self.stock):
                    ware = self.stock.pop(index)
                    self.gold -= getattr(ware, "price", 0)
                    self.inventory.append(fixture.item(
                        chr(ord("a") + len(self.inventory) % 26), ware.tval, ware.sval,
                        count=ware.count, name=ware.name,
                    ))
                if key.endswith(LEAVE_STORE_KEY):
                    self.inside = False
                    self.exits += 1
                return
            return
        # A composed atomic visit starts with WAIT, performs its store command,
        # and may finish with Escape before another JSON snapshot exists.
        if key.startswith(WAIT_KEY) and "p" in key:
            self.entries += 1
            self.inside = True
            self.apply(key[1:])
            return
        if key == WAIT_KEY and self.position == self.entrance:
            self.inside = True
            self.entries += 1
            self.top = 0
            return
        first = key[:1]
        if first in MOVES:
            if self.blocked_movement:
                return
            dy, dx = MOVES[first]
            self.position = Position(self.position.y + dy, self.position.x + dx)
            self.visited_positions.add(self.position)
            if self.position == self.entrance:
                self.inside = True
                self.entries += 1
                self.top = 0
            self.turn += 1
            return
        if key.startswith("rr") or key.startswith(">"):
            self.depth = max(1, self.depth + 1)
            self.turn += 1

    def deliver_events(self, policy):
        for character in self.pending_events:
            policy.observe_character_snapshot(character)
            self.character_events_delivered += 1
        self.pending_events.clear()

    def release_modelled(self, reason):
        if reason == "calibration:await-capture":
            return True
        if reason.startswith("town:wait-restock:"):
            return True
        # The catalogue's other waits release through snapshot fields modelled
        # above (position/store/messages/inventory/floor), not side-channel events.
        return not (reason.startswith("calibration:") and "await" in reason)

    def durable_fingerprint(self):
        # Position and turn are intentionally excluded: a two-cell shuffle and
        # mere passage of turns do not advance a town workflow.
        return (
            self.depth, self.gold,
            # A real walk expands its footprint. A stationary wait or two-cell
            # shuffle does not; positions enter only after a third distinct cell.
            len(self.visited_positions) if len(self.visited_positions) >= 3 else 0,
            tuple(sorted((i.tval, i.sval, i.count, i.name) for i in self.inventory)),
            tuple(sorted((i.tval, i.sval, i.count, i.name) for i in self.stock)),
        )

    def visible_terminal(self, reason: str):
        if self.character_events_delivered and reason != "calibration:await-capture":
            return "character payload delivered"
        if reason == "livelock:exhausted":
            return reason
        if reason.startswith("town:blocked:"):
            self.blocked_streak += 1
            if self.blocked_streak >= 30:
                return "town:blocked:* fuse"
        else:
            self.blocked_streak = 0
        return None


def _arrived_depth(_policy, world):
    return "non-town floor" if world.depth > 0 else None


def _arrived_outside(_policy, world):
    return "fresh outside-Home restart" if world.exits else None


def _departure_freeze():
    helper = fixture.NoSafeRecallDestinationTest()
    policy, snap = helper._fixture()
    policy._town_errand_plan = None
    policy._town_blocked_reason = "repetition"
    policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
    policy._home_entry_operation_posted = True
    entrance = replace(snap.grids[snap.player.position], store_number=STORE_HOME)
    safe = fixture.grid(45, 122, lit=True, in_view=True)
    snap = replace(snap, grids={entrance.position: entrance, safe.position: safe})
    return policy, TownWorld(snap)


def _version_discard(*, swallow=False):
    helper = fixture.HomeOneOperationPerEntryTest()
    stock = [fixture.store_item(chr(ord("a") + n % 12), TVAL_POTION, 2000 + n,
                        name=f"catalogue {n}") for n in range(60)]
    policy = HengbotPolicy()
    policy._home_pending_item = policy._item_signature(stock[50])
    pack = helper._real_pack()
    def page(items, turn, messages=()):
        return replace(helper._home_page_snapshot(pack, items, turn=turn), messages=messages)
    # Reconstruct page 0 -> page 1 -> repeated page 1 through choose_key.  The
    # repeated observation is the game-side evidence that the posted SPACE was
    # swallowed; it causes the version probe measured in the incident.
    policy.choose_key(page(stock[:12], 3000001))
    if swallow:
        policy.choose_key(page(stock[:12], 3000002))
        policy.choose_key(page(stock[:12], 3000003, ("Hengband 3.0",)))
        current = stock[:12]
    else:
        policy.choose_key(page(stock[12:24], 3000002))
        policy.choose_key(page(stock[12:24], 3000003))
        current = stock[12:24]
    world = TownWorld(page(current, 3000004), stock=stock,
                      swallow_space=swallow, version_reply=True)
    world.top = 0 if swallow else 12
    world.last_key = "V"
    return policy, world


def _page_recurrence():
    return _version_discard(swallow=False)


def _page_zero_echo():
    return _version_discard(swallow=True)


def _home_entry_cycle():
    helper = fixture.NoSafeRecallDestinationTest()
    policy, snap = helper._fixture()
    policy._town_errand_plan = None
    for store_type in range(8):
        policy._town_visit_ledger.approach_fails[store_type] = policy_module.TOWN_STOP_PASS_LIMIT
    policy._town_blocked_reason = "no-safe-recall-destination"
    policy._calibration_blocked_this_visit = True
    policy._equipment_catalog.home_scan_complete = True
    policy._home_entry_operation_posted = True
    snap = replace(
        snap,
        inventory=[],
        equipment=[],
    )
    entrance = replace(snap.grids[snap.player.position], store_number=STORE_HOME)
    safe = fixture.grid(45, 122, lit=True, in_view=True)
    return policy, TownWorld(replace(snap, grids={entrance.position: entrance, safe.position: safe}))


def _atomic_restore():
    helper = fixture.HomeOneOperationPerEntryTest()
    targets = [fixture.store_item("a", TVAL_POTION, 3000 + n, name=f"restore {n}") for n in range(12)]
    filler = [fixture.store_item("a", TVAL_POTION, 3100 + n, name=f"home {n}") for n in range(20)]
    stock = [*filler[:7], *targets, *filler[7:]]
    policy = HengbotPolicy()
    policy._calibration_phase = "restore-supplies"
    policy._calibration_restore_signatures = [policy._item_signature(x) for x in targets]
    policy._home_candidate_waiting = True
    pack = helper._real_pack()
    entrance = replace(helper._entrance_snapshot(pack, turn=3100000),
                       equipment=[fixture.item("light", policy_module.TVAL_LITE, 0, name="a light")])
    world = TownWorld(entrance, stock=stock, version_reply=True)
    world.target_names = {x.name for x in targets}
    return policy, world


def _withdraw_refusal_cycle():
    helper = fixture.HomeOneOperationPerEntryTest()
    missing = fixture.store_item("a", TVAL_POTION, 3990, name="missing restore")
    other = fixture.store_item("a", TVAL_POTION, 3991, name="other home item")
    policy = HengbotPolicy()
    policy._calibration_phase = "restore-supplies"
    policy._calibration_restore_signatures = [policy._item_signature(missing)]
    policy._home_candidate_waiting = True
    pack = helper._real_pack()
    page = replace(
        helper._home_page_snapshot(pack, [other], turn=3050000),
        messages=(HOME_PAGE_SINGLE_PAGE_MESSAGES[0],),
    )
    policy.choose_key(page)
    entrance = replace(helper._entrance_snapshot(pack, turn=3050001),
                       equipment=[fixture.item("light", policy_module.TVAL_LITE, 0, name="a light")])
    return policy, TownWorld(entrance, stock=[other])


def _restored(_policy, world):
    names = {x.name for x in world.inventory}
    return "all twelve carried restores" if world.target_names <= names else None


def _released_bound():
    helper = fixture.HomeOneOperationPerEntryTest()
    policy = HengbotPolicy()
    pack = helper._real_pack()
    entrance = helper._entrance_snapshot(pack, turn=3200000)
    surface = replace(
        entrance,
        player=replace(entrance.player, position=Position(45, 122)),
        equipment=[fixture.item("light", policy_module.TVAL_LITE, 0, name="a light")],
    )
    for n in range(4):
        # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: incident seed reconstructs a bounded pre-history before the physics drive starts
        policy.choose_key(replace(surface, turn=3200000 + n))
    target = fixture.store_item("a", TVAL_POTION, 3900, name="bound restore")
    signature = policy._item_signature(target)
    policy._calibration_phase = "restore-supplies"
    policy._calibration_restore_signatures = [signature]
    policy._home_candidate_waiting = True
    # TEST_FAKERY_LINT_ALLOW: private-state-injected: catalogue seed reconstructs the measured persisted address state, while drive outcomes remain public
    policy._home_address_pages = [(target,)]
    policy._home_address_ordinals = [0]
    policy._home_address_page_count = 1
    policy._home_address_scan_valid = True
    policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
    policy._town_visit_ledger.approach_fails[STORE_HOME] = policy_module.TOWN_STOP_PASS_LIMIT
    policy._town_visit_ledger.need_attempts["calibration-restore"] = policy_module.TOWN_STOP_PASS_LIMIT
    policy._town_store_attempted[STORE_HOME] = 3200003
    return policy, TownWorld(surface, blocked_movement=True)


SEEDED_STATES = (
    AbsorbingState("home-blocked-departure", 200, _departure_freeze, _arrived_depth),
    AbsorbingState("home-withdraw-enter-escape", 300, _withdraw_refusal_cycle, lambda _p, _w: None),
    AbsorbingState("home-page-recurrence", 400, _page_recurrence, _arrived_outside),
    AbsorbingState("home-page-zero-echo", 400, _page_zero_echo, _arrived_outside),
    AbsorbingState("wait-reenters-home-door", 200, _home_entry_cycle, lambda _p, _w: None),
    AbsorbingState("released-home-attempt-bound", 600, _released_bound, lambda _p, _w: None),
)
