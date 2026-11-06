"""The Magic-Eater's Home take for *Identify* bounced, and taken gear left town.

Owner 2026-11-06 「預ける前に＋自宅の品も」: a Magic-Eater with a spare
*Identify* takes ONE gear piece not fully known out of Home, *identifies* it
and puts it back (me_powerful_activation._home_take_key).

n1-b life-333 2026-11-07 02:59:23-31: ``home-errand:atomic-withdraw:
identification-catalog`` took 金属製ブリガンダイン・アーマー out ('5py'); the next
board planned it as an unused deposit (``equipment-transaction:atomic-deposit``
'5', ``home:atomic-deposit`` 'di') and shelved it again with no *Identify*
between, then 鋲付軟革よろい ('5pD') and 硬革よろい ('5pE') the same way, until the
owner retirements stopped the town (owner-retired-burst; n1-b life-332
00:41:44-55 the same with rings).  The only *Identify* rung before the
transaction, ``me_powerful_activation.town_key``, targeted carried gear only as
a planned deposit of an open transaction, and right after the take there was
none.

n1-c life-158 02:20-02:33: Home takes brought weapons out; once *identified*
they were spare gear, but Home was already attempted (``spare_gear
.stow_pending`` false), so the character left with them; at 02:33 eight of them
were carried, a further take held Home and the town stopped as
``town:blocked:overflow-no-legal-disposal``.

Recorded substrate: the n1-c life-146 12:09 town-arrival checkpoint and its
journal (tests/fixtures/ident-jewel-1106, test_ident_jewel_1106_recorded), the
same Magic-Eater with 53 *Identify* charges and Home gear not fully known.

DECLARED CONSTRUCTED for every pin (as test_ident_jewel_1106_recorded's
spare-take pins): the recall read that files the take is not in the window, so
the take is filed on the arrival board (row 0) with the carried and worn
gear's *Identify* uses spent and the pack letters ``DROP`` left out (the take
must fit the pack reserve and the weight limit); the following boards are that
board with the player on the Home entrance (y45 x123, where n1-b's take landed
too), the ``~9`` scan answered by the recorded scan of the visit (journal row
14), and the taken スリング added as the next pack letter once the posted take
landed, fully known once its *Identify* completed.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import string
import unittest

from hengbot.cli import _consume_response_sequence
from hengbot.equipment_optimizer import equipment_identity
from hengbot.model import STORE_HOME, parse_snapshot
from hengbot import me_powerful_activation, spare_gear  # after hengbot.cli: me_powers import cycle
import test_ident_jewel_1106_recorded as ident_jewel


LETTERS = string.ascii_lowercase + string.ascii_uppercase
DROP = "abcdel"
SLING = "スリング (x2) (0.80turn) (+4,+4)"
PLAIN_SLING = "スリング (x2) (0.80turn) (+0,+0)"
# The shelved スリング as the pack shows it once taken (its catalogue row).
SLING_RAW = {"ac": 0, "aware": True, "charges": 0, "charging": False, "count": 1,
             "damage_dice": {"num": 0, "sides": 0}, "fully_known": False, "inscription": "",
             "is_artifact": False, "is_bounty": False, "is_broken": False, "is_cursed": False,
             "is_ego": False, "is_equipment": True, "known": True, "known_flags": [74],
             "name": SLING, "pval": 0, "sval": 2, "to_a": 0, "to_d": 4, "to_h": 4, "tval": 19,
             "weight": 5}
HOME_ENTRANCE = (45, 123)


class MeTakeBounce1107RecordedTest(unittest.TestCase):

    # The recorded substrate's helpers (not its tests).
    _recorded = ident_jewel.IdentJewel1106RecordedTest
    setUpClass = _recorded.__dict__["setUpClass"]
    setUp = _recorded.setUp
    restore = _recorded.restore
    decide = _recorded.decide
    post = staticmethod(_recorded.post)
    spare_take_board = _recorded.spare_take_board
    leave_home_targets = _recorded.leave_home_targets

    def board_state(self, turn, *, carried=False, identified=False):
        """The arrival board on the Home entrance (DECLARED, module doc)."""
        state = json.loads(self.journal[0]["line"] or self.journal[0]["inputs"][-1])
        for name in [name for name in state if name.startswith("_")]:
            del state[name]  # row 0's own completed operation
        state["inventory"] = [item for item in state["inventory"] if item["slot"] not in DROP]
        for index, item in enumerate(state["inventory"]):
            item["slot"] = LETTERS[index]
        if carried:
            state["inventory"].append(dict(SLING_RAW, slot=LETTERS[len(state["inventory"])],
                                           fully_known=identified))
        state["turn"] += turn
        state["player"]["y"], state["player"]["x"] = HOME_ENTRANCE
        state["messages"] = []
        return state

    def deliver(self, policy, *states):
        """The response lines of the last posted key, as the CLI consumes them."""
        _consume_response_sequence(
            [json.dumps(state, ensure_ascii=False) + "\n" for state in states], policy,
            lambda _key: True, policy._monrace_knowledge, parse_snapshots=False,
            knowledge_ledger_path=self.scratch / "knowledge.jsonl")
        policy.observe_store_screen(False)
        return parse_snapshot(states[-1], policy._monrace_knowledge)

    def decide_board(self, policy, *states):
        board = self.deliver(policy, *states)
        key = policy.choose_key(board)
        self.post(policy, key)
        return board, key

    def take_sling(self, policy, *targets):
        """File the Home take of the スリング and play it until it lands.

        Returns the first board with the taken piece carried and its key.
        """
        board, memory = self.spare_take_board(policy, drop=DROP)
        self.leave_home_targets(policy, memory, SLING, *targets)
        self.assertTrue(me_powerful_activation.spare_identify_ready(policy, board))
        me_powerful_activation.spare_identify_key(policy, board)
        self.assertEqual(policy._home_errand.request.signature, (SLING, 19, 2))
        # On the Home entrance the errand asks for fresh knowledge first.
        _board, key = self.decide_board(policy, self.board_state(2))
        self.assertEqual((key, policy.last_reason),
                         ("~9\x1b", "home-errand:request-knowledge:identification-catalog"))
        scan = next(json.loads(line) for line in self.journal[14]["inputs"]
                    if json.loads(line).get("type") == "knowledge")
        scan["turn"] = self.board_state(3)["turn"]
        self.decide_board(policy, scan, self.board_state(3))
        for turn in range(5, 10):
            _board, key = self.decide_board(policy, self.board_state(turn))
            if policy.last_reason == "home-errand:atomic-withdraw:identification-catalog":
                break
        self.assertEqual(policy.last_reason, "home-errand:atomic-withdraw:identification-catalog")
        board = self.deliver(policy, self.board_state(12, carried=True))
        return board, policy.choose_key(board)

    @staticmethod
    def sling_of(board):
        return next(item for item in board.inventory if item.name == SLING)

    @staticmethod
    def planned_deposit_identities(policy):
        session = policy._equipment_transaction_session
        return {action.item_identity for action in getattr(getattr(session, "plan", None), "actions", ())
                if action.kind == "deposit"}

    def identified_board(self, policy, turn):
        """Decide the board after the スリング's *Identify* completed (fully known)."""
        state = self.board_state(turn, carried=True, identified=True)
        state["_completed_operation_owner"] = "me-powerful:identify"
        state["_completed_operation_receipt"] = {"owner": "me-powerful:identify", "refusal": None}
        return self.decide_board(policy, state)

    def test_taken_piece_is_identified_before_anything_shelves_it(self):
        """n1-b life-333 02:59:23: the first decision after the take *identifies*
        the taken piece; no deposit is planned for it before that."""
        policy = self.restore()
        board, key = self.take_sling(policy)
        sling = self.sling_of(board)
        self.assertFalse(sling.fully_known)
        self.assertEqual((key, policy.last_reason), (f"UAf{sling.slot}", "me-powerful:identify"))
        self.assertNotIn(equipment_identity(sling), self.planned_deposit_identities(policy))
        self.assertTrue(policy._identification_flow_owns(sling))
        self.post(policy, key)
        # Identified, it is spare gear again: Home takes it back.
        board, _key = self.identified_board(policy, 14)
        sling = self.sling_of(board)
        self.assertFalse(policy._identification_flow_owns(sling))
        self.assertTrue(spare_gear.released(policy, board, sling))
        self.assertTrue(spare_gear.stow_pending(policy, board))

    def test_taken_piece_is_not_held_without_a_charge(self):
        """With the last charge spent the piece is not held: the deposit flow
        shelves it as before (DECLARED: the next board browses the staff list,
        row 1's recorded list with 鑑定 shown empty)."""
        policy = self.restore()
        board, key = self.take_sling(policy)
        self.assertTrue(policy._identification_flow_owns(self.sling_of(board)))
        state = self.board_state(13, carried=True)
        listed = json.loads(self.journal[1]["line"])["_magic_eater_power_list"]
        for row in listed["rows"]:
            if row["name"] == "鑑定":
                row["current"] = 0
        state["_magic_eater_power_list"] = listed
        board = self.deliver(policy, state)
        policy.choose_key(board)
        self.assertFalse(policy._identification_flow_owns(self.sling_of(board)))

    def test_last_charge_spent_files_no_take(self):
        """The staff list is read at the power prompt, before the use pays: row 1
        recorded 鑑定 53/53 on the board after the row-0 *Identify*.  DECLARED:
        that list showed the last charge (1); after the use no charge is left,
        so no Home take is filed for an *Identify* that cannot run."""
        policy = self.restore()
        board, key = self.decide(policy, 0)
        self.assertEqual((key, policy.last_reason), ("UAfs", "me-powerful:identify"))
        self.post(policy, key)
        entry = self.journal[1]
        line = json.loads(entry["line"] or entry["inputs"][-1])
        listed = line["_magic_eater_power_list"]
        self.assertEqual(next(row for row in listed["rows"] if row["name"] == "鑑定")["current"], 53)
        for row in listed["rows"]:
            if row["name"] == "鑑定":
                row["current"] = 1
        _consume_response_sequence(
            [json.dumps(line, ensure_ascii=False) + "\n"], policy, lambda _key: True,
            policy._monrace_knowledge, parse_snapshots=False,
            knowledge_ledger_path=self.scratch / "knowledge.jsonl")
        board = parse_snapshot(copy.deepcopy(line), policy._monrace_knowledge)
        self.post(policy, policy.choose_key(board))
        # The next board on the Home entrance, HP recovered (the use's cost no
        # longer reads as a hit this turn; module doc).
        for later in (10, 12):
            board = self.deliver(policy, self.board_state(
                line["turn"] - self.board_state(0)["turn"] + later))
            self.post(policy, policy.choose_key(board))
        self.no_spare.stop()
        self.assertEqual(me_powerful_activation.charges_left(
            policy, board, me_powerful_activation.IDENTIFY), 0)
        self.assertEqual(me_powerful_activation.me_capability.charges(
            policy, board, "staff", me_powerful_activation.IDENTIFY.sval), 1)
        self.assertTrue(me_powerful_activation.pays_safely(policy, board))
        self.assertTrue(me_powerful_activation._safe(policy, board))
        memory = me_powerful_activation._memory(policy)
        self.leave_home_targets(policy, memory, SLING)
        self.assertFalse(me_powerful_activation.spare_identify_ready(policy, board))
        self.assertIsNone(me_powerful_activation.spare_identify_key(policy, board))
        self.assertFalse(policy._home_errand.active)


if __name__ == "__main__":
    unittest.main()
