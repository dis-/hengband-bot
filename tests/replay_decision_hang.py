"""Offline suffix replay for the copied 12:19:56 October 4 watchdog capture.

Use --calibrated to reconstruct visible-board calibration from the archived
template (it is rejected at the hanging decision). Profiling bounds each
decision to ten seconds; --no-profile disables diagnostic sampling. Optional
--freeze PATH exports the pre-decision row-82 checkpoint to a new file.
This is a reconstructed suffix, not a checkpoint of the original live process.
"""
import tests  # isolate runtime files before importing policy
import gzip
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import traceback
import base64
import pickle
from hengbot.latch_onset_capture import checkpoint
from collections import Counter
from dataclasses import replace

from hengbot.cli import _consume_response_sequence, _capture_decision_facts
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy
from hengbot.warrior_optimization import load_character_calibration
from hengbot.warrior_equipment_evaluator import modify_stat_value
from hengbot.warrior_loadout_evaluator import constitution_hp_bonus
from hengbot.equipment_optimizer import OwnedEquipmentCatalog, current_loadout
from hengbot.warrior_defense_evaluator import WarriorDefenseInputs, loadout_armor_class


def main():
    source = Path(sys.argv[1])
    decisions_source = source.with_name(source.name.replace(
        '.bot-state-fixed.jsonl.gz', '.bot-decisions.jsonl.gz'))
    with gzip.open(decisions_source, 'rt', encoding='utf-8-sig') as stream:
        last_purchases = [json.loads(line) for line in stream][-2:]
    assert [row['key'] for row in last_purchases] == ['pm1\r\r', 'po1\r\r']
    assert all(row['turn'] == 8144392 for row in last_purchases)
    monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
    with TemporaryDirectory() as raw:
        directory = Path(raw)
        policy = _policy(directory, monrace)
        policy._crossarea_fundraising_enforced = True
        policy._in_store_ops_enabled = True
        with gzip.open(source.parent / 'state-upto-1150.jsonl.gz', 'rt', encoding='utf-8-sig') as stream:
            history = [json.loads(line) for line in stream]
            skill = next(row for row in history if row.get('knowledge', {}).get('category') == 'skill_exp')
        with gzip.open(source, "rt", encoding="utf-8-sig") as stream:
            lines = list(stream)
        for index, line in enumerate(lines):
            board = json.loads(line)
            if board.get('knowledge', {}).get('category') == 'home':
                policy._home_knowledge_scan_inflight = True
                policy._home_knowledge_scan_epoch = policy._town_visit_epoch
            _, snapshots = _consume_response_sequence(
                [line], policy, lambda _key: True, monrace,
                knowledge_ledger_path=directory / "knowledge.jsonl",
            )
            if not snapshots:
                continue
            snapshot = snapshots[-1]
            if index == 0:
                policy.prime(snapshot)
            policy.consume_skill_knowledge({**skill, 'player': {'level': snapshot.player.level}})
            snapshot = policy.with_known_skill_exp(snapshot)
            # DECLARED RECONSTRUCTION: the C dump is absent. Preserve the same
            # race/class/personality adjustments from the archived C record,
            # deriving current constants from the captured visible board.
            if '--calibrated' in sys.argv:
                template = load_character_calibration(Path(__file__).parent / 'fixtures/store-reentry-20261003.character-calibration.json')
                player = snapshot.player
                natural = player.stat_max
                intrinsic = tuple(modify_stat_value(n, a) for n, a in zip(natural, template.intrinsic_adjustments))
                catalog = OwnedEquipmentCatalog()
                catalog.refresh_carried((), snapshot.equipment)
                armor = loadout_armor_class(current_loadout(catalog.items), WarriorDefenseInputs(player.level, natural[3], shield_skill=player.shield_skill, intrinsic_dex=template.intrinsic_adjustments[3]))
                policy._character_calibration = replace(template,
                    level=player.level, stat_cur=natural, natural_stats=natural,
                    base_stats=intrinsic, visible_stat_key=player.printed_stat_cur_key,
                    base_hp=player.max_hp-constitution_hp_bonus(player.stat_use[4],player.level),
                    base_ac_bonus=player.ac-armor, hp_floor=player.level+1,
                    session_id=policy._calibration_session_id)
                policy._character_calibration_loaded = True
            policy.observe_store_screen(snapshot.store is not None)
            print('context', policy._home_knowledge_current, len(policy._equipment_catalog.items),
                  policy._validated_character_calibration(snapshot) is not None,
                  policy._calibration_unavailable_reason, flush=True)
            print(index, snapshot.turn, 'choose', flush=True)
            if '--freeze' in sys.argv and index == 81:
                frozen = {'source': source.name, 'source_row': index + 1,
                    'construction': 'Offline suffix replay; recorded boards and requested Home knowledge; visible-board calibration reconstruction (rejected at this point). Prior two purchase keys reproduced.',
                    'policy': checkpoint(policy),
                    'snapshot': base64.b64encode(pickle.dumps(snapshot, protocol=5)).decode('ascii')}
                target = Path(sys.argv[sys.argv.index('--freeze') + 1])
                if target.exists():
                    raise FileExistsError(target)
                target.write_bytes(gzip.compress(json.dumps(frozen).encode(), mtime=0))
                print('FROZEN', target, target.stat().st_size, flush=True)
                return
            start = time.perf_counter()
            counts = Counter()
            deadline = start + 10
            events = 0
            def sample(frame, event, arg):
                nonlocal events
                if event == 'call':
                    events += 1
                    name = frame.f_code.co_name
                    if name.startswith(('_fixed_quest', '_shelf_', '_town_need', '_next_purchase', '_prepare_equipment', '_enumerate_town')):
                        counts[name] += 1
                    if name == '_fixed_quest_is_offered':
                        counts['offer-caller:' + frame.f_back.f_code.co_name] += 1
                    if events % 4096 == 0 and time.perf_counter() > deadline:
                        sys.setprofile(None)
                        print('TIME BUDGET', counts.most_common(25), flush=True)
                        traceback.print_stack(frame)
                        raise TimeoutError('offline per-decision ten-second budget')
            try:
                if '--no-profile' not in sys.argv:
                    sys.setprofile(sample)
                key = policy.choose_key(snapshot)
                if '--calibrated' in sys.argv and index in {79, 80}:
                    assert key == last_purchases[index - 79]['key'], (index, key)
                print(index, repr(key), policy.last_reason, time.perf_counter()-start,
                      'facts', flush=True)
                _capture_decision_facts(snapshot, policy)
            finally:
                sys.setprofile(None)
            if key:
                policy.confirm_key_posted(key)


if __name__ == '__main__':
    main()
