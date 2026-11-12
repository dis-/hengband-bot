"""Structural equality of two object graphs, sharing included (tests of hengbot.json_snapshot).

Two graphs are equal when every object has the type, the value and the reduction (what pickle
would record) of its counterpart, and the objects shared in one are shared alike in the other:
the walk keeps an id bijection.  ``graph_equal`` returns None, or the path of the first
difference.  Tuples and frozensets of atoms are compared as values, as json_snapshot writes them.
"""
from __future__ import annotations

import copyreg
import math

ATOMS = (str, int, bool, type(None))
_ATOM_TYPES = frozenset(ATOMS)
_ROUTINES = frozenset({type(len), type(lambda: None)})


def _reduction(obj):
    reducer = copyreg.dispatch_table.get(type(obj))
    reduction = reducer(obj) if reducer else obj.__reduce_ex__(5)
    function, args, state, items, pairs = tuple(reduction) + (None,) * (5 - len(reduction))
    return (function, args, state, None if items is None else list(items),
            None if pairs is None else list(pairs))


def graph_equal(first, second) -> str | None:
    forward, backward, keep = {}, {}, []
    stack = [(first, second, "root")]
    while stack:
        a, b, path = stack.pop()
        if type(a) is not type(b):
            return f"{path}: type {type(a).__name__} != {type(b).__name__}"
        kind = type(a)
        if kind in _ATOM_TYPES:
            if a != b:
                return f"{path}: {a!r} != {b!r}"
            continue
        if kind is float:
            if not (a == b or (math.isnan(a) and math.isnan(b))):
                return f"{path}: {a!r} != {b!r}"
            continue
        if isinstance(a, type) or kind in _ROUTINES:
            if a is not b:
                return f"{path}: {a!r} is not {b!r}"
            continue
        if kind in (tuple, frozenset) and _ATOM_TYPES.issuperset(map(type, a)):
            if a != b:
                return f"{path}: {a!r} != {b!r}"
            continue
        if id(a) in forward or id(b) in backward:
            if forward.get(id(a)) != id(b):
                return f"{path}: shared differently"
            continue
        forward[id(a)], backward[id(b)] = id(b), id(a)
        keep.append((a, b))
        if kind is dict:
            if len(a) != len(b):
                return f"{path}: {len(a)} items != {len(b)}"
            for (key_a, value_a), (key_b, value_b) in zip(a.items(), b.items()):
                stack.append((key_a, key_b, f"{path}.<key>"))
                stack.append((value_a, value_b, f"{path}[{key_a!r}]"[:240]))
        elif kind in (list, tuple):
            if len(a) != len(b):
                return f"{path}: length {len(a)} != {len(b)}"
            stack.extend((x, y, f"{path}[{index}]") for index, (x, y) in enumerate(zip(a, b)))
        elif kind in (set, frozenset):
            if a != b:
                return f"{path}: sets differ"
        elif kind is bytes:
            if a != b:
                return f"{path}: bytes differ"
        else:
            parts_a, parts_b = _reduction(a), _reduction(b)
            keep.append((parts_a, parts_b))
            if parts_a[0] != parts_b[0]:
                return f"{path}: reduced by {parts_a[0]!r}, not {parts_b[0]!r}"
            for index, name in ((1, "args"), (2, "state"), (3, "items"), (4, "pairs")):
                stack.append((parts_a[index], parts_b[index], f"{path}.<{name}>"))
    return None
