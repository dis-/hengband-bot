"""The 99F/100F preparation phase: one owner of the switch from the 95F exploration (owner 2026-11-21).

Owner 2026-11-21 (verbatim, LOCKED): 「99Fに挑む要件を満たしたら専用の準備フェイズを作って準備して。
変に既存の仕組みを使おうとして破綻しているように見える」, and the answer to its question 1:
「キー操作だけ既存の着け替えの処理に任せる」.  Questions 2 and 3 as proposed: one "cap lifted" mark
carries the carry counts, the weight allowance and the dedicated ranking from the phase's end to the
next town; back in town the phase is entered again when the requirements still hold, else the 95F
exploration goes on; a phase stopped in the middle of the swap returns to the ordinary play, whose
optimizer restores the ordinary gear.

The phase replaces the arrival-only switch latch (angband_finale's former ``Memory.switching`` /
``decided``), the read-only search run beside every town optimization and the readiness latch the
cap read (``Memory.ready``).  Every reader of the finale's carry, weight, ranking and cap asks this
module (``carrying``, ``dedicated_order``, ``lifted``), so the transition has one owner.

The steps, each with its done-check, measured on every town board (``observe``); the phase's own
keys come from ``town_key`` (the objectives ladder, before the ordinary town work):

``home``      entered on a town board with the supplies owned (angband_finale ``supplied``: the
              pack and the Home census, current or kept from the last visit), no equipment swap
              under way and no recall counting down.  Reads the Home (``~9``, no game time) unless
              its census is current; done when it is.  The supplies are counted again on that
              census (``home:supplies-not-owned`` stops a phase whose kept census was stale).
``check``     done when the read-only search over the owned gear in the finale's rank (policy_equipment
              ``_angband_finale_feasibility``, run only in this step) chose a set meeting every
              equipment condition (``set_missing``: speed after the weight, the resistances,
              telepathy, resist curse, resist blindness or light, the *Destruction* means of that
              set: the absorbed power unless the set wears a NO_MAGIC).
``supplies``  takes the finale's counts out of the Home, one stack at a time (a Home errand of the
              phase's own purpose, routed by the need ``CATEGORY``; a census another Home take or
              deposit dropped is read again first, and a stack whose slot that take left
              unaddressed is filed for the errand's own read); the carry holds from here
              (angband_finale ``carry_target``: nothing deposits them again).  Done when the pack
              holds every count (``readiness``'s ``carried``) and no swap is under way.
``loadout``   the worn loadout's search runs in the finale's rank with the supplies carried; its
              chosen set is the phase's target, fixed here (``fix_target``).
``swap``      the equipment transaction composes the keys toward the fixed target only (every
              other owned piece is out of its search: ``excluded_ids``); done when the worn set is
              the target, no transaction is left and the board meets every condition.
``recall``    the cap is lifted (``lifted``): the town's Word of Recall toward Angband is read past
              95F, the small-floor option first (angband_finale ``small_floor_key``); done when the
              recall counts down.
``done``      the expedition: the mark holds until the next town board.

No equipment swap starts while ``home``, ``check`` or ``loadout`` runs (``holds_swap``), and the
phase enters ``home`` and ``loadout`` only with no swap under way: the order of the worn loadout's search never
changes under a swap (n1-b life-411 2026-11-20 22:29-22:32: a swap through Home failed half done
when the order changed mid-visit).  A step that cannot complete stops the phase with a named reason
(``stopped``): the visit goes on as the 95F exploration (no cap lift), and the next town visit may
enter again.  The departure's read of the recall while a step before ``recall`` runs stops the phase
(``departure_reached``): the town had nothing left to do for that step.
"""
from __future__ import annotations

from dataclasses import dataclass, field

IDLE = "idle"
HOME = "home"
CHECK = "check"
SUPPLIES = "supplies"
LOADOUT = "loadout"
SWAP = "swap"
RECALL = "recall"
DONE = "done"
STOPPED = "stopped"
STEPS = (HOME, CHECK, SUPPLIES, LOADOUT, SWAP, RECALL)

# Decisions a step may take before it stops the phase (a step that makes no progress for this
# long will not finish this visit).
STEP_LIMIT = {HOME: 60, CHECK: 80, SUPPLIES: 400, LOADOUT: 80, SWAP: 600, RECALL: 300}

