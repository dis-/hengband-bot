"""A policy checkpoint or board snapshot as gzip-compressed JSON, in place of pickle.

Maintainability review 2026-11-09, step 8: a pickle can be read only by Python, and only
while every class it names still loads, so a recorded checkpoint is opaque to everything but a
restore.  This writes the same object graph as JSON: what the pickle protocol would record
(``__reduce_ex__``: the class or callable, its arguments, the state, list and dict items), so
every class's own ``__getstate__``/``__setstate__``/``__reduce__`` keeps its meaning and a
restore builds the same objects a pickle restore did.  An object reached twice is written once
and referred to (``$id``/``$ref``), so shared and cyclic references survive as they do in a
pickle.  Immutable values made only of strings, numbers, booleans and None (tuples and
frozensets of such) are written as values each time they are met: nothing in the policy tells
two equal ones apart by identity.

The document is ``{"format": FORMAT, "version": VERSION, "state": <node>}``.  A node is a
JSON string, number, boolean or null for itself; a JSON array for a list; a JSON object for a
dict whose keys are strings not starting with ``$``; otherwise an object with one tag:

* ``$t`` tuple, ``$s`` set, ``$fs`` frozenset, ``$l`` shared list, ``$d`` shared dict,
  ``$dl`` dict as ``[key, value]`` pairs, ``$b`` bytes (base64), ``$f`` a float JSON cannot
  hold (``nan``, ``inf``), ``$g`` a class or function by ``module:qualname``;
* ``$o`` an object made by ``cls.__new__(cls, *a)`` (``copyreg.__newobj__``), ``$r`` one made
  by calling ``$r`` with ``a``; both with ``s`` (state), ``li`` (list items), ``di`` (dict
  items) when the reduction has them;
* ``$ref`` an object written before, and ``$id`` on the first writing of a shared one; a
  ``$ref`` may carry ``$pre``, the parts of an immutable value or the arguments of a reduced
  object that reached it again while being written (read for what they define, then dropped,
  as pickle drops them before its memo get).

``loads`` reads only this format.  The bot itself still writes pickles, fast, on its decision
path; ``convert_pickle`` (``main``, run as a module with the paths to sweep) turns recorded
pickles into these files in a process of its own, off that path, and removes the pickle.
``latch_onset_capture.load_bytes`` (so ``restore_checkpoint_bytes``) and
``town_arrival_checkpoint.policy_file`` read either form.
"""
from __future__ import annotations

import base64
import copyreg
import gzip
import importlib
import json
import math
import os
import pathlib
import sys
from pathlib import Path

FORMAT = "hengbot-json-snapshot"
VERSION = 1
GZIP_MAGIC = b"\x1f\x8b"

_ATOMS = (str, int, bool, type(None))
_ATOM_TYPES = frozenset({str, int, bool, type(None)})
_ROUTINES = frozenset({type(len), type(_ATOMS.__len__), type(lambda: None)})
_PATH_CLASSES = frozenset({
    "Path", "WindowsPath", "PosixPath", "PurePath", "PureWindowsPath", "PurePosixPath",
})
# The concrete path class of the other OS cannot be instantiated here (the viewing bots run
# on Linux): such a path becomes this OS's ``Path``, as latch_onset_capture's unpickler does.
_FOREIGN_CONCRETE_PATH = "PosixPath" if os.name == "nt" else "WindowsPath"


def _qualname(obj) -> str:
    return f"{obj.__module__}:{obj.__qualname__}"


def _resolve(name: str):
    module, _, qual = name.partition(":")
    if module in {"pathlib", "pathlib._local"} and qual in _PATH_CLASSES:
        return pathlib.Path if qual == _FOREIGN_CONCRETE_PATH else getattr(pathlib, qual)
    value = importlib.import_module(module)
    for part in qual.split("."):
        value = getattr(value, part)
    return value


def _atomic_value(obj) -> bool:
    """A tuple or frozenset of atoms: written as a value, never by identity."""
    return _ATOM_TYPES.issuperset(map(type, obj))


