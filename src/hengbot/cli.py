from __future__ import annotations

import argparse
import faulthandler
import json
import os
import sys
import time
from collections import deque
from pathlib import Path
from typing import Iterable

from hengbot.model import MissingMonraceKnowledgeError, parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.dungeon_knowledge import find_dungeon_definitions, load_dungeon_knowledge
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import find_quest_strategies, load_quest_strategies
from hengbot.town_maps import TownMap, find_outpost_map, find_town_map, parse_town_map
from hengbot.wilderness_map import find_wilderness_definition, load_wilderness_map
from hengbot.wait_telemetry import WaitTelemetry
from hengbot.policy import (
    FUNDRAISING_START_GOLD,
    PACK_CAPACITY,
    ConservativePolicy,
    TOWN_TRAVEL_STALL_LIMIT,
    TOWN_TRAVEL_TURN_STALL_LIMIT,
    required_depth_gates,
)


# Character posted to the window to dismiss a message / "-more-" prompt that the
# game shows without emitting a new bot snapshot (e.g. the level feeling printed
# right after descending). Escape (0x1B) clears any such prompt and is a harmless
# no-op if the game has already returned to the command loop.
NUDGE_KEY = "\x1b"

# After issuing a rest, the game runs many turns without emitting a snapshot;
# hold off the stall nudge this long so it does not cut the rest short.
REST_STALL_GRACE = 20.0

# Emit a live Python stack when one follow-loop iteration stops making progress.
# Re-arming at the top of every iteration means normal polling never reaches the
# deadline; a stuck read/parse/decision/send path repeats the dump once a minute.
# Bounded equipment optimization is intentionally allowed 25 seconds. Leave a
# margin so a normal optimization timeout cannot itself produce a false hang
# dump; truly stuck work still emits a diagnostic shortly afterwards.
DECISION_WATCHDOG_SECONDS = 90

# The dump is the bot's external liveness signal.  The CLI owns wall-clock time;
# policy only receives a deterministic request and waits for a safe filler turn.
DUMP_INTERVAL_SECONDS = 180


def _request_due_dump(policy, now: float, next_dump_at: float) -> float:
    """Deliver one elapsed wall-clock request and return its next deadline."""
    if now >= next_dump_at:
        policy.request_character_dump()
        return now + DUMP_INTERVAL_SECONDS
    return next_dump_at


def _arm_decision_watchdog() -> None:
    faulthandler.cancel_dump_traceback_later()
    faulthandler.dump_traceback_later(
        DECISION_WATCHDOG_SECONDS,
        repeat=True,
        file=sys.stderr,
    )
# Measured Release-build serialization is ~250 ms even for a 4.5 MB town
# snapshot. This long grace is reserved for native travel, which legitimately
# runs many turns without a snapshot. Ordinary shop commands must fall back to
# the configured stall timeout; giving every rejected Home/store command twelve
# quiet seconds made a single stale slot look like a very long deliberate wait.
COMMAND_RESPONSE_GRACE = 12.0

# When the character dies, the game leaves the command loop for the tombstone /
# death-info / high-score screens (close_game) and never emits another snapshot;
# Escape nudges cannot revive it. After this many fruitless nudges in a row we
# treat it as a terminal screen and drive the shutdown so the game quit()s.
TERMINAL_NUDGE_LIMIT = 8
# Keys that march through close_game: Escape clears the tombstone and aborts the
# death-info dump, "n" answers the NO_ESCAPE "stand by for score registration?"
# prompt, Return confirms anything else. Repeated to cover every screen.
DEATH_EXIT_KEYS = ("\x1b", "n", "\r")
DEATH_EXIT_ROUNDS = 8

# Every tenth level Hengband blocks outside the command loop and asks for a stat
# (a-f), then confirmation; the screen ignores Escape and no JSON snapshot is
# emitted while it is up. After two harmless Esc nudges, alternate the stat
# choice (Strength, for the warrior bot) with a confirm — alternating retries
# both keys, so a single lost keystroke cannot strand the game there. The gate
# accepts levels ending in 8 or 9: one strong kill can jump two levels (8→10),
# which still lands on the stat screen while our last snapshot said clvl 8.
LEVEL_UP_STAT_CHOICE = "a"
LEVEL_UP_RECOVERY_START = 2

# Loop / stuck detection. If the character stays confined to a handful of tiles
# on a single floor for this many consecutive decisions, it is looping — an
# exploration oscillation the policy's own anti-stuck guards (visit penalty,
# probe, livelock breaker) could not break (e.g. a 2-cycle between two tiles that
# gate the only routes to both frontiers, where the keys alternate so the
# same-key livelock guard never trips). Rather than flail forever, STOP the bot
# so the situation can be investigated from the preserved game state.
LOOP_WINDOW = 40
# A live random-quest exploration failure cycled through six cells for more
# than 130 decisions.  Four cells was too narrow to recognize that confined
# hexagonal route as the same class of non-progress loop.
LOOP_MAX_DISTINCT = 6
# Multipliers repeatedly appear and disappear between melee turns as their pack
# shifts around the player. Give that productive fight longer to resolve, while
# retaining a finite guard for a genuinely unwinnable engagement.
MULTIPLIER_COMBAT_LOOP_WINDOW = 80
MULTIPLIER_COMBAT_GRACE = 10
STARVING_STOP_LIMIT = 60


def _advance_starving_streak(
    streak: int,
    *,
    food_state: str,
    has_edible: bool,
    reason: str,
    position_changed: bool,
) -> int:
    """Count starvation decisions, sparing active escape/recall workflows."""
    starving = food_state in {"weak", "fainting"} and not has_edible
    advancing_escape = reason.startswith(("return:", "survival:", "livelock:"))
    if not starving or advancing_escape:
        return 0
    return streak + 1


# The emitter can present the exact same command state several times while a
# posted Windows key is still waiting to be consumed. Sending on every copy
# builds a large input backlog and makes the loop detector judge stale positions.
# A genuinely rejected move still needs retries so the policy can break out;
# throttle exact duplicates instead of dropping them forever.
DUPLICATE_RETRY_SECONDS = 2.0
# Snapshots can advance their turn/message state before a posted movement key is
# consumed.  Sending the next route correction then leaves one direction queued;
# live failures overshot a Q34 chest and orbited six cells around fundraising loot.
# Hold deterministic chest/loot navigation until its position change is visible;
# combat remains unthrottled because an attack legitimately holds position.
CHEST_MOVE_RESPONSE_SECONDS = 2.0
CHEST_MOVEMENT_REASONS = frozenset(
    {"chest:step-off", "chest:approach", "chest:collect-contents"}
)
DIRECTION_KEYS = frozenset("12346789")


def _movement_command_needs_ack(key: str, reason: str) -> bool:
    """Throttle only direction commands whose success must move the player."""
    return key in DIRECTION_KEYS and (
        reason in CHEST_MOVEMENT_REASONS or reason.endswith("seek-loot")
    )
# A command that repeatedly returns the same turn, player state, inventory, and
# equipment consumed no energy and made no useful progress. This catches invalid
# digs and other rejected commands even when their reason is exempt from the
# position-based loop detector.
STALLED_COMMAND_STATE_LIMIT = 12
# Zero-energy travel rejection must fall back before the CLI stops the bot.
assert TOWN_TRAVEL_STALL_LIMIT < STALLED_COMMAND_STATE_LIMIT
# Turn stalls operate after energy consumption, where the CLI signature changes.
assert TOWN_TRAVEL_TURN_STALL_LIMIT == 12
# Both finite travel guards are far below the town-residence net. (The
# constant is defined later in this module; the literal here would silently
# diverge if the net were retuned, so assert against the real value at the
# bottom of the module instead.)
# Store purchases and other multi-prompt commands redraw between each key. A
# 50ms gap was too short on the live Windows build: Return/y reached the queue
# before the quantity/confirmation prompt was ready and were flushed. Keep the
# macro deliberate; single movement keys are unaffected.
MULTI_KEY_DELAY_SECONDS = 0.25
# Entering the item selector from a busy store redraw is measurably slower than
# advancing an already-open prompt. At a 49-stack Home, 250 ms repeatedly lost
# the inventory letter after ``d``; 300 ms succeeded in the preserved game.
# Leave margin for busier redraws instead of relying on that narrow boundary.
STORE_ITEM_PROMPT_DELAY_SECONDS = 0.5
# The live torch macro accepted the first digit of ``10`` but lost the second
# at the generic cadence. Multi-digit store quantities get the proven margin.
STORE_QUANTITY_DIGIT_DELAY_SECONDS = 0.5
# Tunnelling raises a direction prompt more slowly than ordinary item prompts on
# the live Windows Release build. Posting the direction at the generic 250 ms
# interval leaves the game blocked at that prompt; two seconds is verified to
# advance a real digging turn.
TUNNEL_PROMPT_DELAY_SECONDS = 2.0

