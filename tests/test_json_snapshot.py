"""hengbot.json_snapshot: the pickle protocol's object graph as gzip-compressed JSON."""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import collections
import contextlib
import dataclasses
import enum
import gzip
import io
import json
import lzma
import os
import pickle
import tempfile
import unittest
from pathlib import Path

from hengbot import json_snapshot
from hengbot.latch_onset_capture import _PortablePathUnpickler, load_bytes, restore_checkpoint_bytes
from hengbot.model import Position
from hengbot.policy import HengbotPolicy
from hengbot.town_arrival_checkpoint import CONVERTED_POLICY_FILE, POLICY_FILE, policy_file
from tests.support.graph_equal import graph_equal

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class Colour(enum.Enum):
    RED = "red"
    BLUE = "blue"


class Shade(str, enum.Enum):
    RED = "red"


class Rank(enum.IntEnum):
    LOW = 1
    HIGH = 2


@dataclasses.dataclass(frozen=True)
class Frozen:
    name: str
    where: Position


@dataclasses.dataclass(slots=True)
class Slotted:
    count: int
    items: list


class Holder:
    def __init__(self):
        self.peer = None
        self.values = []


class Restoring:
    """A class whose __setstate__ upgrades an older state, as the policy's do."""

    def __init__(self):
        self.version = 2
        self.data = {}

    def __setstate__(self, state):
        state = dict(state)
        state.setdefault("version", 1)
        self.__dict__.update(state)


def round_trip(value):
    return json_snapshot.loads(json_snapshot.dumps(value))


class RoundTripTest(unittest.TestCase):
    def assert_same_graph(self, value):
        back = round_trip(value)
        self.assertIsNone(graph_equal(value, back))
        return back

    def test_atoms_and_containers(self):
        value = {
            "text": "日本語", "int": 2 ** 70, "neg": -3, "true": True, "none": None,
            "float": 0.1, "nan": float("nan"), "inf": float("-inf"), "bytes": b"\x00\xff",
            "tuple": (1, "a", None), "frozen": frozenset({1, 2}), "set": {3, 4},
            "list": [1, [2, [3]]], "$dollar": 1, 5: "int key", (1, 2): "tuple key",
        }
        back = self.assert_same_graph(value)
        self.assertEqual(list(back), list(value))
        self.assertIs(type(back[(1, 2)]), str)

    def test_shared_and_cyclic_references(self):
        shared = [1, 2]
        outer = {"a": shared, "b": shared}
        outer["self"] = outer
        holder, other = Holder(), Holder()
        holder.peer, other.peer = other, holder
        holder.values.append((other, holder))  # a tuple reaching its holder again
        back = self.assert_same_graph({"outer": outer, "holder": holder})
        self.assertIs(back["outer"]["a"], back["outer"]["b"])
        self.assertIs(back["outer"]["self"], back["outer"])
        self.assertIs(back["holder"].peer.peer, back["holder"])
        self.assertIs(back["holder"].values[0][1], back["holder"])

    def test_a_tuple_reached_through_its_own_items(self):
        holder = Holder()
        pair = (holder, 1)
        holder.values.append(pair)
        back = self.assert_same_graph([pair, pair])
        self.assertIs(back[0], back[1])
        self.assertIs(back[0][0].values[0], back[0])

    def test_classes_of_the_policy_kinds(self):
        value = {
            "position": Position(3, 4),
            "frozen": Frozen("x", Position(1, 2)),
            "slotted": Slotted(2, [Colour.RED]),
            "enum": Colour.BLUE, "int_enum": Rank.HIGH,
            "deque": collections.deque([1, 2], maxlen=5),
            "counter": collections.Counter("abca"),
            "default": collections.defaultdict(list, {"k": [1]}),
            "ordered": collections.OrderedDict([("b", 1), ("a", 2)]),
            "path": Path("a") / "b",
            "type": Position, "function": round_trip, "builtin": len,
        }
        back = self.assert_same_graph(value)
        self.assertIs(back["enum"], Colour.BLUE)
        self.assertEqual(back["deque"].maxlen, 5)
        back["default"]["new"].append(1)
        self.assertEqual(back["default"]["new"], [1])
        self.assertIs(back["type"], Position)

    def test_a_str_enum_key_stays_an_enum_after_an_equal_plain_key(self):
        # A (str, Enum) member equals and hashes as its value: a dict with the plain string
        # written first must not let the member's dict be written as a JSON object.
        value = [{"red": 1}, {Shade.RED: 2}, {"$x": 3}, {Shade.RED: 4, "blue": 5}]
        back = self.assert_same_graph(value)
        self.assertIs(next(iter(back[1])), Shade.RED)
        self.assertEqual([type(k) for k in back[3]], [Shade, str])

    def test_a_numpy_array_round_trips_with_its_writability(self):
        # Protocol 5 reduces an array to _frombuffer(PickleBuffer, ...): the buffer is written
        # in band, as pickle writes it (a recorded checkpoint's grid masks are bool arrays).
        import numpy

        grid = numpy.zeros((3, 4), dtype=bool)
        grid[1, 2] = True
        frozen = numpy.arange(6, dtype=numpy.int16)
        frozen.flags.writeable = False
        back = self.assert_same_graph({"grid": grid, "frozen": frozen, "again": grid})
        self.assertTrue(numpy.array_equal(back["grid"], grid))
        self.assertTrue(back["grid"].flags.writeable)
        self.assertFalse(back["frozen"].flags.writeable)
        self.assertIs(back["again"], back["grid"])
        self.assertEqual(pickle.loads(pickle.dumps(grid, protocol=5)).flags.writeable,
                         back["grid"].flags.writeable)

    def test_set_state_runs_as_in_a_pickle_restore(self):
        old = Restoring()
        del old.version
        back = round_trip(old)
        self.assertEqual(back.version, 1)
        self.assertEqual(pickle.loads(pickle.dumps(old)).version, 1)

    def test_a_foreign_path_class_reads_as_this_os_path(self):
        payload = json_snapshot.dumps({"p": Path("x")})
        document = json.loads(gzip.decompress(payload))
        native = type(Path("x")).__name__
        foreign = "PosixPath" if native == "WindowsPath" else "WindowsPath"
        text = json.dumps(document).replace(native, foreign)
        back = json_snapshot.loads(gzip.compress(text.encode()))
        self.assertEqual(back["p"], Path("x"))

    def test_the_document_names_its_format(self):
        document = json.loads(gzip.decompress(json_snapshot.dumps([1])))
        self.assertEqual((document["format"], document["version"]),
                         (json_snapshot.FORMAT, json_snapshot.VERSION))
        self.assertTrue(json_snapshot.is_snapshot(json_snapshot.dumps([1])))
        self.assertFalse(json_snapshot.is_snapshot(pickle.dumps([1], protocol=5)))
        with self.assertRaises(ValueError):
            json_snapshot.loads(gzip.compress(b'{"format": "other", "version": 1, "state": 1}'))

    def test_a_recorded_policy_checkpoint_round_trips(self):
        # A pickle the bot recorded: its whole state graph comes back alike from JSON.
        payload = lzma.decompress((FIXTURES / "curse-first-20261103" / "policy.pkl.xz").read_bytes())
        state = _PortablePathUnpickler(io.BytesIO(payload)).load()
        self.assertGreater(len(state), 100)
        self.assertIsNone(graph_equal(state, round_trip(state)))


