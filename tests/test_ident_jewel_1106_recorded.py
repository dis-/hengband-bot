"""n1-c life-146 2026-11-06: {並} rings went to Home unidentified.

10:58:04 the Q31 reward ディリシウムの指輪 (an unaware flavor) was picked up;
10:58:10 it and the carried ダメージの指輪 were sensed {並}; decisions 17359 and
17362 shelved both in Home unidentified.  An {average} item was never worth an
Identify charge, whatever its kind.  Owner 2026-11-06: 「並で何も分からない品だけ
— 指輪・首飾りと、種類がまだ分からない品は、並でも鑑定する（並では種類も数値も
分からないため）。武器・防具・光源の並は今のまま修正なしとみなし…自宅の2つの
指輪も鑑定される。」 (equipment_optimizer.awaits_identification).

Recorded: the 10:58:10 board (turn 1683399) with the deposit decisions, and the
town-arrival checkpoint of the character's next visit (12:09, incident capture
20261106-120911-stuck-prompt) with its journal rows 0-17
(tests/extract_ident_jewel_1106_fixture.py).  The 10:58 visit itself has no
arrival checkpoint left (the server keeps the last few), and its level-25
calibration is not recorded, so the carried-ring pins replay the 12:09 visit.

Owner 2026-11-06 (Magic-Eater): 「預ける前に＋自宅の品も — 預ける予定の装備は
預ける前に *鑑定* する。自宅にある *鑑定* されていない装備も、町で余裕がある時に
取り出して *鑑定* し、また仕舞う。」 (me_powerful_activation).  The recorded
12:09 visit predates it: except in the two *Identify* pins, ``restore`` declares
no time to spare for the spare *Identify* so the recorded keys replay.

DECLARED CONSTRUCTED, carried-ring pins: the 10:58 ring (its exact board row) is
carried into the 12:09 visit instead of being on the shelf - appended as the
last pack letter of every journalled board, its Home row removed from the
catalog and from the Home pages (later letters shifted).  The {並} weapon pin
appends a constructed unidentified {average} dagger the same way.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import lzma
import string
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.cli import _consume_response_sequence
from hengbot.equipment_optimizer import equipment_identity
from hengbot.equipment_transaction_session import planned_item
from hengbot.model import STORE_ALCHEMIST, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST
from hengbot import me_powerful_activation  # after hengbot.cli: me_powers import cycle
from replay_town_arrival import adopt_calibration, restore
from tests.support.recorded import EDIT, _policy


FIXTURES = Path(__file__).with_name("fixtures") / "ident-jewel-1106"
DILITHIUM = "ディリシウムの指輪 {並}"
DAMAGE = "ダメージの指輪 {並}"
LETTERS = string.ascii_lowercase + string.ascii_uppercase


def _incident() -> dict:
    with gzip.open(FIXTURES / "incident-1058.json.gz", "rt", encoding="utf-8") as stream:
        return json.load(stream)


def _journal() -> list[dict]:
    return [json.loads(line) for line in
            lzma.decompress((FIXTURES / "journal.jsonl.xz").read_bytes()).splitlines()]


class IdentJewel1106RecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.incident = _incident()
        cls.journal = _journal()
        cls.ring = copy.deepcopy(next(item for item in cls.incident["board"]["inventory"]
                                      if item["slot"] == "l"))

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def restore(self, *, spare=False):
        """The 12:09 arrival policy.

        ``spare=False`` (DECLARED CONSTRUCTED): the town has no time to spare
        for the Magic-Eater's *Identify* (me_powerful_activation
        .spare_identify_ready), as the recorded visit, decided before the
        owner's 2026-11-06 *Identify*-before-deposit rule, behaved.
        """
        if not spare:
            self.no_spare = mock.patch.object(
                me_powerful_activation, "spare_identify_ready", lambda *args: False)
            self.no_spare.start()
            self.addCleanup(self.no_spare.stop)
        visit = self.scratch / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((FIXTURES / "policy.pkl.xz").read_bytes()))
        sidecars = json.loads(lzma.decompress((FIXTURES / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(json.dumps(sidecars["manifest"]), encoding="utf-8")
        (visit / SIDECAR_DIRECTORY).mkdir()
        for role, text in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(text.encode("latin-1"))
        runtime = self.scratch / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path",
                          runtime)
        return policy

    def decide(self, policy, row, carried=None, shelved=None, identified=()):
        """Decide journal ``row``; ``carried`` is appended to the pack and the
        pack items named in ``identified`` are fully known (DECLARED)."""
        entry = self.journal[row]

        def transform(state):
            for item in state.get("inventory", ()):
                if item["name"] in identified:
                    item["fully_known"] = True
            if carried is not None and "inventory" in state:
                state["inventory"].append(
                    dict(copy.deepcopy(carried), slot=LETTERS[len(state["inventory"])]))
            store = state.get("store")
            if shelved is not None and isinstance(store, dict) and store.get("store_type") == 7:
                kept = [item for item in store["items"] if item["name"] != shelved]
                if len(kept) != len(store["items"]):
                    for index, item in enumerate(kept):
                        item["letter"] = LETTERS[index]
                    store["items"] = kept
                    store["stock_num"] -= 1
            return state

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
        key = policy.choose_key(board)
        return board, key

    @staticmethod
    def post(policy, key):
        """Acknowledge a posted key as town_work_corpus.replay_window does."""
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def replay_unchanged(self, policy, rows, **carry):
        for row in rows:
            _board, key = self.decide(policy, row, **carry)
            self.assertEqual((key, policy.last_reason),
                             (self.journal[row]["key"], self.journal[row]["reason"]), row)
            self.post(policy, key)

    def planned_deposits(self, policy):
        session = policy._equipment_transaction_session
        return {action.item_id for action in getattr(getattr(session, "plan", None), "actions", ())
                if action.kind == "deposit"}

    def test_incident_shelved_both_average_rings(self):
        facts = {d["decision_sequence"]: d for d in self.incident["decisions"]}
        self.assertEqual((facts[17359]["reason"], facts[17359]["key"]),
                         ("equipment-transaction:deposit", "dk"))
        self.assertEqual(facts[17362]["reason"], "home:atomic-deposit")
        rings = {item["slot"]: item for item in self.incident["board"]["inventory"]
                 if item["tval"] == 45}
        self.assertEqual({slot: (item["name"], item["known"], item["pseudo_feeling"])
                          for slot, item in rings.items()},
                         {"k": (DAMAGE, False, "average"), "l": (DILITHIUM, False, "average")})
        self.assertFalse(rings["l"]["aware"])

    def test_recorded_board_owns_both_rings_for_identification(self):
        """On the 10:58:10 board the identification flow owns both {並} rings,
        so the equipment transaction preserves them instead of shelving them."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        policy = _policy(Path(directory.name), monrace)
        board = parse_snapshot(copy.deepcopy(self.incident["board"]), monrace)
        rings = [item for item in board.inventory if item.tval == 45]
        self.assertEqual(len(rings), 2)
        for ring in rings:
            self.assertTrue(policy._identification_flow_owns(ring), ring.name)
            self.assertFalse(policy._is_disposable_item(ring), ring.name)

    def test_carried_average_ring_is_not_shelved_but_identified(self):
        """The ring the 10:58 visit shelved stays in the pack and is identified."""
        policy = self.restore()
        shelf = next(owned.item for owned in policy._equipment_catalog._home.values()
                     if owned.item.name == DILITHIUM)
        # DECLARED CONSTRUCTED: the ring was never shelved.
        policy._equipment_catalog.record_home_withdrawal(shelf, intent=("constructed",))
        carry = {"carried": self.ring, "shelved": DILITHIUM}
        self.replay_unchanged(policy, range(12), **carry)
        ring_ids = {owned.id for owned in policy._equipment_catalog.items
                    if owned.origin == "pack" and owned.item.name == DILITHIUM}
        self.assertEqual(len(ring_ids), 1)
        self.assertFalse(ring_ids & self.planned_deposits(policy))
        # Row 12: the recorded last staged deposit; the ring is not shelved.
        board, key = self.decide(policy, 12, **carry)
        ring = next(item for item in board.inventory if item.name == DILITHIUM)
        self.assertEqual((key, policy.last_reason), ("dp\x1b", "home:atomic-deposit"))
        self.assertNotEqual(key, f"d{ring.slot}\x1b")
        self.post(policy, key)
        self.replay_unchanged(policy, (13,), **carry)
        board, key = self.decide(policy, 14, **carry)
        ring = next(item for item in board.inventory if item.name == DILITHIUM)
        self.assertEqual(policy.last_reason, "identify:normal")
        self.assertTrue(key.endswith(ring.slot), key)

    def test_average_weapon_is_treated_as_today(self):
        """A {並} dagger on the same visit: read as plain, destroyed as disposable."""
        policy = self.restore()
        # DECLARED CONSTRUCTED: an unidentified {average} dagger in the pack.
        dagger = dict(copy.deepcopy(self.ring), tval=23, sval=4, aware=True, weight=12,
                      name="Constructed Dagger {average}", damage_dice={"num": 1, "sides": 4})
        self.replay_unchanged(policy, range(13), carried=dagger)
        board, key = self.decide(policy, 13, carried=dagger)
        dagger_slot = next(item.slot for item in board.inventory if item.tval == 23
                           and not item.known)
        self.assertEqual((key, policy.last_reason),
                         (f"01k{dagger_slot}", "inventory:destroy-disposable-item"))

    def test_shelved_average_ring_is_withdrawn_for_identification(self):
        """The recorded 12:09 visit: the shelved ダメージの指輪 {並} is taken out."""
        policy = self.restore()
        self.replay_unchanged(policy, range(17))
        home = json.loads(self.journal[12]["line"] or self.journal[12]["inputs"][-1])["store"]
        letter = next(item["letter"] for item in home["items"] if item["name"] == DAMAGE)
        _board, key = self.decide(policy, 17)
        self.assertEqual((key, policy.last_reason),
                         (f"5p{letter}\x1b",
                          "home-errand:atomic-withdraw:identification-catalog"))

    def test_unidentifiable_average_ring_is_deferred_without_a_source(self):
        """Home equipment that awaits identification is deferred for the visit
        when no source exists after the Alchemist was tried, or the Home route
        insists on work nothing can do.

        DECLARED CONSTRUCTED: no identification source on the row-17 board
        (``_find_identification_source`` answers None) and the Alchemist tried.
        """
        policy = self.restore()
        self.replay_unchanged(policy, range(17))
        board, _key = self.decide(policy, 17)
        policy._find_identification_source = lambda *args, **kwargs: None
        policy._town_store_attempted[STORE_ALCHEMIST] = board.turn
        policy._has_actionable_incomplete_home_item(board)
        rings = {policy._item_signature(owned.item) for owned in policy._equipment_catalog.items
                 if owned.origin == "home" and owned.item.name in (DAMAGE, DILITHIUM)}
        self.assertEqual(len(rings), 2)
        self.assertTrue(rings <= set(policy._deferred_home_items))

    def test_planned_deposit_is_star_identified_before_it_is_shelved(self):
        """Owner 2026-11-06 「預ける前に＋自宅の品も」: the ring the equipment
        transaction plans to shelve is *identified* first, with a charge and
        time to spare (53 charges, HP 371/383 on the first safe board)."""
        policy = self.restore(spare=True)
        self.replay_unchanged(policy, range(3))
        planned = self.planned_deposits(policy)
        board, key = self.decide(policy, 3)
        ring = next(item for item in board.inventory if item.name == "耐因果混乱の指輪")
        self.assertFalse(ring.fully_known)
        self.assertIn(next(owned.id for owned in policy._equipment_catalog.items
                           if owned.origin == "pack" and owned.item.slot == ring.slot), planned)
        self.assertEqual((key, policy.last_reason),
                         (f"UAf{ring.slot}", "me-powerful:identify"))
        self.assertTrue(me_powerful_activation.spare_identify_ready(policy, board))

    def test_shelved_gear_is_taken_out_for_star_identify(self):
        """「自宅にある *鑑定* されていない装備も、町で余裕がある時に取り出して
        *鑑定* し、また仕舞う」: with no carried gear left for the spare *Identify*,
        the recall-read rung files one shelved piece not fully known as the
        catalogue take Home identification already executes.

        DECLARED CONSTRUCTED: the recall read is not in the window, so the rung
        (spare_identify_key) is asked on the arrival board (row 0, no owner holds
        the town yet), with the carried and worn gear's *Identify* uses spent
        and the five potion stacks a-e left out so that a take fits the pack
        reserve (23 of 23 slots were used).
        """
        policy = self.restore()
        board, key = self.decide(policy, 0)
        self.assertEqual((key, policy.last_reason), ("UAfs", "me-powerful:identify"))
        self.post(policy, key)
        self.no_spare.stop()
        raw = json.loads(self.journal[0]["line"] or self.journal[0]["inputs"][-1])
        raw["inventory"] = [item for item in raw["inventory"] if item["slot"] not in "abcde"]
        board = parse_snapshot(raw, policy._monrace_knowledge)
        memory = me_powerful_activation._memory(policy)
        for item in (*board.equipment, *board.inventory):
            if me_powerful_activation.spare_identify_target(item):
                memory.attempts[("identify", policy._item_signature(item))] = (
                    me_powerful_activation.ATTEMPTS_PER_TARGET)
        self.assertTrue(me_powerful_activation.spare_identify_ready(policy, board))
        self.assertFalse(policy._home_errand.active)
        me_powerful_activation.spare_identify_key(policy, board)
        request = policy._home_errand.request
        shelved = next(owned.item for owned in policy._equipment_catalog.items
                       if owned.origin == "home"
                       and policy._item_signature(owned.item) == request.signature)
        self.assertEqual(request.purpose, "identification-catalog")
        self.assertTrue(me_powerful_activation.spare_identify_target(shelved))
        self.assertEqual(memory.takes, {request.signature: 1})

    def test_star_identified_planned_deposit_is_still_deposited(self):
        """n1-c life-150 18:05:31-45 (and life-151 19:49, 19:59): the planned
        deposit *identified* before the walk was no longer found by its plan
        (the identity names fully_known), so the transaction closed for the
        visit as ``deposit-missing`` and Home became unavailable.

        DECLARED CONSTRUCTED: the 耐因果混乱の指輪 the row-3 *Identify* names is
        fully known on the later boards (rows 4-5), as the game shows it after
        identify_fully; the 耐電のアミュレット *Identify* of row 4 is not
        reflected on row 5.
        """
        ring_name = "耐因果混乱の指輪"
        policy = self.restore(spare=True)
        self.replay_unchanged(policy, range(3))
        board, key = self.decide(policy, 3)
        ring = next(item for item in board.inventory if item.name == ring_name)
        self.assertEqual((key, policy.last_reason), (f"UAf{ring.slot}", "me-powerful:identify"))
        self.post(policy, key)
        # The plan goes on: the next planned deposit is *identified* too.
        board, key = self.decide(policy, 4, identified=(ring_name,))
        amulet = next(item for item in board.inventory if item.name == "耐電のアミュレット")
        self.assertEqual((key, policy.last_reason), (f"UAf{amulet.slot}", "me-powerful:identify"))
        ring = next(item for item in board.inventory if item.name == ring_name)
        self.assertTrue(ring.fully_known)
        deposits = [action for action in policy._equipment_transaction_session.plan.actions
                    if action.kind == "deposit"]
        self.assertIn(equipment_identity(ring), {action.item_identity for action in deposits})
        self.assertTrue(all(planned_item(action, board.inventory) is not None
                            for action in deposits))
        self.post(policy, key)
        # Row 5, in Home: the recorded deposit of the identified ring.
        board, key = self.decide(policy, 5, identified=(ring_name,))
        ring = next(item for item in board.inventory if item.name == ring_name)
        self.assertEqual((key, policy.last_reason),
                         (f"d{ring.slot}", "equipment-transaction:deposit"))

    def spare_take_board(self, policy, drop="abcde"):
        """The arrival board (row 0) with the spare *Identify* of carried and
        worn gear spent, as in test_shelved_gear_is_taken_out_for_star_identify;
        ``drop`` names the pack letters left out (DECLARED CONSTRUCTED)."""
        board, key = self.decide(policy, 0)
        self.post(policy, key)
        self.no_spare.stop()
        raw = json.loads(self.journal[0]["line"] or self.journal[0]["inputs"][-1])
        raw["inventory"] = [item for item in raw["inventory"] if item["slot"] not in drop]
        board = parse_snapshot(raw, policy._monrace_knowledge)
        memory = me_powerful_activation._memory(policy)
        for item in (*board.equipment, *board.inventory):
            if me_powerful_activation.spare_identify_target(item):
                memory.attempts[("identify", policy._item_signature(item))] = (
                    me_powerful_activation.ATTEMPTS_PER_TARGET)
        return board, memory

    def leave_home_targets(self, policy, memory, *names):
        """Spend the Home takes of every shelved target but ``names``."""
        # The restored Memory predates ``takes`` (me_powerful_activation._home_take_key).
        takes = memory.__dict__.setdefault("takes", {})
        for owned in policy._equipment_catalog.items:
            if (owned.origin == "home" and owned.item.name not in names
                    and me_powerful_activation.spare_identify_target(owned.item)):
                takes[policy._item_signature(owned.item)] = (
                    me_powerful_activation.ATTEMPTS_PER_TARGET)

    def test_heavy_shelved_gear_is_not_taken_over_the_weight_limit(self):
        """n1-c life-150 19:09: 二重鎖かたびら was taken for *Identify* and
        ``home:weight-overload-deposit`` shelved it again before *Identify*
        ran, then 重鎖かたびら, ... eight owner retirements.

        DECLARED CONSTRUCTED: the spare-take board with the 恐慌モンスターの
        魔法棒 (l) also left out - carried 1638 of the 1650 limit - and only
        the 250-weight 二重鎖かたびら (-2) [16,+6] left to take.
        """
        policy = self.restore()
        board, memory = self.spare_take_board(policy, drop="abcdel")
        self.assertEqual((policy._inventory_weight(board), policy._inventory_weight_limit(board)),
                         (1638, 1650))
        mail = "二重鎖かたびら (-2) [16,+6]"
        self.leave_home_targets(policy, memory, mail)
        self.assertTrue(me_powerful_activation.spare_identify_ready(policy, board))
        self.assertIsNone(me_powerful_activation.spare_identify_key(policy, board))
        self.assertFalse(policy._home_errand.active)
        self.assertEqual(sum(memory.takes.get(policy._item_signature(owned.item), 0)
                             for owned in policy._equipment_catalog.items
                             if owned.item.name == mail), 0)

    def test_shelved_gear_within_the_weight_limit_is_still_taken(self):
        """The same board: past the mail that does not fit, the 5-weight
        スリング (x2) (+4,+4) does (1643 of 1650) and is taken."""
        policy = self.restore()
        board, memory = self.spare_take_board(policy, drop="abcdel")
        mail = "二重鎖かたびら (-2) [16,+6]"
        sling = "スリング (x2) (0.80turn) (+4,+4)"
        self.leave_home_targets(policy, memory, mail, sling)
        me_powerful_activation.spare_identify_key(policy, board)
        request = policy._home_errand.request
        self.assertEqual(request.purpose, "identification-catalog")
        shelved = next(owned.item for owned in policy._equipment_catalog.items
                       if owned.origin == "home"
                       and policy._item_signature(owned.item) == request.signature)
        self.assertEqual(shelved.name, sling)
        self.assertEqual(memory.takes[request.signature], 1)


if __name__ == "__main__":
    unittest.main()
