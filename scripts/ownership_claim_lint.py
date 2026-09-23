"""Count the reason assignments that are not inside a declared claim.

``SOL-DESIGN-ownership-contract.md`` section 5.1 names the static figure that
must reach zero at S4: ``self.last_reason =`` assignment *sites* that are not
lexically enclosed by a claim marker, counted per owner family.  This is the
lint that computes it.  **It reports; it does not fail the build.**  Nothing
is enforced before S2, and the number is expected to start near its maximum.

    python scripts/ownership_claim_lint.py
    python scripts/ownership_claim_lint.py --json
    python scripts/ownership_claim_lint.py --path some/module.py

What counts as a site
---------------------
An ``Assign`` (or ``AnnAssign``) whose target is ``self.last_reason``.  One
statement is one site, whatever it assigns; augmented and tuple assignments to
the same attribute would count too, and there are none today.

What counts as covered
----------------------
Design 5.1 gives the marker two spellings, and the lint looks for both
*lexically* -- it reads the file, it does not import it:

* the site is inside a ``with self.claim(...):`` block, at any depth;
* the site is inside a function decorated ``@claims(...)``, at any depth,
  including a nested function defined inside that one.

Which family an uncovered site belongs to
-----------------------------------------
From the reason it assigns, through ``town_arbiter.reason_owner_family`` --
the same map the arbiter, the S0 classifier and the claim register use, so the
lint cannot invent a family:

``"shop:approach"``          the literal's family.
``f"town:blocked:{x}"``      the family of the leading literal segment; an
                             f-string that does not start with a literal is
                             ``unknown``.
``a if c else b``            the common family of the literals it can see,
                             otherwise ``mixed``.
``variable``, a call, ...    ``unknown`` -- the reason is not visible here.

``mixed`` and ``unknown`` are lint categories, never claim owners: a site
that lands in one still has to be migrated, and the migration decides its
owner.  A *covered* site is counted under the owner its marker declares.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hengbot.town_arbiter import reason_owner_family  # noqa: E402


REASON_ATTRIBUTE = "last_reason"
CLAIM_DECORATOR = "claims"
CLAIM_CONTEXT_MANAGER = "claim"
FAMILY_MIXED = "mixed"
FAMILY_UNKNOWN = "unknown"
DEFAULT_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "hengbot"


def _decorator_owner(node: ast.AST) -> str | None:
    """The owner a ``@claims(owner)`` decorator declares, read lexically."""
    for decorator in getattr(node, "decorator_list", ()):
        if not isinstance(decorator, ast.Call):
            continue
        name = decorator.func
        called = (
            name.id if isinstance(name, ast.Name)
            else name.attr if isinstance(name, ast.Attribute)
            else None
        )
        if called != CLAIM_DECORATOR or not decorator.args:
            continue
        return _owner_literal(decorator.args[0])
    return None


def _owner_literal(node: ast.AST) -> str:
    """``ClaimOwner.STORE_ROUTER`` or ``"store-router"`` as a family name."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Attribute):
        return node.attr.lower().replace("_", "-")
    return FAMILY_UNKNOWN


def _claim_scope_owner(node: ast.With) -> str | None:
    """The owner of a ``with self.claim(owner, goal):`` block."""
    for item in node.items:
        call = item.context_expr
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr == CLAIM_CONTEXT_MANAGER:
            return _owner_literal(call.args[0]) if call.args else FAMILY_UNKNOWN
    return None


