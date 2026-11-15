"""The cross-layer rules' observer: where each rule is or is not consulted, per decision.

Maintainability review of the dungeon decisions (2026-11-15, N1, stage 1): the ladder fixed the
order of the decisions, but the rules that cross the layers have no single point every producer
passes and no lint:

- ``left-cells``: every walker reads the shared record of the cells an owner left
  (``left_cells.refused``, inside ``policy._walk_veto``; owner 2026-11-13 「1と2だけ」).
- ``uncurse-before-rest``: a rest or a wait in the dungeon is preceded by the worn curse's
  removal (``curse_cure.removal_key``, which the safe-now rung and ``before_rest`` ask;
  owner 2026-11-15).
- ``escape-line-of-fire``: an escape joins the two-escape count only when a cause had a line of
  fire, which the deciding producer records (``line_of_fire.note``; owner 2026-11-14).  An escape
  no producer noted is judged later on the board's known causes (``line_of_fire.counts``).
- ``destruction-forget``: the monsters a *Destruction* removed are forgotten
  (``monster_memory.forget_within`` for its KINDS, ``destruction_use.FORGET_VISIT``).
- ``deep-teleport``: a self-teleport on 50F+ passes ``deep_teleport.substitute`` (the one rule
  of the five with a single point every read passes, ``policy._read_key``).

This module only records.  The producers call ``produce`` where a rule applies and the
registered points call ``consult``; ``end`` (the ``choose_key`` exit) settles the decision's
reading, which the decision log carries as ``cross_rule`` (``report``).  Nothing here is read by
a decision, and nothing is stored on the policy (the ledgers live beside it, weakly keyed), so
the checkpoints, the pickles and the purity of a town producer are unchanged.
"""

from __future__ import annotations

import sys
import weakref
from dataclasses import dataclass, field

LEFT_CELLS = "left-cells"
UNCURSE_BEFORE_REST = "uncurse-before-rest"
ESCAPE_LINE_OF_FIRE = "escape-line-of-fire"
DESTRUCTION_FORGET = "destruction-forget"
DEEP_TELEPORT = "deep-teleport"
RULES = (LEFT_CELLS, UNCURSE_BEFORE_REST, ESCAPE_LINE_OF_FIRE, DESTRUCTION_FORGET, DEEP_TELEPORT)

CONSULTED = "consulted"
NOT_CONSULTED = "not-consulted"

# The monster memories a *Destruction* does not forget (the flash board records each one that
# still holds something).  scripts/cross_rule_lint.py derives the same list from the source and
# fails when the two disagree, so a new memory is not missed here.
UNFORGOTTEN_MONSTER_MEMORIES = (
    "_breeder_quest_seen",       # breeder_quest.BREEDER_SEEN: a monster_memory Kind outside KINDS
    "_oneshot_breath_visit",     # oneshot_breath
    "_retreat_veto_life",        # retreat_veto_life
    "_summon_response_memory",   # summon_response
    "_threat_tier_memory",       # threat_tier_memory
    "_sensed_approach_memory",   # threat_tiers.APPROACH_MEMORY
    "_sent_away_t1",             # sent_away_t1
    "_deep_teleport_landing",    # deep_teleport
    "_blind_strike_monsters",    # blind_strike
)


@dataclass
class Ledger:
    """One decision's events: ``clock`` orders them; ``consults`` rule -> [(clock, site)],
    ``produced`` [(rule, clock, site)]; ``result`` the settled reading (``end``)."""
    clock: int = 0
    consults: dict = field(default_factory=dict)
    produced: list = field(default_factory=list)
    result: tuple = ()


_LEDGERS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_BY_ID: dict = {}  # a policy that cannot be weakly referenced (none in production)


def _ledger(policy) -> Ledger:
    try:
        ledger = _LEDGERS.get(policy)
        if ledger is None:
            ledger = _LEDGERS[policy] = Ledger()
        return ledger
    except TypeError:
        return _BY_ID.setdefault(id(policy), Ledger())


def _caller(depth: int) -> str:
    """The calling producer's function name (``depth`` frames above the caller of the hook)."""
    try:
        frame = sys._getframe(depth + 1)
    except ValueError:
        return "?"
    name = frame.f_code.co_name
    # The shared helpers name the producer that called them.
    while ((name in _HELPERS or frame.f_globals.get("__name__") in _HELPER_MODULES)
           and frame.f_back is not None):
        frame = frame.f_back
        name = frame.f_code.co_name
    if name.startswith("<"):
        # A lambda or a comprehension: the function it was written in.
        named = [part for part in frame.f_code.co_qualname.split(".") if not part.startswith("<")]
        name = named[-1] if named else name
    return name


# The named combinations of the cells a walk keeps off: the walker that called one is named.
_HELPER_MODULES = frozenset({"hengbot.walk_vetoes"})
_HELPERS = frozenset({"_path_step", "_step_toward", "refused_yx", "_walk_veto", "refused",
                      "removal_key", "before_rest", "note", "scroll_substitute", "substitute"})


