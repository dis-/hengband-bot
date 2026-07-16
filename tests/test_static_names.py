"""Static undefined-global scanner.

The b9c8f88 incident: an enumeration branch referenced a constant that was
never defined; every test passed because no fixture reached that branch, and
the bot crashed live days later at 13F. This test kills the whole class
without external tools: for every function defined in the hengbot package,
every name its bytecode loads via LOAD_GLOBAL must resolve in the function's
OWN runtime namespace (``func.__globals__`` — the exact dict LOAD_GLOBAL
consults) or in builtins. Attribute loads use LOAD_ATTR and are naturally
excluded, so there are no case heuristics and no false positives on
``module.attr`` access.
"""

from __future__ import annotations

import builtins
import dis
import importlib
import pkgutil
import types
import unittest

import hengbot

_BUILTIN_NAMES = set(vars(builtins))


def _iter_code_objects(code):
    yield code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from _iter_code_objects(const)


def _iter_functions(module):
    for value in vars(module).values():
        if isinstance(value, types.FunctionType):
            if value.__module__ and value.__module__.startswith("hengbot"):
                yield value
        elif isinstance(value, type):
            if not (value.__module__ or "").startswith("hengbot"):
                continue  # imported stdlib classes (Path, deque, ...) are not ours
            for attr in vars(value).values():
                inner = getattr(attr, "__func__", attr)
                if isinstance(inner, property):
                    inner = inner.fget
                if isinstance(inner, types.FunctionType):
                    yield inner


class StaticNameResolutionTest(unittest.TestCase):
    def test_every_referenced_global_resolves(self):
        problems = []
        seen: set[types.CodeType] = set()
        for module_info in pkgutil.iter_modules(hengbot.__path__):
            module = importlib.import_module(f"hengbot.{module_info.name}")
            for func in _iter_functions(module):
                if func.__code__ in seen:
                    continue
                seen.add(func.__code__)
                namespace = func.__globals__
                for code in _iter_code_objects(func.__code__):
                    for instruction in dis.get_instructions(code):
                        if instruction.opname != "LOAD_GLOBAL":
                            continue
                        name = instruction.argval
                        if name.startswith("__"):
                            continue
                        if name in namespace or name in _BUILTIN_NAMES:
                            continue
                        problems.append(
                            f"{func.__module__}.{func.__qualname__}"
                            f" references undefined '{name}'"
                        )
        self.assertEqual(problems, [], "\n".join(sorted(set(problems))))


if __name__ == "__main__":
    unittest.main()
