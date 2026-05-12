# Standard library imports
import math
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Callable,
    Dict,
    Generic,
    Iterator,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    TypeVar,
)

# Third-party imports
# (none)

# Local imports
from dungeon.entities import (
    BurnEffect,
    ConfusionConsumable,
    CurioMerchant,
    Entity,
    Equippable,
    FreezeEffect,
    GoldConsumable,
    HealingConsumable,
    Item,
    LightningConsumable,
    LoreSystem,
    MagicConsumable,
    ManaRestorationConsumable,
    Monster,
    Player,
    PoisonEffect,
    RegenEffect,
    Shrine,
    Stairs,
    TransmutationSpell,
    WetEffect,
)
from dungeon.map import Map, Rect
from dungeon.network import GameState
from dungeon.save_system import save_system
from dungeon.storylets import storylet_system


# ============================================================================
# NEW: Event System & Callback Architecture
# ============================================================================

class EventType(Enum):
    """Enumeration of observable engine events for decoupled systems."""
    PLAYER_MOVED = auto()
    COMBAT_HIT = auto()
    ENEMY_KILLED = auto()
    ITEM_PICKED_UP = auto()
    ITEM_CONSUMED = auto()
    FLOOR_CHANGED = auto()
    PLAYER_LEVELED_UP = auto()
    SHRINE_USED = auto()
    CURIO_PURCHASED = auto()
    SPELL_CAST = auto()
    STATUS_EFFECT_APPLIED = auto()
    STATUS_EFFECT_REMOVED = auto()
    ACHIEVEMENT_UNLOCKED = auto()
    PLAYER_DIED = auto()
    UNDO_PERFORMED = auto()


T = TypeVar("T")

@dataclass
class GameEvent(Generic[T]):
    """Strongly-typed event payload for the observer pattern."""
    event_type: EventType
    payload: T
    timestamp: float = field(default_factory=time.time)


class EventListener(Protocol):
    """Protocol for any system that wishes to observe engine events."""
    def on_event(self, event: GameEvent) -> None:
        ...


class EventBus:
    """Decoupled publish-subscribe system for cross-cutting concerns."""
    
    def __init__(self):
        self._listeners: Dict[EventType, List[EventListener]] = defaultdict(list)
        self._history: List[GameEvent] = []
        self._history_limit: int = 1000
    
    def subscribe(self, event_type: EventType, listener: EventListener) -> None:
        self._listeners[event_type].append(listener)
    
    def unsubscribe(self, event_type: EventType, listener: EventListener) -> None:
        if listener in self._listeners[event_type]:
            self._listeners[event_type].remove(listener)
    
    def publish(self, event: GameEvent) -> None:
        self._history.append(event)
        if len(self._history) > self._history_limit:
            self._history.pop(0)
        
        for listener in self._listeners[event.event_type]:
            try:
                listener.on_event(event)
            except Exception as e:
                # Fail-soft: don't let observers crash the engine
                pass
    
    def get_history(self, event_type: Optional[EventType] = None) -> List[GameEvent]:
        if event_type is None:
            return list(self._history)
        return [e for e in self._history if e.event_type == event_type]


# ============================================================================
# NEW: Difficulty & Progression System
# ============================================================================

class AscensionModifier:
    """Encapsulates NG+ difficulty scaling rules."""
    
    MODIFIERS = {
        2: {"max_room_size": 8, "monster_density": 1.2, "elite_chance": 0.0},
        5: {"max_room_size": 8, "monster_density": 1.3, "elite_chance": 0.05},
        7: {"max_room_size": 7, "monster_density": 1.4, "elite_chance": 0.08},
        10: {"max_room_size": 7, "monster_density": 1.5, "elite_chance": 0.12},
        12: {"mental_fatigue": True, "mana_drain_chance": 0.05},
        15: {"max_room_size": 6, "monster_density": 1.7, "elite_chance": 0.18, "no_healing_shrines": True},
    }
    
    def __init__(self, tier: int):
        self.tier = tier
        self._active = self._compute_modifiers()
    
    def _compute_modifiers(self) -> Dict[str, float]:
        active: Dict[str, float] = {}
        for threshold, mods in sorted(self.MODIFIERS.items()):
            if self.tier >= threshold:
                active.update(mods)
        return active
    
    def get(self, key: str, default=0.0):
        return self._active.get(key, default)
    
    @property
    def max_room_size(self) -> int:
        return int(self.get("max_room_size", 10))
    
    @property
    def monster_density_multiplier(self) -> float:
        return self.get("monster_density", 1.0)
    
    @property
    def elite_spawn_chance(self) -> float:
        return self.get("elite_chance", 0.0)
    
    @property
    def has_mental_fatigue(self) -> bool:
        return self.get("mental_fatigue", False)
    
    @property
    def blocks_healing_shrines(self) -> bool:
        return self.get("no_healing_shrines", False)


# ============================================================================
# NEW: Spatial Indexing for O(1) Entity Lookup
# ============================================================================

class SpatialIndex:
    """Grid-based spatial hash for efficient entity queries."""
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self._grid: Dict[Tuple[int, int], Set[Entity]] = defaultdict(set)
        self._entity_positions: Dict[int, Tuple[int, int]] = {}
    
    def _key(self, x: int, y: int) -> Tuple[int, int]:
        return (x, y)
    
    def add(self, entity: Entity) -> None:
        key = self._key(entity.x, entity.y)
        self._grid[key].add(entity)
        self._entity_positions[id(entity)] = key
    
    def remove(self, entity: Entity) -> None:
        old_key = self._entity_positions.get(id(entity))
        if old_key:
            self._grid[old_key].discard(entity)
            if not self._grid[old_key]:
                del self._grid[old_key]
            del self._entity_positions[id(entity)]
    
    def move(self, entity: Entity, new_x: int, new_y: int) -> None:
        self.remove(entity)
        entity.x, entity.y = new_x, new_y
        self.add(entity)
    
    def get_at(self, x: int, y: int) -> Set[Entity]:
        return set(self._grid.get(self._key(x, y), []))
    
    def get_blocking_at(self, x: int, y: int) -> Optional[Entity]:
        for entity in self.get_at(x, y):
            if entity.blocks_movement:
                return entity
        return None
    
    def get_in_radius(self, cx: int, cy: int, radius: int) -> Iterator[Entity]:
        """Yield entities within Chebyshev distance `radius`."""
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) <= radius:
                    yield from self.get_at(cx + dx, cy + dy)
    
    def get_hostiles_near(self, x: int, y: int, radius: int) -> List[Entity]:
        """Return sorted list of hostile entities by distance."""
        hostiles = []
        for entity in self.get_in_radius(x, y, radius):
            if entity.fighter and not isinstance(entity, Player):
                dist = max(abs(entity.x - x), abs(entity.y - y))
                hostiles.append((dist, entity))
        hostiles.sort(key=lambda t: t[0])
        return [e for _, e in hostiles]
    
    def rebuild(self, entities: List[Entity]) -> None:
        self._grid.clear()
        self._entity_positions.clear()
        for entity in entities:
            self.add(entity)
    
    def clear(self) -> None:
        self._grid.clear()
        self._entity_positions.clear()


