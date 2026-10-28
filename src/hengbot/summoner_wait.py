"""Own the evidence collected while waiting for summoners at a choke."""

from dataclasses import dataclass, field
from functools import wraps


SUMMONER_WAIT_GAME_TURNS = 50


@dataclass
class SummonerWait:
    floor: tuple
    position: object
    started: dict = field(default_factory=dict)
    refused: dict = field(default_factory=dict)

    def observe(self, policy, snapshot, monsters):
        """A closer monster invalidates both its wait and its stale verdict."""
        if self.position != snapshot.player.position:
            self.started.clear()
            self.position = snapshot.player.position
        current = {(m.index, m.race_id): m for m in monsters}
        for identity, (turn, distance) in list(self.started.items()):
            monster = current.get(identity)
            if monster is None or monster.distance < distance or snapshot.turn < turn:
                del self.started[identity]
        for identity, (distance, position) in list(self.refused.items()):
            monster = current.get(identity)
            if monster is not None and monster.distance < distance:
                del self.refused[identity]
                floor, remembered = getattr(policy, "_immobile_summoner_memory", (None, {}))
                if floor == snapshot.floor_key and remembered.get(position) == monster.race_id:
                    del remembered[position]


def wait_state(policy, snapshot):
    state = getattr(policy, "_summoner_wait", None)
    if state is None or state.floor != snapshot.floor_key:
        state = SummonerWait(snapshot.floor_key, snapshot.player.position)
        policy._summoner_wait = state
    state.observe(policy, snapshot, policy._perceived_hostiles(snapshot))
    return state


def hold_key(policy, snapshot, monsters):
    """Start clocks only for the summoners this selected wait is awaiting."""
    state = wait_state(policy, snapshot)
    waiting = {
        (m.index, m.race_id): m for m in monsters
        if m.can_summon and not m.asleep
    }
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
        try:
            return decide(policy, snapshot)
        finally:
            if policy.last_reason != "summoner:hold-choke":
                state.started.clear()
    return wrapped