STATE = "_finale_prep"
PURPOSE = "finale-prep-supplies"   # the Home errand of the supplies step
CATEGORY = "finale-prep-home"      # its town need (home-first, never blocking a departure)
HOME_REASON = "finale-prep:read-home"


@dataclass
class Phase:
    step: str = IDLE
    since: int = 0                      # the decision sequence the step began
    target: frozenset | None = None     # the dedicated set's item signatures (``fix_target``)
    lifted: bool = False                # the cap lifted: carry, weight, ranking until the next town
    stopped: str | None = None          # the named reason of a stopped phase
    in_town: bool | None = None         # the last board's side (None: no board yet)
    log: list = field(default_factory=list)  # [(sequence, step, note)] of this visit


def phase(policy) -> Phase:
    held = getattr(policy, STATE, None)
    if held is None:
        held = Phase()
        setattr(policy, STATE, held)
    return held


# The finale's carry a process restarted on a 99F/100F floor reads as the expedition's: the
# ordinary play carries neither potion (consumable_policy: they go to the Home), so two of either
# are the expedition's (``expedition_evident``).
RESTART_EVIDENCE = 2


def expedition_evident(policy, snapshot) -> bool:
    """A board of the finale's expedition, read from the game alone (a fresh process): a
    Magic-Eater of the 95F exploration on Angband 99F/100F whose quest is still TAKEN, carrying
    the finale's Restore Mana or *Healing* (``RESTART_EVIDENCE``)."""
    from hengbot import angband_finale
    if not (angband_finale.preparing(snapshot) and angband_finale.on_finale_floor(snapshot)
            and not angband_finale.quest_done(snapshot)):
        return False
    return any(angband_finale.carried(snapshot, kind) >= RESTART_EVIDENCE
               for kind in (angband_finale.RESTORE_MANA, angband_finale.STAR_HEALING))


def _go(policy, held: Phase, step: str, note: str = "") -> None:
    held.step, held.since = step, policy._decision_sequence
    held.log.append((policy._decision_sequence, step, note))


def _stop(policy, held: Phase, reason: str) -> None:
    held.stopped = reason
    held.lifted = False
    held.target = None
    errand = policy._home_errand
    if errand.request is not None and errand.request.purpose == PURPOSE:
        errand.cancel_unposted()
    _go(policy, held, STOPPED, reason)


def _reset(held: Phase) -> None:
    held.step, held.since, held.target, held.lifted, held.stopped = IDLE, 0, None, False, None
    held.log = []


# -- the readers ---------------------------------------------------------------------

def carrying(policy) -> bool:
    """The finale's carry and weight allowance hold: the phase reached its supplies, or the cap is
    lifted for the expedition."""
    held = getattr(policy, STATE, None)
    return bool(held is not None and (held.lifted or held.step in (SUPPLIES, LOADOUT, SWAP, RECALL,
                                                                   DONE)))


def dedicated_order(policy) -> bool:
    """The worn loadout's search is in the finale's rank: from the phase's loadout step on, and on
    the expedition."""
    held = getattr(policy, STATE, None)
    return bool(held is not None and (held.lifted or held.step in (LOADOUT, SWAP, RECALL, DONE)))


def lifted(policy) -> bool:
    """The 95F cap is lifted (angband_cap): the phase's recall step and the expedition."""
    held = getattr(policy, STATE, None)
    return bool(held is not None and held.lifted)


def recall_closed(policy, snapshot) -> bool:
    """On the 99F/100F floors of the expedition, Word of Recall is the battle's alone: read on
    success or once the Restore Mana is overspent (angband_finale_battle ``recall_permitted``,
    owner 2026-11-20 「帰還による離脱は成功時と魔力復活の薬を予定の倍以上使ったときのみ」); every
    other rule (deep_teleport, the summoner's, the ESP threat's, the emergencies) finds none."""
    from hengbot import angband_finale_battle  # import cycle
    return (angband_finale_battle.applies(policy, snapshot)
            and not angband_finale_battle.recall_permitted(policy, snapshot))


def owned_search_due(policy) -> bool:
    """The read-only search over the owned gear (policy_equipment): the check step only."""
    held = getattr(policy, STATE, None)
    return bool(held is not None and held.step == CHECK)


def holds_swap(policy) -> bool:
    """No equipment swap starts before the phase's swap step (policy_equipment)."""
    held = getattr(policy, STATE, None)
    return bool(held is not None and held.step in (HOME, CHECK, LOADOUT))