def begin(policy) -> None:
    """A new public decision (``choose_key``'s entry)."""
    try:
        _LEDGERS[policy] = Ledger()
    except TypeError:
        _BY_ID[id(policy)] = Ledger()


def consult(policy, rule: str, site: str | None = None) -> None:
    """A registered point of ``rule`` was asked."""
    ledger = _ledger(policy)
    ledger.clock += 1
    ledger.consults.setdefault(rule, []).append((ledger.clock, site or _caller(2)))


def produce(policy, rule: str, site: str | None = None) -> None:
    """A producer did what ``rule`` governs (a step, a teleport read, a flash)."""
    ledger = _ledger(policy)
    ledger.clock += 1
    ledger.produced.append((rule, ledger.clock, site or _caller(2)))


def _consulted_before(ledger: Ledger, rule: str, clock: int | None) -> bool:
    return any(clock is None or seen < clock for seen, _site in ledger.consults.get(rule, ()))


def _rest_or_wait(key: str) -> bool:
    from hengbot.curse_cure import rests_or_waits  # the one reading (import cycle)

    return rests_or_waits(key)


def end(policy, snapshot, key) -> tuple:
    """The decision's reading: one (rule, state, site) per rule that applied on this board."""
    ledger = _ledger(policy)
    rows = []
    for rule, clock, site in ledger.produced:
        state = CONSULTED if _consulted_before(ledger, rule, clock) else NOT_CONSULTED
        if rule == DESTRUCTION_FORGET:
            state = site[0]
            site = site[1]
        rows.append((rule, state, site))
    reason = getattr(policy, "last_reason", None) or ""
    in_dungeon = (snapshot is not None and not getattr(snapshot, "in_town", True)
                  and getattr(snapshot, "store", None) is None
                  and (getattr(snapshot, "dungeon_level", 0) or 0) > 0)
    if in_dungeon and isinstance(key, str) and key and _rest_or_wait(key):
        state = CONSULTED if _consulted_before(ledger, UNCURSE_BEFORE_REST, None) else NOT_CONSULTED
        rows.append((UNCURSE_BEFORE_REST, state, reason))
    if in_dungeon and reason:
        from hengbot.line_of_fire import PROOF_REASONS
        from hengbot.policy_constants import EMERGENCY_ESCAPE_REASONS, RELOCATING_ESCAPE_REASONS

        if reason in EMERGENCY_ESCAPE_REASONS or reason in RELOCATING_ESCAPE_REASONS:
            noted = (reason in PROOF_REASONS
                     or _consulted_before(ledger, ESCAPE_LINE_OF_FIRE, None))
            rows.append((ESCAPE_LINE_OF_FIRE, CONSULTED if noted else NOT_CONSULTED, reason))
    ledger.result = tuple(dict.fromkeys(rows))  # in order, once each
    return ledger.result


def destruction_flash(policy, forgotten: tuple) -> None:
    """The flash board (destruction_use ``observe``): what was forgotten, and each registered
    monster memory a *Destruction* does not forget that still holds something."""
    ledger = _ledger(policy)
    ledger.clock += 1
    ledger.produced.append((DESTRUCTION_FORGET, ledger.clock, (CONSULTED, "+".join(forgotten))))
    for attribute in UNFORGOTTEN_MONSTER_MEMORIES:
        if getattr(policy, attribute, None):
            ledger.produced.append((DESTRUCTION_FORGET, ledger.clock, (NOT_CONSULTED, attribute)))


def report(policy) -> list | None:
    """The decision log's ``cross_rule``: ``cross-rule:<rule>:<state>:<site>`` per row."""
    try:
        ledger = _LEDGERS.get(policy)
    except TypeError:
        ledger = _BY_ID.get(id(policy))
    if ledger is None or not ledger.result:
        return None
    return [f"cross-rule:{rule}:{state}:{site}" for rule, state, site in ledger.result]


# -- the registry (stage 2): each rule's owner, its registered points and its producers --------
#
# scripts/cross_rule_lint.py lists every producer that does not reach its rule's point; the gaps
# known on 2026-11-15 are kept in scripts/cross_rule_baseline.json (advisory) and a new one fails.

# Modules and functions of the town (the rules are the dungeon's).
TOWN_MODULES = (r"^(policy_(town|shop|home|instore|equipment)|town_|store|shop|home|cli$|input_executor"
                r"|model$|zul_trip|arena|morivant|me_inn|armor_smith|wand_tower|q2_tower|cross_rules$)")
TOWN_FUNCTIONS = r"town|store|shop|home|wilderness|morivant|telmora"
# The rest and wait keys (uncurse-before-rest's producers return one).
REST_KEY_NAMES = frozenset({"REST_MACRO", "REST_KEY", "REST_COMMAND", "WAIT_KEY", "SEARCH_KEY", "HOLD_KEY"})
# The ladder layers below the safe-now rung curse_cure.key: a rest or wait they return was
# preceded by that rung on the same decision (dungeon_ladder.LADDER).
LAYERS_AFTER_SAFE_NOW = frozenset({"ladder_objectives", "ladder_rest", "ladder_descent", "ladder_idle"})
# The calls that compose a read, a use or a cast (deep-teleport's producers call one).
KEY_COMPOSERS = frozenset({"_read_key", "_issue_emergency_consumable", "_use_staff_key", "_staff_key",
                           "_device_key", "device_teleport_key", "blind_teleport_key", "cast", "_use"})
