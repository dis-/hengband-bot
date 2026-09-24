"""Goal typing by (owner family, reason prefix), and the survival constant.

``SOL-DESIGN-ownership-contract.md`` rev 9.1, "Rev 9: S2a.1 specified",
items 1 and 3.  Recording only: nothing here is read by a producer, the
ladder or the driver, so no key, reason or decision can depend on it.

Goal typing (item 1)
--------------------
One owner family can hold several kinds of work -- ``departure`` walks to the
stairs (``Reach``), waits for Word of Recall (``Observe`` a floor change) and
departs (``Terminal``) -- so the unit of the table is the census prefix, not
the family.  ``GOAL_TYPING`` is a checked-in constant keyed by
``(family, prefix)``:

* every census prefix of every family of ``town_arbiter.owner_families()``
  has its own row (``tests/test_ownership_s2a1_closure.py`` pins that);
* a row may also name a *longer* prefix of the same family when one part of
  a prefix is a different kind (``return:recall`` inside ``return:``);
  ``goal_typing`` resolves a reason to the longest matching prefix of its own
  family, so a refinement can never leak into another family.

What each kind means for the claim (``policy._claim_goal``):

``Reach``     the producer must have written its target -- a cell, a monster
              ``(index, race_id)`` or a named place (rev 9.2) -- into the
              decision's goal slot on this board, and the slot carries the
              writing producer's family; a Reach row with no slot, or with a
              slot of another family, declares ``Terminal`` and records
              ``goal_missing`` (``no-slot`` / ``owner-mismatch``).
``Observe``   the goal is the expectation the producer posted on this board
              (``_post_owner_expectation``), or else the same owner's still
              open ``Observe`` claim (a transaction's later keys), or else the
              row's own content -- ``floor-change`` always uses its own
              content, because a stair or recall is judged by
              ``snapshot.floor_key`` and nothing else.
``Terminal``  the effect label; it owns exactly the decision that emits it
              and is closed on the reading side
              (``ownership_metrics._closure_of``).

``within`` for each ``Observe`` content is an existing bound (design 3.1):
``OWNER_EXPECTATION_MAX_TURNS`` for a transaction, ``STORE_STUCK_LIMIT`` for
a store or Home operation, ``RECALL_ACTIVATION_MAX_GAME_TURNS`` (350 game
turns) for a floor change.  No new tunable number is introduced.

Survival (item 3)
-----------------
``is_survival`` is exactly the user's list of 2026-09-24
(「emergency・disengage・unseen と危険が理由の return だけ」): the emergency
ladder's output (``emergency:``, ``unseen-recall:``,
``guardian:teleport-to-cover``), ``combat:disengage``, ``unseen:``,
``esp-threat:leave-*``, and a ``return:`` decision while the last return
trigger is a danger trigger.  The policy suspends a claim only for it, and
``ownership_metrics`` reuses the same function for "outside survival".
``flee``, ``summoner:retreat`` / ``summoner:stairs``, ``threat:scroll`` /
``threat:wait``, ``breeder-breakthrough:``, ``combat:fruitless``, status
recovery and ``town:seek-shelter`` are ordinary owners and are *not* in it.
"""

from __future__ import annotations

from dataclasses import dataclass

from hengbot.claim_register import GOAL_OBSERVE, GOAL_REACH, GOAL_TERMINAL
from hengbot.policy_constants import STORE_STUCK_LIMIT
from hengbot.policy_types import OWNER_EXPECTATION_MAX_TURNS
from hengbot.town_arbiter import RECALL_ACTIVATION_MAX_GAME_TURNS


# -- goal contents ------------------------------------------------------

WALK_TARGET = "walk-target"        # Reach: the cell the producer walks to
ENTRANCE = "entrance"              # Reach: the entrance cell of a building
TRANSACTION = "transaction"        # Observe: a transaction's expected change
STORE_OPERATION = "store-operation"  # Observe: a posted store/Home effect
FLOOR_CHANGE = "floor-change"      # Observe: the floor key changes
EFFECT = "effect"                  # Terminal: the effect label

