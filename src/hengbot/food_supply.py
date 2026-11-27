"""Ordinary food in nutrition, and the departure reserve sized from digestion.

n1-a life-544 (2026-11-26, Amberite rogue CL14, the first character the bot played
that eats ordinary food): the food ledger counted carried food by item, so five
Hard Biscuits (500 food each) or five strips of Jerky (1500) met the departure's
"five rations" (25000 food).  Regeneration (innate to the Amberite and on the worn
Trump blade) tripled the digestion of a normal-speed character, and the last dive
(Yeek cave 5F-13F, game day 4 01:16-08:32) outlasted its food; the character
recalled hungry.

The game's facts (Hengband C:/hengband):

* ``starve_player`` (src/player/digestion-processor.cpp:29-61) runs every
  ``TURNS_PER_TICK`` (10) game turns (src/world/world-turn-processor.cpp:91,
  src/system/gamevalue.h:13); every ``TURNS_PER_TICK * 5`` = 50 game turns it
  takes ``speed_to_energy(pspeed)`` (src/core/speed-table.cpp extract_energy:
  10 at normal speed) +20 with regeneration, +20 in a monk/samurai stance, +30
  with the FAST_DIGEST curse, -5 with slow digestion, clamped to 1..100.
* Thresholds (src/player/digestion-processor.h:5-10): 15000 gorged, 10000 full,
  2000 hungry, 1000 weak, 500 fainting (paralysis 1 in 10 per tick), 100 starving.
* Nutrition (lib/edit/BaseitemDefinitions.jsonc ``parameter_value``): Ration
  (sval 35) 5000 (line 812), Hard Biscuit (32) 500 (853), Jerky (33) 1500 (878),
  Slime Mold (36) 3000 (902), Elvish Waybread (37) 7500 (932), Pint of Fine Ale
  (38) 500 (965), Pint of Fine Wine (39) 1000 (989).
* The General Store always stocks Rations (src/store/articles-on-sale.cpp:32,
  ``store_regular_sale_table``).

The ledger's food count is therefore whole Rations' worth of carried nutrition,
and the departure target the larger of ``FOOD_STOCK_TARGET`` and one planned trip
(``TRIP_GAME_TURNS``) at the board's own digestion plus one Ration of margin.  A
mana eater (food_type MANA, the Zombie) keeps its device-charge ledger untouched.
"""
from __future__ import annotations

from math import ceil

from hengbot.ability_sources import ability_source_map
from hengbot.model import TVAL_FOOD
from hengbot.policy_constants import FOOD_MIN_SVAL, FOOD_STOCK_TARGET, FOOD_TYPE_MANA

RATION_FOOD_VALUE = 5000
# sval -> nutrition (lib/edit/BaseitemDefinitions.jsonc, see the module docstring).
FOOD_VALUE_BY_SVAL = {32: 500, 33: 1500, 35: 5000, 36: 3000, 37: 7500, 38: 500, 39: 1000}
# Energy per game turn by speed (src/core/speed-table.cpp extract_energy), index speed.
_EXTRACT_ENERGY = (
    (1,) * 70
    + (2,) * 10
    + (2, 2, 2, 2, 2, 2, 2, 3, 3, 3)
    + (3, 3, 3, 3, 3, 4, 4, 4, 4, 4)
    + (5, 5, 5, 5, 6, 6, 7, 7, 8, 9)
    + tuple(range(10, 30))
    + (30, 31, 32, 33, 34, 35, 36, 36, 37, 37)
    + (38, 38, 39, 39, 40, 40, 40, 41, 41, 41)
    + (42, 42, 42, 43, 43, 43, 44, 44, 44, 44)
    + (45, 45, 45, 45, 45, 46, 46, 46, 46, 46)
    + (47, 47, 47, 47, 47, 48, 48, 48, 48, 48)
    + (49,) * 20
)
NORMAL_SPEED = 110
LASTING_SOURCES = frozenset({"equipment", "permanent"})
DIGESTION_INTERVAL = 50  # game turns: TURNS_PER_TICK * 5
# One planned trip: half a game day (a game day is 100000 game turns, TOWN_DAWN
# 10000 * TURNS_PER_TICK).  life-544's dives lasted 7 to 10 game hours.
TRIP_GAME_TURNS = 50000
MARGIN_RATIONS = 1


