"""The 99F/100F battle recharges a drained food wand with a Scroll of Recharging (owner 2026-11-26).

Owner 2026-11-26 (verbatim): 「魔力充填の巻物を10巻持っていき、空腹かつ3本とも空の場合のみ充填して
食料とする」.  n1-c life-222 (Zombie Magic-Eater, Angband 100F, 2026-11-26 10:00-10:04) carried the
three food wands of finale_prep's food step (謎の魔法棒 {@E1} {@E2} {@E3}, 71 charges); monsters'
UN_POWER blows (「ザックからエネルギーが吸い取られた！」, monster-attack/monster-eating.cpp
process_un_power) left each at 0 charges, and hungry at turn 12325001 with nothing to eat the battle
recalled (angband_finale_battle ``starving_out``) with the Serpent of Chaos almost dead.

The carry is angband_finale's (``RECHARGING``, ten scrolls for a race that eats device charges);
this module is its only reader:

* ``recharge_due``: hungry (the game's 「お腹が空いてきた」 or worse), every food wand drained -- the
  pack's aware Wands of Wonder, each identified at 0 charges or marked empty ({空}) -- and nothing
  else to eat (policy ``_find_edible``), a scroll carried, no recharged wand waiting to be eaten
  and no read refused on this floor.  Then ``key`` reads the scroll on one of the wands
  (do_cmd_read_scroll, then recharge()'s prompt 「どのアイテムに魔力を充填しますか?」 answered with
  the wand's pack letter: spell-kind/magic-item-recharger.cpp).  At no other time is a scroll read:
  not for a wand that still has charges, not for an attack device.
* The outcomes (recharge(power 130) on a Wand of Wonder, level 3, at 0 charges: strength
  (100 + 130 - 3) / 15 = 15, so 1 in 15 fails): a success adds 1-13 charges
  (randnum1(1 + pval 24 / 2)) and clears the wand's KNOWN flag, so the board shows it unidentified
  with no charges (bot-json-output.cpp make_item_json): ``recharged`` -- it is eaten (``key``,
  ``RECHARGED_EAT_REASON``; eating sets no KNOWN flag, cmd-eat.cpp exe_eat_charge_of_magic_device,
  and an empty one becomes {空}).  A Magic-Eater's failure (PlayerClass::is_wizard) destroys the
  wand three times in four, else drains it: the next board is hungry with the wands drained again,
  and the next scroll is read, until no scroll or no food wand is left.
* ``relief``: the battle's ``starving_out`` (its recall) does not hold while a recharge is due or a
  recharged wand waits: only with no scroll, no food wand, or a refused read is the recall read.
* A read the game refused (the scroll count unchanged on a later game turn of the same floor:
  ``Watch``) is not sent again on that floor.
"""
from __future__ import annotations

from dataclasses import dataclass

from hengbot.model import TVAL_WAND

REASON = "angband-finale"
RECHARGE_REASON = f"{REASON}:recharge-food"
RECHARGED_EAT_REASON = f"{REASON}:eat-recharged"
STATE = "_finale_recharge_food"


@dataclass
class Watch:
    """The last read of this module: the floor, its game turn, the scroll count before it; and
    whether a read on this floor was refused."""
    floor: tuple | None = None
    posted_turn: int | None = None
    scrolls_before: int = 0
    refused: bool = False


def watch(policy) -> Watch:
    held = getattr(policy, STATE, None)
    if held is None:
        held = Watch()
        setattr(policy, STATE, held)
    return held


def applies(snapshot) -> bool:
    """A race that eats device charges (finale_prep ``food_wanted``)."""
    from hengbot.policy_constants import FOOD_TYPE_MANA
    return getattr(snapshot.player, "food_type", None) == FOOD_TYPE_MANA


def scrolls(snapshot) -> int:
    from hengbot import angband_finale
    return angband_finale.carried(snapshot, angband_finale.RECHARGING)


def _scroll(snapshot):
    from hengbot import angband_finale
    return next((item for item in snapshot.inventory
                 if angband_finale.is_recharging(item) and item.count > 0), None)


