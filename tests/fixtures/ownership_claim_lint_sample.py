"""A hand-written module the claim lint is checked against (pin S1-4).

It is never imported or executed: ``scripts/ownership_claim_lint.py`` parses
it.  Every site below is annotated with what the lint must say about it, and
``tests/test_ownership_claims.py`` asserts exactly that list, line by line, so
a marker the lint stops recognising -- or starts recognising where it should
not -- fails rather than quietly changing the number.
"""

from hengbot.claim_register import ClaimOwner, claims


class Sample:
    def plain_producer(self):
        # uncovered, family from the literal -> store-router
        self.last_reason = "shop:approach"
        return "6"

    def composed_producer(self, detail):
        # uncovered, family from the leading literal of the f-string
        self.last_reason = f"town:blocked:{detail}"
        return ""

    def branching_producer(self, flag):
        # uncovered, two literals in two families -> mixed
        self.last_reason = "shop:approach" if flag else "calibration:start"
        return "5"

    def opaque_producer(self, computed):
        # uncovered, the reason is not visible here -> unknown
        self.last_reason = computed
        return "5"

    @claims(ClaimOwner.DEPARTURE)
    def decorated_producer(self):
        # covered by the decorator, under the owner it declares
        self.last_reason = "stair:descend"
        return ">"

    @claims(ClaimOwner.DEPARTURE)
    def decorated_with_nested(self):
        def inner():
            # covered: a nested function is lexically inside the decorator
            self.last_reason = "recall:read"
            return "r"

        return inner()

    def scoped_producer(self, goal):
        with self.claim(ClaimOwner.SURVIVAL, goal):
            # covered by the context manager
            self.last_reason = "survival:flee"
            return "4"

    def scope_that_ended(self, goal):
        with self.claim(ClaimOwner.SURVIVAL, goal):
            pass
        # uncovered: the block closed before this statement
        self.last_reason = "eat"
        return "E"

    def unrelated_with(self, lock):
        with lock:
            # uncovered: an ordinary ``with`` is not a claim marker
            self.last_reason = "home:deposit"
            return "d"

    def not_the_attribute(self, other):
        # not a site at all: the attribute belongs to another object
        other.last_reason = "shop:approach"
        self.last_reason_note = "shop:approach"
        return "5"
