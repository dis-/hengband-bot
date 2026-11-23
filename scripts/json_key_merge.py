#!/usr/bin/env python3
"""Git merge driver for the town work JSON objects: a three-way merge by key, not by line.

usage (git runs it): python scripts/json_key_merge.py %O %A %B
setup, once per clone (every worktree shares it):
    git config merge.json-keys.name "three-way merge of a JSON object by key"
    git config merge.json-keys.driver "python scripts/json_key_merge.py %O %A %B"

.gitattributes routes src/hengbot/town_work_sites.json (the runtime index that
scripts/town_work_manifest.py --write generates) and scripts/town_work_review.json
(the hand reviews) here. Every branch adds, changes or removes a few keys of these
objects, and a line merge of two branches that touched neighbouring keys conflicts
even when no key was touched by both (whole-bot review 2026-11-23 (a)-11). This
merges the objects key by key: a key added, changed or removed by one side only
takes that side; a key both sides set to the same value is kept. When git's line
merge succeeds and reads as the same object, its bytes are kept unchanged; otherwise the result is
dumped in the generator's format (indent 2, UTF-8, LF); a sorted object stays sorted
(the index), otherwise ours' order with theirs' new keys appended in theirs' order
(the reviews, like merge_gate's merge_json_keys.py).

A key both sides changed differently, a file that is not a JSON object, or a file
whose re-dump does not reproduce its bytes falls back to git's line merge with
conflict markers (exit 1), exactly as without this driver. Without the git config
above, git ignores the attribute and line-merges as before.

The merged index is the merge of two generated indexes, not a regeneration;
town_structure_lint (town_work_manifest.check_repository) still fails a stale one,
and the landing gate regenerates it after every merge, as before.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + '\n'


def load(data):
    """The JSON object in ``data`` or None when it is not one this driver may re-dump."""
    try:
        obj = json.loads(data.decode('utf-8'))
    except ValueError:
        return None
    if not isinstance(obj, dict) or dump(obj).encode('utf-8') != data.replace(b'\r\n', b'\n'):
        return None
    return obj


def merge(base, ours, theirs):
    """The key-wise merge of three JSON objects, or (None, key) when both sides changed ``key``."""
    merged = dict(ours)
    for key in base.keys() | ours.keys() | theirs.keys():
        old, mine, other = base.get(key, KeyError), ours.get(key, KeyError), theirs.get(key, KeyError)
        if mine == other or other == old:
            continue
        if mine != old:
            return None, key
        if other is KeyError:
            del merged[key]
        else:
            merged[key] = other
    if list(ours) == sorted(ours) and list(theirs) == sorted(theirs):
        return dict(sorted(merged.items())), None
    # Ours' order, then theirs' new keys in theirs' order.
    return {**{k: merged[k] for k in ours if k in merged},
            **{k: merged[k] for k in theirs if k in merged and k not in ours}}, None


def main(argv):
    base_path, ours_path, theirs_path = (Path(arg) for arg in argv[1:4])
    objects = [load(path.read_bytes()) for path in (base_path, ours_path, theirs_path)]
    if None in objects:
        reason = 'not a JSON object in the generator format'
    else:
        merged, both = merge(*objects)
        if merged is not None:
            # Git's own line merge when it merges cleanly to the same object: the bytes (key order of
            # the reviews) stay what they were before this driver; the key merge only replaces conflicts.
            line = subprocess.run(['git', 'merge-file', '-p', '-q', str(ours_path), str(base_path),
                                   str(theirs_path)], capture_output=True)
            text = (line.stdout if line.returncode == 0 and load(line.stdout) == merged
                    else dump(merged).encode('utf-8'))
            ours_path.write_bytes(text)
            return 0
        reason = f'both sides changed {both!r}'
    print(f'json_key_merge: {reason}; line merge with conflict markers '
          '(for town_work_sites.json resolve the review, then town_work_manifest.py --write)',
          file=sys.stderr)
    # Same as git's own text merge: markers in %A, exit 1 marks the path conflicted.
    result = subprocess.run(['git', 'merge-file', '-L', 'ours', '-L', 'base', '-L', 'theirs',
                             str(ours_path), str(base_path), str(theirs_path)])
    return 1 if result.returncode else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
