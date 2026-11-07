"""n1-b life-338 2026-11-07: one Musashi piece refused every calibration.

n1-b (Lv34 Magic-Eater) wields ★二天一流開祖宮本武蔵の脇差し in main_hand and
a small metal shield in sub_hand.  derive_equipped_calibration refused any
worn item whose name held 武蔵 / 二天 / クイック / ... ("unsupported-ac-set"),
so the equipment optimizer answered calibration-required, and the picked-up
★ロヒアリムの金属製ブリガンダイン・アーマー {+腕器r酸電火冷乱轟沌} (resist
chaos, required from 31F) went to Home unevaluated (20:15:47
home:atomic-deposit).  The game adds set AC only for a complete set
(player-status.cpp calc_ac / set_musasi: MUSASI_KATANA in INVEN_MAIN_HAND and
MUSASI_WAKIZASI in INVEN_SUB_HAND; likewise QUICKTHORN+TINYTHORN and
ICINGDEATH+TWINKLE); one piece alone has no set effect.

Recorded: the 20:38:56 town-arrival checkpoint (the armor on the Home shelf,
the arrival policy holding the previous dump's "unsupported-ac-set"
rejection) and its journal rows 0-43 (tests/extract_set_ac_1107_fixture.py).
Row 42 posts the departure character dump; row 43 decides on its C response.

DECLARED CONSTRUCTED: (1) the dump file the game wrote at row 42 is not
recorded; the character dump captured at the arrival (same worn gear, same
level, the row-43 C response agrees with it) is written in its place.  (2) The
live process still held the preparation of its previous dump
(``_calibration_dump_prepared``, transient, dropped by the checkpoint); it is
restored from the recorded rejection's pending record.  (3) The full-set pins
change only the worn hands' ``artifact_id`` on the row-43 inputs and board.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.character_sheet import completed_ac_set
from hengbot.cli import _consume_response_sequence
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST
from replay_town_arrival import restore


FIXTURES = Path(__file__).with_name("fixtures") / "set-ac-1107"
DUMP_ROW = 43
ROHIRRIM = "★ロヒアリムの金属製ブリガンダイン・アーマー"
WAKIZASHI = 172  # FixedArtifactId::MUSASI_WAKIZASI
KATANA = 171  # FixedArtifactId::MUSASI_KATANA


def _journal() -> list[dict]:
    return [json.loads(line) for line in
            lzma.decompress((FIXTURES / "journal.jsonl.xz").read_bytes()).splitlines()]


class SetAc1107RecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.journal = _journal()
        cls.sidecars = json.loads(lzma.decompress((FIXTURES / "sidecars.json.xz").read_bytes()))

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def restore(self):
        visit = self.scratch / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((FIXTURES / "policy.pkl.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(
            json.dumps(self.sidecars["manifest"]), encoding="utf-8")
        (visit / SIDECAR_DIRECTORY).mkdir()
        for role, text in self.sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(text.encode("latin-1"))
        runtime = self.scratch / "runtime"
        runtime.mkdir()
        return restore(visit, runtime)

    def decide(self, policy, row, transform=lambda state: state):
        entry = self.journal[row]
        inputs = [json.dumps(transform(json.loads(line)), ensure_ascii=False) + "\n"
                  for line in entry["inputs"]]
        _consume_response_sequence(inputs, policy, lambda _key: True, policy._monrace_knowledge,
                                   parse_snapshots=False,
                                   knowledge_ledger_path=self.scratch / "knowledge.jsonl")
        line = entry["line"] if entry["line"] is not None else entry["inputs"][-1]
        for name, value in entry["cli_latches"].items():
            setattr(policy, name, tuple(value) if isinstance(value, list) else value)
        policy.observe_store_screen(entry["store_screen_verified"])
        board = parse_snapshot(transform(json.loads(line)), policy._monrace_knowledge)
        return board, policy.choose_key(board)

    @staticmethod
    def post(policy, key):
        """Acknowledge a posted key as town_work_corpus.replay_window does."""
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def to_dump_row(self, transform=lambda state: state):
        """Replay rows 0-42 unchanged, then decide row 43 on the dump."""
        policy = self.restore()
        pending, reason = policy._calibration_rejection
        self.assertEqual(reason, "unsupported-ac-set")
        # DECLARED CONSTRUCTED (2): the live process's dump preparation.
        policy._calibration_dump_prepared = {
            "baseline": pending["baseline"], "started_ns": pending["started_ns"]}
        for row in range(DUMP_ROW):
            _board, key = self.decide(policy, row)
            self.assertEqual((key, policy.last_reason),
                             (self.journal[row]["key"], self.journal[row]["reason"]), row)
            self.post(policy, key)
        # DECLARED CONSTRUCTED (1): the dump the row-42 macro wrote.
        time.sleep(0.01)
        policy._character_dump_path.write_bytes(
            self.sidecars["files"]["_character_dump_path"].encode("latin-1"))
        board, key = self.decide(policy, DUMP_ROW, transform)
        return policy, board, key

    @staticmethod
    def hands(main_id, sub_id):
        def transform(state):
            for item in state.get("equipment") or ():
                if item.get("slot") == "main_hand":
                    item["artifact_id"] = main_id
                elif item.get("slot") == "sub_hand":
                    item["artifact_id"] = sub_id
            return state
        return transform

    def test_recorded_hands_hold_one_musashi_piece(self):
        policy = self.restore()
        line = json.loads(self.journal[DUMP_ROW]["line"])
        hands = {item["slot"]: (item.get("artifact_id"), item["tval"])
                 for item in line["equipment"] if item["slot"] in ("main_hand", "sub_hand")}
        self.assertEqual(hands, {"main_hand": (WAKIZASHI, 23), "sub_hand": (None, 34)})
        self.assertEqual(policy._calibration_unavailable_reason, "unsupported-ac-set")

    def test_wakizashi_alone_calibrates_and_wears_the_chaos_armor(self):
        policy, board, key = self.to_dump_row()
        self.assertIsNone(completed_ac_set(board.equipment))
        self.assertIsNotNone(policy._character_calibration,
                             policy._calibration_unavailable_reason)
        self.assertIsNone(policy._calibration_unavailable_reason)
        # Recorded live: town:armor-smith:travel with calibration refused.
        self.assertEqual((key, policy.last_reason),
                         ("\x1b`n(.", "equipment-transaction:travel-home"))
        preparation = policy._equipment_optimization_preparation
        self.assertEqual(preparation.blockers, ())
        names = {owned.id: owned.item.name for owned in policy._equipment_catalog.items}
        actions = [(action.kind, names.get(action.item_id, ""))
                   for action in preparation.transaction.actions]
        self.assertIn("withdraw", [kind for kind, name in actions if name.startswith(ROHIRRIM)])
        self.assertIn("equip", [kind for kind, name in actions if name.startswith(ROHIRRIM)])
        worn = dict((slot, owned.item.name) for slot, owned in preparation.result.best.loadout.slots)
        self.assertTrue(worn["body"].startswith(ROHIRRIM), worn["body"])
        self.assertIn("宮本武蔵の脇差し", worn["main_hand"])

    def test_complete_musashi_set_still_refuses_calibration(self):
        """Katana in main_hand and wakizashi in sub_hand complete set_musasi."""
        policy, board, key = self.to_dump_row(self.hands(KATANA, WAKIZASHI))
        self.assertEqual(completed_ac_set(board.equipment), (KATANA, WAKIZASHI))
        self.assertIsNone(policy._character_calibration)
        self.assertEqual(policy._calibration_unavailable_reason, "unsupported-ac-set")
        self.assertEqual((key, policy.last_reason),
                         (self.journal[DUMP_ROW]["key"], self.journal[DUMP_ROW]["reason"]))

    def test_musashi_pieces_in_swapped_hands_are_no_set(self):
        """set_musasi requires the katana in INVEN_MAIN_HAND; swapped hands
        give no set AC, so the calibration proceeds."""
        policy, board, _key = self.to_dump_row(self.hands(WAKIZASHI, KATANA))
        self.assertIsNone(completed_ac_set(board.equipment))
        self.assertIsNotNone(policy._character_calibration,
                             policy._calibration_unavailable_reason)


if __name__ == "__main__":
    unittest.main()