# ============================================================================
# NEW: Combat Log & Statistics Tracking
# ============================================================================

@dataclass
class CombatRecord:
    """Immutable record of a combat interaction."""
    attacker_name: str
    defender_name: str
    damage_dealt: int
    was_fatal: bool
    dungeon_level: int
    timestamp: float = field(default_factory=time.time)
    attacker_hp_after: int = 0
    defender_hp_after: int = 0


class CombatLedger:
    """Persistent combat history for analytics and achievements."""
    
    def __init__(self):
        self.records: List[CombatRecord] = []
        self.total_damage_dealt: int = 0
        self.total_damage_taken: int = 0
        self.enemies_slain: int = 0
        self.critical_hits: int = 0  # Damage > 50% max HP
        self.finesse_hits: int = 0   # Damage <= 50% max HP
        self._brutality_streak: int = 0
        self._finesse_streak: int = 0
        self.max_brutality_streak: int = 0
        self.max_finesse_streak: int = 0
    
    def record_hit(self, record: CombatRecord, target_max_hp: int) -> None:
        self.records.append(record)
        self.total_damage_dealt += record.damage_dealt
        
        if record.damage_dealt > target_max_hp // 2:
            self.critical_hits += 1
            self._brutality_streak += 1
            self._finesse_streak = 0
            self.max_brutality_streak = max(self.max_brutality_streak, self._brutality_streak)
        else:
            self.finesse_hits += 1
            self._finesse_streak += 1
            self._brutality_streak = 0
            self.max_finesse_streak = max(self.max_finesse_streak, self._finesse_streak)
        
        if record.was_fatal:
            self.enemies_slain += 1
    
    def record_damage_taken(self, amount: int) -> None:
        self.total_damage_taken += amount
    
    def get_favorite_style(self) -> str:
        if self.critical_hits > self.finesse_hits * 1.5:
            return "brutality"
        elif self.finesse_hits > self.critical_hits * 1.5:
            return "finesse"
        return "balanced"


# ============================================================================
# NEW: Inventory & Economy Manager
# ============================================================================

class EconomyTracker:
    """Tracks wealth flow and spending patterns."""
    
    def __init__(self):
        self.total_gold_earned: int = 0
        self.total_gold_spent: int = 0
        self.gold_from_kills: int = 0
        self.gold_from_loot: int = 0
        self.curio_purchases: int = 0
        self.transaction_log: List[Dict] = []
    
    def record_income(self, amount: int, source: str) -> None:
        self.total_gold_earned += amount
        if source == "kill":
            self.gold_from_kills += amount
        elif source == "loot":
            self.gold_from_loot += amount
        self.transaction_log.append({
            "type": "income", "amount": amount, "source": source,
            "timestamp": time.time()
        })
    
    def record_expense(self, amount: int, item: str) -> None:
        self.total_gold_spent += amount
        if "curio" in item.lower():
            self.curio_purchases += 1
        self.transaction_log.append({
            "type": "expense", "amount": amount, "item": item,
            "timestamp": time.time()
        })


# ============================================================================
# ENHANCED: GameEngine with Modern Architecture
# ============================================================================

