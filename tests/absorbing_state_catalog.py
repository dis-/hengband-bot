"""Seed catalogue for the six absorbing-state incident families.

Modelled physics: numeric movement changes position; stepping onto, or WAITing
on, a store/building entrance opens it; Escape leaves it; Home SPACE changes
page (with an incident-selectable swallowed-redraw fault); ``p<letter>`` removes
stock, debits gold, and adds the item to the pack. Energy actions advance ten
emitted game turns per player turn; numeric rests advance ten times their
requested player turns. ``C`` queues the emitter's character payload for the
next decision. Recall/dungeon-entry macros change floor. Menu internals, combat
damage, monsters, and the contents chosen by store restocking are not modelled.
The indefinite ``R&`` rest macro is an explicitly unmodelled release: this
world has no recovery/status physics with which to decide when it completes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import SimpleNamespace

import hengbot.policy as policy_module
from hengbot.model import Position, Snapshot, StoreState
from hengbot.model import (
    STORE_ALCHEMIST, STORE_GENERAL, STORE_HOME, TVAL_DIGGING, TVAL_POTION,
)
from hengbot.policy import HengbotPolicy, LEAVE_STORE_KEY, WAIT_KEY
from hengbot.policy import (
    CHARACTER_DUMP_MACRO, HOME_PAGE_SINGLE_PAGE_MESSAGES,
)
from hengbot.cli import TOWN_BLOCKED_STOP_LIMIT, _stall_recovery_action
from hengbot.home_visit import (
    HomeVisitExecutor, HomeVisitKind, HomeVisitRequest,
)

from absorbing_state_harness import AbsorbingState
import test_policy as fixture


MOVES = {
    "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
    "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
}

EMITTED_TURNS_PER_PLAYER_TURN = 10
class TownWorld:
    def __init__(self, snapshot: Snapshot, *, entrance=STORE_HOME, stock=(),
                 page_size=12, swallow_space=False, version_reply=False,
                 passable_positions=None, purchases_succeed=True,
                 single_page_message=HOME_PAGE_SINGLE_PAGE_MESSAGES[0]):
        self.base = snapshot
        self.position = snapshot.player.position
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
        self.passable_positions = passable_positions or {
            Position(y, x)
            for y in range(self.position.y - 20, self.position.y + 21)
            for x in range(self.position.x - 20, self.position.x + 21)
        }
        self.purchases_succeed = purchases_succeed
        self.single_page_message = single_page_message
        self.entries = int(self.inside)
        self.exits = 0
        self.depth = snapshot.dungeon_level
        self.equipment = list(snapshot.equipment)
        self.blocked_streak = 0
        self.last_key = ""
        self.turn = snapshot.turn
        self.pending_events = []
        self.pending_home_knowledge = False
        self.pending_home_scan_snapshots = []
        self.character_events_delivered = 0
        self._town_blocked_durable_state = self.durable_fingerprint()
        self._town_blocked_depth = self.depth

    def snapshot(self, decision: int) -> Snapshot:
        grids = dict(self.base.grids)
        entrance_grid = grids.get(self.entrance, fixture.grid(self.entrance.y, self.entrance.x))
        grids[self.entrance] = replace(entrance_grid, store_number=self.entrance_type)
        visible = self.stock[self.top:self.top + self.page_size]
        store_letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        visible = [replace(ware, letter=store_letters[n]) for n, ware in enumerate(visible)]
        if self.version_reply and self.last_key == "V":
            messages = ("Hengband 3.0",)
        elif self.inside and self.last_key == " " and len(self.stock) <= self.page_size:
            messages = (self.single_page_message,)
        else:
            messages = ()
        return replace(
            self.base,
            turn=self.turn,
            player=replace(self.base.player, position=self.position, gold=self.gold),
            grids=grids,
            inventory=list(self.inventory),
            store=(
                StoreState(
                    self.entrance_type, visible, stock_num=len(self.stock),
                    page_top=self.top, page_size=self.page_size,
                )
                if self.inside else None
            ),
            messages=messages,
            floor_key=(self.base.floor_key[0], self.depth, self.base.floor_key[2]),
        )

    def apply(self, key: str) -> None:
        self.last_key = key
        if key == CHARACTER_DUMP_MACRO:
            self.pending_events.append({"mutations": [], "characteristics": []})
            return
        if key.startswith("R") and key.endswith("\r") and key[1:-1].isdigit():
            self.turn += EMITTED_TURNS_PER_PLAYER_TURN * int(key[1:-1])
            return
        if key == "~9":
            self.pending_home_knowledge = True
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
            deposit = key.find("d")
            if deposit >= 0 and deposit + 1 < len(key):
                letter = key[deposit + 1]
                index = ord(letter) - ord("a")
                if 0 <= index < len(self.inventory):
                    self.inventory.pop(index)
                if key.endswith(LEAVE_STORE_KEY):
                    self.inside = False
                    self.exits += 1
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
        if key.startswith(WAIT_KEY) and ("p" in key or "d" in key):
            self.entries += 1
            self.inside = True
            self.turn += EMITTED_TURNS_PER_PLAYER_TURN
            self.apply(key[1:])
            return
        if key == WAIT_KEY:
            self.turn += EMITTED_TURNS_PER_PLAYER_TURN
            if self.position == self.entrance:
                self.inside = True
                self.entries += 1
                self.top = 0
            return
        first = key[:1]
        if first in MOVES:
            dy, dx = MOVES[first]
            destination = Position(self.position.y + dy, self.position.x + dx)
            self.turn += EMITTED_TURNS_PER_PLAYER_TURN
            if destination not in self.passable_positions:
                return
            self.position = destination
            if self.position == self.entrance:
                self.inside = True
                self.entries += 1
                self.top = 0
            return
        if key.startswith("rr") or key.startswith(">"):
            self.depth = max(1, self.depth + 1)
            self.turn += EMITTED_TURNS_PER_PLAYER_TURN

    def deliver_events(self, policy):
        if self.pending_home_knowledge:
            policy.consume_home_knowledge(tuple(self.stock))
            self.pending_home_knowledge = False
        for character in self.pending_events:
            policy.observe_character_snapshot(character)
            self.character_events_delivered += 1
        self.pending_events.clear()

    def unmodelled_release(self, reason):
        # Evidence belongs to the world model, not to a reason allow-list. All
        # ordinary waits, movement, menus, and numeric rests above have a
        # modelled stimulus. R& is reachable from town:recover, but recovery
        # physics is absent, so only that observed key/reason pair qualifies.
        # This deliberately classifies the final decision only: a frozen drive
        # ending in one such pair can share this label, but remains a FAIL.
        return self.last_key == "R&\r" and reason == "town:recover"

    def durable_fingerprint(self):
        # Position and turn are intentionally excluded: a two-cell shuffle and
        # mere passage of turns do not advance a town workflow.
        def items(values):
            return tuple(
                (
                    getattr(i, "slot", None), i.tval, i.sval, i.name,
                    i.count, i.charges, i.inscription, i.known,
                    i.fully_known, i.is_equipment,
                )
                for i in values
            )

        return (
            (
                self.entrance_type,
                len(self.stock),
                self.top,
                items(self.stock[self.top:self.top + self.page_size]),
            )
            if self.inside else None,
            items(self.inventory),
            items(self.equipment),
            self.gold,
        )

    def visible_terminal(self, reason: str):
        from hengbot import cli
        if reason in getattr(cli, "POLICY_FINAL_STOP_REASONS", ()):
            return f"policy final stop: {reason}"
        if getattr(self, "invalid_store_entries", 0):
            return None
        if self.depth != self._town_blocked_depth:
            self.blocked_streak = 0
            self._town_blocked_depth = self.depth
        if self.depth != 0:
            self.blocked_streak = 0
            return None
        durable_state = self.durable_fingerprint()
        if durable_state != self._town_blocked_durable_state:
            self.blocked_streak = 0
            self._town_blocked_durable_state = durable_state
        if reason == getattr(self, "expected_terminal_reason", None):
            return f"expected {reason}"
        if reason == "home:atomic-withdraw":
            return "surplus staff composed withdrawal"
        if reason == "livelock:exhausted":
            return reason
        if reason.startswith("town:blocked:"):
            self.blocked_streak += 1
            if self.blocked_streak >= TOWN_BLOCKED_STOP_LIMIT:
                return "town:blocked:* fuse"
        elif self.blocked_streak and reason != "shop:leave":
            self.blocked_streak += 1
            if self.blocked_streak >= TOWN_BLOCKED_STOP_LIMIT:
                return "town:blocked:* fuse"

    def terminal_ends_drive(self, reason: str, key: str) -> bool:
        """Model only terminals whose owner actually ends the CLI drive."""
        from hengbot import cli
        if reason in getattr(cli, "POLICY_FINAL_STOP_REASONS", ()):
            return True
        if reason == "livelock:exhausted":
            return True
        if self.blocked_streak >= TOWN_BLOCKED_STOP_LIMIT:
            return True
        if reason == "equipment-transaction:restore-blocked-terminal":
            return reason in getattr(cli, "POLICY_FINAL_STOP_REASONS", ())
        if reason == getattr(self, "expected_terminal_reason", None):
            return True
        if reason == "home:atomic-withdraw":
            return True
        return self.visible_terminal(reason) in {
            "calibration prerequisite Home scan complete",
            "equipment transaction owns ten-item restoration",
            "transaction preserved through Home withdrawal handoff",
            "surplus staff composed withdrawal",
        }


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


def _home_suppression_one_shot(*, purchases_succeed=True):
    """Selected Home gear must withdraw before recovery exits can repeat."""
    fillers = [
        fixture.store_item("a", TVAL_POTION, index, name=f"filler-{index}")
        for index in range(12)
    ]
    sword = fixture.store_item(
        "a", 23, 25, name="selected sword", known=True,
        fully_known=False, is_equipment=True, is_ego=True,
    )
    policy = HengbotPolicy()
    policy.consume_home_knowledge(tuple([*fillers, sword]))
    policy._home_page_size = 12
    def preparation(_snapshot):
        matching = [
            candidate for candidate in policy._equipment_catalog.items
            if policy_module.equipment_identity(candidate.item)
            == policy_module.equipment_identity(sword)
        ]
        loadout = fixture.Loadout(
            (("main_hand", matching[0]),) if matching else (),
            "one_handed" if matching else "empty",
        )
        evaluated = fixture.EvaluatedLoadout(
            loadout, fixture.LoadoutMetrics(0.0, 0.0, 0.0)
        )
        result = fixture.OptimizationResult(
            evaluated, (), (), frozenset(), 1, 1, 0, 0.0,
            False, frozenset(),
        )
        return policy_module.WarriorOptimizationPreparation(
            loadout,
            result,
            None,
            ("pending-random-teleport-suppression",) if matching else (),
        )

    policy._prepare_equipment_optimization = preparation
    surface = Snapshot(
        fixture.player(10, 10, class_id=fixture.PLAYER_CLASS_WARRIOR),
        {
            Position(10, 10): replace(
                fixture.grid(10, 10), store_number=STORE_HOME
            ),
            Position(10, 9): fixture.grid(10, 9),
        },
        [],
        floor_key=(0, 0, 0),
        town_flag=True,
        equipment=[
            fixture.item(
                "light", fixture.TVAL_LITE, fixture.SV_LITE_LANTERN,
                fuel=7000, known=True, is_equipment=True,
            )
        ],
    )
    policy._shopping_approach_store_type = STORE_HOME

    class SuppressionWorld(TownWorld):
        def apply(self, key):
            inventory_size = len(self.inventory)
            super().apply(key)
            if len(self.inventory) > inventory_size:
                carried = self.inventory[-1]
                if carried.name == sword.name:
                    self.inventory[-1] = fixture.item(
                        carried.slot, sword.tval, sword.sval,
                        count=sword.count, name=sword.name,
                        known=sword.known, fully_known=sword.fully_known,
                        is_equipment=sword.is_equipment, is_ego=sword.is_ego,
                        is_artifact=sword.is_artifact,
                        known_flags=sword.known_flags,
                    )

        def visible_terminal(self, reason):
            if (
                not purchases_succeed
                and reason == self.expected_terminal_reason
            ):
                return super().visible_terminal(reason)
            if (
                reason == "home:route-claim-unfulfilled"
                or reason.startswith("calibration:")
                or reason.startswith("equipment-transaction:")
            ):
                return "historical Home recovery exit repeated"
            if reason == "home:atomic-withdraw":
                return None
            return super().visible_terminal(reason)

        def terminal_ends_drive(self, reason, key):
            if not purchases_succeed and reason == self.expected_terminal_reason:
                return super().terminal_ends_drive(reason, key)
            if (
                reason == "home:route-claim-unfulfilled"
                or reason.startswith("calibration:")
                or reason.startswith("equipment-transaction:")
            ):
                return False
            if reason == "home:atomic-withdraw":
                return False
            return super().terminal_ends_drive(reason, key)

    world = SuppressionWorld(
        surface, stock=[*fillers, sword], purchases_succeed=purchases_succeed
    )
    world.expected_terminal_reason = (
        "equipment:suppress-random-teleport"
        if purchases_succeed
        else "calibration:strip-installed"
    )
    return policy, world


def _home_suppression_refusal():
    """A refused Home take must defer once and release to another decision."""
    return _home_suppression_one_shot(purchases_succeed=False)


def _catalogue_invalidated_with_equipment_work():
    """A cleared catalogue must release through ~9 despite equipment work."""
    surface = fixture.TownErrandPlanTest()._snapshot(turn=3542954)
    entrance = Position(10, 11)
    surface = replace(
        surface,
        player=replace(surface.player, position=Position(10, 10)),
        grids={
            **surface.grids,
            entrance: replace(
                fixture.grid(10, 11, lit=True, in_view=True),
                store_number=STORE_HOME,
            ),
        },
        store=None,
    )

    policy = HengbotPolicy()
    policy._equipment_catalog.invalidate_home()
    policy._equipment_optimization_preparation = SimpleNamespace(
        blockers=("home-scan-incomplete",), result=None,
    )
    policy._shopping_approach_store_type = STORE_HOME
    world = TownWorld(surface)
    world.expected_terminal_reason = "home:request-knowledge-scan"
    return policy, world


def _invalid_command_noop_home_cycle():
    """An observation-only disposal pass cannot own a Home entry."""
    helper = fixture.TownErrandPlanTest()
    surface = helper._snapshot(turn=2994536)
    entrance = Position(10, 11)
    surface = replace(
        surface,
        player=replace(surface.player, position=entrance, class_id=1),
        floor_key=(0, 0, 0),
        grids={
            **surface.grids,
            entrance: replace(
                fixture.grid(entrance.y, entrance.x), store_number=STORE_HOME
            ),
        },
        equipment=[
            fixture.item(
                "light", policy_module.TVAL_LITE,
                policy_module.SV_LITE_TORCH, fuel=5000,
            )
        ],
    )
    policy = HengbotPolicy()
    policy._home_disposal_pass = True

    return policy, TownWorld(surface, passable_positions={entrance})


def _doubled_store_entry_cycle():
    """Delay the Home-open page once after accepting its entry command."""
    helper = fixture.HomeOneOperationPerEntryTest()
    target = fixture.store_item("a", TVAL_POTION, 2999, name="delayed target")
    policy = HengbotPolicy()
    policy._calibration_phase = "restore-supplies"
    policy._calibration_restore_signatures = [policy._item_signature(target)]
    policy._home_candidate_waiting = True
    surface = replace(
        helper._entrance_snapshot(helper._real_pack(), turn=3041933),
        equipment=[
            fixture.item("light", policy_module.TVAL_LITE, 0, name="a light")
        ],
    )

    delayed_page = [False]

    class DelayedEntryWorld(TownWorld):
        def __init__(self, snapshot):
            super().__init__(snapshot, stock=[target])
            self.invalid_store_entries = 0
            self.expected_terminal_reason = "home:request-knowledge-scan"

        def snapshot(self, decision):
            current = super().snapshot(decision)
            if delayed_page[0]:
                delayed_page[0] = False
                return replace(current, store=None)
            return current

        def apply(self, key):
            was_inside = self.inside
            if was_inside and key == WAIT_KEY:
                self.invalid_store_entries += 1
                self.last_key = key
                return
            super().apply(key)
            if not was_inside and key == WAIT_KEY and self.inside:
                delayed_page[0] = True

    return policy, DelayedEntryWorld(surface)


def _lagged_successful_store_entry():
    """Expose a direction posted into a store whose first page is lagged."""
    helper = fixture.HomeOneOperationPerEntryTest()
    target = fixture.store_item("a", TVAL_POTION, 3001, name="lagged target")
    policy = HengbotPolicy()
    policy._calibration_phase = "restore-supplies"
    policy._calibration_restore_signatures = [policy._item_signature(target)]
    policy._home_candidate_waiting = True
    surface = replace(
        helper._entrance_snapshot(helper._real_pack(), turn=3041933),
        equipment=[
            fixture.item("light", policy_module.TVAL_LITE, 0, name="a light")
        ],
        messages=(),
    )

    lag_store_page = [False]

    class LaggedSuccessfulEntryWorld(TownWorld):
        def __init__(self, snapshot):
            super().__init__(snapshot, stock=[target])
            self.invalid_store_entries = 0
            self.expected_terminal_reason = "home:request-knowledge-scan"

        def snapshot(self, decision):
            current = super().snapshot(decision)
            if lag_store_page[0]:
                lag_store_page[0] = False
                return replace(current, store=None, messages=())
            return current

        def apply(self, key):
            was_inside = self.inside
            if was_inside and key[:1] in MOVES:
                self.invalid_store_entries += 1
                self.last_key = key
                return
            super().apply(key)
            if not was_inside and key == WAIT_KEY and self.inside:
                lag_store_page[0] = True

    return policy, LaggedSuccessfulEntryWorld(surface)


def _failed_store_entry_same_turn():
    """A refused entrance WAIT must hand routing back without a filler key."""
    helper = fixture.HomeOneOperationPerEntryTest()
    target = fixture.store_item("a", TVAL_POTION, 3000, name="refused target")
    policy = HengbotPolicy()
    policy._calibration_phase = "restore-supplies"
    policy._calibration_restore_signatures = [policy._item_signature(target)]
    policy._home_candidate_waiting = True
    surface = replace(
        helper._entrance_snapshot(helper._real_pack(), turn=3467379),
        equipment=[
            fixture.item("light", policy_module.TVAL_LITE, 0, name="a light")
        ],
    )

    class RefusedEntryWorld(TownWorld):
        def __init__(self, snapshot):
            super().__init__(snapshot, stock=[target])
            self.expected_terminal_reason = "store:entry-failed-step-off"

        def apply(self, key):
            if not self.inside and key == WAIT_KEY:
                self.last_key = key
                return
            super().apply(key)

        def snapshot(self, decision):
            current = super().snapshot(decision)
            if not self.inside and self.last_key == WAIT_KEY:
                return replace(
                    current,
                    messages=("The doors are locked.",),
                )
            return current

    return policy, RefusedEntryWorld(surface)


def _scan_address_burst_visit_seed():
    """Replay archived decisions 4050-4052 from the 2026-08-08 burst."""
    return _evidence_visit_cycle((
        EvidenceFrame(3693201, 45, 123, None, "home:scan-address-burst", "5                     \x1b"),
        EvidenceFrame(3693210, 45, 123, STORE_HOME, "home:leave-after-one-operation", "\x1b"),
    ))


def _abandon_blocked_home_visit_seed():
    """Replay archived decisions 40-42 from the 2026-08-09 abandonment."""
    return _evidence_visit_cycle((
        EvidenceFrame(3698697, 45, 124, None, "equipment-transaction:approach-home", "4"),
        EvidenceFrame(3698697, 45, 123, None, "store:entry-await-observation", ""),
        EvidenceFrame(3698697, 45, 123, STORE_HOME, "equipment-transaction:abandon-blocked-home", "\x1b"),
    ))


def _approach_entrance_stepoff_visit_seed():
    """Replay the 2026-08-07 02:57:15 entrance-step-off onset."""
    return _evidence_visit_cycle((
        EvidenceFrame(2940187, 44, 124, None, "shop:approach", "1"),
        EvidenceFrame(2940187, 45, 123, None, "town:entrance-step-off:shop:travel:await-entry", "6"),
        EvidenceFrame(2940187, 45, 123, STORE_HOME, "home:scan-catalog-page", " "),
    ))


def _live_shop_entry_exit_visit_seed():
    """Replay archived decisions 26-28 from the 531-occurrence incident."""
    return _evidence_visit_cycle((
        EvidenceFrame(3754150, 44, 124, None, "shop:approach", "1"),
        EvidenceFrame(3754150, 45, 123, None, "store:entry-await-observation", ""),
        EvidenceFrame(3754150, 45, 123, STORE_HOME, "home:store-context-exit", "\x1b"),
    ))


@dataclass(frozen=True)
class EvidenceFrame:
    """Decision fields copied verbatim from the preserved JSONL evidence."""

    turn: int
    y: int
    x: int
    store_type: int | None
    reason: str
    key: str


def _evidence_visit_cycle(frames):
    """Cycle a preserved live burst without inventing game-side progress."""
    helper = fixture.HomeOneOperationPerEntryTest()
    base = helper._entrance_snapshot(helper._real_pack(), turn=frames[0].turn)
    policy = HengbotPolicy()
    policy._shopping_approach_store_type = STORE_HOME

    class EvidenceWorld(TownWorld):
        def __init__(self):
            super().__init__(base)
            self.index = 0

        @property
        def frame(self):
            return frames[self.index % len(frames)]

        def snapshot(self, decision):
            frame = self.frame
            store = (
                StoreState(frame.store_type, [], stock_num=0, page_top=0, page_size=12)
                if frame.store_type is not None else None
            )
            return replace(
                base, turn=frame.turn,
                player=replace(base.player, position=Position(frame.y, frame.x)),
                store=store,
            )

        def apply(self, key):
            before = self.frame.store_type
            self.index += 1
            after = self.frame.store_type
            self.entries += int(before is None and after is not None)
            self.exits += int(before is not None and after is None)
            self.last_key = key

    world = EvidenceWorld()

    def archived_decision(_snapshot):
        policy._decision_sequence += 1
        policy.last_reason = world.frame.reason
        return world.frame.key

    policy._choose_key_with_latch_capture = archived_decision
    return policy, world


def _transaction_abandoned_mid_strip():
    """A stripped optimizer transaction restores or stops at its named terminal."""
    policy, surface, _ = (
        fixture.EquipmentTransactionOwnershipRegressionTest()._stripped_fixture()
    )

    class MidStripWorld(TownWorld):
        def visible_terminal(self, reason):
            if (
                policy._equipment_transaction_restoring
                and reason == "equipment-transaction:abandon-blocked"
            ):
                # The durable restore plan itself is progress out of the
                # historical abandoned/ordinary-town absorbing state.
                return "equipment transaction owns ten-item restoration"
            if reason == "equipment-transaction:restore-blocked-terminal":
                return reason
            return super().visible_terminal(reason)

    return policy, MidStripWorld(surface)


def _abandon_retry_home_pass_burn():
    """Inside Home must release the historical abandon/retry/pass-burn cycle."""
    policy, surface, _ = (
        fixture.EquipmentTransactionOwnershipRegressionTest()._stripped_fixture()
    )
    target = fixture.store_item(
        "a", fixture.TVAL_RING, 99, name="Home target", known=True,
        fully_known=True, is_equipment=True,
    )
    identity = policy_module.equipment_identity(target)
    action = policy_module.EquipmentTransaction(
        policy_module.PHASE_HOME_PREPARE,
        "withdraw",
        "home-target",
        item_identity=identity,
    )
    policy._equipment_transaction_session = policy_module.EquipmentTransactionSession(
        policy_module.EquipmentTransactionPlan((action,), (), len(surface.inventory))
    )
    policy._equipment_transaction_restoring = False
    surface = replace(surface, store=StoreState(STORE_HOME, [target]))

    class AbandonRetryWorld(TownWorld):
        def visible_terminal(self, reason):
            if reason == "equipment-transaction:leave-for-atomic-withdraw":
                return "transaction preserved through Home withdrawal handoff"
            return super().visible_terminal(reason)

    return policy, AbandonRetryWorld(surface, stock=[target])


def _movement_opens_store_before_surface_observation():
    """A disclosed movement destination opens a shop before its first page."""
    helper = fixture.HomeOneOperationPerEntryTest()
    origin = Position(45, 122)
    entrance = Position(45, 123)
    surface = helper._entrance_snapshot(helper._real_pack(), turn=3500000)
    surface = replace(
        surface,
        player=replace(surface.player, position=origin),
        grids={
            origin: fixture.grid(origin.y, origin.x),
            entrance: replace(
                fixture.grid(entrance.y, entrance.x),
                store_number=STORE_ALCHEMIST,
            ),
        },
        store=None,
    )
    policy = HengbotPolicy()

    def decide(snapshot):
        if snapshot.store is not None:
            policy.last_reason = "shop:leave"
            return LEAVE_STORE_KEY
        policy.last_reason = "town:kill-mob-approach"
        target = entrance if snapshot.player.position == origin else origin
        return policy._step_toward(snapshot, target)

    policy._decide = decide
    lag = [False]

    class AccidentalEntryWorld(TownWorld):
        def __init__(self, snapshot):
            super().__init__(snapshot, entrance=STORE_ALCHEMIST)
            self.invalid_store_entries = 0
            self.expected_terminal_reason = "shop:leave"

        def terminal_ends_drive(self, reason, key):
            return reason == self.expected_terminal_reason and key == LEAVE_STORE_KEY

        def snapshot(self, decision):
            current = super().snapshot(decision)
            if lag[0]:
                lag[0] = False
                return replace(current, store=None, messages=())
            return current

        def apply(self, key):
            was_inside = self.inside
            super().apply(key)
            if was_inside and key[:1] in MOVES:
                self.invalid_store_entries += 1
            if not was_inside and self.inside and key[:1] in MOVES:
                lag[0] = True

    return policy, AccidentalEntryWorld(surface)


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


def _withdraw_refusal_cycle():
    """Reproduce the version-probe freeze, not the 150-entry refusal cycle.

    The measured refusal incident had valid incomplete 3-of-5 page provenance;
    this seed reconstructs only the independently observed version-probe freeze.
    """
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
    # Once the entry-owned WAIT is delivered, model the real store's version
    # response so this seed continues to test the bounded refusal cycle rather
    # than freezing on an omitted protocol response.
    return policy, TownWorld(entrance, stock=[other], version_reply=True)


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
    policy.consume_home_knowledge((target,))
    policy._home_page_size = 52
    policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
    policy._town_visit_ledger.approach_fails[STORE_HOME] = policy_module.TOWN_STOP_PASS_LIMIT
    policy._town_visit_ledger.need_attempts["calibration-restore"] = policy_module.TOWN_STOP_PASS_LIMIT
    policy._town_store_attempted[STORE_HOME] = 3200003
    return policy, TownWorld(
        surface,
        passable_positions={surface.player.position, entrance.player.position},
    )


def _calibration_deposit_claim_budget():
    """Unsafe recall must not install its terminal over a live Home deposit."""
    helper = fixture.NoSafeRecallDestinationTest()
    policy, snap = helper._fixture()
    home = replace(
        fixture.grid(45, 122, lit=True, in_view=True), store_number=STORE_HOME
    )
    snap = replace(
        snap,
        grids={**snap.grids, home.position: home},
        inventory=[replace(snap.inventory[0], count=19), *snap.inventory[1:]],
    )
    policy._town_was_in_town = True
    policy._calibration_phase = "deposit"
    policy._town_visit_ledger.need_attempts["deposit"] = 3
    policy._town_errand_plan = policy_module.TownErrandPlan(
        [STORE_HOME, policy_module.STORE_TEMPLE, policy_module.STORE_WEAPON,
         policy_module.STORE_BLACK],
        index=4,
    )
    policy._town_store_attempted[STORE_HOME] = snap.turn

    class CalibrationDepositWorld(TownWorld):
        def __init__(self, snapshot):
            super().__init__(snapshot)
            self.initial_inventory_size = len(self.inventory)

        def visible_terminal(self, reason):
            if reason == "town:blocked:no-safe-recall-destination":
                return None
            if (
                reason in {"town:blocked:repetition", "livelock:exhausted"}
                and len(self.inventory) == self.initial_inventory_size
            ):
                return None
            return super().visible_terminal(reason)

    return policy, CalibrationDepositWorld(snap)


def _plan_none_live_calibration_home_available():
    """A live calibration owner with no plan must still reach bounded Home."""
    helper = fixture.NoSafeRecallDestinationTest()
    policy, snap = helper._fixture()
    home = replace(
        fixture.grid(45, 122, lit=True, in_view=True), store_number=STORE_HOME
    )
    snap = replace(snap, grids={**snap.grids, home.position: home})
    policy._town_was_in_town = True
    policy._calibration_phase = "deposit"
    policy._equipment_catalog.home_scan_complete = True
    policy._equipment_optimization_preparation = SimpleNamespace(
        blockers=("calibration-required",), result=None,
    )
    policy._town_errand_plan = None
    policy._town_blocked_reason = "repetition"
    policy._town_visit_ledger.unsatisfied_passes[STORE_HOME] = 16
    return policy, TownWorld(snap)


def _calibration_prerequisite_scan_bound():
    """Mixed pre-phase Home work must survive the legacy third-pass boundary."""
    helper = fixture.NoSafeRecallDestinationTest()
    policy, snap = helper._fixture()
    home = replace(
        fixture.grid(45, 122, lit=True, in_view=True), store_number=STORE_HOME
    )
    snap = replace(snap, turn=2947508, grids={**snap.grids, home.position: home})
    policy._equipment_catalog.home_scan_complete = False
    policy._equipment_optimization_preparation = SimpleNamespace(
        blockers=("home-scan-incomplete",), result=None,
    )
    policy._town_was_in_town = True
    policy._enumerate_town_needs = lambda _snapshot: [
        policy_module.TownNeed(STORE_HOME, "equipment-catalog", "home-first"),
        policy_module.TownNeed(
            STORE_HOME,
            "identification-withdrawal",
            "surplus-identify-staff",
        ),
    ]
    policy._town_errand_plan = policy_module.TownErrandPlan(
        [STORE_HOME],
        need_categories={
            STORE_HOME: ("equipment-catalog", "identification-withdrawal")
        },
    )
    policy._town_visit_ledger.unsatisfied_passes[STORE_HOME] = 2
    policy._recent.extend([snap.player.position] * policy_module.STUCK_WINDOW)
    policy._shop_approach_stuck_count = policy_module.SHOP_APPROACH_STUCK_LIMIT - 1
    policy._shopping_approach_step(snap, STORE_HOME)
    policy._report_town_stop_pass(
        snap, STORE_HOME, goal_satisfied=False, operation_completed=False
    )
    class PrerequisiteScanWorld(TownWorld):
        def __init__(self, snapshot):
            super().__init__(snapshot)
            self.started_blocked = (
                STORE_HOME in policy._town_visit_ledger.blocked_stores
                or STORE_HOME in policy._town_store_attempted
            )

        def visible_terminal(self, reason):
            if self.started_blocked:
                return None
            if policy._equipment_catalog.home_scan_complete:
                terminal = super().visible_terminal("livelock:exhausted")
                if terminal is not None:
                    return "calibration prerequisite Home scan complete"
            return super().visible_terminal(reason)

    return policy, PrerequisiteScanWorld(snap)


def _successful_optimizer_transaction():
    """Optimizer success must retain the Home route needed to apply its plan."""
    helper = fixture.NoSafeRecallDestinationTest()
    policy, snap = helper._fixture()
    home = replace(
        fixture.grid(45, 122, lit=True, in_view=True), store_number=STORE_HOME
    )
    snap = replace(snap, grids={**snap.grids, home.position: home})
    target = snap.inventory[0]
    identity = policy_module.equipment_identity(target)
    action = policy_module.EquipmentTransaction(
        policy_module.PHASE_HOME_PREPARE,
        "deposit",
        f"pack:{identity}:0",
        item_identity=identity,
    )
    session = policy_module.EquipmentTransactionSession(
        policy_module.EquipmentTransactionPlan((action,), (), 23)
    )
    policy._equipment_optimization_preparation = SimpleNamespace(
        blockers=(), result=object(),
    )
    policy._set_equipment_transaction_session(session)
    policy._town_visit_ledger.approach_fails[STORE_HOME] = (
        policy_module.TOWN_STOP_PASS_LIMIT
    )

    class SuccessfulTransactionWorld(TownWorld):
        def __init__(self, snapshot):
            super().__init__(snapshot)
            self.initial_inventory_size = len(self.inventory)

        def visible_terminal(self, reason):
            if len(self.inventory) < self.initial_inventory_size:
                return TownWorld.visible_terminal(self, "home:atomic-withdraw")
            return TownWorld.visible_terminal(self, reason)

        def durable_fingerprint(self):
            # The catalogue verdict is deliberately tied to the policy-visible
            # completed operation, not merely to our simulated pack mutation.
            return self.depth, self.gold, tuple(self.stock)

    return policy, SuccessfulTransactionWorld(snap)


def _exhausted_equipment_home_route():
    """Outstanding work with no remaining Home route must stop visibly."""
    helper = fixture.NoSafeRecallDestinationTest()
    policy, snap = helper._fixture()
    policy.choose_key(snap)
    policy._town_errand_plan = None
    policy._equipment_optimization_preparation = SimpleNamespace(
        blockers=("optimization-timeout",), result=None,
    )
    for store_type in (
        policy_module.STORE_GENERAL,
        policy_module.STORE_ARMOURY,
        policy_module.STORE_WEAPON,
        policy_module.STORE_TEMPLE,
        policy_module.STORE_ALCHEMIST,
        policy_module.STORE_MAGIC,
        policy_module.STORE_BLACK,
    ):
        policy._town_visit_ledger.nonhome_attempted_without_effect[store_type] = (
            policy._town_observable_effect_state(snap)
        )
    policy._town_visit_ledger.approach_fails[STORE_HOME] = (
        policy._town_store_visit_limit(STORE_HOME)
    )
    return policy, TownWorld(snap)


def _block_authority_mismatch_home_route():
    """An ordinary Home block cannot absorb later equipment-owned work."""
    policy, world = _successful_optimizer_transaction()
    policy._town_visit_ledger.unsatisfied_passes[STORE_HOME] = 3
    policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
    policy._town_visit_ledger.blocked_store_limits[STORE_HOME] = (
        policy_module.TOWN_STOP_PASS_LIMIT
    )
    return policy, world


def _approach_refused_optimizer_transaction():
    """A detector refusal must not consume an open transaction's Home route."""
    policy, world = _successful_optimizer_transaction()
    policy._town_was_in_town = True
    policy._floor_key = world.base.floor_key
    policy._recent.extend([world.base.player.position] * policy_module.STUCK_WINDOW)
    policy._shop_approach_stuck_count = (
        policy_module.SHOP_APPROACH_STUCK_LIMIT - 1
    )
    return policy, world