class _Encoder:
    def __init__(self):
        self.counts: dict[int, int] = {}
        self.ids: dict[int, int] = {}
        self.reductions: dict[int, tuple] = {}
        self.plain: dict[type, bool] = {}
        self.keep: list = []  # reductions' temporaries stay alive, so their ids stay unique
        self.plain_keys: set = set()  # str keys known not to start with "$"
        self.open: dict[int, int | None] = {}  # unshared objects being written

    def _is_plain(self, kind) -> bool:
        """Instances pickled as ``cls.__new__(cls)`` plus their ``__dict__``, and nothing else."""
        plain = self.plain.get(kind)
        if plain is None:
            plain = (
                kind.__reduce_ex__ is object.__reduce_ex__
                and kind.__reduce__ is object.__reduce__
                and getattr(kind, "__getstate__", object.__getstate__) is object.__getstate__
                and not hasattr(kind, "__getnewargs_ex__")
                and not hasattr(kind, "__getnewargs__")
                and "__slots__" not in kind.__dict__
                and not any("__slots__" in base.__dict__ and base.__dict__["__slots__"]
                            for base in kind.__mro__[1:-1])
                and not issubclass(kind, (list, dict, set, frozenset, tuple, int, str, bytes, float))
                and kind.__dictoffset__ != 0
                and kind.__new__ is object.__new__
                and copyreg.dispatch_table.get(kind) is None
            )
            self.plain[kind] = plain
        return plain

    def _reduce(self, obj) -> tuple:
        key = id(obj)
        reduction = self.reductions.get(key)
        if reduction is None:
            reducer = copyreg.dispatch_table.get(type(obj))
            reduction = reducer(obj) if reducer else obj.__reduce_ex__(5)
            if isinstance(reduction, str):
                raise TypeError(f"{type(obj)!r} reduces to a global name ({reduction})")
            reduction = tuple(reduction) + (None,) * (5 - len(reduction))
            if reduction[3] is not None:
                reduction = reduction[:3] + (list(reduction[3]),) + reduction[4:]
            if reduction[4] is not None:
                reduction = reduction[:4] + (list(reduction[4]),) + reduction[5:]
            self.reductions[key] = reduction
            self.keep.append(reduction)
        return reduction

    def count(self, root) -> None:
        """How often each object that may be shared is reached (the first pass)."""
        counts = self.counts
        stack = [root]
        push = stack.append
        while stack:
            obj = stack.pop()
            kind = type(obj)
            if kind in _ATOM_TYPES or kind is float:
                continue
            if (kind is tuple or kind is frozenset) and _atomic_value(obj):
                continue
            key = id(obj)
            seen = counts.get(key)
            counts[key] = 2 if seen else 1
            if seen:
                continue
            if kind is dict:
                for item_key, value in obj.items():
                    if type(item_key) not in _ATOM_TYPES:
                        push(item_key)
                    if type(value) not in _ATOM_TYPES:
                        push(value)
            elif kind is list or kind is tuple or kind is set or kind is frozenset:
                for item in obj:
                    if type(item) not in _ATOM_TYPES:
                        push(item)
            elif kind is bytes or isinstance(obj, type) or kind in _ROUTINES:
                continue
            elif self._is_plain(kind):
                push(obj.__dict__)
            else:
                _, args, state, items, pairs = self._reduce(obj)
                stack.extend(args)
                if state is not None:
                    push(state)
                if items:
                    stack.extend(items)
                if pairs:
                    for pair in pairs:
                        stack.extend(pair)

    def _number(self, key, shared):
        if not shared:
            return None
        node_id = self.ids[key] = len(self.ids)
        return node_id

    def _plain_keys(self, mapping) -> bool:
        """Every key a string not starting with "$": the dict is written as a JSON object."""
        known = self.plain_keys
        if known.issuperset(mapping):
            return True
        if not all(type(k) is str and not k.startswith("$") for k in mapping):
            return False
        known.update(mapping)
        return True

    @staticmethod
    def _with_id(node, node_id):
        if node_id is not None:
            node["$id"] = node_id
        return node

    def _items(self, items):
        encode = self.encode
        return [item if type(item) in _ATOM_TYPES else encode(item) for item in items]

    def _open(self, key, shared):
        """Number a shared object now; an unshared one may be numbered while it is written."""
        if shared:
            return self._number(key, True)
        self.open[key] = None
        return None

    def _close(self, key, node_id):
        """The number of an object done being written: its own, or one a cycle gave it."""
        if node_id is not None:
            return node_id
        return self.open.pop(key)

    def encode(self, obj):
        kind = type(obj)
        if kind in _ATOM_TYPES:
            return obj
        if kind is float:
            return obj if math.isfinite(obj) else {"$f": repr(obj)}
        key = id(obj)
        node_id = self.ids.get(key)
        if node_id is not None:
            return {"$ref": node_id}
        if key in self.open:
            # Reached again while being written (a cycle through an immutable value, written
            # once more by its re-entry): numbered now; the node takes the number when done.
            node_id = self.open[key] = self._number(key, True)
            return {"$ref": node_id}
        shared = self.counts.get(key, 1) > 1
        # Mutable containers and plain objects are numbered before their items, as pickle
        # memoizes them: the reader makes them first, so an item may refer back to them.
        if kind is dict:
            node_id = self._open(key, shared)
            encode = self.encode
            if self._plain_keys(obj):
                body = {k: v if type(v) in _ATOM_TYPES else encode(v) for k, v in obj.items()}
                node_id = self._close(key, node_id)
                return body if node_id is None else {"$id": node_id, "$d": body}
            node = {"$dl": [[k if type(k) in _ATOM_TYPES else encode(k),
                             v if type(v) in _ATOM_TYPES else encode(v)] for k, v in obj.items()]}
            return self._with_id(node, self._close(key, node_id))
        if kind is list:
            node_id = self._open(key, shared)
            items = self._items(obj)
            node_id = self._close(key, node_id)
            return items if node_id is None else {"$id": node_id, "$l": items}
        if kind is set:
            node_id = self._open(key, shared)
            node = {"$s": self._items(obj)}
            return self._with_id(node, self._close(key, node_id))
        if kind is not tuple and kind is not frozenset and kind is not bytes and                 not isinstance(obj, type) and kind not in _ROUTINES and self._is_plain(kind):
            # copyreg.__newobj__ with no arguments, the instance dict as the state.
            node_id = self._open(key, shared)
            node = {"$o": _qualname(kind), "a": []}
            state = self.encode(obj.__dict__) if obj.__dict__ else None
            node = self._with_id(node, self._close(key, node_id))
            if state is not None:
                node["s"] = state
            return node
        if kind is tuple:
            node = {"$t": self._items(obj)}
        elif kind is frozenset:
            node = {"$fs": self._items(obj)}
        elif kind is bytes:
            node = {"$b": base64.b64encode(obj).decode("ascii")}
        elif isinstance(obj, type) or kind in _ROUTINES:
            node = {"$g": _qualname(obj)}
        else:
            # A reduced object: its arguments first, then the number, as pickle memoizes it.
            function, args, state, items, pairs = self._reduce(obj)
            if function is copyreg.__newobj__:
                node = {"$o": _qualname(args[0]), "a": self._items(args[1:])}
            elif function is copyreg.__newobj_ex__:
                cls, positional, keywords = args
                node = {"$o": _qualname(cls), "a": self._items(positional),
                        "kw": self.encode(dict(keywords))}
            else:
                node = {"$r": self._callable(function), "a": self._items(args)}
            if key in self.ids:
                # Its arguments reached it again and wrote it: keep what they wrote, as
                # pickle keeps the arguments it popped before its memo get.
                return {"$ref": self.ids[key], "$pre": node}
            node_id = self._open(key, shared)
            li = self._items(items) if items else None
            di = [[self.encode(k), self.encode(v)] for k, v in pairs] if pairs else None
            s_node = self.encode(state) if state is not None else None
            node = self._with_id(node, self._close(key, node_id))
            if li is not None:
                node["li"] = li
            if di is not None:
                node["di"] = di
            if s_node is not None:
                node["s"] = s_node
            return node
        if key in self.ids:
            # A part of this immutable value reached it again and wrote it first: keep what its
            # parts wrote (``$pre``, read for their definitions only), then refer to it.
            return {"$ref": self.ids[key], "$pre": node}
        return self._with_id(node, self._number(key, self.counts.get(key, 1) > 1))

    @staticmethod
    def _callable(function):
        owner = getattr(function, "__self__", None)
        if isinstance(owner, type):
            return {"cls": _qualname(owner), "m": function.__name__}
        return _qualname(function)