def food_value(item) -> int:
    """The nutrition one of ``item`` gives an ordinary eater (0 when not travel food)."""
    if item.tval != TVAL_FOOD or item.sval < FOOD_MIN_SVAL:
        return 0
    return FOOD_VALUE_BY_SVAL.get(item.sval, 0)


def is_ration_class(item) -> bool:
    """A ware worth one Ration or more: the procurement's food (Ration, Waybread)."""
    return food_value(item) >= RATION_FOOD_VALUE


def carried_food_value(items) -> int:
    return sum(food_value(item) * max(0, item.count) for item in items
               if getattr(item, "aware", True))


def carried_rations(items) -> int:
    """Whole Rations' worth of carried nutrition (the ledger's food count)."""
    return carried_food_value(items) // RATION_FOOD_VALUE


def speed_to_energy(speed: int) -> int:
    return 49 if speed > 199 else _EXTRACT_ENERGY[max(0, speed)]


def _lasting(player, ability: str) -> bool:
    """An equipment or permanent (race/class) source: what a whole trip carries."""
    return bool(frozenset(ability_source_map(player).get(ability, ())) & LASTING_SOURCES)


def digestion_per_interval(player) -> int:
    """Food lost every ``DIGESTION_INTERVAL`` game turns (digestion-processor.cpp:38-58).

    A temporary source (a spell's regeneration) does not size a trip.  The
    board's ``speed`` is the current one (a hasted board reads a larger reserve,
    never a smaller one), floored at normal speed: an overloaded pack slows the
    character only until it sheds weight.
    """
    digestion = speed_to_energy(max(NORMAL_SPEED, player.speed))
    if _lasting(player, "regenerate"):
        digestion += 20
    if _lasting(player, "slow_digest"):
        digestion -= 5
    return min(100, max(1, digestion))


def trip_rations(player, game_turns: int = TRIP_GAME_TURNS) -> int:
    """Rations eaten over ``game_turns`` of play."""
    eaten = digestion_per_interval(player) * game_turns / DIGESTION_INTERVAL
    return ceil(eaten / RATION_FOOD_VALUE)


def departure_rations(player) -> int:
    """The ordinary eater's departure reserve, in Rations: the purchase target."""
    if player.food_type == FOOD_TYPE_MANA:
        raise ValueError("a mana eater's food is device charges")
    return max(FOOD_STOCK_TARGET, trip_rations(player) + MARGIN_RATIONS)


def below_trip(player, items, extra: int = 0) -> bool:
    """An ordinary eater carries less than one planned trip eats (``trip_rations``, plus
    ``extra`` Rations a longer planned trip adds: zul_trip ``extra_food_items``).

    The departure's floor (MAINTAINABILITY.md rules 2-4, n1-a life-545 2026-11-28): the
    target's MARGIN_RATIONS and FOOD_STOCK_TARGET are a top-up the visit buys when it can;
    a trip's worth is what the departure may leave with.  Below it a food purchase may use
    the pack's departure reserve (town_pack_budget ``purchase_reserve_use``).  A mana eater's
    food is device charges and never below this floor here.
    """
    return (player.food_type != FOOD_TYPE_MANA
            and carried_rations(items) < trip_rations(player) + extra)


def items_for_rations(item, rations: int) -> int:
    """How many of ``item`` supply ``rations`` Rations' worth (0 for no food)."""
    value = food_value(item)
    if value <= 0 or rations <= 0:
        return 0
    return ceil(rations * RATION_FOOD_VALUE / value)


def procurement_food(item, wares) -> bool:
    """Whether the departure's food purchase takes ``item`` from the page ``wares``.

    A Ration or Waybread on the page is bought before a Biscuit, Jerky or Ale:
    Biscuits bought one by one for 1 gold filled pack slots with a tenth of a
    Ration each (life-544's play record).  A page without one still feeds.
    """
    if food_value(item) <= 0:
        return False
    return is_ration_class(item) or not any(is_ration_class(ware) for ware in wares)
