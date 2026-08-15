from __future__ import annotations

import argparse
import faulthandler
import json
import os
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from hengbot.model import (
    STORE_HOME,
    MissingMonraceKnowledgeError,
    _parse_items,
    parse_snapshot,
)
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.terrain_knowledge import (
    find_terrain_definitions,
    load_damaging_terrain_ids,
)
from hengbot.dungeon_knowledge import find_dungeon_definitions, load_dungeon_knowledge
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import find_quest_strategies, load_quest_strategies
from hengbot.town_maps import TownMap, find_outpost_map, find_town_map, parse_town_map
from hengbot.wilderness_map import find_wilderness_definition, load_wilderness_map
from hengbot.wait_telemetry import WaitTelemetry
from hengbot.home_entry_capture import HomeEntryCapture
from hengbot.loop_detection import LOOP_MAX_DISTINCT
from hengbot.policy import (
    ESCAPE_BUDGETED_WAIT_LIMITS,
    EXTENDED_STUCK_WINDOW,
    FUNDRAISING_START_GOLD,
    PACK_CAPACITY,
    ConservativePolicy,
    TOWN_TRAVEL_STALL_LIMIT,
    TOWN_TRAVEL_TURN_STALL_LIMIT,
    WAIT_KEY,
    required_depth_gates,
)
from hengbot.exploration_ledger import EXPLORATION_LEDGER_PATH
from hengbot.flight_recorder import (
    DEFAULT_CAPTURE_LOG_ROTATE_BYTES,
    DEFAULT_CHECKPOINT_INTERVAL,
    DEFAULT_DISK_BUDGET_BYTES,
    DEFAULT_LOG_GENERATIONS,
    DEFAULT_LOG_ROTATE_BYTES,
    FlightRecorder,
    append_session_marker,
    map_memory_summary,
    rotate_log,
)
from hengbot.save_archive import SaveArchiveCoordinator

CAPTURE_LEDGER_ROOT = Path(__file__).resolve().parents[2] / "capture-ledger"
READ_BATCH_LEDGER_PATH = CAPTURE_LEDGER_ROOT / "read-batches.jsonl"
KNOWLEDGE_RESPONSE_LEDGER_PATH = CAPTURE_LEDGER_ROOT / "knowledge-responses.jsonl"


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
        policy.request_game_save()
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
# A live process that remains silent after one complete ESC/look recovery round
# is parked in an input modal, not recovered. Derive the round count from the
# established terminal nudge allowance rather than adding another timing.
# The loop checks at LIMIT, continues, then first probes at LIMIT + 1.  To run
# one real probe before stopping, the exclusive stop boundary is +1+1.
MODAL_RECOVERY_ROUNDS = (TERMINAL_NUDGE_LIMIT + 1 + 1) - (TERMINAL_NUDGE_LIMIT + 1)


def _modal_recovery_action(recovery_attempts: int) -> str:
    """Return the finite post-nudge recovery phase for a silent live game."""
    if recovery_attempts <= TERMINAL_NUDGE_LIMIT:
        return "nudge"
    if recovery_attempts < TERMINAL_NUDGE_LIMIT + 1 + MODAL_RECOVERY_ROUNDS:
        return "esc-look"
    return "stop"


def _silent_game_incident(window_pid) -> str:
    """Give process death priority when terminal modal recovery is exhausted."""
    return "stuck-prompt" if _game_process_alive(window_pid) else "player-death"
# Keys that march through close_game: Escape clears the tombstone and aborts the
# death-info dump, "n" answers the NO_ESCAPE "stand by for score registration?"
# prompt, Return confirms anything else. Repeated to cover every screen.
DEATH_EXIT_KEYS = ("\x1b", "n", "\r")
DEATH_EXIT_ROUNDS = 8

# Every tenth level Hengband blocks outside the command loop and asks for a stat
# (a-f), then confirmation. The screen ignores Escape and emits no snapshot.
# After two harmless Esc nudges, alternate Strength and confirmation only when
# the last observed page was outside a store. A DEFAULT_Y purchase confirmation
# is reachable only from a store page; a level-up prompt is not.
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


# Bound how long the desynchronization look barrier waits when its response is
# lost. The value is unchanged from the former duplicate retry.
LOOK_BARRIER_TIMEOUT_SECONDS = 2.0
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
# These gaps existed because the game DISCARDED queued input: flush_failure
# routed "various failures" through term_flush(), so a key that arrived while a
# prompt was still redrawing was thrown away, and every delay here was tuned to
# out-wait that window (0.25 for generic prompt chains; 0.5 after ``d`` because
# a 49-stack Home lost the inventory letter at 0.25).
#
# The BOT_PLAY pref now turns that option off (``X:flush_failure``), which is a
# verified precondition of the macro path — see _valid_bot_play_macro_pref. With
# input no longer discarded, 2026-07-31 measurements over full store, Home and
# travel macro traffic showed no lost keys at the values below, so a human's
# uninterrupted typing cadence is what the bot uses too. If a key ever goes
# missing again, check that the pref is still installed and still disables
# flush_failure BEFORE raising these numbers.
MULTI_KEY_DELAY_SECONDS = 0.02
STORE_ITEM_PROMPT_DELAY_SECONDS = 0.05
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
BOT_PLAY_MACRO_PREF_MARKER = "HENGBOT_INPUT_MACROS_V4"
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
# target-selector redraws intermittently flushed one of them at 250 ms, leaving
# the game at destination selection until the duplicate retry. The verified
# BOT_PLAY macro path replaces each complete sequence with one WM_CHAR, and the
# same pref disables the discard — see MULTI_KEY_DELAY_SECONDS.
TRAVEL_PROMPT_DELAY_SECONDS = 0.05
INPUT_DELAY_DEFAULTS = {
    "input_key_delay": MULTI_KEY_DELAY_SECONDS,
    "input_item_prompt_delay": STORE_ITEM_PROMPT_DELAY_SECONDS,
    "input_tunnel_prompt_delay": TUNNEL_PROMPT_DELAY_SECONDS,
    "input_travel_prompt_delay": TRAVEL_PROMPT_DELAY_SECONDS,
}

# ``~9`` emits the requested Home catalogue before entering two nested,
# persistent input loops: the Home file viewer and the enclosing knowledge
# menu.  Neither loop is represented in the JSON snapshot.  The response
# dispatcher closes both only after observing the catalogue; sending Escape in
# the request batch races the emitter and can suppress that response.
KNOWLEDGE_HOME_COMMAND = "~9"


TRAVEL_MACRO_TRIGGERS = {
    "\x1b`n!.": "\x0b",
    "\x1b`n\".": "\x0c",
    "\x1b`n#.": "\x0e",
    "\x1b`n$.": "\x0f",
    "\x1b`n%.": "\x10",
    "\x1b`n&.": "\x11",
    "\x1b`n'.": "\x12",
    "\x1b`n(.": "\x15",
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
    "\x1b`n(.": "^U",
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
        # Clearing a physically occupied escape route attacks without changing
        # cells. Accuracy-aware combat projection bounds whether this is chosen.
        "fundraise:clear-escape-path",
        "town:wait-recall",
        "town:wait-restock",
        "wilderness:wait-recall",
        # Waiting in place for Word of Recall to fire after a breeder disengage
        # is a bounded, stationary hold (FRUITLESS_DISENGAGE_LIMIT backstops it,
        # and recall triggers within ~35 turns).  Like the other *:wait-recall
        # reasons it must not feed the position loop guard, or the very escape
        # armed by the breeder-containment disengage re-trips it.
        "combat:disengage-wait-recall",
        # _fruitless_disengage_key re-labels return:* reasons before the CLI
        # sees them; this is the same bounded _wall_search_counts search above.
        "combat:disengage-search-upstairs",
    }
)

