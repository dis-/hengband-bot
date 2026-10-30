"""Slice-0 work coverage receipts, strictly observational.

Source sites, not reason prefixes, authorize a coverage record. A scoped return
observer captures the actually executed producer/delegation chain, including
legacy direct branches and rewrites. This is not semantic effect accounting.
Missing coverage is fail-closed in the receipt's verdict; the operator explicitly
keeps actuation unchanged in this slice. Nothing reads that verdict to pick keys.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache, wraps
from inspect import CO_OPTIMIZED
import json
import opcode
from pathlib import Path
import sys
import threading
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


def _note_return(state, frame, site, entry, value):
    """The observer's per-frame filter, shared by both collectors."""
    policy = state['policy']
    if entry or frame.f_locals.get('self') is policy:
        caller = frame.f_back
        state['returns'].append(dict(site=site, key=str(value), line=frame.f_lineno,
                                     caller=frame_site(caller) if caller else None,
                                     policy_reason=getattr(policy, 'last_reason', None)))


@contextmanager
def _profile_returns(state):
    """The original observer: a per-thread sys.setprofile hook on every call.

    It runs a Python callback for every call and return of every function,
    including C functions, which made town decisions 2-4 times slower (D39).
    It is kept only as the fallback when no sys.monitoring tool id is free,
    and as the reference the equivalence check compares _monitor_returns with.
    """
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
        _note_return(state, frame, site, entry, value)

    sys.setprofile(profile)
    try:
        yield
    finally:
        sys.setprofile(previous)


_MONITORING = getattr(sys, 'monitoring', None)
_RETURN_EVENTS = (_MONITORING.events.PY_RETURN | _MONITORING.events.PY_YIELD
                  if _MONITORING else 0)
_RETURN_CONST = opcode.opmap.get('RETURN_CONST')
_TOOL_NAME = 'hengbot-town-work'
_tool = None
_observing = []
_targets = {}


def _return_target(code, frame, policy):
    """(site, manifest entry) when a return of this code can be recorded.

    This is the profile hook's filter without its per-event checks (value,
    module, 'self'). It depends only on the code and the policy's class, so
    the observer disables a location whose returns can never be recorded.
    """
    site = code_site(code)
    if site is None or site.startswith('town_work.py:'):
        return None
    entry = manifest().get(site)
    if entry:
        return None if entry['classification'] == 'data' else (site, entry)
    # An unknown site is recorded only when its frame's 'self' is the
    # policy. An optimized frame has no 'self' unless its code names it, and
    # a method (or closure) of a class the policy is not an instance of gets
    # the policy as 'self' only when called explicitly as Class.method(policy).
    if (code.co_flags & CO_OPTIMIZED and 'self' not in code.co_varnames
            and 'self' not in code.co_cellvars and 'self' not in code.co_freevars):
        return None
    owner = frame.f_globals.get(code.co_qualname.split('.', 1)[0])
    if isinstance(owner, type) and not isinstance(policy, owner):
        return None
    return site, entry


def _on_return(code, offset, value):
    # Keyed by id: hashing a code object hashes its bytecode and constants.
    # The entry keeps the code alive, so its id cannot be reused.
    target = _targets.get(id(code))
    if target is None:
        state = _deciding_state()
        if state is None:
            return None
        found = _return_target(code, sys._getframe(1), state['policy'])
        target = _targets[id(code)] = (code, *found, code.co_code) if found else (code, None)
    if target[1] is None:
        return _MONITORING.DISABLE
    if not isinstance(value, str) or not value:
        # A constant return location returns this same value every time.
        return _MONITORING.DISABLE if target[3][offset] == _RETURN_CONST else None
    frame = sys._getframe(1)
    if not str(frame.f_globals.get('__name__', '')).startswith('hengbot.'):
        return None
    thread = threading.get_ident()
    for state in _observing:
        # sys.setprofile observed only the deciding thread; so does this.
        if state['thread'] == thread:
            _note_return(state, frame, target[1], target[2], value)
    return None


def _deciding_state():
    thread = threading.get_ident()
    return next((state for state in reversed(_observing) if state['thread'] == thread), None)


def _monitoring_tool():
    """A free sys.monitoring tool id for the observer, or None."""
    global _tool
    if _tool is not None:
        return _tool
    if _MONITORING is None:
        return None
    for tool in (3, 4):
        if _MONITORING.get_tool(tool) is None:
            _MONITORING.use_tool_id(tool, _TOOL_NAME)
            _MONITORING.register_callback(tool, _MONITORING.events.PY_RETURN, _on_return)
            _MONITORING.register_callback(tool, _MONITORING.events.PY_YIELD, _on_return)
            _tool = tool
            return tool
    return None


@contextmanager
def _monitor_returns(state):
    """Record the same returns as _profile_returns with sys.monitoring.

    Only PY_RETURN and PY_YIELD (the profile hook's 'return' event) are
    watched, and locations that can never be recorded are disabled, so the
    observer does not pay for every call, C call and helper return.
    """
    tool = _monitoring_tool()
    if tool is None:
        with _profile_returns(state) as observed:
            yield observed
        return
    state['thread'] = threading.get_ident()
    _observing.append(state)
    if len(_observing) == 1:
        _MONITORING.set_events(tool, _RETURN_EVENTS)
    try:
        yield
    finally:
        _observing.remove(state)
        if not _observing:
            _MONITORING.set_events(tool, 0)


_collect_returns = _monitor_returns


def town_work_decision(function):
    @wraps(function)
    def run(policy, board):
        _receipts[policy] = []
        _records.pop(policy, None)
        if not town_context(board):
            return function(policy, board)
        state = dict(policy=policy, board=board, returns=[], offers=[])
        token = _active.set(state)
        try:
            with _collect_returns(state):
                key = function(policy, board)
        finally:
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
