# Standard library imports
from __future__ import annotations

import random
from typing import TYPE_CHECKING

# Third-party imports
# (none)

# Local imports
from .components import Consumable

if TYPE_CHECKING:
    from engine import GameEngine
    from . import Entity



class GoldConsumable(Consumable):
    """Pick-up treasure: using from inventory banks the coin (or auto-counts as flavor)."""

    def __init__(self, amount: int):
        self.amount = amount

    def consume(self, engine: GameEngine):
        consumer = self.entity.parent
        consumer.gold += self.amount
        engine.messages.append(f"You tally {self.amount} tarnished coin into your hoard.")
        return self.amount


class ManaRestorationConsumable(Consumable):
    def __init__(self, amount: int):
        self.amount = amount

    def consume(self, engine: GameEngine):
        consumer = self.entity.parent
        if not consumer.mana:
            engine.messages.append("You have no well of spirit to refill.")
            return False
        if consumer.mana.mana >= consumer.mana.max_mana:
            engine.messages.append("Your spirit is already brimming.")
            return False
        restored = min(self.amount, consumer.mana.max_mana - consumer.mana.mana)
        consumer.mana.mana += restored
        engine.messages.append(f"The Essence Phial shatters softly; you draw in {restored} spirit.")
        return True


class HealingConsumable(Consumable):
    def __init__(self, amount: int):
        self.amount = amount

    def consume(self, engine: GameEngine):
        consumer = self.entity.parent
        if consumer.fighter.hp >= consumer.fighter.max_hp:
            engine.messages.append("Your health is already full.")
            return False
        
        amount_healed = min(consumer.fighter.max_hp - consumer.fighter.hp, self.amount)
        consumer.fighter.hp += amount_healed
        engine.messages.append(f"You consume the {self.entity.name}, and recover {amount_healed} HP!")
        return True


class LightningConsumable(Consumable):
    def __init__(self, damage: int, maximum_range: int):
        self.damage = damage
        self.maximum_range = maximum_range

    def consume(self, engine: GameEngine):
        consumer = self.entity.parent
        target = None
        closest_distance = self.maximum_range + 1

        for entity in engine.entities:
            if entity.fighter and entity != consumer and engine.game_map.tiles[entity.y][entity.x].visible:
                distance = max(abs(entity.x - consumer.x), abs(entity.y - consumer.y))

                if distance < closest_distance:
                    target = entity
                    closest_distance = distance

        if target:
            engine.messages.append(
                f"A lightning bolt strikes the {target.name} with a loud thunder, for {self.damage} HP!"
            )
            target.fighter.hp -= self.damage
            if target.fighter.hp <= 0:
                engine.messages.append(f"The {target.name} is dead!")
                loot = 4 + engine.dungeon_level + random.randint(0, 6)
                loot += (target.level.xp_given // 12) if target.level else 0
                consumer.gold += loot
                engine.messages.append(f"Static discharge reveals {loot} coin fused to the corpse.")
                if consumer.level:
                    xp_gained = target.level.xp_given
                    if consumer.level.add_xp(xp_gained):
                        engine.messages.append(f"You gained {xp_gained} experience points and leveled up!")
                        consumer.fighter.max_hp += 20
                        consumer.fighter.hp = consumer.fighter.max_hp
                        consumer.fighter.power += 1
                        consumer.level.increase_level()
                    else:
                        engine.messages.append(f"You gained {xp_gained} experience points.")
                engine.spatial.remove(target)
                engine.entities.remove(target)
            return True
        
        engine.messages.append("No enemy is close enough to strike.")
        return False


class ConfusionConsumable(Consumable):
    def __init__(self, num_turns: int):
        self.num_turns = num_turns

    def consume(self, engine: GameEngine):
        consumer = self.entity.parent
        target = None
        closest_distance = 6

        for entity in engine.entities:
            if entity.fighter and entity != consumer and engine.game_map.tiles[entity.y][entity.x].visible:
                distance = max(abs(entity.x - consumer.x), abs(entity.y - consumer.y))
                if distance < closest_distance:
                    target = entity
                    closest_distance = distance

        if target:
            engine.messages.append(f"A purple mist envelops the {target.name}!")
            if hasattr(target, 'ai'):
                from .ai import ConfusedAI
                target.ai = ConfusedAI(target.ai, self.num_turns)
            return True

        engine.messages.append("No enemy is close enough to confuse.")
        return False
