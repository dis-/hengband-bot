"""Dependency hashing and PASS cache for the town-producer purity partitions.

The verdict is produced by ``tests/town_producer_purity_matrix.py``.  Starting
at that file, this module follows Python imports mechanically through tests/
and src/hengbot/.  It also includes the six wrappers and every existing repo
file named by a string literal in the graph (the matrix's JSONL captures are
found this way).  Dynamic imports cannot be proved statically, so every
``src/hengbot/*.py`` file is included when one is encountered; this is a
deliberately conservative invalidation rule, never a false cache hit.
"""

from __future__ import annotations

import ast
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path


PURITY_MODULES = tuple(f"tests.test_town_producer_purity_part{i}" for i in range(1, 7))


def dependency_files(root: Path) -> tuple[Path, ...]:
    seeds = [root / "tests" / "town_producer_purity_matrix.py"]
    seeds += [root / (module.replace(".", "/") + ".py") for module in PURITY_MODULES]
    found = {path.resolve() for path in seeds}
    pending = list(found)
    while pending:
        path = pending.pop()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeError):
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
                names.extend(f"{node.module}.{alias.name}" for alias in node.names)
            for name in names:
                candidates = [root / "src" / (name.replace(".", "/") + ".py"),
                              root / "tests" / (name.replace(".", "/") + ".py")]
                for candidate in candidates:
                    if candidate.is_file() and candidate.resolve() not in found:
                        found.add(candidate.resolve()); pending.append(candidate.resolve())
            if (path.name == "town_producer_purity_matrix.py"
                    and isinstance(node, ast.Constant) and isinstance(node.value, str)):
                value = node.value.replace("\\", "/")
                if not value.endswith((".jsonl", ".json", ".jsonc", ".gz")):
                    continue
                for candidate in (root / value, root / "jsonlog" / value, root / "tests" / value):
                    if candidate.is_file() and candidate.resolve() not in found:
                        found.add(candidate.resolve()); pending.append(candidate.resolve())
    # Hengbot policy modules use mixins and occasional runtime imports.  Include
    # the whole local package when the graph enters it (safe over-invalidation).
    if any((root / "src" / "hengbot") in path.parents for path in found):
        found.update(path.resolve() for path in (root / "src" / "hengbot").glob("*.py"))
    # find_monrace_definitions() searches this location for both captures.
    monrace = root.parent / "lib" / "edit" / "MonraceDefinitions.jsonc"
    if monrace.is_file(): found.add(monrace.resolve())
    return tuple(sorted(found, key=lambda path: path.as_posix()))


def input_sha256(root: Path) -> tuple[str, tuple[str, ...]]:
    digest = hashlib.sha256()
    digest.update(platform.python_version().encode()); digest.update(b"\0")
    paths = dependency_files(root)
    for path in paths:
        try: label = path.relative_to(root).as_posix()
        except ValueError: label = path.as_posix()
        digest.update(label.encode()); digest.update(b"\0")
        digest.update(path.read_bytes()); digest.update(b"\0")
    labels = []
    for path in paths:
        try: labels.append(path.relative_to(root).as_posix())
        except ValueError: labels.append(path.as_posix())
    return digest.hexdigest(), tuple(labels)


def load_pass(cache: Path, digest: str) -> dict[str, object] | None:
    try:
        payload = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    row = payload.get(digest) if isinstance(payload, dict) else None
    return row if isinstance(row, dict) and row.get("result") == "PASS" else None


def record_pass(cache: Path, digest: str, head_sha: str, inputs: tuple[str, ...]) -> dict[str, object]:
    try:
        payload = json.loads(cache.read_text(encoding="utf-8"))
        if not isinstance(payload, dict): payload = {}
    except (OSError, ValueError, TypeError):
        payload = {}
    row = {"result": "PASS", "head_sha": head_sha,
           "time": datetime.now(timezone.utc).astimezone().isoformat(),
           "python": platform.python_version(), "inputs": list(inputs)}
    payload[digest] = row
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return row