OBSERVE_WITHIN = {
    TRANSACTION: OWNER_EXPECTATION_MAX_TURNS,
    STORE_OPERATION: STORE_STUCK_LIMIT,
    FLOOR_CHANGE: RECALL_ACTIVATION_MAX_GAME_TURNS,
}
# The observable a floor-change goal names (an ``OwnerProgressCore`` field).
FLOOR_EXPECTATION = ("floor",)


@dataclass(frozen=True)
class GoalTypingRow:
    family: str
    prefix: str
    kind: str
    content: str


def _rows(family: str, *entries: tuple[str, str, str]) -> tuple[GoalTypingRow, ...]:
    return tuple(
        GoalTypingRow(family, prefix, kind, content)
        for prefix, kind, content in entries
    )


R, O, T = GOAL_REACH, GOAL_OBSERVE, GOAL_TERMINAL

GOAL_TYPING: tuple[GoalTypingRow, ...] = (
    *_rows(
        "home-errand",
        ("home-errand:", O, STORE_OPERATION),
        ("home-errand:stopped:", T, EFFECT),
        ("home-errand:filed:", T, EFFECT),
    ),
    *_rows(
        "home-scan",
        ("home:request-knowledge", O, STORE_OPERATION),
        ("home:scan", O, STORE_OPERATION),
        ("home:seek-", O, STORE_OPERATION),
    ),
    *_rows(
        "home-visit",
        ("home:", O, STORE_OPERATION),
        ("home:identify-staff-reserve-", T, EFFECT),
        ("home:no-", T, EFFECT),
        ("home:need-", T, EFFECT),
        ("home:processing-complete", T, EFFECT),
        ("home-visit:", T, EFFECT),
        ("home-disposal:", O, STORE_OPERATION),
        ("home-disposal:destroy-refused", T, EFFECT),
    ),
    *_rows(
        "shop-sell",
        ("shop:sale", T, EFFECT),
        ("shop:sell-", T, EFFECT),
        ("shop:batch-sale", T, EFFECT),
        ("shop:batch-sell", O, STORE_OPERATION),
        ("shop:batch-inscribe", O, STORE_OPERATION),
        ("shop:one-shot-sale", O, STORE_OPERATION),
        ("shop:one-shot-sell", O, STORE_OPERATION),
        ("shop:unsellable-", T, EFFECT),
        ("shop:defective-target-leave", T, EFFECT),
        ("shop:leave", O, STORE_OPERATION),
        ("shop:stuck-leave", T, EFFECT),
        ("shop:invalid", T, EFFECT),
        ("shop:retain-standing-digging-tool", T, EFFECT),
        ("town:destroy-overflow", T, EFFECT),
        ("equipment:sale", T, EFFECT),
    ),
    *_rows(
        "shop-buy",
        ("shop:one-shot-buy", O, STORE_OPERATION),
        ("shop:one-shot-in-flight", O, STORE_OPERATION),
        ("shop:one-shot-page-not-zero", T, EFFECT),
        ("shop:buy", O, STORE_OPERATION),
        ("shop:await-", O, STORE_OPERATION),
        ("shop:observe", T, EFFECT),
        # Rev 9.2 (T2): ``shop:observe-and-leave`` emits the leave key inside
        # the store and never walks; rev 9 had listed it with the travel rows.
        ("shop:observe-and-leave", T, EFFECT),
        ("shop:home-first-before-purchase", T, EFFECT),
        ("shop:store-context-exit", O, STORE_OPERATION),
        ("town:wait-restock", T, EFFECT),
    ),
    *_rows(
        "store-router",
        ("shop:approach", R, ENTRANCE),
        ("shop:approach:await-entry", O, STORE_OPERATION),
        ("shop:travel", R, ENTRANCE),
        ("shop:travel:await-entry", O, STORE_OPERATION),
        ("store:", T, EFFECT),
        ("store:entry-await-observation", O, STORE_OPERATION),
        ("store:entry-failed-step-off", R, ENTRANCE),
        ("store:entry-interrupted-replan", R, ENTRANCE),
        ("town:travel", R, ENTRANCE),
        ("town-travel:", R, ENTRANCE),
        # The walk to the teleport building (its route's goal cell).
        ("town:teleport", R, ENTRANCE),
        ("town:teleport-refused-fare", T, EFFECT),
        # One step off the teleport building; the step is computed inside the
        # route helper, which no producer can name without recomputing it.
        ("town:teleport-step-off", T, EFFECT),
        ("store:entry-interrupted-replan:await-entry", O, STORE_OPERATION),
        ("wilderness:enter-town", T, EFFECT),
        ("wilderness:global-travel", R, WALK_TARGET),
        ("wilderness:enter-global", T, EFFECT),
        ("bounty:approach", R, ENTRANCE),
    ),
    *_rows(
        "equipment-opt",
        ("equipment-optimization:", O, TRANSACTION),
        ("equipment:opt", O, TRANSACTION),
        ("optimizer:", O, TRANSACTION),
    ),
    *_rows(
        "equipment-txn",
        ("equipment-transaction:", O, TRANSACTION),
        ("equipment-transaction:approach-home", R, ENTRANCE),
        ("equipment-transaction:travel-home", R, ENTRANCE),
        ("equipment-transaction:travel-home:await-entry", O, STORE_OPERATION),
        # Rev 9.2 (T2): it walks to the Home through the store router.
        ("equipment-transaction:acquire-home-catalog", R, ENTRANCE),
        ("equipment-transaction:home-route-unavailable", T, EFFECT),
        ("equipment-transaction:abandon", T, EFFECT),
        ("equipment-transaction:confirmation-stall-bound", T, EFFECT),
        ("equipment-transaction:retain-", T, EFFECT),
        ("equipment-transaction:defer-identification", T, EFFECT),
        ("equipment-transaction:stale-identity-invalidated:", T, EFFECT),
        ("equipment-transaction:deposit-missing", T, EFFECT),
        ("equipment-transaction:withdraw-missing", T, EFFECT),
        ("equipment-mutation:", T, EFFECT),
        ("equipment:", O, TRANSACTION),
        ("equipment:destroy-", T, EFFECT),
        ("town:restore-combat-weapon", O, TRANSACTION),
        ("town:remove-no-teleport-weapon", O, TRANSACTION),
        ("wield-light", T, EFFECT),
        ("town:replace-no-teleport-weapon", O, TRANSACTION),
    ),
    *_rows(
        "calibration",
        ("calibration:", O, TRANSACTION),
        ("calibration:restore-home-unavailable", T, EFFECT),
        ("calibration:restore-home-unreachable", T, EFFECT),
        # Rev 9.2 (T2): calibration's walks to the Home are native travel.
        ("calibration:restore-travel", R, ENTRANCE),
        ("calibration:restore-travel:await-entry", O, STORE_OPERATION),
    ),
    *_rows(
        "identification",
        ("identify:", T, EFFECT),
        ("identification:", O, STORE_OPERATION),
        ("item-processing:", T, EFFECT),
        ("inventory:", T, EFFECT),
    ),
    *_rows(
        "fundraising",
        ("fundraise:", T, EFFECT),
        ("fundraise:dig-to-treasure", R, WALK_TARGET),
        ("fundraise:seek-treasure", R, WALK_TARGET),
        ("fundraise:seek-loot", R, WALK_TARGET),
        ("fundraise:seek-upstairs", R, WALK_TARGET),
        ("fundraise:sweep-explore", R, WALK_TARGET),
        ("fundraise:recall", O, FLOOR_CHANGE),
        ("fundraise:recall-stuck", T, EFFECT),
        ("fundraise:wait-recall", O, FLOOR_CHANGE),
        ("fundraise:ascend", O, FLOOR_CHANGE),
        ("fundraising:", T, EFFECT),
        ("mining:", T, EFFECT),
        ("town:recall-stockout-mining", T, EFFECT),
        ("town:identify-staff-stockout-mining", T, EFFECT),
    ),
    *_rows(
        "curse-enchant",
        ("town:remove-curse", T, EFFECT),
        ("town:enchant-launcher-", T, EFFECT),
        ("curse:", O, STORE_OPERATION),
        ("remove-curse:", O, STORE_OPERATION),
        ("enchant:", O, STORE_OPERATION),
    ),
    *_rows(
        "cross-town",
        ("town:cross-town", R, ENTRANCE),
        ("town:cross-town-shopping-needs-funds", T, EFFECT),
        ("town:morivant", R, ENTRANCE),
    ),
    *_rows(
        "survival",
        ("survival:", T, EFFECT),
        ("survival:mana-home-approach", R, ENTRANCE),
        ("survival:mana-sale-approach", R, ENTRANCE),
        ("survival:mana-shop-approach", R, ENTRANCE),
        ("survival:shop-approach", R, ENTRANCE),
        # Rev 9.2 (T2): the survival errands' native-travel legs.
        ("survival:shop-travel", R, ENTRANCE),
        ("survival:mana-home-travel", R, ENTRANCE),
        ("survival:mana-sale-travel", R, ENTRANCE),
        ("survival:mana-shop-travel", R, ENTRANCE),
        ("survival:shop-travel:await-entry", O, STORE_OPERATION),
        ("survival:mana-home-travel:await-entry", O, STORE_OPERATION),
        ("survival:mana-sale-travel:await-entry", O, STORE_OPERATION),
        ("survival:mana-shop-travel:await-entry", O, STORE_OPERATION),
        ("survival:seek-exit", R, WALK_TARGET),
        ("weak-fainting", T, EFFECT),
        ("status-threat:", T, EFFECT),
        ("status-threat:retreat", R, WALK_TARGET),
        ("status-threat:stairs", O, FLOOR_CHANGE),
        ("town:kill-mob", R, WALK_TARGET),
        ("town:kill-mob-friendly", T, EFFECT),
        ("town:eat-before-travel", T, EFFECT),
        ("town:recover", T, EFFECT),
        ("town:seek-shelter", R, WALK_TARGET),
        ("confused:", T, EFFECT),
        ("item:", T, EFFECT),
        ("mana-food:", T, EFFECT),
        ("mana-food:seek-", R, WALK_TARGET),
        ("stat-gain:", T, EFFECT),
        ("experience:", T, EFFECT),
        ("wilderness:escape-scroll", T, EFFECT),
        ("wilderness:flee", T, EFFECT),
        ("refill-light", T, EFFECT),
        ("restore-lantern", T, EFFECT),
        ("eat", T, EFFECT),
        ("rest", T, EFFECT),
    ),
    *_rows(
        "departure",
        ("depart", T, EFFECT),
        ("descend", O, FLOOR_CHANGE),
        ("recall", O, FLOOR_CHANGE),
        ("return:", T, EFFECT),
        ("return:recall", O, FLOOR_CHANGE),
        ("return:wait-recall", O, FLOOR_CHANGE),
        ("return:await-recall-confirmation", O, FLOOR_CHANGE),
        ("return:ascend", O, FLOOR_CHANGE),
        ("return:seek-upstairs", R, WALK_TARGET),
        # every producer of it emits the search key in place
        ("return:search-upstairs", T, EFFECT),
        ("return:seek-secret-wall", R, WALK_TARGET),
        ("return:explore", R, WALK_TARGET),
        ("return:seek-loot", R, WALK_TARGET),
        ("stair:", O, FLOOR_CHANGE),
        ("stair:observation-timeout-probe", T, EFFECT),
        ("postlevel:", T, EFFECT),
        ("repetition-depart", T, EFFECT),
        ("town:repetition-depart", T, EFFECT),
        ("town:repetition-depart:enter", O, FLOOR_CHANGE),
        ("town:repetition-depart:recall", O, FLOOR_CHANGE),
        ("town:entrance", T, EFFECT),
        ("town:entrance-step-off:", R, WALK_TARGET),
        ("town:wait-recall", O, FLOOR_CHANGE),
        ("town:wait-recall-step-off", R, WALK_TARGET),
        ("town:await-recall-confirmation", O, FLOOR_CHANGE),
        ("town:recall-to-", O, FLOOR_CHANGE),
        ("town:cancel-", T, EFFECT),
        ("town:unsafe-recall-fallback", T, EFFECT),
        ("wilderness:no-safe-route", T, EFFECT),
        ("esp-threat:leave-", O, FLOOR_CHANGE),
        ("seek-downstairs", R, WALK_TARGET),
        ("approach-descent", R, WALK_TARGET),
        ("clear-descent", R, WALK_TARGET),
    ),
    *_rows(
        "town-plan",
        ("town:blocked", T, EFFECT),
        ("town:procurement", T, EFFECT),
        ("procurement:", T, EFFECT),
        ("town-plan:", T, EFFECT),
        ("quest:readiness", T, EFFECT),
        ("town:repetition-required-shopping", T, EFFECT),
    ),
    *_rows(
        "rumor",
        ("town:rumor", R, ENTRANCE),
        ("town:rumor-batch", T, EFFECT),
        ("town:rumor-needs-funds", T, EFFECT),
        ("town:rumor-wait-supplies", T, EFFECT),
    ),
    *_rows(
        "quest-request",
        ("fixedquest:", T, EFFECT),
        ("fixedquest:approach", R, ENTRANCE),
        ("fixedquest:reward-approach", R, ENTRANCE),
        ("fixedquest:reward-approach:route-unavailable", T, EFFECT),
        ("fixedquest:claim:approach", R, ENTRANCE),
        ("fixedquest:claim:approach:route-unavailable", T, EFFECT),
        ("fixedquest:claim:approach:unsatisfiable", T, EFFECT),
        ("fixedquest:request:approach", R, ENTRANCE),
        ("fixedquest:request:approach:route-unavailable", T, EFFECT),
        ("fixedquest:request:approach:unsatisfiable", T, EFFECT),
        ("fixedquest:q22-travel", R, ENTRANCE),
        ("fixedquest:q22-travel:route-unavailable", T, EFFECT),
        ("fixedquest:q22-travel:unsatisfiable", T, EFFECT),
        ("fixedquest:prepare-return", R, WALK_TARGET),
        ("fixedquest:prepare-return:route-unavailable", T, EFFECT),
        ("fixedquest:prepare-return:unsatisfiable", T, EFFECT),
        ("fixedquest:seek-exit", R, WALK_TARGET),
        ("fixedquest:enter", O, FLOOR_CHANGE),
        ("fixedquest:exit", O, FLOOR_CHANGE),
        ("quest:", T, EFFECT),
        ("quest:enter:approach", R, ENTRANCE),
        ("quest:enter:approach:route-unavailable", T, EFFECT),
        ("quest:enter:approach:unsatisfiable", T, EFFECT),
        ("quest:regen:ascend", O, FLOOR_CHANGE),
        ("quest:regen:descend", O, FLOOR_CHANGE),
        ("opening-q34:", T, EFFECT),
        ("bounty:cashout", T, EFFECT),
        ("bounty:step-off", R, WALK_TARGET),
        ("bounty:leave", T, EFFECT),
    ),
    *_rows(
        "detectors",
        ("livelock:", T, EFFECT),
        ("livelock:ascend", O, FLOOR_CHANGE),
        ("livelock:recall-escape", O, FLOOR_CHANGE),
        ("livelock:seek-", R, WALK_TARGET),
        ("town-progress-invariant:", T, EFFECT),
        ("town-progress-invariant:boxed-breakout-travel", R, ENTRANCE),
        ("town-progress-invariant:boxed-breakout-travel:await-entry", O, STORE_OPERATION),
        ("town-liveness-invariant:", T, EFFECT),
        ("town:cycle-break", T, EFFECT),
        ("posting-contract:", T, EFFECT),
        ("stuck:", T, EFFECT),
        ("stuck:ascend", O, FLOOR_CHANGE),
        ("stuck:recall-escape", O, FLOOR_CHANGE),
        ("stuck:seek-stairs", R, WALK_TARGET),
        ("novel:", T, EFFECT),
        ("breakout", T, EFFECT),
        ("breakout:seek-frontier", R, WALK_TARGET),
        # a tunnel command toward a stair the reason site cannot name
        ("breakout:dig-to-stairs", T, EFFECT),
        ("no-wait:", T, EFFECT),
        ("nav:", T, EFFECT),
        ("warning:", T, EFFECT),
        ("dark:", R, WALK_TARGET),
        ("dark:locomotion-exhausted", T, EFFECT),
        ("dark:no-recovery:", T, EFFECT),
        ("dark:probe", T, EFFECT),
    ),
    *_rows(
        "positioning",
        ("detected:", R, WALK_TARGET),
        ("melee:choke", T, EFFECT),
        ("melee:choke-reposition", R, WALK_TARGET),
        ("summoner:hold-choke", T, EFFECT),
        ("threat:reposition", R, WALK_TARGET),
        ("threat:avoid-engagement", R, WALK_TARGET),
        ("threat:paralyzer-avoid", R, WALK_TARGET),
        ("threat:paralyzer-avoid:blocked-step", T, EFFECT),
        ("paralyzer-guard:", R, WALK_TARGET),
    ),
    *_rows(
        "esp-threat",
        ("esp-threat:hunt-", R, WALK_TARGET),
        ("esp-threat:hunt-heal", T, EFFECT),
        ("esp-threat:hunt-speed", T, EFFECT),
        ("melee:esp-threat-hunt", T, EFFECT),
    ),
    *_rows(
        "escape",
        ("emergency:", T, EFFECT),
        ("emergency:recall", O, FLOOR_CHANGE),
        ("emergency:stairs", O, FLOOR_CHANGE),
        ("emergency:seek-upstairs", R, WALK_TARGET),
        ("flee", T, EFFECT),
        ("flee:stairs", O, FLOOR_CHANGE),
        ("combat:disengage", T, EFFECT),
        ("combat:disengage-recall", O, FLOOR_CHANGE),
        ("combat:disengage-stairs", O, FLOOR_CHANGE),
        ("combat:disengage-seek-upstairs", R, WALK_TARGET),
        ("combat:fruitless", T, EFFECT),
        ("unseen:", T, EFFECT),
        ("unseen-recall:", T, EFFECT),
        ("breeder-breakthrough:", T, EFFECT),
        ("breeder-breakthrough:ascend", O, FLOOR_CHANGE),
        ("breeder-breakthrough:recall", O, FLOOR_CHANGE),
        ("breeder-breakthrough:wait-recall", O, FLOOR_CHANGE),
        ("breeder-breakthrough:seek-", R, WALK_TARGET),
        ("guardian:teleport-to-cover", T, EFFECT),
        ("summoner:retreat", T, EFFECT),
        ("summoner:stairs", O, FLOOR_CHANGE),
        ("threat:scroll", T, EFFECT),
        ("threat:wait", T, EFFECT),
    ),
    *_rows(
        "combat",
        ("melee", T, EFFECT),
        ("ranged:", T, EFFECT),
        ("summoner:ranged-kill", T, EFFECT),
        ("unique:quaff-", T, EFFECT),
    ),
    *_rows("hunt", ("hunt", R, WALK_TARGET)),
    *_rows(
        "explore",
        ("explore", R, WALK_TARGET),
        ("explore:", T, EFFECT),
        ("search", T, EFFECT),
        ("seek-secret-wall", R, WALK_TARGET),
        ("probe", T, EFFECT),
    ),
    *_rows(
        "floor-loot",
        ("seek-loot", R, WALK_TARGET),
        ("loot:", T, EFFECT),
        ("loot:seek-", R, WALK_TARGET),
        ("chest:", T, EFFECT),
        ("chest:approach", R, WALK_TARGET),
        ("chest:return-reserved-position", R, WALK_TARGET),
        ("chest:step-off", R, WALK_TARGET),
        ("victory:", R, WALK_TARGET),
        ("conquest:", R, WALK_TARGET),
    ),
    *_rows(
        "quest-sweep",
        ("quest-strategy:", T, EFFECT),
        ("quest-strategy:approach-", R, WALK_TARGET),
        ("quest-strategy:placement-sweep", R, WALK_TARGET),
        ("quest-strategy:placement-sweep-repeat", T, EFFECT),
        ("quest-strategy:q2-approach-", R, WALK_TARGET),
        ("quest-strategy:q2-blue-confirm-approach", R, WALK_TARGET),
        ("quest-strategy:q2-breach-approach", R, WALK_TARGET),
        ("quest-strategy:q2-final-patrol", R, WALK_TARGET),
        ("quest-strategy:q2-final-patrol-round-complete", T, EFFECT),
    ),
    *_rows(
        "bookkeeping",
        ("periodic:", T, EFFECT),
        ("town:character-dump", T, EFFECT),
    ),
    *_rows(
        "idle",
        ("policy:", T, EFFECT),
        ("wait", T, EFFECT),
    ),
    # ``misc`` keeps its registration (design 6/S2a) but the census answers
    # an earlier family for every prefix except ``town:misc:``; each still
    # needs its row so the table cannot silently lose one.
    *_rows(
        "misc",
        ("policy:", T, EFFECT),
        ("town:misc:", T, EFFECT),
        ("town:character-dump", T, EFFECT),
        ("periodic:", T, EFFECT),
        ("explore", R, WALK_TARGET),
        ("melee", T, EFFECT),
        ("hunt", R, WALK_TARGET),
        ("esp-threat:hunt-", R, WALK_TARGET),
        ("seek-loot", R, WALK_TARGET),
        ("wait", T, EFFECT),
    ),
)

