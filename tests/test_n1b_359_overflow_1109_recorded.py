"""n1-b (Magic-Eater) life-359 2026-11-09 20:20-20:21: three overflow stops in town.

Recorded: tests/fixtures/n1b-359-overflow-1109/
(tests/extract_n1b_359_overflow_1109_fixture.py), the town-arrival checkpoint of
the first of the three ``town:blocked:overflow-no-legal-disposal`` stops (build
a0b7b8e7b, arrival turn 3365213).  Every decision is the public ``choose_key``.

The life recalled with a full pack (23/23): the supplies, the Stone to Mud
stack, the mana food, two bolt stacks and eleven unidentified pickups (six
wands and staffs, five pieces of armour and weapons).  Home took the scythe
and the Short Teleport scrolls (21/23); every remaining stack was either
reserved or an unidentified piece the identify-first rule protects (owner
2026-10-20 「拾って鑑定したあと不要であれば壊す」).

The absorbed Identify (owner 2026-10-30 「以降、鑑定と財宝感知は取り込みで賄う」)
was listed and reliable, and the town item processor composes it first
(``_carried_identify_command`` -> ``_absorbed_identify_key``).  Its terminal
admission (town_terminal ``gather_identify_carried``) asked the carried scroll
or staff only, refused the rung (no-identification-source) and requested a
scroll: the bot walked to the Alchemist, whose Identify scrolls the town pack
budget refused to carry at 21/23 (four free slots kept), and the overflow
rung found nothing legal to destroy.  The admission now asks the source tier
the body composes (``carried_source_held``, item_fate ``can_identify_now``).

DECLARED CONSTRUCTED (the continuation after row 9): the engine is the Home
fake of tests/test_n1b_q2_home_ammo_1109_recorded.py with the recorded Home
(the ~9 catalogue of row 9), plus the two commands the visit issues outside:
the absorbed Identify ('mAf' + item) lands -- the piece becomes known with
plain values (+0,+0), its base values as carried -- and destroy ('k' + item)
removes the stack.  The drive ends when the pack holds its four free slots.
The identified rag and robe are plain armour the optimizer did not select and
have no special property: owner 2026-11-09 「耐性の無い素の防具は不要」 makes them
junk, destroyed rather than shelved (the recorded build shelved them: the worn
ego body armour's (-1) to-hit outranked their 0 in the dominance comparison).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import lzma
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.cli import _consume_response_sequence, _ExecutorInputPort, _send_new_decision_key
from hengbot import me_capability
from hengbot.home_disposal import HOME_HISTORY_DIR_ENV
from hengbot.me_staff_sequence import identify_power_command
from hengbot.model import SV_STAFF_IDENTIFY, parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import MIN_TERMINAL_FREE_PACK_SLOTS, PACK_CAPACITY
from hengbot.runtime_paths import RUNTIME_DIR_ENV
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST)
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from tests import test_input_executor as executor_pins
from tests.test_magic_eater_o3 import prompt
from tests.test_me_staff_sequence import power_list
from tests.test_n1b_q2_home_ammo_1109_recorded import MergingHomeGame

FIXTURES = Path(__file__).with_name("fixtures") / "n1b-359-overflow-1109"
CAST_ROW = 9
STOP_ROW = 13
STOP = "town:blocked:overflow-no-legal-disposal"
POWER_PROMPT = "('*'で一覧, ESCで中断) どの魔力を使いますか？"
PIECES = ["汚れたボロ服 [1]", "ローブ [2]", "鉄ヘルメット [5]", "セスタス [5]",
          "トライデント (1d8)"]


class IdentifyingHomeGame(MergingHomeGame):
    """DECLARED CONSTRUCTED (module docstring): Home plus 'mAf'+item and 'k'+item.

    The cast asks cmd-magiceat.cpp's questions in turn: the kind (command_char),
    the power (spell; '*' lists the record row of the arrival's power list) and
    the item to identify (item, the pack labels).
    """
    me_stage = None
    power_row = None

    def _consume(self, keys):
        for key in keys:
            if self.me_stage is not None:
                self.trace.append(key)
                self._me_key(key)
            elif self.inside or self.pending is not None or self.modal is not None:
                super()._consume(key)
            elif key == "m":
                self.trace.append(key)
                self.me_stage = "kind"
            elif key == "k":
                self.trace.append(key)
                self.me_stage = "destroy"
            else:
                super()._consume(key)

    def _me_key(self, key):
        stage, self.me_stage = self.me_stage, None
        if key == "":
            return
        if stage == "kind" and key == "A":
            self.me_stage = "power"
        elif stage == "power" and key == "*":
            self.me_stage = "power-list"
        elif stage in {"power", "power-list"} and key == "f":
            self.me_stage = "identify"
        elif stage == "identify":
            self._identify(key)
        elif stage == "destroy":
            self._destroy(key)
        else:
            raise AssertionError(f"unexpected Magic-Eater key {key!r} at {stage}")

    def request(self, request):
        if request["op"] == "screen" and self.queued:
            queued, self.queued = self.queued, ""
            self._consume(queued)
        if request["op"] == "screen" and self.me_stage is not None:
            screen = {
                "kind": lambda: prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
                "power": lambda: prompt(POWER_PROMPT, "spell"),
                "power-list": lambda: power_list(SV_STAFF_IDENTIFY, *self.power_row),
                "identify": lambda: prompt(
                    "どのアイテムを鑑定しますか? ", "item", area="inventory",
                    areas=["inventory"], menu=False, first_label="a",
                    last_label=chr(96 + len(self.pack))),
            }.get(self.me_stage)
            if screen is not None:
                return {"id": request["id"], "ok": True, "result": screen()}
        return super().request(request)

    def _pack_item(self, letter):
        return self.pack[ord(letter) - ord("a")]

    def _identify(self, letter):
        item = self._pack_item(letter)
        for name, value in dict(charging=False, charges=0, to_h=0, to_d=0, to_a=0, pval=0,
                                known_flags=[], is_cursed=False, is_broken=False).items():
            if item.get(name) is None:
                item[name] = value
        item["known"] = True
        self.power_row = (self.power_row[0] - 1, self.power_row[1])
        self.identified.append(item["name"])
        self.message = ""
        self.turn += 1

    def _destroy(self, letter):
        item = self._pack_item(letter)
        self.pack.remove(item)
        self.destroyed.append(item["name"])
        self.message = ""
        self.turn += 1


class N1b359Overflow1109RecordedTest(executor_pins.ProductionHarness):

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        for name in ("runtime-env", "history-env", "runtime"):
            (self.scratch / name).mkdir()
        env = mock.patch.dict(os.environ, {
            RUNTIME_DIR_ENV: str(self.scratch / "runtime-env"),
            HOME_HISTORY_DIR_ENV: str(self.scratch / "history-env")})
        env.start()
        self.addCleanup(env.stop)

    def visit(self):
        visit = self.scratch / "town-arrival"
        (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((FIXTURES / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((FIXTURES / "journal.jsonl.xz").read_bytes())))
        sidecars = json.loads(lzma.decompress((FIXTURES / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(json.dumps(sidecars["manifest"]), encoding="utf-8")
        for role, text in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(text.encode("latin-1"))
        return visit

    def arrival(self):
        visit, runtime = self.visit(), self.scratch / "runtime"
        policy = restore(visit, runtime)
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path",
                          runtime)
        return policy, decisions(policy, visit, runtime), journal(visit)

    @staticmethod
    def post(policy, key):
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def to_row(self, last):
        """Rows before ``last`` decide as recorded; ``last``'s board is returned undecided."""
        policy, rows, entries = self.arrival()
        for recorded, supply in rows:
            board = supply()
            if recorded["row"] == last:
                return policy, board, entries
            key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason),
                             (recorded["key"], recorded["reason"]), recorded["row"])
            self.post(policy, key)
        self.fail("the journal ends early")

    @staticmethod
    def raw(entries, row):
        entry = entries[row]
        return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])

    @staticmethod
    def unknown_pieces(board):
        return [item.name for item in board.inventory
                if item.is_equipment and not item.is_ammo and not item.known]

    def test_recorded_visit_walked_for_a_scroll_and_stopped(self):
        policy, board, entries = self.to_row(CAST_ROW)
        self.assertEqual(len(board.inventory), 21)
        self.assertEqual(self.unknown_pieces(board), PIECES)
        # Every stack is reserved or protected until identified: nothing is legal to destroy.
        self.assertTrue(all(policy._item_is_procurement_protected(board, item)
                            for item in board.inventory))
        piece = next(item for item in board.inventory if item.name == PIECES[0])
        self.assertEqual(identify_power_command(policy, board, piece, full=False),
                         "mAf" + piece.slot)
        recorded = [(entry["key"], entry["reason"]) for entry in entries[CAST_ROW:]]
        self.assertEqual(recorded, [
            ("\x1b`n%.", "shop:travel"),
            ("\x1b", "town-progress-invariant:continue-observed-shop"),
            ("\x1b`n$.", "shop:travel"),
            ("\x1b", "town-progress-invariant:continue-observed-shop"),
            ("1", STOP)])
        alchemist = self.raw(entries, 10)["store"]
        self.assertEqual(alchemist["store_type"], 4)
        self.assertIn("鑑定の巻物", [item["name"] for item in alchemist["items"]])
        stop = self.raw(entries, STOP_ROW)
        self.assertEqual(len(stop["inventory"]), 21)
        self.assertLess(PACK_CAPACITY - len(stop["inventory"]), MIN_TERMINAL_FREE_PACK_SLOTS)

    def test_absorbed_identify_identifies_and_the_pack_is_freed(self):
        policy, board, entries = self.to_row(CAST_ROW)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("mAfo", "identify:normal"))
        # DECLARED CONSTRUCTED (module docstring): the Home of row 9's ~9 catalogue.
        catalogue = [json.loads(line) for line in entries[CAST_ROW]["inputs"]
                     if '"knowledge"' in line][-1]
        knowledge = catalogue["knowledge"]["items"]
        shelf = [{k: v for k, v in item.items() if k != "slot"} for item in knowledge]
        home_page = self.raw(entries, 7)
        self.assertEqual(len(shelf), home_page["store"]["stock_num"])
        outside = self.raw(entries, CAST_ROW)
        game = IdentifyingHomeGame(
            pack=copy.deepcopy(outside["inventory"]),
            equipment={item["slot"]: item for item in copy.deepcopy(outside["equipment"])},
            pages=[shelf[index:index + 52] for index in range(0, len(shelf), 52)],
            inside=False, state_template=copy.deepcopy(outside),
            home_limit=home_page["store"]["capacity"])
        game.identified, game.destroyed = [], []
        row = me_capability.observed_row(policy, "staff", SV_STAFF_IDENTIFY)
        game.power_row = (row["current"], row.get("max") or row["current"])
        game.entrance = (home_page["player"]["y"], home_page["player"]["x"])
        game.position = (outside["player"]["y"], outside["player"]["x"])
        game.turn = outside["turn"]
        _, _, executor = self.make(game)
        executor.drain = lambda: [game._state()]
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 5).outcome,
                         "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2,
                                  policy=policy)
        reasons = [(key, policy.last_reason)]
        current = board
        for _ in range(20):
            _send_new_decision_key(
                port, json.dumps(game._state()), key, None, set(),
                in_store=current.store is not None, snapshot=current,
                decision={"sequence": policy._decision_sequence,
                          "reason": policy.last_reason, "key": key})
            self.assertEqual(port.last_result.outcome, "completed",
                             (reasons, port.last_result.reason))
            self.post(policy, key)
            if "request-knowledge" in policy.last_reason:
                # DECLARED CONSTRUCTED: the ~9 answer, the engine's shelf in the
                # recorded catalogue line of row 9.
                answer = copy.deepcopy(catalogue)
                answer.update({k: v for k, v in game._state().items()
                               if k in {"turn", "inventory", "equipment", "messages"}})
                answer["knowledge"]["items"] = [dict(item, slot=index) for index, item
                                                in enumerate(copy.deepcopy(game._items()))]
                _consume_response_sequence([json.dumps(answer) + "\n"], policy,
                                           lambda _key: True, policy._monrace_knowledge,
                                           parse_snapshots=False,
                                           knowledge_ledger_path=self.scratch / "k.jsonl")
            current = parse_snapshot(port.last_result.board, policy._monrace_knowledge)
            if PACK_CAPACITY - len(current.inventory) >= MIN_TERMINAL_FREE_PACK_SLOTS:
                break
            key = policy.choose_key(current)
            reasons.append((key, policy.last_reason))
            self.assertFalse(policy.last_reason.startswith("town:blocked"), reasons)
        # The pieces are identified by the absorbed power where they lie (no
        # scroll trip, no Alchemist) and, plain armour the optimizer did not
        # select and without a special property, destroyed (owner 2026-11-09
        # 「耐性の無い素の防具は不要」; not shelved at Home) until the pack keeps
        # its four free slots again.
        self.assertEqual(PACK_CAPACITY - len(current.inventory), MIN_TERMINAL_FREE_PACK_SLOTS)
        self.assertEqual(game.identified, PIECES[:2])
        self.assertEqual([k for k, reason in reasons if reason == "identify:normal"],
                         ["mAfo"] * 2)
        self.assertNotIn("shop:travel", [reason for _key, reason in reasons], reasons)
        self.assertEqual(game.destroyed, PIECES[:2])
        self.assertEqual([key[-2:] for key, reason in reasons
                          if reason == "inventory:destroy-worthless-junk"], ["ko"] * 2)
        self.assertFalse([item["name"] for item in game._items() if item["name"] in PIECES])
        self.assertEqual(self.unknown_pieces(current), PIECES[2:])

    def test_plain_armour_with_a_resist_is_kept(self):
        """Owner 2026-11-09: only plain armour without a special property is not needed.

        DECLARED CONSTRUCTED: the row-9 board after the absorbed Identify of the
        rag landed (known, +0); the control gives it one resist (the worn ego
        body armour's 62).
        """
        policy, board, entries = self.to_row(CAST_ROW)
        key = policy.choose_key(board)
        self.assertEqual(key, "mAfo")
        self.post(policy, key)
        raw = self.raw(entries, CAST_ROW)
        rag = next(item for item in raw["inventory"] if item["slot"] == "o")
        for name, value in dict(charging=False, charges=0, to_h=0, to_d=0, to_a=0, pval=0,
                                known_flags=[], is_cursed=False, is_broken=False).items():
            if rag.get(name) is None:
                rag[name] = value
        rag["known"] = True
        raw["turn"] += 10
        raw["messages"] = []
        plain = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        piece = next(item for item in plain.inventory if item.slot == "o")
        self.assertEqual(policy._junk_class(plain, piece), "plain-gear")
        rag["known_flags"] = [62]
        resisting = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        piece = next(item for item in resisting.inventory if item.slot == "o")
        self.assertIsNone(policy._junk_class(resisting, piece))


if __name__ == "__main__":
    unittest.main()
