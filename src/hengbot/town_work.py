"""Slice-0 work coverage receipts, strictly observational.

Source sites, not reason prefixes, authorize a coverage record. A scoped return
observer captures the actually executed producer/delegation chain, including
legacy direct branches and rewrites. This is not semantic effect accounting.
Missing coverage is fail-closed in the receipt's verdict; the operator explicitly
keeps actuation unchanged in this slice. Nothing reads that verdict to pick keys.
"""
from __future__ import annotations

from contextvars import ContextVar
from functools import lru_cache, wraps
import json
from pathlib import Path
import sys
from weakref import WeakKeyDictionary

UNMAPPED = 'town:blocked:work-contract:unmapped-producer'
_active = ContextVar('town_work_coverage', default=None)
_receipts = WeakKeyDictionary()
_records = WeakKeyDictionary()


@lru_cache(maxsize=1)
def manifest():
    try:
        return json.loads(Path(__file__).with_name('town_work_sites.json').read_text(encoding='utf8'))
    except (OSError, ValueError):
        # A broken installation has no admission coverage. Keep the operator's
        # slice-0 actuation unchanged and emit missing-contract receipts.
        return {}


def town_context(board):
    if isinstance(board, dict):
        floor = board.get('floor') or {}
        fallback = floor.get('dungeon_id') == 0 and floor.get('level') == 0
        return bool(floor.get('in_town', floor.get('town', fallback))
                    or board.get('in_town', False) or board.get('store') is not None)
    return bool(getattr(board, 'in_town', False) or getattr(board, 'store', None) is not None)


def frame_site(frame):
    return code_site(frame.f_code)


@lru_cache(maxsize=None)
def code_site(code):
    filename = Path(code.co_filename)
    try:
        filename = filename.resolve().relative_to(Path(__file__).resolve().parent).as_posix()
    except ValueError:
        return None
    qualified = code.co_qualname.replace('.<locals>', '')
    # Anonymous callback execution delegates to its lexical reviewed caller.
    if qualified.endswith('.<lambda>'):
        qualified = qualified.removesuffix('.<lambda>')
    return f'{filename}:{qualified}'


def work_record(site, key, *, sequence=None, caller=None, line=None, work_id=None):
    entry = manifest().get(site)
    if entry is None or entry['classification'] in {'data', 'dungeon-only'}:
        return None
    return dict(schema=1, producer=site, caller=caller, line=line,
                sequence=sequence, key=str(key), work_id=work_id or f'{site}:{sequence}',
                rows=entry['rows'], admission='town_work.validate_emit',
                observer='shadow-v1', effect_credit=False,
                delegation=entry.get('delegation'), reconstructed=False)


def validate_emit(board, key, record, *, seam, producer=None):
    """One pure validator for offers, policy output, driver and physical tails.

    Returning an invalid verdict must never be mistaken for admission. The
    shadow-only caller deliberately ignores it for actuation in slice 0.
    """
    required = bool(key) and town_context(board)
    mapped = (isinstance(record, dict)
              and record.get('producer') in manifest()
              and manifest()[record['producer']]['classification'] not in {'data', 'dungeon-only'}
              and bool(record.get('work_id')) and bool(record.get('rows'))
              and record.get('key') == str(key))
    return dict(schema=1, mode='shadow', seam=seam, key=key,
                producer=producer or (record or {}).get('producer'),
                required=required, valid=not required or bool(mapped),
                reason=UNMAPPED if required and not mapped else None,
                work=record, effect_credit=False)


def note(policy, receipt):
    _receipts.setdefault(policy, []).append(receipt)
    return receipt


def receipts(policy):
    return list(_receipts.get(policy, ()))


def current_record(policy, key):
    record = _records.get(policy)
    return record if record and record.get('key') == str(key) else None


def bind_driver_override(policy, key, *, site):
    """An explicit driver replacement opens a mapped cleanup child."""
    record = driver_record(policy, key, site=site,
                           sequence=getattr(policy, '_decision_sequence', None))
    if record:
        _records[policy] = record


