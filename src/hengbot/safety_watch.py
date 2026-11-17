"""The "is it safe now" gates, one table, and a record-only watcher of where they differ.

Owner 2026-11-15 (maintainability review Q9 「差は残し表で説明する」, the review's stage 6 first): the
dungeon's gates that wait for a quiet moment each read their own facts, and they differ.  The
differences are kept; this table says what each gate reads beyond the strictest one
(safety_facts ``strict_quiet``, junk_destroy_now's) and why.  The watcher records, on every
decision, each gate's answer beside the board's facts (safety_facts ``of``) and the strict
reading, so a replay measures which differences take effect (a gate saying safe where the strict
reading does not, or the reverse).  Nothing here is read by a decision; nothing is stored on
the policy (the ledger is the process's, cleared at each ``choose_key``).

The gates (``GATES``: name -> what it reads beyond / instead of the strict reading, and why).

Measured 2026-11-16 (the dungeon boards of tests/fixtures, 160 files, 1,764 decisions, 30 each):
the differences that took effect were me_powers ``_gate`` answering yes with a hostile in view
or a hit just taken (137 times; its rows' own hostile rule ``_hostiles_allow`` then agreed with
the strict reading every time), ``_loot_before_recall_calm`` refusing for a hostile known by
detection only (29), and the periodic filler in town (5).  junk_destroy_now, the utility
device rule, the far summoner loot and the rows' hostile rule never differed; curse_cure,
the once quest's quiet, the sealed loot and Q34's recharge were not asked on these boards.
"""
from __future__ import annotations

import functools
import weakref

from hengbot import safety_facts

GATES = {
    "junk_destroy_now.safe": (
        "the strict reading itself (no visible hostile, not just hit, no impairment, no flight)",
        "destroying junk can always wait (owner 2026-11-02 DL3's reference gate)"),
    "curse_cure.safe": (
        "a visible hostile only when the combat ladder judges it dangerous; none beside; "
        "a refused command; not stunned",
        "the removal takes one turn and its rest or wait comes next (owner 2026-11-15)"),
    "me_powerful_activation._safe": (
        "the town only; none beside; a refused command; not stunned",
        "the town recovery's Powerful Activation (the cost in HP is its own gate)"),
    "me_powers._gate": (
        "the class, the screen protocol, a refused command; no hostile test at all",
        "the absorbed powers' common gate; each power adds its own hostile rule"),
    "me_powers._hostiles_allow": (
        "a power aimed at a hostile passes; a harmless hostile beside passes when the row says so",
        "the 10-31 power table rows (owner 2026-10-31)"),
    "me_powers._when_safe": (
        "no visible hostile, not just hit, the HP cost leaves the low-HP rungs behind",
        "Powerful Activation 「安全なら」 (owner 2026-10-31)"),
    "me_powers.utility_device_permitted": (
        "a visible hostile only when the combat ladder judges it dangerous; not just hit",
        "the mapping row's hostile rule, shared by a carried device of the same effect"),
    "once_quest_recall._quiet": (
        "an enemy about (seen or sensed) or a hit from the unseen; no status test",
        "a once quest's floor rests and keeps its plan when nothing is about (owner 2026-11-03)"),
    "sealed_loot._safe": (
        "no hostile seen or sensed; no status test",
        "the melt into a sealed pocket (owner 2026-11-13 「安全な時」)"),
    "summoner_far_loot._quiet": (
        "no hostile seen or sensed; no status test",
        "the far loot past a remembered summoner"),
    "return_yield.quiet_recall_due": (
        "no awake hostile in view; blind or confused refuse; a latched survival return",
        "the emergency recall when nothing awake is in view (owner 2026-11-04)"),
    "policy._periodic_filler_is_safe": (
        "the last reason (an explore or a Q2 patrol) and no store posting in flight",
        "the periodic save/dump/refresh replaces only a filler key"),
    "policy._loot_before_recall_calm": (
        "no hostile seen (one only sensed does not count) and a zero threat prediction",
        "the loot collected while Recall counts down (owner 2026-09-23; sensed-only not counted, 2026-11-18)"),
    "q34_recharge.safe_to_recharge": (
        "full HP, not hungry, every status, the plan's stand and the cleared targets",
        "Q34's recharge rest at the approved throwing stand"),
}

_LEDGER: list = []
_CURRENT = None  # a weak reference to the policy deciding now


def begin(policy) -> None:
    """A new public decision (``choose_key``'s entry): its records start empty."""
    global _CURRENT
    _LEDGER.clear()
    try:
        _CURRENT = weakref.ref(policy)
    except TypeError:
        _CURRENT = None


def _policy_and_board(args):
    policy = board = None
    for arg in args:
        if board is None and hasattr(arg, "visible_monsters") and hasattr(arg, "player"):
            board = arg
        elif policy is None and hasattr(arg, "_escape_state"):
            policy = arg
        elif hasattr(arg, "policy") and hasattr(arg, "snapshot"):
            policy = policy or arg.policy
            board = board or arg.snapshot
    if policy is None and _CURRENT is not None:
        policy = _CURRENT()
    return policy, board


def watched(name: str):
    """Record each answer of the gate ``name`` (a row of ``GATES``) beside the board's facts."""
    assert name in GATES, name

    def wrap(gate):
        @functools.wraps(gate)
        def watched_gate(*args, **kwargs):
            answer = gate(*args, **kwargs)
            policy, board = _policy_and_board(args)
            if policy is not None and board is not None:
                try:
                    facts = safety_facts.of(policy, board)
                except Exception:  # a test's stand-in policy: nothing to record
                    return answer
                _LEDGER.append((name, bool(answer), safety_facts.strict_quiet(facts), facts))
            return answer
        return watched_gate
    return wrap


def report() -> list:
    """This decision's records: (gate, answer, strict answer, facts)."""
    return list(_LEDGER)


def differences(facts) -> tuple:
    """The strict reading's facts that are set on ``facts`` (why the strict reading said no)."""
    names = ("in_town", "in_store", "hostile_in_view", "took_damage", "blind", "confused",
             "stunned", "paralyzed", "hallucinated")
    found = tuple(name for name in names if getattr(facts, name))
    if facts.escape_owner not in {None, "return"}:
        found += ("escape_owner",)
    return found
