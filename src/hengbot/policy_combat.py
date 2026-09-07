from __future__ import annotations

from collections import Counter, deque
from heapq import heappop, heappush
from itertools import count
from math import ceil
from hengbot.loop_detection import LOOP_MAX_DISTINCT
from hengbot.monster_ranged_evaluator import (
    SpellSelectionContext,
    ability_selection_probabilities,
    cause_damage_percentile,
    evaluate_ability_effect,
    expected_ability_hp_damage,
    maximum_ability_hp_damage,
)
from hengbot.projection_path import projection_path
from hengbot.policy_types import ChokeEngagementPlan
from hengbot.policy_constants import (
    BREEDER_STALEMATE_TURN_LIMIT,
    COMBAT_OUTCOME_WINDOW,
    COMBAT_REASON_PREFIXES,
    EMERGENCY_RETURN_COUNT,
    ENGAGEMENT_AVOID_DAMAGE_RATIO,
    FIRE_KEY,
    FIXED_QUEST_HEAL_HP_RATIO,
    FLEE_HP_RATIO,
    HEAL_HP_RATIO,
    HEAL_POTION_SVALS,
    HUNT_HP_RATIO,
    HUNT_MAX_HOSTILES,
    HUNT_RANGE,
    QUAFF_KEY,
    RANGED_SLEEPER_MAX_DISTANCE,
    RANGED_TARGET_FAILURE_LIMIT,
    RESIST_FLAG_BY_ABILITY,
    SUMMONER_EXPOSED_NEIGHBORS,
    SUMMONER_RANGED_KILL_SHOTS,
    SWARM_COUNT,
    SWARM_LOOKAHEAD,
    THREAT_PREDICTION_MEMO_LIMIT,
    THROW_KEY,
    TORCH_THROW_MAX_DEPTH,
    UNIQUE_COMBAT_HP_RESERVE_RATIO,
    BARREN_FLOOR_SKIP_THRESHOLD,
    BREEDER_CONTAINMENT_WINDOW,
    CURE_CRITICAL_REQUIRED_DEPTH,
    FOOD_STOCK_TARGET,
    IDENTIFY_CHARGE_FLOOR,
    LANTERN_REFILL_FUEL,
    MANA_FOOD_DEVICE_TARGET,
    OIL_TARGET,
    QUEST_STATUS_UNTAKEN,
    STAFF_IDENTIFY_MAX_COUNT,
    STAFF_IDENTIFY_MIN_CHARGES,
    STAFF_IDENTIFY_MIN_DEPTH,
    SUMMONER_CHOKE_NEIGHBORS,
    SUPPLY_STORES,
    TELEPORT_REQUIRED_DEPTH,
    TORCH_REFILL_FUEL,
    BUY_KEY,
    CARDINAL_OFFSETS,
    CHARACTER_DUMP_MACRO,
    CHEST_COLLECT_BUDGET,
    CHEST_DISARM_BUDGET,
    CHEST_DISARM_KEY,
    CHEST_DROP_KEY,
    CHEST_OPEN_BUDGET,
    CHEST_OPEN_KEY,
    CHEST_SEARCH_BUDGET,
    CHEST_SEARCH_KEY,
    DIRECTION_KEYS,
    DOWN_STAIRS_KEY,
    EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
    EQUIPMENT_TRANSACTION_FINAL_STOP_REASONS,
    EAT_KEY,
    ExplorationPathOutcome,
    FOOD_MIN_SVAL,
    FOOD_TYPE_MANA,
    FULL_IDENTIFY_DISMISS_SUFFIX,
    FUNDRAISING_GOLD_TARGET,
    FUNDRAISING_DETECTION_BASE_PRICE,
    FUNDRAISING_DIGGER_BASE_PRICE,
    FUNDRAISING_KIT_MARGIN,
    FUNDRAISING_KIT_RESERVE,
    IDENTIFY_FAIL_LIMIT,
    IDENTIFY_PRESSURE_FREE_SLOTS,
    LEAVE_STORE_KEY,
    LOOT_DEFER_BLOCKERS,
    LOOT_THREAT_DAMAGE_RATIO,
    DIGGER_WIELD_LIMIT,
    MINING_COMBAT_CONTACT_LIMIT,
    MINING_DETECTION_RADIUS,
    MINING_NAVIGATION_REVISIT_LIMIT,
    MINING_OSCILLATION_RETARGET_LIMIT,
    MINING_ROUTE_REVISIT_LIMIT,
    MINING_STALL_LIMIT,
    MINING_SWEEP_HARD_LIMIT,
    MINING_SWEEP_NO_PROGRESS_LIMIT,
    MINING_THREAT_FREE_LIMIT,
    NEIGHBOR_OFFSETS,
    PACK_CAPACITY,
    PROBE_LIMIT,
    RANGED_MAX_DISTANCE,
    READ_KEY,
    RECALL_MIN_DEPTH,
    REFILL_KEY,
    SEARCH_KEY,
    SEARCH_LIMIT,
    SELL_KEY,
    STAFF_IDENTIFY_MIN_SUCCESS,
    STORE_RESTOCK_WAIT_TURNS,
    STORE_STUCK_LIMIT,
    STUCK_ESCAPE_LIMIT,
    TERMINAL_NUDGE_LIMIT,
    TOWN_TRAVEL_STORE_SYMBOLS,
    TOWN_STOP_PASS_LIMIT,
    TOWN_TRAVEL_STALL_LIMIT,
    TOWN_TRAVEL_TURN_STALL_LIMIT,
    TUNNEL_KEY,
    UP_STAIRS_KEY,
    USE_STAFF_KEY,
    WAIT_KEY,
    ZAP_ROD_KEY,
)
from hengbot.model import (
    DUNGEON_ANGBAND,
    DUNGEON_CHAMELEON_CAVE,
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
    SV_LITE_LANTERN,
    SV_LITE_FEANOR,
    SV_LITE_TORCH,
    SV_POTION_SLEEP,
    SV_POTION_SPEED,
    SV_POTION_CURE_CRITICAL,
    SV_POTION_HEALING,
    SV_POTION_RESIST_COLD,
    SV_SCROLL_PHASE_DOOR,
    SV_SCROLL_TELEPORT,
    RESTORE_POTION_SVAL_BY_STAT,
    STAT_GAIN_POTION_SVALS,
    SV_ROD_IDENTIFY,
    SV_ROD_LITE,
    SV_SCROLL_IDENTIFY,
    SV_SCROLL_DETECT_INVISIBLE,
    SV_SCROLL_DETECT_TRAP,
    SV_SCROLL_DETECT_ITEM,
    SV_SCROLL_DETECT_DOOR,
    SV_SCROLL_LIGHT,
    SV_SCROLL_BLESSING,
    SV_SCROLL_HOLY_CHANT,
    SV_SCROLL_STAR_IDENTIFY,
    SV_SCROLL_REMOVE_CURSE,
    SV_SCROLL_STAR_REMOVE_CURSE,
    SV_SCROLL_ENCHANT_WEAPON_TO_HIT,
    SV_SCROLL_ENCHANT_WEAPON_TO_DAM,
    SV_SCROLL_STAR_DESTRUCTION,
    SV_SCROLL_WORD_OF_RECALL,
    SV_STAFF_DESTRUCTION,
    SV_STAFF_IDENTIFY,
    SV_WAND_STONE_TO_MUD,
    SV_WAND_TELEPORT_AWAY,
    SV_HAFTED_WIZSTAFF,
    SPELLBOOK_TVALS,
    TVAL_AMULET,
    TVAL_ARROW,
    TVAL_BOLT,
    TVAL_BOW,
    TVAL_BOOTS,
    TVAL_CROWN,
    TVAL_CLOAK,
    TVAL_SOFT_ARMOR,
    TVAL_HARD_ARMOR,
    TVAL_DRAG_ARMOR,
    TVAL_GLOVES,
    TVAL_HELM,
    TVAL_SHIELD,
    TVAL_DIGGING,
    TVAL_FLASK,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_LIFE_BOOK,
    TVAL_CRUSADE_BOOK,
    TVAL_HISSATSU_BOOK,
    TVAL_POTION,
    TVAL_RING,
    TVAL_ROD,
    TVAL_SCROLL,
    TVAL_SHOT,
    TVAL_STAFF,
    TVAL_WAND,
    StoreState,
    TVAL_HAFTED,
    TVAL_POLEARM,
    TVAL_SWORD,
    TVAL_WHISTLE,
    TVAL_SPIKE,
    TVAL_FIGURINE,
    TVAL_STATUE,
    TVAL_CAPTURE,
    TVAL_CARD,
    TVAL_BOTTLE,
    TVAL_CHEST,
    GridState,
    InventoryItem,
    MonsterState,
    Position,
    QuestState,
    Snapshot,
    StoreItem,
    item_requires_full_identification,
)
from hengbot.policy import ExplorationGoalIdentity, ExplorationGoalKind
from hengbot.policy_constants import (
    BACKTRACK_PENALTY, DOOR_OPEN_LIMIT, EXTENDED_STUCK_WINDOW,
    NAV_ESCAPE_STEP_LIMIT, OPEN_KEY, RUBBLE_DIG_LIMIT, RUBBLE_REJECT_LIMIT,
    STAIR_OBSERVATION_WAIT_LIMIT, STUCK_WINDOW, VISIT_PENALTY,
)