def routed(policy) -> bool:
    """The supplies step's Home errand is on foot: its need routes the visit to the Home."""
    errand = policy._home_errand
    return bool(errand.active and errand.request is not None and errand.request.purpose == PURPOSE)


def release_stopped(policy) -> bool:
    """A stopped Home errand of the supplies step: the phase stops by name and the errand is
    released (a stopped errand otherwise holds the whole bot: policy ``_decide``)."""
    errand = policy._home_errand
    if errand.request is None or errand.request.purpose != PURPOSE:
        return False
    held = getattr(policy, STATE, None)
    if held is not None and held.step == SUPPLIES:
        _stop(policy, held, f"supplies:withdrawal-{errand.stopped_fact or 'stopped'}")
    errand.release_stopped()
    return True


def excluded_ids(policy, items) -> frozenset:
    """The owned pieces out of the worn loadout's search during the swap: all but the target's."""
    held = getattr(policy, STATE, None)
    if held is None or held.step != SWAP or held.target is None:
        return frozenset()
    return frozenset(owned.id for owned in items if _signature(owned.id) not in held.target)


def _signature(item_id: str) -> str:
    """The catalogue id's item part (``origin:signature:n``): the same piece wherever it is."""
    parts = item_id.split(":")
    return ":".join(parts[1:]) if len(parts) > 1 else item_id


def set_missing(policy, snapshot, loadout, metrics) -> list:
    """The equipment conditions ``loadout`` does not meet (angband_finale ``_missing``): its flags
    and the board's intrinsic abilities, its speed after the weight, and its *Destruction* means
    (the absorbed power unless the set wears a NO_MAGIC, else a staff the board makes reliable)."""
    from hengbot import angband_finale, destruction_means, destruction_use
    from hengbot.equipment_optimizer import ABILITY_FLAG
    from hengbot.me_power_success import TR_NO_MAGIC
    from hengbot.speed_valuation import loadout_speed, meets_speed_gate
    flags = loadout.flags
    names = {**ABILITY_FLAG, angband_finale.RESIST_CURSE: 148, "resist_blind": 56,
             "resist_lite": 54}
    abilities = {name for name, flag in names.items() if flag in flags}
    abilities |= {name for name, sources in snapshot.player.ability_sources.items()
                  if set(sources) & angband_finale.INTRINSIC_SOURCES}
    absorbed = (destruction_means.Means(policy, snapshot).optimizer_without_gear()
                and TR_NO_MAGIC not in flags)
    return angband_finale._missing(
        policy, snapshot, frozenset(abilities), speed_met=meets_speed_gate(loadout_speed(metrics)),
        means_held=absorbed or destruction_use.holds_means(policy, snapshot))


def _best(preparation):
    return getattr(getattr(preparation, "result", None), "best", None)


def fix_target(policy, snapshot, preparation) -> None:
    """policy_equipment, the worn loadout's search in the finale's rank during the loadout step:
    its chosen set becomes the phase's fixed target, or the phase stops."""
    held = getattr(policy, STATE, None)
    if held is None or held.step != LOADOUT:
        return
    best = _best(preparation)
    if best is None and "home-scan-incomplete" in (getattr(preparation, "blockers", ()) or ()):
        # The search did not run over the whole Home: another Home take or deposit of this visit
        # left its scan incomplete (n1-b life-411 2026-11-21 14:26:13, the swap's deposits just
        # before; the step stopped as loadout:no-set and the supplies were deposited again).  The
        # supplies step reads the Home and comes back here.
        _go(policy, held, SUPPLIES, "home-scan-incomplete")
        return
    if best is None:
        _stop(policy, held, "loadout:no-set")
        return
    missing = set_missing(policy, snapshot, best.loadout, best.metrics)
    if missing:
        _stop(policy, held, "loadout:" + ",".join(missing))
        return
    held.target = frozenset(_signature(item.id) for _, item in best.loadout.slots)
    _go(policy, held, SWAP, f"{len(held.target)} pieces")


def departure_reached(policy, snapshot) -> None:
    """The town's Word of Recall read while a step before ``recall`` runs: the town had nothing
    left to do for that step, so the phase stops and the 95F departure goes on."""
    held = getattr(policy, STATE, None)
    if held is not None and held.step in (HOME, CHECK, SUPPLIES, LOADOUT, SWAP):
        _stop(policy, held, f"{held.step}:unfinished-at-departure")


