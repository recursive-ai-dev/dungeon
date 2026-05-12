"""
AI module for the dungeon game.

Provides various AI behaviors for entities, from simple hostile melee
to sophisticated state-driven NPCs with pathfinding.
"""

from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Iterator, Protocol

if TYPE_CHECKING:
    from dungeon.engine import GameEngine
    from dungeon.entities import Entity


# ---------------------------------------------------------------------------
# Action Results
# ---------------------------------------------------------------------------

class ActionResult(Enum):
    """Outcome of an AI action."""
    SUCCESS = auto()
    FAILURE = auto()
    IMPOSSIBLE = auto()
    NO_ACTION = auto()


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

class HasPosition(Protocol):
    """Protocol for objects with x, y coordinates."""
    x: int
    y: int


# ---------------------------------------------------------------------------
# Pathfinding
# ---------------------------------------------------------------------------

@dataclass(order=True)
class _Node:
    """A* search node (internal)."""
    f_score: float
    position: tuple[int, int] = field(compare=False)
    g_score: float = field(compare=False, default=0.0)
    parent: tuple[int, int] | None = field(compare=False, default=None)


class Pathfinder:
    """A* pathfinding on the game map."""

    def __init__(self, engine: GameEngine):
        self.engine = engine

    def _heuristic(self, a: tuple[int, int], b: tuple[int, int]) -> float:
        """Chebyshev distance (diagonal movement allowed)."""
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

    def _neighbors(self, pos: tuple[int, int]) -> Iterator[tuple[int, int]]:
        """Yield walkable neighbor positions."""
        x, y = pos
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if self.engine.game_map.is_in_bounds(nx, ny) and self.engine.game_map.is_walkable(nx, ny):
                    # Skip if another entity blocks (except target)
                    blocking = self.engine.get_blocking_entity_at(nx, ny)
                    if blocking is None or blocking == self.engine.player:
                        yield (nx, ny)

    def find_path(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
        max_steps: int = 50,
    ) -> list[tuple[int, int]] | None:
        """
        Find a path from *start* to *goal* using A*.

        Returns a list of positions (excluding start, including goal)
        or ``None`` if no path exists within *max_steps*.
        """
        if start == goal:
            return []

        open_set: list[_Node] = []
        heapq.heappush(open_set, _Node(f_score=0.0, position=start, g_score=0.0))
        closed: set[tuple[int, int]] = set()
        g_scores: dict[tuple[int, int], float] = {start: 0.0}
        parents: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

        while open_set:
            current = heapq.heappop(open_set)
            if current.position == goal:
                # Reconstruct path
                path: list[tuple[int, int]] = []
                node = goal
                while node is not None:
                    path.append(node)
                    node = parents[node]
                path.reverse()
                return path[1:]  # exclude start

            closed.add(current.position)

            if len(closed) > max_steps:
                return None

            for neighbor in self._neighbors(current.position):
                if neighbor in closed:
                    continue
                tentative_g = g_scores[current.position] + 1.0
                if neighbor not in g_scores or tentative_g < g_scores[neighbor]:
                    parents[neighbor] = current.position
                    g_scores[neighbor] = tentative_g
                    f = tentative_g + self._heuristic(neighbor, goal)
                    heapq.heappush(open_set, _Node(f_score=f, position=neighbor, g_score=tentative_g))

        return None

    def next_step_toward(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
    ) -> tuple[int, int] | None:
        """Return the first step toward *goal*, or ``None``."""
        path = self.find_path(start, goal)
        return path[0] if path else None


# ---------------------------------------------------------------------------
# Base AI
# ---------------------------------------------------------------------------