class GameEngine:
    """
    Enhanced dungeon crawl engine with event-driven architecture,
    spatial indexing, combat analytics, and NG+ progression system.
    
    All original public methods preserved for backward compatibility.
    """
    
    # -------------------------------------------------------------------------
    # Initialization
    # -------------------------------------------------------------------------
    
    def __init__(
        self,
        map_width: int,
        map_height: int,
        is_host: bool = True,
        local_player_id: int = 1,
        is_ng_plus: bool = False,
    ):
        # Original parameters
        self.map_width = map_width
        self.map_height = map_height
        self.dungeon_level = 1
        self.entities: List[Entity] = []
        self.local_player_id = local_player_id
        self.is_ng_plus = is_ng_plus
        self.start_time = time.time()
        self.ascension_tier = save_system.persistent_context.ng_plus_level
        
        # NEW: Subsystem initialization
        self.events = EventBus()
        self.spatial = SpatialIndex(map_width, map_height)
        self.combat_ledger = CombatLedger()
        self.economy = EconomyTracker()
        self.ascension = AscensionModifier(self.ascension_tier)
        
        # Original state (preserved)
        self._undo_buffer: List[dict] = []
        self._max_undo = 5
        self.player_last_dx = 1
        self.player_last_dy = 0
        self.run_curio_spawned = False
        
        self._achievements: List[str] = []
        self._track_achievements()
        
        # Player setup
        self.player = Player(0, 0, player_id=local_player_id)
        self.player.fighter.ascension_tier = self.ascension_tier
        self.players = {local_player_id: self.player}
        
        # NEW: Seed-based RNG for reproducible floors (optional)
        self._floor_seed: Optional[int] = None
        self._rng = random.Random()
        
        if is_ng_plus:
            self._init_ng_plus()
        else:
            self.generate_floor()
            self.messages = [
                "You stand before the Iron Maw. The air is thick with the scent of wet stone and old blood."
            ]
    
    def _init_ng_plus(self) -> None:
        """Encapsulated NG+ initialization."""
        ng_bonus = save_system.start_ng_plus({})
        self.player.fighter.max_hp += ng_bonus["hp_bonus"]
        self.player.fighter.hp = self.player.fighter.max_hp
        if self.player.mana:
            self.player.mana.max_mana += ng_bonus["mana_bonus"]
            self.player.mana.mana = self.player.mana.max_mana
        self.messages = [
            ng_bonus["alibi"],
            "The cycle begins anew, but the shadows have grown longer...",
        ]
    
    # -------------------------------------------------------------------------
    # Network Player Management (Original API Preserved)
    # -------------------------------------------------------------------------
    
    def add_network_player(self, player_id: int, name: str = "Player") -> Player:
        if player_id not in self.players:
            rooms = list(self.game_map.rooms) if hasattr(self.game_map, 'rooms') else []
            if rooms:
                room = rooms[min(len(rooms) - 1, player_id)]
                x, y = room.center
            else:
                x, y = player_id, 1
            player = Player(x, y, player_id=player_id, name=name)
            self.players[player_id] = player
            self.entities.append(player)
            self.spatial.add(player)
            return player
        return self.players[player_id]
    
    def remove_network_player(self, player_id: int) -> None:
        if player_id in self.players and player_id != self.local_player_id:
            player = self.players[player_id]
            if player in self.entities:
                self.entities.remove(player)
                self.spatial.remove(player)
            del self.players[player_id]
    
    def get_player(self, player_id: int) -> Optional[Player]:
        return self.players.get(player_id)
    
    @property
    def player(self) -> Player:
        return self.players.get(self.local_player_id)
    
    @player.setter
    def player(self, value: Player):
        self.players[self.local_player_id] = value
        if value not in self.entities:
            self.entities.append(value)
            self.spatial.add(value)
    
    # -------------------------------------------------------------------------
    # Floor Generation (Enhanced with Spatial Index & Ascension)
    # -------------------------------------------------------------------------
    
    def generate_floor(self, seed: Optional[int] = None) -> None:
        """
        Enhanced floor generation with seed support and spatial indexing.
        
        Args:
            seed: Optional seed for reproducible dungeon layouts.
        """
        self._floor_seed = seed
        if seed is not None:
            self._rng.seed(seed)
        
        self.game_map = Map(self.map_width, self.map_height, self.dungeon_level)
        
        # Use ascension-modified room sizes
        max_size = self.ascension.max_room_size
        min_size = 4
        max_rooms = 10
        
        # Scale monster/item counts by ascension
        density_mult = self.ascension.monster_density_multiplier
        
        self.entities = list(self.players.values())
        self.spatial.clear()
        for player in self.players.values():
            self.spatial.add(player)
        
        rooms = self._generate_with_rooms(max_rooms, min_size, max_size)
        self.game_map.rooms = rooms
        
        for pid, player in self.players.items():
            room_idx = min(pid - 1, len(rooms) - 1)
            start_x, start_y = rooms[room_idx].center
            player.x, player.y = start_x, start_y
            self.spatial.move(player, start_x, start_y)
        
        stairs_x, stairs_y = rooms[-1].center
        stairs = Stairs(stairs_x, stairs_y)
        self.entities.append(stairs)
        self.spatial.add(stairs)
        
        for room in rooms[1:-1]:
            self._place_entities(room, density_mult)
        
        self._maybe_place_shrine(rooms)
        self._maybe_place_curio(rooms)
        
        self.update_all_fov()
        
        # Publish floor change event
        self.events.publish(GameEvent(
            EventType.FLOOR_CHANGED,
            {"level": self.dungeon_level, "seed": seed, "rooms": len(rooms)}
        ))
    
    def next_floor(self) -> None:
        self.dungeon_level += 1
        
        if self.dungeon_level % 5 == 1 and self.dungeon_level > 1:
            if self.autosave():
                self.messages.append("[Memory etched in the stone... autosaved]")
        
        self.messages.append(f"You descend further into the pit... (Depth {self.dungeon_level})")
        self.generate_floor()
    
    # -------------------------------------------------------------------------
    # Enhanced Entity Placement with Ascension Scaling
    # -------------------------------------------------------------------------
    
    def _place_entities(self, room: Rect, density_mult: float = 1.0) -> None:
        max_monsters = int((2 + self.dungeon_level // 3) * density_mult)
        max_items = int((1 + self.dungeon_level // 5) * density_mult)
        
        # Elite spawn chance from ascension
        elite_chance = self.ascension.elite_spawn_chance
        
        number_of_monsters = self._rng.randint(0, max_monsters)
        number_of_items = self._rng.randint(0, max_items)
        
        for i in range(number_of_monsters):
            x = self._rng.randint(room.x1 + 1, room.x2 - 1)
            y = self._rng.randint(room.y1 + 1, room.y2 - 1)
            
            if not self.spatial.get_at(x, y):
                monster = self._select_monster_type(i, elite_chance)
                monster.x, monster.y = x, y
                self.entities.append(monster)
                self.spatial.add(monster)
        
        for i in range(number_of_items):
            x = self._rng.randint(room.x1 + 1, room.x2 - 1)
            y = self._rng.randint(room.y1 + 1, room.y2 - 1)
            
            if not self.spatial.get_at(x, y):
                item = self._select_item_type()
                item.x, item.y = x, y
                self.entities.append(item)
                self.spatial.add(item)
    
    def _select_monster_type(self, index: int, elite_chance: float) -> Monster:
        """Centralized monster selection logic with elite variants."""
        # Dragon boss on every 5th floor
        if self.dungeon_level % 5 == 0 and index == 0:
            return Monster.dragon(0, 0)
        
        # Elite variants at high ascension
        if self.ascension.tier >= 10 and random.random() < elite_chance:
            # Could add elite versions here
            pass
        
        if self.dungeon_level < 3:
            return Monster.goblin(0, 0) if random.random() < 0.5 else Monster.orc(0, 0)
        
        roll = random.random()
        if self.dungeon_level >= 7 and roll < 0.08:
            return Monster.weaver(0, 0)
        elif self.dungeon_level >= 5 and roll < 0.16:
            return Monster.siphoner(0, 0)
        elif self.dungeon_level >= 4 and roll < 0.26:
            return Monster.disrupter(0, 0)
        elif roll < 0.32:
            return Monster.goblin(0, 0)
        elif roll < 0.62:
            return Monster.orc(0, 0)
        else:
            return Monster.troll(0, 0)
    
    def _select_item_type(self) -> Item:
        """Centralized item generation with better scaling."""
        item_chance = random.random()
        
        if item_chance < 0.50:
            return Item(
                x=0, y=0, char="!", color="#7f00ff",
                name="Health Potion",
                consumable=HealingConsumable(amount=10 + self.dungeon_level * 2)
            )
        elif item_chance < 0.62:
            return Item(
                x=0, y=0, char="/", color="#55aaff",
                name="Sword",
                equippable=Equippable(slot="weapon", power_bonus=2 + self.dungeon_level // 2)
            )
        elif item_chance < 0.70:
            return Item(
                x=0, y=0, char="[", color="#aaaaaa",
                name="Mail Armor",
                equippable=Equippable(slot="armor", defense_bonus=1 + self.dungeon_level // 3)
            )
        elif item_chance < 0.80:
            return Item(
                x=0, y=0, char="?", color="#ffff00",
                name="Lightning Scroll",
                consumable=LightningConsumable(damage=20, maximum_range=5)
            )
        elif item_chance < 0.88:
            return Item(
                x=0, y=0, char="?", color="#ff00ff",
                name="Confusion Scroll",
                consumable=ConfusionConsumable(num_turns=5)
            )
        elif item_chance < 0.93:
            return Item(
                x=0, y=0, char="*", color="#66ddff",
                name="Essence Phial",
                consumable=ManaRestorationConsumable(amount=8 + self.dungeon_level // 2)
            )
        elif item_chance < 0.97:
            pile = 12 + self.dungeon_level * 4 + random.randint(0, 15)
            return Item(
                x=0, y=0, char="$", color="#d4af37",
                name="Tarnished Coin Pile",
                consumable=GoldConsumable(amount=pile)
            )
        else:
            return Item(
                x=0, y=0, char="?", color="#ffff00",
                name="Lightning Scroll",
                consumable=LightningConsumable(damage=20, maximum_range=5)
            )
    
    def _generate_with_rooms(
        self, max_rooms: int, min_size: int, max_size: int
    ) -> List[Rect]:
        rooms: List[Rect] = []
        for r in range(max_rooms):
            w = self._rng.randint(min_size, max_size)
            h = self._rng.randint(min_size, max_size)
            x = self._rng.randint(0, self.game_map.width - w - 1)
            y = self._rng.randint(0, self.game_map.height - h - 1)
            new_room = Rect(x, y, w, h)
            if any(new_room.intersect(other) for other in rooms):
                continue
            self.game_map.create_room(new_room)
            if rooms:
                (prev_x, prev_y) = rooms[-1].center
                (new_x, new_y) = new_room.center
                if self._rng.random() > 0.5:
                    self.game_map.create_h_tunnel(prev_x, new_x, prev_y)
                    self.game_map.create_v_tunnel(prev_y, new_y, new_x)
                else:
                    self.game_map.create_v_tunnel(prev_y, new_y, prev_x)
                    self.game_map.create_h_tunnel(prev_x, new_x, new_y)
            rooms.append(new_room)
        return rooms
    
    def _maybe_place_shrine(self, rooms: List[Rect]) -> None:
        # Ascension 15+: no healing shrines
        if self.ascension.blocks_healing_shrines:
            kinds = ["spirit", "blessing", "cleanse"]
        else:
            kinds = ["vitality", "spirit", "blessing", "cleanse"]
        
        if random.random() > 0.28:
            return
        mid = rooms[1:-1]
        if not mid:
            return
        
        kind = random.choice(kinds)
        for _ in range(40):
            room = random.choice(mid)
            x = random.randint(room.x1 + 1, room.x2 - 1)
            y = random.randint(room.y1 + 1, room.y2 - 1)
            if not self.game_map.is_walkable(x, y):
                continue
            if self.spatial.get_at(x, y):
                continue
            shrine = Shrine(x, y, kind)
            self.entities.append(shrine)
            self.spatial.add(shrine)
            return
    
    def _maybe_place_curio(self, rooms: List[Rect]) -> None:
        if self.run_curio_spawned or self.dungeon_level < 2:
            return
        if random.random() > 0.22:
            return
        mid = rooms[1:-1]
        if not mid:
            return
        for _ in range(50):
            room = random.choice(mid)
            x = random.randint(room.x1 + 1, room.x2 - 1)
            y = random.randint(room.y1 + 1, room.y2 - 1)
            if not self.game_map.is_walkable(x, y):
                continue
            if self.spatial.get_at(x, y):
                continue
            curio = CurioMerchant(x, y, self.dungeon_level)
            self.entities.append(curio)
            self.spatial.add(curio)
            self.run_curio_spawned = True
            self.messages.append(
                "[#eecc66]A folded stall of odds and ends flickers at the edge of sense. "
                "The Curio Peddler appears—but once per descent, they say.[/]"
            )
            return
    
    # -------------------------------------------------------------------------
    # Enhanced Combat with Ledger & Events
    # -------------------------------------------------------------------------
    
    def _track_combat_style(self, damage: int, target: Entity) -> None:
        stats = self.player.fighter.status_effects.delayed_branching_stats
        
        if damage > target.fighter.max_hp // 2:
            stats["brutality"] = stats.get("brutality", 0) + 1
        else:
            stats["finesse"] = stats.get("finesse", 0) + 1
        
        # Ascension Tier 12: Mental Fatigue
        if self.ascension.has_mental_fatigue and random.random() < self.ascension.get("mana_drain_chance", 0.05):
            self.messages.append("Your mind frays under the weight of the descent... (Fatigue)")
            if self.player.mana:
                self.player.mana.spend_mana(1)
        
        vignette = storylet_system.get_vignette(self, probability=0.15)
        if vignette:
            title, text = vignette
            self.messages.append(f"[bold cyan]A MOMENT IN TIME: {title}[/bold cyan] - {text}")
        elif random.random() < 0.1:
            lore_title, lore_text = LoreSystem.get_lore_drop(0.5)
            if lore_title:
                self.messages.append(f"[cyan]SCROLL: {lore_title}[/cyan] - {lore_text}")
    
    def _on_enemy_killed(self, target: Entity) -> None:
        self.messages.append(f"The {target.name} falls, silent at last.")
        
        base = 4 + self.dungeon_level + random.randint(0, 6)
        xp_val = target.level.xp_given if target.level else 0
        gold_drop = base + xp_val // 12
        self.player.gold += gold_drop
        self.economy.record_income(gold_drop, "kill")
        self.messages.append(f"You scrape up {gold_drop} coin from the remains.")
        
        self._check_kill_achievements(target)
        
        # Publish event
        self.events.publish(GameEvent(
            EventType.ENEMY_KILLED,
            {"enemy": target.name, "gold": gold_drop, "level": self.dungeon_level}
        ))
        
        if self.player.level:
            xp_gained = target.level.xp_given
            if self.player.level.add_xp(xp_gained):
                self.messages.append(f"You absorb {xp_gained} essence and grow more potent!")
                self.player.fighter.max_hp += 20
                self.player.fighter.hp = self.player.fighter.max_hp
                self.player.fighter.power += 1
                self.player.level.increase_level()
                
                self.events.publish(GameEvent(
                    EventType.PLAYER_LEVELED_UP,
                    {"new_level": self.player.level.current_level}
                ))
            else:
                self.messages.append(f"You harvest {xp_gained} essence.")
    
    def _check_kill_achievements(self, target: Entity) -> None:
        if target.name == "The Legacy Kernel" and "Slayer of the Fated" not in self._achievements:
            self._achievements.append("Slayer of the Fated")
            self.messages.append("[bold red]🏆 Rite of Passage: Slayer of the Fated![/bold red]")
            self.events.publish(GameEvent(
                EventType.ACHIEVEMENT_UNLOCKED,
                {"achievement": "Slayer of the Fated"}
            ))
        
        if self.dungeon_level >= 10 and "Abyssal Walker" not in self._achievements:
            self._achievements.append("Abyssal Walker")
            self.messages.append("[bold red]🏆 Rite of Passage: Abyssal Walker![/bold red]")
            self.events.publish(GameEvent(
                EventType.ACHIEVEMENT_UNLOCKED,
                {"achievement": "Abyssal Walker"}
            ))
    
    def _track_achievements(self) -> None:
        if self.dungeon_level >= 5 and "The Descent" not in self._achievements:
            self._achievements.append("The Descent")
        
        if self.player.fighter.max_hp >= 50 and "Hardened Spirit" not in self._achievements:
            self._achievements.append("Hardened Spirit")
    
    def get_achievements(self) -> List[str]:
        return list(self._achievements)
    
    # -------------------------------------------------------------------------
    # Core Interaction Handlers (Enhanced with Spatial Index & Events)
    # -------------------------------------------------------------------------
    
    def get_blocking_entity_at(self, x: int, y: int) -> Optional[Entity]:
        """O(1) lookup via spatial index."""
        return self.spatial.get_blocking_at(x, y)
    
    def update_all_fov(self) -> None:
        for player in self.players.values():
            self._update_fov_for_player(player)
    
    def _update_fov_for_player(self, player: Player) -> None:
        radius = 8
        fov_map = self.game_map.compute_fov(player.x, player.y, radius, algorithm="shadow_casting")
        
        for y in range(self.game_map.height):
            for x in range(self.game_map.width):
                if fov_map[y][x]:
                    self.game_map.tiles[y][x].visible = True
                    self.game_map.tiles[y][x].explored = True
    
    def update_fov(self) -> None:
        self.update_all_fov()
    
    def handle_move(self, dx: int, dy: int) -> bool:
        if self.player.fighter.hp <= 0:
            return False
        
        new_x, new_y = self.player.x + dx, self.player.y + dy
        
        target_entity = self.get_blocking_entity_at(new_x, new_y)
        if isinstance(target_entity, CurioMerchant):
            self.messages.append(
                "The Curio Peddler rustles his wares. Press [e] to trade—each tally in his ledger is written once."
            )
            return False
        
        self.save_undo_state()
        
        if target_entity:
            if not target_entity.fighter:
                self.messages.append("You find no purchase in that.")
                self._undo_buffer.pop()
                return False
            
            # Combat resolution
            damage = self.player.fighter.power - target_entity.fighter.defense
            self._track_combat_style(damage, target_entity)
            
            record = CombatRecord(
                attacker_name=self.player.name,
                defender_name=target_entity.name,
                damage_dealt=max(0, damage),
                was_fatal=False,
                dungeon_level=self.dungeon_level,
                attacker_hp_after=self.player.fighter.hp,
                defender_hp_after=target_entity.fighter.hp - max(0, damage)
            )
            
            if damage > 0:
                target_entity.fighter.hp -= damage
                self.messages.append(f"You strike the {target_entity.name}, drawing {damage} HP of life.")
                
                self.events.publish(GameEvent(
                    EventType.COMBAT_HIT,
                    {"attacker": self.player.name, "defender": target_entity.name,
                     "damage": damage, "fatal": False}
                ))
            else:
                self.messages.append(f"Your blow glances off the {target_entity.name}'s defenses.")
                record.damage_dealt = 0
            
            if target_entity.fighter.hp <= 0:
                record.was_fatal = True
                self.combat_ledger.record_hit(record, target_entity.fighter.max_hp)
                self._on_enemy_killed(target_entity)
                self.entities.remove(target_entity)
                self.spatial.remove(target_entity)
            else:
                self.combat_ledger.record_hit(record, target_entity.fighter.max_hp)
            
            self.handle_enemy_turns()
            return True
        
        if self.game_map.is_walkable(new_x, new_y):
            old_x, old_y = self.player.x, self.player.y
            self.player.move(dx, dy)
            self.spatial.move(self.player, new_x, new_y)
            
            if dx != 0 or dy != 0:
                self.player_last_dx, self.player_last_dy = dx, dy
            
            self.events.publish(GameEvent(
                EventType.PLAYER_MOVED,
                {"from": (old_x, old_y), "to": (new_x, new_y)}
            ))
            
            self.update_fov()
            self.handle_enemy_turns()
            return True
        else:
            self.messages.append("The stone is cold, silent, and immovable.")
            self._undo_buffer.pop()
            return False
    
    def handle_pickup(self) -> bool:
        if self.player.fighter.hp <= 0:
            return False
        
        # O(1) lookup instead of O(n) scan
        items_here = [e for e in self.spatial.get_at(self.player.x, self.player.y) 
                      if isinstance(e, Item)]
        
        for entity in items_here:
            if entity.consumable and isinstance(entity.consumable, GoldConsumable):
                entity.parent = self.player
                amount = entity.consumable.consume(self)
                self.economy.record_income(amount, "loot")
                self.entities.remove(entity)
                self.spatial.remove(entity)
                
                self.events.publish(GameEvent(
                    EventType.ITEM_PICKED_UP,
                    {"item": entity.name, "gold": amount}
                ))
                
                self.handle_enemy_turns()
                return True
            
            if len(self.player.inventory.items) >= self.player.inventory.capacity:
                self.messages.append("Your inventory is full.")
                return False
            
            self.entities.remove(entity)
            self.spatial.remove(entity)
            entity.parent = self.player
            self.player.inventory.items.append(entity)
            self.messages.append(f"You picked up the {entity.name}!")
            
            self.events.publish(GameEvent(
                EventType.ITEM_PICKED_UP,
                {"item": entity.name}
            ))
            
            self.handle_enemy_turns()
            return True
        
        self.messages.append("There is nothing here to pick up.")
        return False
    
    def handle_consume(self, item: Item) -> bool:
        if item.consumable:
            if item.consumable.consume(self):
                self.player.inventory.items.remove(item)
                
                self.events.publish(GameEvent(
                    EventType.ITEM_CONSUMED,
                    {"item": item.name, "type": "consumable"}
                ))
                
                self.handle_enemy_turns()
                return True
        elif item.equippable:
            self.player.equipment.toggle_equip(item, self)
            
            self.events.publish(GameEvent(
                EventType.ITEM_CONSUMED,
                {"item": item.name, "type": "equip"}
            ))
            
            self.handle_enemy_turns()
            return True
        return False
    
    def handle_wait(self) -> bool:
        if self.player.fighter.hp <= 0:
            return False
        self.messages.append("You catch your breath in the heavy silence...")
        self.handle_enemy_turns()
        return True
    
    def _closest_hostile_in_spell_range(self, range_val: int) -> Optional[Entity]:
        """Optimized using spatial index."""
        caster = self.player
        closest: Optional[Entity] = None
        best = 999
        
        for entity in self.spatial.get_hostiles_near(caster.x, caster.y, range_val):
            if entity is caster:
                continue
            if not self.game_map.tiles[entity.y][entity.x].visible:
                continue
            dist = max(abs(entity.x - caster.x), abs(entity.y - caster.y))
            if dist <= range_val and dist < best:
                best = dist
                closest = entity
        return closest
    
    def cast_spell_slot(self, slot: int) -> bool:
        if self.player.fighter.hp <= 0 or not self.player.mana:
            return False
        
        spells = self.player.mana.learned_spells
        if slot < 0 or slot >= len(spells):
            return False
        
        spell = spells[slot]
        if not self.player.mana.can_cast(spell):
            self.messages.append("Your spirit is too thin to voice that working.")
            return False
        
        # Transmutation spell
        if isinstance(spell, TransmutationSpell):
            tx = self.player.x + self.player_last_dx
            ty = self.player.y + self.player_last_dy
            if not self.game_map.is_in_bounds(tx, ty):
                self.messages.append("The weave finds only void that way.")
                return False
            tile = self.game_map.tiles[ty][tx]
            if tile.walkable:
                self.messages.append("There is no stone to shame there—only floor and echo.")
                return False
            
            self.save_undo_state()
            self.player.mana.spend_mana(spell.mana_cost)
            result = spell.cast(self.player, (tx, ty), self)
            self.messages.append(result)
            
            self.events.publish(GameEvent(
                EventType.SPELL_CAST,
                {"spell": spell.name, "target": (tx, ty), "type": "transmutation"}
            ))
            
            self.handle_enemy_turns()
            return True
        
        # Healing spell
        if spell.healing > 0:
            self.save_undo_state()
            self.player.mana.spend_mana(spell.mana_cost)
            result = spell.cast(self.player, self.player, self)
            self.messages.append(result)
            MagicConsumable.apply_spell_effects(self.player, None, spell, self)
            
            self.events.publish(GameEvent(
                EventType.SPELL_CAST,
                {"spell": spell.name, "target": "self", "type": "healing"}
            ))
            
            self.handle_enemy_turns()
            return True
        
        # Offensive spell
        target = self._closest_hostile_in_spell_range(spell.range_val)
        if not target:
            self.messages.append("No foe stands within the diagram of that spell.")
            return False
        
        self.save_undo_state()
        self.player.mana.spend_mana(spell.mana_cost)
        result = spell.cast(self.player, target, self)
        self.messages.append(result)
        MagicConsumable.apply_spell_effects(self.player, target, spell, self)
        
        self.events.publish(GameEvent(
            EventType.SPELL_CAST,
            {"spell": spell.name, "target": target.name, "type": "offensive"}
        ))
        
        self.handle_enemy_turns()
        return True
    
    def shrine_under_player(self) -> Optional[Shrine]:
        for e in self.spatial.get_at(self.player.x, self.player.y):
            if (
                isinstance(e, Shrine)
                and not e.shrine_spent
            ):
                return e
        return None
    
    def adjacent_curio(self) -> Optional[CurioMerchant]:
        for e in self.entities:
            if isinstance(e, CurioMerchant):
                d = max(abs(e.x - self.player.x), abs(e.y - self.player.y))
                if d <= 1:
                    return e
        return None
    
    def apply_shrine(self, shrine: Shrine) -> bool:
        self.save_undo_state()
        p = self.player
        k = shrine.shrine_kind
        
        if k == "vitality":
            gap = p.fighter.max_hp - p.fighter.hp
            heal = min(18 + self.dungeon_level * 2, gap)
            if heal <= 0:
                self.messages.append("You are already whole; the shrine withholds its gift, unspent.")
                self._undo_buffer.pop()
                return False
            p.fighter.hp += heal
            self.messages.append(
                f"The shrine knits flesh once. (+{heal} vitality) The vow closes—you will not drink from this well again."
            )
        
        elif k == "spirit":
            if not p.mana:
                self._undo_buffer.pop()
                return False
            r = min(12 + self.dungeon_level, p.mana.max_mana - p.mana.mana)
            if r <= 0:
                self.messages.append("Your spirit brims; cold stone has nothing more to pour.")
                self._undo_buffer.pop()
                return False
            p.mana.mana += r
            self.messages.append(
                f"A single draught of clarity. (+{r} spirit) That channel runs dry forever here."
            )
        
        elif k == "blessing":
            p.fighter.max_hp += 6
            p.fighter.hp += 6
            self.messages.append(
                "The stone loans you a little more room in your flesh—once. The echo will not return to this corner."
            )
        
        elif k == "cleanse":
            p.fighter.status_effects.effects.clear()
            self.messages.append(
                "Filth and hex slough off like rain. The shrine goes blind; it witnessed you once only."
            )
        
        shrine.mark_spent()
        
        self.events.publish(GameEvent(
            EventType.SHRINE_USED,
            {"kind": k, "dungeon_level": self.dungeon_level}
        ))
        
        self.handle_enemy_turns()
        return True
    
    def buy_curio_ware(self, merchant: CurioMerchant, index: int) -> str:
        if merchant not in self.entities:
            return "The peddler's stall is empty air."
        if index < 0 or index >= len(merchant.stock):
            return "No such tally in the ledger."
        if merchant.sold_out[index]:
            return "That line is closed. Only one sale per name."
        
        row = merchant.stock[index]
        price = row["price"]
        if self.player.gold < price:
            return f"Coin light by {price - self.player.gold}. No credit in the deep vaults."
        
        self.player.gold -= price
        self.economy.record_expense(price, row["label"])
        
        key = row["key"]
        px, py = self.player.x, self.player.y
        item = self._create_curio_item(key, px, py)
        
        merchant.sold_out[index] = True
        self._grant_purchased_item(item)
        
        self.events.publish(GameEvent(
            EventType.CURIO_PURCHASED,
            {"item": row["label"], "price": price}
        ))
        
        out = f"Paid {price} coin for {row['label']}. The ink dries; no second line."
        if all(merchant.sold_out):
            self.entities.remove(merchant)
            self.spatial.remove(merchant)
            out += " The peddler folds his stall into rumor and leaves."
        return out
    
    def _create_curio_item(self, key: str, x: int, y: int) -> Item:
        if key == "draught":
            return Item(
                x, y, "!", "#7f00ff", "Health Potion",
                consumable=HealingConsumable(10 + self.dungeon_level * 2),
            )
        elif key == "phial":
            return Item(
                x, y, "*", "#66ddff", "Essence Phial",
                consumable=ManaRestorationConsumable(8 + self.dungeon_level // 2),
            )
        else:
            return Item(
                x, y, "?", "#ffff00", "Lightning Scroll",
                consumable=LightningConsumable(20, 5),
            )
    
    def _grant_purchased_item(self, item: Item) -> None:
        if len(self.player.inventory.items) < self.player.inventory.capacity:
            item.parent = self.player
            self.player.inventory.items.append(item)
        else:
            item.x, item.y = self.player.x, self.player.y
            self.entities.append(item)
            self.spatial.add(item)
            self.messages.append("Your satchel groans full—ware left underfoot.")
    
    # -------------------------------------------------------------------------
    # Turn System (Enhanced)
    # -------------------------------------------------------------------------
    
    def handle_enemy_turns(self) -> None:
        # Process status effects for all players
        for player in self.players.values():
            if player.fighter:
                if not player.fighter.status_effects.can_act():
                    status_msgs = player.fighter.status_effects.process_turn_end(
                        player.fighter, self
                    )
                    for msg in status_msgs:
                        self.messages.append(msg)
                    player.fighter.status_effects.remove_expired(player.fighter, self)
                    continue
        
        # AI turns
        for entity in self.entities:
            if entity.ai and entity not in self.players.values():
                if entity.fighter and not entity.fighter.status_effects.can_act():
                    continue
                entity.ai.perform(self)
        
        # Mana regeneration
        for player in self.players.values():
            if player.fighter and player.mana:
                player.mana.regenerate()
    
    # -------------------------------------------------------------------------
    # Network Player Handlers (Original API Preserved)
    # -------------------------------------------------------------------------
    
    def handle_move_player(self, player: Player, dx: int, dy: int) -> bool:
        if player.fighter.hp <= 0:
            return False
        
        new_x, new_y = player.x + dx, player.y + dy
        
        target_entity = self.get_blocking_entity_at(new_x, new_y)
        if target_entity and target_entity in self.players.values():
            return False
        
        if target_entity and target_entity.fighter:
            damage = player.fighter.power - target_entity.fighter.defense
            
            stats = player.fighter.status_effects.delayed_branching_stats
            if damage > target_entity.fighter.max_hp // 2:
                stats["brutality"] = stats.get("brutality", 0) + 1
            else:
                stats["finesse"] = stats.get("finesse", 0) + 1
            
            if damage > 0:
                target_entity.fighter.hp -= damage
                self.messages.append(f"{player.name} hits the {target_entity.name} for {damage} HP!")
            else:
                self.messages.append(f"{player.name} hits the {target_entity.name} but does no damage.")
            
            if target_entity.fighter.hp <= 0:
                self.messages.append(f"The {target_entity.name} is dead!")
                if target_entity.level:
                    xp_gained = target_entity.level.xp_given
                    if player.level.add_xp(xp_gained):
                        self.messages.append(f"{player.name} gained {xp_gained} XP and leveled up!")
                        player.fighter.max_hp += 20
                        player.fighter.hp = player.fighter.max_hp
                        player.fighter.power += 1
                        player.level.increase_level()
                self.entities.remove(target_entity)
                self.spatial.remove(target_entity)
            
            self.handle_enemy_turns()
            return True
        
        if self.game_map.is_walkable(new_x, new_y):
            self.spatial.move(player, new_x, new_y)
            player.move(dx, dy)
            self._update_fov_for_player(player)
            self.handle_enemy_turns()
            return True
        
        return False
    
    def handle_pickup_player(self, player: Player) -> bool:
        if player.fighter.hp <= 0:
            return False
        
        items_here = [e for e in self.spatial.get_at(player.x, player.y)
                      if isinstance(e, Item)]
        
        for entity in items_here:
            if entity.consumable and isinstance(entity.consumable, GoldConsumable):
                entity.parent = player
                entity.consumable.consume(self)
                self.entities.remove(entity)
                self.spatial.remove(entity)
                self.handle_enemy_turns()
                return True
            
            if len(player.inventory.items) >= player.inventory.capacity:
                self.messages.append(f"{player.name}'s inventory is full.")
                return False
            
            self.entities.remove(entity)
            self.spatial.remove(entity)
            entity.parent = player
            player.inventory.items.append(entity)
            self.messages.append(f"{player.name} picked up the {entity.name}!")
            self.handle_enemy_turns()
            return True
        
        self.messages.append("There is nothing here to pick up.")
        return False
    
    def handle_stairs_player(self, player: Player) -> bool:
        for entity in self.spatial.get_at(player.x, player.y):
            if isinstance(entity, Stairs):
                self.next_floor()
                return True
        self.messages.append("There are no stairs here.")
        return False
    
    # -------------------------------------------------------------------------
    # State Serialization (Enhanced)
    # -------------------------------------------------------------------------
    
    def get_state(self) -> GameState:
        map_data = []
        for row in self.game_map.tiles:
            map_data.append([
                {
                    "char": tile.char,
                    "color": tile.color,
                    "walkable": tile.walkable,
                    "visible": tile.visible,
                    "explored": tile.explored,
                }
                for tile in row
            ])
        
        entities_data = []
        for e in self.entities:
            if e not in self.players.values():
                entities_data.append({
                    "x": e.x,
                    "y": e.y,
                    "char": e.char,
                    "color": e.color,
                    "name": e.name,
                    "blocks": e.blocks_movement,
                    "hp": e.fighter.hp if e.fighter else 0,
                    "max_hp": e.fighter.max_hp if e.fighter else 0,
                })
        
        return GameState(
            dungeon_level=self.dungeon_level,
            players=[p.to_dict() for p in self.players.values()],
            entities=entities_data,
            map_data=map_data,
            messages=self.messages[-10:],
            turn_count=self.dungeon_level * 100,  # Approximate turn count
            game_time=time.time() - self.start_time,
            seed=self._floor_seed or 0,
            sequence_number=self.dungeon_level
        )
    
    def get_save_data(self):
        return {
            "ephemeral": {
                "entities": [self._serialize_entity(e) for e in self.entities if e not in self.players.values()],
                "map": [[{"char": t.char, "color": t.color, "visible": t.visible, "explored": t.explored}
                         for t in row] for row in self.game_map.tiles],
            },
            "persistent": {
                "player": self.player.to_dict() if self.player else None,
                "combat_ledger": {
                    "total_damage_dealt": self.combat_ledger.total_damage_dealt,
                    "total_damage_taken": self.combat_ledger.total_damage_taken,
                    "enemies_slain": self.combat_ledger.enemies_slain,
                    "favorite_style": self.combat_ledger.get_favorite_style(),
                },
                "economy": {
                    "total_gold_earned": self.economy.total_gold_earned,
                    "total_gold_spent": self.economy.total_gold_spent,
                },
            },
            "dungeon_level": self.dungeon_level,
            "player_hp": self.player.fighter.hp if self.player and self.player.fighter else 0,
            "player_max_hp": self.player.fighter.max_hp if self.player and self.player.fighter else 0,
            "is_ng_plus": self.is_ng_plus,
            "playtime_seconds": int(time.time() - self.start_time),
            "ascension_tier": self.ascension_tier,
            "achievements": list(self._achievements),
        }
    
    def _serialize_entity(self, entity):
        return {
            "x": entity.x, "y": entity.y, "char": entity.char, "color": entity.color,
            "name": entity.name, "hp": entity.fighter.hp if entity.fighter else 0,
            "max_hp": entity.fighter.max_hp if entity.fighter else 0
        }
    
    def save(self, slot_id: int) -> bool:
        return save_system.save_game(slot_id, self.get_save_data(), self.player.name)
    
    def load(self, slot_id: int) -> bool:
        data = save_system.load_game(slot_id)
        if not data:
            return False
        self.dungeon_level = data.get("dungeon_level", 1)
        # Rebuild spatial index after load
        self.spatial.rebuild(self.entities)
        return True
    
    def autosave(self) -> bool:
        return save_system.autosave(self.get_save_data())
    
    # -------------------------------------------------------------------------
    # Display & UI Helpers (Enhanced)
    # -------------------------------------------------------------------------
    
    def get_status_display(self) -> str:
        if not self.player or not self.player.fighter:
            return ""
        
        effects = self.player.fighter.status_effects.effects
        if not effects:
            return ""
        
        status = "Status: "
        effect_strs = []
        for e in effects:
            if isinstance(e, BurnEffect):
                effect_strs.append(f"🔥{e.duration}")
            elif isinstance(e, PoisonEffect):
                effect_strs.append(f"☠{e.duration}")
            elif isinstance(e, FreezeEffect):
                effect_strs.append(f"❄{e.duration}")
            elif isinstance(e, WetEffect):
                effect_strs.append(f"💧{e.duration}")
            elif isinstance(e, RegenEffect):
                effect_strs.append(f"✨{e.duration}")
        return status + " ".join(effect_strs)
    
    def get_mana_display(self) -> str:
        if not self.player or not self.player.mana:
            return ""
        return f"Mana: {self.player.mana.mana}/{self.player.mana.max_mana}"
    
    def get_stats_display(self) -> str:
        """NEW: Rich statistics panel for UI rendering."""
        lines = []
        lines.append(f"Depth: {self.dungeon_level} | Gold: {self.player.gold}")
        lines.append(f"Kills: {self.combat_ledger.enemies_slain} | Style: {self.combat_ledger.get_favorite_style().title()}")
        if self.ascension_tier > 0:
            lines.append(f"Ascension: {self.ascension_tier}")
        return " | ".join(lines)
    
    def get_render_data(self, cursor=None):
        lines = []
        visible_entities = [e for e in self.entities if self.game_map.tiles[e.y][e.x].visible]
        visible_entities.sort(key=lambda e: e.blocks_movement)
        
        entity_map = {(e.x, e.y): e for e in visible_entities}
        
        for y in range(self.game_map.height):
            line = []
            for x in range(self.game_map.width):
                tile = self.game_map.tiles[y][x]
                
                if cursor and (x, y) == cursor:
                    line.append("[bold #d4af37]X[/]")
                elif (x, y) in entity_map:
                    e = entity_map[(x, y)]
                    line.append(f"[bold {e.color}]{e.char}[/]")
                elif tile.visible:
                    color = tile.color
                    if tile.char == ".": color = "#555"
                    elif tile.char == "#": color = "#888"
                    line.append(f"[{color}]{tile.char}[/]")
                elif tile.explored:
                    color = "#222"
                    line.append(f"[{color}]{tile.char}[/]")
                else:
                    line.append(" ")
            lines.append("".join(line))
        return "\n".join(lines)
    
    def get_death_scene_data(self) -> tuple:
        stats = self.player.fighter.status_effects.delayed_branching_stats if self.player and self.player.fighter else {}
        death_scene = LoreSystem.get_death_scene(self.dungeon_level, stats)
        lore_title, lore_text = LoreSystem.get_lore_drop(probability=0.4)
        return death_scene, lore_title or "", lore_text or ""
    
    def get_hint(self) -> str:
        if not self.player:
            return "The dungeon awaits your return..."
        return LoreSystem.get_hint(
            self.dungeon_level,
            self.player.x,
            self.player.y,
            self.entities,
            self.game_map
        )
    
    def get_tactical_info(self, x: int, y: int) -> str:
        if not self.game_map.is_in_bounds(x, y):
            return ""
        
        tile = self.game_map.tiles[y][x]
        if not tile.visible:
            return ""
        
        tactical = []
        
        # Check exposure using spatial index for enemies
        is_exposed = True
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                nx, ny = x + dx, y + dy
                if self.game_map.is_in_bounds(nx, ny):
                    if not self.game_map.tiles[ny][nx].walkable:
                        is_exposed = False
                        break
        
        if is_exposed:
            tactical.append("Exposed to the dark")
        
        # Fast hostile count via spatial index
        enemy_count = sum(1 for e in self.spatial.get_in_radius(x, y, 1)
                         if e.fighter and e != self.player and not isinstance(e, Player))
        
        if enemy_count > 0:
            tactical.append(f"Threat: {enemy_count} nearby denizen")
        
        if enemy_count == 0:
            safe_exits = 0
            for dx, dy in [(0,1),(0,-1),(1,0),(-1,0)]:
                nx, ny = x + dx, y + dy
                if self.game_map.is_walkable(nx, ny):
                    safe_exits += 1
            if safe_exits >= 3:
                tactical.append("Open path for escape")
            elif safe_exits == 1:
                tactical.append("Narrow bottleneck")
        
        return " | ".join(tactical) if tactical else "Lurking silence"
    
    # -------------------------------------------------------------------------
    # Undo System (Enhanced with Event)
    # -------------------------------------------------------------------------
    
    def save_undo_state(self) -> None:
        state = {
            "player_x": self.player.x,
            "player_y": self.player.y,
            "player_hp": self.player.fighter.hp,
            "dungeon_level": self.dungeon_level,
            "entities": [(e.x, e.y, e.name, e.fighter.hp if e.fighter else 0)
                        for e in self.entities if e != self.player],
            "messages": list(self.messages[-5:]),
            "spatial_snapshot": [(e.x, e.y) for e in self.entities if e != self.player],
        }
        self._undo_buffer.append(state)
        if len(self._undo_buffer) > self._max_undo:
            self._undo_buffer.pop(0)
    
    def undo(self) -> bool:
        if not self._undo_buffer:
            return False
        
        state = self._undo_buffer.pop()
        self.player.x = state["player_x"]
        self.player.y = state["player_y"]
        self.player.fighter.hp = state["player_hp"]
        self.dungeon_level = state["dungeon_level"]
        
        # Restore entity positions
        entity_iter = (e for e in self.entities if e != self.player)
        for entity, (ex, ey, _, _) in zip(entity_iter, state["entities"]):
            self.spatial.move(entity, ex, ey)
        
        self.messages.append("[The threads of fate unravel... state restored]")
        
        self.events.publish(GameEvent(
            EventType.UNDO_PERFORMED,
            {"restored_level": self.dungeon_level}
        ))
        
        self.update_fov()
        return True
    
    # -------------------------------------------------------------------------
    # NEW: Query API for External Systems
    # -------------------------------------------------------------------------
    
    def query_entities(
        self,
        *,
        has_fighter: Optional[bool] = None,
        is_hostile: Optional[bool] = None,
        in_radius: Optional[Tuple[int, int, int]] = None,
        visible_only: bool = False
    ) -> List[Entity]:
        """
        Flexible entity query API for UI, AI, and analytics.
        
        Args:
            has_fighter: Filter by fighter component presence
            is_hostile: Filter for non-player fighters
            in_radius: Tuple of (cx, cy, radius) for spatial query
            visible_only: Only visible entities
        """
        candidates = self.entities
        
        if in_radius:
            cx, cy, r = in_radius
            candidates = list(self.spatial.get_in_radius(cx, cy, r))
        
        results = []
        for e in candidates:
            if has_fighter is not None:
                if has_fighter and not e.fighter:
                    continue
                if not has_fighter and e.fighter:
                    continue
            
            if is_hostile is not None:
                is_enemy = e.fighter and not isinstance(e, Player)
                if is_hostile and not is_enemy:
                    continue
                if not is_hostile and is_enemy:
                    continue
            
            if visible_only and not self.game_map.tiles[e.y][e.x].visible:
                continue
            
            results.append(e)
        
        return results
    
    def get_run_statistics(self) -> Dict:
        """NEW: Comprehensive run statistics for end-game screen."""
        playtime = int(time.time() - self.start_time)
        return {
            "dungeon_level_reached": self.dungeon_level,
            "playtime_seconds": playtime,
            "enemies_slain": self.combat_ledger.enemies_slain,
            "total_damage_dealt": self.combat_ledger.total_damage_dealt,
            "total_damage_taken": self.combat_ledger.total_damage_taken,
            "gold_earned": self.economy.total_gold_earned,
            "gold_spent": self.economy.total_gold_spent,
            "combat_style": self.combat_ledger.get_favorite_style(),
            "achievements": list(self._achievements),
            "ascension_tier": self.ascension_tier,
            "brutality_streak_max": self.combat_ledger.max_brutality_streak,
            "finesse_streak_max": self.combat_ledger.max_finesse_streak,
        }