# These productive actions deliberately hold the player on ONE tile, which looks
# like a confined oscillation to the position-based guard. Mining has its own
# MINING_STALL_LIMIT leash; a quest hold ends when a wave appears or completion
# routing takes ownership. Walking and failed-position reasons remain guardable.
STATIONARY_EXEMPT_REASONS = frozenset(
    {
        "breakout:dig-to-stairs",
        # Mining-rework dig, bounded by the sweep's MINING_SWEEP_HARD_LIMIT.
        "fundraise:dig-to-treasure",
        "fundraise:dig-mark-bump",
        "fundraise:mine-treasure",
        "fundraise:tunnel-out",
        "unseen:choke-wait",
        "quest-strategy:hold",
        # Exact policy-registered escape WAIT terminals. Each owns the existing
        # bound recorded in ESCAPE_BUDGETED_WAIT_LIMITS and ends visibly as
        # livelock:exhausted; no other escape reason bypasses the outer guard.
        *ESCAPE_BUDGETED_WAIT_LIMITS,
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
POLICY_FINAL_STOP_REASONS = frozenset(
    {
        "equipment-transaction:restore-blocked-terminal",
        "town:blocked:home-known-empty-withdrawal",
        "wilderness:no-safe-route",
    }
)
# Relocated from the travel-guard block: assert against the real constant so
# a retuned residence net cannot silently invert the guard ordering.
assert max(TOWN_TRAVEL_STALL_LIMIT, TOWN_TRAVEL_TURN_STALL_LIMIT) < TOWN_RESIDENCE_STOP_LIMIT


def _cell_loop_guard_applies(
    snapshot, reason: str, previous_position=None
) -> bool:
    """Leave town repetition to the policy's bounded repair path.

    Town deliberately has its own cycle/no-progress counters and a visible
    blocked-state stop.  Feeding the same decisions to the generic dungeon
    cell guard can stop the bot before ``town:cycle-break`` is emitted.
    """
    if previous_position is None:
        previous_position = snapshot.player.position
    return (
        not snapshot.in_town
        and not (
            previous_position == snapshot.player.position
            and (
                any(
                    reason == stationary
                    or reason.startswith(f"{stationary}:")
                    for stationary in STATIONARY_REASONS
                )
                or reason in STATIONARY_EXEMPT_REASONS
                or reason.startswith(QUEST_COMBAT_REASON_PREFIXES)
                or reason.startswith("item:")
                or reason.startswith("ranged:")
                or reason.startswith("chest:")
            )
        )
    )


def _uses_multiplier_combat_grace(reason: str) -> bool:
    """Recognize the fundraising multiplier-combat label."""
    return reason.startswith("fundraise:eliminate-multiplier")


def _advance_town_blocked_streak(
    streak: int,
    reason: str,
    *,
    key: str | None = None,
    in_town: bool = True,
    floor_changed: bool = False,
    durable_progress: bool = False,
) -> int:
    """Count unproductive decisions during one uninterrupted town visit."""
    if floor_changed or not in_town:
        return 0
    if durable_progress:
        streak = 0
    # Only a WAIT actually spends the policy's registered escape budget. Let
    # those waits reach its visible terminal; ESC, step-off, and travel keys
    # remain covered by the short town-block fuse.
    if (
        key == WAIT_KEY
        and reason == "town:blocked:repetition"
        and reason in ESCAPE_BUDGETED_WAIT_LIMITS
    ):
        return streak
    if reason.startswith("town:blocked:"):
        return streak + 1
    if streak and reason != "shop:leave":
        return streak + 1
    return streak


def _advance_town_blocked_iteration(
    policy,
    snapshot,
    streak: int,
    previous_durable_state,
    *,
    key: str | None = None,
    floor_changed: bool = False,
):
    """Apply the production town-fuse projection and authoritative gate."""
    current_durable_state = policy._town_workflow_progress_state(snapshot)
    durable_progress = (
        previous_durable_state is not None
        and current_durable_state != previous_durable_state
    )
    streak = _advance_town_blocked_streak(
        streak,
        policy.last_reason,
        key=key,
        in_town=snapshot.in_town,
        floor_changed=floor_changed,
        durable_progress=durable_progress,
    )
    return streak, current_durable_state


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
    key: str,
    index: int,
    *,
    in_store: bool = False,
    input_delays: Mapping[str, float] = INPUT_DELAY_DEFAULTS,
) -> tuple[float, str | None]:
    """Return the delay and telemetry category after one macro character."""
    if len(key) <= 1 or index >= len(key) - 1:
        return 0.0, None
    # Store buy/sell and in-store inscription prompt chains do not flush input;
    # they are synchronized entirely by key count and are safe as one blast.
    if in_store and key[0] in {"d", "p", "{"}:
        return 0.0, None
    if key.startswith("T") and index == 0:
        return input_delays["input_tunnel_prompt_delay"], "input:tunnel-prompt"
    if key in TRAVEL_MACRO_TRIGGERS and index in {1, 2, 3}:
        return input_delays["input_travel_prompt_delay"], "input:travel-prompt"
    # f/v raise an item-selection prompt before the direction prompt, the same
    # settle shape as store drop/get.
    if key[0] in {"d", "g", "f", "v"} and index == 0:
        return input_delays["input_item_prompt_delay"], "input:item-prompt"
    if key[0] in {"p", "d"} and key[index].isdigit() and key[index + 1].isdigit():
        return STORE_QUANTITY_DIGIT_DELAY_SECONDS, "input:quantity-digit"
    return input_delays["input_key_delay"], "input:generic-prompt"


def _delay_after_macro_key(
    key: str,
    index: int,
    *,
    in_store: bool = False,
    input_delays: Mapping[str, float] = INPUT_DELAY_DEFAULTS,
) -> float:
    """Return the prompt-settling delay after one character in a macro."""
    return _delay_spec_after_macro_key(
        key, index, in_store=in_store, input_delays=input_delays
    )[0]


def _add_input_delay_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input-key-delay",
        type=float,
        default=MULTI_KEY_DELAY_SECONDS,
    )
    parser.add_argument(
        "--input-item-prompt-delay",
        type=float,
        default=STORE_ITEM_PROMPT_DELAY_SECONDS,
    )
    parser.add_argument(
        "--input-tunnel-prompt-delay",
        type=float,
        default=TUNNEL_PROMPT_DELAY_SECONDS,
    )
    parser.add_argument(
        "--input-travel-prompt-delay",
        type=float,
        default=TRAVEL_PROMPT_DELAY_SECONDS,
    )


def _input_delay_values(args: argparse.Namespace) -> dict[str, float]:
    return {name: getattr(args, name) for name in INPUT_DELAY_DEFAULTS}


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
        if reason == "shop:travel":
            # A rejected symbol selection stays in point_target without
            # consuming a turn.  Do not grant that modal selector the full
            # multi-turn travel window: one share of the existing no-progress
            # allowance is enough to distinguish prompt settling from silence.
            return COMMAND_RESPONSE_GRACE / TOWN_TRAVEL_STALL_LIMIT
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
    # The input cadence above assumes the game no longer discards queued keys,
    # which this pref line is what actually guarantees. Verify it here rather
    # than trusting it: a pref that lost the line must fall back to the slow
    # macro-less path instead of silently typing into a flushing terminal.
    if "\nX:flush_failure\n" not in f"\n{normalized}\n":
        return False
    # A bare Enter at the command loop opens the command menu and can consume a
    # following macro as menu navigation. Keep that menu disabled for BOT_PLAY.
    if "\nX:command_menu\n" not in f"\n{normalized}\n":
        return False
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


def _write_posted_character(
    path: Path | None,
    character: str,
    composed_key: str,
    character_index: int,
    decision: dict | None,
) -> None:
    """Record one successfully posted WM_CHAR, including its decision join."""
    if path is None:
        return
    with path.open("a", encoding="utf-8") as file:
        json.dump(
            {
                "time": datetime.now().astimezone().isoformat(),
                "character": character,
                "character_repr": repr(character),
                "composed_key": composed_key,
                "character_index": character_index,
                "decision": decision,
            },
            file,
            ensure_ascii=False,
        )
        file.write("\n")


