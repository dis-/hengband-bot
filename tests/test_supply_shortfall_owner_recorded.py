"""October 18 c4-a life-012 owner-retired bursts with a buyable shortfall.

Captures (bot d667f466, Outpost, C:\\hengband-backups\\state-logs\\
c4a-loops-20261016): 031620 failed ``teleport_ready`` (Teleport 14/15) and
035319 failed ``identify_staff_ready`` (Identify staff 14/20).  Both visits
ended in ``town:blocked:no-actionable-claim-owner`` WAITs and probes until
``owner-retired-burst``.  Neither was a stock-out:

- 031620: the Alchemist page (decision row 123) offered 60 Teleport scrolls
  at 68 gold with 10,235 gold carried.  The pack was full (23 rows) and the
  first wanted ware, a non-stacking Light scroll, was refused for pack space;
  ``_next_purchase`` returned None for the whole page although the Teleport
  scroll stacks onto the carried 14.  Fix: skip only the refused class.
- 035319: the Magic shop page (row 128) was closed as observed-uncomposable
  while four Identify staves were carried; the release sale on the next
  board left three staves (14 charges) and the remembered page's 13-charge
  staff became a legal required buy, but the stop stayed in
  ``blocked_this_visit`` and no owner routed back.  Fix: a blocked stop whose
  remembered page offers a departure-blocking purchase is still a supplier.

Substrate: the recorded state rows of each capture, replayed through the
public response path on one policy (tests/extract_supply_shortfall_owner_
fixture.py).  DECLARED WALLS (constructed context): the live process carried
knowledge from before the capture window, so (1) the 031620 ``~f`` skill list
(the same character) is applied before every decision except the recorded
``periodic:skill-exp-knowledge`` one, and (2) the capture's own later Home
knowledge row is consumed (public consume_home_knowledge) on the first town
board;
(3) every board after a posted key carries the executor's completed-operation
binding.  Under these walls every recorded decision before each pin
reproduces (asserted below); the pinned board is the first changed response.
"""

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import STORE_ALCHEMIST, STORE_MAGIC
from hengbot.model import _parse_items
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.protocol import snapshot_protocol_version
from test_esp_threat_rest_recorded import EDIT, _policy
from recorded_junk_scope import pre_town_junk_step_replay

FIXTURE = Path(__file__).parent / "fixtures/supply-shortfall-owner-20261018.json.gz"
SHA256 = "4e2f33cc2a75914484c750cd04dc5704a8d72d873ccad90b507080562902c9c6"


def _segments(lines, decisions):
    """Assign each recorded decision the state rows it drained."""
    turns = [json.loads(line)["turn"] for line in lines]
    segments = []
    cursor = 0
    for index, decision in enumerate(decisions):
        if decision["turn"] < turns[0]:
            continue
        end = min(len(lines), cursor + decision["drained"])
        while end > cursor + 1 and turns[end - 1] > decision["turn"]:
            end -= 1
        following = decisions[index + 1]["turn"] if index + 1 < len(decisions) else None
        while (end < len(lines) and turns[end] == decision["turn"]
               and following != decision["turn"]):
            end += 1
        if turns[end - 1] != decision["turn"] and len(segments) <= 2:
            if turns[cursor] > decision["turn"]:
                segments = []
                continue
            candidates = [k for k in range(len(turns)) if turns[k] <= decision["turn"]]
            end = candidates[-1] + 1
            if turns[end - 1] != decision["turn"]:
                continue
        segments.append((index, cursor, end))
        cursor = end
    return segments


class SupplyShortfallOwnerRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = FIXTURE.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == SHA256
        cls.pin = json.loads(gzip.decompress(raw))
        cls.skill = json.loads(cls.pin["skill_line"])
        assert cls.skill["knowledge"]["category"] == "skill_exp"
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.results = {}

    # declared wall: pre-2026-10-21 town junk step
    @pre_town_junk_step_replay
    def replay(self, name):
        """Replay to the pinned board; return (policy, board, key, prefix)."""
        capture = self.pin["captures"][name]
        lines, decisions = capture["lines"], capture["decisions"]
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        policy = _policy(root, self.monrace)
        policy._crossarea_fundraising_enforced = True  # live argv
        policy._in_store_ops_enabled = True  # live argv (--in-store-shop-ops)
        ledger = root / "knowledge.jsonl"
        primed = home_done = False
        previous = None
        prefix = []
        for index, start, end in _segments(lines, decisions):
            recorded = decisions[index]
            segment = lines[start:end]
            if previous is not None and previous["key"]:
                row = json.loads(segment[-1])
                row["_completed_operation_sequence"] = previous["decision_sequence"]
                row["_completed_operation_owner"] = previous["reason"]
                segment = segment[:-1] + [json.dumps(row, ensure_ascii=False) + "\n"]
            _, boards = _consume_response_sequence(
                segment, policy, lambda _key: True, self.monrace,
                knowledge_ledger_path=ledger)
            board = boards[-1]
            if not primed:
                policy.prime(board)
                primed = True
            if board.in_town and not home_done:
                # Wall (2): see the module docstring.
                home_done = True
                home = json.loads(lines[capture["home_row"]])
                policy.consume_home_knowledge(tuple(_parse_items(
                    home["knowledge"]["items"],
                    protocol=snapshot_protocol_version(home))))
            if recorded["reason"] != "periodic:skill-exp-knowledge":
                # Wall (1).
                policy.consume_skill_knowledge(
                    {**self.skill, "player": {"level": board.player.level}})
                board = policy.with_known_skill_exp(board)
            if recorded["reason"] == "periodic:game-save":
                policy.request_game_save()
            elif recorded["reason"] == "periodic:character-dump":
                policy.request_character_dump()
            key = policy.choose_key(board)
            if index == capture["pin"]:
                return policy, board, str(key), prefix, recorded
            prefix.append((recorded["row"], str(key) == recorded["key"]
                           and policy.last_reason == recorded["reason"]))
            policy.confirm_key_posted(key)
            previous = recorded
        raise AssertionError("pin not reached")

    def test_teleport_shortfall_is_bought_on_the_full_pack_alchemist_page(self):
        policy, board, key, prefix, recorded = self.replay("teleport-0316")
        # Row 122 is excluded since #69: with the Feanorian lamp worn the
        # single spare torch is surplus, and the full pack routes Home first
        # (recorded '\x1b`n%.' shop:travel -> now '\x1b`n(.' shop:travel).
        self.assertTrue(
            prefix and all(ok for row, ok in prefix if row != 122), prefix)
        self.assertEqual((recorded["key"], recorded["reason"]),
                         ("\x1b`n#.", "shop:travel"))
        # The adjacent outside board composes the observed Alchemist page.
        self.assertEqual((key, policy.last_reason), ("5", "shop:one-shot-buy"))
        self.assertEqual(
            policy._town_visit_ledger.pending_store_transaction[0], STORE_ALCHEMIST)
        page = policy._town_supplier_stock[STORE_ALCHEMIST]
        page_board = replace(board, store=page)
        self.assertEqual(len(page_board.inventory), 23)
        wanted = policy._next_purchase(page_board)
        self.assertTrue(wanted.is_teleport_scroll)
        self.assertEqual((wanted.price, wanted.count), (68, 60))

    def test_full_pack_with_only_nonstacking_wares_still_refuses(self):
        # Control (constructed page): without the stacking Teleport scroll the
        # full pack still refuses the page exactly as before.
        policy, board, _key, _prefix, _recorded = self.replay("teleport-0316")
        page = policy._town_supplier_stock[STORE_ALCHEMIST]
        page = replace(page, items=[
            ware for ware in page.items if not ware.is_teleport_scroll])
        page_board = replace(board, store=page)
        self.assertIsNone(policy._next_purchase(page_board))
        self.assertEqual(
            policy._shop_selector_diagnostics.get("pack_refusal"),
            "full-pack-nonstacking")

    def test_identify_staff_swap_returns_to_the_blocked_magic_shop(self):
        policy, board, key, prefix, recorded = self.replay("idstaff-0353")
        # Rows 104-126 are outside the walls' reach (Home trips the live
        # process composed from earlier state); from the Magic shop visit on
        # every recorded decision reproduces.  Row 139 is excluded since #69:
        # with the Feanorian lamp worn the spare torch is surplus under pack
        # pressure (recorded "\x1b`n'." shop:travel -> now '\x1b`n&.'
        # town-progress-invariant:defect:inventory:destroy-disposable-item
        # =>town-progress-invariant:approach).
        self.assertTrue(
            all(ok for row, ok in prefix if row >= 127 and row != 139), prefix)
        self.assertEqual((recorded["key"], recorded["reason"]),
                         ("\x1b`n%.", "shop:travel"))
        self.assertEqual(key, "\x1b`n&.")
        self.assertTrue(
            policy.last_reason.endswith("town-progress-invariant:approach"),
            policy.last_reason)
        self.assertIn(STORE_MAGIC, policy._town_errand_plan.blocked_this_visit)
        staves = policy._carried_identify_staves(board)
        self.assertEqual(sum(s.count * s.charges for s in staves), 14)
        page_board = replace(board, store=policy._town_supplier_stock[STORE_MAGIC])
        purchase = policy._departure_blocking_page_purchase(page_board)
        self.assertEqual(purchase.item.charges, 13)

    def test_blocked_stop_without_a_required_offer_stays_closed(self):
        # Control (constructed page): with the Identify staves removed from
        # the remembered Magic page, the blocked stop is not re-routed.
        policy, board, _key, _prefix, _recorded = self.replay("idstaff-0353")
        page = policy._town_supplier_stock[STORE_MAGIC]
        policy._town_supplier_stock[STORE_MAGIC] = replace(page, items=[
            ware for ware in page.items if not (ware.tval == 55 and ware.sval == 5)])
        self.assertIn(STORE_MAGIC, policy._town_errand_plan.blocked_this_visit)
        self.assertIsNone(policy._town_procurement_progress_key(board))

    def test_blocked_stop_the_plan_moved_past_stays_closed(self):
        # Control (constructed plan): the remembered Magic page still offers
        # the required 13-charge staff, but the plan no longer routes to the
        # blocked stop (cursor past its end); the stop is not re-routed, as in
        # the guardian-recall fallback board where a later need arose.
        policy, board, _key, _prefix, _recorded = self.replay("idstaff-0353")
        plan = policy._town_errand_plan
        self.assertEqual(plan.stops[plan.index:], [STORE_MAGIC])
        page_board = replace(board, store=policy._town_supplier_stock[STORE_MAGIC])
        self.assertIsNotNone(policy._departure_blocking_page_purchase(page_board))
        plan.index = len(plan.stops)
        self.assertIsNone(policy._town_procurement_progress_key(board))


if __name__ == "__main__":
    unittest.main()