class BaseAI:
    """Abstract base for all entity AI controllers."""

    entity: Entity

    def __init__(self) -> None:
        pass

    def perform(self, engine: GameEngine) -> ActionResult:
        """Execute one turn of behavior."""
        raise NotImplementedError

    def on_damage_taken(self, engine: GameEngine, attacker: Entity | None) -> None:
        """Hook called when the entity takes damage."""
        pass

    def on_entity_death(self, engine: GameEngine) -> None:
        """Hook called when the entity dies."""
        pass

    def get_pathfinder(self, engine: GameEngine) -> Pathfinder:
        """Return a pathfinder instance bound to the engine."""
        return Pathfinder(engine)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def chebyshev_distance(a: HasPosition, b: HasPosition) -> int:
    """Chebyshev (king) distance between two positions."""
    return max(abs(a.x - b.x), abs(a.y - b.y))


def euclidean_distance(a: HasPosition, b: HasPosition) -> float:
    """Euclidean distance between two positions."""
    return math.hypot(a.x - b.x, a.y - b.y)


def direction_toward(
    source: HasPosition, target: HasPosition
) -> tuple[int, int]:
    """Return the single-step direction vector from *source* to *target*."""
    dx = target.x - source.x
    dy = target.y - source.y
    move_x = (dx // abs(dx)) if dx != 0 else 0
    move_y = (dy // abs(dy)) if dy != 0 else 0
    return move_x, move_y


def can_see(
    engine: GameEngine,
    viewer: HasPosition,
    target: HasPosition,
    max_range: int | None = None,
) -> bool:
    """Check if *viewer* can see *target* (FOV + range)."""
    dist = chebyshev_distance(viewer, target)
    if max_range is not None and dist > max_range:
        return False
    if not engine.game_map.is_in_bounds(target.x, target.y):
        return False
    tile = engine.game_map.tiles[target.y][target.x]
    return getattr(tile, "visible", False)


def _bark(entity: Entity, engine: GameEngine, chance: float = 0.15) -> None:
    """Emit a random bark if the entity has any and RNG hits."""
    if getattr(entity, "barks", None) and random.random() < chance:
        bark = random.choice(entity.barks)
        engine.messages.append(f"[italic]{entity.name}: '{bark}'[/italic]")


# ---------------------------------------------------------------------------
# Hostile AI (with pathfinding)
# ---------------------------------------------------------------------------

class HostileAI(BaseAI):
    """
    Aggressive melee AI.

    * If the player is visible and within 1 tile → attack.
    * If visible but farther → pathfind toward the player.
    * If not visible → wait (or wander if a ``wander_chance`` is set).
    """

    def __init__(self, wander_chance: float = 0.0) -> None:
        super().__init__()
        self.wander_chance = wander_chance
        self._last_known_player_pos: tuple[int, int] | None = None

    def perform(self, engine: GameEngine) -> ActionResult:
        players = list(engine.players.values())
        if not players:
            return ActionResult.NO_ACTION

        player = self._pick_target(players)
        dist = chebyshev_distance(self.entity, player)
        visible = can_see(engine, self.entity, player)

        if visible:
            self._last_known_player_pos = (player.x, player.y)
            _bark(self.entity, engine)

        if dist <= 1:
            return self._attack(player, engine)

        if visible or self._last_known_player_pos:
            goal = (player.x, player.y) if visible else self._last_known_player_pos
            # type guard
            if goal is None:
                return self._wander_or_wait(engine)
            return self._move_toward(goal, engine)

        return self._wander_or_wait(engine)

    def _pick_target(self, players: list[Entity]) -> Entity:
        """Select the closest player."""
        return min(players, key=lambda p: chebyshev_distance(self.entity, p))

    def _attack(self, target: Entity, engine: GameEngine) -> ActionResult:
        """Melee attack the target."""
        if not hasattr(self.entity, "fighter") or not hasattr(target, "fighter"):
            return ActionResult.IMPOSSIBLE

        damage = self.entity.fighter.power - target.fighter.defense
        if damage > 0:
            target.fighter.hp -= damage
            engine.messages.append(
                f"The {self.entity.name} attacks {target.name} for {damage} HP!"
            )
        else:
            engine.messages.append(
                f"The {self.entity.name} attacks {target.name} but does no damage."
            )

        if target.fighter.hp <= 0:
            engine.messages.append(f"{target.name} has died!")
        return ActionResult.SUCCESS

    def _move_toward(
        self, goal: tuple[int, int], engine: GameEngine
    ) -> ActionResult:
        """Pathfind and take one step toward *goal*."""
        pf = self.get_pathfinder(engine)
        nxt = pf.next_step_toward((self.entity.x, self.entity.y), goal)
        if nxt is None:
            return self._wander_or_wait(engine)
        dx, dy = nxt[0] - self.entity.x, nxt[1] - self.entity.y
        self.entity.move(dx, dy)
        return ActionResult.SUCCESS

    def _wander_or_wait(self, engine: GameEngine) -> ActionResult:
        """Random idle movement or do nothing."""
        if random.random() < self.wander_chance:
            dx, dy = random.choice([
                (-1, -1), (-1, 0), (-1, 1),
                (0, -1),           (0, 1),
                (1, -1),  (1, 0),  (1, 1),
            ])
            new_x, new_y = self.entity.x + dx, self.entity.y + dy
            if (
                not engine.get_blocking_entity_at(new_x, new_y)
                and engine.game_map.is_walkable(new_x, new_y)
            ):
                self.entity.move(dx, dy)
                return ActionResult.SUCCESS
        return ActionResult.NO_ACTION


# ---------------------------------------------------------------------------
# Ranged AI
# ---------------------------------------------------------------------------

class RangedAI(BaseAI):
    """
    Hostile AI that keeps distance and uses ranged attacks.

    * If player is too close → try to back away.
    * If in optimal range → shoot.
    * Otherwise → move to optimal range.
    """

    def __init__(
        self,
        optimal_range: int = 4,
        min_range: int = 2,
        flee_range: int = 1,
        wander_chance: float = 0.0,
    ) -> None:
        super().__init__()
        self.optimal_range = optimal_range
        self.min_range = min_range
        self.flee_range = flee_range
        self.wander_chance = wander_chance
        self._last_known_player_pos: tuple[int, int] | None = None

    def perform(self, engine: GameEngine) -> ActionResult:
        players = list(engine.players.values())
        if not players:
            return ActionResult.NO_ACTION

        player = min(players, key=lambda p: chebyshev_distance(self.entity, p))
        dist = chebyshev_distance(self.entity, player)
        visible = can_see(engine, self.entity, player)

        if visible:
            self._last_known_player_pos = (player.x, player.y)
            _bark(self.entity, engine)

        if visible and dist <= self.flee_range:
            return self._flee_from((player.x, player.y), engine)

        if visible and self.min_range <= dist <= self.optimal_range:
            return self._shoot(player, engine)

        goal = (player.x, player.y) if visible else self._last_known_player_pos
        if goal:
            return self._move_toward(goal, engine)
        return self._wander_or_wait(engine)

    def _flee_from(
        self, threat: tuple[int, int], engine: GameEngine
    ) -> ActionResult:
        """Move directly away from *threat*."""
        dx = self.entity.x - threat[0]
        dy = self.entity.y - threat[1]
        move_x = (dx // abs(dx)) if dx != 0 else 0
        move_y = (dy // abs(dy)) if dy != 0 else 0
        new_x, new_y = self.entity.x + move_x, self.entity.y + move_y
        if (
            not engine.get_blocking_entity_at(new_x, new_y)
            and engine.game_map.is_walkable(new_x, new_y)
        ):
            self.entity.move(move_x, move_y)
            return ActionResult.SUCCESS
        return self._wander_or_wait(engine)

    def _shoot(self, target: Entity, engine: GameEngine) -> ActionResult:
        """Fire a ranged attack at *target*."""
        # Hook for projectile / spell logic; default falls back to melee
        engine.messages.append(
            f"The {self.entity.name} fires at {target.name}!"
        )
        # Placeholder: integrate with your projectile system here
        return ActionResult.SUCCESS

    def _move_toward(
        self, goal: tuple[int, int], engine: GameEngine
    ) -> ActionResult:
        pf = self.get_pathfinder(engine)
        nxt = pf.next_step_toward((self.entity.x, self.entity.y), goal)
        if nxt is None:
            return self._wander_or_wait(engine)
        dx, dy = nxt[0] - self.entity.x, nxt[1] - self.entity.y
        self.entity.move(dx, dy)
        return ActionResult.SUCCESS

    def _wander_or_wait(self, engine: GameEngine) -> ActionResult:
        if random.random() < self.wander_chance:
            dx, dy = random.choice([
                (-1, -1), (-1, 0), (-1, 1),
                (0, -1),           (0, 1),
                (1, -1),  (1, 0),  (1, 1),
            ])
            new_x, new_y = self.entity.x + dx, self.entity.y + dy
            if (
                not engine.get_blocking_entity_at(new_x, new_y)
                and engine.game_map.is_walkable(new_x, new_y)
            ):
                self.entity.move(dx, dy)
                return ActionResult.SUCCESS
        return ActionResult.NO_ACTION


# ---------------------------------------------------------------------------
# Patrol AI
# ---------------------------------------------------------------------------

class PatrolAI(BaseAI):
    """
    Walks between a list of waypoints.

    * If player is spotted → switches to ``alert_ai`` (default HostileAI).
    * Otherwise → patrol waypoints in order.
    """

    def __init__(
        self,
        waypoints: list[tuple[int, int]],
        alert_ai: BaseAI | None = None,
        sight_range: int | None = None,
        loop: bool = True,
    ) -> None:
        super().__init__()
        self.waypoints = waypoints
        self.alert_ai = alert_ai or HostileAI()
        self.sight_range = sight_range
        self.loop = loop
        self._current_index = 0
        self._direction = 1

    def perform(self, engine: GameEngine) -> ActionResult:
        players = list(engine.players.values())
        for player in players:
            if can_see(engine, self.entity, player, self.sight_range):
                _bark(self.entity, engine, chance=0.25)
                self.entity.ai = self.alert_ai
                self.entity.ai.entity = self.entity
                return self.entity.ai.perform(engine)

        if not self.waypoints:
            return ActionResult.NO_ACTION

        target = self.waypoints[self._current_index]
        if (self.entity.x, self.entity.y) == target:
            self._advance_waypoint()
            return ActionResult.SUCCESS

        return self._move_toward(target, engine)

    def _advance_waypoint(self) -> None:
        self._current_index += self._direction
        if self._current_index >= len(self.waypoints):
            if self.loop:
                self._current_index = 0
            else:
                self._direction = -1
                self._current_index = len(self.waypoints) - 2
        elif self._current_index < 0:
            self._direction = 1
            self._current_index = 1 if len(self.waypoints) > 1 else 0

    def _move_toward(
        self, goal: tuple[int, int], engine: GameEngine
    ) -> ActionResult:
        pf = self.get_pathfinder(engine)
        nxt = pf.next_step_toward((self.entity.x, self.entity.y), goal)
        if nxt is None:
            return ActionResult.FAILURE
        dx, dy = nxt[0] - self.entity.x, nxt[1] - self.entity.y
        self.entity.move(dx, dy)
        return ActionResult.SUCCESS


# ---------------------------------------------------------------------------
# Flee AI
# ---------------------------------------------------------------------------

class FleeAI(BaseAI):
    """
    Runs away from the nearest player.

    Useful for harmless creatures or low-HP enemies.
    """

    def __init__(self, panic_hp_percent: float = 0.3) -> None:
        super().__init__()
        self.panic_hp_percent = panic_hp_percent

    def perform(self, engine: GameEngine) -> ActionResult:
        players = list(engine.players.values())
        if not players:
            return ActionResult.NO_ACTION

        player = min(players, key=lambda p: chebyshev_distance(self.entity, p))
        dist = chebyshev_distance(self.entity, player)

        if dist > 8:
            return ActionResult.NO_ACTION

        # Move away
        dx = self.entity.x - player.x
        dy = self.entity.y - player.y
        move_x = (dx // abs(dx)) if dx != 0 else 0
        move_y = (dy // abs(dy)) if dy != 0 else 0

        # Prefer lateral escape if direct is blocked
        candidates = [
            (move_x, move_y),
            (move_x, 0),
            (0, move_y),
            (-move_y, move_x),   # perpendicular
            (move_y, -move_x),   # perpendicular other way
        ]
        for mx, my in candidates:
            nx, ny = self.entity.x + mx, self.entity.y + my
            if (
                not engine.get_blocking_entity_at(nx, ny)
                and engine.game_map.is_walkable(nx, ny)
            ):
                self.entity.move(mx, my)
                return ActionResult.SUCCESS

        return ActionResult.FAILURE

    def on_damage_taken(self, engine: GameEngine, attacker: Entity | None) -> None:
        """If HP drops below threshold, switch to permanent flee."""
        if (
            hasattr(self.entity, "fighter")
            and self.entity.fighter.hp
            / max(1, getattr(self.entity.fighter, "max_hp", self.entity.fighter.hp))
            <= self.panic_hp_percent
        ):
            _bark(self.entity, engine, chance=0.5)


# ---------------------------------------------------------------------------
# Confused AI (decorator / state wrapper)
# ---------------------------------------------------------------------------

class ConfusedAI(BaseAI):
    """
    Temporarily replaces another AI with random wandering.

    After *num_turns* expire, the original AI is restored.
    """

    def __init__(self, old_ai: BaseAI, num_turns: int) -> None:
        super().__init__()
        self.old_ai = old_ai
        self.num_turns = num_turns

    def perform(self, engine: GameEngine) -> ActionResult:
        if self.num_turns <= 0:
            self.entity.ai = self.old_ai
            self.entity.ai.entity = self.entity
            engine.messages.append(
                f"The {self.entity.name} is no longer confused!"
            )
            return ActionResult.SUCCESS

        dx = random.randint(-1, 1)
        dy = random.randint(-1, 1)
        if dx == 0 and dy == 0:
            self.num_turns -= 1
            return ActionResult.NO_ACTION

        new_x, new_y = self.entity.x + dx, self.entity.y + dy
        if (
            not engine.get_blocking_entity_at(new_x, new_y)
            and engine.game_map.is_walkable(new_x, new_y)
        ):
            self.entity.move(dx, dy)

        self.num_turns -= 1
        if self.num_turns > 0:
            engine.messages.append(
                f"The {self.entity.name} wanders in confusion!"
            )
        return ActionResult.SUCCESS


# ---------------------------------------------------------------------------
# Stunned AI
# ---------------------------------------------------------------------------

class StunnedAI(BaseAI):
    """
    Entity does nothing for *num_turns*, then reverts to *old_ai*.
    """

    def __init__(self, old_ai: BaseAI, num_turns: int) -> None:
        super().__init__()
        self.old_ai = old_ai
        self.num_turns = num_turns

    def perform(self, engine: GameEngine) -> ActionResult:
        if self.num_turns <= 0:
            self.entity.ai = self.old_ai
            self.entity.ai.entity = self.entity
            engine.messages.append(
                f"The {self.entity.name} shakes off the stun!"
            )
            return ActionResult.SUCCESS

        self.num_turns -= 1
        engine.messages.append(f"The {self.entity.name} is stunned!")
        return ActionResult.NO_ACTION


# ---------------------------------------------------------------------------
# State-driven AI (HFSM)
# ---------------------------------------------------------------------------

class AIState(Enum):
    """Generic states for a state-machine AI."""
    IDLE = auto()
    CHASE = auto()
    ATTACK = auto()
    FLEE = auto()
    PATROL = auto()


class StateMachineAI(BaseAI):
    """
    A simple hierarchical finite-state-machine AI.

    Override ``update_state`` and ``act`` to build custom behaviors.
    """

    def __init__(self, initial_state: AIState = AIState.IDLE) -> None:
        super().__init__()
        self.state = initial_state
        self.state_timer: int = 0
        self.target: Entity | None = None
        self._last_known_pos: tuple[int, int] | None = None

    def perform(self, engine: GameEngine) -> ActionResult:
        self.update_state(engine)
        return self.act(engine)

    def update_state(self, engine: GameEngine) -> None:
        """Evaluate transitions; override in subclasses."""
        players = list(engine.players.values())
        if not players:
            self.state = AIState.IDLE
            return

        player = min(players, key=lambda p: chebyshev_distance(self.entity, p))
        dist = chebyshev_distance(self.entity, player)
        visible = can_see(engine, self.entity, player)

        if visible:
            self.target = player
            self._last_known_pos = (player.x, player.y)

        if self.state == AIState.IDLE:
            if visible and dist <= 6:
                self.state = AIState.CHASE
        elif self.state == AIState.CHASE:
            if dist <= 1:
                self.state = AIState.ATTACK
            elif not visible and not self._last_known_pos:
                self.state = AIState.IDLE
        elif self.state == AIState.ATTACK:
            if dist > 1:
                self.state = AIState.CHASE
        # FLEE is usually set externally (e.g. on_damage_taken)

    def act(self, engine: GameEngine) -> ActionResult:
        """Execute behavior for the current state."""
        if self.state == AIState.IDLE:
            return self._act_idle(engine)
        if self.state == AIState.CHASE:
            return self._act_chase(engine)
        if self.state == AIState.ATTACK:
            return self._act_attack(engine)
        if self.state == AIState.FLEE:
            return self._act_flee(engine)
        if self.state == AIState.PATROL:
            return self._act_patrol(engine)
        return ActionResult.NO_ACTION

    def _act_idle(self, engine: GameEngine) -> ActionResult:
        return ActionResult.NO_ACTION

    def _act_chase(self, engine: GameEngine) -> ActionResult:
        goal = (
            (self.target.x, self.target.y)
            if self.target and can_see(engine, self.entity, self.target)
            else self._last_known_pos
        )
        if goal is None:
            return ActionResult.NO_ACTION
        pf = self.get_pathfinder(engine)
        nxt = pf.next_step_toward((self.entity.x, self.entity.y), goal)
        if nxt is None:
            return ActionResult.FAILURE
        dx, dy = nxt[0] - self.entity.x, nxt[1] - self.entity.y
        self.entity.move(dx, dy)
        return ActionResult.SUCCESS

    def _act_attack(self, engine: GameEngine) -> ActionResult:
        if self.target is None:
            return ActionResult.IMPOSSIBLE
        return HostileAI()._attack(self.target, engine)  # type: ignore[arg-type]

    def _act_flee(self, engine: GameEngine) -> ActionResult:
        if self.target is None:
            return ActionResult.NO_ACTION
        dx = self.entity.x - self.target.x
        dy = self.entity.y - self.target.y
        move_x = (dx // abs(dx)) if dx != 0 else 0
        move_y = (dy // abs(dy)) if dy != 0 else 0
        nx, ny = self.entity.x + move_x, self.entity.y + move_y
        if (
            not engine.get_blocking_entity_at(nx, ny)
            and engine.game_map.is_walkable(nx, ny)
        ):
            self.entity.move(move_x, move_y)
            return ActionResult.SUCCESS
        return ActionResult.FAILURE

    def _act_patrol(self, engine: GameEngine) -> ActionResult:
        return ActionResult.NO_ACTION
