#!/usr/bin/env python3
"""Reject store-sale commands selected by mutable inventory letters."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "src" / "hengbot"


def _contains(node: ast.AST, predicate) -> bool:
    return any(predicate(child) for child in ast.walk(node))


def analyze_source(source: str) -> list[str]:
    tree = ast.parse(source)
    findings: list[str] = []
    for function in (
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and "sell" in node.name
    ):
        sale_compositions = [
            node for node in ast.walk(function)
            if isinstance(node, ast.BinOp)
            and _contains(node, lambda child: isinstance(child, ast.Name) and child.id == "SELL_KEY")
        ]
        for composition in sale_compositions:
            if _contains(
                composition,
                lambda child: isinstance(child, ast.Attribute) and child.attr == "slot",
            ):
                findings.append(
                    f"line {composition.lineno}: {function.name} composes a sale key from an item letter"
                )
        if sale_compositions:
            observes_tag = _contains(
                function,
                lambda child: isinstance(child, ast.Constant)
                and child.value == "await-inscription",
            ) and _contains(
                function,
                lambda child: isinstance(child, ast.Attribute)
                and child.attr == "inscription",
            )
            if not observes_tag:
                findings.append(
                    f"line {function.lineno}: {function.name} composes a sale key without an inscription-observation gate"
                )
    return findings


def main() -> int:
    findings = [
        f"{path.name}: {finding}"
        for path in sorted(POLICY_ROOT.glob("*.py"))
        for finding in analyze_source(path.read_text(encoding="utf-8"))
    ]
    for finding in findings:
        print(f"sale-key-lint: {finding}")
    print(f"sale-key-lint: {len(findings)} violation(s)")
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
