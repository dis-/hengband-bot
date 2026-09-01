"""AST census for every production ``StoreVisit`` constructor."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path


EXPECTED_ORIGINS = Counter({
    "acquire": 1,
    "store-router": 2,
    "home-one-shot": 1,
    "recovered-store-context": 1,
    "equipment-transaction-recovery": 1,
    "shop-handler-recovery": 1,
    "home-operation-staging": 1,
})


def production_constructor_sites(source_root: Path) -> dict[str, str]:
    sites = {}
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if name != "StoreVisit":
                continue
            values = {keyword.arg: keyword.value for keyword in node.keywords}
            origin = values.get("visit_origin")
            if not isinstance(origin, ast.Constant) or not isinstance(origin.value, str):
                raise AssertionError(f"{path}:{node.lineno} lacks exact visit_origin")
            relative = path.relative_to(source_root.parent).as_posix()
            sites[f"{relative}:{node.lineno}"] = origin.value
    return dict(sorted(sites.items()))
