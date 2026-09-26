"""Standing guard: the decision-row telemetry is a pure observer.

Principle (reviewer 2026-09-23, from the standing rule "telemetry must be
pure"): ``cli._capture_decision_facts`` evaluates policy state for the
decision row.  Whether it runs, and how often, must not change any later
decision, key or policy state: a driver that never writes decision rows must
reach exactly the decisions of one that does.

Defect (proven by these pins on the parent commit): the evaluators share their
implementation with the decision path, and that implementation memoizes into
the policy.  ``equipment_optimization_state(snapshot)`` ran
``_prepare_equipment_optimization`` at no depth and stored its preparation,
signature, input keys and search telemetry (policy_equipment.py 553-1110), and
the decision path then reused that preparation: its blockers entered the town
progress fingerprint (policy_town.py 801) and so the town turn arbiter's
recurrence keys.  The same capture filled the town fact / entrance caches, the
town need evaluation caches, the lazily loaded character calibration and the
identity memos.

Differential harness: two policies are driven through the same recorded rows
(or the same synthetic world).  Policy A runs the capture at every decision
boundary exactly as the CLI does (after ``validate_read_key``, before the key
is posted); policy B never runs it.  After every step:
- T1: A and B decided the same key and reason;
- T2: A's and B's policy state (``vars``) are identical, with two declared
  normalisations: the three identity memos (``_fixed_quest_head_cache``,
  ``_fixed_quest_offer_cache``, ``_threat_prediction_memo``) key their entries
  by ``id()`` of transient board objects, which differ between two drivers by
  construction, so they compare by their entries in insertion order with the
  ``id()`` components dropped (each entry holds its board, which compares by
  value); and ``elapsed_seconds`` (the optimizer's wall-clock timing) is
  ignored.  The per-policy temporary directory is normalised in paths.
T3: the capture's facts equal those of the pre-change evaluation (the
unscoped ``_capture_decision_facts_unchecked`` on an independent copy of the
same policy state), field for field.

Substrates (frozen fixtures, sha256-pinned by their own modules):
- protocol 3: the 2026-09-22 unaffordable-claim-tour lifetime (the experience
  potion rounds), its first town visit while the ~f skill values are still
  unknown (skill-exp-unknown) through the Home scan, shopping and the recall;
- protocol 3: the 2026-09-22 entrance-travel boards (decisions 20633-20636);
- protocol 2: the 2026-09-22 Morivant travel lifetime prefix;
- protocol 2: the golden opening trajectory (synthetic town world).
Walls: the recorded periodic save/dump decisions receive the CLI timer
request that produced them; the tour lifetime walls the experience drain view
to unknown (its module's documented wall).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import copy
import enum
import gzip
import hashlib
import json
import shutil
import types
import unittest
from pathlib import Path, PurePath
from tempfile import TemporaryDirectory

from hengbot.cli import (
    _capture_decision_facts,
    _capture_decision_facts_unchecked,
    _consume_response_sequence,
)
from hengbot.monrace_knowledge import load_monrace_knowledge

import test_entrance_travel_retired_recorded as entrance
import test_esp_threat_rest_recorded as esp_recorded
import test_golden_trajectory as golden
import test_morivant_travel_retired_recorded as morivant
import test_unaffordable_claim_tour_recorded as tour


# The tour lifetime's first town visit: list index 20 is the recorded
# 'town:recall-to-angband'; the window runs past it into the dungeon.
TOUR_WINDOW = 40
# The tour lifetime's second town arrival (list indices = decision + 4):
# 2636-2639 wait for the recall in the dungeon, 2640 is the arrival's ~f
# request (skill values unknown), 2641 town:recover, 2642 shop:approach into
# the Home, and 2643 is the first decision whose key depends on the capture.
RECALL_WAIT = 2636
SKILL_REQUEST = 2640
FIRST_CAPTURE_DEPENDENT = 2643
# The tour recording contains the loot/choke alternation this repository fixed
# on 2026-09-23: at the (15, 16) choke of floor (1, 42, 0) the recorded run
# bounced between detected:prepare-choke (north) and explore/search (south)
# until a livelock recall escaped it.  A started anticipatory retreat now
# commits to the covered cell it chose and, having reached it, holds it under
# the unchanged 50-turn bound, so the replay answers these boards differently.
CHOKE_ALTERNATION_FIXED = {
    1848: ["5", "summoner:hold-choke"],
    1997: ["5", "summoner:hold-choke"],
    1999: ["5", "summoner:hold-choke"],
    2001: ["5", "summoner:hold-choke"],
    2003: ["5", "summoner:hold-choke"],
    2011: ["s", "search"],
    2013: ["5", "summoner:hold-choke"],
    2014: ["s", "search"],
}
MORIVANT_WINDOW = 120
IDENTITY_MEMOS = frozenset({
    "_fixed_quest_head_cache",
    "_fixed_quest_offer_cache",
    "_threat_prediction_memo",
})
TIMING_FIELDS = frozenset({"elapsed_seconds"})
# Static game data loaded identically by both builders; shared so the state
# comparison does not re-walk it every step.
STATIC_KNOWLEDGE = (
    "_town_map", "_town_maps", "_wilderness_map", "_dungeon_knowledge",
    "_monrace_knowledge", "_damaging_terrain_ids", "_quest_knowledge",
    "_quest_strategies", "_baseitem_costs",
)
_ATOMS = (int, float, complex, str, bytes, bool, type(None), range, enum.Enum)


class _StateComparison:
    """Structural difference of two independently driven policies."""

    def __init__(self, directories: tuple[str, str]):
        self._directories = tuple(
            spelling
            for directory in directories
            for spelling in (directory, directory.replace("\\", "/"))
        )
        # Frozen dataclasses (boards, items, grids) never change after
        # construction; an equal pair stays equal while both are alive.
        self._equal_frozen: dict[tuple[int, int], tuple[object, object]] = {}

    def _path(self, text: str) -> str:
        for spelling in self._directories:
            text = text.replace(spelling, "<tmp>")
        return text

    def policies(self, left, right, limit: int = 20) -> list[tuple[str, str, str]]:
        out: list[tuple[str, str, str]] = []
        seen: set[tuple[int, int]] = set()
        left_state, right_state = vars(left), vars(right)
        for name in sorted(set(left_state) | set(right_state)):
            if name not in left_state or name not in right_state:
                out.append((
                    name,
                    "present" if name in left_state else "absent",
                    "present" if name in right_state else "absent",
                ))
                continue
            a, b = left_state[name], right_state[name]
            if name in IDENTITY_MEMOS and isinstance(a, dict) and isinstance(b, dict):
                a, b = self._identity_memo(a), self._identity_memo(b)
            self._diff(a, b, name, out, seen, limit)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _identity_memo(memo: dict) -> list:
        def without_identity(key):
            if isinstance(key, int):
                return None
            if isinstance(key, tuple):
                # (id(board), turn, turns, ids of hostiles, contact, speed, slots)
                return tuple(
                    None if index in {0, 3} else part
                    for index, part in enumerate(key)
                )
            return key
        return [(without_identity(key), value) for key, value in memo.items()]

    def _diff(self, a, b, path, out, seen, limit):
        if len(out) >= limit or a is b:
            return
        pair = (id(a), id(b))
        if pair in seen:
            return
        seen.add(pair)
        if isinstance(a, PurePath) and isinstance(b, PurePath):
            a, b = str(a), str(b)
        if isinstance(a, str) and isinstance(b, str):
            if self._path(a) != self._path(b):
                out.append((path, repr(a)[:160], repr(b)[:160]))
            return
        if type(a) is not type(b):
            out.append((path, type(a).__name__, type(b).__name__))
            return
        params = getattr(type(a), "__dataclass_params__", None)
        if params is not None and params.frozen:
            cached = self._equal_frozen.get(pair)
            if cached is not None and cached[0] is a and cached[1] is b:
                return
            before = len(out)
            self._structure(a, b, path, out, seen, limit)
            if len(out) == before:
                self._equal_frozen[pair] = (a, b)
            return
        self._structure(a, b, path, out, seen, limit)

    def _structure(self, a, b, path, out, seen, limit):
        if isinstance(a, _ATOMS):
            if a != b:
                out.append((path, repr(a)[:160], repr(b)[:160]))
            return
        if isinstance(a, dict):
            if set(a) != set(b):
                out.append((
                    path,
                    f"only {sorted(map(repr, set(a) - set(b)))[:3]}",
                    f"only {sorted(map(repr, set(b) - set(a)))[:3]}",
                ))
                return
            for key in a:
                if key in TIMING_FIELDS:
                    continue
                self._diff(a[key], b[key], f"{path}[{key!r}]", out, seen, limit)
            return
        if isinstance(a, (list, tuple)) or type(a).__name__ == "deque":
            if len(a) != len(b):
                out.append((path, f"len {len(a)}", f"len {len(b)}"))
                return
            for index, (x, y) in enumerate(zip(a, b)):
                self._diff(x, y, f"{path}[{index}]", out, seen, limit)
            return
        if isinstance(a, (set, frozenset)):
            if a != b:
                out.append((
                    path,
                    repr(sorted(map(repr, a - b))[:3]),
                    repr(sorted(map(repr, b - a))[:3]),
                ))
            return
        if isinstance(a, (types.FunctionType, types.MethodType, types.BuiltinFunctionType)):
            if a.__qualname__ != b.__qualname__:
                out.append((path, a.__qualname__, b.__qualname__))
            return
        if hasattr(a, "__dict__") or hasattr(type(a), "__slots__"):
            if hasattr(a, "__dict__"):
                left, right = vars(a), vars(b)
                if set(left) != set(right):
                    out.append((path, sorted(set(left) - set(right)),
                                sorted(set(right) - set(left))))
                    return
                for name in left:
                    if name in TIMING_FIELDS:
                        continue
                    self._diff(left[name], right[name], f"{path}.{name}", out, seen, limit)
            for cls in type(a).__mro__:
                slots = getattr(cls, "__slots__", ())
                for name in (slots,) if isinstance(slots, str) else slots:
                    if name in {"__dict__", "__weakref__"} or name in TIMING_FIELDS:
                        continue
                    self._diff(
                        getattr(a, name, None), getattr(b, name, None),
                        f"{path}.{name}", out, seen, limit,
                    )
            return
        if a != b:
            out.append((path, repr(a)[:160], repr(b)[:160]))


def _without_timing(value):
    if isinstance(value, dict):
        return {
            key: _without_timing(item)
            for key, item in value.items()
            if key not in TIMING_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [_without_timing(item) for item in value]
    return value


def _independent_copy(policy):
    clone = copy.deepcopy(policy)
    # Cached NeedSpec closures would evaluate the original policy.
    clone._town_need_specs = None
    return clone


def _relocate(policy, old: Path, new: Path) -> None:
    """Point a forked policy's own files (and its Home state's) at ``new``."""
    for holder in (policy, *(
        value for value in vars(policy).values() if hasattr(value, "history_path")
    )):
        for name, value in list(vars(holder).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                setattr(holder, name, new / value.relative_to(old))


def _recorded(fixture: Path) -> tuple[dict, list[str]]:
    boundaries = json.loads(
        fixture.with_suffix(".boundaries.json").read_text(encoding="utf-8")
    )
    with gzip.open(fixture, "rt", encoding="utf-8") as stream:
        lines = list(stream)
    return boundaries, lines


class _Lockstep:
    """Policy A captures telemetry at every boundary; policy B never does."""

    def __init__(self, test, build, walls=None):
        self.test = test
        self.directories = []
        self.policies = []
        self.monrace = None
        for _ in range(2):
            directory = TemporaryDirectory()
            test.addCleanup(directory.cleanup)
            self.directories.append(Path(directory.name))
            policy, self.monrace = build(Path(directory.name))
            self.policies.append(policy)
        telemetry, silent = self.policies
        for name in STATIC_KNOWLEDGE:
            if hasattr(telemetry, name):
                setattr(silent, name, getattr(telemetry, name))
        self.walls = walls
        self.comparison = _StateComparison(tuple(map(str, self.directories)))
        self.decisions = []
        self.facts = []
        self.state_differences = []
        self.decision_differences = []
        self.t3_every = 0

    def observe(self, segment):
        boards = []
        for policy, directory in zip(self.policies, self.directories):
            _decoded, snapshots = _consume_response_sequence(
                segment, policy, lambda _key: True, self.monrace,
                knowledge_ledger_path=directory / "knowledge.jsonl",
            )
            if self.walls is not None:
                self.walls(policy)
            boards.append(snapshots[-1])
        return boards

    def decide(self, boards, recorded_reason=None, step=None):
        decided = []
        for index, (policy, board) in enumerate(zip(self.policies, boards)):
            if recorded_reason == "periodic:game-save":
                policy.request_game_save()
            elif recorded_reason == "periodic:character-dump":
                policy.request_character_dump()
            key = policy.choose_key(board)
            key = policy.validate_read_key(board, key)
            decided.append((str(key), policy.last_reason))
            if index == 0:
                if self.t3_every and len(self.decisions) % self.t3_every == 0:
                    reference = _capture_decision_facts_unchecked(
                        policy.with_known_skill_exp(board),
                        _independent_copy(policy),
                    )
                    self.facts.append((
                        len(self.decisions), reference,
                        _capture_decision_facts(board, policy),
                    ))
                else:
                    _capture_decision_facts(board, policy)
            policy.confirm_key_posted(key)
        step = len(self.decisions) if step is None else step
        self.decisions.append(decided)
        if decided[0] != decided[1]:
            self.decision_differences.append((step, *decided))
        difference = self.comparison.policies(*self.policies)
        if difference:
            self.state_differences.append((step, difference))
        return decided

    def files(self):
        """Files each policy wrote in its own directory, by relative name.

        JSON-lines records drop their wall-clock ``time`` stamp.
        """
        def content(path):
            if path.suffix != ".jsonl":
                return path.read_bytes()
            return [
                {key: value for key, value in json.loads(line).items() if key != "time"}
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        return [
            {
                str(path.relative_to(directory)): content(path)
                for path in sorted(directory.rglob("*"))
                if path.is_file()
            }
            for directory in self.directories
        ]

    def assert_pure(self):
        # T1: every step decided the same key and reason.
        self.test.assertEqual(self.decision_differences, [])
        # T2: no step left the two policies in different state (the first
        # differing step alone is reported; a later one cannot be first).
        self.test.assertEqual(self.state_differences[:1], [])
        # The capture also wrote no file of its own.
        first, second = self.files()
        self.test.assertEqual(sorted(first), sorted(second))
        self.test.assertEqual(first, second)


def _tour_build(directory: Path):
    return tour._live_like_policy(directory)


def _tour_walls(policy):
    policy._experience_drain_known = tour._drain_unknown


def _skill_request_not_inflight(policy):
    policy._skill_exp_request_inflight = False


_MONRACE = []


def _esp_build(directory: Path):
    if not _MONRACE:
        _MONRACE.append(
            load_monrace_knowledge(esp_recorded.EDIT / "MonraceDefinitions.jsonc")
        )
    return esp_recorded._policy(directory, _MONRACE[0]), _MONRACE[0]


class PureDecisionTelemetryTest(unittest.TestCase):
    def _recorded_lifetime(self, fixture, sha256, build, walls, window, t3_every=0):
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), sha256)
        boundaries, lines = _recorded(fixture)
        lockstep = _Lockstep(self, build, walls)
        lockstep.t3_every = t3_every
        cursor = 0
        for index in range(window):
            count = boundaries["input_rows"][index]
            boards = lockstep.observe(lines[cursor:cursor + count])
            cursor += count
            lockstep.decide(boards, boundaries["recorded"][index][1], index)
        return lockstep, boundaries

    def test_t1_t2_protocol3_tour_first_town_visit(self):
        lockstep, boundaries = self._recorded_lifetime(
            tour.FIXTURE, tour.FIXTURE_SHA256, _tour_build, _tour_walls,
            TOUR_WINDOW,
        )
        # Substrate fidelity: the window replays the recorded decisions
        # (the town visit opens on the skill-exp-unknown ~f request).
        decisions = [list(pair) for pair, _silent in lockstep.decisions]
        # The captured b stack holds eleven potions. A one-item Home deposit
        # now answers input_quantity at index 5; compare the remaining frozen
        # stream modulo that exact response (R4).
        self.assertEqual(boundaries["recorded"][5], ["db\x1b", "home:atomic-deposit"])
        self.assertEqual(decisions[5], ["db1\r\x1b", "home:atomic-deposit"])
        decisions[5] = boundaries["recorded"][5]
        self.assertEqual(decisions, boundaries["recorded"][:TOUR_WINDOW])
        self.assertEqual(lockstep.decisions[0][0][1], "periodic:skill-exp-knowledge")
        self.assertEqual(
            sum(pair[1] == "town:recall-to-angband" for pair, _ in lockstep.decisions), 1
        )
        lockstep.assert_pure()

    def test_t1_t2_protocol3_town_arrival_reuses_no_telemetry_result(self):
        """T1 revert-proof: the second town arrival of the tour lifetime.

        The lifetime is replayed WITHOUT the capture to the recall wait (its
        decisions are the recorded ones), then forked into two identical
        policies: A captures at every boundary, B never does.  On the parent
        commit A's capture on the ~f request board (skill values unknown)
        stored a preparation blocked on skill-exp-unknown under the
        skill-independent selector signature; after the ~f response the
        decision path reused it as a signature-cache hit, opened no equipment
        transaction and at 2643 posted the recorded '~9' Home scan, where B
        (its own fresh search) had opened the transaction.
        """
        self.assertEqual(
            hashlib.sha256(tour.FIXTURE.read_bytes()).hexdigest(), tour.FIXTURE_SHA256
        )
        boundaries, lines = _recorded(tour.FIXTURE)
        recorded = boundaries["recorded"]
        silent_directory = TemporaryDirectory()
        self.addCleanup(silent_directory.cleanup)
        silent_root = Path(silent_directory.name)
        silent, monrace = tour._live_like_policy(silent_root)
        cursor = 0
        replayed = []
        for index in range(RECALL_WAIT):
            count = boundaries["input_rows"][index]
            _decoded, snapshots = _consume_response_sequence(
                lines[cursor:cursor + count], silent, lambda _key: True, monrace,
                knowledge_ledger_path=silent_root / "knowledge.jsonl",
            )
            cursor += count
            _tour_walls(silent)
            board = snapshots[-1]
            if recorded[index][1] == "periodic:game-save":
                silent.request_game_save()
            elif recorded[index][1] == "periodic:character-dump":
                silent.request_character_dump()
            key = silent.validate_read_key(board, silent.choose_key(board))
            replayed.append([str(key), silent.last_reason])
            silent.confirm_key_posted(key)
        # R4: the b stack has eleven potions at both Home deposits. The
        # corrected one-item quantity answer changes keys 5 and 2054 only;
        # compare the later frozen stream modulo those exact answers and the
        # previously declared choke fix.
        quantity_indices = (5, 2054)
        for index in quantity_indices:
            self.assertEqual(recorded[index], ["db\x1b", "home:atomic-deposit"])
            self.assertEqual(replayed[index], ["db1\r\x1b", "home:atomic-deposit"])
        # Substrate fidelity: every other capture-free replay decision is the
        # recording, apart from the pinned choke-alternation decisions.
        self.assertEqual(
            [
                pair for index, pair in enumerate(replayed)
                if index not in CHOKE_ALTERNATION_FIXED and index not in quantity_indices
            ],
            [
                pair for index, pair in enumerate(recorded[:RECALL_WAIT])
                if index not in CHOKE_ALTERNATION_FIXED and index not in quantity_indices
            ],
        )
        self.assertEqual(
            {index: replayed[index] for index in CHOKE_ALTERNATION_FIXED},
            CHOKE_ALTERNATION_FIXED,
        )
        self.assertEqual(
            [tuple(recorded[index]) for index in sorted(CHOKE_ALTERNATION_FIXED)],
            [
                ("8", "explore"), ("2", "explore"), ("2", "explore"),
                ("2", "explore"), ("s", "search"),
                ("2", "breakout:seek-frontier"), ("8", "explore"),
                ("8", "explore"),
            ],
        )
        self.assertEqual(
            recorded[RECALL_WAIT:FIRST_CAPTURE_DEPENDENT + 1],
            [["5", "return:wait-recall"]] * (SKILL_REQUEST - RECALL_WAIT)
            + [["~f\x1b", "periodic:skill-exp-knowledge"], ["R&\r", "town:recover"],
               ["1", "shop:approach"], ["~9\x1b", "home:request-knowledge-scan"]],
        )

        telemetry_directory = TemporaryDirectory()
        self.addCleanup(telemetry_directory.cleanup)
        telemetry_root = Path(telemetry_directory.name) / "fork"
        shutil.copytree(silent_root, telemetry_root)
        memo = {
            id(getattr(silent, name)): getattr(silent, name)
            for name in STATIC_KNOWLEDGE
        }
        telemetry = copy.deepcopy(silent, memo)
        # The derived NeedSpec registry closes over the policy that built it;
        # both sides rebuild it on first use (restore_checkpoint excludes it).
        telemetry._town_need_specs = None
        silent._town_need_specs = None
        _relocate(telemetry, silent_root, telemetry_root)
        lockstep = _Lockstep.__new__(_Lockstep)
        lockstep.test = self
        lockstep.policies = [telemetry, silent]
        lockstep.directories = [telemetry_root, silent_root]
        lockstep.monrace = monrace
        lockstep.walls = _tour_walls
        lockstep.comparison = _StateComparison((str(telemetry_root), str(silent_root)))
        lockstep.decisions = []
        lockstep.state_differences = []
        lockstep.decision_differences = []
        lockstep.t3_every = 0
        self.assertEqual(lockstep.comparison.policies(telemetry, silent), [])
        for index in range(RECALL_WAIT, FIRST_CAPTURE_DEPENDENT + 1):
            count = boundaries["input_rows"][index]
            boards = lockstep.observe(lines[cursor:cursor + count])
            cursor += count
            if index == SKILL_REQUEST:
                self.assertTrue(boards[0].in_town)
                self.assertIsNone(boards[0].player.two_weapon_skill)
            lockstep.decide(boards, recorded[index][1], index)
        self.assertEqual(
            [list(pair) for pair, _silent in lockstep.decisions][:-1],
            recorded[RECALL_WAIT:FIRST_CAPTURE_DEPENDENT],
        )
        lockstep.assert_pure()

    def test_t1_t2_protocol3_entrance_travel_boards(self):
        self.assertEqual(
            hashlib.sha256(entrance.FIXTURE.read_bytes()).hexdigest(),
            entrance.FIXTURE_SHA256,
        )
        boundaries, lines = _recorded(entrance.FIXTURE)
        # Wall: the capture holds boards only; its process had read ~f before
        # them.  Each board is decided with the ~f request not in flight, so
        # the policy re-requests it and every evaluator sees skill-exp-unknown
        # (the reported protocol-3 state).
        lockstep = _Lockstep(self, _esp_build, _skill_request_not_inflight)
        cursor = 0
        for index, count in enumerate(boundaries["input_rows"]):
            boards = lockstep.observe(lines[cursor:cursor + count])
            cursor += count
            self.assertTrue(boards[0].in_town)
            self.assertEqual(getattr(boards[0], "protocol_version", 2), 3)
            lockstep.decide(boards, boundaries["recorded"][index][1], index)
        lockstep.assert_pure()

    def test_t1_t2_protocol2_morivant_lifetime_prefix(self):
        lockstep, boundaries = self._recorded_lifetime(
            morivant.FIXTURE, morivant.FIXTURE_SHA256, _esp_build, None,
            MORIVANT_WINDOW,
        )
        self.assertEqual(
            [list(pair) for pair, _silent in lockstep.decisions],
            boundaries["recorded"][:MORIVANT_WINDOW],
        )
        lockstep.assert_pure()

    def test_t1_t2_protocol2_golden_opening_trajectory(self):
        builder = golden.GoldenOpeningTrajectoryTest()
        golden.GoldenOpeningTrajectoryTest.setUpClass()
        pairs = [builder.build(), builder.build()]
        lockstep = _Lockstep.__new__(_Lockstep)
        lockstep.test = self
        lockstep.policies = [policy for policy, _world in pairs]
        lockstep.directories = []
        lockstep.comparison = _StateComparison(())
        lockstep.decisions = []
        lockstep.state_differences = []
        lockstep.decision_differences = []
        lockstep.t3_every = 0
        worlds = [world for _policy, world in pairs]
        for decision in range(1, 31):
            boards = []
            for policy, world in pairs:
                world.deliver_events(policy)
                boards.append(world.snapshot(decision))
            decided = lockstep.decide(boards)
            for world, (key, _reason) in zip(worlds, decided):
                world.apply(key)
            if worlds[0].on_quest_floor and 34 in lockstep.policies[0]._quest_navigators:
                break
        # The trajectory reaches its final milestone inside the window.
        self.assertTrue(worlds[0].on_quest_floor)
        self.assertEqual(lockstep.decision_differences, [])
        self.assertEqual(lockstep.state_differences[:1], [])

    def test_t3_capture_fields_equal_the_unscoped_evaluation(self):
        lockstep, _boundaries = self._recorded_lifetime(
            tour.FIXTURE, tour.FIXTURE_SHA256, _tour_build, _tour_walls,
            TOUR_WINDOW, t3_every=4,
        )
        self.assertGreaterEqual(len(lockstep.facts), TOUR_WINDOW // 4)
        searched = skill_unknown = 0
        for step, reference, captured in lockstep.facts:
            with self.subTest(step=step):
                self.assertEqual(sorted(captured), sorted(reference))
                self.assertEqual(
                    json.loads(json.dumps(_without_timing(captured), default=str)),
                    json.loads(json.dumps(_without_timing(reference), default=str)),
                )
                equipment = captured["equipment_optimization"]
                searched += (
                    equipment.get("catalog_items", 0) > 0
                    and "band_descent" in equipment
                )
                skill_unknown += "skill-exp-unknown" in equipment.get("blockers", ())
        # Not vacuous: the sampled captures include the protocol-3 board whose
        # ~f values are unknown and boards carrying a real optimizer search.
        self.assertGreater(searched, 0)
        self.assertGreater(skill_unknown, 0)


if __name__ == "__main__":
    unittest.main()
