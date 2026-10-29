"""Check every fix, leaving the two documented owner-decision conflicts intact."""
import json
from pathlib import Path
import subprocess
import sys

out = Path(__file__).resolve().parent
names = json.loads((out / 'incident-tests.json').read_text(encoding='utf-8'))
conflicts = {
    'tests.test_two_cell_oscillation_recorded.SummonerRetreatVetoRecordedTest.test_replay_reproduces_the_retreat',
    'tests.test_two_cell_oscillation_recorded.SummonerRetreatVetoRecordedTest.test_seek_loot_does_not_walk_back_into_the_abandoned_square',
}
selected = [name for name in names if name not in conflicts] + [
    'tests.test_census_owner_declaration',
    'tests.test_immobile_summoner_recorded.ImmobileSummonerRecordedTest.test_first_capture_avoids_and_posts',
    'tests.test_immobile_summoner_recorded.ImmobileSummonerRecordedTest.test_recorded_board_collects_safe_loot_and_vetoes_loot_in_summoner_view',
]
(out / 'mutation-tests.json').write_text(json.dumps(selected, indent=2), encoding='utf-8')
command = [sys.executable, str(out / 'run_check.py'), 'mutation', 'PYTHON',
           'C:/hengband-backups/guard-tools/mutation_check.py', '.', 'main',
           '--record', '--tests', *selected]
raise SystemExit(subprocess.call(command, cwd=out.parents[1]))