def _decision_record(
    snapshot,
    key: str,
    reason: str,
    procurement_requirements: list[dict] | None = None,
    abandoned_quest_carry_requirements: dict[str, str] | None = None,
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
    cross_town_shopping: dict | None = None,
    quest_strategy: dict | None = None,
    escape_ladder: dict | None = None,
    shop_selector: dict | None = None,
    identification_source_reservation: dict | None = None,
    map_memory: dict | None = None,
    descent_refusal: str | None = None,
    home_scan: dict | None = None,
    choke_engagement: dict | None = None,
    town_teleport_refusal: dict | None = None,
    read: dict | None = None,
    town_stall_report: dict | None = None,
    decision_sequence: int | None = None,
    timing: dict | None = None,
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
        "decision_sequence": decision_sequence,
        "turn": snapshot.turn,
        "objective": _objective_for_reason(reason),
        "reason": reason,
        "key": key,
        # Preserve the player-visible evidence associated with the exact board
        # against which this key was chosen.  In particular, repeat counters in
        # the message line let an incident review distinguish a newly rejected
        # command from an older message carried by a later snapshot.
        "messages": list(snapshot.messages),
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
        "abandoned_quest_carry_requirements": (
            abandoned_quest_carry_requirements or {}
        ),
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
        **(
            {"cross_town_shopping": cross_town_shopping}
            if cross_town_shopping
            else {}
        ),
        **({"quest_strategy": quest_strategy} if quest_strategy is not None else {}),
        **({"escape_ladder": escape_ladder} if escape_ladder else {}),
        **({"shop_selector": shop_selector} if shop_selector else {}),
        **(
            {"identification_source_reservation": identification_source_reservation}
            if identification_source_reservation
            else {}
        ),
        "map_memory": map_memory or {},
        **({"descent_refusal": descent_refusal} if descent_refusal else {}),
        **({"home_scan": home_scan} if home_scan else {}),
        **({"choke_engagement": choke_engagement} if choke_engagement else {}),
        **(
            {"town_teleport_refusal": town_teleport_refusal}
            if town_teleport_refusal
            else {}
        ),
        **({"read": read} if read else {}),
        **({"town_stall_report": town_stall_report} if town_stall_report else {}),
        **({"timing": timing} if timing is not None else {}),
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
                    rotate_log(
                        self.path,
                        getattr(self, "rotate_bytes", DEFAULT_LOG_ROTATE_BYTES),
                        getattr(self, "generations", DEFAULT_LOG_GENERATIONS),
                    )
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


def _town_stall_report(
    snapshot,
    policy,
    reason: str,
    repeating_reason_count: int = 0,
    *,
    stopping: bool = False,
) -> dict | None:
    """Describe a repeating town stall without changing policy state."""
    if policy is None or not snapshot.in_town:
        return None
    claims = list(getattr(policy, "_town_claim_categories", ()))
    ledger = getattr(policy, "_town_visit_ledger", None)
    passes = getattr(ledger, "passes_since_progress", 0)
    fallback = (
        reason == "breakout"
        or reason.startswith("breakout:")
        or reason == "explore"
        or reason.startswith("explore:")
        or reason == "stuck:wander"
    )
    named_block = reason.startswith("town:blocked:")
    if not stopping and (
        (fallback and (not claims or passes < EXTENDED_STUCK_WINDOW))
        or not (fallback or named_block)
        or (named_block and repeating_reason_count < EXTENDED_STUCK_WINDOW)
        or (named_block and repeating_reason_count % EXTENDED_STUCK_WINDOW)
        or (fallback and passes % EXTENDED_STUCK_WINDOW)
    ):
        return None

    visit = getattr(policy, "_store_visit", None)
    plan = getattr(policy, "_town_errand_plan", None)
    session = getattr(policy, "_equipment_transaction_session", None)
    selector = getattr(policy, "_shop_selector_diagnostics", {})

    def action_state(action) -> dict | None:
        if action is None:
            return None
        return {
            "phase": action.phase,
            "kind": action.kind,
            "item_id": action.item_id,
            "target_slot": action.target_slot,
        }

    return {
        "trigger": {
            "window": "passes_since_progress",
            "value": passes,
            "cadence": EXTENDED_STUCK_WINDOW,
        },
        "town_claims": claims,
        "store_visit": None if visit is None else {
            "owner": visit.owner,
            "store": visit.store_type,
            "opened_sequence": visit.opened_sequence,
        },
        "town_blocked_reason": getattr(policy, "_town_blocked_reason", None),
        **(
            {
                "repeating_named_block": {
                    "reason": reason,
                    "consecutive_decisions": repeating_reason_count,
                    "out_ranked_candidate": (
                        selector.get("wanted_purchase")
                        or selector.get("considered_candidate")
                    ),
                    "shop_selector": selector,
                }
            }
            if named_block
            else {}
        ),
        "town_plan": None if plan is None else {
            "stops": list(plan.stops),
            "index": plan.index,
        },
        "visit_ledger": {
            "store_visits": dict(getattr(ledger, "store_visits", {})),
            "need_attempts": dict(getattr(ledger, "need_attempts", {})),
            "approach_fails": dict(getattr(ledger, "approach_fails", {})),
            "unsatisfied_passes": dict(
                getattr(ledger, "unsatisfied_passes", {})
            ),
            "blocked_stores": sorted(getattr(ledger, "blocked_stores", ())),
            "passes_since_progress": passes,
        },
        "equipment_transaction": None if session is None else {
            "target_loadout_id": session.target_loadout_id,
            "index": session.index,
            "complete": session.complete,
            "blockers": list(session.blockers),
            "required_context": session.required_context,
            "current_action": action_state(session.current_action),
            "pending_action": action_state(session.pending_action),
        },
        "equipment_transaction_owned_items": [
            list(item)
            for item in getattr(policy, "_equipment_transaction_owned_items", ())
        ],
        "calibration_phase": getattr(policy, "_calibration_phase", None),
        "choke_engagement": policy.choke_engagement_state(),
    }


def _advance_repeating_reason_iteration(
    snapshot,
    policy,
    previous_reason: str | None,
    repeating_reason_count: int,
) -> tuple[str, int, dict | None]:
    """Count one live decision reason and build its town-stall diagnostic."""
    reason = policy.last_reason
    if reason == previous_reason:
        repeating_reason_count += 1
    elif reason.startswith("periodic:") and repeating_reason_count:
        # Periodic CLI housekeeping neither belongs to nor makes progress on a
        # policy stall. Preserve the named-block count across the whole class;
        # the measured character dump is one member, not a special case.
        pass
    else:
        repeating_reason_count = 1
    tracked_reason = (
        previous_reason
        if reason.startswith("periodic:") and previous_reason is not None
        else reason
    )
    return (
        tracked_reason,
        repeating_reason_count,
        _town_stall_report(snapshot, policy, reason, repeating_reason_count),
    )


def _stopping_town_stall_report(
    snapshot,
    policy,
    repeating_reason_count: int,
    blocked_streak: int,
) -> dict | None:
    """Build the diagnostic attached to either town-stall stop path."""
    if (
        blocked_streak < TOWN_BLOCKED_STOP_LIMIT
        and policy.last_reason != "livelock:exhausted"
    ):
        return None
    return _town_stall_report(
        snapshot,
        policy,
        policy.last_reason,
        repeating_reason_count,
        stopping=True,
    )


def _town_stall_report_terminates_named_block(
    report: dict | None, reason: str
) -> bool:
    """Treat the existing named-block report cadence as its terminal bound."""
    return report is not None and reason.startswith("town:blocked:")


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


_AUTO_TOWN_STALL_REPORT = object()


def _write_decision(
    path: Path | None,
    snapshot,
    key: str,
    reason: str,
    policy=None,
    economy_ledger: EconomyLedger | None = None,
    repeating_reason_count: int = 0,
    town_stall_report: dict | None | object = _AUTO_TOWN_STALL_REPORT,
    timing: dict | None = None,
) -> None:
    if economy_ledger is not None:
        economy_ledger.observe(snapshot, key, reason)
    if path is None:
        return
    try:
        rotate_log(
            path,
            getattr(policy, "_recorder_log_rotate_bytes", DEFAULT_LOG_ROTATE_BYTES),
            getattr(policy, "_recorder_log_generations", DEFAULT_LOG_GENERATIONS),
        )
        with path.open("a", encoding="utf-8") as file:
            requirements = (
                policy.procurement_requirements(snapshot) if policy is not None else []
            )
            abandoned_quest_carries = (
                dict(policy._abandoned_quest_carry_requirements)
                if policy is not None
                else {}
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
            cross_town_shopping = (
                policy.cross_town_shopping_state() if policy is not None else {}
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
                    abandoned_quest_carries,
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
                    cross_town_shopping,
                    quest_strategy,
                    (
                        policy.escape_ladder_telemetry
                        if policy is not None
                        else None
                    ),
                    (
                        getattr(policy, "_shop_selector_diagnostics", {})
                        if policy is not None
                        else {}
                    ),
                    (
                        getattr(policy, "_identification_source_reservation", None)
                        if policy is not None
                        else None
                    ),
                    map_memory_summary(policy) if policy is not None else {},
                    (
                        getattr(policy, "_descent_refusal_reason", None)
                        if policy is not None
                        and getattr(policy, "_remembered_downstairs", None)
                        and not reason.startswith("descend")
                        else None
                    ),
                    (
                        {
                            "source": getattr(policy, "_home_scan_source", None),
                            "item_count": getattr(
                                policy, "_home_scan_item_count", None
                            ),
                        }
                        if policy is not None
                        and getattr(policy, "_home_scan_source", None)
                        else None
                    ),
                    (
                        policy.choke_engagement_state()
                        if policy is not None
                        else {}
                    ),
                    (
                        policy.town_teleport_refusal
                        if policy is not None
                        else None
                    ),
                    (
                        policy.read_telemetry
                        if policy is not None
                        else None
                    ),
                    (
                        _town_stall_report(
                            snapshot, policy, reason, repeating_reason_count
                        )
                        if town_stall_report is _AUTO_TOWN_STALL_REPORT
                        else town_stall_report
                    ),
                    getattr(policy, "_decision_sequence", None),
                    timing,
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
    return True


def _posting_effect_signature(snapshot, owner: str, key: str) -> tuple:
    """Project the observable effect relevant to one posted operation.

    In general an effect is observed when a later snapshot changes the turn,
    floor/position, store context, messages, pack, equipment, gold, or recall
    state.  Recall reads are deliberately stricter: only a changed
    ``player.recalling`` value acknowledges that operation, because unrelated
    turn advance must not authorize a second read that cancels the first.
    """
    player = snapshot.player
    recalling = getattr(player, "recalling", None)
    if "recall" in owner and key.startswith("r"):
        return (recalling,)

    def item_state(item):
        return tuple(
            getattr(item, field, None)
            for field in (
                "slot", "tval", "sval", "name", "count", "charges",
                "inscription", "known", "fully_known", "is_equipment",
            )
        )

    store = snapshot.store
    store_state = None if store is None else (
        getattr(store, "store_type", None),
        getattr(store, "stock_num", None),
        getattr(store, "page_top", None),
        tuple(item_state(item) for item in getattr(store, "items", ())),
    )
    position = player.position
    return (
        getattr(snapshot, "turn", None),
        getattr(snapshot, "floor_key", None),
        (position.y, position.x),
        store_state,
        tuple(getattr(snapshot, "messages", ())),
        tuple(item_state(item) for item in snapshot.inventory),
        tuple(item_state(item) for item in snapshot.equipment),
        getattr(player, "gold", None),
        recalling,
    )


def _open_game_prompt(messages) -> str | None:
    """Return the newest serialized interactive prompt, if any."""
    markers = ("[Y/n]", "[y/n]", "[Y/N]", "Quantity", "quantity", "個")
    for message in reversed(tuple(messages)):
        if any(marker in message for marker in markers):
            return message
    return None


class PostingContract:
    """Universal sender-side observation and prompt-ownership contract."""

    def __init__(self) -> None:
        self._posted_by_owner: dict[str, tuple[str, tuple]] = {}
        self._last_posted_owner: str | None = None
        self.last_incident: dict[str, object] | None = None

    @staticmethod
    def _equipment_signature(snapshot) -> tuple:
        return tuple(
            sorted(
                ((
                    getattr(item, "slot", None), getattr(item, "tval", None),
                    getattr(item, "sval", None), getattr(item, "name", None),
                    getattr(item, "count", None), getattr(item, "is_equipment", None),
                ) for item in snapshot.equipment),
                key=repr,
            )
        )

    def allow(self, snapshot, key: str, owner: str) -> bool:
        self.last_incident = None
        prompt = _open_game_prompt(getattr(snapshot, "messages", ()))
        if (
            prompt is not None
            and self._last_posted_owner is not None
            and owner != self._last_posted_owner
        ):
            self.last_incident = {
                "marker": "posting-contract:prompt-owner-mismatch",
                "prompt_owner": self._last_posted_owner,
                "answer_owner": owner,
                "key": key,
                "prompt": prompt,
            }
            return False
        previous = self._posted_by_owner.get(owner)
        effect = _posting_effect_signature(snapshot, owner, key)
        if previous is not None and previous == (key, effect):
            self.last_incident = {
                "marker": "posting-contract:identical-repost-unobserved",
                "owner": owner,
                "key": key,
            }
            return False
        return True

    def posted(self, snapshot, key: str, owner: str) -> None:
        self._posted_by_owner[owner] = (
            key, _posting_effect_signature(snapshot, owner, key)
        )
        self._last_posted_owner = owner


def _write_posting_contract_incident(
    path: Path | None, snapshot, incident: dict[str, object], *, visible: bool = True
) -> None:
    marker = str(incident["marker"])
    if visible:
        print(f"<{marker}> {incident}", file=sys.stderr, flush=True)
    if path is None:
        return
    try:
        with path.open("a", encoding="utf-8") as file:
            json.dump(
                {
                    "time": datetime.now().astimezone().isoformat(),
                    "turn": getattr(snapshot, "turn", None),
                    "reason": marker,
                    "key": "",
                    "contract_incident": incident,
                },
                file,
                ensure_ascii=False,
            )
            file.write("\n")
    except OSError as exc:
        print(f"failed to write decision log: {exc}", file=sys.stderr)


def _freeze_incident_safely(
    recorder, kind: str, policy, snapshot, decision_log: Path | None,
    reasons: list[str],
) -> Path | None:
    """Freeze diagnostics without ever changing gameplay control flow."""
    try:
        capture = recorder.freeze(kind, policy, snapshot, decision_log, reasons)
    except Exception as exc:
        print(f"flight recorder failed to freeze incident: {exc}", file=sys.stderr)
        capture = None
    if capture is None:
        _write_posting_contract_incident(
            decision_log,
            snapshot,
            {
                "marker": "instrument:incident-freeze-failed",
                "incident_kind": kind,
            },
            visible=False,
        )
    return capture


def _send_new_decision_key(
    send,
    snapshot_line: str,
    key: str,
    posted_line: str | None,
    posted_keys: set[str],
    *,
    in_store: bool,
    suppress: bool = False,
    decision: dict | None = None,
    snapshot=None,
    posting_contract: PostingContract | None = None,
) -> tuple[bool, str]:
    """Post each policy key at most once for a byte-identical board."""
    if snapshot_line != posted_line:
        posted_keys.clear()
        posted_line = snapshot_line
    if suppress:
        return False, posted_line
    if not key:
        return False, posted_line
    owner = str((decision or {}).get("reason", "unknown"))
    if (
        posting_contract is not None
        and snapshot is not None
        and not posting_contract.allow(snapshot, key, owner)
    ):
        return False, posted_line
    if key in posted_keys:
        return False, posted_line
    sent = send(key, in_store=in_store, decision=decision)
    if sent:
        posted_keys.add(key)
        if posting_contract is not None and snapshot is not None:
            posting_contract.posted(snapshot, key, owner)
    return sent, posted_line


def _direction_desynchronized(before, key: str, after) -> bool:
    """Detect an adjacent move that differs from its plain direction command."""
    if before is None or key not in DIRECTION_KEYS:
        return False
    if before.floor_key != after.floor_key:
        return False
    start = before.player.position
    end = after.player.position
    dy, dx = end.y - start.y, end.x - start.x
    if (dy, dx) == (0, 0):
        return False
    # Larger displacements are teleports, not evidence about the direction key.
    if max(abs(dy), abs(dx)) != 1:
        return False
    return end != _movement_destination(start, key)


def _look_barrier_allows_decision(complete_lines: list[str]) -> bool:
    """Resume at an ordinary board after look, or make progress if look is lost."""
    decoded_lines = _decode_response_lines(complete_lines)
    eligible_lines, _, _ = _look_barrier_timed_release(
        complete_lines,
        False,
        LOOK_BARRIER_TIMEOUT_SECONDS,
        decoded_lines,
    )
    eligible_decoded_lines = (
        decoded_lines[-len(eligible_lines) :] if eligible_lines else []
    )
    return bool(
        _newest_snapshot_entry(
            eligible_lines, {}, decoded_lines=eligible_decoded_lines
        )
    )


def _look_barrier_release(
    complete_lines: list[str], look_seen: bool = False, decoded_lines=None
) -> tuple[list[str], bool]:
    """Return only lines eligible after the one-shot look consumption barrier."""
    if decoded_lines is None:
        decoded_lines = _decode_response_lines(complete_lines)
    last_look_index = None
    for index, data in enumerate(decoded_lines):
        try:
            response_type = data.get("type")
        except (AttributeError, TypeError):
            continue
        if response_type == "look":
            last_look_index = index
    if last_look_index is not None:
        look_seen = True
        return complete_lines[last_look_index + 1 :], look_seen
    if look_seen:
        return complete_lines, look_seen
    return [], look_seen


def _look_barrier_timed_release(
    complete_lines: list[str], look_seen: bool, elapsed: float, decoded_lines=None
) -> tuple[list[str], bool, bool]:
    """Apply the look barrier, escaping once if its response was lost."""
    eligible_lines, look_seen = _look_barrier_release(
        complete_lines, look_seen, decoded_lines
    )
    timed_out = not look_seen and elapsed >= LOOK_BARRIER_TIMEOUT_SECONDS
    if timed_out:
        eligible_lines = complete_lines
        print("<look-barrier:timeout>", flush=True)
    return eligible_lines, look_seen, timed_out


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


def _stall_recovery_key(
    nudge_streak: int,
    last_player_level: int | None,
    last_snapshot_in_store: bool,
) -> tuple[str, str]:
    if (
        not last_snapshot_in_store
        and last_player_level is not None
        and last_player_level % 10 in (8, 9)
        and nudge_streak >= LEVEL_UP_RECOVERY_START
    ):
        if (nudge_streak - LEVEL_UP_RECOVERY_START) % 2 == 0:
            return LEVEL_UP_STAT_CHOICE, f"<level-stat:{LEVEL_UP_STAT_CHOICE}>"
        return "y", "<level-stat:y>"
    return NUDGE_KEY, "<esc>"


def _send_stall_recovery_nudge(
    send, key: str, posted_keys: set[str], *, in_store: bool = False,
) -> bool:
    """Send one bounded command-loop recovery nudge."""
    sent = send(key)
    if sent:
        posted_keys.clear()
    return sent


def _stall_recovery_action(
    quiet_seconds: float, stall_timeout: float, *, in_store: bool,
    recovery_attempts: int = 0,
    send_failed: bool = False,
) -> str:
    """Choose the transport recovery without bypassing store ownership."""
    if quiet_seconds <= stall_timeout:
        return "wait"
    if in_store:
        if recovery_attempts == 0:
            return "store-escape"
        return "nudge" if send_failed else "wait"
    return "nudge"


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument(
        "--decision-log",
        type=Path,
        help="append structured policy decisions for an external live viewer",
    )
    parser.add_argument(
        "--capture-home-entry",
        action="store_true",
        help="capture diagnostic policy state around home entry",
    )
    parser.add_argument(
        "--capture-latch-onset",
        action="store_true",
        help="capture diagnostic policy state when a latch begins",
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
    parser.add_argument("--poll-interval", type=float, default=0.02)
    parser.add_argument("--send-to-window", action="store_true")
    parser.add_argument("--window-title")
    parser.add_argument("--window-title-contains", action="store_true")
    parser.add_argument("--window-class", default="ANGBAND")
    parser.add_argument("--window-pid", type=int)
    parser.add_argument("--list-windows", action="store_true")
    _add_input_delay_arguments(parser)
    parser.add_argument(
        "--stall-timeout",
        type=float,
        default=1.5,
        help="seconds without a new snapshot before nudging a stuck prompt (0 disables)",
    )
    parser.add_argument(
        "--recorder-budget-bytes",
        type=int,
        default=DEFAULT_DISK_BUDGET_BYTES,
        help="combined jsonlog/ and incident-captures/ flight-recorder budget (default: 3 GiB)",
    )
    parser.add_argument(
        "--recorder-checkpoint-decisions",
        type=int,
        default=DEFAULT_CHECKPOINT_INTERVAL,
        help="write a policy-state checkpoint every N decisions (default: 100)",
    )
    parser.add_argument(
        "--recorder-log-rotate-bytes",
        type=int,
        default=DEFAULT_LOG_ROTATE_BYTES,
        help="rotate decision/economy JSONL after this many bytes (default: 128 MiB)",
    )
    parser.add_argument(
        "--recorder-log-generations",
        type=int,
        default=DEFAULT_LOG_GENERATIONS,
        help="retained rotated generations for decision/economy logs (default: 8)",
    )
    return parser


def _configure_policy_output_paths(policy, args) -> HomeEntryCapture | None:
    if args.decision_log is None:
        return None
    home_entry_capture = (
        HomeEntryCapture(
            args.decision_log.with_name("home-entry-capture.jsonl"),
            DEFAULT_CAPTURE_LOG_ROTATE_BYTES,
            args.recorder_log_generations,
        )
        if args.capture_home_entry
        else None
    )
    policy._home_entry_capture = home_entry_capture
    policy._latch_capture_path = (
        args.decision_log.with_name("latch-onset.jsonl")
        if args.capture_latch_onset
        else None
    )
    policy._latch_capture_rotate_bytes = DEFAULT_CAPTURE_LOG_ROTATE_BYTES
    policy._latch_capture_generations = args.recorder_log_generations
    policy._loadout_report_path = args.decision_log.with_name("loadout-report.jsonl")
    policy._character_calibration_path = args.decision_log.with_name(
        "character-calibration.json"
    )
    policy._confirmed_loadout_path = args.decision_log.with_name(
        "confirmed-loadout.json"
    )
    return home_entry_capture


def main(argv: list[str] | None = None) -> int:
    parser = _build_argument_parser()
    args = parser.parse_args(argv)
    input_delays = _input_delay_values(args)

    if args.economy_log is None and args.decision_log is not None:
        args.economy_log = args.decision_log.with_name("bot-economy.jsonl")
    if args.wait_log is None and args.decision_log is not None:
        args.wait_log = args.decision_log.with_name("bot-waits.json")

    wait_telemetry = WaitTelemetry(args.wait_log if not args.once else None)
    if not args.once:
        wait_telemetry.flush()
    args.wait_telemetry = wait_telemetry

    if args.decision_log is not None and not args.once:
        rotate_log(
            args.decision_log,
            args.recorder_log_rotate_bytes,
            args.recorder_log_generations,
        )
        append_session_marker(
            args.decision_log,
            sys.argv if argv is None else argv,
            input_delays=input_delays,
        )

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

    baseitem_costs: dict[tuple[int, int], int] = {}
    baseitem_path = monrace_path.with_name("BaseitemDefinitions.jsonc")
    if baseitem_path.is_file():
        try:
            baseitem_costs = load_baseitem_costs(baseitem_path)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"could not load base-item definitions ({baseitem_path}): {exc}", file=sys.stderr)

    damaging_terrain_ids: frozenset[int] = frozenset()
    terrain_path = find_terrain_definitions(args.state_file)
    if terrain_path is not None:
        try:
            damaging_terrain_ids = load_damaging_terrain_ids(terrain_path)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"invalid terrain definitions: {exc}", file=sys.stderr)
            return 2

    tunnel_macros_ready = _bot_play_macros_ready(
        args.state_file, monrace_path, args.window_pid
    )

    posted_character_path = (
        args.decision_log.with_name("bot-posted-characters.jsonl")
        if args.decision_log is not None
        else None
    )
    def send(
        key: str, *, in_store: bool = False, decision: dict | None = None
    ) -> bool:
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
                _write_posted_character(
                    posted_character_path, char, key, index, decision
                )
                if decision is not None and home_entry_capture is not None:
                    try:
                        home_entry_capture.record_posted_character(
                            decision["sequence"], char
                        )
                    except (KeyError, TypeError) as exc:
                        home_entry_capture.report_failure(
                            "record_posted_character", exc,
                            "decision.sequence/character",
                        )
                delay, wait_category = (
                    _delay_spec_after_macro_key(
                        key,
                        index,
                        in_store=in_store,
                        input_delays=input_delays,
                    )
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
        damaging_terrain_ids=damaging_terrain_ids,
        quest_knowledge=quest_knowledge,
        quest_strategies=quest_strategies,
        exploration_ledger_path=EXPLORATION_LEDGER_PATH,
        baseitem_costs=baseitem_costs,
    )
    policy._recorder_log_rotate_bytes = args.recorder_log_rotate_bytes
    policy._recorder_log_generations = args.recorder_log_generations
    posting_contract = PostingContract()
    home_entry_capture = _configure_policy_output_paths(policy, args)

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
            key = policy.validate_read_key(snapshot, key)
            _write_decision(args.decision_log, snapshot, key, policy.last_reason, policy)
            print(key, flush=True)
            decision = {
                "sequence": policy._decision_sequence,
                "turn": snapshot.turn,
                "reason": policy.last_reason,
                "key": key,
            }
            if not posting_contract.allow(snapshot, key, policy.last_reason):
                _write_posting_contract_incident(
                    args.decision_log, snapshot, posting_contract.last_incident
                )
                return 3
            if not send(
                key, in_store=snapshot.store is not None, decision=decision
            ):
                return 3
            posting_contract.posted(snapshot, key, policy.last_reason)
            policy.confirm_key_posted(key)
            return 0
        return 1

    try:
        return _run_follow(
            args, policy, send, monrace_knowledge, home_entry_capture,
            posting_contract,
        )
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
    except Exception:
        recorder = getattr(args, "flight_recorder", None)
        snapshot = getattr(args, "last_snapshot", None)
        if recorder is not None and snapshot is not None:
            _freeze_incident_safely(
                recorder, "unhandled-exception", policy, snapshot,
                args.decision_log, [getattr(policy, "last_reason", "unknown")],
            )
        raise


def _run_follow(
    args, policy, send, monrace_knowledge, home_entry_capture=None,
    posting_contract: PostingContract | None = None,
) -> int:
    path = args.state_file
    wait_telemetry: WaitTelemetry = args.wait_telemetry
    recorder_root = (
        args.decision_log.parent if args.decision_log is not None else Path("jsonlog")
    )
    recorder = FlightRecorder(
        recorder_root,
        recorder_root.parent / "incident-captures",
        budget_bytes=args.recorder_budget_bytes,
        checkpoint_interval=args.recorder_checkpoint_decisions,
    )
    args.flight_recorder = recorder
    save_archive = SaveArchiveCoordinator(
        log=lambda message: print(message, file=sys.stderr, flush=True)
    )
    recent_reasons: deque[str] = deque(maxlen=20)
    if posting_contract is None:
        posting_contract = PostingContract()
    batch_seq = 0
    pending_batch_row = None
    last_observed_home_page = None

    def finish_pending_batch() -> None:
        nonlocal pending_batch_row
        if pending_batch_row is not None:
            _append_capture_ledger(
                READ_BATCH_LEDGER_PATH,
                pending_batch_row,
                args.recorder_log_rotate_bytes,
                args.recorder_log_generations,
            )
            pending_batch_row = None

    def incident_stop(kind: str, snapshot) -> int:
        finish_pending_batch()
        _freeze_incident_safely(
            recorder,
            kind, policy, snapshot, args.decision_log, list(recent_reasons)
        )
        return 0

    while not path.exists():
        time.sleep(args.poll_interval)

    initial_snapshot = _newest_snapshot(
        list(_read_last_line(path)), monrace_knowledge
    )
    try:
        recorder.record_snapshot_lines(
            path.read_text(encoding="utf-8", errors="replace").splitlines()
        )
    except OSError as exc:
        print(f"flight recorder failed to seed snapshot history: {exc}", file=sys.stderr)
    if initial_snapshot is not None:
        policy.prime(initial_snapshot)
        args.last_snapshot = initial_snapshot
        if (
            initial_snapshot.store is not None
            and initial_snapshot.store.store_type == STORE_HOME
        ):
            last_observed_home_page = (initial_snapshot.store, initial_snapshot.turn)
    snapshot = initial_snapshot
    economy_ledger = EconomyLedger(args.economy_log)
    economy_ledger.rotate_bytes = args.recorder_log_rotate_bytes
    economy_ledger.generations = args.recorder_log_generations
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
        recovery_send_failed = False
        last_player_level = initial_snapshot.player.level if initial_snapshot is not None else None
        # (floor_key, y, x) of the last LOOP_WINDOW decisions, for loop detection.
        recent_cells: deque[tuple] = deque(maxlen=MULTIPLIER_COMBAT_LOOP_WINDOW)
        multiplier_combat_grace = 0
        last_decision_line: str | None = None
        last_decision_reason: str | None = None
        repeating_reason_count = 0
        last_decision_at = 0.0
        posted_decision_line: str | None = None
        posted_decision_keys: set[str] = set()
        pending_action_wait: tuple[str, float] | None = None
        stalled_command_count = 0
        blocked_streak = 0
        town_blocked_durable_state = (
            policy._town_workflow_progress_state(initial_snapshot)
            if initial_snapshot is not None
            else None
        )
        town_residence_streak = 0
        residence_floor_key = None
        starving_streak = 0
        starving_last_position = None
        cell_guard_last_position = None
        last_snapshot_floor_key = (
            initial_snapshot.floor_key if initial_snapshot is not None else None
        )
        last_command_signature: tuple | None = None
        pending_chest_movement: tuple[
            tuple[int, int, int], object, object, float
        ] | None = None
        pending_direction: tuple[object, str] | None = None
        look_barrier_pending: str | None = None
        look_barrier_seen = False
        look_barrier_started_at = 0.0
        next_dump_at = time.monotonic() + DUMP_INTERVAL_SECONDS
        poll_wait_started_at = time.perf_counter()
        while True:
            finish_pending_batch()
            _arm_decision_watchdog()
            save_archive.poll(time.monotonic())
            if poll_wait_started_at is None:
                poll_wait_started_at = time.perf_counter()
            read_started_at = time.perf_counter()
            chunk = file.read()
            read_finished_at = time.perf_counter()
            if chunk:
                batch_seq += 1
                decision_started_at = read_finished_at
                decision_timing = {
                    "read_ms": round(
                        (read_finished_at - read_started_at) * 1000, 3
                    ),
                    "batch_bytes": len(chunk),
                    "poll_wait_ms": round(
                        (read_started_at - poll_wait_started_at) * 1000, 3
                    ),
                    "record_snapshot_lines_ms": 0.0,
                    "decode_ms": 0.0,
                    "parse_snapshot_ms": 0.0,
                    "choose_key_ms": 0.0,
                    "send_ms": 0.0,
                }
                poll_wait_started_at = None
                last_activity = _last_activity_after_read(
                    last_activity, time.monotonic(), chunk
                )
                complete_lines, pending = _split_complete_lines(pending + chunk)
                phase_started_at = time.perf_counter()
                recorder.record_snapshot_lines(complete_lines)
                decision_timing["record_snapshot_lines_ms"] = round(
                    (time.perf_counter() - phase_started_at) * 1000, 3
                )
                phase_started_at = time.perf_counter()
                decoded_lines = _decode_response_lines(complete_lines)
                decision_timing["decode_ms"] = round(
                    (time.perf_counter() - phase_started_at) * 1000, 3
                )
                pending_batch_row = {
                    "time": datetime.now().isoformat(),
                    "batch_seq": batch_seq,
                    "line_count": len(complete_lines),
                    "line_turns": [
                        row.get("turn") if isinstance(row, dict) else None
                        for row in decoded_lines
                    ],
                    "line_types": [
                        row.get("type") if isinstance(row, dict) else None
                        for row in decoded_lines
                    ],
                    "decided": False,
                    "posted_key": None,
                }
                needs_ordered_snapshots = (
                    home_entry_capture is not None
                    and home_entry_capture.pending is not None
                )
                decoded_lines, all_ordered_snapshot_entries = (
                    _consume_response_sequence(
                        complete_lines, policy, send, monrace_knowledge,
                        decoded_lines=decoded_lines,
                        parse_snapshots=needs_ordered_snapshots,
                    )
                )
                ordered_snapshot_entries = (
                    all_ordered_snapshot_entries
                    if needs_ordered_snapshots
                    else []
                )
                _observe_home_entry_capture(
                    home_entry_capture, ordered_snapshot_entries
                )
                # Act ONLY on the newest complete snapshot in this batch. The game
                # emits a snapshot then blocks on request_command, so the file's
                # newest line is ALWAYS the current board the game is waiting on;
                # any older lines in the same read are prompts a fast monster raced
                # us past. The old code answered every line, posting one key per
                # stale board, so the key stream lagged the game by a step and
                # "step onto the monster" (an attack) degraded into a side-step —
                # a speed-118 archer shot a full-HP character to death while it
                # merely circled the archer, whose HP never dropped. Acting on the
                # newest line keeps batches from manufacturing stale commands.
                # It cannot heal a surplus key already in the Windows input queue:
                # that reaches a stable one-command-behind equilibrium. Direction
                # acknowledgements below detect that state and drain it through
                # the existing look channel. Byte-identical boards are decided
                # again so policy loop breakers advance, but their already-posted
                # keys are suppressed at the send boundary below.
                if look_barrier_pending is not None:
                    (
                        eligible_lines,
                        look_barrier_seen,
                        look_barrier_timed_out,
                    ) = _look_barrier_timed_release(
                        complete_lines,
                        look_barrier_seen,
                        time.monotonic() - look_barrier_started_at,
                        decoded_lines,
                    )
                    eligible_decoded_lines = (
                        decoded_lines[-len(eligible_lines) :]
                        if eligible_lines
                        else []
                    )
                    entry = _newest_snapshot_entry(
                        eligible_lines,
                        monrace_knowledge,
                        decoded_lines=eligible_decoded_lines,
                        timing=decision_timing,
                    )
                    if entry is None:
                        continue
                    look_barrier_pending = None
                    look_barrier_seen = False
                    look_barrier_started_at = 0.0
                else:
                    entry = _newest_snapshot_entry(
                        complete_lines,
                        monrace_knowledge,
                        decoded_lines=decoded_lines,
                        timing=decision_timing,
                    )
                if entry is not None:
                    snapshot, snapshot_line = entry
                    floor_changed = _floor_transition_needs_prompt_clear(
                        last_snapshot_floor_key, snapshot.floor_key
                    )
                    # A different store or floor proves the retained Home page
                    # is no longer the applicable context.  Merely leaving Home
                    # does not: atomic-withdraw composition happens on the next
                    # town snapshot, and observed_turn exposes the page's age.
                    last_observed_home_page = _retained_home_page(
                        last_observed_home_page,
                        snapshot,
                        floor_changed=floor_changed,
                    )
                    args.last_snapshot = snapshot
                    # A snapshot means the game is alive and awaiting a command.
                    nudge_streak = 0
                    recovery_send_failed = False
                    last_player_level = snapshot.player.level
                    now = time.monotonic()
                    last_activity = now
                    if pending_direction is not None:
                        command_snapshot, command_key = pending_direction
                        pending_direction = None
                        if _direction_desynchronized(
                            command_snapshot, command_key, snapshot
                        ):
                            barrier_key = policy._look_probe_key(snapshot)
                            print("<input-desync:look-barrier>", flush=True)
                            if send(
                                barrier_key,
                                in_store=snapshot.store is not None,
                            ):
                                look_barrier_pending = "desync"
                                look_barrier_seen = False
                                look_barrier_started_at = time.monotonic()
                            last_activity = time.monotonic()
                            continue
                    if floor_changed:
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
                    duplicate_ready = _duplicate_snapshot_ready(
                        snapshot_line,
                        last_decision_line,
                        last_decision_reason,
                    )
                    if not duplicate_ready:
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
                    recorder.before_floor_change(policy, snapshot.floor_key)
                    store_leave_was_inflight = (
                        policy._store_leave_inflight is not None
                    )
                    phase_started_at = time.perf_counter()
                    chosen_key = policy.choose_key(snapshot)
                    _record_atomic_home_page(
                        policy, snapshot, observed_store=last_observed_home_page
                    )
                    decision_timing["choose_key_ms"] = round(
                        (time.perf_counter() - phase_started_at) * 1000, 3
                    )
                    key = policy.validate_read_key(snapshot, chosen_key)
                    pending_batch_row["decided"] = True
                    suppress_unconfirmed_store_leave = (
                        store_leave_was_inflight
                        and policy._store_leave_inflight is not None
                    )
                    (
                        last_decision_reason,
                        repeating_reason_count,
                        town_stall_report,
                    ) = _advance_repeating_reason_iteration(
                        snapshot,
                        policy,
                        last_decision_reason,
                        repeating_reason_count,
                    )
                    # Diagnose on the existing 24-decision window before the
                    # 30-decision town-block fuse can stop any counted shape.
                    blocked_streak, town_blocked_durable_state = (
                        _advance_town_blocked_iteration(
                            policy,
                            snapshot,
                            blocked_streak,
                            town_blocked_durable_state,
                            key=key,
                            floor_changed=floor_changed,
                        )
                    )
                    # A named block report is emitted only after the existing
                    # extended no-progress cadence has matured.  At that point
                    # another WAIT cannot discover new work: make the report's
                    # ledger-backed terminal authoritative instead of letting
                    # an escape-budget exemption post WAIT indefinitely.
                    if _town_stall_report_terminates_named_block(
                        town_stall_report, policy.last_reason
                    ):
                        blocked_streak = TOWN_BLOCKED_STOP_LIMIT
                    stopping_town_stall_report = _stopping_town_stall_report(
                        snapshot,
                        policy,
                        repeating_reason_count,
                        blocked_streak,
                    )
                    if stopping_town_stall_report is not None:
                        town_stall_report = stopping_town_stall_report
                    if policy.last_reason == "periodic:game-save":
                        save_archive.before_post(snapshot, policy._decision_sequence)
                    recent_reasons.append(policy.last_reason)
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
                            timing={
                                **decision_timing,
                                "total_ms": round(
                                    (time.perf_counter() - decision_started_at) * 1000,
                                    3,
                                ),
                            },
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
                        return incident_stop("loop-detected", snapshot)
                    if policy.last_reason in POLICY_FINAL_STOP_REASONS:
                        _write_decision(
                            args.decision_log, snapshot, key, policy.last_reason,
                            policy, economy_ledger, repeating_reason_count,
                            town_stall_report,
                            timing={
                                **decision_timing,
                                "total_ms": round(
                                    (time.perf_counter() - decision_started_at) * 1000,
                                    3,
                                ),
                            },
                        )
                        if policy.last_reason == "wilderness:no-safe-route":
                            print(
                                "<wilderness:no-safe-route> global-map route to "
                                "town is unavailable; stopping the bot for "
                                "investigation",
                                flush=True,
                            )
                        else:
                            print(
                                "<equipment-transaction:restore-blocked-terminal> "
                                "recoverable gear restored; missing owned items "
                                "remain; stopping the bot for investigation",
                                flush=True,
                            )
                        return incident_stop(policy.last_reason, snapshot)
                    recorder.after_decision(policy, snapshot)
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
                        return incident_stop("loop-detected", snapshot)
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
                        return incident_stop("livelock-exhausted", snapshot)
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
                        return incident_stop("loop-detected", snapshot)
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
                        return incident_stop("loop-detected", snapshot)
                    if suppress_unconfirmed_store_leave:
                        print("<store-leave-key:suppressed>", flush=True)
                    elif (
                        snapshot_line == posted_decision_line
                        and key in posted_decision_keys
                    ):
                        print(f"<duplicate-key:suppressed> {key}", flush=True)
                    else:
                        print(key, flush=True)
                    phase_started_at = time.perf_counter()
                    sent, posted_decision_line = _send_new_decision_key(
                        send,
                        snapshot_line,
                        key,
                        posted_decision_line,
                        posted_decision_keys,
                        in_store=snapshot.store is not None,
                        suppress=suppress_unconfirmed_store_leave,
                        decision={
                            "sequence": policy._decision_sequence,
                            "turn": snapshot.turn,
                            "reason": policy.last_reason,
                            "key": key,
                        },
                        snapshot=snapshot,
                        posting_contract=posting_contract,
                    )
                    pending_batch_row["posted_key"] = key if sent else None
                    decision_timing["send_ms"] = round(
                        (time.perf_counter() - phase_started_at) * 1000, 3
                    )
                    decision_timing["total_ms"] = round(
                        (time.perf_counter() - decision_started_at) * 1000, 3
                    )
                    poll_wait_started_at = time.perf_counter()
                    _write_decision(
                        args.decision_log, snapshot, key, policy.last_reason,
                        policy, economy_ledger, repeating_reason_count,
                        town_stall_report, timing=decision_timing,
                    )
                    if posting_contract.last_incident is not None:
                        incident = posting_contract.last_incident
                        _write_posting_contract_incident(
                            args.decision_log,
                            snapshot,
                            incident,
                        )
                        _freeze_incident_safely(
                            recorder, str(incident["marker"]), policy, snapshot,
                            args.decision_log, list(recent_reasons),
                        )
                        policy.refuse_key_posting(
                            str(incident.get(
                                "owner",
                                incident.get("answer_owner", policy.last_reason),
                            )),
                            str(incident.get("key", key)),
                        )
                        phase_started_at = time.perf_counter()
                        key = policy.choose_key(snapshot)
                        decision_timing["choose_key_ms"] += round(
                            (time.perf_counter() - phase_started_at) * 1000, 3
                        )
                        key = policy.validate_read_key(snapshot, key)
                        phase_started_at = time.perf_counter()
                        sent, posted_decision_line = _send_new_decision_key(
                            send, snapshot_line, key, posted_decision_line,
                            posted_decision_keys,
                            in_store=snapshot.store is not None,
                            decision={
                                "sequence": policy._decision_sequence,
                                "turn": snapshot.turn,
                                "reason": policy.last_reason,
                                "key": key,
                            },
                            snapshot=snapshot,
                            posting_contract=posting_contract,
                        )
                        pending_batch_row["posted_key"] = key if sent else None
                        decision_timing["send_ms"] = round(
                            decision_timing["send_ms"]
                            + (time.perf_counter() - phase_started_at) * 1000,
                            3,
                        )
                        decision_timing["total_ms"] = round(
                            (time.perf_counter() - decision_started_at) * 1000, 3
                        )
                        poll_wait_started_at = time.perf_counter()
                        _write_decision(
                            args.decision_log, snapshot, key, policy.last_reason,
                            policy, economy_ledger, timing=decision_timing,
                        )
                    if sent:
                        policy.confirm_key_posted(key)
                        if policy.last_reason == "periodic:game-save":
                            save_archive.posted(time.monotonic())
                    last_activity = time.monotonic()
                    if sent and key in DIRECTION_KEYS:
                        pending_direction = (snapshot, key)
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
                    # not break the streak).  Filler actions such as restock
                    # waits and wandering do not erase blocked evidence either:
                    # only observed town-workflow progress resets the fuse.
                    if blocked_streak >= TOWN_BLOCKED_STOP_LIMIT:
                        print(
                            f"<loop-detected> floor={snapshot.floor_key} "
                            f"turn={snapshot.turn} town blocked "
                            f"({policy.last_reason}) for {blocked_streak} "
                            "decisions; stopping the bot for investigation",
                            flush=True,
                        )
                        return incident_stop("loop-detected", snapshot)
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
                    previous_position = cell_guard_last_position
                    cell_guard_last_position = snapshot.player.position
                    if not _cell_loop_guard_applies(
                        snapshot, policy.last_reason, previous_position
                    ):
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
                            timing={
                                **decision_timing,
                                "total_ms": round(
                                    (time.perf_counter() - decision_started_at) * 1000,
                                    3,
                                ),
                            },
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
                        return incident_stop("loop-detected", snapshot)
                continue

            # The emitter truncates the JSONL at game start and when it reaches
            # its size limit. Rewind after either shrink so the reader is not
            # stranded beyond the new EOF.
            if _rewind_if_truncated(file, args.state_file):
                pending = ""
                nudge_streak = 0
                recovery_send_failed = False
                continue

            # No new snapshot. If the game has gone quiet for too long it is
            # probably blocked on a message/"-more-" prompt that emits no
            # snapshot; nudge it with Escape to get back to the command loop.
            now = time.monotonic()
            recovery_action = _stall_recovery_action(
                now - last_activity,
                args.stall_timeout,
                in_store=snapshot is not None and snapshot.store is not None,
                recovery_attempts=nudge_streak,
                send_failed=recovery_send_failed,
            )
            if (
                args.send_to_window
                and args.stall_timeout > 0
                and now >= quiet_ok_until
                and recovery_action != "wait"
            ):
                recovery_key, recovery_marker = _stall_recovery_key(
                    nudge_streak,
                    last_player_level,
                    snapshot is not None and snapshot.store is not None,
                )
                recovery_sent = _send_stall_recovery_nudge(
                    send,
                    recovery_key,
                    posted_decision_keys,
                    in_store=False,
                )
                recovery_send_failed = not recovery_sent
                if recovery_sent:
                    print(
                        "<instrument:store-one-shot-abort-escape>"
                        if recovery_action == "store-escape"
                        else recovery_marker,
                        flush=True,
                    )
                last_activity = now
                # A refused store recovery never reaches this branch.  Outside
                # a store, both a successful post and a vanished-window send
                # failure are bounded recovery attempts; the latter must still
                # arm terminal dead-window detection.
                nudge_streak += 1
                # Nudges that never bring back a snapshot mean a screen outside
                # the command loop. That is DEATH only if the game process is
                # actually winding down — a store/sale prompt chain that ate the
                # nudges looks identical from here, and concluding <dead> on it
                # abandoned a healthy character twice (game alive, HP full). So:
                # blast the exit keys, then look at the PROCESS. Gone -> death,
                # exit. Still alive -> the blast doubled as prompt clearing;
                # resync and keep playing.
                if (
                    nudge_streak >= TERMINAL_NUDGE_LIMIT
                    and args.send_to_window
                ):
                    if nudge_streak == TERMINAL_NUDGE_LIMIT:
                        for _ in range(DEATH_EXIT_ROUNDS):
                            for exit_key in DEATH_EXIT_KEYS:
                                send(exit_key, decision={
                                    "sequence": None,
                                    "turn": getattr(snapshot, "turn", None),
                                    "reason": "recovery:terminal-resync",
                                    "key": exit_key,
                                })
                                started = time.monotonic()
                                time.sleep(0.3)
                                wait_telemetry.record(
                                    "recovery:terminal-key-gap",
                                    time.monotonic() - started,
                                )
                        started = time.monotonic()
                        time.sleep(2.0)
                        wait_telemetry.record(
                            "recovery:shutdown-grace",
                            time.monotonic() - started,
                            force_flush=True,
                        )
                        if _silent_game_incident(args.window_pid) == "player-death":
                            print("<dead>", flush=True)
                            return incident_stop("player-death", snapshot)
                        print(
                            "<stuck-prompt> terminal resync exhausted; game "
                            "process alive",
                            flush=True,
                        )
                        continue
                    if _modal_recovery_action(nudge_streak) == "esc-look":
                        # This recovery must not consume or invalidate policy's
                        # floor-look state.  A store can interpret `l` as a menu
                        # command, so only Escape is modal-safe there.
                        probe = NUDGE_KEY if snapshot is not None and snapshot.store is not None else NUDGE_KEY + "l" + NUDGE_KEY
                        send(probe, in_store=False, decision={
                            "sequence": None,
                            "turn": getattr(snapshot, "turn", None),
                            "reason": "recovery:stuck-prompt-probe",
                            "key": probe,
                        })
                        print("<stuck-prompt:esc-look-probe>", flush=True)
                        time.sleep(args.poll_interval)
                        continue
                    print(
                        "<stuck-prompt:modal-recovery-exhausted> ESC/look "
                        "probes produced no batch; stopping bot "
                        "(game left running)",
                        file=sys.stderr,
                        flush=True,
                    )
                    if _silent_game_incident(args.window_pid) == "player-death":
                        print("<dead>", flush=True)
                        return incident_stop("player-death", snapshot)
                    return incident_stop("stuck-prompt", snapshot)

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


def _snapshot_entries_in_order(
    complete_lines: list[str], monrace_knowledge=None, *, decoded_lines=None
) -> list:
    """Parse ordinary board snapshots in file order without deciding on them."""
    if decoded_lines is None:
        decoded_lines = _decode_response_lines(complete_lines)
    snapshots = []
    for line, data in zip(complete_lines, decoded_lines):
        if not line.strip():
            continue
        if isinstance(data, Exception):
            print(f"invalid snapshot: {data}", file=sys.stderr)
            continue
        try:
            if data.get("type") in {"knowledge", "look", "character"}:
                continue
            snapshots.append(parse_snapshot(data, monrace_knowledge))
        except MissingMonraceKnowledgeError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"invalid snapshot: {exc}", file=sys.stderr)
    return snapshots


def _observe_home_entry_capture(home_entry_capture, ordered_snapshots) -> None:
    """Give the capture the first real Snapshot parsed in this CLI read."""
    if home_entry_capture is None or not ordered_snapshots:
        return
    try:
        home_entry_capture.observe_snapshot(ordered_snapshots[0])
    except Exception as exc:
        # Capture must never alter command selection or delivery.
        home_entry_capture.report_failure(
            "observe_snapshot", exc, "next snapshot"
        )


def _retained_home_page(previous, snapshot, *, floor_changed: bool):
    """Retain replay evidence until a transition makes its context unknowable."""
    if floor_changed:
        previous = None
    if snapshot.store is None:
        return previous
    if snapshot.store.store_type == STORE_HOME:
        return snapshot.store, snapshot.turn
    return None


def _newest_snapshot_entry(
    complete_lines: list[str], monrace_knowledge=None, *, decoded_lines=None,
    timing=None,
):
    """Return the newest parseable snapshot together with its exact JSONL line."""
    if decoded_lines is None:
        decoded_lines = _decode_response_lines(complete_lines)
    for line, data in reversed(list(zip(complete_lines, decoded_lines))):
        if not line.strip():
            continue
        if isinstance(data, Exception):
            print(f"invalid snapshot: {data}", file=sys.stderr)
            continue
        try:
            if data.get("type") in {"knowledge", "look", "character"}:
                continue
            parse_started_at = time.perf_counter()
            snapshot = parse_snapshot(data, monrace_knowledge)
            if timing is not None:
                timing["parse_snapshot_ms"] = round(
                    (time.perf_counter() - parse_started_at) * 1000, 3
                )
                timing["snapshot_bytes"] = len(line.encode("utf-8"))
                timing["nearby_grids"] = len(data.get("nearby_grids", ()))
            return snapshot, line
        except MissingMonraceKnowledgeError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"invalid snapshot: {exc}", file=sys.stderr)
    return None


