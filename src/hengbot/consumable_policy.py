"""The owner's potion and scroll table (owner 2026-11-02).

The owner filled one row per potion (tval 75) and scroll (tval 70) kind
(``consumable_policy.json``, copied unchanged from the owner's form
consumable-policy-20261102.json): ``buy`` 「購入する」, ``carry`` 「拾って持ち
歩く」, ``home`` 「拾って自宅に片付ける」, ``use`` 「拾って使う（飲む・読む）」 and
``discard`` 「捨てる」.  Owner answer the same day: 「要求がある時は買う」 -- the
``buy`` flag rules the ordinary (discretionary) purchases only; a requirement
(quest required_force, the mining kit, the departure supplies, a drained stat,
a curse) still buys a kind without the flag.

Only an identified kind (``item.aware``: the sval is meaningful) is looked up;
an unknown flavour keeps today's handling.

Who acts on a row:
 * ``discretionary_buy``: the optional purchase owners (the Black Market
   buy-outs, the launcher enchant scrolls) buy only a kind with ``buy``; the
   requirement rungs do not ask.
 * ``reserve_buy``: a named reserve (``RESERVES``) is a requirement over the
   table: its owner buys the kind without ``buy`` (the Temple's *Remove
   Curse* reserve, policy_shop._star_remove_curse_reserve_purchase_needed).
 * ``discarded``: policy_helpers._junk_class's ``table-discard`` class, so the
   existing junk paths (junk_destroy_now in the dungeon, the town junk rungs)
   destroy a carried one -- unless a requirement reserves it (the junk class's
   own retention / procurement gates).  It is also the full-pack disposable
   kind set (policy_helpers._is_disposable_item); an identified potion or
   scroll is no longer low-level sale stock (「捨てる」, not sold).
 * ``shelved_at_home``: policy_home._home_deposit_candidate deposits a ``home``
   kind that has no ``carry`` flag on the Home visit, unless
   ``carry_required`` names a requirement that reads it from the pack.
 * ``quaffed_on_sight`` / ``read_on_sight``: a ``use`` kind is used when safe:
   potions by the existing stat-gain owner (policy._stat_gain_quaff_key),
   scrolls by ``use_now_key`` on the dungeon's safe decision
   (junk_destroy_now.safe).  ``USE_OWNED_ELSEWHERE`` and ``USE_UNSUPPORTED``
   name the ``use`` kinds this module does not use itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

from hengbot.model import (
    RESTORE_POTION_SVAL_BY_STAT, SV_POTION_EXPERIENCE, SV_POTION_RESTORE_EXP,
    SV_SCROLL_ENCHANT_WEAPON_TO_DAM, SV_SCROLL_ENCHANT_WEAPON_TO_HIT,
    SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_IDENTIFY, SV_SCROLL_STAR_REMOVE_CURSE,
    TVAL_POTION, TVAL_SCROLL, item_requires_full_identification,
)

TABLE = Path(__file__).with_name("consumable_policy.json")
FLAGS = ("buy", "carry", "home", "use", "discard")
KINDS = {TVAL_POTION: "potion", TVAL_SCROLL: "scroll"}

# ``use`` kinds another owner already uses, with its own condition.
USE_OWNED_ELSEWHERE = {
    # policy_shop._experience_potion_quaff_key: Restore Life Levels first.
    (TVAL_POTION, SV_POTION_EXPERIENCE): "experience-quaff",
    # policy_equipment._town_enchant_launcher_key: read on the worn launcher.
    (TVAL_SCROLL, SV_SCROLL_ENCHANT_WEAPON_TO_HIT): "launcher-enchant",
    (TVAL_SCROLL, SV_SCROLL_ENCHANT_WEAPON_TO_DAM): "launcher-enchant",
}
# ``use`` kinds the bot cannot use yet (open questions for the owner): the
# self-knowledge viewer (player-info/self-info.cpp self_knowledge, an any-key
# file screen no input owner answers) and the enchant scrolls whose target
# item no rule chooses (Enchant Armour, *Enchant Armour*, *Enchant Weapon*).
USE_UNSUPPORTED = {
    (TVAL_POTION, 57): "self-knowledge-viewer",   # *Enlightenment*
    (TVAL_POTION, 58): "self-knowledge-viewer",   # Self Knowledge
    (TVAL_SCROLL, 16): "enchant-target",          # Enchant Armour
    (TVAL_SCROLL, 20): "enchant-target",          # *Enchant Armour*
    (TVAL_SCROLL, 21): "enchant-target",          # *Enchant Weapon*
}


# Reserves the owner orders over the table's ``buy`` flag.  2026-11-02 21h
# 「戦士では1枚取り置く。魔道具術師で解呪の杖を取り込み済なら買わない。」: one
# *Remove Curse* kept at Home; an absorbed power that replaces the scroll
# (me_capability.REPLACES) still waives it at the reserve's owner.
RESERVES = {
    (TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE): "star-remove-curse-reserve",
}


@dataclass(frozen=True)
class Consumable:
    tval: int
    sval: int
    names: tuple          # (ja, en) as the owner's form shows them
    buy: bool
    carry: bool
    home: bool
    use: bool
    discard: bool

    @property
    def kind(self) -> tuple[int, int]:
        return self.tval, self.sval


@lru_cache(maxsize=1)
def consumables() -> dict:
    """(tval, sval) -> Consumable, as the owner filled the table."""
    rows = json.loads(TABLE.read_text(encoding="utf-8"))["items"]
    return {(row["tval"], row["sval"]): Consumable(
        row["tval"], row["sval"], (row["name"], row["en"]),
        *(bool(row[flag]) for flag in FLAGS)) for row in rows}


def row(item) -> Consumable | None:
    """The table row of an identified potion or scroll (pack or shelf)."""
    if item.tval not in KINDS or not getattr(item, "aware", True):
        return None
    return consumables().get((item.tval, item.sval))


def discretionary_buy(kind: tuple[int, int]) -> bool:
    """「購入する」: an optional purchase owner may buy this kind.

    Kinds outside the table (devices, food, equipment) are not ruled here.
    """
    entry = consumables().get(kind)
    return entry is None or entry.buy


def reserve_buy(kind: tuple[int, int]) -> bool:
    """A reserve owner may buy this kind: a named reserve, or 「購入する」."""
    return kind in RESERVES or discretionary_buy(kind)


def discarded(item) -> bool:
    """「捨てる」: an identified kind the character never keeps."""
    entry = row(item)
    return entry is not None and entry.discard


def shelved_at_home(item) -> bool:
    """「拾って自宅に片付ける」 without 「拾って持ち歩く」."""
    entry = row(item)
    return entry is not None and entry.home and not entry.carry


def _used_here(item, tval: int) -> bool:
    entry = row(item)
    return (entry is not None and entry.use and item.tval == tval
            and entry.kind not in USE_OWNED_ELSEWHERE
            and entry.kind not in USE_UNSUPPORTED)


def quaffed_on_sight(item) -> bool:
    """A ``use`` potion drunk on sight (policy._stat_gain_quaff_key)."""
    return _used_here(item, TVAL_POTION)


def read_on_sight(item) -> bool:
    """A ``use`` scroll read on the first safe dungeon decision."""
    return _used_here(item, TVAL_SCROLL)


def carry_required(policy, snapshot, item) -> bool:
    """A requirement reads this ``home`` kind from the pack (it stays carried).

    The retention authority (``_retention_surplus``) already keeps what the
    supply ledger, the *Destruction* gate and the *Remove Curse* reserve hold;
    these are the reads that happen right after the purchase or withdrawal.
    """
    if item.tval == TVAL_SCROLL and item.sval in {
            SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_REMOVE_CURSE}:
        return (policy._required_remove_curse_kind(snapshot) is not None
                or policy._has_normal_remove_curse_target(snapshot))
    if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_IDENTIFY:
        # A carried or worn item still owes its *Identify*.
        return (policy._identification_need == "full"
                or policy._full_identification_purchase_wanted()
                or any(other.known and not other.fully_known
                       and item_requires_full_identification(other)
                       for other in (*snapshot.inventory, *snapshot.equipment)))
    if policy.quest_potion_carried_for_strategy(snapshot, item):
        return True
    if item.tval == TVAL_POTION and item.sval == SV_POTION_RESTORE_EXP:
        return bool(snapshot.player.exp_drained)
    if item.tval == TVAL_POTION:
        return any(RESTORE_POTION_SVAL_BY_STAT.get(stat) == item.sval
                   for stat in snapshot.player.drained_stats)
    return False


@dataclass
class _ReadWatch:
    """The last ``use`` read: a stack whose count did not drop was refused."""
    signature: tuple | None = None
    count: int = 0
    floor_key: tuple | None = None
    refused: set = None


def _watch(policy) -> _ReadWatch:
    watch = policy.__dict__.get("_consumable_read_watch")
    if watch is None:
        watch = policy.__dict__["_consumable_read_watch"] = _ReadWatch(refused=set())
    return watch


def use_now_key(policy, snapshot) -> str | None:
    """Read one carried ``use`` scroll when it is safe, or None."""
    from hengbot.junk_destroy_now import safe

    if not safe(policy, snapshot):
        return None
    watch = _watch(policy)
    if watch.floor_key != snapshot.floor_key:
        watch.refused.clear()
    for item in snapshot.inventory:
        if not read_on_sight(item):
            continue
        signature = policy._item_signature(item)
        if (signature == watch.signature and item.count >= watch.count
                and snapshot.floor_key == watch.floor_key):
            # The game refused the read (no light to read by, ...): this
            # floor does not ask again.
            watch.refused.add(signature)
        if signature in watch.refused:
            continue
        watch.signature, watch.count, watch.floor_key = (
            signature, item.count, snapshot.floor_key)
        policy.last_reason = "consumable:read-on-sight"
        return policy._read_key(snapshot, item)
    watch.signature = None
    return None
