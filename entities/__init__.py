"""
Entities module - all game entity classes
"""

# Standard library imports
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING, Union

# Third-party imports
# (none)

# Local imports
if TYPE_CHECKING:
    from engine import GameEngine

# Import from submodules
from entities.ai import (
    AIState,
    ActionResult,
    BaseAI,
    ConfusedAI,
    FleeAI,
    HostileAI,
    PatrolAI,
    Pathfinder,
    RangedAI,
    StunnedAI,
    StateMachineAI,
    can_see,
    chebyshev_distance,
    direction_toward,
    euclidean_distance,
)
from entities.components import (
    BaseComponent,
    Consumable,
    Equipment,
    Equippable,
    Fighter,
    Inventory,
    Level,
)
from entities.consumables import (
    ConfusionConsumable,
    GoldConsumable,
    HealingConsumable,
    LightningConsumable,
    ManaRestorationConsumable,
)
from entities.spells import (
    AbjurationSpell,
    ChronomancySpell,
    ConjurationSpell,
    EvocationSpell,
    ManaSystem,
    MagicConsumable,
    MentomancySpell,
    NecromancySpell,
    Spell,
    SpellSchool,
    TransmutationSpell,
)
from entities.status_effects import (
    AbsorbEffect,
    BarrierEffect,
    BurnEffect,
    CharmEffect,
    ConfusionEffect,
    CurseEffect,
    DecayEffect,
    FearEffect,
    FreezeEffect,
    HasteEffect,
    MagicArmorEffect,
    PoisonEffect,
    ReflectEffect,
    RegenEffect,
    SlowEffect,
    StunEffect,
    StatusEffect,
    StatusEffectManager,
    WetEffect,
)


@dataclass(eq=False)
class Entity:
    x: int
    y: int
    char: str
    color: str
    name: str
    blocks_movement: bool = False
    fighter: Optional[Fighter] = None
    ai: Optional[BaseAI] = None
    inventory: Optional[Inventory] = None
    consumable: Optional[Consumable] = None
    level: Optional[Level] = None
    equipment: Optional[Equipment] = None
    equippable: Optional[Equippable] = None
    barks: List[str] = field(default_factory=list)

    def __hash__(self):
        return id(self)

    def __post_init__(self):
        if self.fighter:
            self.fighter.entity = self
        if self.inventory:
            self.inventory.entity = self
        if self.consumable:
            self.consumable.entity = self
        if self.level:
            self.level.entity = self
        if self.equipment:
            self.equipment.entity = self
        if self.equippable:
            self.equippable.entity = self

    def move(self, dx: int, dy: int):
        self.x += dx
        self.y += dy


class Item(Entity):
    def __init__(
        self, 
        x: int, y: int, 
        char: str, color: str, 
        name: str, 
        consumable: Optional[Consumable] = None,
        equippable: Optional[Equippable] = None,
        barks: List[str] = None
    ):
        super().__init__(
            x=x, y=y, char=char, color=color, name=name, 
            blocks_movement=False, consumable=consumable,
            equippable=equippable, barks=barks or []
        )
        if self.consumable:
            self.consumable.entity = self
        if self.equippable:
            self.equippable.entity = self
        self.parent: Optional[Entity] = None


class Stairs(Entity):
    def __init__(self, x: int, y: int):
        super().__init__(
            x=x, y=y, char=">", color="#ffffff",
            name="Stairs", blocks_movement=False
        )


class Player(Entity):
    next_id = 1
    player_colors = ["#00ff00", "#00ffff", "#ff00ff", "#ffff00", "#ff8800", "#8800ff", "#ff0088", "#88ff00"]

    def __init__(self, x: int, y: int, player_id: int = None, name: str = "Player"):
        if player_id is None:
            player_id = Player.next_id
            Player.next_id += 1
        
        color_idx = (player_id - 1) % len(Player.player_colors)
        fighter = Fighter(hp=30, defense=1, power=2)
        super().__init__(
            x=x, y=y, 
            char="@", color=Player.player_colors[color_idx], 
            name=name, 
            blocks_movement=True,
            fighter=fighter,
            inventory=Inventory(capacity=26),
            level=Level(level_up_base=200),
            equipment=Equipment()
        )
        self.player_id = player_id
        self.gold = 0
        self.mana = ManaSystem(max_mana=20)
        self.mana.learned_spells = [
            Spell("Fireball", SpellSchool.EVOCATION, 5, damage=15, effect="burn", range_val=5),
            Spell("Ice Shard", SpellSchool.EVOCATION, 4, damage=10, effect="freeze", range_val=4),
            Spell("Heal", SpellSchool.EVOCATION, 6, healing=15, range_val=0),
            Spell("Lightning Bolt", SpellSchool.EVOCATION, 7, damage=20, effect="shock", range_val=6),
            TransmutationSpell("Stone to Mud", 8, "wall", ".", "#8B4513", "soft mud")
        ]
        for _ in self.mana.learned_spells:
            for spell in self.mana.learned_spells:
                self.mana.spell_slots[spell.school] = 2

    def to_dict(self):
        return {
            "player_id": self.player_id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "hp": self.fighter.hp,
            "max_hp": self.fighter.max_hp,
            "power": self.fighter.power,
            "defense": self.fighter.defense,
            "gold": self.gold,
            "level": self.level.current_level,
            "inventory_size": len(self.inventory.items),
            "weapon": self.equipment.weapon.name if self.equipment.weapon else None,
            "armor": self.equipment.armor.name if self.equipment.armor else None,
            "mana": self.mana.to_dict() if self.mana else None,
        }