def _decode_response_lines(complete_lines):
    """Decode each complete JSONL line once for all consumers in one read."""
    decoded_lines = []
    for line in complete_lines:
        if not line.strip():
            decoded_lines.append(None)
            continue
        try:
            decoded_lines.append(json.loads(line))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            decoded_lines.append(exc)
    return decoded_lines


def _append_capture_ledger(
    path: Path, row: Mapping, rotate_bytes=DEFAULT_LOG_ROTATE_BYTES,
    generations=DEFAULT_LOG_GENERATIONS,
) -> None:
    """Append one bounded instrumentation row without affecting play."""
    try:
        rotate_log(path, rotate_bytes, generations)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")
    except (OSError, TypeError, ValueError) as exc:
        print(f"capture ledger failed to append {path}: {exc}", file=sys.stderr)


def _capture_item_rows(items, *, page_size=None, page_top=0, limit=256):
    """Project a bounded, replay-oriented view of Home item addresses."""
    size = page_size if isinstance(page_size, int) and page_size > 0 else None
    top = page_top if isinstance(page_top, int) and page_top >= 0 else 0
    rows = []
    for offset, item in enumerate(tuple(items)[:limit]):
        absolute = top + offset
        page_pos = absolute % size if size is not None else None
        composer_letter = None
        if page_pos is not None:
            composer_letter = (
                chr(ord("a") + page_pos)
                if page_pos < 26
                else chr(ord("A") + page_pos - 26)
            )
        rows.append({
            "letter": getattr(item, "letter", getattr(item, "slot", None)),
            "name": getattr(item, "name", None),
            "page": absolute // size if size is not None else None,
            "index": absolute,
            "composer_letter": composer_letter,
        })
    return rows


