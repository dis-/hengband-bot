"""D34: a Library *Identify* batch stays inside the building (morivant-full-identify:library).

Viewing bot n1-a life-433 (2026-10-30 14:47) walked to
Morivant's Library to *Identify* two carried items and posted
``3al<ESC x8>an<ESC x9>``.  cmd-building.cpp: Escape in the building loop
leaves the building, and after identify_fully (spells-perception.cpp) only
screen_object's ``[何かキーを押すとゲームに戻ります]`` (identification.cpp)
waits for a key.  The second Escape therefore left the Library, the second
``a`` reached the command loop as Aim a wand (「どの魔法棒で狙いますか?」)
and the run stopped (stuck-prompt, ctx=item); n1-b life-256 stopped the same
way (``3ap...aq...``).  The first item was identified and paid for
($1300, gold 4156 -> 2856).

Substrate: the recorded raw state lines of the session tail
(tests/extract_d34_session_fixtures.py library) replayed through the public
chooser on one fresh policy with the live argv flags; the chosen key is
posted through the production executor port to a CONSTRUCTED interpreter of
the source paths above (Library letters a/h/i from 03_Morivant.jsonc; one
screen_object key per item; Escape and a space are no-ops at the command
loop).
"""

import tests  # noqa: F401 -- live runtime-file isolation
import copy
import gzip
import hashlib
import json
from pathlib import Path

from hengbot.cli import _ExecutorInputPort, _send_new_decision_key
from hengbot.monrace_knowledge import load_monrace_knowledge
from recorded_session_replay import replay_session
from test_esp_threat_rest_recorded import EDIT
import tests.test_input_executor as executor_harness

FIXTURE = Path(__file__).parent / "fixtures/morivant-library-identify-20261030.json.gz"
SHA256 = "c38b88034bb8977a22b87605a8e391f3dd31944208c8c225e38cde7b030ad59b"
PIN = 7692
LIBRARY = (41, 106)
WIDTH, HEIGHT = 213, 68


def library_screen(prompt=""):
    # CONSTRUCTED: building-service.cpp centered 80x24 menu (as
    # test_bounty_confirm_1026.building_screen), Morivant's Library letters.
    ox, oy = (WIDTH - 80) // 2, (HEIGHT - 24) // 2
    lines = [""] * HEIGHT
    lines[oy] = " " * ox + prompt
    lines[oy + 2] = " " * ox + " ミリムバー (ハイ=エルフ) 図書館"
    lines[oy + 19] = " " * ox + " a) アイテム調査 (1300)"
    lines[oy + 20] = " " * ox + " h) 街の概要"
    lines[oy + 21] = " " * ox + " i) アイテム鑑定 (100)"
    lines[oy + 23] = " " * ox + " ESC) 建物を出る"
    return {"width": WIDTH, "height": HEIGHT, "lines": lines,
            "cursor": {"visible": True, "x": ox, "y": oy}}


class LibraryHookGame(executor_harness.FaithfulHookGame):
    """CONSTRUCTED Library interpreter on the existing FIFO harness."""

    def __init__(self, board):
        super().__init__()
        self.state = copy.deepcopy(board)
        self.state["messages"] = []
        self.phase = "command"
        self.identified = []
        self.capacity = 64

    def _consume(self, *, pump_frontend=True):
        if pump_frontend:
            self.term_fifo.extend(self.frontend_fifo)
            self.frontend_fifo.clear()
        raw = "".join(self.term_fifo)
        self.term_fifo.clear()
        if not raw:
            return
        for key in raw:
            if self.phase == "command":
                if key == "3":
                    self.state["player"].update(y=LIBRARY[0], x=LIBRARY[1])
                    self.phase = "building"
                elif key == "a":
                    self.phase = "aim"  # cmd-item: Aim a wand
                else:
                    assert key in " \x1b", key
            elif self.phase == "building":
                if key == "a":
                    self.phase = "item"
                elif key == "\x1b":
                    self.phase = "command"
                    self.state["turn"] += 1
            elif self.phase == "item":
                item = next((it for it in self.state["inventory"] if it["slot"] == key), None)
                if item is not None:
                    item["fully_known"] = True
                    self.state["player"]["gold"] -= 1300
                    self.identified.append(key)
                self.phase = "object" if item is not None else "building"
            elif self.phase == "object":
                self.phase = "building"
            elif self.phase == "aim" and key == "\x1b":
                self.phase = "command"
        if self.phase == "command":
            self.screen = executor_harness.command_screen(self.state["turn"])
            self.jsonl.append(copy.deepcopy(self.state))
        elif self.phase == "aim":
            self.screen = executor_harness.prompt_screen("どの魔法棒で狙いますか?")
        elif self.phase == "item":
            self.screen = library_screen("どのアイテムを*鑑定*しますか? ")
        elif self.phase == "object":
            self.screen = library_screen("[何かキーを押すとゲームに戻ります]")
        else:
            self.screen = library_screen()


class MorivantLibraryIdentifyRecordedTest(executor_harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        raw = FIXTURE.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == SHA256
        cls.pin = json.loads(gzip.decompress(raw))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def test_recorded_stop(self):
        final = self.pin["final"]
        self.assertEqual((final["decision_sequence"], final["reason"]),
                         (PIN, "town:morivant-full-identify:library"))
        self.assertEqual(final["key"], "3al" + "\x1b" * 8 + "an" + "\x1b" * 9)
        self.assertIn("owner=town:morivant-full-identify:library", self.pin["stderr_tail"])
        self.assertIn("ctx=item", self.pin["stderr_tail"])

    def test_library_batch_identifies_both_items(self):
        for policy, board, recorded in replay_session(self, self.pin, self.monrace):
            key = policy.choose_key(board)
            if recorded["decision_sequence"] == PIN:
                break
            policy.confirm_key_posted(key)
        self.assertEqual(policy.last_reason, "town:morivant-full-identify:library")
        self.assertEqual((board.player.position.y, board.player.position.x), (40, 105))
        raw = json.loads(self.pin["lines"][-1])
        game = LibraryHookGame(raw)
        game.screen = executor_harness.command_screen(raw["turn"])
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": PIN, "reason": policy.last_reason})
        # Before the fix: the second Escape leaves the Library and the second 'a'
        # opens Aim a wand at the command loop; only 'l' is identified.
        self.assertEqual(game.identified, ["l", "n"])
        self.assertEqual(game.phase, "command")


if __name__ == "__main__":
    import unittest
    unittest.main()
