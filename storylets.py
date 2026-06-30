# Standard library imports
import json
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Callable

# Third-party imports
# (none)

# Local imports
if TYPE_CHECKING:
    from engine import GameEngine


class StoryletCategory(Enum):
    """Categories for storylets."""
    COMBAT = auto()
    EXPLORATION = auto()
    LORE = auto()
    NPC = auto()
    ITEM = auto()
    ENVIRONMENT = auto()
    MYSTERY = auto()


class StoryletEffectType(Enum):
    """Types of effects a storylet can have."""
    NONE = auto()
    GOLD = auto()
    XP = auto()
    ITEM = auto()
    STATUS_EFFECT = auto()
    HEAL = auto()
    DAMAGE = auto()
    STAT_BOOST = auto()
    REVEAL_MAP = auto()
    TRIGGER_STORYLET = auto()


@dataclass
class StoryletEffect:
    """Effect that a storylet can apply when triggered."""
    effect_type: StoryletEffectType
    value: Any = None
    duration: int = 0  # For status effects
    item_name: str = ""  # For item rewards
    stat_name: str = ""  # For stat boosts
    target_storylet_id: str = ""  # For chaining


@dataclass
class Storylet:
    """Enhanced storylet with categories, tags, effects, and chaining."""
    title: str
    text: str
    weight: float = 1.0
    preconditions: Optional[Dict[str, Any]] = None
    once_only: bool = True
    
    # New: Identification
    storylet_id: str = ""
    
    # New: Categorization
    category: StoryletCategory = StoryletCategory.LORE
    tags: List[str] = field(default_factory=list)
    
    # New: Priority and cooldown
    priority: int = 0  # Higher priority storylets are selected first
    cooldown_seconds: float = 0.0
    last_triggered: float = 0.0
    
    # New: Effects and rewards
    effects: List[StoryletEffect] = field(default_factory=list)
    
    # New: Chaining
    triggers_after: Optional[str] = None  # ID of storylet that must trigger first
    triggers_next: Optional[str] = None  # ID of storylet to trigger after this
    
    # New: State
    triggered: bool = False
    trigger_count: int = 0
    max_triggers: int = 1  # -1 for unlimited
    
    def __post_init__(self):
        if self.preconditions is None:
            self.preconditions = {}
        if self.storylet_id == "":
            self.storylet_id = self.title.lower().replace(" ", "_").replace("'", "")

    def is_available(self, engine: 'GameEngine', current_time: float = 0.0) -> bool:
        """Check if storylet is available to trigger."""
        # Check trigger limit
        if self.max_triggers != -1 and self.trigger_count >= self.max_triggers:
            return False
        
        # Check cooldown
        if current_time - self.last_triggered < self.cooldown_seconds:
            return False
        
        # Check chain dependency
        if self.triggers_after:
            prerequisite = storylet_system.get_storylet_by_id(self.triggers_after)
            if not prerequisite or not prerequisite.triggered:
                return False
        
        # Check preconditions
        for key, value in self.preconditions.items():
            if key == "depth_min" and engine.dungeon_level < value:
                return False
            if key == "depth_max" and engine.dungeon_level > value:
                return False
            if key == "hp_lt" and engine.player.fighter.hp >= value:
                return False
            if key == "hp_gt" and engine.player.fighter.hp <= value:
                return False
            if key == "brutality_min" and engine.player.fighter.status_effects.delayed_branching_stats.get("brutality", 0) < value:
                return False
            if key == "finesse_min" and engine.player.fighter.status_effects.delayed_branching_stats.get("finesse", 0) < value:
                return False
            if key == "has_item" and not any(item.name == value for item in engine.player.inventory.items):
                return False
            if key == "gold_min" and engine.player.gold < value:
                return False
            if key == "gold_max" and engine.player.gold > value:
                return False
            if key == "has_status" and not any(se.name == value for se in engine.player.fighter.status_effects.active):
                return False
            if key == "has_not_status" and any(se.name == value for se in engine.player.fighter.status_effects.active):
                return False
            if key == "kills_min" and engine.combat_ledger.total_kills < value:
                return False
            if key == "has_achievement" and value not in engine.save_system.get_achievements():
                return False
        return True

    def trigger(self, engine: 'GameEngine') -> tuple[str, str]:
        """Trigger the storylet and apply effects."""
        self.triggered = True
        self.trigger_count += 1
        self.last_triggered = time.time()
        
        # Apply effects
        for effect in self.effects:
            self._apply_effect(effect, engine)
        
        return self.title, self.text
    
    def _apply_effect(self, effect: StoryletEffect, engine: 'GameEngine') -> None:
        """Apply a single effect to the game state."""
        if effect.effect_type == StoryletEffectType.GOLD:
            engine.player.gold += effect.value
            engine.messages.append(f"You gained {effect.value} gold.")
        
        elif effect.effect_type == StoryletEffectType.XP:
            if hasattr(engine.player.fighter, 'xp'):
                engine.player.fighter.xp += effect.value
                engine.messages.append(f"You gained {effect.value} XP.")
        
        elif effect.effect_type == StoryletEffectType.HEAL:
            engine.player.fighter.hp = min(engine.player.fighter.max_hp, engine.player.fighter.hp + effect.value)
            engine.messages.append(f"You healed for {effect.value} HP.")
        
        elif effect.effect_type == StoryletEffectType.DAMAGE:
            engine.player.fighter.hp -= effect.value
            engine.messages.append(f"You took {effect.value} damage.")
        
        elif effect.effect_type == StoryletEffectType.STATUS_EFFECT:
            from entities.status_effects import StatusEffect
            new_effect = StatusEffect(name=str(effect.value), duration=effect.duration, power=1)
            msg = engine.player.fighter.status_effects.add_effect(new_effect, engine.player.fighter, engine)
            engine.messages.append(f"You feel {effect.value}. {msg}")
        
        elif effect.effect_type == StoryletEffectType.STAT_BOOST:
            if hasattr(engine.player.fighter, effect.stat_name):
                current = getattr(engine.player.fighter, effect.stat_name)
                setattr(engine.player.fighter, effect.stat_name, current + effect.value)
                engine.messages.append(f"Your {effect.stat_name} increased by {effect.value}.")
        
        elif effect.effect_type == StoryletEffectType.REVEAL_MAP:
            # Reveal area around player
            radius = effect.value or 5
            for y in range(engine.player.y - radius, engine.player.y + radius + 1):
                for x in range(engine.player.x - radius, engine.player.x + radius + 1):
                    if engine.game_map.is_in_bounds(x, y):
                        engine.game_map.tiles[y][x].explored = True
            engine.messages.append("The map reveals itself to you.")
        
        elif effect.effect_type == StoryletEffectType.TRIGGER_STORYLET:
            if effect.target_storylet_id:
                storylet_system._queue_chain_trigger(effect.target_storylet_id)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize storylet to dict."""
        return {
            "storylet_id": self.storylet_id,
            "title": self.title,
            "text": self.text,
            "weight": self.weight,
            "preconditions": self.preconditions,
            "once_only": self.once_only,
            "category": self.category.name,
            "tags": self.tags,
            "priority": self.priority,
            "cooldown_seconds": self.cooldown_seconds,
            "effects": [{
                "effect_type": e.effect_type.name,
                "value": e.value,
                "duration": e.duration,
                "item_name": e.item_name,
                "stat_name": e.stat_name,
                "target_storylet_id": e.target_storylet_id,
            } for e in self.effects],
            "triggers_after": self.triggers_after,
            "triggers_next": self.triggers_next,
            "triggered": self.triggered,
            "trigger_count": self.trigger_count,
            "max_triggers": self.max_triggers,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Storylet':
        """Deserialize storylet from dict."""
        effects = []
        for e_data in data.get("effects", []):
            effects.append(StoryletEffect(
                effect_type=StoryletEffectType[e_data["effect_type"]],
                value=e_data.get("value"),
                duration=e_data.get("duration", 0),
                item_name=e_data.get("item_name", ""),
                stat_name=e_data.get("stat_name", ""),
                target_storylet_id=e_data.get("target_storylet_id", ""),
            ))
        
        return cls(
            title=data["title"],
            text=data["text"],
            weight=data.get("weight", 1.0),
            preconditions=data.get("preconditions", {}),
            once_only=data.get("once_only", True),
            storylet_id=data.get("storylet_id", ""),
            category=StoryletCategory[data.get("category", "LORE")],
            tags=data.get("tags", []),
            priority=data.get("priority", 0),
            cooldown_seconds=data.get("cooldown_seconds", 0.0),
            effects=effects,
            triggers_after=data.get("triggers_after"),
            triggers_next=data.get("triggers_next"),
            triggered=data.get("triggered", False),
            trigger_count=data.get("trigger_count", 0),
            max_triggers=data.get("max_triggers", 1),
        )

class StoryletSystem:
    def __init__(self, save_system=None):
        self.storylets: List[Storylet] = []
        self.save_system = save_system
        self._load_default_storylets()
        self._load_from_files()
    
    def _load_default_storylets(self):
        """Load the default hardcoded storylets."""
        self.storylets = [
            Storylet(
                "The Heavy Scent of Failure",
                "You find a notched blade embedded in the wall. It's identical to your own. The cycle is tighter than you thought.",
                preconditions={"depth_min": 3, "finesse_min": 5},
                category=StoryletCategory.LORE,
                tags=["combat", "weapon"],
                effects=[StoryletEffect(StoryletEffectType.XP, 5)],
            ),
            Storylet(
                "A Moment of Mercy",
                "A Famine Goblin cringes before you, offering a moldy crust. You realize it's not hunger in its eyes, but recognition.",
                preconditions={"depth_min": 2, "hp_lt": 10},
                category=StoryletCategory.NPC,
                tags=["goblin", "mercy"],
                effects=[StoryletEffect(StoryletEffectType.HEAL, 5)],
            ),
            Storylet(
                "The Auditor's Ledger",
                "You find a scorched piece of parchment. It lists your name under 'Assets to be Liquidated'.",
                preconditions={"brutality_min": 10},
                category=StoryletCategory.LORE,
                tags=["mystery", "paper"],
                effects=[StoryletEffect(StoryletEffectType.GOLD, 20)],
            ),
            Storylet(
                "The Wyrm's Shadow",
                "The heat here is unnatural. The Legacy Kernel isn't just a beast; it's a furnace for the world's sins.",
                preconditions={"depth_min": 4},
                category=StoryletCategory.ENVIRONMENT,
                tags=["heat", "boss"],
                effects=[StoryletEffect(StoryletEffectType.STATUS_EFFECT, "heat")],
            ),
            Storylet(
                "Echoes of the High Halls",
                "For a second, the stone turns to marble. You hear the ghostly sound of a banquet, then the damp rot returns.",
                preconditions={"depth_min": 1, "finesse_min": 2},
                category=StoryletCategory.MYSTERY,
                tags=["sound", "ghost"],
            ),
            Storylet(
                "The Siphoner's Receipt",
                "A slip of vellum drifts from nowhere: your name, a timestamp, and 'DEBIT: 3 seconds of future.' You never felt the withdrawal.",
                preconditions={"depth_min": 5, "brutality_min": 3},
                category=StoryletCategory.MYSTERY,
                tags=["time", "paper"],
                effects=[StoryletEffect(StoryletEffectType.DAMAGE, 2)],
            ),
            Storylet(
                "The Tollkeeper's Dream",
                "You wake from a micro-sleep standing up. In the dream you paid a toll you cannot remember counting. Your purse feels lighter—or maybe it always was.",
                preconditions={"depth_min": 4, "gold_min": 40},
                category=StoryletCategory.MYSTERY,
                tags=["dream", "gold"],
                effects=[StoryletEffect(StoryletEffectType.GOLD, -10)],
            ),
            Storylet(
                "Weaver's Knot",
                "Threads of dust hang in a shaft of nothing-light. For one heartbeat they spell a word you refuse to read. Then they are only dust again.",
                preconditions={"depth_min": 6, "finesse_min": 8},
                category=StoryletCategory.LORE,
                tags=["mystery", "dust"],
                effects=[StoryletEffect(StoryletEffectType.REVEAL_MAP, 3)],
            ),
        ]
    
    def _load_from_files(self):
        """Load storylets from JSON files in the storylets directory."""
        storylets_dir = Path("storylets")
        if not storylets_dir.exists():
            return
        
        for file_path in storylets_dir.glob("*.json"):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for storylet_data in data:
                            storylet = Storylet.from_dict(storylet_data)
                            self.add_storylet(storylet)
                    else:
                        storylet = Storylet.from_dict(data)
                        self.add_storylet(storylet)
            except Exception as e:
                print(f"Warning: Failed to load storylets from {file_path}: {e}")
    
    def add_storylet(self, storylet: Storylet):
        """Add a storylet to the system."""
        # Check for duplicate IDs
        if any(s.storylet_id == storylet.storylet_id for s in self.storylets):
            print(f"Warning: Storylet with ID {storylet.storylet_id} already exists, skipping")
            return
        self.storylets.append(storylet)
    
    def remove_storylet(self, storylet_id: str):
        """Remove a storylet by ID."""
        self.storylets = [s for s in self.storylets if s.storylet_id != storylet_id]
    
    def get_storylet_by_id(self, storylet_id: str) -> Optional[Storylet]:
        """Get a storylet by its ID."""
        for storylet in self.storylets:
            if storylet.storylet_id == storylet_id:
                return storylet
        return None
    
    def get_storylets_by_category(self, category: StoryletCategory) -> List[Storylet]:
        """Get all storylets in a category."""
        return [s for s in self.storylets if s.category == category]
    
    def get_storylets_by_tag(self, tag: str) -> List[Storylet]:
        """Get all storylets with a specific tag."""
        return [s for s in self.storylets if tag in s.tags]
    
    def load_persistent_state(self):
        """Load triggered storylets from save system."""
        if self.save_system:
            triggered_ids = self.save_system.persistent_context.triggered_storylets
            cooldowns = self.save_system.persistent_context.storylet_cooldowns
            
            for storylet in self.storylets:
                if storylet.storylet_id in triggered_ids:
                    storylet.triggered = True
                if storylet.storylet_id in cooldowns:
                    storylet.last_triggered = cooldowns[storylet.storylet_id]
    
    def save_persistent_state(self):
        """Save triggered storylets to save system."""
        if self.save_system:
            triggered_ids = [s.storylet_id for s in self.storylets if s.triggered]
            cooldowns = {s.storylet_id: s.last_triggered for s in self.storylets if s.cooldown_seconds > 0}
            
            self.save_system.persistent_context.triggered_storylets = triggered_ids
            self.save_system.persistent_context.storylet_cooldowns = cooldowns
            self.save_system.save_persistent_context()

    def get_vignette(self, engine: 'GameEngine', probability: float = 0.2, 
                    category_filter: Optional[StoryletCategory] = None,
                    tag_filter: Optional[str] = None) -> Optional[tuple[str, str]]:
        """Get a random vignette/storylet."""
        if random.random() > probability:
            return None
        
        current_time = time.time()
        available = []
        
        for storylet in self.storylets:
            # Apply filters
            if category_filter and storylet.category != category_filter:
                continue
            if tag_filter and tag_filter not in storylet.tags:
                continue
            
            # Check chain dependencies
            if storylet.triggers_after:
                prerequisite = self.get_storylet_by_id(storylet.triggers_after)
                if not prerequisite or not prerequisite.triggered:
                    continue
            
            if storylet.is_available(engine, current_time):
                available.append(storylet)
        
        if not available:
            return None
        
        # Sort by priority (higher priority first)
        available.sort(key=lambda s: s.priority, reverse=True)
        
        # Weighted selection among top priority storylets
        top_priority = available[0].priority
        priority_group = [s for s in available if s.priority == top_priority]
        
        weights = [s.weight for s in priority_group]
        chosen = random.choices(priority_group, weights=weights, k=1)[0]
        
        # Trigger the storylet
        title, text = chosen.trigger(engine)
        
        # Handle chaining
        if chosen.triggers_next:
            self._queue_chain_trigger(chosen.triggers_next)
        
        # Save persistent state
        self.save_persistent_state()
        
        # Publish event
        if hasattr(engine, 'events'):
            engine.events.publish({
                "type": "storylet_triggered",
                "storylet_id": chosen.storylet_id,
                "title": title,
            })
        
        return title, text
    
    def _queue_chain_trigger(self, storylet_id: str):
        """Queue a chained storylet to trigger on next check."""
        # This could be implemented with a queue system
        # For now, we'll just mark it as available immediately
        storylet = self.get_storylet_by_id(storylet_id)
        if storylet:
            storylet.last_triggered = 0  # Reset cooldown for chained storylet
    
    def trigger_storylet(self, storylet_id: str, engine: 'GameEngine') -> Optional[tuple[str, str]]:
        """Manually trigger a specific storylet by ID."""
        storylet = self.get_storylet_by_id(storylet_id)
        if not storylet:
            return None
        
        current_time = time.time()
        if not storylet.is_available(engine, current_time):
            return None
        
        return storylet.trigger(engine)
    
    def reset_storylet(self, storylet_id: str):
        """Reset a storylet's triggered state."""
        storylet = self.get_storylet_by_id(storylet_id)
        if storylet:
            storylet.triggered = False
            storylet.trigger_count = 0
            storylet.last_triggered = 0
    
    def export_storylets(self, file_path: str):
        """Export all storylets to a JSON file."""
        data = [s.to_dict() for s in self.storylets]
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def import_storylets(self, file_path: str):
        """Import storylets from a JSON file."""
        with open(file_path, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                for storylet_data in data:
                    storylet = Storylet.from_dict(storylet_data)
                    self.add_storylet(storylet)
            else:
                storylet = Storylet.from_dict(data)
                self.add_storylet(storylet)

storylet_system = StoryletSystem()
