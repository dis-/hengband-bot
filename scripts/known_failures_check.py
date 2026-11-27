#!/usr/bin/env python3
"""Run test modules and fail only on failures that ``tests/KNOWN_FAILURES.txt`` does not list.

MAINTAINABILITY.md rule 6 (2026-11-27): the tests failing on main are the ones listed in
``tests/KNOWN_FAILURES.txt``, and no change adds an unlisted failure.  A listed failure is fixed
from where one works, and its line removed.

    python scripts/known_failures_check.py tests.test_a test_b      # these modules
    python scripts/known_failures_check.py --all                    # every tests/test*.py
    python scripts/known_failures_check.py test_a --update-passing  # drop listed ids that pass

The modules run through ``scripts/test_timing_runner.py`` (its exclusions, its isolated history
and runtime directories) in batches of ``--batch`` modules, on at most two lanes (``--workers``,
capped at 2), so at most two test processes run at a time.  The exit code is 1 when a failing or
erroring test id of a module that ran is not listed (``FAIL``/``ERROR`` of a test, or the
module's ``(setUpClass)`` / ``(setUpModule)`` / ``(import)`` / ``(crash)``), else 0.  Listed ids of
the modules that ran and now pass are printed (``--update-passing`` removes them).

The file holds one id per line, sorted: ``tests.test_x.Class.test_name``, or
``tests.test_x.Class (setUpClass)``, ``tests.test_x (import)``.  Ids below a ``# flaky`` line
differ between two runs of their module; they are known either way and never offered for removal.
``--write`` records every failure of this run (after re-running the failing modules once to find
the flaky ones) as the new file.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
TESTS = ROOT / 'tests'
KNOWN_PATH = TESTS / 'KNOWN_FAILURES.txt'
FLAKY_MARKER = '# flaky'
MAX_WORKERS = 2
DEFAULT_BATCH = 40
BATCH_TIMEOUT = 3600
# Mutually serial modules (test_parallel_runner.SERIAL_MODULES) run in one batch of their own.
SERIAL_MODULES = frozenset({
    'tests.test_absorbing_states', 'tests.test_cli', 'tests.test_latch_onset_capture',
    'tests.test_policy_structure',
})

_HEADER = re.compile(r'^(FAIL|ERROR): (\S+) \(([^)\r\n]+)\)(?: \[[^\r\n]*\])?(?: \([^\r\n]*\))?\r?$',
                     re.MULTILINE)
_FAILED_IMPORT = 'unittest.loader._FailedTest.'


# ---------------------------------------------------------------- ids and the file
def normalize(name: str, identity: str) -> str:
    """One id for a FAIL/ERROR header ``<name> (<identity>)``."""
    if identity.startswith(_FAILED_IMPORT):
        module = identity[len(_FAILED_IMPORT):]
        return f'{module if module.startswith("tests.") else "tests." + module} (import)'
    if name in ('setUpClass', 'tearDownClass', 'setUpModule', 'tearDownModule'):
        return f'{identity} ({name})'
    return identity


def parse_failures(stderr: str) -> dict[str, str]:
    """id -> ``FAIL`` / ``ERROR`` from unittest's output (subTests fold into their test)."""
    out: dict[str, str] = {}
    for match in _HEADER.finditer(stderr):
        out.setdefault(normalize(match.group(2), match.group(3)), match.group(1))
    return out


def module_of(test_id: str) -> str:
    return '.'.join(test_id.split(' ', 1)[0].split('.')[:2])


def load_known(path: Path = KNOWN_PATH) -> tuple[set[str], set[str]]:
    """(known, flaky)."""
    known: set[str] = set()
    flaky: set[str] = set()
    if not path.exists():
        return known, flaky
    target = known
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower() == FLAKY_MARKER:
            target = flaky
            continue
        if line.startswith('#'):
            continue
        target.add(line)
    return known, flaky


def write_known(known, flaky, path: Path = KNOWN_PATH, header: str = '') -> None:
    lines = [f'# {row}' for row in header.splitlines() if row] if header else []
    lines += sorted(set(known) - set(flaky))
    if flaky:
        lines += [FLAKY_MARKER, *sorted(flaky)]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')