def owners_with(kind: str, content: str) -> frozenset[str]:
    """The families that have a row of this kind and content (rev 9.2 U)."""
    return frozenset(
        row.family for row in GOAL_TYPING
        if row.kind == kind and row.content == content and row.family != "misc"
    )


# The owners a shared store goal can belong to, derived from the table so the
# closing sites of rev 9.2 item U name owners without a hand-kept list.
ENTRANCE_OWNERS = owners_with(GOAL_REACH, ENTRANCE)
STORE_OPERATION_OWNERS = owners_with(GOAL_OBSERVE, STORE_OPERATION)
TRANSACTION_OWNERS = owners_with(GOAL_OBSERVE, TRANSACTION)

# The owners whose walks share one committed target, named by the closing
# sites that drop or reach that target (rev 9.2 U).  Each is the set of
# families whose producers write that target into the slot.
LOOT_OWNERS = frozenset(
    {"floor-loot", "fundraising", "departure"}  # seek-loot, fundraise:, return:
)
EXPLORE_GOAL_OWNERS = frozenset(
    # explore; return:explore; breakout:seek-frontier; the fundraising and
    # quest-sweep exploration legs
    {"explore", "departure", "detectors", "fundraising", "quest-sweep"}
)
MONSTER_CHASE_OWNERS = frozenset(
    {"hunt", "departure", "survival"}  # hunt, clear-descent, town:kill-mob-approach
)
# A confirmed Home withdrawal or deposit completes the Home operation of any
# owner that posts one, under the sources those owners declare it with: the
# store-operation and transaction table contents, and the expectation names
# they post.
HOME_EFFECT_OWNERS = frozenset(
    {"home-visit", "home-errand", "home-scan", "calibration", "equipment-txn"}
)
HOME_EFFECT_SOURCES = (
    STORE_OPERATION,
    TRANSACTION,
    "equipment-transaction",
    "home-errand:",
    "home-withdrawal:",
    "home:",
)