# The bot character's pref binds these otherwise-unused control characters to complete
# tunnelling commands. A single WM_CHAR then lets Hengband's own macro queue
# supply both ``T`` and the direction without racing the direction prompt.
BOT_PLAY_MACRO_PREF_MARKER = "HENGBOT_INPUT_MACROS_V3"
TUNNEL_MACRO_TRIGGERS = {
    # Ctrl+A is Hengband's built-in repeat-command control.  Use the otherwise
    # unused Ctrl+Y for southwest tunnelling so it expands atomically too.
    "1": "\x19",
    "2": "\x02",
    "3": "\x03",
    "4": "\x04",
    "6": "\x05",
    "7": "\x06",
    "8": "\x07",
    "9": "\x08",
}
TUNNEL_MACRO_PREF_TRIGGERS = {
    "1": "^Y",
    "2": "^B",
    "3": "^C",
    "4": "^D",
    "6": "^E",
    "7": "^F",
    "8": "^G",
    "9": "^H",
}
# Native travel uses five external key messages without a loaded macro. Busy
# target-selector redraws intermittently flush one of them at 250 ms, leaving
# the game at destination selection until the duplicate retry. The verified
# BOT_PLAY macro path replaces each complete sequence with one WM_CHAR.
TRAVEL_PROMPT_DELAY_SECONDS = 0.5
TRAVEL_MACRO_TRIGGERS = {
    "\x1b`n!.": "\x0b",
    "\x1b`n\".": "\x0c",
    "\x1b`n#.": "\x0e",
    "\x1b`n$.": "\x0f",
    "\x1b`n%.": "\x10",
    "\x1b`n&.": "\x11",
    "\x1b`n'.": "\x12",
    "\x1b`n(.": "\x13",
    "\x1b`n>.": "\x14",
}
TRAVEL_MACRO_PREF_TRIGGERS = {
    "\x1b`n!.": "^K",
    "\x1b`n\".": "^L",
    "\x1b`n#.": "^N",
    "\x1b`n$.": "^O",
    "\x1b`n%.": "^P",
    "\x1b`n&.": "^Q",
    "\x1b`n'.": "^R",
    "\x1b`n(.": "^S",
    "\x1b`n>.": "^T",
}

# Decision reasons that legitimately hold the player on one tile for many
# consecutive snapshots and so must NOT feed the loop detector: searching a
# dead-end, meleeing in place, and waiting out a Word of Recall countdown
# (~15-35 stationary turns — enough to trip a ≤4-cell window by itself).
STATIONARY_REASONS = frozenset(
    {
        "search",
        "melee",
        # Walking returns may need SEARCH_LIMIT stationary searches at each
        # candidate wall before moving to the next one.  The policy bounds that
        # work with _wall_search_counts; feeding these deliberate holds to the
        # 40-cell watchdog produces a false loop at five walls (5 * 8).
        "return:search-upstairs",
        "return:wait-recall",
        "fundraise:wait-recall",
        "town:wait-recall",
        "town:wait-restock",
        "wilderness:wait-recall",
        # Waiting in place for Word of Recall to fire after a breeder disengage
        # is a bounded, stationary hold (FRUITLESS_DISENGAGE_LIMIT backstops it,
        # and recall triggers within ~35 turns).  Like the other *:wait-recall
        # reasons it must not feed the position loop guard, or the very escape
        # armed by the breeder-containment disengage re-trips it.
        "combat:disengage-wait-recall",
    }
)

# These productive actions deliberately hold the player on ONE tile, which looks
# like a confined oscillation to the position-based guard. Mining has its own
# MINING_STALL_LIMIT leash; a quest hold ends when a wave appears or completion
# routing takes ownership. Walking and failed-position reasons remain guardable.
STATIONARY_EXEMPT_REASONS = frozenset(
    {
        "breakout:dig-to-stairs",
        "fundraise:mine-treasure",
        "fundraise:tunnel-out",
        "quest-strategy:hold",
    }
)

# Fixed-quest combat is productive even when a strategy deliberately fights
# from one post for an entire wave.  Route/avoid failures remain guardable;
# only commands which actually attack are exempt from the positional loop net.
QUEST_COMBAT_REASON_PREFIXES = (
    "quest-strategy:melee",
    "quest-strategy:ranged-fire",
)

# Consecutive town:blocked:* decisions before the bot stops itself. The block
# is a deliberate stationary latch, so this is a short fuse — it exists because
# store-door snapshots reset the cell-based loop guard and could otherwise hide
# the latched state forever.
TOWN_BLOCKED_STOP_LIMIT = 30
# Outermost town safety net. Policy-level repetition checks deliberately reset
# when gold, pack, or equipment changes, so transaction ping-pong can evade
# them forever. A continuous town residence this long is faulty regardless of
# the recorded reasons (about 25+ minutes at normal decision cadence).
TOWN_RESIDENCE_STOP_LIMIT = 1500
# Relocated from the travel-guard block: assert against the real constant so
# a retuned residence net cannot silently invert the guard ordering.
assert max(TOWN_TRAVEL_STALL_LIMIT, TOWN_TRAVEL_TURN_STALL_LIMIT) < TOWN_RESIDENCE_STOP_LIMIT


def _cell_loop_guard_applies(snapshot, reason: str) -> bool:
    """Leave town repetition to the policy's bounded repair path.

    Town deliberately has its own cycle/no-progress counters and a visible
    blocked-state stop.  Feeding the same decisions to the generic dungeon
    cell guard can stop the bot before ``town:cycle-break`` is emitted.
    """
    return (
        not snapshot.in_town
        and reason not in STATIONARY_REASONS
        and reason not in STATIONARY_EXEMPT_REASONS
        and not reason.startswith(QUEST_COMBAT_REASON_PREFIXES)
        and not reason.startswith("item:")
        # A firefight legitimately holds one tile for many decisions.
        and not reason.startswith("ranged:")
        # The chest pipeline (search/disarm/open budgets) holds two tiles.
        and not reason.startswith("chest:")
    )


def _uses_multiplier_combat_grace(reason: str) -> bool:
    """Recognize both the legacy and current deep-fundraising combat labels."""
    return reason.startswith(
        ("fundraise:eliminate-multiplier", "fundraise:clear-hostile")
    )


def _advance_town_blocked_streak(streak: int, reason: str) -> int:
    """Count consecutive latched-town-block decisions. In-store leaves do not
    break the streak: standing blocked on a store door alternates blocked WAITs
    with shop:leave rows."""
    if reason.startswith("town:blocked:"):
        return streak + 1
    if reason == "shop:leave":
        return streak
    return 0


def _advance_town_residence_streak(
    streak: int, previous_floor_key: tuple | None, floor_key: tuple
) -> int:
    """Count decisions in one uninterrupted residence on the town floor."""
    if floor_key != previous_floor_key:
        streak = 0
    if floor_key[0] == 0 and floor_key[1] == 0:
        return streak + 1
    return 0


def _floor_transition_needs_prompt_clear(
    previous_floor_key: tuple | None, floor_key: tuple
) -> bool:
    """Clear level-arrival messages once before sending the first floor action."""
    return previous_floor_key is not None and floor_key != previous_floor_key