def _frozen_approach_optimizer_transaction():
    """A swallowed owned-route step must exhaust the existing Home ceiling."""
    policy, world = _approach_refused_optimizer_transaction()

    class FrozenApproachWorld(type(world)):
        def apply(self, key):
            if key and all(ch in "12346789" for ch in key):
                return
            super().apply(key)

    world.__class__ = FrozenApproachWorld
    return policy, world


def _ordinary_alchemist_entry_seed(*, turn, target_sval):
    """Build an entrance-owned Alchemist trip without invoking Home scanning."""
    helper = fixture.HomeOneOperationPerEntryTest()
    target = fixture.store_item(
        "a", TVAL_POTION, target_sval, name="ordinary-shop target"
    )
    policy = HengbotPolicy()
    policy._next_required_store_type = lambda _snapshot: STORE_ALCHEMIST
    policy._next_purchase = lambda snapshot: (
        target if snapshot.store is not None else None
    )
    surface = helper._entrance_snapshot(helper._real_pack(), turn=turn)
    entrance = surface.player.position
    surface = replace(
        surface,
        grids={
            **surface.grids,
            entrance: replace(
                surface.grids[entrance], store_number=STORE_ALCHEMIST
            ),
        },
        messages=(),
    )
    return policy, surface, target


def _all_nonhome_needs_unobtainable():
    """Established no-effect evidence must survive the next WAIT turn."""
    helper = fixture.NoSafeRecallDestinationTest()
    policy, surface = helper._fixture()
    fixture.seed_character_calibration(policy, surface)
    policy._equipment_optimization_preparation = SimpleNamespace(
        blockers=(), result=None,
    )
    policy._recall_destination_safe = lambda *_args: True
    durable_state = policy._town_observable_effect_state(surface)
    for store_type in (
        policy_module.STORE_GENERAL,
        policy_module.STORE_ARMOURY,
        policy_module.STORE_WEAPON,
        policy_module.STORE_TEMPLE,
        STORE_ALCHEMIST,
        policy_module.STORE_MAGIC,
        policy_module.STORE_BLACK,
    ):
        policy._town_visit_ledger.nonhome_attempted_without_effect[
            store_type
        ] = durable_state
    policy._town_visit_ledger.approach_fails[STORE_HOME] = (
        policy._town_store_visit_limit(STORE_HOME)
    )
    policy._town_was_in_town = True

    class UnobtainableWorld(TownWorld):
        expected_terminal_reason = "town:blocked:departure-unsatisfiable"

        def terminal_ends_drive(self, reason, key):
            return reason == self.expected_terminal_reason and key == WAIT_KEY

    world = UnobtainableWorld(surface, entrance=STORE_ALCHEMIST, stock=())
    # Model the replacement stop's already-posted WAIT before the next
    # decision.  At 443e21a this turn tick erases the refusal and wanders.
    world.turn += EMITTED_TURNS_PER_PLAYER_TURN
    return policy, world


