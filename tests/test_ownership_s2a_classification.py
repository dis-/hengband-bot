"""Stage S2a: every producer's owner is known, and nothing else moved.

``SOL-DESIGN-ownership-contract.md`` section 6 stage **S2a** is classification
only.  Its whole job is that the ownership of every producer is *known*, so
that the implicit-handoff metric of section 5.2 measures real handoffs instead
of traffic between a real family and a catch-all.  Nothing is enforced here:
there is no violation class, no priority ladder and no bar table, and no key
or reason changes.

How it is done, and why it cannot move a decision
-------------------------------------------------
``TownOwnerRegistration`` now answers two separate questions with two separate
prefix tuples:

* ``reason_prefixes`` -- **arbitration**.  ``owner_for_reason`` reads only
  these, and they decide which budget bucket a town decision spends, which
  owner can retire, and therefore when ``town:blocked:owner-retired`` is
  emitted.  S2a changes none of them, and the ten families it adds carry an
  *empty* tuple here, so they can never be an answer of ``owner_for_reason``.
* ``census_prefixes`` -- **the ownership census**.  ``ownership_family`` reads
  these, and the claim ledger, ``stop_shape.producer_identity`` and the
  ownership lint read that.

That is why behaviour neutrality is structural rather than hoped for: the
arbiter's own answer is computed from a tuple this round did not touch.

The pins
--------
A1  the two recorded replays produce byte-identical keys and reasons -- pinned
    as a digest of the whole trajectory -- and the arbitration table is pinned
    so a prefix cannot quietly move out of it.
A2  every uncovered reason site is inside a function listed in
    ``scripts/ownership_claim_exceptions.txt`` with a one-line reason, and no
    line of that file is stale.
A3  no producer declares ``UNREGISTERED`` (or ``MISC``) any more, and no reason
    literal in the package lands in a catch-all family.
A4  the implicit-handoff metric over the named replay
    ``tests/fixtures/loot-choke-oscillation-20260923.jsonl.gz``, before and
    after, with the before values produced by reverting S2a's single runtime
    hook.  **Revert-proof**: ``test_a4_reverting_the_census_restores_the_s1
    _numbers`` undoes ``ownership_family`` and asserts the S1 numbers come
    back, so a silent revert of the census fails here.
A5  the S0 stop-shape classifier and the claim ledger agree on the family of
    every reason in the recorded fixtures -- one source of families.

The measured result, recorded here because it is the round's finding
--------------------------------------------------------------------
On this replay the by-owner count does **not** fall: 3 before, 3 after.  On
the live S1 session ledger of 2026-09-24 (2,591 claim rows, 2 h 17 min) it
falls only from 138 to 137 by owner and from 144 to 137 by producer, while the
rows owned by a catch-all fall from 137 to 0.  The catch-all traffic was not
spurious: ``fundraise:seek-loot`` giving way to ``ranged:fire-target`` and back
is two real owners, and naming them ``fundraising`` and ``combat`` does not
make it one.  The number the S2b gate reads is dominated by something else --
a claim with a ``Terminal`` goal has no closure path at all in S1
(``ClaimRegister.release`` and ``.suspend`` have no caller, and ``complete``
fires only when a ``Reach`` cell is reached), so 1,808 of those 2,591 claims
could never end explicitly.  That is recorded in the report, not fixed here.

Stage S2a.1 fixed it (``tests/test_ownership_s2a1_closure.py``): all three
owner changes of this replay are now closed, so A4 pins the three changes as
raw owner changes and the implicit count as 0 (before and after the census).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare runs

import ast
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from hengbot.claim_register import ClaimOwner
from hengbot.ownership_metrics import (
    OWNERSHIP_CLAIMS_NAME,
    implicit_handoffs,
    read_records,
)
from hengbot.stop_shape import CATCH_ALL_FAMILIES, producer_identity
from hengbot.town_arbiter import (
    TownTurnArbiter,
    UNREGISTERED_FAMILY,
    _new_town_turn_arbiter,
    owner_families,
    owner_family_budgets,
    reason_arbitration_family,
    reason_owner_family,
)

import ownership_claim_lint

from test_ownership_claims import _Replay, _owner_changes, _rows, _volatile_free


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "hengbot"
EXCEPTIONS = ROOT / "scripts" / "ownership_claim_exceptions.txt"

# The twenty families that arbitrate a town decision, in registration order.
# Their prefixes are the ones the arbiter had before S2a; the digest below is
# over ``[(name, list(reason_prefixes)), ...]`` of exactly these, so moving a
# single prefix into or out of arbitration fails this pin.  Regenerate with:
#   python -c "import json,hashlib;from hengbot.town_arbiter import *;
#     e=_new_town_turn_arbiter().registry.values();
#     print(hashlib.sha256(json.dumps([[x.name,list(x.reason_prefixes)]
#       for x in e if x.reason_prefixes]).encode()).hexdigest())"
ARBITRATING_FAMILIES = (
    "home-errand", "home-scan", "home-visit", "shop-sell", "shop-buy",
    "store-router", "equipment-opt", "equipment-txn", "calibration",
    "identification", "fundraising", "curse-enchant", "cross-town",
    "survival", "departure", "town-plan", "rumor", "quest-request",
    "detectors", "misc",
)
# Measured on the pre-S2a tree (HEAD f7e80d2) and again after this round;
# the two agree, which is the evidence that arbitration did not move.
ARBITRATION_TABLE_SHA256 = (
    "48465520040f2f8ec138fee10e0a1259693bf1c9481cb28bcf5cad01bd30f07d"
)

# The ten families S2a adds, each named after what it owns.  They are
# census-only: no arbitration prefix, no budget of its own.
CENSUS_ONLY_FAMILIES = (
    "positioning", "esp-threat", "escape", "combat", "hunt", "explore",
    "floor-loot", "quest-sweep", "bookkeeping", "idle",
)

# A1.  sha256 over ``json.dumps([[key, reason], ...])`` of the whole replay,
# measured on the pre-S2a tree (HEAD f7e80d2) and again after this round.
DUNGEON_TRAJECTORY_SHA256 = (
    "fa99ad53803ab1d97291cb6915685595cac980bd0cc50fa4900458c0a689ecb6"
)
TOWN_TRAJECTORY_SHA256 = (
    "76be970a2fdf2898fd8f00e5925d81b41243f67d7659823b636c223fc2503f2a"
)

# A4, on tests/fixtures/loot-choke-oscillation-20260923.jsonl.gz.
BEFORE_OWNERS = (
    ["misc"] * 2 + ["unregistered"] * 3 + ["misc"] + ["unregistered"] * 18
)
BEFORE_PAIRS = {"misc>unregistered": 2, "unregistered>misc": 1}
BEFORE_CATCH_ALL_ROWS = 24
AFTER_OWNERS = (
    ["explore"] * 2 + ["positioning"] * 3 + ["combat"] + ["positioning"] * 18
)
AFTER_PAIRS = {
    "explore>positioning": 1,
    "positioning>combat": 1,
    "combat>positioning": 1,
}
AFTER_CATCH_ALL_ROWS = 0
# The three owner changes of the window, closed or not.  S2a measured all
# three as implicit; S2a.1 (design rev 9.1 item 3) closes each of them -- the
# explore goal completes, the positioning retreat is released, melee is a
# Terminal claim closed on posting -- so the implicit count is now 0, under
# either census.  The pairs are pinned as raw owner changes instead.
OWNER_CHANGES = 3
IMPLICIT_HANDOFFS = 0


def _trajectory_digest(trajectory) -> str:
    blob = json.dumps(
        [[str(key) if key is not None else None, reason]
         for key, reason in trajectory],
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _reason_literals() -> set[str]:
    """Every string a ``self.last_reason =`` site can be seen to assign."""

    def strings(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
        elif isinstance(node, ast.JoinedStr):
            head = node.values[0] if node.values else None
            if isinstance(head, ast.Constant) and isinstance(head.value, str):
                yield head.value
        elif isinstance(node, ast.IfExp):
            yield from strings(node.body)
            yield from strings(node.orelse)
        elif isinstance(node, ast.BoolOp):
            for value in node.values:
                yield from strings(value)

    found: set[str] = set()
    for path in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            else:
                continue
            if any(ownership_claim_lint._is_reason_target(target)
                   for target in targets):
                found |= set(strings(value))
    return found


def _replay_claims(boards, *, census: bool = True):
    """Run a recorded replay and return its claim ledger rows."""
    skill, raw = boards
    root = Path(tempfile.mkdtemp(prefix="s2a-"))
    trajectory, log = _Replay.run(root, skill, raw, register=True, ledger=True)
    return trajectory, _rows(log), read_records(root / OWNERSHIP_CLAIMS_NAME)


class CensusSeparationTest(unittest.TestCase):
    """A1: arbitration is a different tuple, and S2a did not touch it."""

    def test_the_arbitration_table_is_the_one_that_existed_before_s2a(self):
        entries = list(_new_town_turn_arbiter().registry.values())
        arbitrating = [entry for entry in entries if entry.reason_prefixes]
        self.assertEqual(
            [entry.name for entry in arbitrating], list(ARBITRATING_FAMILIES)
        )
        table = json.dumps(
            [[entry.name, list(entry.reason_prefixes)]
             for entry in arbitrating]
        )
        self.assertEqual(
            hashlib.sha256(table.encode("utf-8")).hexdigest(),
            ARBITRATION_TABLE_SHA256,
        )

    def test_a_census_only_family_can_never_arbitrate(self):
        registry = _new_town_turn_arbiter().registry
        self.assertEqual(
            [name for name, entry in registry.items()
             if not entry.reason_prefixes],
            list(CENSUS_ONLY_FAMILIES),
        )
        for name in CENSUS_ONLY_FAMILIES:
            with self.subTest(family=name):
                entry = registry[name]
                self.assertEqual(entry.reason_prefixes, ())
                self.assertTrue(entry.census_prefixes)
                # No budget is invented for a family nothing arbitrates.
                self.assertIsNone(entry.budget)
                self.assertNotIn(name, owner_family_budgets())
        # and no reason, whatever it is, can make the arbiter answer one
        for reason in sorted(_reason_literals()):
            with self.subTest(reason=reason):
                self.assertNotIn(
                    reason_arbitration_family(reason), CENSUS_ONLY_FAMILIES
                )

    def test_the_census_refines_arbitration_and_never_contradicts_it(self):
        for entry in _new_town_turn_arbiter().registry.values():
            with self.subTest(family=entry.name):
                self.assertEqual(
                    entry.census_prefixes[:len(entry.reason_prefixes)],
                    entry.reason_prefixes,
                )
        for reason in sorted(_reason_literals()):
            arbitration = reason_arbitration_family(reason)
            census = reason_owner_family(reason)
            with self.subTest(reason=reason):
                if arbitration not in CATCH_ALL_FAMILIES:
                    # A reason an arbitrating family already owned keeps it.
                    self.assertEqual(census, arbitration)

    def test_the_named_replays_decide_byte_identically(self):
        for name, boards, digest in (
            ("dungeon", _Replay.dungeon_boards(), DUNGEON_TRAJECTORY_SHA256),
            ("town", _Replay.town_boards(), TOWN_TRAJECTORY_SHA256),
        ):
            with self.subTest(replay=name):
                trajectory, rows, _claims = _replay_claims(boards)
                self.assertEqual(_trajectory_digest(trajectory), digest)
                # the row itself is unchanged too, bar the claim block
                self.assertTrue(rows)
                for row in rows:
                    self.assertIn("claim", row)
                    self.assertNotIn("claim", _volatile_free(row))


class ExceptionsFileTest(unittest.TestCase):
    """A2: every uncovered producer is excused by a checked-in line."""

    @classmethod
    def setUpClass(cls):
        cls.excused = ownership_claim_lint.read_exceptions(EXCEPTIONS)
        cls.sites = ownership_claim_lint.scan(sorted(PACKAGE.glob("*.py")))
        cls.summary = ownership_claim_lint.summarise(cls.sites, cls.excused)

    def test_no_uncovered_site_is_unexcused(self):
        self.assertEqual(
            self.summary["unexcused"],
            0,
            [f"{site['file']}:{site['host']}:{site['line']}"
             for site in self.summary["unexcused_sites"][:20]],
        )
        self.assertEqual(
            self.summary["covered"] + self.summary["uncovered"],
            self.summary["sites"],
        )
        self.assertEqual(self.summary["excused"], self.summary["uncovered"])

    def test_no_exception_line_is_stale(self):
        self.assertEqual(self.summary["stale_exceptions"], [])

    def test_every_exception_carries_a_reason(self):
        self.assertTrue(self.excused)
        for entry, reason in sorted(self.excused.items()):
            with self.subTest(entry=entry):
                self.assertIn(".py:", entry)
                self.assertTrue(reason, "an exception needs a reason")

    def test_the_lint_still_reports_rather_than_failing(self):
        with tempfile.TemporaryDirectory(prefix="s2a-lint-") as raw:
            output = Path(raw) / "lint.json"
            self.assertEqual(
                ownership_claim_lint.main(["--json", "--output", str(output)]),
                0,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["unexcused"], 0)
            self.assertEqual(payload["stale_exceptions"], [])


class NoCatchAllOwnerTest(unittest.TestCase):
    """A3: nothing declares, or falls into, a catch-all any more."""

    def test_no_producer_declares_unregistered_or_misc(self):
        declared = []
        for path in sorted(PACKAGE.glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    continue
                owner = ownership_claim_lint._decorator_owner(node)
                if owner in CATCH_ALL_FAMILIES:
                    declared.append(f"{path.name}:{node.name} -> {owner}")
        self.assertEqual(declared, [])

    def test_no_reason_literal_lands_in_a_catch_all(self):
        stranded = sorted(
            reason for reason in _reason_literals()
            if reason_owner_family(reason) in CATCH_ALL_FAMILIES
        )
        self.assertEqual(stranded, [])
        # the empty reason too: design 4 leaves no board unattributed
        self.assertEqual(reason_owner_family(""), "idle")

    def test_every_declared_owner_is_a_registered_family(self):
        families = {*owner_families(), UNREGISTERED_FAMILY}
        self.assertEqual({owner.value for owner in ClaimOwner}, families)
        summary = ownership_claim_lint.summarise(
            ownership_claim_lint.scan(sorted(PACKAGE.glob("*.py")))
        )
        for family in summary["covered_by_family"]:
            with self.subTest(family=family):
                self.assertIn(family, families)
                self.assertNotIn(family, CATCH_ALL_FAMILIES)


class ImplicitHandoffTest(unittest.TestCase):
    """A4: the metric over the named replay, before and after."""

    NAMED_REPLAY = "tests/fixtures/loot-choke-oscillation-20260923.jsonl.gz"

    def test_a4_after_the_census_the_replay_has_no_catch_all_owner(self):
        _trajectory, _rowset, claims = _replay_claims(_Replay.dungeon_boards())
        self.assertEqual([record["owner"] for record in claims], AFTER_OWNERS)
        self.assertEqual(
            sum(1 for record in claims
                if record["owner"] in CATCH_ALL_FAMILIES),
            AFTER_CATCH_ALL_ROWS,
        )
        self.assertEqual(_owner_changes(claims), AFTER_PAIRS)
        self.assertEqual(_owner_changes(claims, by="producer"), AFTER_PAIRS)
        self.assertEqual(sum(AFTER_PAIRS.values()), OWNER_CHANGES)
        by_owner = implicit_handoffs(claims)
        self.assertEqual(by_owner["implicit_handoffs"], IMPLICIT_HANDOFFS)
        self.assertEqual(by_owner["pairs"], {})
        self.assertEqual(
            implicit_handoffs(claims, by="producer")["pairs"], {}
        )

    def test_a4_reverting_the_census_restores_the_s1_numbers(self):
        """Revert-proof: undo the one hook S2a added and the old numbers come back.

        ``ownership_family`` is the whole runtime surface of this round --
        ``policy._record_decision_claim`` asks the arbiter for it, and
        ``town_arbiter.reason_owner_family`` (hence
        ``stop_shape.producer_identity``) asks a throwaway arbiter for it.
        Replacing it with the pre-S2a answer must reproduce the S1 ledger
        exactly, or this test is not measuring what it claims to.
        """
        original = TownTurnArbiter.ownership_family
        TownTurnArbiter.ownership_family = TownTurnArbiter.owner_for_reason
        try:
            _trajectory, _rowset, claims = _replay_claims(
                _Replay.dungeon_boards()
            )
        finally:
            TownTurnArbiter.ownership_family = original
        self.assertEqual([record["owner"] for record in claims], BEFORE_OWNERS)
        self.assertEqual(
            sum(1 for record in claims
                if record["owner"] in CATCH_ALL_FAMILIES),
            BEFORE_CATCH_ALL_ROWS,
        )
        self.assertEqual(_owner_changes(claims), BEFORE_PAIRS)
        self.assertEqual(sum(BEFORE_PAIRS.values()), OWNER_CHANGES)
        by_owner = implicit_handoffs(claims)
        self.assertEqual(by_owner["implicit_handoffs"], IMPLICIT_HANDOFFS)
        self.assertEqual(by_owner["pairs"], {})
        # And the guard on the guard: the hook really is restored afterwards.
        self.assertIsNot(
            TownTurnArbiter.ownership_family, TownTurnArbiter.owner_for_reason
        )

    def test_a4_the_town_replay_loses_its_catch_all_owner_too(self):
        _trajectory, _rowset, claims = _replay_claims(_Replay.town_boards())
        self.assertEqual(
            sum(1 for record in claims
                if record["owner"] in CATCH_ALL_FAMILIES),
            0,
        )
        self.assertEqual({record["owner"] for record in claims},
                         {"bookkeeping"})
        self.assertEqual(implicit_handoffs(claims)["implicit_handoffs"], 0)


class OneSourceOfFamiliesTest(unittest.TestCase):
    """A5: the classifier and the ledger answer from the same table."""

    def test_the_classifier_and_the_ledger_agree_on_every_recorded_reason(self):
        for name, boards in (("dungeon", _Replay.dungeon_boards()),
                             ("town", _Replay.town_boards())):
            _trajectory, _rowset, claims = _replay_claims(boards)
            self.assertTrue(claims)
            for record in claims:
                with self.subTest(replay=name, reason=record["reason"]):
                    family = reason_owner_family(record["reason"])
                    self.assertEqual(record["owner"], family)
                    # producer_identity only refines a catch-all, and there
                    # are none left, so the two now coincide.
                    self.assertEqual(
                        producer_identity(record["reason"]), family
                    )
                    self.assertEqual(record["producer"], family)

    def test_the_catch_all_names_are_still_registered_families(self):
        for family in CATCH_ALL_FAMILIES:
            with self.subTest(family=family):
                self.assertIn(
                    family, {*owner_families(), UNREGISTERED_FAMILY}
                )


if __name__ == "__main__":
    unittest.main()