def _objective_for_reason(reason: str) -> str:
    if reason == "loop-detected":
        return "Stopped for loop investigation"
    prefix = reason.split(":", 1)[0]
    if prefix in {"flee", "unseen", "summoner", "item"}:
        return "Survive and disengage"
    if prefix in {"melee", "hunt"}:
        return "Fight visible threats"
    if prefix == "return":
        return "Return to town"
    if prefix in {"shop", "home", "town", "identify", "equipment"}:
        return "Town maintenance and resupply"
    if prefix == "fundraise":
        return "Raise funds on Yeek cave level 1"
    if prefix == "victory":
        return "Collect conquest drops and return"
    if reason in {"pickup", "seek-loot"}:
        return "Collect visible floor items"
    if prefix in {"descend", "seek-downstairs", "approach-descent", "clear-descent"}:
        return "Reach the next dungeon level"
    if prefix in {"explore", "probe", "search", "breakout", "stuck"}:
        return "Explore and break out of dead ends"
    if prefix in {"rest", "eat", "wield-light", "refill-light"}:
        return "Recover and maintain supplies"
    if prefix in {"confused", "wait"}:
        return "Wait safely"
    return "Continue conservative progression"


def _command_state_signature(snapshot, reason: str, key: str) -> tuple:
    """Return the stable, player-visible state relevant to command progress."""
    store_signature = None
    if snapshot.store is not None:
        store_signature = (
            snapshot.store.store_type,
            tuple(snapshot.store.items),
        )
    return (
        snapshot.floor_key,
        snapshot.turn,
        snapshot.player,
        tuple(snapshot.inventory),
        tuple(snapshot.equipment),
        store_signature,
        reason,
        key,
    )


def _advance_stalled_command_count(
    count: int,
    *,
    signature: tuple,
    previous_signature: tuple | None,
) -> int:
    """Count repeated commands that consume no turn and change no useful state."""
    if signature == previous_signature:
        return count + 1
    return 0


def _last_activity_after_read(last_activity: float, now: float, chunk: str) -> float:
    """Treat a partial snapshot write as live emitter activity.

    Live snapshots can be several megabytes.  Waiting for the terminating
    newline before refreshing the stall clock lets the prompt recovery path
    enqueue Escapes while the emitter is still writing.  Those Escapes then sit
    ahead of the policy command and manufacture a stream of stale snapshots.
    """
    return now if chunk else last_activity


def _delay_spec_after_macro_key(
    key: str, index: int, *, in_store: bool = False
) -> tuple[float, str | None]:
    """Return the delay and telemetry category after one macro character."""
    if len(key) <= 1 or index >= len(key) - 1:
        return 0.0, None
    # Store buy/sell and in-store inscription prompt chains do not flush input;
    # they are synchronized entirely by key count and are safe as one blast.
    if in_store and key[0] in {"d", "p", "{"}:
        return 0.0, None
    if key.startswith("T") and index == 0:
        return TUNNEL_PROMPT_DELAY_SECONDS, "input:tunnel-prompt"
    if key in TRAVEL_MACRO_TRIGGERS and index in {1, 2, 3}:
        return TRAVEL_PROMPT_DELAY_SECONDS, "input:travel-prompt"
    # f/v raise an item-selection prompt before the direction prompt, the same
    # settle shape as store drop/get.
    if key[0] in {"d", "g", "f", "v"} and index == 0:
        return STORE_ITEM_PROMPT_DELAY_SECONDS, "input:item-prompt"
    if key[0] in {"p", "d"} and key[index].isdigit() and key[index + 1].isdigit():
        return STORE_QUANTITY_DIGIT_DELAY_SECONDS, "input:quantity-digit"
    return MULTI_KEY_DELAY_SECONDS, "input:generic-prompt"


def _delay_after_macro_key(key: str, index: int, *, in_store: bool = False) -> float:
    """Return the prompt-settling delay after one character in a macro."""
    return _delay_spec_after_macro_key(key, index, in_store=in_store)[0]


def _intentional_action_wait_category(key: str, reason: str) -> str | None:
    """Classify commands whose purpose is to spend time without repositioning."""
    if key.startswith("R"):
        return f"action:{reason or 'rest'}"
    if key == "5":
        return f"action:{reason or 'wait'}"
    return None


def _command_response_grace(key: str, reason: str) -> float:
    """Extra snapshot silence allowed only for genuinely multi-turn commands."""
    if key in TRAVEL_MACRO_TRIGGERS:
        return COMMAND_RESPONSE_GRACE
    return 0.0


def _bot_play_macro_pref_path(monrace_path: Path) -> Path | None:
    """Find bot-test.prf beside the lib tree used by the running game.

    ``-u BOT_PLAY`` selects the savefile, but Hengband loads character prefs by
    PlayerType.base_name. The established BOT_PLAY character is named bot-test.
    """
    try:
        hengband_root = monrace_path.resolve().parents[2]
    except (IndexError, OSError):
        return None
    return hengband_root / "lib" / "user" / "bot-test.prf"


def _valid_bot_play_macro_pref(path: Path) -> bool:
    try:
        text = path.read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return False
    if BOT_PLAY_MACRO_PREF_MARKER not in text:
        return False
    normalized = text.replace("\r\n", "\n")
    tunnel_bindings_valid = all(
        f"A:T{direction}\nP:{trigger}" in normalized
        for direction, trigger in TUNNEL_MACRO_PREF_TRIGGERS.items()
    )
    travel_bindings_valid = all(
        f"A:{macro.replace(chr(27), r'\e')}\nP:{trigger}" in normalized
        for macro, trigger in TRAVEL_MACRO_PREF_TRIGGERS.items()
    )
    return tunnel_bindings_valid and travel_bindings_valid


def _bot_play_macros_ready(
    state_file: Path,
    monrace_path: Path,
    window_pid: int | None,
) -> bool:
    """Whether this game process loaded the verified BOT_PLAY macro file.

    The lifecycle writes hengband.pid immediately after process creation. The
    pref must predate that marker: a pref installed while an existing game is
    running is not in that process's macro table and must use the slow fallback.
    """
    if not window_pid:
        return False
    pref_path = _bot_play_macro_pref_path(monrace_path)
    pid_path = state_file.parent / "hengband.pid"
    if pref_path is None or not _valid_bot_play_macro_pref(pref_path):
        return False
    try:
        recorded_pid = int(pid_path.read_text(encoding="ascii").strip())
        return (
            recorded_pid == window_pid
            and pref_path.stat().st_mtime_ns <= pid_path.stat().st_mtime_ns
        )
    except (OSError, ValueError):
        return False


def _transport_key(key: str, tunnel_macros_ready: bool) -> str:
    if tunnel_macros_ready and key in TRAVEL_MACRO_TRIGGERS:
        return TRAVEL_MACRO_TRIGGERS[key]
    if tunnel_macros_ready and len(key) == 2 and key[0] == "T":
        return TUNNEL_MACRO_TRIGGERS.get(key[1], key)
    return key