def _doubled_store_entry_cycle():
    """Delay the Alchemist page once after accepting its bare entrance WAIT."""
    policy, surface, target = _ordinary_alchemist_entry_seed(
        turn=3041933, target_sval=2999
    )
    delayed_page = [False]

    class DelayedEntryWorld(TownWorld):
        def __init__(self, snapshot):
            super().__init__(snapshot, entrance=STORE_ALCHEMIST, stock=[target])
            self.invalid_store_entries = 0
            self.expected_terminal_reason = "shop:one-shot-buy"

        def terminal_ends_drive(self, reason, key):
            return reason == self.expected_terminal_reason and key.startswith("p")

        def snapshot(self, decision):
            current = super().snapshot(decision)
            if delayed_page[0]:
                delayed_page[0] = False
                return replace(current, store=None)
            return current

        def apply(self, key):
            was_inside = self.inside
            if was_inside and key == WAIT_KEY:
                self.invalid_store_entries += 1
                self.last_key = key
                return
            super().apply(key)
            if not was_inside and key == WAIT_KEY and self.inside:
                delayed_page[0] = True

    return policy, DelayedEntryWorld(surface)


def _lagged_successful_store_entry():
    """Expose a direction posted into an Alchemist whose first page is lagged."""
    policy, surface, target = _ordinary_alchemist_entry_seed(
        turn=3041933, target_sval=3001
    )
    lag_store_page = [False]

    class LaggedSuccessfulEntryWorld(TownWorld):
        def __init__(self, snapshot):
            super().__init__(snapshot, entrance=STORE_ALCHEMIST, stock=[target])
            self.invalid_store_entries = 0
            self.expected_terminal_reason = "shop:one-shot-buy"

        def terminal_ends_drive(self, reason, key):
            return reason == self.expected_terminal_reason and key.startswith("p")

        def snapshot(self, decision):
            current = super().snapshot(decision)
            if lag_store_page[0]:
                lag_store_page[0] = False
                return replace(current, store=None, messages=())
            return current

        def apply(self, key):
            was_inside = self.inside
            if was_inside and key[:1] in MOVES:
                self.invalid_store_entries += 1
                self.last_key = key
                return
            super().apply(key)
            if not was_inside and key == WAIT_KEY and self.inside:
                lag_store_page[0] = True

    return policy, LaggedSuccessfulEntryWorld(surface)


