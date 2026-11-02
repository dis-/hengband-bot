"""Keep recorded replays on the consumable handling of their recorded boards.

``pre_consumable_table_rule`` / ``pre_consumable_table_replay``: multi-step
replays whose subject is not potion/scroll handling and whose later recorded
rows answer the recorded keys.  The owner's consumable table (2026-11-02,
consumable_policy) shelves 「拾って自宅に片付ける」 kinds and destroys
「捨てる」 kinds, so such a replay now takes a Home deposit or a junk destroy
earlier than its recording, and the recorded rows after it cannot answer that
key.  This wall answers the table's two pack predicates (``discarded``,
``shelved_at_home``) and the ``table-discard`` junk class as before the
table, and nothing else.  Tests whose subject is the table pin the new
behaviour instead (tests/test_consumable_policy_recorded.py).
"""

from contextlib import contextmanager
from functools import wraps
from unittest.mock import patch

from hengbot import consumable_policy
from hengbot.policy import HengbotPolicy

# The disposable / low-level sale kinds before the table
# (policy_constants DISPOSABLE_POTION_SVALS / DISPOSABLE_SCROLL_SVALS).
PRE_TABLE_DISPOSABLE = frozenset({
    (75, 28), (75, 34), (75, 11), (75, 31),
    (70, 30), (70, 28), (70, 27), (70, 29), (70, 24), (70, 33), (70, 34),
})
_JUNK_CLASS = HengbotPolicy._junk_class


def _pre_table_discarded(item):
    return bool(getattr(item, "aware", True)) and (item.tval, item.sval) in PRE_TABLE_DISPOSABLE


def _pre_table_junk_class(policy, snapshot, item):
    junk = _JUNK_CLASS(policy, snapshot, item)
    return None if junk == "table-discard" else junk


@contextmanager
def pre_consumable_table_rule():
    """The disposable kinds, junk and Home shelving before 2026-11-02."""
    with patch.object(consumable_policy, "discarded", _pre_table_discarded), \
            patch.object(consumable_policy, "shelved_at_home", lambda _item: False), \
            patch.object(HengbotPolicy, "_junk_class", _pre_table_junk_class):
        yield


def pre_consumable_table_replay(test):
    """Run one test method under ``pre_consumable_table_rule``."""
    @wraps(test)
    def wrapper(*args, **kwargs):
        with pre_consumable_table_rule():
            return test(*args, **kwargs)
    return wrapper
