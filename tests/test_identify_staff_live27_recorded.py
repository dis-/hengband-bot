"""Live27: replay actual response batches through the first changed decision.

Walls: isolate runtime paths, freeze the calibration available at extraction,
and bind each previous posted operation as the live CLI does. No later board
is interpreted as the effect of the changed mining decision.
"""
import tests  # noqa: F401
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURE = Path(__file__).parent / 'fixtures' / 'identify-staff-live27.jsonl.gz'


class IdentifyStaffLive27RecordedTest(unittest.TestCase):
    def test_recorded_shortfall_enters_one_run_mining(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), '09ab28d21a633391954394f4c244800e75e3ca68238440b7a319cb255d72262d')
        boundary = FIXTURE.with_suffix('.boundaries.json')
        self.assertEqual(hashlib.sha256(boundary.read_bytes()).hexdigest(), '13b6ac882b6cdc634b441ed59b5b3621277558db1ea342af7f3470ea9b883829')
        data = json.loads(boundary.read_text(encoding='utf-8'))
        lines = list(gzip.open(FIXTURE, 'rt', encoding='utf-8'))
        monrace = load_monrace_knowledge(EDIT / 'MonraceDefinitions.jsonc')
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy = _policy(directory, monrace)
            policy._crossarea_fundraising_enforced = True
            policy._character_calibration_path.write_bytes(FIXTURE.with_suffix('.calibration.json').read_bytes())
            cursor = 0
            for index, count in enumerate(data['input_rows']):
                segment = lines[cursor:cursor + count]
                cursor += count
                if index:
                    previous = data['recorded'][index - 1]
                    row = json.loads(segment[-1])
                    row['_completed_operation_sequence'] = previous['decision_sequence']
                    row['_completed_operation_owner'] = previous['reason']
                    segment = segment[:-1] + [json.dumps(row, ensure_ascii=False) + '\n']
                _, snapshots = _consume_response_sequence(segment, policy, lambda _key: True, monrace, knowledge_ledger_path=directory / 'knowledge.jsonl')
                board = snapshots[-1]
                recorded = data['recorded'][index]
                if recorded['reason'] == 'periodic:game-save':
                    policy.request_game_save()
                elif recorded['reason'] == 'periodic:character-dump':
                    policy.request_character_dump()
                key = policy.choose_key(board)
                if (str(key), policy.last_reason) != (recorded['key'], recorded['reason']):
                    print('FIRST DIVERGENCE', index, 'live', repr(recorded['key']), recorded['reason'], 'replay', repr(str(key)), policy.last_reason)
                    break
                policy.confirm_key_posted(key)
            print('SHORTFALL', policy._total_identify_staff_charges(board), 'mode', policy._fundraising_mode, 'planned', policy._planned_mining_runs, 'home_current', policy._home_knowledge_current, 'stores', policy._town_store_attempted)
            self.assertEqual(index, 104)
            self.assertEqual(recorded['departure_block']['failed'], ['identify_staff_ready'])
            self.assertEqual((str(key), policy.last_reason), ('5', 'town:identify-staff-stockout-mining'))
            self.assertEqual(policy._planned_mining_runs, 1)
            self.assertTrue(policy._identify_staff_mining_plan)
            self.assertFalse(policy._identify_staff_ready(board))


if __name__ == '__main__':
    unittest.main()