def _failed_store_entry_same_turn():
    """A refused Alchemist WAIT must step off without a same-turn filler."""
    policy, surface, target = _ordinary_alchemist_entry_seed(
        turn=3467379, target_sval=3000
    )

    class RefusedEntryWorld(TownWorld):
        def __init__(self, snapshot):
            super().__init__(snapshot, entrance=STORE_ALCHEMIST, stock=[target])
            # choose_key's outer shop router labels the returned step as
            # shop:approach; reaching it still proves the refusal owner was
            # consumed and routing stepped off in the same decision.
            self.expected_terminal_reason = "shop:approach"

        def apply(self, key):
            if not self.inside and key == WAIT_KEY:
                self.last_key = key
                return
            super().apply(key)

        def snapshot(self, decision):
            current = super().snapshot(decision)
            if not self.inside and self.last_key == WAIT_KEY:
                return replace(current, messages=("The doors are locked.",))
            return current

    return policy, RefusedEntryWorld(surface)


def _aborted_shop_one_shot_stall_escape():
    """A real one-shot stopped mid-prompt gets the extracted bounded Escape."""
    policy, base, target = _ordinary_alchemist_entry_seed(
        turn=3041933, target_sval=2999
    )

    class AbortedWorld(TownWorld):
        expected_terminal_reason = "instrument:store-one-shot-abort-escape"

        def __init__(self, snapshot):
            super().__init__(snapshot, entrance=STORE_ALCHEMIST, stock=[target])
            self.aborted = False

        def terminal_ends_drive(self, reason, key):
            return reason == self.expected_terminal_reason and key == LEAVE_STORE_KEY

        def apply(self, key):
            if self.inside and key.startswith("p"):
                # The game accepts entry and the buy selector, then stops
                # consuming before confirmation and the composed tail.
                self.inside = True
                self.aborted = True
                self.last_key = key
                return
            super().apply(key)

    world = AbortedWorld(base)
    original_choose_key = policy.choose_key

    def choose_with_stall_seam(snapshot):
        key = original_choose_key(snapshot)
        if world.aborted and key == "":
            action = _stall_recovery_action(
                2.0, 1.5, in_store=True, recovery_attempts=0
            )
            if action == "store-escape":
                policy.last_reason = world.expected_terminal_reason
                return LEAVE_STORE_KEY
        return key

    policy.choose_key = choose_with_stall_seam
    return policy, world