class _Decoder:
    def __init__(self):
        self.memo: dict[int, object] = {}

    def _remember(self, node, value):
        node_id = node.get("$id")
        if node_id is not None:
            self.memo[node_id] = value
        return value

    def decode(self, node):
        kind = type(node)
        if kind in _ATOM_TYPES or kind is float:
            return node
        if kind is list:
            decode = self.decode
            return [item if type(item) in _ATOM_TYPES else decode(item) for item in node]
        if "$ref" in node:
            if "$pre" in node:
                self.decode({k: v for k, v in node["$pre"].items() if k != "$id"})
            return self.memo[node["$ref"]]
        if "$d" in node or not any(k.startswith("$") for k in node):
            result = self._remember(node, {})
            body = node["$d"] if "$d" in node else node
            decode = self.decode
            for k, v in body.items():
                result[k] = v if type(v) in _ATOM_TYPES else decode(v)
            return result
        if "$dl" in node:
            result = self._remember(node, {})
            for k, v in node["$dl"]:
                k = self.decode(k)  # the key first, as it was written
                result[k] = self.decode(v)
            return result
        if "$l" in node:
            result = self._remember(node, [])
            result.extend(self.decode(item) for item in node["$l"])
            return result
        if "$s" in node:
            result = self._remember(node, set())
            result.update(self.decode(item) for item in node["$s"])
            return result
        if "$o" in node or "$r" in node:
            args = self.decode(node["a"])
            if "$o" in node:
                cls = _resolve(node["$o"])
                if "kw" in node:
                    result = cls.__new__(cls, *args, **self.decode(node["kw"]))
                else:
                    result = cls.__new__(cls, *args)
            else:
                name = node["$r"]
                function = (getattr(_resolve(name["cls"]), name["m"])
                            if isinstance(name, dict) else _resolve(name))
                result = function(*args)
            self._remember(node, result)
            self._build(result, node)
            return result
        if "$t" in node:
            value = tuple(self.decode(item) for item in node["$t"])
        elif "$fs" in node:
            value = frozenset(self.decode(item) for item in node["$fs"])
        elif "$b" in node:
            value = base64.b64decode(node["$b"])
        elif "$f" in node:
            value = float(node["$f"])
        elif "$g" in node:
            value = _resolve(node["$g"])
        else:
            raise ValueError(f"not a snapshot node: {sorted(node)[:4]}")
        return self._remember(node, value)

    def _build(self, instance, node):
        """pickle's APPENDS, SETITEMS and BUILD, in that order."""
        if "li" in node:
            for item in node["li"]:
                instance.append(self.decode(item))
        if "di" in node:
            for k, v in node["di"]:
                k = self.decode(k)
                instance[k] = self.decode(v)
        if "s" not in node:
            return
        state = self.decode(node["s"])
        setstate = getattr(instance, "__setstate__", None)
        if setstate is not None:
            setstate(state)
            return
        slotstate = None
        if isinstance(state, tuple) and len(state) == 2:
            state, slotstate = state
        if state:
            instance_dict = instance.__dict__
            for k, v in state.items():
                instance_dict[sys.intern(k) if type(k) is str else k] = v
        if slotstate:
            for k, v in slotstate.items():
                setattr(instance, k, v)


