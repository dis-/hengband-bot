"""Keep recorded Home-full sale replays on their recorded sale stock.

One declared wall; production retention and the reserve pins remain untouched.

``pre_star_reserve_retention_rule`` / ``pre_star_reserve_retention_replay``:
replays whose subject is not which item the Home-full relief sells (for example
the one-shot sale bookkeeping of test_oneshot_inflight_recorded) and that were
recorded before 2026-10-20 sold the one *Remove Curse* reserve that the Temple
owner ``curse:star-reserve`` stocks.  The owner decisions 2026-10-04
「呪われた装備があれば解呪を任意購入より優先」 and 2026-10-19 (one predicate answers
"is item I surplus") made ``_retention_reservation`` keep that reserve
(branch ``remove-curse:reserve``, live 2026-10-20 10:25-11:57 buy/sell churn).
This wall removes only that branch, so such a replay still composes its
recorded sale.  Replays whose subject IS the reserve pin the new divergence
instead (test_star_remove_curse_reserve_sale_recorded).
"""

from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from hengbot.policy import HengbotPolicy


@contextmanager
def pre_star_reserve_retention_rule():
    """Retain no *Remove Curse* reserve, as before 2026-10-20."""
    with patch.object(HengbotPolicy, "_star_remove_curse_reserve_retained",
                      staticmethod(lambda _item: False)):
        yield


def pre_star_reserve_retention_replay(cls):
    """Run a TestCase class (setUpClass through tearDownClass) under the rule."""
    original = cls.__dict__["setUpClass"].__func__

    def set_up_class(klass):
        stack = ExitStack()
        stack.enter_context(pre_star_reserve_retention_rule())
        klass.addClassCleanup(stack.close)
        original(klass)

    cls.setUpClass = classmethod(set_up_class)
    return cls