def food_wands(snapshot) -> list:
    """The pack's aware Wands of Wonder (finale_prep's food wands), identified or not."""
    from hengbot.magic_eater_devices import SV_WAND_WONDER
    return [item for item in snapshot.inventory
            if item.tval == TVAL_WAND and item.sval == SV_WAND_WONDER
            and getattr(item, "aware", True) and item.count > 0]


def _drained(item) -> bool:
    return (item.known and item.charges <= 0) or item.known_empty


def recharged(snapshot) -> list:
    """The food wands a recharge left unidentified and not yet eaten empty."""
    return [item for item in food_wands(snapshot) if not item.known and not item.known_empty]


def observe(policy, snapshot) -> Watch:
    """The last read's answer on a later game turn of its floor; a new floor forgets it."""
    held = watch(policy)
    if held.floor != snapshot.floor_key:
        held.floor, held.posted_turn, held.scrolls_before, held.refused = (
            snapshot.floor_key, None, 0, False)
    elif (held.posted_turn is not None and snapshot.turn is not None
            and snapshot.turn > held.posted_turn):
        if scrolls(snapshot) >= held.scrolls_before:
            held.refused = True
        held.posted_turn = None
    return held


def _drained_all(snapshot) -> list:
    """Every food wand drained (and at least one): the wands, else []."""
    wands = food_wands(snapshot)
    return wands if wands and all(_drained(item) for item in wands) else []


def relief(policy, snapshot) -> bool:
    """Something to eat comes from the food wands still: a recharged wand waits, or a scroll can
    recharge a drained one (``starving_out`` does not hold)."""
    if not applies(snapshot):
        return False
    held = observe(policy, snapshot)
    if recharged(snapshot):
        return True
    return bool(scrolls(snapshot) and _drained_all(snapshot) and not held.refused)


def recharge_due(policy, snapshot) -> bool:
    """Owner 2026-11-26 「空腹かつ3本とも空の場合のみ充填」: hungry, every food wand drained,
    nothing else to eat, a scroll carried, none recharged waiting, no refused read here."""
    if not applies(snapshot) or not snapshot.player.hungry or recharged(snapshot):
        return False
    held = observe(policy, snapshot)
    return bool(not held.refused and scrolls(snapshot) and _drained_all(snapshot)
                and policy._find_edible(snapshot) is None)


def _hostile_near(policy, snapshot) -> bool:
    """Merely hungry (not weak) with a hostile within four cells: the eat waits (the battle's
    ``_eat_key`` rule, policy ``_starvation_near_hostiles``)."""
    from hengbot.policy_constants import STARVING_FOOD_STATES
    return (snapshot.player.food_state not in STARVING_FOOD_STATES
            and policy._starvation_near_hostiles(policy._physical_hostiles(snapshot)))


def key(policy, snapshot) -> str | None:
    """Hungry: eat a recharged food wand, else read the scroll on a drained one when due."""
    from hengbot.item_reservation import reserved_item_command
    if not applies(snapshot) or not snapshot.player.hungry:
        return None
    held = observe(policy, snapshot)
    waiting = recharged(snapshot)
    if waiting:
        if _hostile_near(policy, snapshot):
            return None
        food = waiting[0]
        eaten = reserved_item_command(policy, snapshot, "eat", food)
        if eaten is not None:
            policy.last_reason = RECHARGED_EAT_REASON
        return eaten
    if not recharge_due(policy, snapshot) or _hostile_near(policy, snapshot):
        return None
    if not policy._can_read_scrolls(snapshot):
        return None
    scroll = _scroll(snapshot)
    wand = min(_drained_all(snapshot), key=lambda item: item.slot)
    read = policy._read_key(snapshot, scroll, wand.slot)
    if read is None:
        return None
    policy.last_reason = RECHARGE_REASON
    held.posted_turn, held.scrolls_before = snapshot.turn, scrolls(snapshot)
    return read