class ConversionTest(unittest.TestCase):
    """The pickle the bot writes, converted off its decision path (owner 2026-11-13)."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        self.pickle = lzma.decompress(
            (FIXTURES / "curse-first-20261103" / "policy.pkl.xz").read_bytes())

    def visit(self, name="visit"):
        visit = self.root / name
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(self.pickle)
        return visit

    def test_a_converted_checkpoint_restores_the_same_state(self):
        visit = self.visit()
        target = json_snapshot.convert_pickle(visit / POLICY_FILE)
        self.assertEqual(target, visit / CONVERTED_POLICY_FILE)
        self.assertFalse((visit / POLICY_FILE).exists())
        self.assertEqual(policy_file(visit), target)
        converted = load_bytes(target.read_bytes())
        original = load_bytes(self.pickle)
        self.assertIsNone(graph_equal(original, converted))
        self.assertLess(target.stat().st_size, len(self.pickle))
        restored = restore_checkpoint_bytes(HengbotPolicy, target.read_bytes())
        self.assertIsInstance(restored, HengbotPolicy)

    def test_the_streamed_file_is_the_same_document(self):
        value = {"a": [1, 2, {"b": (3, Position(1, 2))}]}
        path = self.root / "value.json.gz"
        json_snapshot.dump(value, path)
        self.assertEqual(gzip.decompress(path.read_bytes()),
                         gzip.decompress(json_snapshot.dumps(value)))
        self.assertEqual(list(self.root.iterdir()), [path])  # no temporary file left

    def test_the_sweep_converts_only_pickles_old_enough(self):
        old, new = self.visit("old"), self.visit("new")
        past = (old / POLICY_FILE).stat().st_mtime - 3600
        os.utime(old / POLICY_FILE, (past, past))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(json_snapshot.main(["--min-age", "600", str(self.root)]), 0)
        self.assertEqual(policy_file(old), old / CONVERTED_POLICY_FILE)
        self.assertEqual(policy_file(new), new / POLICY_FILE)
        self.assertAlmostEqual((old / CONVERTED_POLICY_FILE).stat().st_mtime, past, delta=1)

    def test_an_unconverted_visit_reads_its_pickle(self):
        visit = self.visit()
        self.assertEqual(policy_file(visit), visit / POLICY_FILE)
        self.assertIsInstance(
            restore_checkpoint_bytes(HengbotPolicy, policy_file(visit).read_bytes()), HengbotPolicy)


if __name__ == "__main__":
    unittest.main()