# The self-teleport means (deep-teleport's producers touch one).
TELEPORT_MEANS = (r"^(SV_SCROLL_TELEPORT|SV_SCROLL_PHASE_DOOR|SV_STAFF_TELEPORTATION|_find_teleport_scroll"
                  r"|_find_phase_scroll|pack_teleport_means|blind_teleport_means|TELEPORTATION)$")


@dataclass(frozen=True)
class CrossRule:
    """``points``: the registered pass-through (``module:function`` or ``policy:method``);
    ``helpers``: the shared step/compose helpers the producers call (not producers, and not
    followed when reading whether a producer reaches the point); ``point_modules``: the
    modules that are the rule's own machinery."""
    name: str
    owner: str
    points: tuple
    helpers: tuple = ()
    point_modules: tuple = ()
    # (module, function, call): a point every key passes (``choose_key``'s exit); while the
    # function calls it, no producer is outside the rule.
    exit_point: tuple | None = None


REGISTRY = (
    CrossRule(LEFT_CELLS, "owner 2026-11-13 「1と2だけ」 (left_cells)",
              # The fixed-quest walks' readings (owner 2026-11-15 Q2): the navigator's walk off
              # the cells bound for the board, the Q18 exit plan's walk off the board's cells.
              points=("left_cells:refused", "left_cells:refused_yx", "policy:_walk_veto",
                      "*:walk_path", "quest_find_exit:_walk_off_left", "quest_find_exit:_off_left"),
              helpers=("_step_toward", "_path_step", "walk_key"),
              point_modules=("left_cells", "goal_route")),
    CrossRule(UNCURSE_BEFORE_REST, "owner 2026-11-15 (curse_cure)",
              points=("curse_cure:removal_key", "curse_cure:before_rest_or_wait"),
              # The step's own refusal WAIT is the walk's, not a rest or a hold.
              helpers=("_step_toward",),
              point_modules=("curse_cure",),
              # Owner 2026-11-15 Q4: every key passes the choose_key exit, which asks the point.
              exit_point=("policy", "choose_key", "before_rest_or_wait")),
    CrossRule(ESCAPE_LINE_OF_FIRE, "owner 2026-11-14 「射線が通っている場合のみ」 (line_of_fire)",
              points=("line_of_fire:note",),
              point_modules=("line_of_fire", "escape_count", "reasons", "policy_constants")),
    CrossRule(DESTRUCTION_FORGET, "owner 2026-11-11 (destruction_use, monster_memory)",
              points=("monster_memory:forget_within", "destruction_use:forget_circle"),
              point_modules=("destruction_use", "monster_memory")),
    CrossRule(DEEP_TELEPORT, "owner 2026-11-14 「50F以降のテレポートの条件を厳しくする」 (deep_teleport)",
              points=("deep_teleport:substitute", "deep_teleport:scroll_substitute",
                      "deep_teleport:no_means", "deep_teleport:movement_refused",
                      "policy:_read_key", "policy:_issue_emergency_consumable"),
              point_modules=("deep_teleport",)),
)


@dataclass(frozen=True)
class MonsterMemory:
    """A memory of monsters on the floor and what forgets it at a *Destruction*
    (None: nothing, the flash board records it)."""
    attribute: str
    module: str
    forgotten_by: str | None


MONSTER_MEMORIES = (
    MonsterMemory("_sleeper_reach_memory", "monster_memory", "monster_memory.KINDS"),
    MonsterMemory("_sleeper_loot_block", "monster_memory", "monster_memory.KINDS"),
    MonsterMemory("_disenchant_avoid_seen", "monster_memory", "monster_memory.KINDS"),
    MonsterMemory("_immobile_summoner_memory", "summoner_wait", "destruction_use.FORGET_VISIT"),
    MonsterMemory("_immobile_threat_memory", "immobile_threat_memory", "destruction_use.FORGET_VISIT"),
    MonsterMemory("_hunt_target_memory", "hunt_target", "destruction_use.FORGET_VISIT"),
    MonsterMemory("_left_cells", "left_cells", "destruction_use.FORGET_VISIT"),
    *(MonsterMemory(attribute, module, None) for attribute, module in (
        ("_breeder_quest_seen", "breeder_quest"), ("_oneshot_breath_visit", "oneshot_breath"),
        ("_retreat_veto_life", "retreat_veto_life"), ("_summon_response_memory", "summon_response"),
        ("_threat_tier_memory", "threat_tier_memory"), ("_sensed_approach_memory", "threat_tiers"),
        ("_sent_away_t1", "sent_away_t1"), ("_deep_teleport_landing", "deep_teleport"),
        ("_blind_strike_monsters", "blind_strike"))),
)