def _deep(function, *args):
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(limit, 100_000))
    try:
        return function(*args)
    finally:
        sys.setrecursionlimit(limit)


def _document(obj) -> dict:
    encoder = _Encoder()
    encoder.count(obj)
    return {"format": FORMAT, "version": VERSION, "state": _deep(encoder.encode, obj)}


def dumps(obj) -> bytes:
    """``obj`` as gzip-compressed JSON (the module docstring's format)."""
    text = json.dumps(_document(obj), ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False)
    return gzip.compress(text.encode("utf-8"), compresslevel=6, mtime=0)


def dump(obj, path: Path) -> None:
    """``dumps(obj)`` written to ``path``, streamed (no whole JSON text in memory), atomically."""
    temporary = path.with_name(f".{path.name}.tmp")
    encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    try:
        with open(temporary, "wb") as raw, \
                gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6, mtime=0) as stream:
            for chunk in encoder.iterencode(_document(obj)):
                stream.write(chunk.encode("utf-8"))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def loads(payload: bytes):
    """The object ``dumps`` wrote."""
    document = json.loads(gzip.decompress(payload).decode("utf-8"))
    if document.get("format") != FORMAT:
        raise ValueError(f"not a {FORMAT} document")
    if document.get("version") != VERSION:
        raise ValueError(f"{FORMAT} version {document.get('version')} is not {VERSION}")
    return _deep(_Decoder().decode, document["state"])


