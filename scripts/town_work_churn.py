"""Measure which past commits the town-work manifest rules made touch it.

usage: python scripts/town_work_churn.py [--commits 118] [--rev HEAD] [--jobs 4] [--out PATH]

For each of the last N non-merge commits that changed a manifest/registry file,
the current rules (scripts/town_work_manifest.py) are run on the commit and on
its first parent. Under these rules a commit needs
* a review change when the sites needing a hand review (selected minus proved
  data) differ, or a kept review changes a runtime field (a reclassification);
* an index change when the generated runtime index differs.
review_without_proof counts the review changes the same rules need without the
mechanical data proof (every selected site reviewed by hand).
Edits of review text only (evidence, context) are reported but never required.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# Paths as they existed in the measured history: town_producer_baseline.json (retired 2026-11-01) stays so a
# rerun over the same commits selects the same ones.
FAMILY = ('scripts/town_work_manifest.json.gz', 'src/hengbot/town_work_sites.json',
          'scripts/town_work_review.json', 'scripts/town_producer_baseline.json',
          'scripts/town_work_registry_review.json')


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, check=True).stdout


def tree_state(commit):
    """Sites needing a hand review, kept reviews, runtime index and unmapped sites of one commit."""
    sys.path.insert(0, str(ROOT / 'scripts'))
    import town_work_manifest as generator
    paths = git('ls-tree', '-r', '--name-only', commit, '--', 'src/hengbot').decode().split()
    sources = {path.removeprefix('src/hengbot/'): git('show', f'{commit}:{path}').decode('utf8')
               for path in paths if path.endswith('.py')}
    reviewed = json.loads(git('show', f'{commit}:scripts/town_work_review.json'))
    with tempfile.TemporaryDirectory(prefix='town-work-churn-') as raw:
        design = Path(raw) / 'SOL-DESIGN-town-progress.md'
        design.write_bytes(git('show', f'{commit}:SOL-DESIGN-town-progress.md'))
        generator.ROOT = Path(raw)
        functions, selected, origins, names = generator.inventory(sources)
    proved = generator.proved_data(functions, names, origins, selected)
    kept = generator.kept_reviews(reviewed, proved)
    complete = {site: generator.complete_review(reviewed[site]) if site in reviewed
                else generator.mechanical_review() for site in selected if site in reviewed or site in proved}
    index = {site: {k: review[k] for k in generator.RUNTIME_FIELDS} for site, review in complete.items()}
    return dict(selected=sorted(selected), required=sorted(selected - proved), kept=kept, index=index,
                unmapped=sorted(selected - reviewed.keys() - proved))


def commits(count, rev):
    log = git('log', f'-{count}', '--no-merges', '--format=%h %p', rev).decode().splitlines()
    result = []
    for line in log:
        commit, parent = line.split()[:2]
        touched = git('diff', '--name-only', parent, commit, '--', *FAMILY).decode().split()
        if touched:
            result.append((commit, parent, touched))
    return len(log), result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commits', type=int, default=118)
    parser.add_argument('--rev', default='HEAD')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--out')
    args = parser.parse_args()
    total, touching = commits(args.commits, args.rev)
    trees = sorted({c for commit, parent, _ in touching for c in (commit, parent)})
    with ProcessPoolExecutor(args.jobs) as pool:
        states = dict(zip(trees, pool.map(tree_state, trees)))
    rows = []
    for commit, parent, touched in touching:
        before, after = states[parent], states[commit]
        common = before['kept'].keys() & after['kept'].keys()
        reclassified = [site for site in common if before['index'].get(site) != after['index'].get(site)]
        review = before['required'] != after['required'] or bool(reclassified)
        # The same question under the digest-free rules without the proof: every selected site reviewed.
        old_review = before['selected'] != after['selected'] or bool(reclassified)
        index = before['index'] != after['index']
        text = any(before['kept'][site] != after['kept'][site] for site in common) and not reclassified
        rows.append(dict(commit=commit, touched=touched, review=review, review_without_proof=old_review,
                         index=index, text_only_edit=text,
                         added=sorted(set(after['required']) - set(before['required'])),
                         removed=sorted(set(before['required']) - set(after['required'])),
                         reclassified=sorted(reclassified), unmapped=after['unmapped'],
                         added_proved=sorted(set(after['index']) - set(before['index'])
                                             - set(after['kept']))))
    summary = dict(commits=total, touching=len(touching),
                   review=sum(r['review'] for r in rows),
                   review_without_proof=sum(r['review_without_proof'] for r in rows),
                   voluntary_text_edits=sum(r['text_only_edit'] and not r['review'] for r in rows),
                   index_only=sum(r['index'] and not r['review'] for r in rows),
                   none=sum(not r['index'] and not r['review'] for r in rows), rows=rows)
    text = json.dumps(summary, indent=1) + '\n'
    if args.out:
        Path(args.out).write_text(text, encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
