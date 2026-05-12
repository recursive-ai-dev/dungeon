# Standard library imports
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

# Third-party imports
# (none)

# Local imports
if TYPE_CHECKING:
    from ..engine import GameEngine
    from . import Entity, Item


class BaseComponent:
    entity: Entity

    def __init__(self):
        pass


class Fighter(BaseComponent):
    def __init__(self, hp: int, defense: int, power: int, xp: int = 0):
        self.max_hp = hp
        self._hp = hp
        self.base_defense = defense
        self.base_power = power
        self.xp = xp
        self.status_effects: StatusEffectManager = StatusEffectManager()
        self.ascension_tier = 0

    @property
    def hp(self) -> int:
        return self._hp

    @hp.setter
    def hp(self, value: int):
        self._hp = max(0, min(value, self.max_hp))

    @property
    def defense(self) -> int:
        bonus = self.defense_bonus
        if self.ascension_tier >= 10:
             bonus += 2  # Tier 10: Fated Hardening
        return self.base_defense + bonus

    @property
    def power(self) -> int:
        bonus = self.power_bonus
        if self.ascension_tier >= 5:
            bonus += 1  # Tier 5: The Awakening Strength
        return self.base_power + bonus

    @property
    def defense_bonus(self) -> int:
        if self.entity.equipment:
            return self.entity.equipment.defense_bonus
        return 0

    @property
    def power_bonus(self) -> int:
        if self.entity.equipment:
            return self.entity.equipment.power_bonus
        return 0

    @property
    def elemental_resistance(self) -> dict:
        return {"fire": 0, "ice": 0, "lightning": 0, "poison": 0}


class Equipment(BaseComponent):
    def __init__(self, weapon: Optional[Item] = None, armor: Optional[Item] = None):
        self.weapon = weapon
        self.armor = armor

    @property
    def defense_bonus(self) -> int:
        bonus = 0
        if self.weapon and self.weapon.equippable:
            bonus += self.weapon.equippable.defense_bonus
        if self.armor and self.armor.equippable:
            bonus += self.armor.equippable.defense_bonus
        return bonus

    @property
    def power_bonus(self) -> int:
        bonus = 0
        if self.weapon and self.weapon.equippable:
            bonus += self.weapon.equippable.power_bonus
        if self.armor and self.armor.equippable:
            bonus += self.armor.equippable.power_bonus
        return bonus

    def toggle_equip(self, equippable_item: Item, engine: GameEngine):
        slot = equippable_item.equippable.slot
        if slot == "weapon":
            if self.weapon == equippable_item:
                self.weapon = None
                engine.messages.append(f"You unequip the {equippable_item.name}.")
            else:
                self.weapon = equippable_item
                engine.messages.append(f"You equip the {equippable_item.name}.")
        elif slot == "armor":
            if self.armor == equippable_item:
                self.armor = None
                engine.messages.append(f"You unequip the {equippable_item.name}.")
            else:
                self.armor = equippable_item
                engine.messages.append(f"You equip the {equippable_item.name}.")


class Equippable(BaseComponent):
    def __init__(self, slot: str, power_bonus: int = 0, defense_bonus: int = 0):
        self.slot = slot
        self.power_bonus = power_bonus
        self.defense_bonus = defense_bonus


class Level(BaseComponent):
    def __init__(
        self,
        level_up_base: int = 0,
        level_up_factor: int = 150,
        xp_given: int = 0,
    ):
        self.level_up_base = level_up_base
        self.level_up_factor = level_up_factor
        self.xp_given = xp_given
        self.current_level = 1
        self.current_xp = 0

    @property
    def experience_to_next_level(self) -> int:
        return self.level_up_base + self.current_level * self.level_up_factor

    @property
    def requires_level_up(self) -> bool:
        return self.current_xp >= self.experience_to_next_level

    def add_xp(self, xp: int) -> bool:
        if xp == 0 or self.level_up_base == 0:
            return False

        self.current_xp += xp
        if self.requires_level_up:
            return True
        return False

    def increase_level(self):
        self.current_xp -= self.experience_to_next_level
        self.current_level += 1


class Inventory(BaseComponent):
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.items: list[Item] = []

    def drop(self, item: Item, engine: GameEngine):
        self.items.remove(item)
        item.x, item.y = self.entity.x, self.entity.y
        engine.entities.append(item)
        engine.messages.append(f"You dropped the {item.name}.")


class Consumable(BaseComponent):
    def consume(self, engine: GameEngine):
        raise NotImplementedError()


# Import StatusEffectManager after definition to avoid circular import
from .status_effects import StatusEffectManager