# Why a Reach row declared Terminal (rev 9.2 C and D).
GOAL_NOTE_NO_SLOT = "no-slot"
GOAL_NOTE_OWNER_MISMATCH = "owner-mismatch"

_BY_FAMILY: dict[str, tuple[GoalTypingRow, ...]] = {}
for _row in GOAL_TYPING:
    _BY_FAMILY[_row.family] = (*_BY_FAMILY.get(_row.family, ()), _row)
del _row


def goal_typing(family: str, reason: str | None) -> GoalTypingRow | None:
    """The row of ``family`` whose prefix is the longest that ``reason`` has.

    ``reason`` is normalised exactly as the arbiter normalises it (an empty
    reason is ``policy:none``), so the census and this table read the same
    string.  ``None`` means the family has no row for the reason.
    """
    normalized = reason or "policy:none"
    best: GoalTypingRow | None = None
    for row in _BY_FAMILY.get(family, ()):
        if normalized.startswith(row.prefix) and (
            best is None or len(row.prefix) > len(best.prefix)
        ):
            best = row
    return best


# -- survival (design rev 9 item 3) ---------------------------------------

# The emergency ladder's output (P:5558-5562 enters them into EscapeState as
# ``emergency``), the disengage family, the unseen-attacker family and the
# ESP-threat floor exit.
SURVIVAL_REASON_PREFIXES = (
    "emergency:",
    "unseen-recall:",
    "guardian:teleport-to-cover",
    "combat:disengage",
    "unseen:",
    "esp-threat:leave-",
)
# A ``return:`` decision is survival only while the trigger that started the
# return is a danger trigger (policy_combat.py ``_last_return_trigger``).
SURVIVAL_RETURN_PREFIX = "return:"
SURVIVAL_RETURN_TRIGGERS = frozenset(
    {"esp-threat", "unseen-attacker", "guardian-reposition"}
)
SURVIVAL_RETURN_TRIGGER_PREFIX = "emergency-"
# The ordinary owners the user's list leaves out on purpose (design rev 9
# item 3, "This overrides section 3.2").  Nothing reads this in the policy;
# the survival test asserts that none of them is survival.
ORDINARY_OWNER_PREFIXES = (
    "flee",
    "summoner:retreat",
    "summoner:stairs",
    "threat:scroll",
    "threat:wait",
    "breeder-breakthrough:",
    "combat:fruitless",
    "status-threat:",
    "confused:",
    "town:recover",
    "town:seek-shelter",
)


def is_survival_return_trigger(trigger: str | None) -> bool:
    return bool(trigger) and (
        trigger in SURVIVAL_RETURN_TRIGGERS
        or trigger.startswith(SURVIVAL_RETURN_TRIGGER_PREFIX)
    )


def is_survival(reason: str | None, return_trigger: str | None = None) -> bool:
    """Whether a decision is survival in the sense of design rev 9 item 3."""
    reason = reason or ""
    if reason.startswith(SURVIVAL_REASON_PREFIXES):
        return True
    return reason.startswith(SURVIVAL_RETURN_PREFIX) and is_survival_return_trigger(
        return_trigger
    )