def _record_atomic_home_page(policy, snapshot, *, observed_store=None, path=None):
    reason = getattr(policy, "last_reason", "")
    if not reason.startswith("home:atomic-withdraw"):
        return
    observed_turn = None
    if isinstance(observed_store, tuple):
        store, observed_turn = observed_store
    else:
        store = observed_store or getattr(snapshot, "store", None)
        if store is getattr(snapshot, "store", None) and store is not None:
            observed_turn = getattr(snapshot, "turn", None)
    items = getattr(store, "items", ()) if store is not None else ()
    _append_capture_ledger(
        path or KNOWLEDGE_RESPONSE_LEDGER_PATH,
        {
            "time": datetime.now().isoformat(),
            "turn": getattr(snapshot, "turn", None),
            "observed_turn": observed_turn,
            "category": "home-atomic-withdraw-page",
            "reason": reason,
            "page_top": getattr(store, "page_top", None),
            "page_size": getattr(store, "page_size", None),
            "items": _capture_item_rows(
                items,
                page_size=getattr(store, "page_size", None),
                page_top=getattr(store, "page_top", 0),
            ),
        },
        getattr(policy, "_recorder_log_rotate_bytes", DEFAULT_LOG_ROTATE_BYTES),
        getattr(policy, "_recorder_log_generations", DEFAULT_LOG_GENERATIONS),
    )