def _decision_record(
    snapshot,
    key: str,
    reason: str,
    procurement_requirements: list[dict] | None = None,
    over_extension: dict | None = None,
    depth_safety: dict | None = None,
    threat_prediction: dict | None = None,
    equipment_optimization: dict | None = None,
    loot: dict | None = None,
    mining: dict | None = None,
    fundraising: dict | None = None,
    town_plan: dict | None = None,
    fixedquest_readiness: dict | None = None,
    departure_block: dict | None = None,
    quest_strategy: dict | None = None,
) -> dict:
    player = snapshot.player
    active_status = [
        name
        for name in (
            "blind",
            "confused",
            "afraid",
            "poisoned",
            "stunned",
            "cut",
            "paralyzed",
            "hallucinated",
        )
        if getattr(player, name)
    ]
    return {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "turn": snapshot.turn,
        "objective": _objective_for_reason(reason),
        "reason": reason,
        "key": key,
        "floor": {
            "dungeon_id": snapshot.floor_key[0],
            "level": snapshot.floor_key[1],
            "quest_id": snapshot.floor_key[2],
        },
        "position": {"y": player.position.y, "x": player.position.x},
        "player": {
            "level": player.level,
            "hp": player.hp,
            "max_hp": player.max_hp,
            "mp": player.mp,
            "max_mp": player.max_mp,
            "gold": player.gold,
            "food_state": player.food_state,
            "status": active_status,
        },
        "inventory": {
            "used": len(snapshot.inventory),
            "free": max(0, PACK_CAPACITY - len(snapshot.inventory)),
        },
        "procurement_requirements": procurement_requirements or [],
        "visible_hostiles": sum(monster.hostile for monster in snapshot.visible_monsters),
        "threat_prediction": threat_prediction or {},
        "store_type": snapshot.store.store_type if snapshot.store is not None else None,
        "over_extension": over_extension or {},
        "depth_safety": depth_safety or {},
        "equipment_optimization": equipment_optimization or {},
        "loot": loot or {},
        "mining": mining or {},
        "fundraising": fundraising or {},
        **({"town_plan": town_plan} if town_plan else {}),
        **({"fixedquest_readiness": fixedquest_readiness} if fixedquest_readiness else {}),
        **({"departure_block": departure_block} if departure_block else {}),
        **({"quest_strategy": quest_strategy} if quest_strategy is not None else {}),
    }