class CombatMixin:
    def _forbid_wait_on_town_entrance(
        self, snapshot: Snapshot, key: str
    ) -> str:
        """Step an idle owner off a building door before posting the stay key.

        In the original keyset ``5`` maps to the stay command.  Hengband runs
        store/building entry effects even when that command keeps the player's
        coordinates unchanged.  Idle owners and the equipment executor are
        therefore projected away from an entrance unless this is the explicitly
        owned store-entry command.  Named terminals remain unchanged because
        the CLI consumes them before posting a key.
        Only a disclosed, plain, safe floor cell is eligible.  If the emitter
        supplies no such exit, expose the CLI's named stop instead of guessing
        through an unknown, warning-refused, hazardous, occupied, or special
        grid.
        """
        reason = self.last_reason or ""
        guarded_wait_owner = (
            reason == "rest"
            or reason == "town:recover"
            or reason == "opening-q34:wait"
            or reason == "calibration:await-capture"
            or reason.startswith("town:wait-restock:")
            or reason in {
                "town:wait-recall",
                "town:await-recall-confirmation",
                "fundraise:wait-recall",
                "return:wait-recall",
                "return:await-recall-confirmation",
                "breeder-breakthrough:wait-recall",
            }
            or reason.startswith("town:blocked:")
            or (
                reason.startswith("equipment-transaction:")
                and reason not in EQUIPMENT_TRANSACTION_FINAL_STOP_REASONS
            )
        )
        if key != WAIT_KEY or snapshot.store is not None or not guarded_wait_owner:
            return key
        if not hasattr(snapshot, "grid_at") or not hasattr(snapshot, "player"):
            return key
        if self.last_reason in {"livelock:exhausted", "combat:fruitless"}:
            return key
        here = snapshot.grid_at(snapshot.player.position)
        if (
            self._store_entry_wait_owner is not None
            and here is not None
            and here.store_number == self._store_entry_wait_owner
        ):
            # This WAIT is the store-entry command itself.  Projecting it to a
            # movement direction is unsafe across the player-turn/store
            # transition: the direction can arrive after the store opens and
            # fall through the store dispatcher's default branch.  Keep the
            # command whose meaning at this entrance is precisely "enter".
            return key
        on_disclosed_entrance = here is not None and (
            here.store_number >= 0
            or here.building_special >= 0
            or here.has_quest_enter
            or here.has_quest_exit
        )
        # This visit-scoped memory is deliberately independent of the terrain
        # region key, whose width/height/town-id inputs can transiently flicker.
        on_remembered_entrance = (
            snapshot.player.position in self._town_visit_entrances
        )
        if not (on_disclosed_entrance or on_remembered_entrance):
            return key

        return self._town_entrance_step_off_key(snapshot, self.last_reason)
    def _forbid_wait_while_damaged(self, snapshot: Snapshot, key: str) -> str:
        """Reject every bare no-op after an observed HP loss."""
        bare_no_op = key == WAIT_KEY or (
            snapshot.store is not None and key == "\r"
        )
        if not bare_no_op:
            return key

        # The public choose_key return is the only enforcement point.  In-store
        # carriage return is the store-loop equivalent of WAIT; leave that
        # command language before selecting an ordinary survival action.
        if self._took_damage and snapshot.store is not None:
            self.last_reason = "no-wait:leave-store"
            return LEAVE_STORE_KEY

        reason = self.last_reason
        strategic_hostiles = (
            self._strategic_hostiles(snapshot)
            if hasattr(snapshot, "visible_monsters")
            else []
        )
        hostiles = (
            self._physical_hostiles(snapshot)
            if hasattr(snapshot, "visible_monsters")
            else []
        )
        choke_hold = (
            reason == "melee:choke-hold"
            and not self._took_damage
            and bool(strategic_hostiles)
            and all(
                monster.max_ranged_damage <= 0 and monster.distance > 1
                for monster in strategic_hostiles
            )
        )
        # Keep this aligned with cli.STATIONARY_REASONS and the
        # stationary_by_design cases in _break_positional_oscillation. Importing
        # the CLI set here would introduce a policy/CLI cycle; these are the
        # bounded recall/confirmation waits and deliberate quest/rest holds.
        # A melee choke wait lets the queue approach without burning the escape
        # kit. The engagement-stall bound and the choke plan's sight-loss bound
        # limit an unproductive hold; damage, ranged fire, or adjacent contact
        # still enters the ladder below.
        sanctioned = (
            reason
            in {
                "return:wait-recall",
                "fundraise:wait-recall",
                "town:wait-recall",
                "town:wait-restock",
                "wilderness:wait-recall",
                "combat:disengage-wait-recall",
                "quest-strategy:hold",
                "quest:blocked:hold",
                "rest",
                "recover",
            }
            or (":await-" in reason and reason.endswith("-confirmation"))
            or reason.endswith(":hold")
            or reason.endswith(":recover")
            or choke_hold
        )
        if sanctioned and not self._took_damage:
            return key

        under_fire = self._took_damage or any(
            self._has_line_of_fire(
                snapshot, monster.position, snapshot.player.position
            )
            and self._predicted_damage(snapshot, [monster], turns=1) > 0
            for monster in hostiles
        )
        if not under_fire:
            return key

        # Every visible hostile here deals less than the user's weak-breeder
        # ignore threshold, so spending an escape scroll or fleeing would
        # contradict that rule.  Dangerous unseen attackers are handled by
        # the earlier danger and emergency paths; this function only rewrites
        # an already-selected unsanctioned WAIT.
        only_suppressed_weak_breeders = bool(hostiles) and not strategic_hostiles
        if not only_suppressed_weak_breeders:
            scroll = self._escape_scroll(snapshot)
            if scroll is not None:
                self.last_reason = "no-wait:escape-scroll"
                return self._read_key(snapshot, scroll)

            step = self._flee_step(snapshot, hostiles)
            if step is not None and not (
                self._escape_state.owner in {"disengage", "emergency"}
                and self._is_oscillating()
                and step in set(self._recent)
            ):
                self.last_reason = "no-wait:flee"
                return self._direction_key(snapshot.player.position, step)

        step = self._least_visited_neighbor(snapshot)
        if step is not None:
            self.last_reason = "no-wait:least-visited"
            return self._direction_key(snapshot.player.position, step)

        adjacent = [
            monster
            for monster in hostiles
            if snapshot.player.position.distance_to(monster.position) <= 1
        ]
        if adjacent and not snapshot.player.afraid:
            self.last_reason = "no-wait:melee"
            return self._direction_key(
                snapshot.player.position, self._weakest(adjacent).position
            )

        # A completely boxed player has no legal movement alternative.  Keep
        # the invariant explicit even there: attack the nearest observed threat
        # instead of spending another turn on a bare no-op.
        if self._took_damage and hostiles and not snapshot.player.afraid:
            target = min(hostiles, key=lambda monster: monster.distance)
            self.last_reason = "no-wait:attack"
            return self._direction_key(snapshot.player.position, target.position)

        return key
    def _flee_sustain_key(self, snapshot: Snapshot, key: str) -> str:
        """Spend healing/haste to keep a live escape episode moving."""
        if not hasattr(snapshot, "visible_monsters"):
            return key
        if snapshot.in_town or snapshot.store is not None:
            self._escape_sustain_active = False
            return key
        hostiles = self._physical_hostiles(snapshot)
        escaping = self._escape_action_selected()
        if not escaping:
            if self._escape_sustain_active:
                self._escape_sustain_non_escape_decisions += 1
                if self._escape_sustain_non_escape_decisions <= 1:
                    return key
            self._escape_sustain_active = False
            self._escape_sustain_non_escape_decisions = 0
            self._escape_speed_baseline = None
            self._escape_speed_attempted = False
            return key

        instant_escape = self.last_reason.startswith(
            (
                "emergency:teleport",
                "emergency:phase",
                "emergency:stairs",
                "emergency:cure",
                "flee:scroll",
                "flee:stairs",
            )
        )
        if instant_escape:
            return key
        episode_start = not self._escape_sustain_active
        if episode_start:
            self._escape_sustain_active = True
            self._escape_speed_baseline = snapshot.player.speed
            self._escape_speed_attempted = False
        self._escape_sustain_non_escape_decisions = 0
        if not hostiles:
            return key
        reserve = max(
            1, ceil(snapshot.player.max_hp * UNIQUE_COMBAT_HP_RESERVE_RATIO)
        )
        predicted = self._predicted_damage(snapshot, hostiles, turns=2)
        missing_hp = snapshot.player.max_hp - snapshot.player.hp
        if snapshot.player.hp - predicted <= reserve and missing_hp > reserve:
            potion = self._find_heal_potion(
                snapshot,
                expected_damage=min(predicted, missing_hp),
            )
            if potion is None and missing_hp > 0:
                potion = max(
                    (
                        item
                        for item in snapshot.inventory
                        if item.slot
                        and item.is_potion
                        and item.aware
                        and item.sval in HEAL_POTION_SVALS
                        and self._healing_potion_effective_hp(snapshot, item) > 0
                    ),
                    key=lambda item: (
                        self._healing_potion_effective_hp(snapshot, item),
                        item.slot,
                    ),
                    default=None,
                )
            if potion is not None:
                self.last_reason = "emergency:heal"
                return QUAFF_KEY + potion.slot

        faster_melee = any(
            monster.max_melee_damage > 0
            and monster.speed >= snapshot.player.speed
            for monster in hostiles
        )
        haste_active = (
            self._escape_speed_baseline is not None
            and snapshot.player.speed > self._escape_speed_baseline
        )
        if (
            episode_start
            and faster_melee
            and not haste_active
            and not self._escape_speed_attempted
        ):
            speed = self._find_exact_potion(snapshot, SV_POTION_SPEED)
            if speed is not None:
                self._escape_speed_attempted = True
                self.last_reason = "emergency:quaff-speed"
                return QUAFF_KEY + speed.slot
        return key
    def _strategic_hostiles(self, snapshot: Snapshot) -> list[MonsterState]:
        giveup_plan = self._choke_engagement_plan
        ignoring_immobile_breeders = (
            giveup_plan is not None
            and giveup_plan.floor == snapshot.floor_key
            and giveup_plan.release_cause in {
                "immobile-breeder-growth",
                "breeder-outcome-bound",
            }
        )
        return [
            monster
            for monster in snapshot.visible_monsters
            if (
                monster.hostile
                and not (ignoring_immobile_breeders and monster.can_multiply)
                and not (
                    self._breeder_breakthrough_floor == snapshot.floor_key
                    and self._is_weak_breeder(snapshot, monster)
                )
            )
        ]
    def _perceived_hostiles(self, snapshot: Snapshot) -> list[MonsterState]:
        """Return de-duplicated sight and detection records for anticipation."""
        perceived: dict[int, MonsterState] = {
            monster.index: monster
            for monster in snapshot.detected_monsters
            if monster.hostile
        }
        perceived.update(
            {
                monster.index: monster
                for monster in snapshot.visible_monsters
                if monster.hostile
            }
        )
        return [
            monster
            for monster in perceived.values()
            if not (
                self._breeder_breakthrough_floor == snapshot.floor_key
                and self._is_weak_breeder(snapshot, monster)
            )
        ]
    def _engagement_breeder_population(
        self, snapshot: Snapshot
    ) -> list[MonsterState]:
        """Return the perceived breeder population used for engagement judgement.

        Detection may inform counting, release decisions, and threat modelling,
        but this perceived channel must never be passed to melee, ranged,
        line-of-fire, or blocker-clearing target selection.
        """
        return [
            monster
            for monster in self._perceived_hostiles(snapshot)
            if monster.can_multiply
        ]
    def _ranged_target(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> MonsterState | None:
        """Nearest hostile the bot can hit with a plain direction-key shot.

        Requirements, all verifiable from the emitted (player-visible) state:
        ray-aligned on one of the 8 directions, within RANGED_MAX_DISTANCE,
        every intermediate ray tile KNOWN and passable (a shot flies over
        floor; walls/doors/rubble and unknown tiles abort), and no other
        monster earlier on the ray (the projectile hits the first body)."""
        player = snapshot.player
        occupied = {
            monster.position
            for monster in snapshot.visible_monsters
            if monster.position != player.position
        }
        best: MonsterState | None = None
        best_distance = RANGED_MAX_DISTANCE + 1
        for monster in hostiles:
            dy = monster.position.y - player.position.y
            dx = monster.position.x - player.position.x
            if dy == 0 and dx == 0:
                continue
            if not (dy == 0 or dx == 0 or abs(dy) == abs(dx)):
                continue
            distance = max(abs(dy), abs(dx))
            if distance < 2 or distance > RANGED_MAX_DISTANCE:
                continue
            if monster.asleep and distance > RANGED_SLEEPER_MAX_DISTANCE:
                continue
            step_y = (dy > 0) - (dy < 0)
            step_x = (dx > 0) - (dx < 0)
            clear = True
            for i in range(1, distance):
                tile = Position(
                    player.position.y + step_y * i,
                    player.position.x + step_x * i,
                )
                grid = snapshot.grids.get(tile)
                if grid is None or not grid.passable or tile in occupied:
                    clear = False
                    break
            if clear and distance < best_distance:
                best = monster
                best_distance = distance
        return best
    def _ranged_attack_key(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        adjacent: list[MonsterState],
    ) -> str | None:
        """Fire at (or throw oil at) a hostile before it closes.

        Adjacency is melee's job; confusion randomizes the aim direction and
        blindness hides the ray, so both bail. Fear deliberately does NOT
        bail — do_cmd_fire works while afraid, which turns the old
        flee-while-shot-to-death pattern into an exchange."""
        visible_indices = {monster.index for monster in hostiles}
        for index in self._ranged_target_signatures.keys() - visible_indices:
            self._ranged_target_signatures.pop(index, None)
            self._ranged_target_attempts.pop(index, None)
        if adjacent or not hostiles:
            return None
        player = snapshot.player
        if player.confused or player.blind:
            return None
        ammo = self._matching_ammo(snapshot)
        torch = self._first_item(
            snapshot, lambda it: it.is_torch and it.fuel > 0
        )
        if ammo is not None:
            prefix, slot, reason = FIRE_KEY, ammo.slot, "ranged:fire"
        elif (
            torch is not None
            and 1 <= snapshot.dungeon_level <= TORCH_THROW_MAX_DEPTH
        ):
            # Early floors: spam thrown torches (user directive) — ~1g each
            # and half of them survive on the floor for pickup.
            prefix, slot, reason = THROW_KEY, torch.slot, "ranged:throw-torch"
        else:
            # Deeper with no ammo: throw a spare flask of oil while keeping
            # the lantern-fuel reserve intact. Potions are NEVER thrown.
            flask = self._first_item(snapshot, lambda it: it.is_oil)
            if flask is None or self._supply_ledger(snapshot, snapshot.dungeon_level)["oil"].count <= OIL_TARGET:
                return None
            prefix, slot, reason = THROW_KEY, flask.slot, "ranged:throw-oil"

        if self._ranged_target_macro_signature is not None:
            (
                previous_floor,
                previous_position,
                previous_tval,
                previous_sval,
                previous_count,
            ) = self._ranged_target_macro_signature
            if (
                ammo is not None
                and previous_floor == snapshot.floor_key
                and previous_position == player.position
                and previous_tval == ammo.tval
                and previous_sval == ammo.sval
                and ammo.count >= previous_count
            ):
                self._ranged_target_macro_failures += 1
            else:
                self._ranged_target_macro_failures = 0
            self._ranged_target_macro_signature = None

        target = self._ranged_target(snapshot, hostiles)
        if target is not None:
            self._ranged_target_macro_failures = 0
            self.last_reason = reason
            # No leading ESC: at 00:31:55 it produced a same-turn pre-action
            # snapshot that the posting contract consumed as post-action.
            return prefix + slot + self._direction_key(player.position, target.position)

        eligible = [
            monster
            for monster in hostiles
            if 2 <= player.position.distance_to(monster.position) <= RANGED_MAX_DISTANCE
            and not (
                monster.asleep
                and player.position.distance_to(monster.position)
                > RANGED_SLEEPER_MAX_DISTANCE
            )
        ]
        if not eligible or ammo is None:
            return None
        victim = min(
            eligible,
            key=lambda monster: self._target_cursor_sort_key(player.position, monster),
        )

        if self._ranged_target_guard_position != player.position:
            self._ranged_target_guard_position = player.position
            self._ranged_target_attempts.clear()
            self._ranged_target_signatures.clear()
            self._ranged_target_macro_signature = None
            self._ranged_target_macro_failures = 0
        previous_hp = self._ranged_target_signatures.get(victim.index)
        if previous_hp is not None:
            if victim.hp < previous_hp:
                self._ranged_target_attempts[victim.index] = 0
            else:
                self._ranged_target_attempts[victim.index] = (
                    self._ranged_target_attempts.get(victim.index, 0) + 1
                )
        if self._ranged_target_attempts.get(victim.index, 0) >= RANGED_TARGET_FAILURE_LIMIT:
            return None
        if self._ranged_target_macro_failures >= RANGED_TARGET_FAILURE_LIMIT:
            return None

        aim = self._offset_fire_aim(snapshot, victim)
        if aim is not None:
            keys = self._cursor_delta_keys(player.position, aim)
            self._ranged_target_signatures[victim.index] = victim.hp
            if ammo is not None:
                self._ranged_target_macro_signature = (
                    snapshot.floor_key,
                    player.position,
                    ammo.tval,
                    ammo.sval,
                    ammo.count,
                )
            # 'p' resets both interest and free-grid targeting modes to the
            # player, giving the cursor movement a deterministic origin.
            self.last_reason = "ranged:fire-offset"
            # No leading ESC: at 00:31:55 its same-turn pre-action snapshot was
            # consumed as the post-action observation.
            return FIRE_KEY + ammo.slot + "*p" + keys + "t5\x1b"

        # Hengband's TARGET_KILL list is stably distance-sorted, so `*` initially
        # offers its nearest visible projectable non-pet monster; `t` accepts it.
        # `5` fires at the accepted target after returning to the direction
        # prompt.  The trailing Escape safely cancels fire if targeting failed.
        # Keep throwables on the bot-verified V1 direction path.
        targetable_hostile = any(
            2 <= (distance := max(
                abs(monster.position.y - player.position.y),
                abs(monster.position.x - player.position.x),
            )) <= RANGED_MAX_DISTANCE
            and not (
                monster.asleep and distance > RANGED_SLEEPER_MAX_DISTANCE
            )
            for monster in hostiles
        )
        if not targetable_hostile:
            return None
        self._ranged_target_signatures[victim.index] = victim.hp
        if ammo is not None:
            self._ranged_target_macro_signature = (
                snapshot.floor_key,
                player.position,
                ammo.tval,
                ammo.sval,
                ammo.count,
            )
        self.last_reason = "ranged:fire-target"
        # No leading ESC: at 00:31:55 its same-turn pre-action snapshot was
        # consumed as the post-action observation.
        return FIRE_KEY + ammo.slot + "*t5\x1b"
    def _offset_fire_aim(
        self,
        snapshot: Snapshot,
        victim: MonsterState,
        *,
        allow_direct_cursor: bool = False,
    ) -> Position | None:
        """Find an aim grid strictly beyond ``victim`` on a clear shot path."""
        origin = snapshot.player.position
        occupied = {monster.position for monster in snapshot.visible_monsters}

        def blocks(pos: Position) -> bool:
            grid = snapshot.grids.get(pos)
            # Unknown grids are deliberately optimistic: a wasted arrow is
            # cheaper than abandoning a potentially valid offset shot.
            return grid is not None and grid.known and not grid.allows_los

        def victim_precedes_aim(aim: Position) -> bool:
            path = projection_path(origin, aim, RANGED_MAX_DISTANCE, blocks)
            try:
                victim_index = path.index(victim.position)
                aim_index = path.index(aim)
            except ValueError:
                return False
            return victim_index < aim_index and not any(
                pos in occupied for pos in path[:victim_index]
            )

        # A direct target remains on the established *t5<esc> path.
        direct_path = projection_path(
            origin, victim.position, RANGED_MAX_DISTANCE, blocks
        )
        if victim.position in direct_path and not any(
            pos in occupied for pos in direct_path[: direct_path.index(victim.position)]
        ):
            return victim.position if allow_direct_cursor else None

        delta_y = victim.position.y - origin.y
        delta_x = victim.position.x - origin.x
        victim_dot = delta_y * delta_y + delta_x * delta_x
        candidates = []
        for y in range(1, snapshot.height - 1):
            for x in range(1, snapshot.width - 1):
                candidate = Position(y, x)
                candidate_y = y - origin.y
                candidate_x = x - origin.x
                if candidate_y * delta_y + candidate_x * delta_x > victim_dot:
                    candidates.append(candidate)
        candidates.sort(
            key=lambda pos: (
                len(self._cursor_delta_keys(origin, pos)),
                pos.y,
                pos.x,
            )
        )
        for candidate in candidates:
            if (
                candidate == origin
                or not (1 <= candidate.y < snapshot.height - 1)
                or not (1 <= candidate.x < snapshot.width - 1)
            ):
                continue
            if victim_precedes_aim(candidate):
                return candidate
        return None
    def _engagement_is_winnable(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> bool:
        """Whether the visible engagement can be cleared before HP runs out."""
        weapon = next(
            (
                item for item in snapshot.equipment
                if item.slot == "main_hand"
                and (item.is_melee_weapon or item.is_digging_tool)
            ),
            None,
        )
        melee_damage = (
            self._main_hand_dps(snapshot, weapon)
            if weapon is not None and snapshot.player.main_hand_blows > 0
            else 0.0
        )
        ranged_damage = self._estimated_ranged_damage_per_shot(snapshot)
        turns_to_clear = 0
        for monster in hostiles:
            damage = melee_damage
            if self._summoner_ranged_attack_available(snapshot, monster):
                damage = max(damage, ranged_damage)
            if damage <= 0:
                return False
            turns_to_clear += max(1, ceil(monster.hp / damage))
        incoming = self.threat_prediction(
            snapshot, hostiles, turns=turns_to_clear
        )["operational_total"]
        return incoming < snapshot.player.hp
    def _guarded_paralyzers(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> list[MonsterState]:
        return [
            monster for monster in hostiles
            if (
                (knowledge := self._monrace_knowledge.get(monster.race_id)) is not None
                and "NEVER_MOVE" in knowledge.flags
                and any(blow.effect == "PARALYZE" for blow in knowledge.blows)
                and any(
                    loot.distance_to(monster.position) <= 1
                    for loot in self._known_loot
                )
                and not self._nav_ledger.is_expired(
                    "paralyzer-guard", monster.position
                )
            )
        ]
    def _update_combat_outcome(self, snapshot: Snapshot) -> None:
        """Mark a combat streak fruitless when its full window has no outcome."""
        if self._breeder_engagement_floor != snapshot.floor_key:
            self._breeder_engagement_floor = snapshot.floor_key
            self._breeder_engagement_score = 0
            self._breeder_engagement_start_count = None
            self._breeder_engagement_start_turn = None
            self._breeder_kills = 0
            self._breeder_previous_exp = snapshot.player.exp
            self._breeder_previous_indices.clear()
        perceived_breeders = self._engagement_breeder_population(snapshot)
        if (
            self._breeder_previous_indices
            and self._breeder_previous_exp is not None
            and snapshot.player.exp > self._breeder_previous_exp
            and self._breeder_previous_indices
            - {monster.index for monster in perceived_breeders}
            and (
                self.last_reason == "melee"
                or self.last_reason == "fundraise:eliminate-multiplier"
                or self.last_reason.startswith(("ranged:", "hunt"))
            )
        ):
            self._breeder_kills += 1
        if perceived_breeders and self._breeder_engagement_start_count is None:
            self._breeder_engagement_start_count = len(perceived_breeders)
            self._breeder_engagement_start_turn = snapshot.turn
        if (
            self._breeder_engagement_start_count is not None
            and len(perceived_breeders) < self._breeder_engagement_start_count
        ):
            self._breeder_engagement_start_turn = snapshot.turn
        if (
            self._breeder_engagement_start_count is not None
            and self._breeder_kills >= 5
            and len(perceived_breeders) > self._breeder_engagement_start_count
        ):
            self._breeder_breakthrough_floor = snapshot.floor_key
        if (
            self._breeder_engagement_start_count is not None
            and self._breeder_engagement_start_turn is not None
            and len(perceived_breeders) >= self._breeder_engagement_start_count
            and snapshot.turn - self._breeder_engagement_start_turn
            >= BREEDER_STALEMATE_TURN_LIMIT
        ):
            self._breeder_breakthrough_floor = snapshot.floor_key
        self._breeder_previous_exp = snapshot.player.exp
        self._breeder_previous_indices = {
            monster.index for monster in perceived_breeders
        }
        breeders = (
            perceived_breeders
            if self._breeder_breakthrough_floor != snapshot.floor_key
            else []
        )
        productive_choke = self._productive_choke_hold(snapshot)
        plan = self._choke_engagement_plan
        if (
            not productive_choke
            and plan is not None
            and self._choke_plan_active(snapshot)
            and (
                snapshot.player.exp > plan.start_exp
                or snapshot.player.gold > plan.start_gold
            )
        ):
            # Breeder handling clears the general combat-outcome window below,
            # so reward progress owned by an active choke plan must be read from
            # that plan or a real kill would look like an unproductive hold.
            productive_choke = True
        if breeders and not productive_choke:
            self._breeder_engagement_score += 1
        else:
            # Brief line-of-sight breaks must not erase a nearly overrun fight,
            # while a genuinely cleared encounter should age out promptly.
            self._breeder_engagement_score = max(
                0, self._breeder_engagement_score - 4
            )
        if not self._fruitless_disengage_spent_this_decision:
            self._fruitless_disengage_decisions = max(
                0, self._fruitless_disengage_decisions - 4
            )
        if breeders:
            self._combat_outcomes.clear()
            self._combat_fruitful = True
            return
        reason = self.last_reason
        combat = reason == "melee" or reason.startswith(COMBAT_REASON_PREFIXES)
        combat_adjacent = reason in {
            "fundraise:eliminate-multiplier",
            "fundraise:clear-hostile",
        } or reason == "pickup" or reason.endswith(":pickup")
        if (
            combat_adjacent
            and self._combat_outcomes
            and not snapshot.in_town
            and snapshot.floor_key == self._combat_outcome_floor
        ):
            return
        if not combat or snapshot.in_town or snapshot.floor_key != self._combat_outcome_floor:
            self._combat_outcomes.clear()
            self._combat_fruitful = True
            self._combat_outcome_floor = snapshot.floor_key
            if not combat or snapshot.in_town:
                return

        hostiles = [monster for monster in snapshot.visible_monsters if monster.hostile]
        hp_by_index = {monster.index: monster.hp for monster in hostiles}
        self._combat_outcomes.append(
            (
                snapshot.player.exp,
                snapshot.player.gold,
                len(hostiles),
                hp_by_index,
            )
        )
        if len(self._combat_outcomes) <= COMBAT_OUTCOME_WINDOW:
            self._combat_fruitful = True
            return

        first = self._combat_outcomes[0]
        last = self._combat_outcomes[-1]
        quarter = max(1, len(self._combat_outcomes) // 4)
        outcomes = list(self._combat_outcomes)
        # Breeders make the visible count bob up and down.  Treat only a clean,
        # sustained shift between the opening and closing quarters as kills;
        # an endpoint dip inside the same 54--64 swarm is not an outcome.
        hostile_count_progress = max(
            outcome[2] for outcome in outcomes[-quarter:]
        ) < min(outcome[2] for outcome in outcomes[:quarter])
        single_target_index = next(iter(first[3])) if first[2] == 1 else None
        single_target_progress = (
            single_target_index is not None
            and all(outcome[2] == 1 for outcome in outcomes)
            and all(single_target_index in outcome[3] for outcome in outcomes)
            and last[3][single_target_index] < first[3][single_target_index]
        )
        self._combat_fruitful = bool(
            last[0] > first[0]
            or last[1] > first[1]
            or hostile_count_progress
            or single_target_progress
        )
        if (
            not self._combat_fruitful
            and self._fruitless_disengage_floor != snapshot.floor_key
        ):
            self._fruitless_disengage_floor = snapshot.floor_key
            self._fruitless_disengage_decisions = self._escape_state.budgets[
                "fruitless-disengage"
            ]
            self._returning_to_town = True
            self.last_reason = "combat:disengage-armed"
    def _fruitless_fight_is_winnable(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> bool:
        """Whether ordinary combat can finish the nearest threat survivably."""
        if not hostiles or any(monster.can_multiply for monster in hostiles):
            return False

        target = min(hostiles, key=lambda monster: (monster.distance, monster.hp))
        knowledge = self._monrace_knowledge.get(target.race_id)
        if knowledge is not None and "UNIQUE" in knowledge.flags:
            # Unprofitable uniques have their own bounded attack-budget policy.
            # Do not let a harmless high-HP unique undo that disengage decision.
            return False
        damage = 0.0
        if target.distance <= 1:
            weapon = next(
                (
                    item
                    for item in snapshot.equipment
                    if item.slot == "main_hand"
                    and (item.is_melee_weapon or item.is_digging_tool)
                ),
                None,
            )
            if weapon is not None:
                damage = self._main_hand_dps(snapshot, weapon)
        elif self._summoner_ranged_attack_available(snapshot, target):
            damage = self._estimated_ranged_damage_per_shot(snapshot)
        if damage <= 0:
            return False

        turns_to_kill = max(1, ceil(target.hp / damage))
        incoming = self.threat_prediction(
            snapshot, hostiles, turns=turns_to_kill
        )["operational_total"]
        return incoming < snapshot.player.hp
    def _emergency_item(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        player = snapshot.player

        issue_watch = self._emergency_consumable_issue_watch
        if issue_watch is not None:
            (
                issue_floor,
                issue_turn,
                issue_position,
                item_signature,
                pre_use_count,
                item_kind,
            ) = issue_watch
            current_count = sum(
                item.count
                for item in snapshot.inventory
                if self._item_signature(item) == item_signature
            )
            if snapshot.floor_key != issue_floor:
                self._emergency_consumable_issue_watch = None
            elif current_count < pre_use_count:
                accepted = (
                    item_kind == "recall" and player.recalling
                ) or (
                    item_kind in {"teleport", "phase"}
                    and player.position != issue_position
                )
                if not accepted:
                    owner = "emergency:await-consumable-confirmation"
                    if self._owner_expectations.is_pending(owner) and self._owner_may_select(
                        snapshot, owner
                    ):
                        self._emergency_consumable_issue_watch = None
                    else:
                        self.last_reason = owner
                        if not self._owner_expectations.is_pending(owner):
                            self._post_owner_expectation(
                                snapshot, owner, "position", "recalling", "inventory", "hp"
                            )
                        return WAIT_KEY
                else:
                    self._emergency_consumable_issue_watch = None
            elif snapshot.turn <= issue_turn:
                # Exact/interleaved redraw of the command state: never spend a
                # second scroll.  A queued wait is harmless after a successful
                # relocation and advances the board after a genuine rejection.
                owner = "emergency:await-consumable-confirmation"
                if self._owner_may_select(snapshot, owner):
                    self.last_reason = owner
                    self._post_owner_expectation(
                        snapshot, owner, "position", "recalling", "inventory"
                    )
                    return WAIT_KEY
                self._emergency_consumable_issue_watch = None
            else:
                # The turn advanced with the same stack and no relocation: the
                # original read was rejected, so one ordinary retry is safe.
                self._emergency_consumable_issue_watch = None

        if (
            not player.blind
            and any(
                item.is_teleport_scroll
                or (item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_PHASE_DOOR)
                or item.is_recall_scroll
                for item in snapshot.inventory
            )
        ):
            darkness_recovery = self._darkness_recovery_key(snapshot)
            if darkness_recovery is not None:
                return darkness_recovery

        # Recall takes many game turns.  A monster outside the exported field of
        # view can keep damaging us throughout that countdown, so
        # return:wait-recall is not safe after an observed HP drop.  Relocate to
        # break its firing lane while preserving the active recall; if that is
        # impossible, spend recovery or keep moving toward an immediate exit.
        # This must run before threat projection because an unseen attacker is
        # absent from ``hostiles`` and therefore projects as zero damage.
        if (
            player.recalling
            and self._took_damage
            and self._unseen_attack_evidence is not None
            and not self._took_curse_damage
            and not self._took_trap_or_terrain_damage
            and not hostiles
            and not snapshot.in_town
        ):
            self._emergency_return_active = True
            self._unseen_recall_damage_streak += 1
            self._returning_to_town = True
            self._last_return_trigger = "unseen-attacker"
            here = snapshot.grid_at(player.position)
            if (
                here is not None
                and self._is_upstairs_target(here)
                and not self._quest_floor_exit_locked(snapshot)
            ):
                self.last_reason = "emergency:stairs"
                return UP_STAIRS_KEY
            urgent_relocation = (
                self._unseen_recall_damage_streak >= 2
                or player.hp_ratio < 0.55
                or self._last_damage_amount >= player.max_hp * 0.10
            )
            if urgent_relocation and not player.blind and not player.confused:
                scroll = self._escape_scroll(snapshot)
                if scroll is not None:
                    reason = (
                        "emergency:teleport"
                        if scroll.is_teleport_scroll
                        else "emergency:phase"
                    )
                    return self._issue_emergency_consumable(
                        snapshot, scroll, reason
                    )
            if player.hp_ratio < HEAL_HP_RATIO:
                potion = self._find_heal_potion(snapshot, expected_damage=1)
                if potion is not None:
                    self.last_reason = "unseen-recall:heal"
                    return QUAFF_KEY + potion.slot
            step = self._nearest_goal_step(snapshot, self._is_upstairs_target)
            if step is not None and (
                self._is_oscillating() and step in set(self._recent)
            ):
                step = None
            if step is None:
                step = self._least_visited_neighbor(snapshot)
            if step is not None:
                self.last_reason = "unseen-recall:move"
                return self._step_toward(snapshot, step)
        else:
            # Require consecutive observed hits for the persistence trigger.
            # A quiet decision means movement successfully broke contact.
            self._unseen_recall_damage_streak = 0

        predicted = self._predicted_damage(snapshot, hostiles, turns=3)
        unseen_lethal = (
            self._took_damage
            and self._unseen_attack_evidence is not None
            and not self._took_curse_damage
            and not self._took_trap_or_terrain_damage
            and not hostiles
            and not snapshot.in_town
            and not player.poisoned
            and not player.cut
            and self._last_damage_amount >= player.hp
        )
        ranged_scroll_lock = self._ranged_scroll_lock_escape_needed(
            snapshot, hostiles, predicted=predicted
        )
        profile = self.approved_quest_strategy(snapshot.floor_key[2])
        immediate_races = {
            int(race_id)
            for race_id in (
                profile.engagement_plan.get("immediate_priority_targets", ())
                if profile is not None else ()
            )
        }
        summoners = [monster for monster in hostiles if monster.can_summon]
        committed_summoner_engagement = (
            bool(summoners)
            and all(monster.race_id in immediate_races for monster in summoners)
            and len(hostiles) < SWARM_COUNT
        )
        summoner_open = (
            bool(summoners)
            and not committed_summoner_engagement
            and self._open_neighbor_count(snapshot, player.position)
            >= SUMMONER_EXPOSED_NEIGHBORS
            and not self._summoner_cover_in_one_step(snapshot)
            and not any(
                (shots := self._summoner_shots_to_kill(snapshot, monster))
                is not None and shots <= SUMMONER_RANGED_KILL_SHOTS
                and self._summoner_ranged_attack_available(snapshot, monster)
                for monster in summoners
            )
        )
        guardian_reposition = (
            summoner_open
            and predicted < player.hp
            and self._viable_target_guardian_visible(snapshot, hostiles)
        )
        q22_opening = self._q22_opening_consumable_before_escape(
            snapshot, profile
        )
        if q22_opening is not None:
            return q22_opening
        q22_reposition_active = self._q22_reposition_active(profile)
        q22_healing = self._q22_reposition_recovery_before_escape(
            snapshot, profile, hostiles
        )
        if q22_healing is not None:
            self.last_reason = "quest-strategy:q22-reposition-heal"
            return QUAFF_KEY + q22_healing.slot
        if not summoner_open and not q22_reposition_active:
            unique_consumable = self._unique_combat_consumable(snapshot, hostiles)
            if unique_consumable is not None:
                return unique_consumable
        q31_opening_controlled = self._q31_opening_hold_is_controlled(
            snapshot, profile, hostiles
        )
        if q31_opening_controlled and not self._fixed_quest_speed_attempted:
            threshold = float(
                profile.consumable_plan.get("speed_potion_use_when", {}).get(
                    "expected_damage_hp_ratio_min", 1.0
                )
            )
            projected = self.threat_prediction(snapshot, hostiles, turns=3)[
                "operational_total"
            ]
            if projected >= threshold * snapshot.player.hp:
                speed = self._find_exact_potion(snapshot, SV_POTION_SPEED)
                if speed is not None:
                    self._fixed_quest_speed_attempted = True
                    self.last_reason = "quest-strategy:quaff-speed"
                    return QUAFF_KEY + speed.slot
        q31_healing = self._q31_opening_heal_before_escape(
            snapshot, profile, hostiles
        )
        if q31_healing is not None:
            self.last_reason = "quest-strategy:opening-heal"
            return QUAFF_KEY + q31_healing.slot
        protected_q31_hold = self._q31_opening_hold_absorbs_threat(
            snapshot, profile, hostiles
        )
        protected_q31_stationary_engagement = (
            self._q31_stationary_engagement_absorbs_threat(
                snapshot, profile, hostiles
            )
        )
        heal_ratio = (
            float(
                profile.consumable_plan.get(
                    "heal_threshold_ratio", FIXED_QUEST_HEAL_HP_RATIO
                )
            )
            if profile is not None
            else FIXED_QUEST_HEAL_HP_RATIO
            if self._active_fixed_quest_id(snapshot) is not None
            or self._active_kill_quest_id(snapshot) is not None
            else HEAL_HP_RATIO
        )
        lethal = (
            unseen_lethal
            or (
                bool(hostiles)
                and (predicted >= player.hp or ranged_scroll_lock)
                and not protected_q31_hold
                and not protected_q31_stationary_engagement
                and not self._committed_unique_fight_viable(snapshot, hostiles)
            )
        )
        if lethal or summoner_open:
            self._emergency_escape_pending = True
            self._emergency_return_active = True
            if (
                not guardian_reposition
                and self._dive_emergencies + 1 >= EMERGENCY_RETURN_COUNT
            ):
                self._returning_to_town = True
            self._last_return_trigger = (
                "guardian-reposition"
                if guardian_reposition
                else "emergency-summoner"
                if summoner_open
                else "emergency-ranged-status-lock"
                if ranged_scroll_lock
                else "emergency-lethal-swarm"
            )

        if self._emergency_escape_pending:
            stairs = self._escape_by_stairs(snapshot)
            if stairs is not None:
                self.last_reason = (
                    "emergency:stairs-quest-fail"
                    if self._quest_exit_would_fail(snapshot)
                    else "emergency:stairs"
                )
                return stairs

            if player.blind or player.confused or player.cut:
                potion = self._find_status_cure_potion(snapshot)
                if potion is not None:
                    self.last_reason = (
                        "emergency:cure-critical"
                        if potion.sval == SV_POTION_CURE_CRITICAL
                        else "emergency:cure-status-healing"
                    )
                    return QUAFF_KEY + potion.slot

            if lethal or summoner_open:
                if not player.blind and not player.confused:
                    scroll = self._escape_scroll(snapshot)
                    if scroll is not None:
                        if guardian_reposition:
                            self.last_reason = "guardian:teleport-to-cover"
                        else:
                            if self._fundraising_mode in {"mine", "scavenge"}:
                                self._returning_to_town = True
                            self.last_reason = (
                                "emergency:teleport"
                                if scroll.is_teleport_scroll
                                else "emergency:phase"
                            )
                        return self._issue_emergency_consumable(
                            snapshot, scroll, self.last_reason
                        )
                    # Teleport/phase scrolls exhausted: escape the FLOOR by
                    # Word of Recall rather than be trapped. A dl11 swarm
                    # drained the teleports, after which seek-upstairs/wait had
                    # no exit and the bot waited and died. Reading recall now
                    # starts the countdown home; subsequent turns flee to
                    # survive it. (Teleport relocates on-floor; recall leaves
                    # the floor entirely, so it is the escape of last resort.)
                    if (
                        not player.recalling
                        and not self._quest_floor_exit_locked(snapshot)
                        and self._can_read_scrolls(snapshot)
                    ):
                        recall = self._find_recall_scroll(snapshot)
                        if recall is not None:
                            self.last_reason = (
                                "emergency:recall-quest-fail"
                                if self._quest_exit_would_fail(snapshot)
                                else "emergency:recall"
                            )
                            return self._issue_emergency_consumable(
                                snapshot, recall, self.last_reason
                            )
                if player.hp_ratio < heal_ratio:
                    expected = self._predicted_damage(
                        snapshot, hostiles, turns=1, expected=True
                    )
                    potion = self._find_heal_potion(
                        snapshot, expected_damage=expected
                    )
                    if potion is not None:
                        self.last_reason = "emergency:heal"
                        return QUAFF_KEY + potion.slot
                route_step = self._nearest_goal_step(
                    snapshot, self._is_upstairs_target
                )
                if route_step is None:
                    blocker = self._blocking_escape_melee_key(
                        snapshot, hostiles, self._is_upstairs_target
                    )
                    if blocker is not None:
                        self.last_reason = "emergency:clear-escape-path"
                        return blocker
                if route_step is not None:
                    self.last_reason = "emergency:seek-upstairs"
                    return self._step_toward(snapshot, route_step)
                flee_step = self._flee_step(snapshot, hostiles)
                if flee_step is not None and not (
                    self._is_oscillating() and flee_step in set(self._recent)
                ):
                    self.last_reason = "emergency:seek-upstairs"
                    return self._step_toward(snapshot, flee_step)
                adjacent = [
                    monster for monster in hostiles if monster.distance <= 1
                ]
                if adjacent and not player.afraid:
                    # No stair, relocation, recall, or open retreat cell remains.
                    # Waiting donates every turn to the surrounding monsters;
                    # attack the weakest adjacent blocker to create an exit.
                    self.last_reason = "emergency:cornered-attack"
                    return self._direction_key(
                        player.position, self._weakest(adjacent).position
                    )
                self.last_reason = "emergency:wait"
                return WAIT_KEY

            # A teleport landed safely. One relocation is not enough reason to
            # abandon an otherwise healthy dive; reassess the landing and only
            # keep returning when recovery is unsafe or escapes are repeating.
            self._emergency_escape_pending = False
            return_trigger = self._post_emergency_return_trigger(snapshot, hostiles)
            if return_trigger is not None:
                self._returning_to_town = True
                self._last_return_trigger = return_trigger
            elif not guardian_reposition:
                self._returning_to_town = False
                self._last_return_trigger = None

        # Cure Critical Wounds is status treatment, never an HP-response potion.
        if player.blind or player.confused or player.cut:
            potion = self._find_status_cure_potion(snapshot)
            if potion is not None:
                self.last_reason = (
                    "item:cure-critical"
                    if potion.sval == SV_POTION_CURE_CRITICAL
                    else "item:cure-status-healing"
                )
                return QUAFF_KEY + potion.slot
        # Quaff a healing potion when badly hurt IN A FIGHT. When no enemy is
        # around, resting heals for free, so we don't waste a limited potion.
        if (
            hostiles
            and not q22_reposition_active
            and player.hp_ratio < heal_ratio
        ):
            expected_damage = self._predicted_damage(
                snapshot, hostiles, turns=1, expected=True
            )
            potion = self._find_heal_potion(
                snapshot, expected_damage=expected_damage
            )
            if potion is not None:
                self.last_reason = "item:heal"
                return QUAFF_KEY + potion.slot
        # Eat before we faint from hunger.
        if player.fainting:
            food = self._find_edible(snapshot)
            if food is not None:
                self.last_reason = "item:eat"
                return EAT_KEY + food.slot
        return None
    def _has_state_based_free_action(self, snapshot: Snapshot) -> bool:
        """Trust only an explicitly active per-source free-action grant."""
        return bool(snapshot.player.ability_sources.get("free_action", ()))
    def _paralyzing_monsters(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> list[MonsterState]:
        if self._has_state_based_free_action(snapshot):
            return []
        return [
            monster
            for monster in hostiles
            if (
                (knowledge := self._monrace_knowledge.get(monster.race_id))
                is not None
                and any(blow.effect == "PARALYZE" for blow in knowledge.blows)
            )
        ]
    def _refresh_paralyzer_avoidance(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> list[MonsterState]:
        """Put remembered paralyzer melee rings in the shared route veto."""
        previous_cells = getattr(self, "_paralyzer_avoid_cells", set())
        self._engagement_avoid_cells -= (
            previous_cells
            - self._engagement_owned_avoid_cells
            - self._warning_refused_cells
        )
        # Sleeping paralyzers do not actively trigger prevention, but their
        # adjacency ring still has to veto a hunt step that would wake them in
        # melee range.  The active list below deliberately excludes sleepers.
        ring_threats = (
            []
            if self._has_state_based_free_action(snapshot)
            else [
                monster
                for monster in hostiles
                if (
                    (knowledge := self._monrace_knowledge.get(monster.race_id))
                    is not None
                    and any(
                        blow.effect == "PARALYZE" for blow in knowledge.blows
                    )
                )
            ]
        )
        threats = self._paralyzing_monsters(snapshot, hostiles)
        if not hasattr(self, "_remembered_paralyzers"):
            self._remembered_paralyzers = {}
        visible_positions = {monster.position for monster in hostiles}
        for monster in ring_threats:
            knowledge = self._monrace_knowledge.get(monster.race_id)
            self._remembered_paralyzers[monster.position] = bool(
                knowledge is not None and "NEVER_MOVE" in knowledge.flags
            )
        for position in list(self._remembered_paralyzers):
            observed = snapshot.grids.get(position)
            if (
                position not in visible_positions
                and observed is not None
                and observed.in_view
                and observed.currently_observed
                and (
                    observed.lit
                    or snapshot.player.position.distance_to(position) <= 1
                )
                and not observed.has_monster
            ):
                self._remembered_paralyzers.pop(position, None)
                cleared = {
                    Position(position.y + dy, position.x + dx)
                    for dy, dx in NEIGHBOR_OFFSETS + ((0, 0),)
                }
                released = self._deferred_loot & cleared
                self._deferred_loot -= released
                if released and self._loot_defer_blocker == "paralyzer-ring":
                    self._loot_defer_blocker = None
        cells = {
            position
            for threat_position in self._remembered_paralyzers
            for dy, dx in NEIGHBOR_OFFSETS + ((0, 0),)
            if (position := Position(threat_position.y + dy, threat_position.x + dx))
            in snapshot.grids
        }
        self._paralyzer_avoid_cells = cells
        self._engagement_avoid_cells |= cells
        if any(step in cells for step in self._explore_path):
            self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
        return threats
    def _paralyzer_prevention_key(
        self,
        snapshot: Snapshot,
        threats: list[MonsterState],
        physical_adjacent: list[MonsterState],
    ) -> str | None:
        """Refuse melee and walk away whenever a paralyzer is adjacent."""
        adjacent = [
            monster
            for monster in threats
            if monster.distance <= 1
            and (
                monster.asleep
                or "NEVER_MOVE"
                not in self._monrace_knowledge[monster.race_id].flags
            )
        ]
        if not adjacent:
            return None
        shared_avoid = self._engagement_avoid_cells
        self._engagement_avoid_cells = shared_avoid - self._paralyzer_avoid_cells
        try:
            step = self._flee_step(snapshot, physical_adjacent)
        finally:
            self._engagement_avoid_cells = shared_avoid
        if step is None:
            return None
        self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
        self.last_reason = "threat:paralyzer-avoid"
        return self._step_toward(
            snapshot, step, allow_paralyzer_ring_escape=True
        )
    def _ranged_scroll_lock_threats(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
    ) -> list[MonsterState]:
        """Find visible casters that can disable escape-scroll reading.

        Blindness and confusion are qualitatively different from ordinary HP
        damage: after either lands, a warrior carrying scrolls must first spend
        a turn curing the status.  Use the shared ranged-effect evaluator so
        direct status spells and elemental side effects (notably BA_LITE) obey
        the same resistance and saving-throw model as equipment evaluation.
        """
        if snapshot.player.blind or snapshot.player.confused:
            return []

        flags = frozenset(
            flag
            for ability, flag in RESIST_FLAG_BY_ABILITY.items()
            if ability in snapshot.player.abilities
        )
        threats: list[MonsterState] = []
        for monster in hostiles:
            if monster.asleep or not self._has_line_of_fire(
                snapshot, monster.position, snapshot.player.position
            ):
                continue
            knowledge = self._monrace_knowledge.get(monster.race_id)
            if (
                knowledge is None
                or knowledge.spell_frequency <= 0
                or not knowledge.abilities
            ):
                continue
            selection = ability_selection_probabilities(
                knowledge,
                SpellSelectionContext(distance=max(1, monster.distance)),
            )
            for ability, probability in selection.items():
                if probability <= 0:
                    continue
                exposure = dict(
                    evaluate_ability_effect(
                        ability,
                        knowledge,
                        flags=flags,
                        player_hp=snapshot.player.hp,
                        blind=False,
                        saving_skill=snapshot.player.saving_skill,
                    ).status_turn_exposure
                )
                if exposure.get("blind", 0.0) > 0 or exposure.get(
                    "confused", 0.0
                ) > 0:
                    threats.append(monster)
                    break
        return threats
    def _ranged_scroll_lock_escape_needed(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        *,
        predicted: int,
    ) -> bool:
        """Escape before a ranged status forces a lethal cure turn.

        The ordinary predictor budgets three monster turns against actions the
        player can choose.  A scroll-locking hit instead forces the next action
        to be a status cure.  Charge one additional operational turn for that
        lost action, but only while a readable escape scroll exists now.
        """
        if self._escape_scroll(snapshot) is None:
            return False
        if not self._ranged_scroll_lock_threats(snapshot, hostiles):
            return False
        forced_cure_turn = self._predicted_damage(snapshot, hostiles, turns=1)
        return predicted + forced_cure_turn >= snapshot.player.hp
    def _predicted_damage(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        turns: int,
        *,
        expected: bool = False,
    ) -> int:
        prediction = self.threat_prediction(snapshot, hostiles, turns)
        return prediction["expected_total" if expected else "operational_total"]
    def threat_prediction(
        self, snapshot: Snapshot, hostiles: list[MonsterState], turns: int = 3
    ) -> dict:
        # The aggregate-p95 convolution below costs hundreds of milliseconds per
        # deep-floor caster, and one decision asks for the same prediction up to
        # six times (emergency/return gates plus the decision-log telemetry).
        # Key the memo on OBJECT IDENTITY plus turn/turns — and store the
        # snapshot itself in the entry: the strong reference keeps its id from
        # being recycled, and the `is` check proves the hit really is the same
        # object (a gc'd snapshot's id CAN be reused by its successor, which
        # once served a stale prediction). _observe also clears the memo every
        # decision, scoping it to exactly the repeats it exists for.
        memo_key = (
            id(snapshot),
            snapshot.turn,
            turns,
            tuple(id(monster) for monster in hostiles),
        )
        cached = self._threat_prediction_memo.get(memo_key)
        if cached is not None and cached[0] is snapshot:
            return cached[1]
        total = 0
        operational_total = 0
        expected_total = 0.0
        monsters = []
        for monster in hostiles:
            actions = self._monster_actions(monster.speed, snapshot.player.speed, turns)
            melee = 0
            expected_melee = 0.0
            path_distance = self._monster_path_distance(snapshot, monster.position)
            knowledge = self._monrace_knowledge.get(monster.race_id)
            never_moves = bool(
                knowledge is not None and "NEVER_MOVE" in knowledge.flags
            )
            cannot_approach = not self._monster_can_approach(snapshot, monster)
            can_teleport_player_to = bool(
                knowledge is not None
                and "TELE_TO" in knowledge.abilities
                and self._has_line_of_fire(
                    snapshot, monster.position, snapshot.player.position
                )
            )
            teleport_to_probability = 0.0
            if can_teleport_player_to and knowledge is not None:
                teleport_selection = ability_selection_probabilities(
                    knowledge,
                    SpellSelectionContext(distance=max(1, monster.distance)),
                )
                teleport_to_probability = (
                    knowledge.spell_frequency
                    / 100.0
                    * teleport_selection.get("TELE_TO", 0.0)
                )
            self_destructs_on_melee = bool(
                knowledge is not None
                and any(blow.method == "EXPLODE" for blow in knowledge.blows)
            )
            if path_distance is not None and monster.max_melee_damage > 0:
                movement_attacks = (
                    actions
                    if path_distance <= 1
                    else 0
                    if never_moves or cannot_approach
                    else max(0, actions - (path_distance - 1))
                )
                teleport_to_attacks = (
                    max(0, actions - 1)
                    if path_distance > 1 and can_teleport_player_to
                    else 0
                )
                attacks = max(movement_attacks, teleport_to_attacks)
                expected_teleport_to_attacks = sum(
                    (1.0 - teleport_to_probability) ** (action - 1)
                    * teleport_to_probability
                    * (actions - action)
                    for action in range(1, actions + 1)
                )
                expected_attacks = max(
                    float(movement_attacks), expected_teleport_to_attacks
                )
                if self_destructs_on_melee:
                    attacks = min(attacks, 1)
                    expected_attacks = min(expected_attacks, 1.0)
                if knowledge is not None and knowledge.blows:
                    melee_per_action = sum(
                        self._maximum_melee_blow_damage(snapshot, blow.effect, blow.dice_num * blow.dice_sides)
                        for blow in knowledge.blows
                    )
                    expected_melee_per_action = sum(
                        self._maximum_melee_blow_damage(snapshot, blow.effect, blow.dice_num * blow.dice_sides)
                        * self._melee_hit_probability(
                            blow.effect, knowledge.level, snapshot.player.ac, monster.stunned
                        )
                        for blow in knowledge.blows
                    )
                    melee = attacks * melee_per_action
                    expected_melee = expected_attacks * expected_melee_per_action
                else:
                    melee = attacks * monster.max_melee_damage
                    expected_melee = expected_attacks * monster.max_melee_damage
            ranged = 0
            operational_ranged = 0
            expected_ranged = 0.0
            cause_predictions = []
            aggregate_ranged = None
            if monster.max_ranged_damage > 0 and self._has_line_of_fire(
                snapshot, monster.position, snapshot.player.position
            ):
                if knowledge is not None and knowledge.abilities:
                    flags = frozenset(
                        flag
                        for ability, flag in RESIST_FLAG_BY_ABILITY.items()
                        if ability in snapshot.player.abilities
                    )
                    maximum_by_ability = {
                        ability: damage
                        for ability in knowledge.abilities
                        if (
                            damage := maximum_ability_hp_damage(
                                ability,
                                knowledge,
                                flags=flags,
                                player_hp=snapshot.player.hp,
                                blind=snapshot.player.blind,
                            )
                        ) is not None
                    }
                    ranged = actions * max(maximum_by_ability.values(), default=0)
                    selection_context = SpellSelectionContext(
                        distance=max(1, monster.distance)
                    )
                    selection = ability_selection_probabilities(
                        knowledge, selection_context
                    )
                    for ability, maximum in maximum_by_ability.items():
                        if ability.startswith("CAUSE_"):
                            cause = cause_damage_percentile(
                                ability,
                                knowledge,
                                actions=actions,
                                selection_probability=selection.get(ability, 0.0),
                                saving_skill=snapshot.player.saving_skill,
                            )
                            cause_predictions.append(
                                {
                                    "ability": cause.ability,
                                    "per_action_probability": cause.per_action_probability,
                                    "successful_casts_p95": cause.successful_casts,
                                    "damage_per_cast_p95": cause.damage_per_cast,
                                    "damage_p95": cause.total_damage,
                                }
                            )
                    aggregate_ranged = self._aggregate_ranged_percentile(
                        knowledge,
                        actions=actions,
                        selection_context=selection_context,
                        selection_probabilities=selection,
                        flags=flags,
                        player_hp=snapshot.player.hp,
                        blind=snapshot.player.blind,
                        saving_skill=snapshot.player.saving_skill,
                    )
                    operational_ranged = aggregate_ranged.total_damage
                    expected_per_spell = sum(
                        probability
                        * (
                            expected_ability_hp_damage(
                                ability,
                                knowledge,
                                flags=flags,
                                player_hp=snapshot.player.hp,
                                blind=snapshot.player.blind,
                                saving_skill=snapshot.player.saving_skill,
                            )
                            or 0.0
                        )
                        for ability, probability in selection.items()
                    )
                    expected_ranged = (
                        actions * knowledge.spell_frequency / 100.0 * expected_per_spell
                    )
                else:
                    ranged = actions * monster.max_ranged_damage
                    operational_ranged = ranged
                    expected_ranged = float(ranged)
            contribution = max(melee, ranged)
            operational_contribution = max(melee, operational_ranged)
            expected_contribution = max(expected_melee, expected_ranged)
            total += contribution
            operational_total += operational_contribution
            expected_total += expected_contribution
            monsters.append(
                {
                    "name": monster.name,
                    "race_id": monster.race_id,
                    "position": {"y": monster.position.y, "x": monster.position.x},
                    "distance": monster.distance,
                    "path_distance": path_distance,
                    "speed": monster.speed,
                    "asleep": monster.asleep,
                    "stunned": monster.stunned,
                    "confused": monster.confused,
                    "fearful": monster.fearful,
                    "can_summon": monster.can_summon,
                    "can_multiply": monster.can_multiply,
                    "never_moves": never_moves,
                    "can_teleport_player_to": can_teleport_player_to,
                    "teleport_to_probability_per_action": teleport_to_probability,
                    "self_destructs_on_melee": self_destructs_on_melee,
                    "actions": actions,
                    "max_melee_damage": monster.max_melee_damage,
                    "max_ranged_damage": monster.max_ranged_damage,
                    "melee_prediction": melee,
                    "ranged_prediction": ranged,
                    "contribution": contribution,
                    "operational_ranged_prediction": operational_ranged,
                    "operational_ranged_probability_any_damage": (
                        aggregate_ranged.probability_any_damage
                        if aggregate_ranged is not None
                        else 0.0
                    ),
                    "operational_ranged_floor_applied": (
                        aggregate_ranged.floor_applied
                        if aggregate_ranged is not None
                        else False
                    ),
                    "operational_contribution": operational_contribution,
                    "cause_predictions": cause_predictions,
                    "expected_melee_prediction": expected_melee,
                    "expected_ranged_prediction": expected_ranged,
                    "expected_contribution": expected_contribution,
                }
            )
        result = {
            "turns": turns,
            "total": total,
            "operational_total": operational_total,
            "expected_total": ceil(expected_total),
            "monsters": monsters,
        }
        if len(self._threat_prediction_memo) >= THREAT_PREDICTION_MEMO_LIMIT:
            self._threat_prediction_memo.clear()
        self._threat_prediction_memo[memo_key] = (snapshot, result)
        return result
    @staticmethod
    def _melee_hit_probability(
        effect: str, monster_level: int, player_ac: int, stunned: bool
    ) -> float:
        effect_power = {
            "NONE": 0,
            "HURT": 60,
            "POISON": 5,
            "UN_BONUS": 20,
            "UN_POWER": 15,
            "EAT_GOLD": 5,
            "EAT_ITEM": 5,
            "EAT_FOOD": 5,
            "EAT_LITE": 5,
            "ACID": 0,
            "ELEC": 10,
            "FIRE": 10,
            "COLD": 10,
            "BLIND": 2,
            "CONFUSE": 10,
            "TERRIFY": 10,
            "PARALYZE": 2,
            "LOSE_ALL": 2,
            "SHATTER": 60,
            "DISEASE": 5,
            "TIME": 5,
            "EXP_VAMP": 5,
            "DR_MANA": 5,
            "SUPERHURT": 60,
        }.get(effect, 0)
        accuracy = max(1, effect_power + monster_level * 3)
        if stunned:
            accuracy //= 2
        threshold = player_ac * 3 // 4
        normal_hit = max(0.0, (accuracy - threshold) / accuracy)
        return 0.05 + 0.90 * normal_hit
    def _melee_swarm_combat_key(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        adjacent: list[MonsterState],
    ) -> str | None:
        """Order ranged repelling, re-arming, and choke combat for melee swarms."""
        converging = [
            monster
            for monster in hostiles
            if not monster.asleep
            and self._monster_can_approach(snapshot, monster)
            and (
                monster.distance <= 1
                or (
                    monster.can_multiply
                    and monster.distance <= SWARM_LOOKAHEAD
                )
                or (
                    (previous := self._swarm_previous_distances.get(monster.index))
                    is not None
                    and previous[1].distance_to(snapshot.player.position)
                    > monster.position.distance_to(snapshot.player.position)
                )
            )
        ]
        melee_hostiles = [
            monster for monster in converging if monster.max_ranged_damage <= 0
        ]
        swarm = len(melee_hostiles) >= 2
        mining = (
            self._fundraising_mode in {"mine", "scavenge"}
            and snapshot.floor_key[0] == DUNGEON_YEEK_CAVE
            and snapshot.dungeon_level == 1
            and self._equipped_digging_tool(snapshot) is not None
        )
        if not swarm and not (mining and converging):
            return None
        # Approved and runtime quest targeting has its own reviewed positioning
        # and race-priority semantics; do not steal those engagements.
        if (
            self._active_fixed_quest_id(snapshot) is not None
            or self._active_kill_quest_id(snapshot) is not None
        ):
            return None
        # A ranged member can attack through the queue, so preserve the old
        # flee/disengage behavior rather than treating this as a safe choke.
        if swarm and any(monster.max_ranged_damage > 0 for monster in converging):
            return None

        if not adjacent:
            ranged = self._ranged_attack_key(snapshot, converging, adjacent)
            if ranged is not None:
                return ranged
        if (
            self._mining_combat_contact_streak >= MINING_COMBAT_CONTACT_LIMIT
            and self._equipped_digging_tool(snapshot) is not None
        ):
            restore = self._restore_mining_combat_hand_key(
                snapshot, "melee:restore-weapon"
            )
            if restore is not None:
                return restore

        if not swarm:
            return None
        if self._predicted_damage(snapshot, hostiles, turns=3) >= (
            snapshot.player.hp * ENGAGEMENT_AVOID_DAMAGE_RATIO
        ):
            return None
        if self._should_flee(snapshot, hostiles, adjacent):
            # The ordinary flee branch now prefers narrow cells, preserving the
            # covered retreat line instead of stepping back into the room.
            return None
        openness = self._open_neighbor_count(snapshot, snapshot.player.position)
        if openness > SUMMONER_CHOKE_NEIGHBORS - 1:
            route = self._validated_choke_route(snapshot, melee_hostiles)
            if route is not None:
                if (
                    self._breeder_choke_attempt_ended_floor == snapshot.floor_key
                    and self._engagement_breeder_population(snapshot)
                ):
                    self._returning_to_town = True
                    self._last_return_trigger = "breeder-choke-attempt-ended"
                    exit_key = self._return_to_town_key(
                        snapshot,
                        hostiles,
                        allow_recall=self._fundraising_mode != "mine",
                    )
                    if exit_key is not None:
                        return exit_key
                    return None
                destination, step = route
                self._choke_engagement_plan = ChokeEngagementPlan(
                    floor=snapshot.floor_key,
                    phase="reposition",
                    destination=destination,
                    covered_retreat_direction=(
                        step.y - snapshot.player.position.y,
                        step.x - snapshot.player.position.x,
                    ),
                    trigger_last_seen={
                        monster.index: monster.position for monster in melee_hostiles
                    },
                    start_exp=snapshot.player.exp,
                    start_gold=snapshot.player.gold,
                    start_breeder_count=len(
                        self._engagement_breeder_population(snapshot)
                    ),
                    last_player_hp=snapshot.player.hp,
                    closest_destination_distance=(
                        snapshot.player.position.distance_to(destination)
                    ),
                    last_movement=(snapshot.player.position, step),
                )
                self._inherit_choke_outcome_budget(
                    snapshot, self._choke_engagement_plan
                )
                self.last_reason = "melee:choke"
                return self._step_toward(snapshot, step)

        if openness <= SUMMONER_CHOKE_NEIGHBORS - 1:
            if not self._choke_plan_active(snapshot):
                if (
                    self._breeder_choke_attempt_ended_floor == snapshot.floor_key
                    and self._engagement_breeder_population(snapshot)
                ):
                    self._returning_to_town = True
                    self._last_return_trigger = "breeder-choke-attempt-ended"
                    exit_key = self._return_to_town_key(
                        snapshot,
                        hostiles,
                        allow_recall=self._fundraising_mode != "mine",
                    )
                    if exit_key is not None:
                        return exit_key
                    return None
                self._choke_engagement_plan = ChokeEngagementPlan(
                    floor=snapshot.floor_key,
                    phase="hold",
                    destination=snapshot.player.position,
                    covered_retreat_direction=(0, 0),
                    trigger_last_seen={
                        monster.index: monster.position for monster in melee_hostiles
                    },
                    start_exp=snapshot.player.exp,
                    start_gold=snapshot.player.gold,
                    start_breeder_count=len(
                        self._engagement_breeder_population(snapshot)
                    ),
                    last_player_hp=snapshot.player.hp,
                    closest_destination_distance=0,
                )
                self._inherit_choke_outcome_budget(
                    snapshot, self._choke_engagement_plan
                )
            if adjacent and not snapshot.player.afraid:
                self.last_reason = "melee:choke"
                return self._direction_key(
                    snapshot.player.position, self._weakest(adjacent).position
                )
            self.last_reason = "melee:choke-hold"
            return WAIT_KEY
        return None
    def _choke_plan_active(self, snapshot: Snapshot) -> bool:
        plan = self._choke_engagement_plan
        return bool(
            plan is not None
            and plan.floor == snapshot.floor_key
            and plan.phase in {"reposition", "validate", "hold"}
        )
    def _choke_outcome_key(self, plan: ChokeEngagementPlan) -> Position:
        """Identify the tactical engagement independently of monster churn."""
        return plan.destination
    def _choke_outcome_marker(
        self, snapshot: Snapshot, trigger_count: int, breeder_count: int
    ) -> tuple[int, ...]:
        """Return monotone, observable benefits of continuing this engagement."""
        return (
            snapshot.player.exp,
            snapshot.player.gold,
            -trigger_count,
            -breeder_count,
            len(self._remembered_marked_t),
            snapshot.player.hp,
        )
    def _choke_engagement_key(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        adjacent: list[MonsterState],
    ) -> str | None:
        plan = self._choke_engagement_plan
        if not self._choke_plan_active(snapshot) or plan is None:
            return None
        plan.decisions_consumed += 1
        visible_triggers = [
            monster for monster in hostiles if monster.index in plan.trigger_last_seen
        ]
        for monster in visible_triggers:
            plan.trigger_last_seen[monster.index] = monster.position
        if visible_triggers:
            plan.sight_loss_decisions = 0
        else:
            plan.sight_loss_decisions += 1
        if any(monster.max_ranged_damage > 0 for monster in visible_triggers):
            self._release_choke_plan("ranged-threat")
            return None
        breeder_population = self._engagement_breeder_population(snapshot)
        self._spend_choke_outcome_budget(
            snapshot, plan, len(visible_triggers), len(breeder_population)
        )
        if len(breeder_population) > plan.start_breeder_count:
            immobile_multipliers = bool(breeder_population) and all(
                monster.can_multiply
                and (knowledge := self._monrace_knowledge.get(monster.race_id))
                is not None
                and "NEVER_MOVE" in knowledge.flags
                for monster in breeder_population
            )
            self._release_choke_plan(
                "immobile-breeder-growth"
                if immobile_multipliers
                else "swarm-growth"
            )
            return None
        if (
            snapshot.player.hp_ratio < FLEE_HP_RATIO
            or self._predicted_damage(snapshot, hostiles, turns=3)
            >= snapshot.player.hp * ENGAGEMENT_AVOID_DAMAGE_RATIO
            or self._should_flee(snapshot, hostiles, adjacent)
        ):
            self._release_choke_plan("hp-authority")
            return None
        if (
            (
                snapshot.player.exp > plan.start_exp
                or snapshot.player.gold > plan.start_gold
            )
            and len(visible_triggers) < len(plan.trigger_last_seen)
        ):
            self._release_choke_plan("kill-progress")
            return None
        # Holding blind is dead time in which an unseen swarm can multiply;
        # the choke strategy promises only a bounded hold.
        if plan.sight_loss_decisions > EXTENDED_STUCK_WINDOW:
            self._release_choke_plan("sight-loss-bound")
            return None
        if snapshot.player.position != plan.destination:
            plan.phase = "reposition"
            destination_distance = snapshot.player.position.distance_to(
                plan.destination
            )
            if destination_distance < plan.closest_destination_distance:
                plan.closest_destination_distance = destination_distance
                plan.no_progress_decisions = 0
            else:
                plan.no_progress_decisions += 1
            if plan.decisions_consumed >= EXTENDED_STUCK_WINDOW:
                self._release_choke_plan("engagement-stall-bound")
                return None
            step = self._nearest_goal_step(
                snapshot, lambda grid: grid.position == plan.destination
            )
            if step is None:
                self._release_choke_plan("destination-unreachable")
                return None
            plan.last_movement = (snapshot.player.position, step)
            self.last_reason = "melee:choke-reposition"
            return self._step_toward(snapshot, step)
        plan.phase = "validate"
        here = snapshot.grid_at(plan.destination)
        if (
            here is None
            or not here.currently_observed
            or self._open_neighbor_count(snapshot, plan.destination)
            > SUMMONER_CHOKE_NEIGHBORS - 1
        ):
            self._release_choke_plan("destination-invalid")
            return None
        plan.phase = "hold"
        plan.last_player_hp = snapshot.player.hp
        if plan.no_progress_decisions >= COMBAT_OUTCOME_WINDOW:
            self._release_choke_plan(
                "breeder-outcome-bound"
                if breeder_population
                else "engagement-stall-bound"
            )
            return None
        if not adjacent:
            ranged = self._ranged_attack_key(snapshot, visible_triggers, adjacent)
            if ranged is not None:
                return ranged
        if (
            self._mining_combat_contact_streak >= MINING_COMBAT_CONTACT_LIMIT
            and self._equipped_digging_tool(snapshot) is not None
        ):
            restore = self._restore_mining_combat_hand_key(
                snapshot, "melee:restore-weapon"
            )
            if restore is not None:
                return restore
        if adjacent and not snapshot.player.afraid:
            self.last_reason = "melee:choke"
            return self._direction_key(
                snapshot.player.position, self._weakest(adjacent).position
            )
        self.last_reason = "melee:choke-hold"
        return WAIT_KEY
    def _breeder_breakthrough_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        """Leave upward once extermination on this floor proved impossible.

        The strong/weak breeder distinction governs whether the latch is SET
        (in _update_combat_outcome), not whether the escape executes: the
        latch means "this population cannot be exterminated, leave", and a
        weak-breeder stalemate arms it too.  Refusing to act without a strong
        breeder left the bot oscillating in a monster-sealed pocket until the
        loop guard stopped it (Forest 20F, 2026-08-03 16:16), so once the
        latch names this floor the breakthrough owns the decision.
        """
        if self._breeder_breakthrough_floor != snapshot.floor_key:
            return None
        active_quest = self._active_quest_id(snapshot)
        if (
            self._fundraising_mode != "mine"
            and active_quest is None
            and not self._emergency_return_active
            and not snapshot.player.blind
            and not snapshot.player.confused
        ):
            pending_recall = self._dungeon_recall_confirmation_key(snapshot)
            if pending_recall is not None:
                return pending_recall
            if snapshot.player.recalling:
                self.last_reason = "breeder-breakthrough:wait-recall"
                return WAIT_KEY
            recall = self._find_recall_scroll(snapshot)
            if recall is not None and self._can_read_scrolls(snapshot):
                self._returning_to_town = True
                self.last_reason = "breeder-breakthrough:recall"
                return self._read_dungeon_recall_scroll_key(snapshot, recall)
        if self._fundraising_mode in {"mine", "scavenge"} and not any(
            monster.can_multiply
            and not self._is_weak_breeder(snapshot, monster)
            for monster in hostiles
        ):
            # The latched fundraising floor-exit later in _decide runs its
            # combat re-equip first (the digger re-arm a breakthrough claim
            # here would strip), then _finish_mining_floor.  That exit is not
            # total: its terminal is an absorbing WAIT, so the _decide site
            # backstops it with _breeder_breakthrough_escape_key before the
            # WAIT can be posted.  Every other fundraising decision stays
            # byte-for-byte.
            return None
        return self._breeder_breakthrough_escape_key(snapshot)
    def _breeder_walkout_active(self, snapshot: Snapshot) -> bool:
        fled = self._breeder_fled_floor
        return (
            fled is not None
            and not snapshot.in_town
            and snapshot.floor_key[0] == fled[0]
            and snapshot.dungeon_level < fled[1]
        )
    def _breeder_breakthrough_escape_key(self, snapshot: Snapshot) -> str | None:
        """The breakthrough's own exits: ascend, route upstairs, or discover.

        Returns None only when neither an up-stairs nor any live frontier is
        remembered: the floor is exhausted, and the ordinary navigation
        ladder already owns that state (probe, secret-wall search, stuck
        stair-seeking, nav-exhausted floor departure) — never an unbounded
        WAIT here.
        """
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and self._is_upstairs_target(here):
            if self._active_quest_id(snapshot) is None:
                self._breeder_fled_floor = snapshot.floor_key
                self._returning_to_town = True
            self._defer_descent(snapshot)
            self.last_reason = "breeder-breakthrough:ascend"
            return UP_STAIRS_KEY
        step = self._breeder_breakthrough_step(snapshot)
        seek_reason = "breeder-breakthrough:seek-upstairs"
        if step is None:
            # No remembered route reaches a known up-stairs (or none is known
            # yet).  The exit is discovery: route through the swarm to the
            # nearest remembered tile touching unknown terrain.  Liveness is
            # monotone: an arrival either reveals tiles (the remembered map
            # grows, bounded by the floor) or retires that frontier from the
            # candidate set (which strictly shrinks, emptying into the
            # exhausted-floor handoff below).
            step = self._breeder_breakthrough_frontier_step(snapshot)
            seek_reason = "breeder-breakthrough:seek-frontier"
        if step is not None:
            grid = snapshot.grid_at(step)
            self.last_reason = (
                "breeder-breakthrough:clear-escape-path"
                if grid is not None and grid.has_monster
                else seek_reason
            )
            return self._step_toward(snapshot, step)
        return None
    def _breeder_route_traversable(
        self, snapshot: Snapshot, neighbor: Position, dy: int, dx: int
    ) -> bool:
        """Remembered-terrain traversability for breakthrough routing.

        A monster standing on a known enterable cell counts: on a latched
        floor it is an escape-route blocker to clear by attacking, not a
        wall.  Ordinary routing deliberately excludes occupied cells, which
        is exactly what blinds it when the swarm seals the pocket.
        """
        grid = snapshot.grid_at(neighbor)
        key = (neighbor.y, neighbor.x)
        return (
            key in self._remembered_floor_t
            or key in self._remembered_door_t
            or (
                (dy == 0 or dx == 0)
                and key in self._remembered_rubble_t
            )
            or (
                grid is not None
                and grid.known
                and grid.has_monster
                and grid.enterable
            )
        )
    def _breeder_breakthrough_step(
        self, snapshot: Snapshot
    ) -> Position | None:
        """Route upstairs on remembered terrain, preferring no retreat."""
        start = snapshot.player.position
        goal = self._nearest_upstairs(snapshot)
        if goal is None:
            return None

        def route(monotone: bool) -> Position | None:
            seen = {start}
            queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
            while queue:
                position, first_step = queue.popleft()
                if position == goal:
                    return first_step
                for dy, dx in NEIGHBOR_OFFSETS:
                    neighbor = Position(position.y + dy, position.x + dx)
                    if neighbor in seen or (
                        monotone
                        and neighbor.distance_to(goal) > position.distance_to(goal)
                    ):
                        continue
                    if not self._breeder_route_traversable(
                        snapshot, neighbor, dy, dx
                    ):
                        continue
                    seen.add(neighbor)
                    queue.append(
                        (neighbor, neighbor if first_step is None else first_step)
                    )
            return None

        return route(monotone=True) or route(monotone=False)
    def _breeder_breakthrough_frontier_step(
        self, snapshot: Snapshot
    ) -> Position | None:
        """Route through the swarm to the nearest remembered frontier tile.

        Same traversability as the up-stairs route — monsters on the way are
        escape-route blockers, not walls — because the very swarm that armed
        the latch is what seals the pocket; ordinary exploration refuses to
        path through occupied cells and goes blind exactly here.

        Liveness rests on the emitter contract, not on handler bookkeeping.
        A CAPABLE arrival — player not blind (bot-json-output.cpp:118 emits
        every non-REMEMBER grid unknown while blind), own square carrying
        the emitted `lite` flag, which is grid.is_lite() = CAVE_LITE only
        (bot-json-output.cpp:191), i.e. light radius >= 1 — reveals every
        adjacent in-bounds grid in that same snapshot: update_lite lights
        all eight neighbours unconditionally (specific-object/torch.cpp:
        159-175), the emitter iterates the whole floor with perceivability
        as its only filter (make_nearby_grids_json), and a wall beside the
        player's floor square always passes is_revealed_wall
        (display-map.cpp:92 — it has a non-wall neighbour).  So a capable
        arrival makes the goal simply stop being a frontier: the remembered
        map grew and the tile drops out of the candidate set by itself.  An
        INCAPABLE arrival (blind, or lampless — including squares visible
        only through transient CAVE_MNLT monster light, which never sets
        the lite flag, floor-info.cpp:690-719) legitimately reveals
        nothing, and the frontier must survive for a later capable visit;
        the repair is a real action owned by rungs above this handler in
        _decide (_emergency_item's status-cure quaff for blindness,
        _darkness_recovery_key's refuel/wield for light), and while
        neither has materials the pre-existing FRONTIER_EXHAUST_VISITS
        bookkeeping inside _is_remembered_frontier bounds repeated visits,
        so the candidate set still empties into the exhausted-floor
        handoff.
        """
        start = snapshot.player.position
        seen = {start}
        queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
        while queue:
            position, first_step = queue.popleft()
            if (
                position != start
                and first_step is not None
                and self._is_remembered_frontier(snapshot, position)
            ):
                return first_step
            for dy, dx in NEIGHBOR_OFFSETS:
                neighbor = Position(position.y + dy, position.x + dx)
                if neighbor in seen:
                    continue
                if not self._breeder_route_traversable(
                    snapshot, neighbor, dy, dx
                ):
                    continue
                seen.add(neighbor)
                queue.append(
                    (neighbor, neighbor if first_step is None else first_step)
                )
        return None
    def _remember_swarm_distances(self, snapshot: Snapshot) -> None:
        """Retain one observation so awake monsters moving closer can converge."""
        floor_key = getattr(snapshot, "floor_key", None)
        visible_monsters = getattr(snapshot, "visible_monsters", ())
        if self._swarm_distance_floor != floor_key:
            self._swarm_distance_floor = floor_key
            self._swarm_previous_distances.clear()
        self._swarm_previous_distances = {
            monster.index: (monster.distance, monster.position)
            for monster in visible_monsters
            if monster.hostile and not monster.asleep
        }
    @staticmethod
    def _has_line_of_fire(snapshot: Snapshot, origin: Position, target: Position) -> bool:
        y0, x0 = origin.y, origin.x
        y1, x1 = target.y, target.x
        dy, dx = abs(y1 - y0), abs(x1 - x0)
        sy, sx = (1 if y0 < y1 else -1), (1 if x0 < x1 else -1)
        error = dx - dy
        while (y0, x0) != (y1, x1):
            twice = error * 2
            if twice > -dy:
                error -= dy
                x0 += sx
            if twice < dx:
                error += dx
                y0 += sy
            if (y0, x0) == (y1, x1):
                return True
            grid = snapshot.grid_at(Position(y0, x0))
            if grid is None or not grid.allows_los:
                return False
        return True
    def _flee_step(self, snapshot: Snapshot, hostiles: list[MonsterState]) -> Position | None:
        # Material-engagement retreat records each abandoned square so later
        # navigation cannot walk straight back into the same threat.  Retreat
        # itself must honor that veto too: otherwise the locally farthest
        # neighbor can be the square just abandoned, producing a small cycle at
        # the edge of a faster monster's visibility (live Angband 30F incident,
        # 2026-07-23).
        if not hostiles:
            return None
        walkable = self._walkable_neighbors(snapshot, snapshot.player.position)
        candidates = [
            candidate
            for candidate in walkable
            if candidate not in self._engagement_avoid_cells
        ]
        if not candidates:
            # Fully boxed in by our own accumulated avoid-cells (a stationary
            # status monster in a narrow passage rings every neighbour). Waiting
            # here forever until the loop guard stops the bot is worse than
            # stepping onto a previously-vetoed square, so relax the veto to the
            # least-bad walkable neighbour and keep the retreat moving.
            candidates = walkable
        if not candidates:
            return None

        origin_distance = min(
            snapshot.player.position.distance_to(monster.position)
            for monster in hostiles
        )
        candidates = [
            candidate
            for candidate in candidates
            if min(candidate.distance_to(monster.position) for monster in hostiles)
            > origin_distance
        ]
        if not candidates:
            return None

        def score(pos: Position) -> tuple[int, int, int, int, int]:
            nearest = min(pos.distance_to(m.position) for m in hostiles)
            grid = snapshot.grids.get(pos)
            unsafe = 1 if (grid and grid.unsafe) else 0
            # Known traps are excluded from the routing index before this score;
            # retain the ordering defensively for alternate GridState sources.
            trap = 1 if (grid and grid.trap) else 0
            return (
                nearest,
                -trap,
                -unsafe,
                -self._open_neighbor_count(snapshot, pos),
                -self._visit_counts[pos],
            )

        return max(candidates, key=score)
    def _hunt_step(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        *,
        allow_cooling: bool = True,
    ) -> Position | None:
        player = snapshot.player
        if self._hunt_progress_floor != snapshot.floor_key:
            self._hunt_progress_floor = snapshot.floor_key
            self._hunt_progress.clear()
            self._hunt_target_identities.clear()
            self._hunt_cooled_targets.clear()
            self._hunt_cooling_exempt_targets.clear()
        if player.hp_ratio < HUNT_HP_RATIO or not hostiles:
            return None
        if (
            len(hostiles) > HUNT_MAX_HOSTILES
            and self._predicted_damage(snapshot, hostiles, 3)
            >= snapshot.player.hp * ENGAGEMENT_AVOID_DAMAGE_RATIO
        ):
            return None

        def easy(m: MonsterState) -> bool:
            if m.distance > HUNT_RANGE:
                return False
            # Do not deliberately close with a sleeper that the material-threat
            # gate will immediately flee from after one step.  That disagreement
            # produced a two-cell hunt/reposition loop on Yeek Cave 5F.  Judge
            # the intended engagement at melee range, where every remaining
            # monster action can become an attack, instead of only at its current
            # (temporarily safe) distance.
            if self._material_melee_engagement(snapshot, m):
                return False
            if m.asleep or m.fearful:
                return True
            # Avoid poking things that clearly outclass us.
            if m.max_hp > player.max_hp and m.speed > player.speed + 10:
                return False
            return m.max_hp <= max(player.max_hp, 1)

        identities: dict[int, tuple[int, int, Position]] = {}
        for monster in hostiles:
            identity = self._hunt_target_identities.get(monster.index)
            if identity is None or identity[1] != monster.race_id:
                identity = (monster.index, monster.race_id, monster.position)
                self._hunt_target_identities[monster.index] = identity
            identities[monster.index] = identity
        if not allow_cooling:
            self._hunt_cooling_exempt_targets.update(identities.values())

        targets = [
            m for m in hostiles
            if easy(m) and identities[m.index] not in self._hunt_cooled_targets
        ]
        if not targets:
            return None
        cooled_now = False
        for monster in targets:
            identity = identities[monster.index]
            progress = self._hunt_progress.get(identity)
            if progress is None:
                progress = {
                    "steps": 0,
                    "best_distance": monster.distance,
                    "exp": player.exp,
                    "hp": monster.hp,
                    "decision": self._decision_sequence,
                }
                self._hunt_progress[identity] = progress
            elif progress["decision"] != self._decision_sequence:
                made_progress = (
                    monster.hp < progress["hp"]
                    or player.exp > progress["exp"]
                    or monster.distance < progress["best_distance"]
                )
                progress["steps"] = 0 if made_progress else progress["steps"] + 1
                progress["best_distance"] = min(
                    progress["best_distance"], monster.distance
                )
                progress["exp"] = player.exp
                progress["hp"] = monster.hp
                progress["decision"] = self._decision_sequence
            if (
                allow_cooling
                and identity not in self._hunt_cooling_exempt_targets
                and progress["steps"] >= HUNT_RANGE
            ):
                self._hunt_cooled_targets.add(identity)
                self._hunt_progress.pop(identity, None)
                cooled_now = True
        if cooled_now:
            self._pending_hunt_report = "hunt:abandoned-no-damage-no-closure"
            targets = [
                monster for monster in targets
                if identities[monster.index] not in self._hunt_cooled_targets
            ]
            if not targets:
                return None
        target = min(targets, key=lambda m: m.distance)
        step = self._nearest_goal_step(
            snapshot, lambda g: g.position.distance_to(target.position) <= 1
        )
        if step in self._engagement_avoid_cells:
            return None
        return step