# -- the steps -------------------------------------------------------------------------

def _home_current(policy) -> bool:
    return bool(policy._home_knowledge_current and not policy._home_knowledge_invalidated
                and policy._equipment_catalog.home_scan_complete)


def observe(policy, snapshot, rows: dict | None) -> None:
    """Every decision (angband_finale ``observe``): the town board's step and its done-check;
    ``rows`` is that board's readiness (None out of town or short of the 95F exploration)."""
    held = phase(policy)
    if not snapshot.in_town:
        restarted, held.in_town = held.in_town is None, False
        if not held.lifted and restarted and expedition_evident(policy, snapshot):
            # The mark lives in the process only: a process started on the expedition's floor
            # takes it again from what the game shows (n1-c life-217 2026-11-21 14:41:02, restarted
            # on 100F beside the Serpent of Chaos: no battle, the ordinary rungs climbed and
            # recalled, and it died at 14:41:09).
            held.lifted = True
            held.log.append((policy._decision_sequence, DONE, "restart-on-finale-floor"))
        if held.lifted:
            held.step = DONE  # the recall read: the expedition carries the mark
        elif held.step != DONE:
            _reset(held)
        return
    arrival, held.in_town = held.in_town is False, True
    if arrival:
        _reset(held)
    if rows is None:
        if held.step != IDLE:
            _reset(held)
        return
    if held.step in (DONE, STOPPED):
        return
    from hengbot import angband_finale
    elapsed = policy._decision_sequence - held.since
    if held.step != IDLE and elapsed > STEP_LIMIT[held.step]:
        _stop(policy, held, f"{held.step}:step-limit")
        return
    if held.step == IDLE:
        if (angband_finale.ready(rows["owned"]) and angband_finale.census_known(policy)
                and policy._equipment_transaction_session is None
                and not snapshot.player.recalling):
            _go(policy, held, HOME)
        else:
            return
    if held.step == HOME:
        if not _home_current(policy):
            return
        if not angband_finale.ready(rows["owned"]):
            _stop(policy, held, "home:supplies-not-owned")
            return
        policy._angband_finale_feasibility = None
        _go(policy, held, CHECK)
        return
    if held.step == CHECK:
        best = _best(getattr(policy, "_angband_finale_feasibility", None))
        if best is None:
            return
        missing = set_missing(policy, snapshot, best.loadout, best.metrics)
        if missing:
            _stop(policy, held, "check:" + ",".join(missing))
        else:
            _go(policy, held, SUPPLIES)
        return
    if held.step == SUPPLIES:
        errand = policy._home_errand
        if (errand.request is not None and errand.request.purpose == PURPOSE
                and errand.state.value == "failed"):
            _stop(policy, held, "supplies:withdrawal-failed")
            return
        if (angband_finale.ready(rows["carried"]) and not routed(policy)
                and not _restoring_at_home(policy)
                and policy._equipment_transaction_session is None
                and policy._equipment_catalog.home_scan_complete):
            _go(policy, held, LOADOUT)
        return
    if held.step == SWAP:
        worn = frozenset(_signature(owned.id) for owned in policy._equipment_catalog.items
                         if owned.origin == "equipped")
        if worn != held.target or policy._equipment_transaction_session is not None:
            return
        missing = angband_finale.board_missing(policy, snapshot)
        if missing:
            _stop(policy, held, "swap:" + ",".join(missing))
            return
        if policy._find_edible(snapshot) is None:
            # Owner 2026-11-21 (LOCKED) 「空腹で死ぬ前に帰還するように修正」: no expedition without
            # something to eat (food, or for a MANA race a charged wand or staff); the ordinary town
            # supply buys it and the next visit enters again.
            _stop(policy, held, "swap:no-food")
            return
        held.lifted = True
        _go(policy, held, RECALL)
        return
    if held.step == RECALL and snapshot.player.recalling:
        _go(policy, held, DONE)