class Monster(Entity):
    @staticmethod
    def goblin(x: int, y: int):
        fighter = Fighter(hp=10, defense=0, power=3, xp=35)
        entity = Monster(
            x=x, y=y,
            char="g", color="#8B4513",
            name="Goblin Scavenger",
            blocks_movement=True,
            fighter=fighter,
            level=Level(xp_given=35)
        )
        entity.ai = HostileAI()
        entity.barks = ["Shiny!", "Mine!", "Gimme!"]
        return entity

    @staticmethod
    def orc(x: int, y: int):
        fighter = Fighter(hp=16, defense=1, power=4, xp=60)
        entity = Monster(
            x=x, y=y,
            char="o", color="#3f7f3f",
            name="Orc Auditor",
            blocks_movement=True,
            fighter=fighter,
            level=Level(xp_given=60)
        )
        entity.ai = HostileAI()
        entity.barks = ["Audit!", "Pay up!", "Tax evasion!"]
        return entity

    @staticmethod
    def troll(x: int, y: int):
        fighter = Fighter(hp=30, defense=2, power=8, xp=100)
        entity = Monster(
            x=x, y=y,
            char="T", color="#007f00",
            name="Systemic Troll",
            blocks_movement=True,
            fighter=fighter,
            level=Level(xp_given=100)
        )
        entity.ai = HostileAI()
        entity.barks = ["Smash!", "Crush!", "System error!"]
        return entity

    @staticmethod
    def dragon(x: int, y: int):
        fighter = Fighter(hp=50, defense=3, power=12, xp=300)
        entity = Monster(
            x=x, y=y,
            char="D", color="#ff4444",
            name="The Legacy Kernel",
            blocks_movement=True,
            fighter=fighter,
            level=Level(xp_given=300)
        )
        entity.ai = HostileAI()
        entity.barks = ["DELETE!", "NULL POINTER!", "SEGFAULT!"]
        return entity

    @staticmethod
    def disrupter(x: int, y: int):
        fighter = Fighter(hp=20, defense=1, power=6, xp=80)
        entity = Monster(
            x=x, y=y,
            char="?", color="#ff00ff",
            name="Logic Disrupter",
            blocks_movement=True,
            fighter=fighter,
            level=Level(xp_given=80)
        )
        entity.ai = HostileAI()
        entity.barks = ["Confuse!", "Obfuscate!", "Logic fail!"]
        return entity

    @staticmethod
    def siphoner(x: int, y: int):
        fighter = Fighter(hp=15, defense=0, power=5, xp=70)
        entity = Monster(
            x=x, y=y,
            char="~", color="#00ffff",
            name="Data Siphoner",
            blocks_movement=True,
            fighter=fighter,
            level=Level(xp_given=70)
        )
        entity.ai = HostileAI()
        entity.barks = ["Siphon!", "Extract!", "Data mine!"]
        return entity

    @staticmethod
    def weaver(x: int, y: int):
        fighter = Fighter(hp=25, defense=2, power=7, xp=120)
        entity = Monster(
            x=x, y=y,
            char="W", color="#8844ff",
            name="Fate Weaver",
            blocks_movement=True,
            fighter=fighter,
            level=Level(xp_given=120)
        )
        entity.ai = HostileAI()
        entity.barks = ["Weave!", "Fate!", "Destiny!"]
        return entity


