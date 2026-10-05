"""Regenerate public sale-value facts from a Hengband source directory.

PYTHONPATH=src python scripts/generate_store_sale_knowledge.py C:/hengband
"""
import hashlib
import json
from pathlib import Path
import re
import sys

from hengbot.monrace_knowledge import _strip_jsonc


def generate(root):
    sources = {}

    def read(relative):
        raw = (root / relative).read_bytes()
        sources[relative] = hashlib.sha256(raw).hexdigest()
        return raw.decode('utf-8')

    numbers = {name: int(number) for name, number in re.findall(
        r'TR_(\w+)\s*=\s*(\d+)', read('src/object-enchant/tr-types.h'))}
    read('src/inventory/inventory-slot-types.h')
    result = {'flag_numbers': numbers}
    for filename, key in [('BaseitemDefinitions', 'baseitems'),
                          ('EgoDefinitions', 'egos'), ('ArtifactDefinitions', 'artifacts')]:
        rows = json.loads(_strip_jsonc(read(f'lib/edit/{filename}.jsonc')))[key]
        if key == 'baseitems':
            result[key] = {
                f"{e['itemkind']['type_value']}:{e['itemkind']['subtype_value']}": {
                    'cost': e['cost'], 'hit_bonus': e.get('hit_bonus', 0),
                    'damage_bonus': e.get('damage_bonus', 0),
                    'base_dice': e.get('base_dice', '0d0'),
                    'parameter_value': e.get('parameter_value', 0),
                    'flags': [numbers[f] for f in e.get('flags', []) if f in numbers],
                } for e in rows
            }
        else:
            result[key] = [{
                'name': e['name'], 'cost': e['cost'],
                'flags': [numbers[f] for f in e.get('flags', []) if f in numbers],
                **({'base_item': e['base_item']} if key == 'artifacts' else {'slot': e['slot']}),
            } for e in rows]
    # flag_cost has two grouped tmp_cost*count sums and ordinary linear terms.
    # Capture these public rules as numeric facts, without evaluating C++ code.
    source = read('src/object/object-value-calc.cpp')
    pattern = r'(else )?if \(\(?flags.has\(TR_(\w+)\)\)?(?: && \(plusses > 0\))?\) \{([^{}]*)\}'
    rules = []
    previous_flag = None
    for match in re.finditer(pattern, source):
        body = match[3]
        additions = re.findall(r'(total|tmp_cost) ([+-])= ([^;]+);', body)
        group = source[:match.start()].count('total += (tmp_cost * count);')
        for target, sign, expression in additions:
            if expression.strip() == '0':
                continue
            digits = list(map(int, re.findall(r'\d+', expression)))
            slope = digits[-1] if 'plusses' in expression else 0
            constant = digits[0] if 'plusses' not in expression or '+' in expression else 0
            multiplier = -1 if sign == '-' else 1
            count_match = re.search(r'count \+= (\d+)', body)
            count = int(count_match[1]) if count_match else int('count++' in body)
            rules.append({'flag': numbers[match[2]], 'constant': multiplier * constant,
                          'slope': multiplier * slope, 'positive_pval': 'plusses > 0' in match[0],
                          'group': group if target == 'tmp_cost' else None, 'count': count,
                          'unless': previous_flag if match[1] else None})
        previous_flag = numbers[match[2]]
    # CHAOTIC/BRAND_MAGIC/VAMPIRIC add directly but also increment group 0.
    result['flag_rules'] = rules
    result['group_zero_extra_count'] = [numbers[f] for f in ('CHAOTIC', 'BRAND_MAGIC', 'VAMPIRIC')]
    # TELEPORT's nested is_cursed branch is handled after calc_price's curse
    # rejection. The uncursed contribution is always +250.
    result['uncursed_teleport'] = numbers['TELEPORT']
    monraces = json.loads(_strip_jsonc(read('lib/edit/MonraceDefinitions.jsonc')))['monsters']
    result['monraces'] = [{
        'name': e['name'], 'level': e.get('level', 0),
        'symbol': e.get('symbol', {}).get('character', ''),
        'kind': [f for f in e.get('flags', []) if f in {'GOOD', 'EVIL', 'ANIMAL'}],
    } for e in monraces]
    result['sources'] = sources
    return result


if __name__ == '__main__':
    output = Path(__file__).resolve().parents[1] / 'src/hengbot/store_sale_knowledge.json'
    output.write_text(json.dumps(generate(Path(sys.argv[1])), ensure_ascii=True,
                                 separators=(',', ':')) + '\n', encoding='utf-8')