class EconomyLedger:
    """Append confirmed gold changes with the command that caused them."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.previous_gold: int | None = None
        self.previous_reason: str | None = None
        self.previous_key: str | None = None
        self.previous_store_type: int | None = None
        self.previous_floor: tuple[int, int, int] | None = None

    def prime(self, snapshot) -> None:
        self.previous_gold = snapshot.player.gold
        self.previous_store_type = (
            snapshot.store.store_type if snapshot.store is not None else None
        )
        self.previous_floor = snapshot.floor_key

    def observe(self, snapshot, key: str, reason: str) -> dict | None:
        current_gold = snapshot.player.gold
        event = None
        if self.previous_gold is not None and current_gold != self.previous_gold:
            delta = current_gold - self.previous_gold
            event = {
                "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "turn": snapshot.turn,
                "kind": "income" if delta > 0 else "expense",
                "amount": abs(delta),
                "delta": delta,
                "gold_before": self.previous_gold,
                "gold_after": current_gold,
                "cause_reason": self.previous_reason or "unattributed",
                "cause_key": self.previous_key or "",
                "store_type": self.previous_store_type,
                "floor": {
                    "dungeon_id": self.previous_floor[0],
                    "level": self.previous_floor[1],
                    "quest_id": self.previous_floor[2],
                } if self.previous_floor is not None else None,
            }
            if self.path is not None:
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    with self.path.open("a", encoding="utf-8") as file:
                        json.dump(event, file, ensure_ascii=False)
                        file.write("\n")
                except OSError as exc:
                    print(f"failed to write economy log: {exc}", file=sys.stderr)

        self.previous_gold = current_gold
        self.previous_reason = reason
        self.previous_key = key
        self.previous_store_type = (
            snapshot.store.store_type if snapshot.store is not None else None
        )
        self.previous_floor = snapshot.floor_key
        return event


def _over_extension_state(policy) -> dict:
    """Surface the policy's over-extension counters so the switch is observable.

    The decision to abandon an over-deep dungeon builds up across several dives in
    private policy state; exposing it here lets the viewer (and a watching human)
    see the streak climb and the alternate target get chosen, instead of the switch
    appearing from nowhere.
    """
    knowledge = getattr(policy, "_dungeon_knowledge", {}) or {}

    def name(dungeon_id):
        if dungeon_id is None:
            return None
        info = knowledge.get(dungeon_id)
        return info.name if info is not None else None

    target = getattr(policy, "_target_dungeon_id", None)
    alternate = getattr(policy, "_alternate_dungeon", None)
    return {
        "target_dungeon_id": target,
        "target_dungeon": name(target),
        "over_extended_dive_streak": getattr(policy, "_target_empty_dives", 0),
        "alternate_dungeon_id": alternate,
        "alternate_dungeon": name(alternate),
        "last_overextended_depth": getattr(policy, "_last_overextended_depth", 0),
        "dive_loot": getattr(policy, "_dive_loot", 0),
        "dive_emergencies": getattr(policy, "_dive_emergencies", 0),
        "last_return_trigger": getattr(policy, "_last_return_trigger", None),
    }


def _mining_state(policy) -> dict:
    """Surface the mining coverage counters so the user's design goal —
    collect every low-dig-cost treasure before leaving a floor — is verifiable
    live: detected_total should end ~equal to collected, with dropped the
    (small) walk-failure remainder."""
    known = getattr(policy, "_known_treasure", None) or set()
    dropped_set = getattr(policy, "_mining_dropped_veins", None) or set()
    collected = getattr(policy, "_mining_veins_collected", 0)
    dropped = getattr(policy, "_mining_veins_dropped", 0)
    remaining = len(known - dropped_set)
    return {
        "collected": collected,
        "dropped": dropped,
        "remaining_known": remaining,
        "detected_total": collected + dropped + remaining,
        "sweep_done": getattr(policy, "_mining_sweep_done", False),
        "sweep_steps": getattr(policy, "_mining_sweep_steps", 0),
    }


def _fundraising_state(snapshot, policy) -> dict:
    mode = getattr(policy, "_fundraising_mode", None)
    return {
        "mode": mode,
        "planned_runs": getattr(policy, "_planned_mining_runs", None),
        "kit_secured": policy._fundraising_kit_secured(snapshot),
        "gold_trigger": (
            snapshot.in_town
            and snapshot.player.class_id >= 0
            and snapshot.player.gold < FUNDRAISING_START_GOLD
            and mode in {"prepare", "mine", "scavenge"}
        ),
    }


def _town_plan_state(policy) -> dict:
    plan = getattr(policy, "_town_errand_plan", None)
    if plan is None:
        return {}
    names = (
        "General Store",
        "Armoury",
        "Weapon Smiths",
        "Temple",
        "Alchemist",
        "Magic Shop",
        "Black Market",
        "Home",
    )

    def name(store_type):
        return names[store_type] if 0 <= store_type < len(names) else str(store_type)

    return {
        "stops": [name(store_type) for store_type in plan.stops],
        "index": plan.index,
        "inserted_this_visit": [name(store_type) for store_type in plan.inserted_this_visit],
        "skipped_latched": [name(store_type) for store_type in plan.skipped_latched],
    }


def _depth_safety(snapshot, policy) -> dict:
    """Surface the depth-requirement check so a lethal resistance gap is visible
    (the bot gates its descent on this — see AGENTS.md)."""
    depth = max(1, snapshot.floor_key[1])
    required = sorted(required_depth_gates(depth))
    missing = (
        sorted(policy._missing_required_abilities(snapshot, depth)) if policy else []
    )
    return {
        "depth": depth,
        "required": required,
        "missing": missing,
        "has": sorted(snapshot.player.abilities),
    }


def _write_decision(
    path: Path | None,
    snapshot,
    key: str,
    reason: str,
    policy=None,
    economy_ledger: EconomyLedger | None = None,
) -> None:
    if economy_ledger is not None:
        economy_ledger.observe(snapshot, key, reason)
    if path is None:
        return
    try:
        with path.open("a", encoding="utf-8") as file:
            requirements = (
                policy.procurement_requirements(snapshot) if policy is not None else []
            )
            over_extension = _over_extension_state(policy) if policy is not None else {}
            depth_safety = _depth_safety(snapshot, policy) if policy is not None else {}
            threat_prediction = (
                policy.threat_prediction(
                    snapshot,
                    [monster for monster in snapshot.visible_monsters if monster.hostile],
                )
                if policy is not None
                else {}
            )
            equipment_optimization = (
                policy.equipment_optimization_state(snapshot)
                if policy is not None
                else {}
            )
            loot = policy.loot_state(snapshot) if policy is not None else {}
            mining = _mining_state(policy) if policy is not None else {}
            fundraising = (
                _fundraising_state(snapshot, policy) if policy is not None else {}
            )
            town_plan = _town_plan_state(policy) if policy is not None else {}
            fixedquest_readiness = (
                getattr(policy, "fixed_quest_readiness_state", lambda: {})()
                if policy is not None
                else {}
            )
            departure_block = (
                policy.departure_block_state() if policy is not None else {}
            )
            quest_strategy = None
            quest_id = snapshot.floor_key[2] or int(fixedquest_readiness.get("quest_id", 0))
            if policy is not None and quest_id > 0:
                quest_strategy = {
                    "quest_id": quest_id,
                    "approved_profile": policy.approved_quest_strategy(quest_id) is not None,
                }
            json.dump(
                _decision_record(
                    snapshot,
                    key,
                    reason,
                    requirements,
                    over_extension,
                    depth_safety,
                    threat_prediction,
                    equipment_optimization,
                    loot,
                    mining,
                    fundraising,
                    town_plan,
                    fixedquest_readiness,
                    departure_block,
                    quest_strategy,
                ),
                file,
                ensure_ascii=False,
            )
            file.write("\n")
    except OSError as exc:
        print(f"failed to write decision log: {exc}", file=sys.stderr)


def _rewind_if_truncated(file, path: Path) -> bool:
    """Rewind a tail reader after the emitter rolls over its JSONL file."""
    try:
        if path.stat().st_size >= file.tell():
            return False
        file.seek(0)
        return True
    except OSError:
        return False


def _duplicate_snapshot_ready(
    line: str,
    previous_line: str | None,
    elapsed: float,
    previous_reason: str | None = None,
) -> bool:
    if line == previous_line and previous_reason is not None and (
        previous_reason.startswith("shop:buy-")
        or previous_reason.startswith("shop:sell")
        or previous_reason.startswith("home:deposit")
        or previous_reason.startswith("home:withdraw")
    ):
        # A store transaction can complete without advancing the game turn.
        # Retrying the generic stale-snapshot path then addresses the shifted
        # shelf/pack with the old letter and leaves the macro tail as bare store
        # commands.  Wait for any newly serialized state (gold, inventory, or
        # store stock) before allowing another mutating transaction.
        return False
    return line != previous_line or elapsed >= DUPLICATE_RETRY_SECONDS


def _movement_destination(position, key: str):
    """Return the exact adjacent cell requested by a direction command."""
    offsets = {
        "1": (1, -1),
        "2": (1, 0),
        "3": (1, 1),
        "4": (0, -1),
        "6": (0, 1),
        "7": (-1, -1),
        "8": (-1, 0),
        "9": (-1, 1),
    }
    dy, dx = offsets[key]
    return type(position)(position.y + dy, position.x + dx)


def _chest_movement_response_pending(
    pending: tuple[tuple[int, int, int], object, object, float] | None,
    snapshot,
    now: float,
) -> bool:
    """Wait until the requested destination, not merely another cell, is seen.

    A bot restart can inherit one already-posted direction from the previous
    process.  That stale direction may move the character after the new process
    sends its first route step.  Treating any position change as acknowledgement
    leaves every subsequent key one command behind and makes the character orbit
    a chest or floor item forever.
    """
    if pending is None:
        return False
    floor_key, _origin, destination, sent_at = pending
    return (
        snapshot.floor_key == floor_key
        and snapshot.player.position != destination
        and now - sent_at < CHEST_MOVE_RESPONSE_SECONDS
    )


def _stall_recovery_key(nudge_streak: int, last_player_level: int | None) -> tuple[str, str]:
    if (
        last_player_level is not None
        and last_player_level % 10 in (8, 9)
        and nudge_streak >= LEVEL_UP_RECOVERY_START
    ):
        if (nudge_streak - LEVEL_UP_RECOVERY_START) % 2 == 0:
            return LEVEL_UP_STAT_CHOICE, f"<level-stat:{LEVEL_UP_STAT_CHOICE}>"
        return "y", "<level-stat:y>"
    return NUDGE_KEY, "<esc>"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument(
        "--decision-log",
        type=Path,
        help="append structured policy decisions for an external live viewer",
    )
    parser.add_argument(
        "--economy-log",
        type=Path,
        help="append confirmed income and expense events (defaults beside decision log)",
    )
    parser.add_argument(
        "--wait-log",
        type=Path,
        help="persist cumulative intentional wait timing (defaults beside decision log)",
    )
    parser.add_argument(
        "--monrace-definitions",
        type=Path,
        help="path to Hengband's lib/edit/MonraceDefinitions.jsonc",
    )
    parser.add_argument(
        "--outpost-map",
        type=Path,
        help="path to Hengband's lib/edit/towns/01_Outpost_Full.txt "
        "(auto-located near the state file if omitted)",
    )
    parser.add_argument(
        "--dungeon-definitions",
        type=Path,
        help="path to Hengband's lib/edit/DungeonDefinitions.jsonc "
        "(auto-located near the state file if omitted)",
    )
    parser.add_argument(
        "--quest-definitions",
        type=Path,
        help="path to QuestDefinitionList.txt or the migrated quests directory",
    )
    parser.add_argument(
        "--quest-strategies",
        type=Path,
        help="path to strategy/quests (auto-located near the state file if omitted)",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=0.1)
    parser.add_argument("--send-to-window", action="store_true")
    parser.add_argument("--window-title")
    parser.add_argument("--window-title-contains", action="store_true")
    parser.add_argument("--window-class", default="ANGBAND")
    parser.add_argument("--window-pid", type=int)
    parser.add_argument("--list-windows", action="store_true")
    parser.add_argument(
        "--stall-timeout",
        type=float,
        default=1.5,
        help="seconds without a new snapshot before nudging a stuck prompt (0 disables)",
    )
    args = parser.parse_args(argv)

    if args.economy_log is None and args.decision_log is not None:
        args.economy_log = args.decision_log.with_name("bot-economy.jsonl")
    if args.wait_log is None and args.decision_log is not None:
        args.wait_log = args.decision_log.with_name("bot-waits.json")

    wait_telemetry = WaitTelemetry(args.wait_log if not args.once else None)
    if not args.once:
        wait_telemetry.flush()
    args.wait_telemetry = wait_telemetry

    if args.decision_log is not None and not args.once:
        try:
            args.decision_log.parent.mkdir(parents=True, exist_ok=True)
            args.decision_log.write_text("", encoding="utf-8")
        except OSError as exc:
            print(f"failed to initialize decision log: {exc}", file=sys.stderr)
            return 2

    if args.list_windows:
        from hengbot.input_windows import list_windows

        for window in list_windows():
            line = f"{window.hwnd}\tpid={window.process_id}\tclass={window.class_name}\ttitle={window.title}"
            encoding = sys.stdout.encoding or "utf-8"
            print(line.encode(encoding, errors="replace").decode(encoding))
        return 0

    monrace_path = find_monrace_definitions(args.state_file, args.monrace_definitions)
    if monrace_path is None:
        print("MonraceDefinitions.jsonc was not found", file=sys.stderr)
        return 2
    else:
        try:
            monrace_knowledge = load_monrace_knowledge(monrace_path)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"invalid monster definitions: {exc}", file=sys.stderr)
            return 2

    tunnel_macros_ready = _bot_play_macros_ready(
        args.state_file, monrace_path, args.window_pid
    )

    def send(key: str, *, in_store: bool = False) -> bool:
        if not args.send_to_window:
            return True
        try:
            from hengbot.input_windows import send_key_to_window

            key = _transport_key(key, tunnel_macros_ready)
            # A decision may be a multi-key macro (e.g. "qf" = quaff item f). Post
            # each key in turn; the gap lets the game raise each successive
            # prompt before the follow-up character arrives so it is not flushed.
            multi = len(key) > 1
            recorded_wait = False
            for index, char in enumerate(key):
                send_key_to_window(
                    char,
                    args.window_title,
                    contains=args.window_title_contains,
                    class_name=args.window_class,
                    process_id=args.window_pid,
                )
                delay, wait_category = (
                    _delay_spec_after_macro_key(key, index, in_store=in_store)
                    if multi
                    else (0.0, None)
                )
                if delay:
                    started = time.monotonic()
                    time.sleep(delay)
                    wait_telemetry.record(
                        wait_category or "input:uncategorized",
                        time.monotonic() - started,
                    )
                    recorded_wait = True
            if recorded_wait:
                wait_telemetry.flush()
            return True
        except RuntimeError as exc:
            print(f"failed to send key: {exc}", file=sys.stderr)
            return False

    # The static Outpost layout lets the bot route across a dark town to a store
    # (prior knowledge a returning player has). Optional: if it is not found the
    # bot still plays, just without night-town routing help.
    outpost_map: TownMap | None = None
    town_maps: dict[int, TownMap] = {}
    outpost_path = args.outpost_map or find_outpost_map(args.state_file)
    if outpost_path is not None:
        try:
            outpost_map = parse_town_map(outpost_path)
            town_maps[0] = outpost_map
        except (OSError, ValueError) as exc:
            print(f"could not load Outpost map ({outpost_path}): {exc}", file=sys.stderr)

    # Load every active normal town.  Cross-town errands use the inn in
    # Telmora, Morivant, and Angwil; the static maps keep those routes working
    # at night when the destination building is not currently lit.
    for town_index in range(2, 6):
        town_path = find_town_map(town_index, args.state_file)
        if town_path is None:
            continue
        try:
            town_maps[town_index - 1] = parse_town_map(town_path)
        except (OSError, ValueError) as exc:
            print(f"could not load town map ({town_path}): {exc}", file=sys.stderr)

    wilderness_map = None
    wilderness_path = find_wilderness_definition(args.state_file)
    if wilderness_path is not None:
        try:
            wilderness_map = load_wilderness_map(wilderness_path)
        except (OSError, ValueError) as exc:
            print(
                f"could not load wilderness map ({wilderness_path}): {exc}",
                file=sys.stderr,
            )

    # Static dungeon depth/level facts let the bot recall into a level-appropriate
    # dungeon instead of over-extending in one far past its recommended level.
    # Optional: without it the bot still plays, just never switches dungeons.
    dungeon_knowledge: dict[int, object] = {}
    dungeon_path = find_dungeon_definitions(args.state_file, args.dungeon_definitions)
    if dungeon_path is not None:
        try:
            dungeon_knowledge = load_dungeon_knowledge(dungeon_path)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(
                f"could not load dungeon definitions ({dungeon_path}): {exc}",
                file=sys.stderr,
            )

    quest_knowledge: dict[int, object] = {}
    quest_path = find_quest_definitions(args.state_file, args.quest_definitions)
    if quest_path is not None:
        try:
            quest_knowledge = load_quest_knowledge(quest_path)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"could not load quest definitions ({quest_path}): {exc}", file=sys.stderr)

    quest_strategies: dict[int, object] = {}
    strategy_path = find_quest_strategies(args.state_file, args.quest_strategies)
    if strategy_path is not None:
        quest_strategies = load_quest_strategies(strategy_path)

    policy = ConservativePolicy(
        town_map=outpost_map,
        town_maps=town_maps,
        wilderness_map=wilderness_map,
        dungeon_knowledge=dungeon_knowledge,
        monrace_knowledge=monrace_knowledge,
        quest_knowledge=quest_knowledge,
        quest_strategies=quest_strategies,
    )
    if args.decision_log is not None:
        policy._loadout_report_path = args.decision_log.with_name("loadout-report.jsonl")

    if args.once:
        for line in _read_last_line(args.state_file):
            if not line.strip():
                continue
            try:
                snapshot = parse_snapshot(json.loads(line), monrace_knowledge)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                print(f"invalid snapshot: {exc}", file=sys.stderr)
                return 2
            policy.prime(snapshot)
            key = policy.choose_key(snapshot)
            _write_decision(args.decision_log, snapshot, key, policy.last_reason, policy)
            print(key, flush=True)
            if not send(key, in_store=snapshot.store is not None):
                return 3
            return 0
        return 1

    try:
        return _run_follow(args, policy, send, monrace_knowledge)
    except MissingMonraceKnowledgeError as exc:
        # The definitions file we loaded does not match the running game (e.g. a
        # different lib/ was resolved). Fail fast but CLEANLY — a raw traceback
        # here would leave the game blocked with no hint of what to fix.
        print(
            f"monster definitions mismatch: {exc}; "
            "pass --monrace-definitions with the lib/edit the game actually loads",
            file=sys.stderr,
        )
        return 2


def _run_follow(args, policy, send, monrace_knowledge) -> int:
    path = args.state_file
    wait_telemetry: WaitTelemetry = args.wait_telemetry
    while not path.exists():
        time.sleep(args.poll_interval)

    initial_snapshot = _newest_snapshot(
        list(_read_last_line(path)), monrace_knowledge
    )
    if initial_snapshot is not None:
        policy.prime(initial_snapshot)
    economy_ledger = EconomyLedger(args.economy_log)
    if initial_snapshot is not None:
        economy_ledger.prime(initial_snapshot)
    # errors="replace": a poll can catch the emitter mid-write inside a multibyte
    # character (Japanese monster names); a strict read would raise
    # UnicodeDecodeError and kill the loop. Replacement characters at a torn
    # boundary at worst spoil that one line, and drain-to-newest skips past it.
    with path.open("r", encoding="utf-8", errors="replace") as file:
        file.seek(0, 2)
        pending = ""
        last_activity = time.monotonic()
        quiet_ok_until = 0.0  # suppress the nudge while a rest is expected to run
        nudge_streak = 0  # consecutive nudges with no snapshot in between
        last_player_level = initial_snapshot.player.level if initial_snapshot is not None else None
        # (floor_key, y, x) of the last LOOP_WINDOW decisions, for loop detection.
        recent_cells: deque[tuple] = deque(maxlen=MULTIPLIER_COMBAT_LOOP_WINDOW)
        multiplier_combat_grace = 0
        last_decision_line: str | None = None
        last_decision_reason: str | None = None
        last_decision_at = 0.0
        pending_action_wait: tuple[str, float] | None = None
        stalled_command_count = 0
        blocked_streak = 0
        town_residence_streak = 0
        residence_floor_key = None
        starving_streak = 0
        starving_last_position = None
        last_snapshot_floor_key = (
            initial_snapshot.floor_key if initial_snapshot is not None else None
        )
        last_command_signature: tuple | None = None
        pending_chest_movement: tuple[
            tuple[int, int, int], object, object, float
        ] | None = None
        next_dump_at = time.monotonic() + DUMP_INTERVAL_SECONDS
        while True:
            _arm_decision_watchdog()
            chunk = file.read()
            if chunk:
                last_activity = _last_activity_after_read(
                    last_activity, time.monotonic(), chunk
                )
                complete_lines, pending = _split_complete_lines(pending + chunk)
                # Act ONLY on the newest complete snapshot in this batch. The game
                # emits a snapshot then blocks on request_command, so the file's
                # newest line is ALWAYS the current board the game is waiting on;
                # any older lines in the same read are prompts a fast monster raced
                # us past. The old code answered every line, posting one key per
                # stale board, so the key stream lagged the game by a step and
                # "step onto the monster" (an attack) degraded into a side-step —
                # a speed-118 archer shot a full-HP character to death while it
                # merely circled the archer, whose HP never dropped. Acting on the
                # newest line keeps every key matched to the live board and is
                # self-healing: even after a stray desync the next decision re-syncs
                # to the current state. Rejected moves (wall/door bumps) still
                # re-emit the same board and are retried at a bounded interval so
                # the policy's livelock breaker can act without flooding the
                # Windows input queue.
                entry = _newest_snapshot_entry(complete_lines, monrace_knowledge)
                if entry is not None:
                    snapshot, snapshot_line = entry
                    # A snapshot means the game is alive and awaiting a command.
                    nudge_streak = 0
                    last_player_level = snapshot.player.level
                    now = time.monotonic()
                    last_activity = now
                    if _floor_transition_needs_prompt_clear(
                        last_snapshot_floor_key, snapshot.floor_key
                    ):
                        # Hengband can print a level feeling / arrival message
                        # after emitting the first snapshot on a new floor. With
                        # quick_messages enabled, the first policy key dismisses
                        # it and the remainder of a multi-key command is then
                        # interpreted at the command loop (often opening a menu).
                        # Escape clears the message under either option setting
                        # and is harmless if no prompt is present.
                        if send(NUDGE_KEY):
                            print("<floor-transition:esc>", flush=True)
                    last_snapshot_floor_key = snapshot.floor_key
                    if _chest_movement_response_pending(
                        pending_chest_movement, snapshot, now
                    ):
                        continue
                    pending_chest_movement = None
                    if not _duplicate_snapshot_ready(
                        snapshot_line,
                        last_decision_line,
                        now - last_decision_at,
                        last_decision_reason,
                    ):
                        continue
                    if pending_action_wait is not None:
                        wait_category, wait_started = pending_action_wait
                        wait_telemetry.record(
                            wait_category,
                            max(0.0, now - wait_started),
                            force_flush=True,
                        )
                        pending_action_wait = None
                    last_decision_line = snapshot_line
                    last_decision_at = now
                    next_dump_at = _request_due_dump(policy, now, next_dump_at)
                    key = policy.choose_key(snapshot)
                    last_decision_reason = policy.last_reason
                    command_signature = _command_state_signature(
                        snapshot,
                        policy.last_reason,
                        key,
                    )
                    stalled_command_count = _advance_stalled_command_count(
                        stalled_command_count,
                        signature=command_signature,
                        previous_signature=last_command_signature,
                    )
                    last_command_signature = command_signature
                    if stalled_command_count >= STALLED_COMMAND_STATE_LIMIT:
                        _write_decision(
                            args.decision_log,
                            snapshot,
                            "",
                            "loop-detected",
                            policy,
                            economy_ledger,
                        )
                        print(
                            f"<loop-detected> floor={snapshot.floor_key} "
                            f"turn={snapshot.turn} command repeated without "
                            "consuming a turn or changing player state; stopping "
                            "the bot for investigation",
                            flush=True,
                        )
                        print(
                            f"stalled command loop at floor={snapshot.floor_key} "
                            f"turn={snapshot.turn}; stopping bot (game left running)",
                            file=sys.stderr,
                            flush=True,
                        )
                        return 0
                    _write_decision(
                        args.decision_log,
                        snapshot,
                        key,
                        policy.last_reason,
                        policy,
                        economy_ledger,
                    )
                    starving_position_changed = (
                        starving_last_position is not None
                        and snapshot.player.position != starving_last_position
                    )
                    starving_last_position = snapshot.player.position
                    starving_streak = _advance_starving_streak(
                        starving_streak,
                        food_state=snapshot.player.food_state,
                        has_edible=policy.has_edible(snapshot),
                        reason=policy.last_reason,
                        position_changed=starving_position_changed,
                    )
                    if starving_streak >= STARVING_STOP_LIMIT:
                        print(
                            f"<loop-detected> floor={snapshot.floor_key} "
                            f"turn={snapshot.turn} starvation persisted without "
                            f"edible food for {starving_streak} decisions; stopping "
                            "the bot for investigation",
                            flush=True,
                        )
                        print(
                            f"starvation loop at floor={snapshot.floor_key} "
                            f"turn={snapshot.turn}; stopping bot (game left running)",
                            file=sys.stderr,
                            flush=True,
                        )
                        return 0
                    # The policy's mode-independent navigation invariant found
                    # no coverage/goal/economy progress for hundreds of
                    # decisions AND could not leave the floor. This is the
                    # designed visible stop — cell-based guards cannot see a
                    # loop that keeps its cells varied.
                    if policy.last_reason == "livelock:exhausted":
                        print(
                            f"<loop-detected> floor={snapshot.floor_key} "
                            f"turn={snapshot.turn} navigation exhausted: no new "
                            "coverage, goal progress or combat for the policy's "
                            "no-progress budget and no escape route; stopping "
                            "the bot for investigation",
                            flush=True,
                        )
                        print(
                            f"navigation exhausted at floor={snapshot.floor_key} "
                            f"turn={snapshot.turn}; stopping bot (game left running)",
                            file=sys.stderr,
                            flush=True,
                        )
                        return 0
                    if policy.last_reason == "combat:fruitless":
                        print(
                            f"<loop-detected> floor={snapshot.floor_key} "
                            f"turn={snapshot.turn} combat produced no experience, "
                            "gold, hostile-count reduction, or unique HP progress "
                            "for the combat outcome window; stopping the bot for "
                            "investigation",
                            flush=True,
                        )
                        print(
                            f"fruitless combat at floor={snapshot.floor_key} "
                            f"turn={snapshot.turn}; stopping bot (game left running)",
                            file=sys.stderr,
                            flush=True,
                        )
                        return 0
                    town_residence_streak = _advance_town_residence_streak(
                        town_residence_streak,
                        residence_floor_key,
                        snapshot.floor_key,
                    )
                    residence_floor_key = snapshot.floor_key
                    if town_residence_streak >= TOWN_RESIDENCE_STOP_LIMIT:
                        print(
                            f"<loop-detected> floor={snapshot.floor_key} "
                            f"turn={snapshot.turn} town-residence reached "
                            f"{town_residence_streak} consecutive decisions "
                            "without a floor change; stopping the bot for "
                            "investigation",
                            flush=True,
                        )
                        return 0
                    print(key, flush=True)
                    sent = send(key, in_store=snapshot.store is not None)
                    last_activity = time.monotonic()
                    if (
                        sent
                        and _movement_command_needs_ack(key, policy.last_reason)
                    ):
                        pending_chest_movement = (
                            snapshot.floor_key,
                            snapshot.player.position,
                            _movement_destination(snapshot.player.position, key),
                            last_activity,
                        )
                    action_wait_category = _intentional_action_wait_category(
                        key, policy.last_reason
                    )
                    if sent and action_wait_category is not None:
                        pending_action_wait = (action_wait_category, last_activity)
                    quiet_ok_until = last_activity + _command_response_grace(
                        key, policy.last_reason
                    )
                    # A rest runs many turns emitting no snapshot; give it room so
                    # the stall nudge does not immediately disturb it.
                    if key.startswith("R"):
                        quiet_ok_until = max(
                            quiet_ok_until, last_activity + REST_STALL_GRACE
                        )
                    # A latched town block is stationary BY DESIGN, but standing
                    # on a store door interleaves store snapshots that reset the
                    # cell-based guard below — the visible stop would never fire.
                    # Count the blocked decisions directly (in-store leaves do
                    # not break the streak).
                    blocked_streak = _advance_town_blocked_streak(
                        blocked_streak, policy.last_reason
                    )
                    if blocked_streak >= TOWN_BLOCKED_STOP_LIMIT:
                        print(
                            f"<loop-detected> floor={snapshot.floor_key} "
                            f"turn={snapshot.turn} town blocked "
                            f"({policy.last_reason}) for {blocked_streak} "
                            "decisions; stopping the bot for investigation",
                            flush=True,
                        )
                        return 0
                    # Loop detection: confined to a few tiles on one floor for a
                    # long stretch means the policy is stuck oscillating. Stop so
                    # the cause can be investigated rather than looping forever.
                    # Shopping legitimately pins us to the store tile for many
                    # decisions (one per item bought), so it must not count.
                    if snapshot.store is not None:
                        recent_cells.clear()
                        multiplier_combat_grace = 0
                        continue
                    # Searching a dead-end for a secret door, fighting/drinking in
                    # place during combat, and deliberately waiting out a Word of
                    # Recall countdown all hold position but are NOT exploration
                    # oscillations — don't let them trip the guard (it is meant to
                    # catch a stuck sweep, not abandon a long fight or stop the bot
                    # in the middle of a safe recall home). Recall takes ~15-35
                    # turns of standing still, easily enough to trip a ≤4-cell
                    # window on its own.
                    if not _cell_loop_guard_applies(snapshot, policy.last_reason):
                        # Exempt actions break positional continuity.  Keeping
                        # old route cells across hundreds of intentional hold or
                        # combat decisions makes them look like the latest
                        # consecutive window when movement eventually resumes.
                        recent_cells.clear()
                        if policy.last_reason == "melee" and multiplier_combat_grace:
                            multiplier_combat_grace = MULTIPLIER_COMBAT_GRACE
                        continue
                    if _uses_multiplier_combat_grace(policy.last_reason):
                        multiplier_combat_grace = MULTIPLIER_COMBAT_GRACE
                    elif multiplier_combat_grace:
                        multiplier_combat_grace -= 1
                    pos = snapshot.player.position
                    recent_cells.append((snapshot.floor_key, pos.y, pos.x))
                    loop_window = (
                        MULTIPLIER_COMBAT_LOOP_WINDOW
                        if multiplier_combat_grace
                        else LOOP_WINDOW
                    )
                    if _is_looping(recent_cells, window=loop_window):
                        _write_decision(
                            args.decision_log,
                            snapshot,
                            "",
                            "loop-detected",
                            policy,
                            economy_ledger,
                        )
                        loop_cells = list(recent_cells)[-loop_window:]
                        cells = sorted({(c[1], c[2]) for c in loop_cells})
                        print(
                            f"<loop-detected> floor={snapshot.floor_key} turn={snapshot.turn} "
                            f"confined to {cells} over {loop_window} decisions; stopping the bot "
                            f"for investigation",
                            flush=True,
                        )
                        print(
                            f"loop detected at floor={snapshot.floor_key} cells={cells}; "
                            f"stopping bot (game left running)",
                            file=sys.stderr,
                            flush=True,
                        )
                        return 0
                continue

            # The emitter truncates the JSONL at game start and when it reaches
            # its size limit. Rewind after either shrink so the reader is not
            # stranded beyond the new EOF.
            if _rewind_if_truncated(file, args.state_file):
                pending = ""
                nudge_streak = 0
                continue

            # No new snapshot. If the game has gone quiet for too long it is
            # probably blocked on a message/"-more-" prompt that emits no
            # snapshot; nudge it with Escape to get back to the command loop.
            now = time.monotonic()
            if (
                args.send_to_window
                and args.stall_timeout > 0
                and now - last_activity > args.stall_timeout
                and now >= quiet_ok_until
            ):
                recovery_key, recovery_marker = _stall_recovery_key(
                    nudge_streak, last_player_level
                )
                if send(recovery_key):
                    print(recovery_marker, flush=True)
                last_activity = now
                nudge_streak += 1
                # Nudges that never bring back a snapshot mean a screen outside
                # the command loop. That is DEATH only if the game process is
                # actually winding down — a store/sale prompt chain that ate the
                # nudges looks identical from here, and concluding <dead> on it
                # abandoned a healthy character twice (game alive, HP full). So:
                # blast the exit keys, then look at the PROCESS. Gone -> death,
                # exit. Still alive -> the blast doubled as prompt clearing;
                # resync and keep playing.
                if nudge_streak >= TERMINAL_NUDGE_LIMIT and args.send_to_window:
                    for _ in range(DEATH_EXIT_ROUNDS):
                        for exit_key in DEATH_EXIT_KEYS:
                            send(exit_key)
                            started = time.monotonic()
                            time.sleep(0.3)
                            wait_telemetry.record(
                                "recovery:terminal-key-gap",
                                time.monotonic() - started,
                            )
                    # Give a genuine close_game -> quit() a moment to finish.
                    started = time.monotonic()
                    time.sleep(2.0)
                    wait_telemetry.record(
                        "recovery:shutdown-grace",
                        time.monotonic() - started,
                        force_flush=True,
                    )
                    if not _game_process_alive(args.window_pid):
                        print("<dead>", flush=True)
                        return 0
                    print(
                        "<stuck-prompt> nudges exhausted but the game process "
                        "is alive; cleared prompts and resyncing",
                        flush=True,
                    )
                    nudge_streak = 0

            time.sleep(args.poll_interval)


def _game_process_alive(pid) -> bool:
    """Whether the game process still exists. Unknown pid -> False, preserving
    the old conclude-death behavior when there is nothing to check."""
    if not pid:
        return False
    if not sys.platform.startswith("win"):
        try:
            os.kill(int(pid), 0)
        except OSError:
            return False
        return True
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
    )
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _is_looping(recent_cells, *, window: int = LOOP_WINDOW) -> bool:
    """True for a confined single-floor oscillation or rapid two-floor ping-pong.

    Needs a full window so a genuinely small room or a brief back-and-forth while
    routing does not trip it. A normal floor change happens once; a stair loop
    alternates between two floors on nearly every decision.
    """
    if len(recent_cells) < window:
        return False
    recent_cells = list(recent_cells)[-window:]
    floors = {c[0] for c in recent_cells}
    if len(floors) == 1:
        cells = {(c[1], c[2]) for c in recent_cells}
        return len(cells) <= LOOP_MAX_DISTINCT
    if len(floors) != 2:
        return False

    states = set(recent_cells)
    floor_transitions = sum(
        previous[0] != current[0]
        for previous, current in zip(recent_cells, list(recent_cells)[1:])
    )
    return (
        len(states) <= LOOP_MAX_DISTINCT
        and floor_transitions >= window // 2
    )


def _newest_snapshot(
    complete_lines: list[str], monrace_knowledge=None
):
    """Return the most recent parseable snapshot in a read batch, or ``None``.

    Only the newest snapshot matters: older lines in the same read are stale
    command prompts a fast monster raced past (or exact duplicates it emitted for
    one turn), and answering each would post one key per stale board — desyncing
    our key stream from the game by a step. Parsing walks newest-first and stops
    at the first good line; a malformed tail line simply falls through to the one
    before it.
    """
    entry = _newest_snapshot_entry(complete_lines, monrace_knowledge)
    return entry[0] if entry is not None else None


def _newest_snapshot_entry(
    complete_lines: list[str], monrace_knowledge=None
):
    """Return the newest parseable snapshot together with its exact JSONL line."""
    for line in reversed(complete_lines):
        if not line.strip():
            continue
        try:
            return parse_snapshot(json.loads(line), monrace_knowledge), line
        except MissingMonraceKnowledgeError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"invalid snapshot: {exc}", file=sys.stderr)
    return None


def _read_last_line(path: Path) -> Iterable[str]:
    if not path.exists():
        return []

    with path.open("rb") as file:
        file.seek(0, 2)
        position = file.tell()
        chunks: list[bytes] = []
        newline_count = 0

        while position > 0 and newline_count < 2:
            chunk_size = min(64 * 1024, position)
            position -= chunk_size
            file.seek(position)
            chunk = file.read(chunk_size)
            chunks.append(chunk)
            newline_count += chunk.count(b"\n")

    data = b"".join(reversed(chunks))
    lines = data.splitlines()
    if data and not data.endswith(b"\n"):
        lines = lines[:-1]
    if not lines:
        return []
    return [lines[-1].decode("utf-8")]


def _split_complete_lines(data: str) -> tuple[list[str], str]:
    parts = data.split("\n")
    complete_lines = [part + "\n" for part in parts[:-1]]
    return complete_lines, parts[-1]


def _deduplicate_consecutive(lines: Iterable[str]) -> Iterable[str]:
    previous: str | None = None
    for line in lines:
        snapshot = line.strip()
        if snapshot and snapshot == previous:
            continue
        previous = snapshot
        yield line
