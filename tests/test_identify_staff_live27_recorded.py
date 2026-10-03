"""Live27: independent current Home-arrival and mining decisions.

S3.3 migration: shared admission corrects the old Home hold; the old
prefix cannot supply later equipment inputs or mining boards. The sites
at 63 and 104 are DECLARED CONSTRUCTED baseline-policy checkpoints from
0d2ef6d6, frozen by extract_s33_live27_checkpoints.py. They are independent
operation substrates, not a current trajectory or recovered live state.

Walls: isolate runtime paths, freeze the calibration available at extraction,
and bind each previous posted operation as the live CLI does. No later board
is interpreted as the effect of the changed mining decision.
"""
import tests  # noqa: F401
import gzip
import base64
import io
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import TVAL_STAFF, SV_STAFF_IDENTIFY
from test_esp_threat_rest_recorded import EDIT, _policy
from recorded_equipment_decisions import frozen_equipment_replay
from extraction_calibration import install_extraction_calibration
from xbow_pref_walls import shelf_wall_on_replay
from unittest.mock import patch

from hengbot.policy import HengbotPolicy
from hengbot.policy_state import normalize_policy_state
from test_store_reentry_recorded import _Unpickler

# overweight-home (2026-10-02): live decision 63 left Home with ESC
# home:route-claim-unfulfilled because the arrived store-router Reach (claim 48)
# held every Home producer (recorded errand_deferred, incl.
# queue-digging-tool-withdraw).  Production now runs the Home producers on that
# arrival. Independent baseline sites preserve the separate 63 and 104
# subjects without supplying any old effect after a changed current key.
PRE_FIX_HOME_HOLD = 63

FIXTURE = Path(__file__).parent / 'fixtures' / 'identify-staff-live27.jsonl.gz'


INDEPENDENT = FIXTURE.parent / "live27.s33-independent-checkpoints.json.gz"
INDEPENDENT_SHA256 = "b9c31df3f9c630cb3ca138926649cb0e38aca3c8fbcc38426d6bda0acc5334ef"


def independent_scene(directory, monrace, index):
    assert hashlib.sha256(INDEPENDENT.read_bytes()).hexdigest() == INDEPENDENT_SHA256
    payload = json.loads(gzip.decompress(INDEPENDENT.read_bytes()))
    assert payload["source_revision"] == "0d2ef6d6"
    assert payload["input_sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    policy, board = _Unpickler(io.BytesIO(base64.b64decode(payload["checkpoints"][str(index)])), monrace).load()
    old_directory = policy._character_calibration_path.parent
    for name, value in tuple(vars(policy).items()):
        if isinstance(value, Path) and value.is_relative_to(old_directory):
            setattr(policy, name, directory / value.relative_to(old_directory))
    normalize_policy_state(policy)
    return policy, board


class IdentifyStaffLive27RecordedTest(unittest.TestCase):
    # fixer-reconcile-prompt.txt STEP 2: retain live27's mining/charge/restore
    # assertions while supplying the equipment decisions its boards confirm.
    @frozen_equipment_replay("live27")
    @shelf_wall_on_replay  # declared wall: no 2026-10-02 crossbow swap
    def test_recorded_shortfall_enters_one_run_mining(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), '09ab28d21a633391954394f4c244800e75e3ca68238440b7a319cb255d72262d')
        boundary = FIXTURE.with_suffix('.boundaries.json')
        self.assertEqual(hashlib.sha256(boundary.read_bytes().replace(b'\r\n', b'\n')).hexdigest(), '71db3597fa841de0526b1e1739bbfa2dd6fd93f4738c71c68fd700966c1205f1')
        data = json.loads(boundary.read_text(encoding='utf-8'))
        lines = list(gzip.open(FIXTURE, 'rt', encoding='utf-8'))
        monrace = load_monrace_knowledge(EDIT / 'MonraceDefinitions.jsonc')
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            index = 104
            policy, board = independent_scene(directory, monrace, index)
            recorded = data['recorded'][index]
            restored = restore_checkpoint(type(policy), checkpoint(policy))
            key = policy.choose_key(board)
            print('SHORTFALL', policy._total_identify_staff_charges(board), 'mode', policy._fundraising_mode, 'planned', policy._planned_mining_runs, 'home_current', policy._home_knowledge_current, 'stores', policy._town_store_attempted)
            self.assertEqual(index, 104)
            self.assertEqual(recorded['departure_block']['failed'], ['identify_staff_ready'])
            self.assertEqual((str(key), policy.last_reason), ('5', 'town:identify-staff-stockout-mining'))
            self.assertEqual(policy._planned_mining_runs, 1)
            self.assertTrue(policy._identify_staff_mining_plan)
            self.assertFalse(policy._identify_staff_ready(board))
            restored_key = restored.choose_key(board)
            self.assertEqual((str(restored_key), restored.last_reason), (str(key), policy.last_reason))
            self.assertEqual(restored._planned_mining_runs, 1)
            # Named counterfactuals on the same stop board, not effects of mining:
            # one carried stack with 19 charges remains blocked; 20 satisfies it.
            for charges in (19, 20):
                changed = replace(board, inventory=tuple(
                    replace(item, count=1, charges=charges, pval=charges)
                    if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
                    else item for item in board.inventory
                ))
                self.assertEqual(policy._identify_staff_ready(changed), charges == 20)
            # Constructed run-completion state: exercise the existing return
            # transition on a copy, without claiming the live mining key ran.
            restored._fundraising_mode = 'mine'
            restored._mining_runs_completed = 1
            restored._town_store_attempted[7] = board.turn
            self.assertIsNone(restored._town_special_key(board))
            self.assertIsNone(restored._fundraising_mode)
            self.assertIsNone(restored._planned_mining_runs)
            self.assertFalse(restored._identify_staff_mining_plan)
            self.assertEqual(restored._town_store_attempted, {})
            self.assertFalse(restored._identify_staff_ready(board))


    @frozen_equipment_replay("live27")
    @shelf_wall_on_replay  # declared wall: no 2026-10-02 crossbow swap
    def test_routed_home_arrival_queues_the_mining_digger(self):
        """Production at the recorded arrival: first changed key is index 63."""
        boundary = FIXTURE.with_suffix('.boundaries.json')
        data = json.loads(boundary.read_text(encoding='utf-8'))
        lines = list(gzip.open(FIXTURE, 'rt', encoding='utf-8'))
        monrace = load_monrace_knowledge(EDIT / 'MonraceDefinitions.jsonc')
        recorded = data['recorded'][PRE_FIX_HOME_HOLD]
        self.assertEqual((recorded['key'], recorded['reason']), ('\x1b', 'home:route-claim-unfulfilled'))
        self.assertEqual(recorded['fundraising']['mode'], 'prepare')
        self.assertEqual(
            [(row['holder_family'], row['holder_claim_id'], row['deferred_reason'])
             for row in recorded['claim']['errand_deferred']],
            [('store-router', 48, 'entry:_release_staged_store_operation'),
             ('store-router', 48, 'entry:_home_rearm_key'),
             ('store-router', 48, 'queue-digging-tool-withdraw'),
             ('store-router', 48, 'entry:_open_home_deposit_key')])
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy, board = independent_scene(directory, monrace, PRE_FIX_HOME_HOLD)
            key = policy.choose_key(board)
            # 09-18: carry diggers when departing for mining (mode prepare).
            self.assertEqual((str(key), policy.last_reason), ('\x1b', 'home:queue-digging-tool-withdraw'))


if __name__ == '__main__':
    unittest.main()