def _string_families(node: ast.AST) -> set[str]:
    """Every family the assigned expression can be seen to produce."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {reason_owner_family(node.value)}
    if isinstance(node, ast.JoinedStr):
        head = node.values[0] if node.values else None
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            return {reason_owner_family(head.value)}
        return set()
    if isinstance(node, ast.IfExp):
        return _string_families(node.body) | _string_families(node.orelse)
    if isinstance(node, ast.BoolOp):
        found = set()
        for value in node.values:
            found |= _string_families(value)
        return found
    return set()


def _assigned_family(node: ast.AST) -> str:
    families = _string_families(node)
    if not families:
        return FAMILY_UNKNOWN
    if len(families) == 1:
        return families.pop()
    return FAMILY_MIXED


def _is_reason_target(target: ast.AST) -> bool:
    return (
        isinstance(target, ast.Attribute)
        and target.attr == REASON_ATTRIBUTE
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    )


class _SiteCollector(ast.NodeVisitor):
    """Collect every reason-assignment site with its lexical claim cover."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.sites: list[dict] = []
        self._cover: list[str] = []

    # -- lexical enclosure ------------------------------------------------

    def visit_FunctionDef(self, node):
        owner = _decorator_owner(node)
        if owner is not None:
            self._cover.append(owner)
            self.generic_visit(node)
            self._cover.pop()
        else:
            self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_With(self, node):
        owner = _claim_scope_owner(node)
        if owner is not None:
            self._cover.append(owner)
            self.generic_visit(node)
            self._cover.pop()
        else:
            self.generic_visit(node)

    visit_AsyncWith = visit_With

    # -- the sites --------------------------------------------------------

    def _record(self, node, value) -> None:
        covered = bool(self._cover)
        self.sites.append(
            {
                "file": self.path.name,
                "line": node.lineno,
                "covered": covered,
                # The innermost marker wins: it is the one that would declare.
                "family": self._cover[-1] if covered else _assigned_family(value),
            }
        )

    def visit_Assign(self, node):
        if any(_is_reason_target(target) for target in node.targets):
            self._record(node, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if _is_reason_target(node.target) and node.value is not None:
            self._record(node, node.value)
        self.generic_visit(node)

    def visit_AugAssign(self, node):
        if _is_reason_target(node.target):
            self._record(node, node.value)
        self.generic_visit(node)


def scan(paths) -> list[dict]:
    """Every site in the given modules, in file then line order."""
    sites: list[dict] = []
    for path in paths:
        collector = _SiteCollector(path)
        collector.visit(ast.parse(path.read_text(encoding="utf-8")))
        sites.extend(sorted(collector.sites, key=lambda site: site["line"]))
    return sites


def summarise(sites) -> dict:
    """The design 5.1 figure: uncovered sites, per family."""
    uncovered: dict[str, int] = {}
    covered: dict[str, int] = {}
    for site in sites:
        bucket = covered if site["covered"] else uncovered
        bucket[site["family"]] = bucket.get(site["family"], 0) + 1
    return {
        "sites": len(sites),
        "covered": sum(covered.values()),
        "uncovered": sum(uncovered.values()),
        "uncovered_by_family": dict(sorted(uncovered.items())),
        "covered_by_family": dict(sorted(covered.items())),
    }


def render(summary: dict, *, scanned: int) -> str:
    lines = [
        f"ownership claim lint: {scanned} module(s)",
        f"  self.last_reason sites     {summary['sites']}",
        f"  inside a declared claim    {summary['covered']}",
        f"  NOT inside one (design 5.1){summary['uncovered']:>6}",
        "",
        "uncovered, per owner family:",
    ]
    for family, count in summary["uncovered_by_family"].items():
        lines.append(f"  {family:<18} {count:>5}")
    if summary["covered_by_family"]:
        lines.append("")
        lines.append("covered, per declared owner:")
        for family, count in summary["covered_by_family"].items():
            lines.append(f"  {family:<18} {count:>5}")
    lines.append("")
    lines.append(
        "This number must reach zero at S4.  The lint reports it; it does not "
        "fail the build."
    )
    return "\n".join(lines) + "\n"


def _paths(arguments) -> list[Path]:
    if arguments:
        chosen: list[Path] = []
        for raw in arguments:
            path = Path(raw)
            chosen.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
        return chosen
    return sorted(DEFAULT_PACKAGE.glob("*.py"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path", action="append", default=[],
        help="a module or directory to scan instead of src/hengbot",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--sites", action="store_true", help="list every site")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    paths = _paths(args.path)
    sites = scan(paths)
    summary = summarise(sites)
    if args.json:
        payload = {"modules": [path.name for path in paths], **summary}
        if args.sites:
            payload["site_list"] = sites
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    else:
        text = render(summary, scanned=len(paths))
        if args.sites:
            text += "".join(
                f"  {site['file']}:{site['line']} "
                f"{'claimed' if site['covered'] else 'unclaimed'} "
                f"{site['family']}\n"
                for site in sites
            )
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
