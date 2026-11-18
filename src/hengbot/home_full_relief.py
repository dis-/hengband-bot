"""The full-Home relief's state: one typed container in place of a string-keyed dict.

Maintainability review 2026-11-18 S2 / (a)-7, owner 2026-11-18 Q5 「まず入れ物を整理して様子を
見る」: the relief (``HomeMixin._home_full_relief``) was a dict of 30 keys read by string at about
70 sites, and two of the night's stops were a key one cleanup forgot.  This is the same state with
fixed fields: the relief decides exactly as the dict did.

A field at its default is what the dict's missing key was: every reader of the dict read a missing
key as its field's default here (``relief.get("mode")`` is None, ``relief.get("pack_only", False)``
is False, ``relief.get("skipped", {})`` is empty).  The two fields read for presence
(``"stock_count" in relief`` and ``relief.get("destroy_before_count", count)``) are never stored as
None, so None is their absence.

``reset`` puts fields back to their defaults (the dict's ``pop``), ``consume`` reads one and
resets it, and ``end_sale`` is the one cleanup after the current ware's sale, destroy or skip.

Old saved state (pickles, gzip JSON snapshots and the tests' dicts) holds the dict: the policy
attribute (``RELIEF_ATTRIBUTE``) reads a dict into this type on first read and on every write, and
``policy_state.normalize_policy_state`` does on restore.  The mapping methods (``relief["sale"]``,
``.get``, ``.pop``, ``.setdefault``, ``.update``, ``in``) remain for the recorded tests written
against the dict; the bot's own code reads the fields (``tests/test_home_full_relief_container``).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import MISSING, dataclass, field, fields
from typing import Any

# The policy attribute this container is the value of.
RELIEF_ATTRIBUTE = "_home_full_relief"


def _dict() -> dict:
    return {}


@dataclass
class HomeFullRelief:
    """One full-Home relief: the blocked deposits it makes room for and the ware it handles now."""

    # --- The relief itself (set when it begins) ---------------------------------------------
    # The blocked deposit batch the relief makes room for (``_find_home_deposit`` entries);
    # the junk sweep has none.  Filed as the retry batch when the relief ends.
    deposits: tuple = ()
    # Home slots still to free: each observed shelf take that left the pack earns one.
    remaining: int = 0
    # The town whose Home is full; the relief waits while the player is in another town.
    town: Any = None
    # The Home junk sweep (one junk ware per visit, ``_begin_home_junk_sweep``), not a
    # full Home: frees no deposit and never routes back to Home.
    sweep: bool = False

    # --- The current ware (``end_sale`` forgets these) -----------------------------------------
    # The ware handled now: (signature, store type it is sold to, carried count before the take).
    sale: tuple | None = None
    # The ware is carried: taken out of the Home, or chosen from the pack.
    withdrawn: bool = False
    # What happens to the ware: "sale", "destroy" or "identify"; None between wares.
    mode: str | None = None
    # The ware was chosen from the pack (it frees no Home slot).
    pack_only: bool = False
    # The observed take: (signature, count taken), for the settled shelf count after the sale.
    taken: tuple | None = None
    # The Home's count of the ware's signature when it was chosen (None: not counted).
    stock_count: int | None = None
    # The sale ware chosen as clearly useless (item_fate.relief_useless).
    useless: Any = None
    # The shelf sale ware a reserve-bound pack takes only to sell at once (item_fate.relief_round_trip).
    round_trip: Any = None
    # A destroy key offered and not yet confirmed posted (``confirm_key_posted`` moves it on).
    destroy_pending_key: str | None = None
    # The offered destroy was posted; its effect is awaited.
    destroy_posted: bool = False
    # The carried count of the ware when its destroy was offered (None: none offered).
    destroy_before_count: int | None = None
    # The work id of the destroy's execution offer.
    destroy_work_id: str | None = None
    # An Identify offered and not yet confirmed posted: (key, watch, counts).
    identify_pending: tuple | None = None
    # A posted Identify's watch: (tval, quantity, previous signatures, known, fully known).
    identifying: tuple | None = None
    # The carried known counts by (tval, sval) before the posted Identify.
    identification_counts: dict | None = None
    # The relief waits for a normal identification source before it goes on.
    awaiting_identification_source: bool = False

    # --- Across wares (the relief's memory while it runs) ----------------------------------
    # Retained wares by signature and why (``_home_full_skip_key``).
    skipped: dict = field(default_factory=_dict)
    # The Home count of a skipped ware when it was skipped: more on the shelf lifts the skip.
    skipped_home_counts: dict = field(default_factory=_dict)
    # The shelf count each sold ware must stay below (a rise is a put-back, not a sale).
    settled_home_counts: dict = field(default_factory=_dict)
    # Identify-capacity skips by signature: (carried staves, staff ready, count).
    identify_cap_skip_fingerprint: dict = field(default_factory=_dict)
    # The ware the relief released from the rank keep (item_fate.fate's ROOM).
    rank_released: Any = None
    # The sweep's junk class for its destroy reason (``home:junk-sweep:<class>``).
    sweep_class: str | None = None
    # The sweep's ware is the Home cash sale's (home_cash_sale).
    cash: Any = None
    # The sweep's ware is the Black Market *Destruction* fund's (bm_destruction_fund).
    fund: Any = None

    # --- Resetting ------------------------------------------------------------------------------
    def reset(self, *names: str) -> None:
        """Put ``names`` back to their defaults (the dict's ``pop(name, None)``)."""
        for name in names:
            setattr(self, name, _default(name))

    def consume(self, name: str) -> Any:
        """The field's value, reset to its default (the dict's ``pop(name, default)``)."""
        value = getattr(self, name)
        self.reset(name)
        return value

    def end_sale(self, *also: str) -> None:
        """Forget the current ware: the one cleanup after its sale, destroy or skip.

        Always the ware itself, its carried flag and its clearly-useless and round-trip marks
        (item_fate reads them while the ware is chosen); ``also`` names the rest each caller
        forgets (``SALE_DESTROY_FIELDS``, ``SKIP_FIELDS``).
        """
        self.sale = None
        self.withdrawn = False
        self.reset("useless", "round_trip", *also)

    # --- Old state ------------------------------------------------------------------------------
    @classmethod
    def from_mapping(cls, state: Mapping) -> "HomeFullRelief":
        """An old dict's relief.  A key no field names was read by no code: it is dropped."""
        relief = cls()
        for name, value in state.items():
            if name in FIELD_NAMES:
                setattr(relief, name, value)
        return relief

    # --- The dict's reading, for the recorded tests written against it ------------------------
    def _present(self, name: str) -> bool:
        return name in ALWAYS_PRESENT or getattr(self, name) != _default(name)

    def __contains__(self, name: object) -> bool:
        return name in FIELD_NAMES and self._present(name)

    def __getitem__(self, name: str) -> Any:
        if name not in FIELD_NAMES:
            raise KeyError(name)
        return getattr(self, name)

    def __setitem__(self, name: str, value: Any) -> None:
        if name not in FIELD_NAMES:
            raise KeyError(name)
        setattr(self, name, value)

    def get(self, name: str, default: Any = None) -> Any:
        return getattr(self, name) if name in self else default

    def pop(self, name: str, *default: Any) -> Any:
        if name not in self:
            if default:
                return default[0]
            raise KeyError(name)
        return self.consume(name)

    def setdefault(self, name: str, default: Any = None) -> Any:
        if name not in self:
            self[name] = default
        return getattr(self, name)

    def update(self, state: Mapping = (), **more: Any) -> None:
        for name, value in dict(state, **more).items():
            self[name] = value


FIELD_NAMES = frozenset(entry.name for entry in fields(HomeFullRelief))
# The keys every relief dict was created with.
ALWAYS_PRESENT = frozenset({"deposits", "remaining", "town", "sale", "withdrawn"})
_DEFAULTS = {entry.name: entry for entry in fields(HomeFullRelief)}

# The destroy's fields, forgotten when a restart cannot prove the destroy was posted and
# when the ware's removal is observed.
DESTROY_FIELDS = ("destroy_posted", "destroy_pending_key", "destroy_before_count", "destroy_work_id")
# What the observed removal of the ware forgets besides the ware (``end_sale``).
SALE_DESTROY_FIELDS = (*DESTROY_FIELDS, "mode")
# What a skipped ware forgets besides the ware (``_home_full_skip_key``).
SKIP_FIELDS = ("identifying", "identification_counts", "identify_pending", "mode", "useless",
               "round_trip", "destroy_posted", "destroy_pending_key", "destroy_before_count",
               "destroy_work_id", "pack_only", "stock_count", "taken")


def _default(name: str) -> Any:
    entry = _DEFAULTS[name]
    return entry.default_factory() if entry.default_factory is not MISSING else entry.default


def adopt(value: Any) -> Any:
    """``value`` as the relief attribute holds it: a dict becomes a ``HomeFullRelief``."""
    if isinstance(value, dict):
        return HomeFullRelief.from_mapping(value)
    return value


def adopt_saved(state: dict) -> None:
    """Read an old checkpoint's relief dict into the container (``normalize_policy_state``)."""
    if RELIEF_ATTRIBUTE in state:
        state[RELIEF_ATTRIBUTE] = adopt(state[RELIEF_ATTRIBUTE])


class ReliefAttribute:
    """The policy's ``_home_full_relief``: None or a ``HomeFullRelief``, kept in the instance dict.

    The value stays under its own name in ``__dict__``, so checkpoints, the observer scope's
    rebinding and ``getattr(policy, name, None)`` see it as before; a dict found there (an old
    pickle restored by ``__dict__.update``) or written here is read into the container.
    """

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        if instance is None:
            return self
        state = instance.__dict__
        try:
            value = state[self._name]
        except KeyError:
            raise AttributeError(self._name) from None
        if isinstance(value, dict):
            value = state[self._name] = adopt(value)
        return value

    def __set__(self, instance: Any, value: Any) -> None:
        instance.__dict__[self._name] = adopt(value)

    def __delete__(self, instance: Any) -> None:
        try:
            del instance.__dict__[self._name]
        except KeyError:
            raise AttributeError(self._name) from None