def compare(failing, known, flaky, ran_modules) -> tuple[list[str], list[str]]:
    """(new failures, listed ids of the modules that ran that now pass)."""
    failing = set(failing)
    new = sorted(failing - set(known) - set(flaky))
    passing = sorted(test_id for test_id in set(known) - set(flaky)
                     if module_of(test_id) in ran_modules and test_id not in failing)
    return new, passing


def flaky_between(first, second, modules) -> set[str]:
    """Ids of ``modules`` whose outcome differs between two runs."""
    return {test_id for test_id in set(first) ^ set(second) if module_of(test_id) in modules}


# ---------------------------------------------------------------- running
def all_modules() -> list[str]:
    return [f'tests.{path.stem}' for path in sorted(TESTS.glob('test*.py'))]


def normalize_modules(values) -> list[str]:
    out = []
    for value in values:
        for item in value.split(','):
            name = item.strip()
            if not name:
                continue
            name = Path(name).stem if name.endswith('.py') else name
            out.append(name if name.startswith('tests.') else f'tests.{name}')
    return list(dict.fromkeys(out))


def _weights(path: Path | None) -> dict[str, float]:
    candidates = [path] if path else [ROOT / 'jsonlog' / 'test-parallel-timings.json',
                                      ROOT / 'jsonlog' / 'test-timings.json']
    for candidate in candidates:
        try:
            payload = json.loads(candidate.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        totals: dict[str, float] = {}
        for row in payload.get('tests', []):
            module = module_of(str(row['id']))
            totals[module] = totals.get(module, 0.0) + float(row['seconds'])
        if totals:
            return totals
    return {}


def lanes(modules: list[str], workers: int, batch: int, weights: dict[str, float]) -> list[list[list[str]]]:
    """Per lane, its batches (each one test process)."""
    serial = [module for module in modules if module in SERIAL_MODULES]
    rest = [module for module in modules if module not in SERIAL_MODULES]
    default = sorted(weights.values())[len(weights) // 2] if weights else 1.0
    totals = [0.0] * workers
    assigned: list[list[str]] = [[] for _ in range(workers)]
    if serial:
        totals[0] += sum(weights.get(module, default) for module in serial)
    for module in sorted(rest, key=lambda name: (-weights.get(name, default), name)):
        index = min(range(workers), key=lambda item: (totals[item], item))
        assigned[index].append(module)
        totals[index] += weights.get(module, default)
    out = []
    for index in range(workers):
        chunks = [sorted(assigned[index])[start:start + batch]
                  for start in range(0, len(assigned[index]), batch)]
        if index == 0 and serial:
            chunks.insert(0, serial)
        out.append([chunk for chunk in chunks if chunk])
    return out


def run_batch(modules: list[str], temp_root: Path, label: str, log_dir: Path | None) -> tuple[dict[str, str], int]:
    """Failures of one test process and its test count."""
    work = Path(tempfile.mkdtemp(prefix=f'{label}-', dir=temp_root))
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join((str(ROOT / 'src'), str(TESTS)))
    env['TEMP'] = env['TMP'] = str(work)
    for name, sub in (('HENGBOT_HOME_HISTORY_DIR', 'home-history'), ('HENGBOT_RUNTIME_DIR', 'runtime')):
        (work / sub).mkdir()
        env[name] = str(work / sub)
    output = work / 'timings.json'
    command = [sys.executable, str(SCRIPTS / 'test_timing_runner.py'), '--modules', *modules,
               '--output', str(output), '--summary-output', str(work / 'summary.json'),
               '--top', '0', '--no-receipt']
    try:
        run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=BATCH_TIMEOUT)
        stderr, returncode = run.stderr, run.returncode
    except subprocess.TimeoutExpired as error:
        stderr = error.stderr if isinstance(error.stderr, str) else ''
        returncode = -1
    if log_dir is not None:
        (log_dir / f'{label}.stderr.log').write_text(stderr, encoding='utf-8')
    failures = parse_failures(stderr)
    try:
        count = len(json.loads(output.read_text(encoding='utf-8'))['tests'])
    except (OSError, ValueError, KeyError):
        count = 0
        # The process died before writing its record: every module of the batch is unknown.
        if returncode != 0:
            failures.update({f'{module} (crash)': 'ERROR' for module in modules})
    return failures, count


def run_modules(modules: list[str], workers: int = MAX_WORKERS, batch: int = DEFAULT_BATCH,
                timings: Path | None = None, log_dir: Path | None = None,
                progress=None) -> tuple[dict[str, str], int]:
    workers = max(1, min(MAX_WORKERS, workers, len(modules) or 1))
    plan = lanes(modules, workers, batch, _weights(timings))
    failures: dict[str, str] = {}
    total = 0
    with tempfile.TemporaryDirectory(prefix='hengbot-known-failures-') as directory:
        temp_root = Path(directory)

        def lane(index: int):
            found: dict[str, str] = {}
            count = 0
            for number, chunk in enumerate(plan[index]):
                result, ran = run_batch(chunk, temp_root, f'lane{index + 1}-batch{number + 1:03d}', log_dir)
                found.update(result)
                count += ran
                if progress:
                    progress(f'lane {index + 1}: batch {number + 1}/{len(plan[index])}, '
                             f'{ran} tests, {len(result)} failing')
            return found, count

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for found, count in pool.map(lane, range(workers)):
                failures.update(found)
                total += count
    return failures, total


# ---------------------------------------------------------------- the command
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('modules', nargs='*', help='test modules (tests.test_x, test_x or test_x.py)')
    parser.add_argument('--all', action='store_true', help='every tests/test*.py')
    parser.add_argument('--workers', type=int, default=MAX_WORKERS, help='lanes, at most 2')
    parser.add_argument('--batch', type=int, default=DEFAULT_BATCH, help='modules per test process')
    parser.add_argument('--timings', type=Path, help='a timing record to balance the lanes')
    parser.add_argument('--known', type=Path, default=KNOWN_PATH)
    parser.add_argument('--update-passing', action='store_true', help='remove listed ids that pass')
    parser.add_argument('--write', action='store_true',
                        help='record this run as the new list (re-runs the failing modules once)')
    parser.add_argument('--log-dir', type=Path, help='keep each test process stderr here')
    parser.add_argument('--verbose', action='store_true', help='print each batch as it ends')
    args = parser.parse_args(argv)
    modules = all_modules() if args.all else normalize_modules(args.modules)
    if not modules:
        parser.error('name test modules or pass --all')
    if args.log_dir:
        args.log_dir.mkdir(parents=True, exist_ok=True)
    progress = (lambda line: print(line, flush=True)) if args.verbose else None
    started = time.perf_counter()
    failures, total = run_modules(modules, args.workers, args.batch, args.timings, args.log_dir, progress)
    ran = set(modules)
    kinds = list(failures.values())
    print(f'known-failures: {len(modules)} module(s), {total} test(s), '
          f'{kinds.count("FAIL")} failure(s), {kinds.count("ERROR")} error(s), '
          f'{time.perf_counter() - started:.0f}s')
    known, flaky = load_known(args.known)
    if args.write:
        failing_modules = sorted({module_of(test_id) for test_id in failures})
        second, _ = run_modules(failing_modules, args.workers, args.batch, args.timings, None, progress)
        unstable = flaky_between(failures, second, set(failing_modules))
        write_known(set(failures) - unstable, unstable, args.known,
                    header='Tests failing on main (MAINTAINABILITY.md rule 6). Regenerate: '
                           'python scripts/known_failures_check.py --all --write')
        print(f'known-failures: wrote {len(set(failures) - unstable)} known and '
              f'{len(unstable)} flaky id(s) to {args.known}')
        return 0
    new, passing = compare(failures, known, flaky, ran)
    for test_id in new:
        print(f'NEW {failures[test_id]}: {test_id}')
    for test_id in passing:
        print(f'now passes (remove from {args.known.name}): {test_id}')
    if args.update_passing and passing:
        write_known(known - set(passing), flaky, args.known, header=_header(args.known))
        print(f'known-failures: removed {len(passing)} passing id(s)')
    print(f'known-failures: {len(new)} new, {len(failures) - len(new)} known, '
          f'{len(passing)} listed now passing')
    return 1 if new else 0


def _header(path: Path) -> str:
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return ''
    out = []
    for line in lines:
        if not line.startswith('#') or line.strip().lower() == FLAKY_MARKER:
            break
        out.append(line[1:].strip())
    return '\n'.join(out)


if __name__ == '__main__':
    raise SystemExit(main())
