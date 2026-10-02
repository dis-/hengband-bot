"""Recorded pin: a composed one-shot buy is not retired by another shelf's work.

Live stops 2026-10-02 09:03:33, 09:04:14 and 09:27:34
(``town:blocked:owner-retired``, identical tails; commit a96480df,
``--enforce-crossarea-fundraising``, S3.3 switch off).  The 09:03:38 process
of the 09:04:14 stop is frozen by tests/extract_oneshot_preempt_fixture.py:

- 7: Home ``home:atomic-withdraw`` (``5 pW13``).
- 8: the Home plan stop resolves as ``shop:observed-operation-uncomposable``
  (policy_observation.py ``_resolve_observed_uncomposable_stop``, Home
  branch) and steps off the entrance.  The reason belongs to the shop-buy
  family (``shop:observe`` prefix, tests/fixtures/t1-reason-attribution.json),
  so the arbiter counts (shop-buy, durable vector) once.
- 9, 10: travel ``#`` (store 2, Weapon Smith); the observation-only page
  leaves (policy.py ``shop:observe-and-leave``), relabelled
  ``town-progress-invariant:continue-observed-shop`` because the page holds
  a wanted, affordable purchase (鉄弾, letter l, 3 gold, ammo 90/99).
- 11: outside, the one-shot is composed from that page: dispatch ``5``,
  bound tail ``pl9\\r\\r\\x1b``.  Gold and pack are unchanged since 8, and
  shop-buy's progress vector carried only durable facts, so this was the
  second (shop-buy, vector) occurrence: recurrence -> retired at its own
  entry, and the retirement closed the one-shot visit with its tail.
- 12: the store page the ``5`` opened is a recovered observation visit;
  it leaves again.  13..17: travel ``$`` (store 3, Temple), the same leave,
  and with shop-buy still recurrent no recall one-shot can be composed; the
  router's ``shop:travel:await-entry`` ``5`` enters twice and the page
  leaves twice.  18: ``town:blocked:owner-retired``.

Fix: shop-buy's progress vector names the shelf it acts on (the open page,
else the decision's store visit, else the observed page, else the approached
store), as the store router's names its walk.  The Home step-off and the
Weapon Smith one-shot are different work; repeats on one shelf still recur.

Walls (declared): ``PRE_FIX`` replays with the shelf part removed (the
pre-fix vector) and reproduces every live key 0..18.  The Temple pin replays
0..14 behind that wall (with the fix, 12 diverges and no later board is the
effect of the fixed key, R4), then decides 15 and 16 with the fix.  Key 15
is ``5`` both live and fixed, so board 16 is the effect of the same key.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.model import STORE_HOME, STORE_TEMPLE, STORE_WEAPON
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import TOWN_TRAVEL_STORE_SYMBOLS

from test_esp_threat_rest_recorded import EDIT, _policy
from xbow_pref_walls import shelf_wall_on_replay

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "oneshot-preempt-20261002.jsonl.gz"
BOUNDARIES = FIXTURES / "oneshot-preempt-20261002.boundaries.json"
# The 09:03:38 process's calibration file was overwritten at 09:27; this is
# the 05:51 file (see tests/extract_oneshot_preempt_fixture.py).
CALIBRATION = FIXTURES / "overweight-home-hold-20261002.character-calibration.json"
SHA256 = {
    FIXTURE: "9a3360becb858ad132616f6635a483330e0cc766fa1bbf11d43e6ebac0fced05",
    BOUNDARIES: "b35e02946c08b9b5acd52ac5a5230760b826949dddc6c483a1d276f481674a51",
    CALIBRATION: "0b64f6942910ac432bda1e2c29a7347447d8842de63059628e6eb6f923e6c86e",
}
HOME_STEP_OFF = 8
WEAPON_PAGE = 10
ONE_SHOT = 11
WEAPON_REENTRY = 12
TEMPLE_PAGE = 14
TEMPLE_ENTRY = 15
TEMPLE_REENTRY = 16
STOP = 18
AMMO_TAIL = "pl9\r\r\x1b"
# Integration with overweight-home 81e314e8 (USER DECISION 2026-09-20: buy the
# recall target plus the scroll read at departure): the ledger now counts the
# departure scroll before the safe-landing switch, so the Temple buys 2.
RECALL_TAIL = "pl2\r\r\x1b"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _pre_fix_shelf(_self, _snapshot):
    return None


class OneShotPreemptRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        boundaries = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
        cls.boundaries = boundaries
        fields = boundaries["recorded_fields"]
        cls.recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        cls.detail = boundaries["detail"]
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            lines = stream.read().splitlines(keepends=True)
        assert len(lines) == sum(boundaries["input_rows"])
        cls.segments = []
        start = 0
        for count in boundaries["input_rows"]:
            cls.segments.append(lines[start:start + count])
            start += count
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _replay(self, last, *, pre_fix_through=-1, inspect=None):
        """Replay the frozen process through ``last`` on one policy."""
        rows = []
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy = _policy(directory, self.monrace)
            policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
            policy._crossarea_fundraising_enforced = True  # live argv
            for index in range(last + 1):
                _decoded, snapshots = _consume_response_sequence(
                    self.segments[index], policy, lambda _key: True, self.monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                board = snapshots[-1]
                if index <= pre_fix_through:
                    # create=True: the pre-fix source has no such seam.
                    with patch.object(HengbotPolicy, "_shop_buy_shelf_store",
                                      _pre_fix_shelf, create=True):
                        key = policy.choose_key(board)
                else:
                    key = policy.choose_key(board)
                rows.append((str(key), policy.last_reason))
                if inspect is not None:
                    inspect(index, policy, board)
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain(
                        {"outcome": "released", "posted": str(key)})
        return rows

    def _live(self, index):
        row = self.recorded[index]
        return row["key"], row["reason"]

    @staticmethod
    def _execution(policy):
        execution = (policy.decision_claim or {}).get("execution") or {}
        arguments = execution.get("arguments")
        return (execution.get("next_step"),
                list(arguments) if arguments is not None else None)

    # ------------------------------------------------------------ recorded
    def test_recorded_one_shot_retired_at_its_own_entry(self):
        # R1: the travel symbols name the stores the records name.
        self.assertEqual(TOWN_TRAVEL_STORE_SYMBOLS[STORE_WEAPON], "#")
        self.assertEqual(TOWN_TRAVEL_STORE_SYMBOLS[STORE_TEMPLE], "$")
        self.assertEqual(TOWN_TRAVEL_STORE_SYMBOLS[STORE_HOME], "(")
        self.assertEqual(self._live(HOME_STEP_OFF), (
            "6", "town:entrance-step-off:shop:observed-operation-uncomposable"))
        self.assertEqual(self.detail[str(HOME_STEP_OFF)]["arbiter"]["producer_owner"],
                         "shop-buy")
        page = self.detail[str(WEAPON_PAGE)]
        self.assertEqual(self._live(WEAPON_PAGE),
                         ("\x1b", "town-progress-invariant:continue-observed-shop"))
        self.assertEqual(page["store_type"], STORE_WEAPON)
        wanted = page["shop_selector"]["wanted_purchase"]
        self.assertEqual((wanted["category"], wanted["letter"], wanted["price"]),
                         ("ammo", "l", 3))
        self.assertTrue(wanted["name"].startswith("鉄弾 (1d3)"))
        self.assertEqual(page["shop_selector"]["rejection_reason"], "preempted")
        self.assertEqual(page["shop_selector"]["town_progress_invariant"]["allow_set"], [])
        one_shot = self.detail[str(ONE_SHOT)]
        self.assertEqual(self._live(ONE_SHOT), ("5", "shop:one-shot-buy"))
        self.assertEqual(one_shot["execution"]["arguments"], [STORE_WEAPON, AMMO_TAIL])
        self.assertEqual(
            {name: one_shot["arbiter"][name] for name in
             ("producer_owner", "progress", "budget_remaining_estimate", "retired",
              "retirement_set")},
            {"producer_owner": "shop-buy", "progress": False,
             "budget_remaining_estimate": 0, "retired": True,
             "retirement_set": ["shop-buy"]})
        reentry = self.detail[str(WEAPON_REENTRY)]
        self.assertEqual(self._live(WEAPON_REENTRY),
                         ("\x1b", "town-progress-invariant:continue-observed-shop"))
        self.assertEqual(reentry["store_visit"]["visit_origin"], "shop-handler-recovery")
        for index in (TEMPLE_ENTRY, 17):
            self.assertEqual(self._live(index), ("5", "shop:travel:await-entry"))
        for index in (TEMPLE_PAGE, TEMPLE_REENTRY):
            self.assertEqual(self.detail[str(index)]["store_type"], STORE_TEMPLE)
            self.assertEqual(self.detail[str(index)]["shop_selector"]
                             ["wanted_purchase"]["category"], "recall")
        self.assertEqual(self._live(STOP), ("5", "town:blocked:owner-retired"))

    @shelf_wall_on_replay  # declared wall: no 2026-10-02 crossbow swap (tests/xbow_pref_walls.py)
    def test_pre_fix_vector_reproduces_every_live_key(self):
        rows = self._replay(STOP, pre_fix_through=STOP)
        self.assertEqual(rows, [self._live(index) for index in range(STOP + 1)])

    # ------------------------------------------------------------ fix
    @shelf_wall_on_replay  # declared wall: no 2026-10-02 crossbow swap (tests/xbow_pref_walls.py)
    def test_weapon_smith_one_shot_keeps_its_tail_and_buys(self):
        seen = {}

        def inspect(index, policy, board):
            if index in (ONE_SHOT, WEAPON_REENTRY):
                telemetry = policy._town_turn_arbiter.telemetry or {}
                seen[index] = (
                    self._execution(policy),
                    telemetry.get("retired"), telemetry.get("progress"),
                    board.store.store_type if board.store is not None else None,
                    {item.letter: (item.name, item.price)
                     for item in board.store.items} if board.store is not None else None,
                )

        rows = self._replay(WEAPON_REENTRY, inspect=inspect)
        for index in range(WEAPON_REENTRY):
            self.assertEqual(rows[index], self._live(index), index)
        execution, retired, progress, store_type, _items = seen[ONE_SHOT]
        self.assertEqual(execution, ("shop.one-shot.dispatch", [STORE_WEAPON, AMMO_TAIL]))
        self.assertEqual((retired, progress, store_type), (False, True, None))
        # First changed key versus live (ESC continue-observed-shop): stop here.
        self.assertEqual(rows[WEAPON_REENTRY], (AMMO_TAIL, "shop:one-shot-buy"),
                         self._live(WEAPON_REENTRY))
        execution, retired, _progress, store_type, items = seen[WEAPON_REENTRY]
        self.assertEqual(execution, ("shop.one-shot.send", [STORE_WEAPON, AMMO_TAIL]))
        self.assertFalse(retired)
        self.assertEqual(store_type, STORE_WEAPON)
        self.assertTrue(items["l"][0].startswith("鉄弾 (1d3)"))
        self.assertEqual(items["l"][1], 3)

    @shelf_wall_on_replay  # declared wall: no 2026-10-02 crossbow swap (tests/xbow_pref_walls.py)
    def test_temple_entry_composes_and_releases_the_recall_purchase(self):
        seen = {}

        def inspect(index, policy, board):
            if index in (TEMPLE_ENTRY, TEMPLE_REENTRY):
                seen[index] = (
                    self._execution(policy),
                    board.store.store_type if board.store is not None else None,
                    {item.letter: (item.name, item.price)
                     for item in board.store.items} if board.store is not None else None,
                )

        rows = self._replay(TEMPLE_REENTRY, pre_fix_through=TEMPLE_PAGE,
                            inspect=inspect)
        for index in range(TEMPLE_ENTRY):
            self.assertEqual(rows[index], self._live(index), index)
        # Live posted the same key '5' as a router await-entry (no tail).
        self.assertEqual(self._live(TEMPLE_ENTRY), ("5", "shop:travel:await-entry"))
        self.assertEqual(rows[TEMPLE_ENTRY], ("5", "shop:one-shot-buy"))
        self.assertEqual(seen[TEMPLE_ENTRY][0],
                         ("shop.one-shot.dispatch", [STORE_TEMPLE, RECALL_TAIL]))
        # Board 16 is the effect of the same '5': the Temple page.  First
        # changed key versus live (ESC continue-observed-shop): stop here.
        execution, store_type, items = seen[TEMPLE_REENTRY]
        self.assertEqual(store_type, STORE_TEMPLE)
        self.assertEqual(items["l"], ("帰還の詔の巻物", 231))
        self.assertEqual(rows[TEMPLE_REENTRY], (RECALL_TAIL, "shop:one-shot-buy"),
                         self._live(TEMPLE_REENTRY))
        self.assertEqual(execution, ("shop.one-shot.send", [STORE_TEMPLE, RECALL_TAIL]))


if __name__ == "__main__":
    unittest.main()
