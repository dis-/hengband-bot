"""The readers of the *Destruction* kinds outside the one fact (hengbot.destruction_means).

Whole-bot maintainability review 2026-11-16 (R1, stage 2): "is there a *Destruction* means" was
read in six places with four definitions, each looking at the staff's sval and the
``_is_destruction_*`` predicates on its own.  The means now has one fact; a module outside it
that reads ``SV_STAFF_DESTRUCTION`` or ``_is_destruction_scroll/_staff/_item`` must be on the
list below (``ALLOWED``: the sites of 2026-11-16, each with why it reads the kind and not the
means).  A new site fails: read ``destruction_means.Means`` (or extend it) instead, or add the
site here with its reason when it reads the kind itself (a shop shelf, a route table).

    python scripts/destruction_means_lint.py      # exit 1 on a site off the list
"""

from __future__ import annotations

import ast
import re
import sys
from collections import Counter
from pathlib import Path

POLICY_ROOT = Path(__file__).resolve().parents[1] / "src" / "hengbot"
FACT_MODULE = "destruction_means"
NAMES = frozenset({"SV_STAFF_DESTRUCTION"})
ATTRIBUTE = re.compile(r"^(SV_STAFF_DESTRUCTION|_is_destruction_(scroll|staff|item))$")

# (module, function) -> (count, why the site reads the kind and not the means).
ALLOWED = {
    ("bm_destruction_fund", "<lambda>"): (1, "the Black market's staff shelf row (a purchase)"),
    ("item_fate", "_protected"): (1, "a Home row's kind: the staff is never sold (the ledger's fate)"),
    ("item_use_route", "<module>"): (2, "the route and retention tables key the staff kind"),
    ("me_capability", "<module>"): (2, "the REPLACES row of the absorbed staff (the power's kind)"),
    ("me_inn_refill", "destruction_short"): (1, "the absorbed power's list row against its count "
                                                 "(the inn's refill, not whether a means is held)"),
    ("policy_home", "_retention_reservation_baseline_detail"): (1, "a Home row's kind (retention)"),
    ("policy_shop", "_black_market_optional_purchase"): (4, "Black market rows' kinds (a purchase)"),
    ("policy_shop", "held"): (1, "a Black market row's kind (a purchase's order)"),
    ("policy_shop", "_purchase_rungs"): (2, "shop rows' kinds (the purchase ladder)"),
    ("policy_shop", "_purchase_quantity"): (2, "a purchase row's kind (its quantity)"),
    ("policy_supply", "_procurement_missing_amount"): (1, "a procurement row's kind (its amount)"),
}


class _Sites(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self.module = module
        self.stack: list[str] = []
        self.found: list[tuple[str, str, int]] = []

    def _scope(self, node, name: str) -> None:
        self.stack.append(name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node) -> None:
        self._scope(node, node.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node) -> None:
        # A lambda at module or class level has no function name of its own.
        self._scope(node, self.stack[-1] if self.stack else "<lambda>")

    def _site(self, node) -> None:
        self.found.append((self.module, self.stack[-1] if self.stack else "<module>", node.lineno))

    def visit_Name(self, node) -> None:
        if node.id in NAMES and isinstance(node.ctx, ast.Load):
            self._site(node)

    def visit_Attribute(self, node) -> None:
        if ATTRIBUTE.match(node.attr) and isinstance(node.ctx, ast.Load):
            self._site(node)
        self.generic_visit(node)


def sites(root: Path = POLICY_ROOT) -> list[tuple[str, str, int]]:
    """(module, function, line) of every read outside the fact module."""
    found = []
    for path in sorted(root.glob("*.py")):
        module = path.stem
        if module == FACT_MODULE:
            continue
        visitor = _Sites(module)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        found.extend(visitor.found)
    return found


def findings(root: Path = POLICY_ROOT) -> list[str]:
    """A line per site off the list, per listed count exceeded, and per listed site gone."""
    found = sites(root)
    counted = Counter((module, function) for module, function, _line in found)
    lines = []
    for (module, function), count in sorted(counted.items()):
        allowed, _why = ALLOWED.get((module, function), (0, ""))
        if count > allowed:
            where = ", ".join(str(line) for m, f, line in found if (m, f) == (module, function))
            lines.append(f"{module}.py:{function} reads the *Destruction* kind {count}x (listed {allowed}; "
                         f"lines {where}): read destruction_means.Means instead, or list the site")
    for (module, function), (allowed, _why) in sorted(ALLOWED.items()):
        if counted.get((module, function), 0) < allowed:
            lines.append(f"{module}.py:{function} is listed for {allowed} reads but has "
                         f"{counted.get((module, function), 0)}: shrink ALLOWED")
    return lines


def main() -> int:
    lines = findings()
    for line in lines:
        print(line)
    print(f"destruction_means_lint: {len(lines)} finding(s)")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main())