def _quiet_stair_observation_timeout_probe():
    """Accepted '>' plus quiet same-turn boards must visibly leave the watch."""
    position = Position(10, 10)
    base = Snapshot(
        fixture.player(10, 10),
        {position: replace(fixture.grid(10, 10), has_down_stairs=True)},
        [], floor_key=(2, 1, 0), town_flag=False, turn=2128312,
        messages=("You enter a maze of down staircases.",),
    )
    policy = HengbotPolicy()

    class QuietStairWorld(TownWorld):
        expected_terminal_reason = "stair:observation-timeout-probe"

        def __init__(self, snapshot):
            super().__init__(snapshot)
            self.quiet = replace(base, messages=())

        def terminal_ends_drive(self, reason, key):
            return reason == self.expected_terminal_reason and key == "l\x1b"

        def visible_terminal(self, reason):
            if reason == self.expected_terminal_reason:
                return "bounded stair observation probe"
            return super().visible_terminal(reason)

        def snapshot(self, decision):
            return base if decision == 0 else self.quiet

        def apply(self, key):
            self.last_key = key

    return policy, QuietStairWorld(base)


def _home_semantic_churn_defect():
    """The captured cross-identity zero-delta pair is a real terminal report."""
    taken = ("captured-shovel", 3, 8)
    put = ("captured-shovel", 1, 5)
    executor = HomeVisitExecutor(3)
    executor.file(HomeVisitRequest(
        HomeVisitKind.WITHDRAW, "standing-digger", taken
    ))
    executor.begin_approach(1)
    executor.observe_outside_ready("fresh-take-address", 1)
    executor.record_operation("take", taken, 1)
    executor.post_exit()
    executor.observe_outside(effect_observed=True)
    executor.consume_report()
    executor.file(HomeVisitRequest(
        HomeVisitKind.DEPOSIT, "equipment-transaction", put
    ))
    executor.begin_approach(2)
    executor.observe_outside_ready("fresh-put-address", 2)
    executor.record_operation("put", put, 2)
    executor.post_exit()
    executor.observe_outside(effect_observed=True)
    report = executor.consume_report()
    home_visit_report = (
        f"home-visit:{report.request.requester}:{report.defect}"
    )
    assert executor.semantic_churn_cooldown

    class SemanticChurnPolicy:
        last_reason = ""

        def choose_key(self, _snapshot):
            self.last_reason = "home-visit:deposit-not-authorized"
            self.home_visit_report = home_visit_report
            return ""

    base = fixture.HomeOneOperationPerEntryTest()._entrance_snapshot([])

    world = TownWorld(base)
    world.expected_terminal_reason = (
        "home-visit:deposit-not-authorized"
    )
    return SemanticChurnPolicy(), world