def _short_stack(policy, snapshot):
    """(kind, Home stack, count, addressable) of the first finale kind the pack holds short of its
    count, with a stack in the Home catalogue; (kind, None, count, False) when the catalogue holds
    none.  ``addressable``: the stack's slot is still valid (before ``_home_knowledge_valid_before``;
    another take earlier in the list leaves the later slots to a fresh census, which the filed
    errand reads itself: n1-c life-217 2026-11-21 11:31:14, the *Healing* take at slot 4 left the
    Restore Mana at slots 6-7 unaddressed and the step stopped as if none were at Home)."""
    from hengbot import angband_finale
    targets = {**angband_finale.CARRY,
               angband_finale.RESTORE_MANA: angband_finale.restore_mana_carry(policy, snapshot) or 0}
    for kind, target in targets.items():
        missing = target - angband_finale.carried(snapshot, kind)
        if missing <= 0:
            continue
        found = [(index, item) for index, item in enumerate(policy._home_knowledge_items)
                 if (item.tval, item.sval) == kind and getattr(item, "aware", True)
                 and policy._item_signature(item) not in policy._deferred_home_items]
        addressable = [item for index, item in found
                       if index < policy._home_knowledge_valid_before]
        if addressable:
            return kind, addressable[0], missing, True
        if found:
            return kind, found[0][1], missing, False
        return kind, None, missing, False
    # Owner 2026-11-21 「全復活のキノコをあるだけ持っていく」: every one at Home, no count; none at
    # Home is no shortage.
    found = _restoring_at_home(policy)
    if found:
        index, item = found[0]
        return (angband_finale.RESTORING, item, item.count,
                index < policy._home_knowledge_valid_before)
    return None


def _restoring_at_home(policy) -> list:
    """[(index, stack)] of the Mushrooms of Restoring in the current Home catalogue."""
    from hengbot import angband_finale
    if not policy._home_knowledge_current:
        return []
    return [(index, item) for index, item in enumerate(policy._home_knowledge_items)
            if (item.tval, item.sval) == angband_finale.RESTORING and getattr(item, "aware", True)
            and policy._item_signature(item) not in policy._deferred_home_items]


def _read_home_key(policy, snapshot) -> str | None:
    """The phase's Home read (``~9``, no game time): the census the home step waits for, and the
    one the supplies step reads again when another Home take or deposit dropped it."""
    if not policy._home_knowledge_current and not policy._home_knowledge_invalidated:
        policy._home_knowledge_invalidated = True  # the census to read is this visit's
    if not policy._home_catalogue_scan_owed() and not (
            policy._home_knowledge_scan_inflight
            or policy._home_knowledge_scan_epoch is not None):
        return None
    key = policy._town_producer_entry(
        "home-full-knowledge", lambda: policy._home_full_knowledge_key(snapshot),
        family="home-scan")
    if key is not None and policy.last_reason == "home:request-knowledge-scan":
        policy.last_reason = HOME_REASON
    return key


def town_key(policy, snapshot) -> str | None:
    """The phase's own keys (the objectives ladder, before the ordinary town work): the Home read
    of the home step; the supplies step files its Home errands here (the need ``CATEGORY`` then
    routes the visit to the Home) and returns None."""
    held = getattr(policy, STATE, None)
    if held is None or not snapshot.in_town or snapshot.player.recalling:
        return None
    if held.step == HOME and not _home_current(policy):
        return _read_home_key(policy, snapshot)
    if held.step != SUPPLIES or policy._home_errand.active:
        return None
    from hengbot.home_errand import HomeErrandRequest
    short = _short_stack(policy, snapshot)
    if short is None:
        # Every count carried: the loadout step's search runs over the whole Home, so a scan
        # another Home operation left incomplete is read first (``fix_target``).
        if not policy._equipment_catalog.home_scan_complete:
            return _read_home_key(policy, snapshot)
        return None
    kind, stack, missing, addressable = short
    if stack is None:
        if not _home_current(policy):
            # Another Home take or deposit of this visit dropped the census (n1-c life-217
            # 2026-11-21 11:32:56: the full-home-sale take emptied the catalogue and the step
            # stopped as not-at-home with 98 Healing there): read it again first.
            return _read_home_key(policy, snapshot)
        _stop(policy, held, f"supplies:not-at-home:{kind[0]}-{kind[1]}")
        return None
    policy._file_home_errand(
        snapshot, HomeErrandRequest(policy._item_signature(stack), min(missing, stack.count),
                                    "home-catalog", PURPOSE),
        knowledge_current=policy._home_knowledge_current and addressable)
    return None


def describe(policy) -> dict | None:
    held = getattr(policy, STATE, None)
    if held is None:
        return None
    return {"step": held.step, "lifted": held.lifted, "stopped": held.stopped,
            "target": sorted(held.target) if held.target else None, "log": list(held.log[-12:])}
