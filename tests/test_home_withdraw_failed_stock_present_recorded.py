"""Recorded pin: a Home take that moved the shovel's address is not a failure.

Live incident 2026-09-25 17:29-17:30 (bot process resumed at 17:29:14 onto a
game waiting on its Home page; 66 decisions): preparing a mining run (Word of
Recall 9/10 with no supplier, so ``town:recall-stockout-mining``), the town
needed two digging tools and one Treasure Detection scroll.  The complete
``~9`` catalogue requested at sequence 26 (130 items) held the Treasure Detection stack
(27) at index 11, the ``シャベル (1d2) (+0,+0) (+1) {+掘}`` stack (2) at index
114 and the Healing potions (3) at index 3.  Sequence 32 took one
scroll ('5pl1\\r', index 11) -- its message and the pack (18 -> 19) confirm it
on the sequence-33 board.  From there:

- 33 ``town:entrance-step-off:home:atomic-withdraw-target-unobserved`` and
  the just-taken scroll deferred as ``unobserved-home-withdrawal``;
- 36 the same for the shovel (batch head);
- 39 the Healing potions taken at 'd' (index 3, still addressable);
- 46/47 the shovel's one deferred retry deferred again, unobserved;
- 64/65 the Home-first gate found the only viable digging tool deferred with
  its retry spent: ``town:blocked:home-withdraw-failed-stock-present``.
No decision ever posted a take of the shovel.

Root cause (reproduced below): ``_confirm_home_withdrawal_address`` treats the
take at index 11 as a removal and shortens the addressable prefix to 11; it
asks for a fresh scan only when *every* other owner lies at or beyond 11, and
the potions at 3 kept the prefix alive.  The shovel at 114 stayed catalogued
but unaddressable, and the atomic composer read "catalogued beyond the
prefix" as "target unobserved" -- a failed withdrawal.  (A take of one of 27
did not even move the shelf; the prefix rule is conservative.)  The scroll
itself, still the pending item because carried-item processing waits during
the mining preparation, was re-read the same way although its take had been
observed.  Not the resume inside Home (14fe7a19): the attach page only started
the visit, decisions 0..32 are decided as live, and the fault needs a
confirmed take in the same catalogue generation.

Fix: an owner catalogued at or beyond the shortened prefix earns a fresh scan
instead of a deferral; the pending item whose own take was confirmed is
released as complete (neither deferred nor taken again) unless a new request
queues it.  Class tests: tests/test_home_withdraw_moved_address.py.

Substrate (tests/extract_home_withdraw_failed_stock_present_fixture.py): the
input rows of decisions 0..33 and the recorded facts of all 66, replayed
through the public response path on one policy.  Walls, each declared:
- the calibration file is the one the process loaded, in a temporary
  directory with the Home history/disposal files;
- the board of every decision that follows a posted key carries the live
  input executor's ``_completed_operation_sequence``/``_owner``;
- observer (no behaviour): on decision 33, ``_confirm_home_withdrawal_address``
  is wrapped to record the address state it leaves; it calls through;
- continuation (constructed, after the fixed decision 33): the fresh ``~9``
  catalogue is the recorded sequence-26 request's catalogue with exactly the observed
  take applied (Treasure Detection 27 -> 26; no other Home operation happened
  between 26 and 33), consumed through ``consume_home_knowledge`` (what the
  CLI calls for the requested ``~9`` response), and the composer is asked on
  the recorded sequence-33 entrance board.
The capture boards after 33 are the live bot's own path (step-off, Alchemist,
Temple); the fixed policy has left it at 33, so they are not fed.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence, _parse_items
from hengbot.model import SV_SCROLL_DETECT_TREASURE, TVAL_SCROLL
from hengbot.monrace_knowledge import load_monrace_knowledge

from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "home-withdraw-failed-stock-present-20260925.jsonl.gz"
CALIBRATION = FIXTURES / (
    "recall-read-cancel-pingpong-20260925.character-calibration.json"
)
FIXTURE_SHA256 = "041b395d5882c9eeee2232fb82ce98686bb955a0250b23f0c2f8c7b06330019a"
BOUNDARIES_SHA256 = (
    "fa25476f1f8ac7f4a18419a28dd1e6f8ddc8e33bcb9ce06aa03fe964df624eec"
)
CALIBRATION_SHA256 = (
    "b78abdb573ec899a735b60badc0dec52e4e66a04b22a054e928e2cc4b4450148"
)
SCROLL = ["財宝感知の巻物", 70, 26]
SHOVEL = ["シャベル (1d2) (+0,+0) (+1) {+掘}", 20, 1]
POTION = ["体力回復の薬 {25%引き}", 75, 37]
SCAN = 26  # requested the last complete ~9 catalogue before the take
SCAN_RESPONSE = 27  # whose input carries that response
TAKE = 32  # '5pl1\r\x1b': one Treasure Detection scroll, index 11
CONFIRM = 33  # the take is observed; the first step toward the stop
STOP = 65


class HomeWithdrawFailedStockPresentRecordedTest(unittest.TestCase):
    replay = None

    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        boundaries_path = FIXTURE.with_suffix(".boundaries.json")
        assert hashlib.sha256(boundaries_path.read_bytes()).hexdigest() == (
            BOUNDARIES_SHA256
        )
        assert hashlib.sha256(CALIBRATION.read_bytes()).hexdigest() == (
            CALIBRATION_SHA256
        )
        boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        fields = boundaries["recorded_fields"]
        cls.recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        cls.replayed = boundaries["replayed_decisions"]
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == sum(boundaries["input_rows"])
        assert len(cls.recorded) == STOP + 1 and cls.replayed == CONFIRM + 1
        cls.starts = [0]
        for count in boundaries["input_rows"]:
            cls.starts.append(cls.starts[-1] + count)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    @classmethod
    def _board_lines(cls, index):
        segment = cls.lines[cls.starts[index] : cls.starts[index + 1]]
        previous = cls.recorded[index - 1] if index else None
        if index and previous["key"]:
            # Wall (executor binding): see the module docstring.
            row = json.loads(segment[-1])
            row["_completed_operation_sequence"] = previous["decision_sequence"]
            row["_completed_operation_owner"] = previous["reason"]
            segment = segment[:-1] + [json.dumps(row, ensure_ascii=False) + "\n"]
        return segment

    @classmethod
    def _scan_catalogue(cls):
        rows = [
            json.loads(line)
            for line in cls.lines[cls.starts[SCAN_RESPONSE] : cls.starts[SCAN_RESPONSE + 1]]
        ]
        (row,) = [
            row for row in rows
            if row.get("type") == "knowledge"
            and row["knowledge"].get("category") == "home"
        ]
        return list(_parse_items(row["knowledge"]["items"]))

    @classmethod
    def _replay(cls):
        """Decisions 0..33 on one policy, then the constructed continuation."""
        if cls.replay is not None:
            return cls.replay
        decisions = []
        confirmed = {}
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy = _policy(directory, cls.monrace)
            policy._character_calibration_path.write_bytes(
                CALIBRATION.read_bytes()
            )
            for index in range(cls.replayed):
                _decoded, snapshots = _consume_response_sequence(
                    cls._board_lines(index), policy, lambda _key: True,
                    cls.monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                board = snapshots[-1]
                if index == CONFIRM:
                    # Observer only: record the address state the confirmed
                    # take leaves behind, before the composer reads it.
                    confirm = policy._confirm_home_withdrawal_address

                    def observed_confirm(signature, posted_index):
                        confirm(signature, posted_index)
                        confirmed.update(
                            signature=signature,
                            index=posted_index,
                            valid_before=policy._home_knowledge_valid_before,
                            knowledge_current=policy._home_knowledge_current,
                            pending=policy._home_pending_item,
                            batch=list(policy._home_pending_batch),
                        )

                    with patch.object(
                        policy, "_confirm_home_withdrawal_address",
                        side_effect=observed_confirm,
                    ):
                        key = policy.choose_key(board)
                else:
                    key = policy.choose_key(board)
                decisions.append((str(key), policy.last_reason))
                policy.confirm_key_posted(key)
            after = {
                "pending": policy._home_pending_item,
                "batch": list(policy._home_pending_batch),
                "deferred": set(policy._deferred_home_items),
                "digger_failures": policy._digger_home_withdraw_failures,
                "knowledge_current": policy._home_knowledge_current,
                "knowledge_invalidated": policy._home_knowledge_invalidated,
            }
            # Wall (continuation): see the module docstring.
            catalogue = cls._scan_catalogue()
            (scroll_index,) = [
                index for index, stored in enumerate(catalogue)
                if (stored.tval, stored.sval)
                == (TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE)
            ]
            catalogue[scroll_index] = replace(
                catalogue[scroll_index], count=catalogue[scroll_index].count - 1
            )
            policy.consume_home_knowledge(tuple(catalogue))
            next_board = replace(board, turn=board.turn + 1)
            continuation_key = policy._atomic_home_withdraw_key(
                next_board, next_board.player.position
            )
            continuation = {
                "key": continuation_key,
                "reason": policy.last_reason,
                "telemetry": dict(policy._home_atomic_withdraw_telemetry),
                "scroll": (scroll_index, catalogue[scroll_index].count),
                "catalogue": [
                    list(policy._item_signature(stored)) for stored in catalogue
                ],
                "deferred": set(policy._deferred_home_items),
                "digger_failures": policy._digger_home_withdraw_failures,
            }
        cls.replay = {
            "decisions": decisions,
            "confirmed": confirmed,
            "after": after,
            "continuation": continuation,
        }
        return cls.replay

    # ------------------------------------------------------------ recorded
    def test_recorded_stop_followed_a_confirmed_take_never_a_shovel_take(self):
        recorded = self.recorded
        take, confirm, stop = recorded[TAKE], recorded[CONFIRM], recorded[STOP]
        self.assertEqual(
            (take["key"], take["reason"], take["withdraw_selected_signature"],
             take["withdraw_resolved_index"], take["withdraw_resolved_letter"]),
            ("5pl1\r\x1b", "home:atomic-withdraw", SCROLL, 11, "l"),
        )
        # The take was observed: its message and the pack grew by one.
        self.assertEqual(confirm["messages"], ["財宝感知の巻物(k)を取った。"])
        self.assertEqual(
            (take["inventory_used"], confirm["inventory_used"]), (18, 19)
        )
        self.assertEqual(
            (confirm["key"], confirm["reason"]),
            ("6", "town:entrance-step-off:home:atomic-withdraw-target-unobserved"),
        )
        self.assertEqual(confirm["deferred_home_item_signatures"], [SCROLL])
        shovel_deferrals = [
            row["decision_sequence"]
            for row in recorded
            if row["reason"]
            == "town:entrance-step-off:home:atomic-withdraw-target-unobserved"
            and SHOVEL in (row["deferred_home_item_signatures"] or [])
            and SHOVEL not in (
                recorded[row["decision_sequence"] - 1][
                    "deferred_home_item_signatures"
                ] or []
            )
        ]
        self.assertEqual(shovel_deferrals, [36, 47])
        # Only the scroll, the Speed potions, the Weapon Damage scroll and the
        # Healing potions were ever taken; never the shovel.
        self.assertNotIn(
            SHOVEL,
            [row["withdraw_selected_signature"] for row in recorded],
        )
        self.assertEqual(recorded[39]["withdraw_selected_signature"], POTION)
        self.assertEqual(
            (stop["key"], stop["reason"], stop["home_gate_branch"]),
            ("2", "town:blocked:home-withdraw-failed-stock-present",
             "wrapper-withdraw-failed-stock-present"),
        )
        self.assertEqual(
            stop["home_gate_deferred_matches"],
            [{"identity": SHOVEL, "site": "unobserved-home-withdrawal"}],
        )
        self.assertTrue(stop["home_gate_deferred_retry"]["fresh_attempt_failed"])

    # ------------------------------------------------------------ fidelity
    def test_replay_reproduces_the_process_up_to_the_confirmed_take(self):
        decisions = self._replay()["decisions"]
        self.assertEqual(
            decisions[:CONFIRM],
            [(row["key"], row["reason"]) for row in self.recorded[:CONFIRM]],
        )

    def test_the_take_shortened_the_prefix_past_the_shovel(self):
        """On the confirming board: owners on both sides of index 11."""
        replay = self._replay()
        confirmed, continuation = replay["confirmed"], replay["continuation"]
        # The confirmed take of the pending scroll at index 11 left the
        # catalogue current, addressable only below 11 ...
        self.assertEqual(
            (list(confirmed["signature"]), confirmed["index"]), (SCROLL, 11)
        )
        self.assertEqual(confirmed["valid_before"], 11)
        self.assertTrue(confirmed["knowledge_current"])
        # ... with the scroll still pending and the shovel queued behind it.
        self.assertEqual(list(confirmed["pending"]), SCROLL)
        self.assertEqual(
            [list(signature) for signature in confirmed["batch"]],
            [SHOVEL, POTION],
        )
        catalogue = continuation["catalogue"]
        self.assertEqual(
            [catalogue.index(SCROLL), catalogue.index(SHOVEL),
             catalogue.index(POTION)],
            [11, 114, 3],
        )

    # ------------------------------------------------------------ W1
    def test_w1_confirming_board_rescans_instead_of_deferring(self):
        """Fixed: decision 33 enters Home for a fresh ~9, nothing is deferred."""
        replay = self._replay()
        self.assertEqual(
            replay["decisions"][CONFIRM], ("5", "shop:travel:await-entry")
        )
        after = replay["after"]
        self.assertFalse(after["knowledge_current"])
        self.assertTrue(after["knowledge_invalidated"])
        self.assertEqual(after["deferred"], set())
        self.assertEqual(after["digger_failures"], 0)
        # The scroll's withdrawal is complete; the shovel and the potions
        # remain queued Home work.
        self.assertIsNone(after["pending"])
        self.assertEqual(
            [list(signature) for signature in after["batch"]], [SHOVEL, POTION]
        )

    def test_w1_after_the_rescan_the_shovels_are_taken(self):
        continuation = self._replay()["continuation"]
        self.assertEqual(continuation["scroll"], (11, 26))
        telemetry = continuation["telemetry"]
        self.assertEqual(telemetry["selected_signature"], SHOVEL)
        self.assertEqual(
            (telemetry["resolved_index"], telemetry["resolved_page"],
             telemetry["resolved_letter"], telemetry["quantity"]),
            (114, 2, "k", 2),
        )
        self.assertEqual(continuation["key"], "5  pk2\r\x1b")
        self.assertEqual(continuation["reason"], "home:atomic-withdraw")
        self.assertEqual(continuation["deferred"], set())
        self.assertEqual(continuation["digger_failures"], 0)


if __name__ == "__main__":
    unittest.main()