def _town_sell_rebuy_churn_defect():
    """A same-class purchase after an observed sale is visibly terminal."""
    offered = fixture.store_item(
        "a", TVAL_DIGGING, 1, name="replacement shovel", price=50,
        is_equipment=True,
    )
    base = Snapshot(
        fixture.player(10, 10, gold=1000, class_id=0),
        {Position(10, 10): fixture.grid(10, 10)},
        [], floor_key=(0, 0, 0), town_flag=True,
        inventory=fixture.TownAndFundraisingPolicyTest()._strict_supplies(detection=5),
        store=StoreState(STORE_GENERAL, [offered]),
    )
    class ChurnPolicy(HengbotPolicy):
        def choose_key(self, snapshot):
            return self._shop(snapshot)

    policy = ChurnPolicy()
    policy._fundraising_mode = "prepare"
    policy._town_visit_sale_tvals.add(TVAL_DIGGING)
    class DefectWorld(TownWorld):
        def apply(self, key):
            self.last_key = key

    world = DefectWorld(base, entrance=STORE_GENERAL, stock=[offered])
    world.expected_terminal_reason = "shop:sell-rebuy-churn-defect"
    return policy, world


SEEDED_STATES = (
    AbsorbingState(
        "home-visit-semantic-churn-defect", 3,
        _home_semantic_churn_defect,
    ),
    AbsorbingState(
        "town-sell-rebuy-churn-defect", 3,
        _town_sell_rebuy_churn_defect,
    ),
    AbsorbingState(
        "quiet-stair-observation-timeout-probe", 20,
        _quiet_stair_observation_timeout_probe,
    ),
    AbsorbingState(
        "all-nonhome-needs-unobtainable-departure-unsatisfiable", 20,
        _all_nonhome_needs_unobtainable,
    ),
    AbsorbingState(
        "aborted-shop-one-shot-stall-escape", 12,
        _aborted_shop_one_shot_stall_escape,
    ),
    AbsorbingState(
        "home-random-teleport-suppression-one-shot", 20,
        _home_suppression_one_shot,
    ),
    AbsorbingState(
        "home-random-teleport-suppression-refusal", 20,
        _home_suppression_refusal,
    ),
    AbsorbingState(
        "catalogue-invalidated-equipment-work-repetition", 20,
        _catalogue_invalidated_with_equipment_work,
    ),
    AbsorbingState("home-blocked-departure", 300, _departure_freeze),
    AbsorbingState("wait-reenters-home-door", 200, _home_entry_cycle),
    AbsorbingState("released-home-attempt-bound", 800, _released_bound),
    AbsorbingState(
        "calibration-deposit-claim-budget", 300, _calibration_deposit_claim_budget
    ),
    AbsorbingState(
        "plan-none-live-calibration-home-available", 300,
        _plan_none_live_calibration_home_available,
    ),
    AbsorbingState(
        "calibration-prerequisite-scan-bound", 1000,
        _calibration_prerequisite_scan_bound,
    ),
    AbsorbingState(
        "successful-optimizer-transaction", 100,
        _successful_optimizer_transaction,
    ),
    AbsorbingState(
        "block-authority-mismatch-home-route", 100,
        _block_authority_mismatch_home_route,
    ),
    AbsorbingState(
        "exhausted-equipment-home-route", 40,
        _exhausted_equipment_home_route,
    ),
    AbsorbingState(
        "approach-refused-optimizer-transaction", 100,
        _approach_refused_optimizer_transaction,
    ),
    AbsorbingState(
        "frozen-approach-optimizer-transaction", 200,
        _frozen_approach_optimizer_transaction,
    ),
    AbsorbingState(
        "invalid-command-noop-home-cycle", 40,
        _invalid_command_noop_home_cycle,
    ),
    AbsorbingState("doubled-store-entry-cycle", 10, _doubled_store_entry_cycle),
    AbsorbingState("lagged-successful-store-entry", 10, _lagged_successful_store_entry),
    AbsorbingState("failed-store-entry-same-turn", 10, _failed_store_entry_same_turn),
    AbsorbingState(
        "transaction-abandoned-mid-strip", 20,
        _transaction_abandoned_mid_strip,
    ),
    AbsorbingState(
        "movement-opens-store-before-surface-observation", 10,
        _movement_opens_store_before_surface_observation,
    ),
    AbsorbingState("visit-scan-address-burst", 20, _scan_address_burst_visit_seed),
    AbsorbingState("visit-abandon-blocked-home", 20, _abandon_blocked_home_visit_seed),
    AbsorbingState(
        "visit-approach-entrance-stepoff", 20,
        _approach_entrance_stepoff_visit_seed,
    ),
    AbsorbingState(
        "visit-live-shop-entry-exit-531", 100,
        _live_shop_entry_exit_visit_seed,
    ),
)
