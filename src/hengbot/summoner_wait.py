"""Own the evidence collected while waiting for summoners at a choke."""

from dataclasses import dataclass, field
from functools import wraps

from hengbot.model import Position


SUMMONER_WAIT_GAME_TURNS = 50


@dataclass
class SummonerWait:
    floor: tuple
    position: Position
    targets: set[tuple[int, int]] = field(default_factory=set)
    holding: bool = False
    started: dict[tuple[int, int], tuple[int, int]] = field(default_factory=dict)
    refused: dict[tuple[int, int], tuple[int, Position]] = field(default_factory=dict)

    def observe(self, policy, snapshot, monsters):
        """A closer monster invalidates both its wait and its stale verdict."""
        if self.position != snapshot.player.position:
            self.started.clear()
            self.targets.clear()
            self.holding = False
            self.position = snapshot.player.position
        current = {(m.index, m.race_id): m for m in monsters}
        for identity, (turn, distance) in list(self.started.items()):
            monster = current.get(identity)
            if monster is None or monster.distance < distance or snapshot.turn < turn:
                del self.started[identity]
        for identity, (distance, position) in list(self.refused.items()):
            monster = current.get(identity)
            if (monster is not None and monster.position != position
                    and monster.distance < distance):
                del self.refused[identity]
                floor, remembered = getattr(policy, "_immobile_summoner_memory", (None, {}))
                if floor == snapshot.floor_key and remembered.get(position) == monster.race_id:
                    del remembered[position]


def forget_floor_visit(policy):
    """End this floor visit's summoner evidence (D46).

    The memory, its avoid cells and the wait clocks were keyed by the floor
    key alone, and leaving a level does not run the immobile-summoner rung's
    own reset (it returns early when nothing is remembered there), so a
    summoner remembered on an earlier Castle 22F survived into a new level
    with the same (dungeon, level, quest) key.  Called on every floor
    transition beside the other per-visit latches.
    """
    policy._immobile_summoner_memory = (None, {})
    policy._immobile_summoner_avoid_cells = set()
    policy._summoner_wait = None


def wait_state(policy, snapshot):
    state = getattr(policy, "_summoner_wait", None)
    if state is None or state.floor != snapshot.floor_key:
        state = SummonerWait(snapshot.floor_key, snapshot.player.position)
        policy._summoner_wait = state
    state.observe(policy, snapshot, policy._perceived_hostiles(snapshot))
    return state


def hold_key(policy, snapshot, monsters, *, continuing=False):
    """Start clocks only for the summoners this selected wait is awaiting."""
    state = wait_state(policy, snapshot)
    waiting = {
        (m.index, m.race_id): m for m in monsters
        if m.can_summon and not m.asleep
        and (not continuing or not state.holding or (m.index, m.race_id) in state.targets)
    }
    state.targets = set(waiting)
    state.holding = True
    state.started = {
        identity: state.started.get(identity, (snapshot.turn, m.distance))
        for identity, m in waiting.items()
    }
    policy.last_reason = "summoner:hold-choke"
    return "5"


def wait_expired(policy, snapshot, monster):
    """Keep the avoidance verdict after handing an expired wait to retreat."""
    state = wait_state(policy, snapshot)
    identity = (monster.index, monster.race_id)
    start = state.started.get(identity)
    if start is not None and snapshot.turn - start[0] >= SUMMONER_WAIT_GAME_TURNS:
        state.refused[identity] = (start[1], monster.position)
    return identity in state.refused


def summoner_wait_decision(decide):
    @wraps(decide)
    def wrapped(policy, snapshot):
        state = wait_state(policy, snapshot)
        key = None
        try:
            key = decide(policy, snapshot)
            return key
        finally:
            if key != "5" or policy.last_reason != "summoner:hold-choke":
                state.started.clear()
                state.targets.clear()
                state.holding = False
    return wrapped
