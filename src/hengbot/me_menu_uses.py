"""The declared uses of the Magic-Eater menu, in the order they are asked.

A new use is one row here (its module subclasses me_menu.MagicEaterMenu).  The
order is the order a key is offered to the compilers: a key the first use owns
never reaches the later ones.
"""

from hengbot.magic_eater_input import ABSORBED_USE
from hengbot.me_device_attacks_input import DEVICE_USE
from hengbot.me_powerful_activation_input import POWERFUL_USE
from hengbot.me_powers_refresh_input import BROWSE_USE


USES = (ABSORBED_USE, DEVICE_USE, POWERFUL_USE, BROWSE_USE)


def compile_menu_key(key, owner):
    """(prefix, steps) of the first use that owns ``key``, else None."""
    for use in USES:
        plan = use.compile(key, owner)
        if plan is not None:
            return plan
    return None


def advance_menus(executor, screen, match, deadline, outcome):
    """The result of the first use that answers the observed screen, else None.

    A use that ends its step returns None, so the next step in the queue is
    still offered to the uses after it.
    """
    for use in USES:
        result = use.advance(executor, screen, match, deadline, outcome)
        if result is not None:
            return result
    return None