def observe_offer(policy, key, work_id):
    active = _active.get()
    if not active or active['policy'] is not policy:
        return
    frame = sys._getframe(1)
    while frame and frame.f_code.co_name in {
            '_offer_execution', '_offer_execution_awaiting', 'observe_offer'}:
        frame = frame.f_back
    site = frame_site(frame) if frame else None
    record = work_record(site, key, sequence=getattr(policy, '_decision_sequence', None),
                         line=frame.f_lineno if frame else None, work_id=work_id)
    receipt = note(policy, validate_emit(active['board'], key, record,
                                        seam='offer', producer=site))
    active['offers'].append(receipt)


def town_work_decision(function):
    @wraps(function)
    def run(policy, board):
        _receipts[policy] = []
        _records.pop(policy, None)
        if not town_context(board):
            return function(policy, board)
        state = dict(policy=policy, board=board, returns=[], offers=[])
        token = _active.set(state)
        previous = sys.getprofile()

        def profile(frame, event, value):
            if previous:
                previous(frame, event, value)
            if event != 'return' or not isinstance(value, str) or not value:
                return
            if not str(frame.f_globals.get('__name__', '')).startswith('hengbot.'):
                return
            site = frame_site(frame)
            if site is None or site.startswith('town_work.py:'):
                return
            entry = manifest().get(site)
            # Known observational helpers cannot mint a work record, even if
            # their incidental string value happens to equal a command byte.
            if entry and entry['classification'] == 'data':
                return
            if entry or frame.f_locals.get('self') is policy:
                caller = frame.f_back
                state['returns'].append(dict(site=site, key=str(value), line=frame.f_lineno,
                                              caller=frame_site(caller) if caller else None,
                                              policy_reason=getattr(policy, 'last_reason', None)))

        sys.setprofile(profile)
        try:
            key = function(policy, board)
        finally:
            sys.setprofile(previous)
            _active.reset(token)
        matching = [r for r in state['returns'] if r['key'] == str(key)]
        unknown = [r for r in matching if r['site'] not in manifest()
                   or manifest()[r['site']]['classification'] == 'dungeon-only']
        # A reviewed decision wrapper is allowed to describe its literal WAIT,
        # cleanup or refusal branch, but cannot hide an unknown returning child.
        selected = next((r for r in reversed(matching)
                         if manifest().get(r['site'], {}).get('classification') == 'producer'),
                        matching[-1] if matching else None)
        record = (work_record(selected['site'], key,
                              sequence=getattr(policy, '_decision_sequence', None),
                              caller=selected['caller'], line=selected['line'])
                  if selected and not unknown else None)
        if record:
            record['chain'] = matching
            record['policy_reason'] = getattr(policy, 'last_reason', None)
            # An offer is usable only for the exact surviving command and
            # source chain. Rejected/rewritten offers cannot authorize a send.
            offer = next((r['work'] for r in reversed(state['offers'])
                          if r['valid'] and r['work'] and r['key'] == key
                          and r['work']['producer'] in {m['site'] for m in matching}), None)
            if offer:
                record['offered_work_id'] = offer['work_id']
            _records[policy] = record
        receipt = validate_emit(board, key, record, seam='policy-final',
                                producer=unknown[0]['site'] if unknown else None)
        receipt['policy_reason'] = getattr(policy, 'last_reason', None)
        note(policy, receipt)
        return key
    return run


def driver_record(policy, key, *, site, sequence=None):
    """Bind a driver command to its concrete mapped call site.

    A changed driver key gets a cleanup/routing child, retaining its parent's
    record. No reason-based synthesis and no borrowing a mismatched policy key.
    """
    parent = _records.get(policy) if policy is not None else None
    record = work_record(site, key, sequence=sequence)
    if record and parent:
        record['parent'] = parent
    return record