def is_snapshot(payload: bytes) -> bool:
    """A ``dumps`` payload, by its first bytes (a pickle starts otherwise)."""
    return payload[:2] == GZIP_MAGIC


# The conversion off the bot's path (owner 2026-11-13 「ログの圧縮を別で行うことでbotを止めないことと
# 容量節約を両立できないか？」): the bot writes its checkpoints as pickles, fast, and this turns the
# recorded ones into json_snapshot files later, in a process of its own.
PICKLE_SUFFIX = ".pkl"
SNAPSHOT_SUFFIX = ".json.gz"


def converted_path(pickle_path: Path) -> Path:
    """Where ``convert_pickle`` writes the snapshot of ``pickle_path`` (policy.pkl -> policy.json.gz)."""
    return pickle_path.with_name(pickle_path.name.removesuffix(PICKLE_SUFFIX) + SNAPSHOT_SUFFIX)


def convert_pickle(pickle_path: Path) -> Path:
    """Write ``pickle_path``'s object as a json_snapshot beside it, then remove the pickle.

    The pickle is read as a checkpoint restore reads it (latch_onset_capture's portable
    unpickler).  The snapshot is written to a temporary name and renamed into place before the
    pickle is removed, so a reader always finds one of the two whole.
    """
    from hengbot.latch_onset_capture import _PortablePathUnpickler

    with open(pickle_path, "rb") as stream:
        state = _PortablePathUnpickler(stream).load()
    target = converted_path(pickle_path)
    dump(state, target)
    stat = pickle_path.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    pickle_path.unlink()
    return target


def _pickles(roots, min_age_seconds: float):
    import time

    now = time.time()
    for root in roots:
        candidates = [root] if root.is_file() else sorted(root.rglob("*" + PICKLE_SUFFIX))
        for path in candidates:
            try:
                if path.suffix == PICKLE_SUFFIX and now - path.stat().st_mtime >= min_age_seconds:
                    yield path
            except OSError:
                continue  # removed meanwhile (a visit rotated out)


def main(argv=None) -> int:
    """Convert recorded pickles: ``json_snapshot [--min-age SECONDS] PATH...`` (run with -m)."""
    import argparse

    parser = argparse.ArgumentParser(description="Convert recorded policy pickles to json_snapshot.")
    parser.add_argument("paths", nargs="+", type=Path,
                        help="pickle files, or directories searched for *.pkl")
    parser.add_argument("--min-age", type=float, default=0.0,
                        help="only pickles last written at least this many seconds ago")
    args = parser.parse_args(argv)
    if hasattr(os, "nice"):
        os.nice(10)  # the bots come first on a shared machine
    failed = 0
    for path in _pickles(args.paths, args.min_age):
        try:
            before = path.stat().st_size
            target = convert_pickle(path)
            print(f"{path}: {before} -> {target.stat().st_size} bytes", flush=True)
        except Exception as exc:  # one bad or vanished file does not stop the sweep
            failed += 1
            print(f"{path}: not converted: {exc}", file=sys.stderr, flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