class LoreSystem:
    _lore_pool = [
        ("The First Crash", "Before the first reboot, there was only void. Then came the Code, and with it, the first bug."),
        ("The Eternal Loop", "Some say the dungeon is a recursion error that the developers never fixed. We are the exception handlers."),
        ("The Ghost in the Machine", "They speak of a player who found the exit. The logs say they were deleted for cheating."),
        ("The Memory Leak", "Every death adds to the heap. Someday, the garbage collector will come for us all."),
        ("The Stack Overflow", "Deep below, the recursion is infinite. Those who venture too far become part of the call stack."),
    ]

    @classmethod
    def get_lore_drop(cls, probability: float = 0.1) -> tuple[str, str]:
        import random
        if random.random() > probability:
            return None, None
        return random.choice(cls._lore_pool)

    @classmethod
    def get_death_scene(cls, depth: int, stats: dict) -> str:
        if depth < 3:
            return "A minor failure in the shallow sectors. Your logs are purged."
        if depth < 7:
            return "Deep in the sub-routines, you were caught in a race condition. Termination is final."
        if stats.get("brutality", 0) > 20:
            return "You fought with savage recursion, but the stack finally overflowed."
        return "The Maw consumes your data. You are but a footnote in the history of the system."

    @classmethod
    def get_hint(cls, depth: int, px: int, py: int, entities: list) -> str:
        import random
        hints = [
            "Rest with [Space] to recover spirit and let the world turn.",
            "Items in your satchel can be used with [Enter] or discarded with [d].",
            "Shrines offer power, but only once. Choose your moment.",
            "The Curio Peddler's wares are unique; spend your coin wisely.",
            "Some walls are thinner than they look... stone can become mud.",
        ]

        for e in entities:
            if hasattr(e, "fighter") and e.fighter and not isinstance(e, Player):
                dist = max(abs(e.x - px), abs(e.y - py))
                if dist < 3:
                    return f"The {e.name} is dangerously close. Prepare your arcana."

        if depth > 5:
            hints.append("The Legacy Kernel lies deeper still. You are not ready.")

        return random.choice(hints)


class Shrine(Entity):
    def __init__(self, x: int, y: int, shrine_kind: str):
        super().__init__(
            x=x, y=y,
            char="+", color="#ffd700",
            name=f"{shrine_kind.capitalize()} Shrine",
            blocks_movement=False
        )
        self.shrine_kind = shrine_kind
        self.shrine_spent = False

    def mark_spent(self):
        self.shrine_spent = True
        self.char = "x"
        self.color = "#666666"
        self.name = "Cold Cinder"


class CurioMerchant(Entity):
    def __init__(self, x: int, y: int, dungeon_level: int):
        super().__init__(
            x=x, y=y,
            char="&", color="#eecc66",
            name="Curio Peddler",
            blocks_movement=False
        )
        self.dungeon_level = dungeon_level
        self.stock = [
            {"key": "draught", "label": "Alchemical Draught", "price": 15 + dungeon_level * 2},
            {"key": "phial", "label": "Essence Phial", "price": 20 + dungeon_level * 3},
            {"key": "scroll", "label": "Storm-touched Parchment", "price": 25 + dungeon_level * 3},
        ]
        self.sold_out = [False] * len(self.stock)


__all__ = [
    # Base classes
    "BaseComponent",
    "Entity",
    "Item",
    "Player",
    "Monster",
    "Stairs",
    # Components
    "Fighter",
    "Equipment",
    "Inventory",
    "Level",
    "Consumable",
    "Equippable",
    # AI
    "BaseAI",
    "HostileAI",
    "ConfusedAI",
    "RangedAI",
    "PatrolAI",
    "FleeAI",
    "StunnedAI",
    "StateMachineAI",
    "AIState",
    "ActionResult",
    "Pathfinder",
    # AI utilities
    "chebyshev_distance",
    "euclidean_distance",
    "direction_toward",
    "can_see",
    # Status effects
    "StatusEffect",
    "StatusEffectManager",
    "BurnEffect",
    "PoisonEffect",
    "FreezeEffect",
    "WetEffect",
    "StunEffect",
    "RegenEffect",
    "HasteEffect",
    "SlowEffect",
    "DecayEffect",
    "FearEffect",
    "CharmEffect",
    "ConfusionEffect",
    "BarrierEffect",
    "ReflectEffect",
    "AbsorbEffect",
    "MagicArmorEffect",
    "CurseEffect",
    # Spells
    "Spell",
    "SpellSchool",
    "TransmutationSpell",
    "EvocationSpell",
    "ChronomancySpell",
    "MentomancySpell",
    "ConjurationSpell",
    "AbjurationSpell",
    "NecromancySpell",
    "ManaSystem",
    "MagicConsumable",
    # Consumables
    "HealingConsumable",
    "LightningConsumable",
    "ConfusionConsumable",
    "GoldConsumable",
    "ManaRestorationConsumable",
    # Special entities
    "LoreSystem",
    "Shrine",
    "CurioMerchant",
]