def _dispatch_response_lines(
    complete_lines, policy, send, *, decoded_lines=None,
    knowledge_ledger_path: Path | None = None,
) -> int:
    """Consume requested menu responses without treating them as board states."""
    if decoded_lines is None:
        decoded_lines = _decode_response_lines(complete_lines)
    consumed = 0
    for line, data in zip(complete_lines, decoded_lines):
        if not line.strip():
            continue
        try:
            response_type = data.get("type")
        except (AttributeError, TypeError):
            continue
        if response_type not in {"knowledge", "look", "character"}:
            continue
        consumed += 1
        knowledge = data.get("knowledge")
        inflight_at_arrival = bool(
            getattr(policy, "_home_knowledge_scan_inflight", False)
        )
        requested_home_knowledge = (
            response_type == "knowledge"
            and isinstance(knowledge, dict)
            and knowledge.get("category") == "home"
            and knowledge.get("menu_key") == "9"
            and getattr(policy, "_home_knowledge_scan_inflight", False)
        )
        if response_type == "knowledge" and isinstance(knowledge, dict):
            knowledge_items = knowledge.get("items", ())
            parsed_knowledge_items = tuple(_parse_items(knowledge_items))
            _append_capture_ledger(
                knowledge_ledger_path or KNOWLEDGE_RESPONSE_LEDGER_PATH,
                {
                    "time": datetime.now().isoformat(),
                    "turn": data.get("turn"),
                    "category": knowledge.get("category"),
                    "menu_key": knowledge.get("menu_key"),
                    "item_count": len(knowledge_items) if isinstance(
                        knowledge_items, (list, tuple)
                    ) else 0,
                    "accepted": requested_home_knowledge,
                    "inflight_at_arrival": inflight_at_arrival,
                    "items": _capture_item_rows(
                        parsed_knowledge_items,
                        page_size=getattr(policy, "_home_page_size", None),
                    ) if knowledge.get("category") == "home" else [],
                },
                getattr(policy, "_recorder_log_rotate_bytes", DEFAULT_LOG_ROTATE_BYTES),
                getattr(policy, "_recorder_log_generations", DEFAULT_LOG_GENERATIONS),
            )
        if requested_home_knowledge:
            policy.consume_home_knowledge(parsed_knowledge_items)
            send(NUDGE_KEY + NUDGE_KEY)
        elif response_type == "character":
            character = data.get("character")
            if isinstance(character, dict) and hasattr(
                policy, "observe_character_snapshot"
            ):
                # Every `C` status snapshot — the calibration capture's naked
                # dump and the pre-existing periodic liveness dump alike —
                # carries the mutation id set and the characteristics table.
                # The policy records the observation; no nudge, no request
                # state beyond the capture-phase latch it owns itself.
                policy.observe_character_snapshot(character)
        elif response_type == "look" and getattr(policy, "_look_probe_inflight", False):
            policy.consume_look(data)
    return consumed


