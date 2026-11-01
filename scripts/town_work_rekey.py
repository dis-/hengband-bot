#!/usr/bin/env python3
"""Re-key town work reviews of moved or renamed functions (dry run unless --write).

usage: PYTHONPATH=src python scripts/town_work_rekey.py [--base REV] [--write]

town_work_review.json keys each review by module:qualname, so moving a function
to another module or renaming it leaves the old review stale and the new site
unmapped (town_work_manifest.py fails). This finds each stale review whose
function disappeared since --base (default HEAD, the tree before an uncommitted
move) while exactly one unreviewed selected function appeared with the same
body, and moves the review to the new key. The body is the normalized AST
without the name and the docstring; a changed body is never re-keyed. The
review text is kept as it was; regenerate the index afterwards
(town_work_manifest.py --write).
"""
from __future__ import annotations

import argparse
import ast
import copy
from collections import defaultdict
import json
import sys

import town_structure_lint as lint
import town_work_manifest as generator


def body_fingerprint(function):
    """The function's AST without its name, docstring and positions: equal for a pure move or rename."""
    node = copy.deepcopy(function)
    node.name = ''
    if ast.get_docstring(node, clean=False) is not None:
        node.body = node.body[1:] or [ast.Pass()]
    return ast.dump(node, include_attributes=False)


def rekey_plan(old_functions, new_functions, reviewed, selected):
    """(moves {old: new}, ambiguous {old: [candidates]}, unmatched [old]) for the stale reviews."""
    appeared = defaultdict(list)
    for site in sorted(selected - reviewed.keys() - old_functions.keys()):
        appeared[body_fingerprint(new_functions[site])].append(site)
    stale = sorted(reviewed.keys() - selected)
    disappeared = defaultdict(list)
    for site in stale:
        if site in old_functions and site not in new_functions:
            disappeared[body_fingerprint(old_functions[site])].append(site)
    moves, ambiguous = {}, {}
    for fingerprint, olds in disappeared.items():
        targets = appeared.get(fingerprint, [])
        if len(olds) == 1 and len(targets) == 1:
            moves[olds[0]] = targets[0]
        elif targets:
            ambiguous.update({old: targets for old in olds})
    unmatched = [site for site in stale if site not in moves and site not in ambiguous]
    return moves, ambiguous, unmatched


def plan_for_sources(old_sources, new_sources, reviewed):
    """rekey_plan for two policy trees, selecting sites the way the manifest does."""
    functions, selected, _origins, _names = generator.inventory(new_sources)
    return rekey_plan(lint.collect(old_sources), functions, reviewed, selected)


def apply_moves(reviewed, moves):
    """The review with each moved key renamed in place (order and entries unchanged)."""
    return {moves.get(site, site): review for site, review in reviewed.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', default='HEAD', help='git revision of the tree before the move (default HEAD)')
    parser.add_argument('--write', action='store_true', help='rewrite scripts/town_work_review.json')
    args = parser.parse_args()
    reviewed = json.loads(generator.REVIEW.read_text(encoding='utf8'))
    moves, ambiguous, unmatched = plan_for_sources(generator.revision_sources(args.base),
                                                   generator.sources(), reviewed)
    for old, new in sorted(moves.items()):
        print(f'town-work-rekey: {old} -> {new}')
    for old, targets in sorted(ambiguous.items()):
        print(f'town-work-rekey: {old}: same body at {targets}; re-key by hand')
    for old in unmatched:
        print(f'town-work-rekey: {old}: stale, no function with the same body appeared; review by hand')
    if args.write and moves:
        generator.REVIEW.write_text(json.dumps(apply_moves(reviewed, moves), ensure_ascii=False, indent=2) + '\n',
                                    encoding='utf8', newline='\n')
    action = ('rewrote the review' if moves else 'nothing to write') if args.write else 'dry run; --write applies'
    print(f'town-work-rekey: {len(moves)} re-keyed, {len(ambiguous) + len(unmatched)} left ({action})')
    return 1 if ambiguous or unmatched else 0


if __name__ == '__main__':
    sys.exit(main())
