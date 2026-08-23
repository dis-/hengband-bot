#!/usr/bin/env python3
"""Generate producer, consumer, and decision-reason maps from policy modules."""

from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_ROOT = ROOT / "src" / "hengbot"


class OwnerMapVisitor(ast.NodeVisitor):
    """Collect facts and reasons without importing the module being inspected."""

    def __init__(self) -> None:
        self.functions: list[str] = []
        self.reasons: list[dict[str, Any]] = []
        self.facts: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
            lambda: {"writes": [], "reads": []}
        )

    @property
    def function(self) -> str:
        return self.functions[-1] if self.functions else "<module>"

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _site(self, node: ast.AST, **extra: Any) -> dict[str, Any]:
        return {"function": self.function, "line": node.lineno, **extra}

    @staticmethod
    def _self_fact(node: ast.AST) -> str | None:
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and node.attr.startswith("_")
        ):
            return node.attr
        return None

    @staticmethod
    def _value_description(node: ast.AST) -> dict[str, Any]:
        try:
            literal = ast.literal_eval(node)
        except (ValueError, TypeError):
            pass
        else:
            return {"value": ast.unparse(node), "truthiness": bool(literal)}
        return {"value": ast.unparse(node), "truthiness": "dynamic"}

    def _record_target(self, target: ast.AST, value: ast.AST) -> None:
        fact = self._self_fact(target)
        if fact is not None:
            self.facts[fact]["writes"].append(
                self._site(target, **self._value_description(value))
            )

    def _record_reason(self, target: ast.AST, value: ast.AST) -> None:
        if not (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and target.attr == "last_reason"
        ):
            return
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            reason = value.value
            skeleton = None
        elif isinstance(value, ast.JoinedStr):
            reason = "<dynamic>"
            skeleton = ast.unparse(value)
            if skeleton.startswith("f"):
                skeleton = skeleton[1:]
        else:
            reason = "<dynamic>"
            skeleton = ast.unparse(value)
        self.reasons.append(self._site(target, reason=reason, skeleton=skeleton))

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._record_target(target, node.value)
            self._record_reason(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._record_target(node.target, node.value)
            self._record_reason(node.target, node.value)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        fact = self._self_fact(node.target)
        if fact is not None:
            self.facts[fact]["reads"].append(self._site(node.target))
            self.facts[fact]["writes"].append(
                self._site(node.target, value=ast.unparse(node), truthiness="dynamic")
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        fact = self._self_fact(node)
        if fact is not None and isinstance(node.ctx, ast.Load):
            self.facts[fact]["reads"].append(self._site(node))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = node.func.id if isinstance(node.func, ast.Name) else None
        if call_name in {"getattr", "setattr"} and len(node.args) >= 2:
            receiver, name_node = node.args[:2]
            if isinstance(receiver, ast.Name) and receiver.id == "self":
                if isinstance(name_node, ast.Constant) and isinstance(name_node.value, str):
                    fact = name_node.value if name_node.value.startswith("_") else None
                else:
                    fact = "<dynamic>"
                if fact is not None:
                    if call_name == "getattr":
                        self.facts[fact]["reads"].append(self._site(node))
                    else:
                        value = node.args[2] if len(node.args) >= 3 else node
                        self.facts[fact]["writes"].append(
                            self._site(node, **self._value_description(value))
                        )
        self.generic_visit(node)


def _module_paths(source: Path) -> list[Path]:
    return sorted(source.glob("*.py")) if source.is_dir() else [source]


def build_report(policy_path: Path = DEFAULT_POLICY_ROOT) -> dict[str, Any]:
    visitor = OwnerMapVisitor()
    paths = _module_paths(policy_path)
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor.visit(tree)

    facts: dict[str, Any] = {}
    starvation: list[dict[str, Any]] = []
    for name in sorted(visitor.facts):
        accesses = visitor.facts[name]
        writes = sorted(accesses["writes"], key=lambda site: (site["line"], site["function"]))
        reads = sorted(accesses["reads"], key=lambda site: (site["line"], site["function"]))
        writer_functions = sorted({site["function"] for site in writes})
        producer_functions = sorted(
            {site["function"] for site in writes if site["truthiness"] is not False}
        )
        consumer_functions = sorted({site["function"] for site in reads})
        facts[name] = {
            "producer_functions": producer_functions,
            "writer_functions": writer_functions,
            "consumer_functions": consumer_functions,
            "writes": writes,
            "reads": reads,
        }
        if len(producer_functions) == 1 and len(consumer_functions) >= 3:
            starvation.append(
                {
                    "fact": name,
                    "producer": producer_functions[0],
                    "consumer_count": len(consumer_functions),
                    "consumers": consumer_functions,
                }
            )
    starvation.sort(key=lambda item: (-item["consumer_count"], item["fact"]))
    reasons = sorted(visitor.reasons, key=lambda site: (site["line"], site["function"]))
    return {"policy": str(policy_path), "modules": [str(path) for path in paths], "reasons": reasons, "facts": facts, "starvation_prone": starvation}


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Decision-owner map", "", f"Policy: `{report['policy']}`", "", "## Reasons", "", "| Reason | Function | Line |", "| --- | --- | ---: |"]
    for site in report["reasons"]:
        reason = site["reason"]
        if site["skeleton"] is not None:
            reason = f"{reason} `{site['skeleton']}`"
        lines.append(f"| {reason.replace('|', '&#124;')} | `{site['function']}` | {site['line']} |")
    lines += ["", "## Facts", ""]
    for fact, entry in report["facts"].items():
        lines += [f"### `{fact}`", "", "| Access | Function | Line |", "| --- | --- | ---: |"]
        for kind, sites in (("WRITE", entry["writes"]), ("READ", entry["reads"])):
            for site in sites:
                lines.append(f"| {kind} | `{site['function']}` | {site['line']} |")
        lines.append("")
    lines += ["## Starvation-prone facts", "", "| Fact | Producer | Consumer functions |", "| --- | --- | ---: |"]
    for item in report["starvation_prone"]:
        lines.append(f"| `{item['fact']}` | `{item['producer']}` | {item['consumer_count']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--json", type=Path, metavar="PATH")
    parser.add_argument("--markdown", type=Path, metavar="PATH")
    args = parser.parse_args()
    report = build_report(args.policy.resolve())
    if args.json:
        args.json.write_text(render_json(report), encoding="utf-8", newline="\n")
    if args.markdown:
        args.markdown.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    if not args.json and not args.markdown:
        print(f"reasons: {len(report['reasons'])}")
        print(f"facts: {len(report['facts'])}")
        print(f"starvation-prone: {len(report['starvation_prone'])}")


if __name__ == "__main__":
    main()