def _consume_response_sequence(
    complete_lines, policy, send, monrace_knowledge=None, *, decoded_lines=None,
    parse_snapshots=True, batch_ledger=None, knowledge_ledger_path=None,
    batch_callback=None,
):
    """Deliver every JSONL record through the live response consumption path."""
    if batch_ledger is not None:
        if isinstance(batch_ledger, (str, Path)):
            batch_rows = [
                json.loads(line)
                for line in Path(batch_ledger).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            batch_rows = list(batch_ledger)
        offset = 0
        all_decoded = []
        all_snapshots = []
        for batch in batch_rows:
            count = int(batch["line_count"])
            group = complete_lines[offset : offset + count]
            offset += count
            group_decoded, group_snapshots = _consume_response_sequence(
                group, policy, send, monrace_knowledge,
                parse_snapshots=parse_snapshots,
                knowledge_ledger_path=knowledge_ledger_path,
            )
            all_decoded.extend(group_decoded)
            all_snapshots.extend(group_snapshots)
            if batch_callback is not None:
                batch_callback(group_decoded, group_snapshots)
        if offset != len(complete_lines):
            raise ValueError("batch ledger line counts do not cover the response sequence")
        return all_decoded, all_snapshots
    if decoded_lines is None:
        decoded_lines = _decode_response_lines(complete_lines)
    _dispatch_response_lines(
        complete_lines, policy, send, decoded_lines=decoded_lines,
        knowledge_ledger_path=knowledge_ledger_path,
    )
    snapshots = (
        _snapshot_entries_in_order(
            complete_lines, monrace_knowledge, decoded_lines=decoded_lines
        )
        if parse_snapshots else []
    )
    return decoded_lines, snapshots


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
