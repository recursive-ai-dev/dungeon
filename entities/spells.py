# Standard library imports
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Callable, Optional

# Third-party imports
# (none)

# Local imports
if TYPE_CHECKING:
    from dungeon.engine import GameEngine
    from dungeon.entities import Entity


class Spell:
    """Base class for all magical spells in the dungeon."""
    
    def __init__(self, name: str, school: str, mana_cost: int, damage: int = 0, 
                 healing: int = 0, effect: str = None, range_val: int = 1, aoe: int = 0,
                 cooldown: int = 0, cast_time: int = 1, requires_line_of_sight: bool = True,
                 description: str = ""):
        self.name = name
        self.school = school
        self.mana_cost = mana_cost
        self.damage = damage
        self.healing = healing
        self.effect = effect
        self.range_val = range_val
        self.aoe = aoe
        self.cooldown = 0
        self.max_cooldown = cooldown
        self.cast_time = cast_time  # Turns to cast (1 = standard, >1 = ritual)
        self.requires_line_of_sight = requires_line_of_sight
        self.description = description or f"A {school} spell."
        self.power_scaling = 1.0  # Multiplier for spell power
        self.mastery_level = 0  # Increases with use
        
    def cast(self, caster: Entity, target, engine: GameEngine) -> str:
        """Cast the spell. Target can be Entity or position tuple."""
        self._start_cooldown()
        self._gain_mastery()
        return f"{caster.name} casts {self.name}."
    
    def _start_cooldown(self):
        """Put the spell on cooldown."""
        if self.max_cooldown > 0:
            self.cooldown = self.max_cooldown
    
    def _gain_mastery(self):
        """Increase mastery from use, slightly improving efficiency."""
        self.mastery_level += 1
        if self.mastery_level % 10 == 0:
            self.power_scaling = min(2.0, self.power_scaling + 0.05)
    
    def tick_cooldown(self):
        """Reduce cooldown by 1. Call each turn."""
        if self.cooldown > 0:
            self.cooldown -= 1
    
    def is_ready(self) -> bool:
        """Check if spell is off cooldown."""
        return self.cooldown <= 0
    
    def get_effective_damage(self) -> int:
        """Calculate damage with scaling."""
        return int(self.damage * self.power_scaling)
    
    def get_effective_healing(self) -> int:
        """Calculate healing with scaling."""
        return int(self.healing * self.power_scaling)
    
    def can_target_position(self) -> bool:
        """Whether this spell can target a map position instead of an entity."""
        return False
    
    def to_dict(self):
        return {
            "name": self.name, "school": self.school, "mana_cost": self.mana_cost,
            "damage": self.damage, "healing": self.healing, "effect": self.effect,
            "range_val": self.range_val, "aoe": self.aoe, "cooldown": self.max_cooldown,
            "cast_time": self.cast_time, "requires_line_of_sight": self.requires_line_of_sight,
            "description": self.description, "mastery_level": self.mastery_level,
            "power_scaling": self.power_scaling
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Spell:
        spell = cls(
            name=data["name"],
            school=data["school"],
            mana_cost=data["mana_cost"],
            damage=data.get("damage", 0),
            healing=data.get("healing", 0),
            effect=data.get("effect"),
            range_val=data.get("range_val", 1),
            aoe=data.get("aoe", 0),
            cooldown=data.get("cooldown", 0),
            cast_time=data.get("cast_time", 1),
            requires_line_of_sight=data.get("requires_line_of_sight", True),
            description=data.get("description", "")
        )
        spell.mastery_level = data.get("mastery_level", 0)
        spell.power_scaling = data.get("power_scaling", 1.0)
        return spell


class SpellSchool:
    """Constants for magical schools."""
    EVOCATION = "evocation"
    CHRONOMANCY = "chronomancy"
    TRANSMUTATION = "transmutation"
    MENTOMANCY = "mentomancy"
    CONJURATION = "conjuration"
    DIVINATION = "divination"
    NECROMANCY = "necromancy"
    ABJURATION = "abjuration"
    ILLUSION = "illusion"
    
    ALL_SCHOOLS = [
        EVOCATION, CHRONOMANCY, TRANSMUTATION, MENTOMANCY,
        CONJURATION, DIVINATION, NECROMANCY, ABJURATION, ILLUSION
    ]


# =============================================================================
# EVOCATION SPELLS - Raw elemental damage
# =============================================================================

class EvocationSpell(Spell):
    """Spells dealing direct elemental damage."""
    
    ELEMENTS = ["fire", "ice", "lightning", "earth", "wind", "arcane"]
    
    def __init__(self, name: str, mana_cost: int, damage: int, element: str = "arcane",
                 range_val: int = 5, aoe: int = 0, cooldown: int = 0, **kwargs):
        super().__init__(
            name=name, school=SpellSchool.EVOCATION, mana_cost=mana_cost,
            damage=damage, range_val=range_val, aoe=aoe, cooldown=cooldown,
            description=f"Deals {damage} {element} damage.", **kwargs
        )
        self.element = element
        self.chain_hits = 0  # For chain lightning style spells
        self.chain_range = 0
        self.piercing = False  # Whether it pierces through targets
    
    def cast(self, caster: Entity, target, engine: GameEngine) -> str:
        if isinstance(target, tuple):
            return self._cast_at_position(caster, target, engine)
        
        base_msg = super().cast(caster, target, engine)
        
        if self.aoe > 0:
            return self._apply_aoe(caster, target, engine) or base_msg
        
        if target and hasattr(target, 'fighter') and target.fighter:
            dmg = self._calculate_damage(caster, target)
            actual = target.fighter.take_damage(dmg)
            engine.messages.append(f"{target.name} takes {actual} {self.element} damage!")
            self._apply_elemental_effect(target, engine)
            
            if self.chain_hits > 0 and self.chain_range > 0:
                self._chain_lightning(caster, target, engine, visited={target})
        
        return base_msg
    
    def _cast_at_position(self, caster: Entity, pos: tuple[int, int], engine: GameEngine) -> str:
        """Cast at a map position (for AoE ground targeting)."""
        super().cast(caster, pos, engine)
        if self.aoe > 0:
            return self._apply_aoe_at_position(caster, pos, engine)
        return f"{caster.name} casts {self.name} at the ground."
    
    def _calculate_damage(self, caster: Entity, target: Entity) -> int:
        """Calculate damage with caster bonuses and target resistances."""
        base = self.get_effective_damage()
        
        # Caster power bonus
        if hasattr(caster, 'fighter') and caster.fighter:
            base += getattr(caster.fighter, 'spell_power', 0)
        
        # Target resistance
        if hasattr(target, 'fighter') and target.fighter:
            resist = getattr(target.fighter, f'{self.element}_resist', 0)
            base = max(1, base - resist)
            defense = getattr(target.fighter, 'defense', 0)
            base = max(1, base - defense // 2)
        
        # Random variance ±15%
        variance = random.uniform(0.85, 1.15)
        return max(1, int(base * variance))
    
    def _apply_elemental_effect(self, target: Entity, engine: GameEngine):
        """Apply status effect based on element."""
        from dungeon.entities.status_effects import BurnEffect, FreezeEffect, StunEffect
        
        if self.element == "fire" and random.random() < 0.3:
            msg = target.fighter.status_effects.apply_effect(BurnEffect(3, 3), engine)
            if msg:
                engine.messages.append(msg)
        elif self.element == "ice" and random.random() < 0.25:
            msg = target.fighter.status_effects.apply_effect(FreezeEffect(2, 0), engine)
            if msg:
                engine.messages.append(msg)
        elif self.element == "lightning" and random.random() < 0.2:
            msg = target.fighter.status_effects.apply_effect(StunEffect(1, 0), engine)
            if msg:
                engine.messages.append(msg)
    
    def _chain_lightning(self, caster: Entity, target: Entity, engine: GameEngine, visited: set):
        """Chain to nearby targets."""
        if len(visited) >= self.chain_hits + 1:
            return
        
        for entity in engine.entities:
            if entity in visited or not entity.fighter:
                continue
            dist = max(abs(entity.x - target.x), abs(entity.y - target.y))
            if dist <= self.chain_range:
                dmg = int(self._calculate_damage(caster, entity) * 0.7)
                actual = entity.fighter.take_damage(dmg)
                engine.messages.append(
                    f"⚡ The {self.element} arcs to {entity.name} for {actual} damage!"
                )
                visited.add(entity)
                self._chain_lightning(caster, entity, engine, visited)
                break
    
    def _apply_aoe(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        """Apply area damage around target."""
        return self._apply_aoe_at_position(caster, (target.x, target.y), engine)
    
    def _apply_aoe_at_position(self, caster: Entity, center: tuple[int, int], engine: GameEngine) -> str:
        """Apply area damage at position."""
        cx, cy = center
        hit_count = 0
        
        for entity in list(engine.entities):
            if not entity.fighter or entity == caster:
                continue
            dist = math.sqrt((entity.x - cx)**2 + (entity.y - cy)**2)
            if dist <= self.aoe:
                # Falloff damage based on distance
                falloff = 1.0 - (dist / (self.aoe + 1))
                dmg = int(self._calculate_damage(caster, entity) * falloff)
                actual = entity.fighter.take_damage(max(1, dmg))
                engine.messages.append(f"{entity.name} caught in {self.name} for {actual} damage!")
                self._apply_elemental_effect(entity, engine)
                hit_count += 1
        
        return f"{caster.name} casts {self.name}, engulfing {hit_count} foes in {self.element}!"
    
    def can_target_position(self) -> bool:
        return self.aoe > 0


# =============================================================================
# CHRONOMANCY SPELLS - Time manipulation
# =============================================================================

class ChronomancySpell(Spell):
    """Spells manipulating the flow of time."""
    
    def __init__(self, name: str, mana_cost: int, time_effect: str, 
                 duration: int = 3, range_val: int = 5, cooldown: int = 3, **kwargs):
        super().__init__(
            name=name, school=SpellSchool.CHRONOMANCY, mana_cost=mana_cost,
            range_val=range_val, cooldown=cooldown,
            description=f"Manipulates time: {time_effect}.", **kwargs
        )
        self.time_effect = time_effect  # "haste", "slow", "rewind", "stop", "accelerate"
        self.duration = duration
    
    def cast(self, caster: Entity, target, engine: GameEngine) -> str:
        super().cast(caster, target, engine)
        
        if self.time_effect == "haste":
            return self._apply_haste(caster, target, engine)
        elif self.time_effect == "slow":
            return self._apply_slow(caster, target, engine)
        elif self.time_effect == "rewind":
            return self._apply_rewind(caster, engine)
        elif self.time_effect == "stop":
            return self._apply_time_stop(caster, target, engine)
        elif self.time_effect == "accelerate":
            return self._apply_accelerate(caster, engine)
        elif self.time_effect == "dilation":
            return self._apply_dilation(caster, target, engine)
        
        return f"{caster.name} warps time with {self.name}."
    
    def _apply_haste(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import HasteEffect
        if target and hasattr(target, 'fighter') and target.fighter:
            msg = target.fighter.status_effects.apply_effect(
                HasteEffect(self.duration, 1), engine
            )
            if msg:
                engine.messages.append(msg)
            return f"Time accelerates around {target.name}!"
        return "The spell fizzles."
    
    def _apply_slow(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import SlowEffect
        if target and hasattr(target, 'fighter') and target.fighter:
            msg = target.fighter.status_effects.apply_effect(
                SlowEffect(self.duration, 1), engine
            )
            if msg:
                engine.messages.append(msg)
            return f"Time crawls for {target.name}!"
        return "The spell fizzles."
    
    def _apply_rewind(self, caster: Entity, engine: GameEngine) -> str:
        """Rewind caster to previous state (heal and restore position)."""
        if hasattr(caster, 'fighter') and caster.fighter:
            heal_amount = int(caster.fighter.max_hp * 0.25)
            actual = min(heal_amount, caster.fighter.max_hp - caster.fighter.hp)
            caster.fighter.hp += actual
            
            # Restore some mana too
            if hasattr(caster, 'mana_system') and caster.mana_system:
                caster.mana_system.mana = min(
                    caster.mana_system.max_mana,
                    caster.mana_system.mana + 5
                )
            
            return f"{caster.name} rewinds their personal timeline, restoring {actual} HP!"
        return "Nothing to rewind."
    
    def _apply_time_stop(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import StunEffect
        if target and hasattr(target, 'fighter') and target.fighter:
            msg = target.fighter.status_effects.apply_effect(
                StunEffect(self.duration, 0), engine
            )
            if msg:
                engine.messages.append(msg)
            return f"{target.name} is frozen in time!"
        return "Time refuses to stop."
    
    def _apply_accelerate(self, caster: Entity, engine: GameEngine) -> str:
        """Next spell casts instantly (reduced cast time)."""
        if hasattr(caster, 'fighter') and caster.fighter:
            # Apply a buff that reduces next spell cast time
            caster.fighter._next_spell_instant = True
            return f"{caster.name} accelerates their next casting!"
        return "The spell fizzles."
    
    def _apply_dilation(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        """Target takes damage over time as they age rapidly."""
        from dungeon.entities.status_effects import DecayEffect
        if target and hasattr(target, 'fighter') and target.fighter:
            msg = target.fighter.status_effects.apply_effect(
                DecayEffect(self.duration, self.damage), engine
            )
            if msg:
                engine.messages.append(msg)
            return f"{target.name} ages centuries in seconds!"
        return "The spell fizzles."


# =============================================================================
# TRANSMUTATION SPELLS - Matter transformation
# =============================================================================

class TransmutationSpell(Spell):
    """Spells that transform terrain, items, or creatures."""
    
    def __init__(self, name: str, mana_cost: int, target_type: str, 
                 result_char: str = "", result_color: str = "", result_name: str = "",
                 range_val: int = 5, **kwargs):
        super().__init__(
            name=name, school=SpellSchool.TRANSMUTATION, mana_cost=mana_cost,
            range_val=range_val,
            description=f"Transmutes {target_type} into {result_name}.", **kwargs
        )
        self.target_type = target_type  # "wall", "floor", "water", "creature", "item"
        self.result_char = result_char
        self.result_color = result_color
        self.result_name = result_name
        self.duration = kwargs.get("duration", -1)  # -1 = permanent
    
    def cast(self, caster: Entity, target_pos: tuple[int, int], engine: GameEngine) -> str:
        super().cast(caster, target_pos, engine)
        x, y = target_pos
        
        if not engine.game_map.is_in_bounds(x, y):
            return "The spell dissipates into the void."
        
        tile = engine.game_map.tiles[y][x]
        
        if self.target_type == "wall":
            return self._transmute_wall(x, y, tile, engine)
        elif self.target_type == "floor":
            return self._transmute_floor(x, y, tile, engine)
        elif self.target_type == "water":
            return self._transmute_water(x, y, tile, engine)
        elif self.target_type == "creature":
            return self._transmute_creature(caster, x, y, engine)
        elif self.target_type == "trap":
            return self._transmute_trap(x, y, tile, engine)
        elif self.target_type == "terrain":
            return self._transmute_terrain(x, y, tile, engine)
        
        return "The spell finds no purchase here."
    
    def _transmute_wall(self, x: int, y: int, tile, engine: GameEngine) -> str:
        if not tile.walkable:
            tile.walkable = True
            tile.transparent = True
            if self.result_char:
                tile.char = self.result_char
            if self.result_color:
                tile.color = self.result_color
            return f"The solid stone ripples and turns into {self.result_name}."
        return "There is no wall to transmute."
    
    def _transmute_floor(self, x: int, y: int, tile, engine: GameEngine) -> str:
        if tile.walkable:
            tile.walkable = False
            tile.transparent = False
            if self.result_char:
                tile.char = self.result_char
            if self.result_color:
                tile.color = self.result_color
            return f"The floor solidifies into {self.result_name}!"
        return "The ground resists transmutation."
    
    def _transmute_water(self, x: int, y: int, tile, engine: GameEngine) -> str:
        # Assuming tiles have a 'liquid' property or similar
        if getattr(tile, 'liquid', False):
            tile.walkable = True
            tile.liquid = False
            return f"The water freezes into a solid {self.result_name} bridge!"
        return "There is no water here."
    
    def _transmute_creature(self, caster: Entity, x: int, y: int, engine: GameEngine) -> str:
        for entity in list(engine.entities):
            if entity.x == x and entity.y == y and entity != caster:
                if hasattr(entity, 'fighter') and entity.fighter:
                    # Polymorph - reduce stats temporarily
                    original_hp = entity.fighter.max_hp
                    entity.fighter.max_hp = max(1, int(original_hp * 0.5))
                    entity.fighter.hp = min(entity.fighter.hp, entity.fighter.max_hp)
                    entity.name = f"Polymorphed {entity.name}"
                    return f"{entity.name} is twisted into a weaker form!"
        return "No creature to transmute."
    
    def _transmute_trap(self, x: int, y: int, tile, engine: GameEngine) -> str:
        # Remove trap if present
        if hasattr(engine.game_map, 'traps'):
            for trap in list(engine.game_map.traps):
                if trap.x == x and trap.y == y:
                    engine.game_map.traps.remove(trap)
                    return f"The trap is transmuted into harmless {self.result_name}."
        return "No trap detected."
    
    def _transmute_terrain(self, x: int, y: int, tile, engine: GameEngine) -> str:
        tile.walkable = True
        tile.transparent = True
        if self.result_char:
            tile.char = self.result_char
        if self.result_color:
            tile.color = self.result_color
        return f"The terrain shifts into {self.result_name}."
    
    def can_target_position(self) -> bool:
        return True


# =============================================================================
# MENTOMANCY SPELLS - Mind and psychic powers
# =============================================================================

class MentomancySpell(Spell):
    """Spells affecting the mind - fear, charm, confusion, telepathy."""
    
    def __init__(self, name: str, mana_cost: int, mind_effect: str,
                 duration: int = 3, range_val: int = 6, cooldown: int = 2, **kwargs):
        super().__init__(
            name=name, school=SpellSchool.MENTOMANCY, mana_cost=mana_cost,
            range_val=range_val, cooldown=cooldown,
            description=f"Mental assault: {mind_effect}.", **kwargs
        )
        self.mind_effect = mind_effect  # "fear", "charm", "confuse", "dominate", "telepathy", "psychic_blast"
        self.duration = duration
        self.psychic_damage = kwargs.get("psychic_damage", 0)
    
    def cast(self, caster: Entity, target, engine: GameEngine) -> str:
        super().cast(caster, target, engine)
        
        if isinstance(target, tuple):
            return self._cast_psychic_aoe(caster, target, engine)
        
        if not target or not hasattr(target, 'fighter') or not target.fighter:
            return "The spell finds no mind to affect."
        
        # Check mental resistance
        resist = getattr(target.fighter, 'mental_resist', 0)
        caster_power = getattr(caster.fighter, 'spell_power', 0) if hasattr(caster, 'fighter') else 0
        
        if random.randint(1, 20) + resist > 10 + caster_power // 2:
            return f"{target.name} resists the mental intrusion!"
        
        if self.mind_effect == "fear":
            return self._apply_fear(caster, target, engine)
        elif self.mind_effect == "charm":
            return self._apply_charm(caster, target, engine)
        elif self.mind_effect == "confuse":
            return self._apply_confusion(caster, target, engine)
        elif self.mind_effect == "dominate":
            return self._apply_dominate(caster, target, engine)
        elif self.mind_effect == "psychic_blast":
            return self._apply_psychic_blast(caster, target, engine)
        elif self.mind_effect == "mind_read":
            return self._apply_mind_read(caster, target, engine)
        
        return f"{caster.name} probes {target.name}'s mind."
    
    def _apply_fear(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import FearEffect
        msg = target.fighter.status_effects.apply_effect(
            FearEffect(self.duration, 2), engine
        )
        if msg:
            engine.messages.append(msg)
        return f"{target.name} is overcome with terror!"
    
    def _apply_charm(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import CharmEffect
        msg = target.fighter.status_effects.apply_effect(
            CharmEffect(self.duration, caster), engine
        )
        if msg:
            engine.messages.append(msg)
        return f"{target.name} looks at {caster.name} with adoration!"
    
    def _apply_confusion(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import ConfusionEffect
        msg = target.fighter.status_effects.apply_effect(
            ConfusionEffect(self.duration, 1), engine
        )
        if msg:
            engine.messages.append(msg)
        return f"{target.name}'s thoughts scatter like leaves!"
    
    def _apply_dominate(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        """Briefly take control of target."""
        if hasattr(target, 'ai'):
            target._original_ai = target.ai
            target.ai = None  # Will need external handling for dominated turns
            target._dominated_by = caster
            target._dominated_turns = self.duration
            return f"{target.name} is dominated by {caster.name}'s will!"
        return f"{target.name} cannot be dominated."
    
    def _apply_psychic_blast(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        dmg = self.psychic_damage + (getattr(caster.fighter, 'spell_power', 0) if hasattr(caster, 'fighter') else 0)
        actual = target.fighter.take_damage(dmg)
        engine.messages.append(f"{target.name}'s mind is ravaged for {actual} psychic damage!")
        return f"{caster.name} unleashes a psychic assault!"
    
    def _apply_mind_read(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        """Reveal information about target."""
        info = []
        if hasattr(target, 'fighter') and target.fighter:
            info.append(f"HP: {target.fighter.hp}/{target.fighter.max_hp}")
            info.append(f"Defense: {target.fighter.defense}")
        if hasattr(target, 'ai') and target.ai:
            info.append("Hostile intent detected")
        
        engine.messages.append(f"You read {target.name}'s thoughts: {', '.join(info)}")
        return f"{target.name}'s thoughts flood into your mind!"
    
    def _cast_psychic_aoe(self, caster: Entity, pos: tuple[int, int], engine: GameEngine) -> str:
        """Psychic blast in area."""
        if self.aoe <= 0:
            return "The spell requires a target."
        
        cx, cy = pos
        hit = 0
        for entity in list(engine.entities):
            if not entity.fighter or entity == caster:
                continue
            dist = math.sqrt((entity.x - cx)**2 + (entity.y - cy)**2)
            if dist <= self.aoe:
                dmg = int(self.psychic_damage * (1 - dist / (self.aoe + 1)))
                actual = entity.fighter.take_damage(max(1, dmg))
                engine.messages.append(f"{entity.name}'s mind burns for {actual} damage!")
                hit += 1
        
        return f"A wave of psychic energy washes over {hit} minds!"
    
    def can_target_position(self) -> bool:
        return self.aoe > 0 or self.mind_effect == "psychic_blast"


# =============================================================================
# CONJURATION SPELLS - Summoning and creation
# =============================================================================

class ConjurationSpell(Spell):
    """Spells that summon creatures or create objects."""
    
    def __init__(self, name: str, mana_cost: int, summon_type: str = None,
                 summon_count: int = 1, duration: int = 10, range_val: int = 3,
                 cooldown: int = 5, **kwargs):
        super().__init__(
            name=name, school=SpellSchool.CONJURATION, mana_cost=mana_cost,
            range_val=range_val, cooldown=cooldown,
            description=f"Conjures {summon_type or 'aid'}.", **kwargs
        )
        self.summon_type = summon_type
        self.summon_count = summon_count
        self.duration = duration  # Summon duration in turns
        self.summon_hp = kwargs.get("summon_hp", 10)
        self.summon_damage = kwargs.get("summon_damage", 3)
    
    def cast(self, caster: Entity, target_pos: tuple[int, int], engine: GameEngine) -> str:
        super().cast(caster, target_pos, engine)
        
        if self.summon_type:
            return self._summon_creature(caster, target_pos, engine)
        return f"{caster.name} conjures... nothing."
    
    def _summon_creature(self, caster: Entity, pos: tuple[int, int], engine: GameEngine) -> str:
        from dungeon.entities import Entity
        from dungeon.components.fighter import Fighter
        from dungeon.ai import BasicMonster
        
        x, y = pos
        if not engine.game_map.is_in_bounds(x, y) or not engine.game_map.tiles[y][x].walkable:
            # Find nearest valid position
            found = False
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    nx, ny = x + dx, y + dy
                    if engine.game_map.is_in_bounds(nx, ny) and engine.game_map.tiles[ny][nx].walkable:
                        x, y = nx, ny
                        found = True
                        break
                if found:
                    break
            if not found:
                return "No space to summon!"
        
        summoned = []
        for i in range(self.summon_count):
            summon = Entity(
                x=x, y=y,
                char="s",
                color=(150, 150, 200),
                name=f"{caster.name}'s {self.summon_type}",
                blocks=True,
                fighter=Fighter(hp=self.summon_hp, defense=0, power=self.summon_damage),
                ai=BasicMonster()
            )
            summon._summoned = True
            summon._summon_duration = self.duration
            summon._summon_master = caster
            engine.entities.append(summon)
            summoned.append(summon.name)
        
        return f"{caster.name} summons {', '.join(summoned)}!"
    
    def can_target_position(self) -> bool:
        return True


# =============================================================================
# ABJURATION SPELLS - Protection and wards
# =============================================================================

class AbjurationSpell(Spell):
    """Defensive spells - shields, barriers, dispels."""
    
    def __init__(self, name: str, mana_cost: int, shield_type: str,
                 potency: int = 10, duration: int = 5, range_val: int = 5,
                 cooldown: int = 3, **kwargs):
        super().__init__(
            name=name, school=SpellSchool.ABJURATION, mana_cost=mana_cost,
            range_val=range_val, cooldown=cooldown,
            description=f"Protective {shield_type} shield.", **kwargs
        )
        self.shield_type = shield_type  # "barrier", "reflect", "absorb", "ward", "dispel"
        self.potency = potency
        self.duration = duration
    
    def cast(self, caster: Entity, target, engine: GameEngine) -> str:
        super().cast(caster, target, engine)
        
        if self.shield_type == "barrier":
            return self._apply_barrier(caster, target, engine)
        elif self.shield_type == "reflect":
            return self._apply_reflect(caster, target, engine)
        elif self.shield_type == "absorb":
            return self._apply_absorb(caster, target, engine)
        elif self.shield_type == "ward":
            return self._apply_ward(caster, target, engine)
        elif self.shield_type == "dispel":
            return self._apply_dispel(caster, target, engine)
        elif self.shield_type == "magic_armor":
            return self._apply_magic_armor(caster, target, engine)
        
        return f"{caster.name} weaves protective magic."
    
    def _apply_barrier(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import BarrierEffect
        if target and hasattr(target, 'fighter') and target.fighter:
            msg = target.fighter.status_effects.apply_effect(
                BarrierEffect(self.duration, self.potency), engine
            )
            if msg:
                engine.messages.append(msg)
            return f"A shimmering barrier surrounds {target.name}!"
        return "The barrier collapses."
    
    def _apply_reflect(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import ReflectEffect
        if target and hasattr(target, 'fighter') and target.fighter:
            msg = target.fighter.status_effects.apply_effect(
                ReflectEffect(self.duration, self.potency), engine
            )
            if msg:
                engine.messages.append(msg)
            return f"{target.name} is surrounded by reflective energy!"
        return "The reflection fails."
    
    def _apply_absorb(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import AbsorbEffect
        if target and hasattr(target, 'fighter') and target.fighter:
            msg = target.fighter.status_effects.apply_effect(
                AbsorbEffect(self.duration, self.potency), engine
            )
            if msg:
                engine.messages.append(msg)
            return f"{target.name} is wrapped in absorbing energies!"
        return "The absorption fails."
    
    def _apply_ward(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        """Ward against specific damage type."""
        if target and hasattr(target, 'fighter') and target.fighter:
            ward_type = getattr(self, 'ward_element', 'fire')
            attr_name = f'ward_{ward_type}'
            setattr(target.fighter, attr_name, self.potency)
            return f"{target.name} is warded against {ward_type}!"
        return "The ward fails."
    
    def _apply_dispel(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        """Remove magical effects from target."""
        if target and hasattr(target, 'fighter') and target.fighter:
            removed = 0
            if hasattr(target.fighter, 'status_effects'):
                effects = target.fighter.status_effects.active_effects
                for effect in list(effects):
                    if getattr(effect, 'is_magical', True):
                        effects.remove(effect)
                        removed += 1
            return f"{removed} magical effects dispelled from {target.name}!"
        return "Nothing to dispel."
    
    def _apply_magic_armor(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import MagicArmorEffect
        if target and hasattr(target, 'fighter') and target.fighter:
            msg = target.fighter.status_effects.apply_effect(
                MagicArmorEffect(self.duration, self.potency), engine
            )
            if msg:
                engine.messages.append(msg)
            return f"Arcane armor materializes around {target.name}!"
        return "The armor fails to form."


# =============================================================================
# NECROMANCY SPELLS - Life drain and undead
# =============================================================================

class NecromancySpell(Spell):
    """Dark magic - life drain, curses, raising dead."""
    
    def __init__(self, name: str, mana_cost: int, necromancy_type: str,
                 damage: int = 0, healing: int = 0, range_val: int = 4,
                 cooldown: int = 3, **kwargs):
        super().__init__(
            name=name, school=SpellSchool.NECROMANCY, mana_cost=mana_cost,
            damage=damage, healing=healing, range_val=range_val, cooldown=cooldown,
            description=f"Necromantic {necromancy_type}.", **kwargs
        )
        self.necromancy_type = necromancy_type  # "drain", "curse", "raise", "animate", "wither"
    
    def cast(self, caster: Entity, target, engine: GameEngine) -> str:
        super().cast(caster, target, engine)
        
        if self.necromancy_type == "drain":
            return self._life_drain(caster, target, engine)
        elif self.necromancy_type == "curse":
            return self._apply_curse(caster, target, engine)
        elif self.necromancy_type == "raise":
            return self._raise_dead(caster, target, engine)
        elif self.necromancy_type == "wither":
            return self._apply_wither(caster, target, engine)
        elif self.necromancy_type == "soul_harvest":
            return self._soul_harvest(caster, engine)
        
        return f"{caster.name} channels dark energies."
    
    def _life_drain(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        if target and hasattr(target, 'fighter') and target.fighter:
            dmg = self.get_effective_damage()
            actual = target.fighter.take_damage(dmg)
            
            # Heal caster for portion of damage
            if hasattr(caster, 'fighter') and caster.fighter:
                heal = min(actual // 2, caster.fighter.max_hp - caster.fighter.hp)
                caster.fighter.hp += heal
                engine.messages.append(f"{caster.name} drains {actual} HP and heals for {heal}!")
            
            return f"Dark tendrils sap {target.name}'s life force!"
        return "The drain finds no life to steal."
    
    def _apply_curse(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import CurseEffect
        if target and hasattr(target, 'fighter') and target.fighter:
            msg = target.fighter.status_effects.apply_effect(
                CurseEffect(5, 3), engine
            )
            if msg:
                engine.messages.append(msg)
            return f"{target.name} is cursed!"
        return "The curse fails."
    
    def _raise_dead(self, caster: Entity, target_pos: tuple[int, int], engine: GameEngine) -> str:
        """Raise a nearby corpse as undead servant."""
        x, y = target_pos
        # Look for a "corpse" or dead entity marker
        for entity in list(engine.entities):
            if getattr(entity, 'is_corpse', False) and entity.x == x and entity.y == y:
                entity.name = f"Undead {entity.name.replace(' corpse', '')}"
                entity.char = "z"
                entity.color = (100, 150, 100)
                entity.is_corpse = False
                if hasattr(entity, 'fighter') and entity.fighter:
                    entity.fighter.hp = entity.fighter.max_hp // 2
                entity._summoned = True
                entity._summon_master = caster
                return f"{entity.name} rises to serve {caster.name}!"
        return "No corpse to raise."
    
    def _apply_wither(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import WitherEffect
        if target and hasattr(target, 'fighter') and target.fighter:
            msg = target.fighter.status_effects.apply_effect(
                WitherEffect(4, self.damage), engine
            )
            if msg:
                engine.messages.append(msg)
            return f"{target.name} withers under the necromantic curse!"
        return "The withering fails."
    
    def _soul_harvest(self, caster: Entity, engine: GameEngine) -> str:
        """Drain life from all nearby enemies."""
        if not hasattr(caster, 'fighter') or not caster.fighter:
            return "The spell fizzles."
        
        total_drained = 0
        for entity in list(engine.entities):
            if entity == caster or not hasattr(entity, 'fighter') or not entity.fighter:
                continue
            dist = max(abs(entity.x - caster.x), abs(entity.y - caster.y))
            if dist <= self.range_val:
                dmg = max(1, self.damage // dist)
                actual = entity.fighter.take_damage(dmg)
                total_drained += actual // 2
        
        heal = min(total_drained, caster.fighter.max_hp - caster.fighter.hp)
        caster.fighter.hp += heal
        return f"{caster.name} harvests souls, healing for {heal} HP!"
    
    def can_target_position(self) -> bool:
        return self.necromancy_type == "raise"


# =============================================================================
# DIVINATION SPELLS - Detection and revelation
# =============================================================================

class DivinationSpell(Spell):
    """Spells for detection, identification, and foresight."""
    
    def __init__(self, name: str, mana_cost: int, divination_type: str,
                 range_val: int = 10, duration: int = 20, **kwargs):
        super().__init__(
            name=name, school=SpellSchool.DIVINATION, mana_cost=mana_cost,
            range_val=range_val,
            description=f"Reveals {divination_type}.", **kwargs
        )
        self.divination_type = divination_type  # "map", "enemies", "items", "traps", "magic", "identify"
        self.duration = duration
    
    def cast(self, caster: Entity, target, engine: GameEngine) -> str:
        super().cast(caster, target, engine)
        
        if self.divination_type == "map":
            return self._reveal_map(caster, engine)
        elif self.divination_type == "enemies":
            return self._reveal_enemies(caster, engine)
        elif self.divination_type == "traps":
            return self._reveal_traps(caster, engine)
        elif self.divination_type == "items":
            return self._reveal_items(caster, engine)
        elif self.divination_type == "identify":
            return self._identify_item(caster, target, engine)
        elif self.divination_type == "foresight":
            return self._apply_foresight(caster, engine)
        
        return f"{caster.name} peers beyond the veil."
    
    def _reveal_map(self, caster: Entity, engine: GameEngine) -> str:
        """Reveal entire map."""
        for y in range(engine.game_map.height):
            for x in range(engine.game_map.width):
                engine.game_map.tiles[y][x].explored = True
                engine.game_map.tiles[y][x].visible = True
        return "The dungeon's layout is burned into your mind!"
    
    def _reveal_enemies(self, caster: Entity, engine: GameEngine) -> str:
        """Mark all enemies."""
        count = 0
        for entity in engine.entities:
            if hasattr(entity, 'fighter') and entity.fighter and entity != caster:
                entity._detected = True
                count += 1
        return f"You sense {count} hostile minds!"
    
    def _reveal_traps(self, caster: Entity, engine: GameEngine) -> str:
        """Reveal traps in area."""
        if hasattr(engine.game_map, 'traps'):
            for trap in engine.game_map.traps:
                trap.revealed = True
            return f"You detect {len(engine.game_map.traps)} traps!"
        return "No traps detected."
    
    def _reveal_items(self, caster: Entity, engine: GameEngine) -> str:
        """Reveal items on floor."""
        count = 0
        for entity in engine.entities:
            if getattr(entity, 'is_item', False):
                entity._highlighted = True
                count += 1
        return f"You sense {count} magical items!"
    
    def _identify_item(self, caster: Entity, target, engine: GameEngine) -> str:
        """Identify an item."""
        if target and getattr(target, 'is_item', False):
            target.identified = True
            return f"The {target.name} reveals its true nature: {target.description}!"
        return "Nothing to identify."
    
    def _apply_foresight(self, caster: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import ForesightEffect
        if hasattr(caster, 'fighter') and caster.fighter:
            msg = caster.fighter.status_effects.apply_effect(
                ForesightEffect(self.duration, 5), engine
            )
            if msg:
                engine.messages.append(msg)
            return "You glimpse possible futures!"
        return "The future remains clouded."


# =============================================================================
# ILLUSION SPELLS - Deception and misdirection
# =============================================================================

class IllusionSpell(Spell):
    """Spells creating false images and invisibility."""
    
    def __init__(self, name: str, mana_cost: int, illusion_type: str,
                 duration: int = 5, range_val: int = 5, **kwargs):
        super().__init__(
            name=name, school=SpellSchool.ILLUSION, mana_cost=mana_cost,
            range_val=range_val,
            description=f"Creates {illusion_type} illusion.", **kwargs
        )
        self.illusion_type = illusion_type  # "invisibility", "mirror_image", "phantasm", "blind", "silence"
        self.duration = duration
    
    def cast(self, caster: Entity, target, engine: GameEngine) -> str:
        super().cast(caster, target, engine)
        
        if self.illusion_type == "invisibility":
            return self._apply_invisibility(caster, target, engine)
        elif self.illusion_type == "mirror_image":
            return self._create_mirror_images(caster, engine)
        elif self.illusion_type == "phantasm":
            return self._create_phantasm(caster, target, engine)
        elif self.illusion_type == "blind":
            return self._apply_blind(caster, target, engine)
        elif self.illusion_type == "silence":
            return self._apply_silence(caster, target, engine)
        
        return f"{caster.name} weaves an illusion."
    
    def _apply_invisibility(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import InvisibleEffect
        tgt = target or caster
        if hasattr(tgt, 'fighter') and tgt.fighter:
            msg = tgt.fighter.status_effects.apply_effect(
                InvisibleEffect(self.duration, 1), engine
            )
            if msg:
                engine.messages.append(msg)
            return f"{tgt.name} fades from sight!"
        return "The invisibility fails."
    
    def _create_mirror_images(self, caster: Entity, engine: GameEngine) -> str:
        """Create decoy images of caster."""
        images = []
        for i in range(3):
            # Create illusory copies
            img = type(caster)(
                x=caster.x + random.choice([-1, 0, 1]),
                y=caster.y + random.choice([-1, 0, 1]),
                char=caster.char,
                color=caster.color,
                name=f"Mirror {caster.name}",
                blocks=False
            )
            img._illusion = True
            img._illusion_duration = self.duration
            engine.entities.append(img)
            images.append(img)
        
        caster._mirror_images = images
        return f"{len(images)} mirror images of {caster.name} appear!"
    
    def _create_phantasm(self, caster: Entity, target_pos: tuple[int, int], engine: GameEngine) -> str:
        """Create a terrifying illusion at position."""
        from dungeon.entities import Entity
        x, y = target_pos
        phantasm = Entity(
            x=x, y=y,
            char="P",
            color=(200, 50, 200),
            name="Phantasmal Horror",
            blocks=False
        )
        phantasm._illusion = True
        phantasm._illusion_duration = self.duration
        phantasm._fear_aura = True
        engine.entities.append(phantasm)
        return "A horrifying phantasm materializes!"
    
    def _apply_blind(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import BlindEffect
        if target and hasattr(target, 'fighter') and target.fighter:
            msg = target.fighter.status_effects.apply_effect(
                BlindEffect(self.duration, 1), engine
            )
            if msg:
                engine.messages.append(msg)
            return f"{target.name} is blinded!"
        return "The blindness fails."
    
    def _apply_silence(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        from dungeon.entities.status_effects import SilenceEffect
        if target and hasattr(target, 'fighter') and target.fighter:
            msg = target.fighter.status_effects.apply_effect(
                SilenceEffect(self.duration, 1), engine
            )
            if msg:
                engine.messages.append(msg)
            return f"{target.name} is silenced!"
        return "The silence fails."


# =============================================================================
# MANA SYSTEM - Expanded
# =============================================================================

class ManaSystem:
    """Advanced mana and spell slot management system."""
    
    def __init__(self, max_mana: int = 20):
        self.max_mana = max_mana
        self._mana = max_mana
        self.mana_regen = 1
        self.learned_spells: list[Spell] = []
        self.spell_slots = {school: 0 for school in SpellSchool.ALL_SCHOOLS}
        self.school_mastery = {school: 0 for school in SpellSchool.ALL_SCHOOLS}
        self.active_concentration: Optional[Spell] = None
        self.concentration_target = None
        self.spell_resistance = 0
        self.spell_power = 0
        self.casting_modifiers: list[SpellModifier] = []
        self._mana_overflow = 0  # Excess mana from potions
        self._mana_shield = 0  # Damage absorbed by mana instead of HP
    
    @property
    def mana(self) -> int:
        return self._mana
    
    @mana.setter
    def mana(self, value: int):
        self._mana = max(0, min(value, self.max_mana + self._mana_overflow))
    
    @property
    def mana_percentage(self) -> float:
        return self._mana / self.max_mana if self.max_mana > 0 else 0.0
    
    def can_cast(self, spell: Spell) -> bool:
        """Check if spell can be cast considering all factors."""
        if not spell.is_ready():
            return False
        if self._mana < spell.mana_cost:
            return False
        if self.spell_slots.get(spell.school, 0) <= 0:
            # Allow casting with just mana if no slots (but at higher cost)
            return self._mana >= spell.mana_cost * 2
        return True
    
    def get_cast_cost(self, spell: Spell) -> int:
        """Calculate actual mana cost with modifiers."""
        cost = spell.mana_cost
        
        # School mastery reduces cost
        mastery = self.school_mastery.get(spell.school, 0)
        cost = int(cost * max(0.5, 1.0 - mastery * 0.02))
        
        # Apply active modifiers
        for mod in self.casting_modifiers:
            cost = mod.modify_cost(cost, spell)
        
        # Overcast without slot
        if self.spell_slots.get(spell.school, 0) <= 0:
            cost *= 2
        
        return max(1, cost)
    
    def spend_mana(self, amount: int) -> bool:
        if self._mana >= amount:
            self._mana -= amount
            return True
        return False
    
    def regenerate(self):
        """Regenerate mana and reduce overflow."""
        regen = self.mana_regen
        
        # Bonus regen at low mana
        if self.mana_percentage < 0.25:
            regen += 1
        
        self._mana = min(self.max_mana, self._mana + regen)
        if self._mana_overflow > 0:
            self._mana_overflow = max(0, self._mana_overflow - 1)
    
    def learn_spell(self, spell: Spell) -> bool:
        """Learn a new spell. Returns True if newly learned."""
        if any(s.name == spell.name for s in self.learned_spells):
            return False
        
        self.learned_spells.append(spell)
        self.spell_slots[spell.school] = self.spell_slots.get(spell.school, 0) + 1
        return True
    
    def forget_spell(self, spell_name: str) -> bool:
        """Forget a spell to free up a slot."""
        for spell in self.learned_spells:
            if spell.name == spell_name:
                self.learned_spells.remove(spell)
                self.spell_slots[spell.school] = max(0, self.spell_slots[spell.school] - 1)
                return True
        return False
    
    def add_school_mastery(self, school: str, amount: int = 1):
        """Increase mastery in a school."""
        if school in self.school_mastery:
            self.school_mastery[school] += amount
            # Every 5 mastery grants a bonus slot
            if self.school_mastery[school] % 5 == 0:
                self.spell_slots[school] += 1
    
    def set_concentration(self, spell: Spell, target=None):
        """Set active concentration spell. Ends previous concentration."""
        self.break_concentration()
        self.active_concentration = spell
        self.concentration_target = target
    
    def break_concentration(self):
        """Break concentration on current spell."""
        if self.active_concentration:
            self.active_concentration = None
            self.concentration_target = None
    
    def check_concentration(self, damage_taken: int) -> bool:
        """Check if concentration is maintained after taking damage."""
        if not self.active_concentration:
            return True
        # DC 10 or half damage, whichever is higher
        dc = max(10, damage_taken // 2)
        roll = random.randint(1, 20)
        if roll + self.spell_power < dc:
            self.break_concentration()
            return False
        return True
    
    def add_mana_shield(self, amount: int):
        """Add temporary mana shield that absorbs damage."""
        self._mana_shield += amount
    
    def absorb_damage_with_mana(self, damage: int) -> int:
        """Absorb damage with mana shield. Returns remaining damage."""
        if self._mana_shield <= 0:
            return damage
        absorbed = min(damage, self._mana_shield)
        self._mana_shield -= absorbed
        # Also costs mana
        self._mana = max(0, self._mana - absorbed // 2)
        return damage - absorbed
    
    def get_spells_by_school(self, school: str) -> list[Spell]:
        """Get all learned spells of a specific school."""
        return [s for s in self.learned_spells if s.school == school]
    
    def get_ready_spells(self) -> list[Spell]:
        """Get all spells that are off cooldown."""
        return [s for s in self.learned_spells if s.is_ready()]
    
    def tick_all_cooldowns(self):
        """Reduce cooldowns for all learned spells."""
        for spell in self.learned_spells:
            spell.tick_cooldown()
    
    def to_dict(self):
        return {
            "max_mana": self.max_mana,
            "mana": self._mana,
            "mana_regen": self.mana_regen,
            "spells": [s.to_dict() for s in self.learned_spells],
            "spell_slots": self.spell_slots,
            "school_mastery": self.school_mastery,
            "spell_resistance": self.spell_resistance,
            "spell_power": self.spell_power,
            "mana_shield": self._mana_shield
        }
    
    @classmethod
    def from_dict(cls, data):
        mana_sys = cls(data.get("max_mana", 20))
        mana_sys._mana = data.get("mana", 20)
        mana_sys.mana_regen = data.get("mana_regen", 1)
        mana_sys.spell_slots = data.get("spell_slots", {s: 0 for s in SpellSchool.ALL_SCHOOLS})
        mana_sys.school_mastery = data.get("school_mastery", {s: 0 for s in SpellSchool.ALL_SCHOOLS})
        mana_sys.spell_resistance = data.get("spell_resistance", 0)
        mana_sys.spell_power = data.get("spell_power", 0)
        mana_sys._mana_shield = data.get("mana_shield", 0)
        
        for s_data in data.get("spells", []):
            spell = Spell.from_dict(s_data)
            mana_sys.learned_spells.append(spell)
        
        return mana_sys


# =============================================================================
# SPELL MODIFIERS - Metamagic
# =============================================================================

class SpellModifier:
    """Metamagic modifiers that alter spell behavior."""
    
    def __init__(self, name: str, mana_multiplier: float = 1.0, 
                 cooldown_increase: int = 0, description: str = ""):
        self.name = name
        self.mana_multiplier = mana_multiplier
        self.cooldown_increase = cooldown_increase
        self.description = description
    
    def modify_cost(self, base_cost: int, spell: Spell) -> int:
        return int(base_cost * self.mana_multiplier)
    
    def modify_damage(self, base_damage: int, spell: Spell) -> int:
        return base_damage
    
    def modify_range(self, base_range: int, spell: Spell) -> int:
        return base_range
    
    def can_apply(self, spell: Spell) -> bool:
        return True


class EmpowerSpell(SpellModifier):
    """Increase spell damage by 50% at 1.5x mana cost."""
    
    def __init__(self):
        super().__init__("Empower", mana_multiplier=1.5, description="+50% damage")
    
    def modify_damage(self, base_damage: int, spell: Spell) -> int:
        return int(base_damage * 1.5)


class QuickenSpell(SpellModifier):
    """Cast as free action at 2x mana cost."""
    
    def __init__(self):
        super().__init__("Quicken", mana_multiplier=2.0, description="Cast as swift action")


class ExtendSpell(SpellModifier):
    """Double duration at 1.3x mana cost."""
    
    def __init__(self):
        super().__init__("Extend", mana_multiplier=1.3, description="Double duration")


class WidenSpell(SpellModifier):
    """Increase AoE by 2 at 1.4x mana cost."""
    
    def __init__(self):
        super().__init__("Widen", mana_multiplier=1.4, description="+2 AoE radius")
    
    def modify_range(self, base_range: int, spell: Spell) -> int:
        return base_range + 2


class SilentSpell(SpellModifier):
    """Cast without verbal components at 1.2x mana cost."""
    
    def __init__(self):
        super().__init__("Silent", mana_multiplier=1.2, description="No verbal components")


class TwinSpell(SpellModifier):
    """Target two creatures at 2.5x mana cost."""
    
    def __init__(self):
        super().__init__("Twin", mana_multiplier=2.5, description="Two targets")


# =============================================================================
# SPELL COMBOS - Synergy system
# =============================================================================

class SpellCombo:
    """Defines a combination of spells that produces enhanced effects."""
    
    def __init__(self, name: str, required_spells: list[str], 
                 bonus_effect: str, bonus_damage: int = 0,
                 bonus_duration: int = 0, description: str = ""):
        self.name = name
        self.required_spells = required_spells  # List of spell names
        self.bonus_effect = bonus_effect
        self.bonus_damage = bonus_damage
        self.bonus_duration = bonus_duration
        self.description = description
    
    def check_trigger(self, cast_spells: list[str]) -> bool:
        """Check if combo conditions are met."""
        # Check if all required spells were cast recently
        return all(req in cast_spells for req in self.required_spells)
    
    def apply(self, caster: Entity, target, engine: GameEngine) -> str:
        """Apply combo bonus effect."""
        return f"COMBO: {self.name}! {self.bonus_effect}"


class ComboRegistry:
    """Registry of known spell combinations."""
    
    COMBOS = [
        SpellCombo(
            "Steam Cloud",
            ["Fireball", "Ice Bolt"],
            "Creates a steam cloud that blinds enemies",
            bonus_duration=3,
            description="Fire + Ice creates obscuring steam"
        ),
        SpellCombo(
            "Supernova",
            ["Fireball", "Fireball"],
            "Massive explosion! Damage doubled",
            bonus_damage=20,
            description="Double fire creates a supernova"
        ),
        SpellCombo(
            "Absolute Zero",
            ["Ice Bolt", "Time Stop"],
            "Enemy is frozen in time permanently",
            bonus_duration=5,
            description="Ice + Time creates absolute zero"
        ),
        SpellCombo(
            "Psychic Fire",
            ["Fireball", "Mind Blast"],
            "Burning thoughts! Fire damage ignores defense",
            bonus_damage=10,
            description="Fire + Mind creates burning thoughts"
        ),
        SpellCombo(
            "Raise Legion",
            ["Raise Dead", "Summon Skeleton"],
            "Summons an undead army",
            bonus_duration=10,
            description="Necromancy + Conjuration raises a legion"
        ),
        SpellCombo(
            "Diamond Skin",
            ["Stone Skin", "Magic Armor"],
            "Ultimate defense! Immunity to physical and magical",
            bonus_duration=5,
            description="Earth + Abjuration creates diamond skin"
        ),
    ]
    
    @classmethod
    def check_combos(cls, recent_spells: list[str]) -> list[SpellCombo]:
        """Check for triggered combos in recent spell history."""
        triggered = []
        for combo in cls.COMBOS:
            if combo.check_trigger(recent_spells):
                triggered.append(combo)
        return triggered


# =============================================================================
# SPELL BOOK / GRIMOIRE
# =============================================================================

class SpellBook:
    """A collection of spells that can be studied to learn them."""
    
    def __init__(self, name: str = "Spell Tome", rarity: str = "common"):
        self.name = name
        self.rarity = rarity
        self.spells: list[Spell] = []
        self.required_intelligence = 10
        self.is_cursed = False
        self.read_count = 0
    
    def add_spell(self, spell: Spell):
        self.spells.append(spell)
    
    def study(self, reader: Entity, engine: GameEngine) -> str:
        """Attempt to learn a spell from the book."""
        if not hasattr(reader, 'mana_system') or not reader.mana_system:
            return "You cannot comprehend the arcane writings."
        
        intel = getattr(reader, 'intelligence', 10)
        if intel < self.required_intelligence:
            return "The text is too complex for your current understanding."
        
        if self.is_cursed and random.random() < 0.3:
            # Cursed book effect
            reader.fighter.take_damage(5)
            return "The book burns your mind! Cursed knowledge!"
        
        learned = []
        for spell in self.spells:
            if reader.mana_system.learn_spell(spell):
                learned.append(spell.name)
        
        self.read_count += 1
        if learned:
            return f"You study {self.name} and learn: {', '.join(learned)}!"
        return "You already know all spells in this tome."
    
    def to_dict(self):
        return {
            "name": self.name,
            "rarity": self.rarity,
            "spells": [s.to_dict() for s in self.spells],
            "required_intelligence": self.required_intelligence,
            "is_cursed": self.is_cursed,
            "read_count": self.read_count
        }


# =============================================================================
# RITUAL SPELLS - Powerful but slow
# =============================================================================

class RitualSpell(Spell):
    """Spells requiring multiple turns to cast but with powerful effects."""
    
    def __init__(self, name: str, school: str, mana_cost: int, 
                 cast_turns: int = 3, damage: int = 0, **kwargs):
        super().__init__(
            name=name, school=school, mana_cost=mana_cost,
            damage=damage, cast_time=cast_turns, **kwargs
        )
        self.ritual_progress = 0
        self.interrupted = False
        self._ritual_position = None
    
    def start_ritual(self, caster: Entity, target, engine: GameEngine) -> str:
        """Begin the ritual casting."""
        self.ritual_progress = 0
        self.interrupted = False
        self._ritual_position = (caster.x, caster.y)
        caster._casting_ritual = self
        return f"{caster.name} begins the ritual of {self.name}..."
    
    def continue_ritual(self, caster: Entity, engine: GameEngine) -> str:
        """Continue ritual on subsequent turns."""
        if self.interrupted:
            return "The ritual was interrupted!"
        
        # Check if caster moved
        if (caster.x, caster.y) != self._ritual_position:
            self.interrupt()
            return "The ritual fails as you move!"
        
        self.ritual_progress += 1
        
        # Visual feedback
        engine.messages.append(
            f"The ritual of {self.name} progresses... ({self.ritual_progress}/{self.cast_time})"
        )
        
        if self.ritual_progress >= self.cast_time:
            return self.complete_ritual(caster, engine)
        
        return ""
    
    def complete_ritual(self, caster: Entity, engine: GameEngine) -> str:
        """Complete the ritual and apply effect."""
        caster._casting_ritual = None
        self.ritual_progress = 0
        return f"The ritual of {self.name} is complete!"
    
    def interrupt(self):
        """Interrupt the ritual."""
        self.interrupted = True
        self.ritual_progress = 0


class MeteorSwarm(RitualSpell):
    """Ultimate evocation ritual - rain of meteors."""
    
    def __init__(self):
        super().__init__(
            name="Meteor Swarm",
            school=SpellSchool.EVOCATION,
            mana_cost=15,
            cast_turns=3,
            damage=50,
            aoe=4,
            range_val=8,
            cooldown=10,
            description="Calls down a swarm of meteors from the sky."
        )
    
    def complete_ritual(self, caster: Entity, engine: GameEngine) -> str:
        super().complete_ritual(caster, engine)
        
        # Find target area - all visible enemies
        targets = []
        for entity in engine.entities:
            if entity != caster and hasattr(entity, 'fighter') and entity.fighter:
                if engine.game_map.tiles[entity.y][entity.x].visible:
                    targets.append((entity.x, entity.y))
        
        if not targets:
            return "The meteors fall... but hit nothing."
        
        total_dmg = 0
        for tx, ty in targets:
            # Meteor strike at each target
            for entity in list(engine.entities):
                if not entity.fighter:
                    continue
                dist = math.sqrt((entity.x - tx)**2 + (entity.y - ty)**2)
                if dist <= self.aoe:
                    dmg = int(self.damage * (1 - dist / (self.aoe + 1)))
                    actual = entity.fighter.take_damage(max(1, dmg))
                    total_dmg += actual
                    engine.messages.append(
                        f"💥 A meteor slams into {entity.name} for {actual} damage!"
                    )
        
        return f"METEOR SWARM! {len(targets)} impacts dealing {total_dmg} total damage!"


class GrandHealing(RitualSpell):
    """Powerful healing ritual."""
    
    def __init__(self):
        super().__init__(
            name="Grand Healing",
            school=SpellSchool.TRANSMUTATION,
            mana_cost=12,
            cast_turns=2,
            healing=30,
            aoe=3,
            range_val=5,
            cooldown=8,
            description="A ritual of grand healing for all allies."
        )
    
    def complete_ritual(self, caster: Entity, engine: GameEngine) -> str:
        super().complete_ritual(caster, engine)
        
        total_heal = 0
        for entity in engine.entities:
            if not hasattr(entity, 'fighter') or not entity.fighter:
                continue
            dist = max(abs(entity.x - caster.x), abs(entity.y - caster.y))
            if dist <= self.aoe:
                heal = min(self.healing, entity.fighter.max_hp - entity.fighter.hp)
                entity.fighter.hp += heal
                total_heal += heal
                engine.messages.append(f"✨ {entity.name} is healed for {heal} HP!")
        
        return f"GRAND HEALING! Restored {total_heal} HP across the battlefield!"


# =============================================================================
# TELEPORTATION / BLINK
# =============================================================================

class TeleportSpell(Spell):
    """Instant movement spells."""
    
    def __init__(self, name: str, mana_cost: int, range_val: int = 5,
                 precision: str = "controlled", cooldown: int = 4, **kwargs):
        super().__init__(
            name=name, school=SpellSchool.TRANSMUTATION, mana_cost=mana_cost,
            range_val=range_val, cooldown=cooldown,
            description=f"{precision} teleportation.", **kwargs
        )
        self.precision = precision  # "controlled", "random", "blink", "swap"
    
    def cast(self, caster: Entity, target_pos: tuple[int, int], engine: GameEngine) -> str:
        super().cast(caster, target_pos, engine)
        
        if self.precision == "controlled":
            return self._controlled_teleport(caster, target_pos, engine)
        elif self.precision == "random":
            return self._random_teleport(caster, engine)
        elif self.precision == "blink":
            return self._blink(caster, target_pos, engine)
        elif self.precision == "swap":
            return self._swap(caster, target_pos, engine)
        
        return f"{caster.name} teleports!"
    
    def _controlled_teleport(self, caster: Entity, pos: tuple[int, int], engine: GameEngine) -> str:
        x, y = pos
        if engine.game_map.is_in_bounds(x, y) and engine.game_map.tiles[y][x].walkable:
            old_pos = (caster.x, caster.y)
            caster.x, caster.y = x, y
            return f"{caster.name} teleports from {old_pos} to {pos}!"
        return "The destination is blocked!"
    
    def _random_teleport(self, caster: Entity, engine: GameEngine) -> str:
        """Teleport to random valid location."""
        valid_tiles = []
        for y in range(engine.game_map.height):
            for x in range(engine.game_map.width):
                if engine.game_map.tiles[y][x].walkable:
                    valid_tiles.append((x, y))
        
        if valid_tiles:
            new_pos = random.choice(valid_tiles)
            caster.x, caster.y = new_pos
            return f"{caster.name} teleports to a random location!"
        return "No valid teleport destination!"
    
    def _blink(self, caster: Entity, pos: tuple[int, int], engine: GameEngine) -> str:
        """Short-range instant teleport (no line of sight needed)."""
        x, y = pos
        dx = x - caster.x
        dy = y - caster.y
        dist = max(abs(dx), abs(dy))
        
        if dist > self.range_val:
            return "Too far to blink!"
        
        if engine.game_map.is_in_bounds(x, y) and engine.game_map.tiles[y][x].walkable:
            caster.x, caster.y = x, y
            return f"{caster.name} blinks across space!"
        return "Blink failed - destination blocked!"
    
    def _swap(self, caster: Entity, target, engine: GameEngine) -> str:
        """Swap positions with target."""
        if target and hasattr(target, 'x') and hasattr(target, 'y'):
            old_cx, old_cy = caster.x, caster.y
            caster.x, caster.y = target.x, target.y
            target.x, target.y = old_cx, old_cy
            return f"{caster.name} swaps places with {target.name}!"
        return "Swap failed!"
    
    def can_target_position(self) -> bool:
        return self.precision in ["controlled", "blink"]


# =============================================================================
# CANTrips - Weak but free/cheap spells
# =============================================================================

class Cantrip(Spell):
    """Minor magical tricks that cost minimal or no mana."""
    
    def __init__(self, name: str, school: str, effect_type: str, **kwargs):
        super().__init__(
            name=name, school=school, mana_cost=0, range_val=3,
            description=f"A minor {school} cantrip.", **kwargs
        )
        self.effect_type = effect_type
        self.uses_per_turn = 1
    
    def cast(self, caster: Entity, target, engine: GameEngine) -> str:
        # Cantrips don't trigger cooldown or cost
        if self.effect_type == "light":
            return self._cast_light(caster, engine)
        elif self.effect_type == "spark":
            return self._cast_spark(caster, target, engine)
        elif self.effect_type == "mage_hand":
            return self._cast_mage_hand(caster, target, engine)
        elif self.effect_type == "prestidigitation":
            return self._cast_prestidigitation(caster, engine)
        elif self.effect_type == "message":
            return self._cast_message(caster, target, engine)
        return f"{caster.name} performs a minor magic trick."
    
    def _cast_light(self, caster: Entity, engine: GameEngine) -> str:
        """Briefly illuminate area."""
        radius = 5
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = caster.x + dx, caster.y + dy
                if engine.game_map.is_in_bounds(nx, ny):
                    engine.game_map.tiles[ny][nx].visible = True
        return f"{caster.name} conjures a brief burst of light!"
    
    def _cast_spark(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        """Tiny damage cantrip."""
        if target and hasattr(target, 'fighter') and target.fighter:
            dmg = 1
            actual = target.fighter.take_damage(dmg)
            engine.messages.append(f"A spark zaps {target.name} for {actual} damage!")
            return f"{caster.name} flicks a spark at {target.name}!"
        return "The spark fizzles."
    
    def _cast_mage_hand(self, caster: Entity, target, engine: GameEngine) -> str:
        """Manipulate object at distance."""
        if target and getattr(target, 'is_item', False):
            # Move item toward caster
            target.x = caster.x + random.choice([-1, 0, 1])
            target.y = caster.y + random.choice([-1, 0, 1])
            return f"An invisible hand pulls the {target.name} closer!"
        return "The mage hand finds nothing to grab."
    
    def _cast_prestidigitation(self, caster: Entity, engine: GameEngine) -> str:
        """Minor cosmetic effect."""
        effects = [
            "colors shift across the walls",
            "a faint melody plays",
            "the air smells of cinnamon",
            "small sparks dance around"
        ]
        return f"{caster.name} makes {random.choice(effects)}."
    
    def _cast_message(self, caster: Entity, target: Entity, engine: GameEngine) -> str:
        """Send a whispered message."""
        if target:
            return f"A whisper reaches {target.name}: '...'"
        return "The message dissipates."


# =============================================================================
# MAGIC CONSUMABLE - Enhanced
# =============================================================================

class MagicConsumable:
    """Items that cast spells when consumed/used."""
    
    def __init__(self, spell: Spell, uses: int = 1, rechargeable: bool = False):
        self.spell = spell
        self.uses = uses
        self.max_uses = uses
        self.rechargeable = rechargeable
        self.recharge_rate = 0.1  # 10% per turn if rechargeable
        self.entity = None  # Set when equipped/carried
    
    def consume(self, engine: GameEngine) -> bool:
        if self.uses <= 0:
            engine.messages.append("The item has no charges left.")
            return False
        
        consumer = self.entity.parent if self.entity and hasattr(self.entity, 'parent') else None
        if not consumer:
            engine.messages.append("No one to consume the item.")
            return False
        
        if not hasattr(consumer, 'mana_system') or not consumer.mana_system:
            engine.messages.append("You cannot use magical items.")
            return False
        
        target = self._find_target(consumer, engine)
        if target or self.spell.can_target_position():
            result = self.spell.cast(consumer, target or (consumer.x, consumer.y), engine)
            engine.messages.append(result)
            self._apply_spell_effects(consumer, target, engine)
            self.uses -= 1
            
            if self.uses <= 0 and not self.rechargeable:
                engine.messages.append(f"The {self.entity.name} crumbles to dust.")
                # Remove from inventory
                if hasattr(consumer, 'inventory') and self.entity in consumer.inventory.items:
                    consumer.inventory.remove(self.entity)
            
            return True
        
        engine.messages.append("No valid target for spell.")
        return False
    
    def _find_target(self, caster, engine: GameEngine):
        """Find closest visible enemy."""
        closest = None
        min_dist = float('inf')
        
        for entity in engine.entities:
            if entity == caster:
                continue
            if not hasattr(entity, 'fighter') or not entity.fighter:
                continue
            if not engine.game_map.tiles[entity.y][entity.x].visible:
                continue
            
            dist = max(abs(entity.x - caster.x), abs(entity.y - caster.y))
            if dist < min_dist and dist <= self.spell.range_val:
                min_dist = dist
                closest = entity
        
        return closest
    
    def _apply_spell_effects(self, caster, target, engine: GameEngine):
        MagicConsumable.apply_spell_effects(caster, target, self.spell, engine)
    
    def recharge(self):
        """Recharge a rechargeable item."""
        if self.rechargeable and self.uses < self.max_uses:
            if random.random() < self.recharge_rate:
                self.uses += 1
    
    @staticmethod
    def apply_spell_effects(caster, target, spell: Spell, engine: GameEngine) -> None:
        from dungeon.entities.status_effects import BurnEffect, FreezeEffect, PoisonEffect, StunEffect
        
        if spell.damage > 0 and target is not None and hasattr(target, 'fighter') and target.fighter:
            actual_damage = max(1, spell.get_effective_damage() - target.fighter.defense)
            target.fighter.hp -= actual_damage
            engine.messages.append(f"{target.name} takes {actual_damage} {spell.school} damage!")
            
            if spell.effect == "burn":
                msg = target.fighter.status_effects.apply_effect(BurnEffect(3, 3), engine)
                if msg:
                    engine.messages.append(msg)
            elif spell.effect == "freeze":
                msg = target.fighter.status_effects.apply_effect(FreezeEffect(2, 0), engine)
                if msg:
                    engine.messages.append(msg)
            elif spell.effect == "poison":
                msg = target.fighter.status_effects.apply_effect(PoisonEffect(4, 2), engine)
                if msg:
                    engine.messages.append(msg)
            elif spell.effect == "shock":
                msg = target.fighter.status_effects.apply_effect(StunEffect(1, 0), engine)
                if msg:
                    engine.messages.append(msg)
            
            if target.fighter.hp <= 0:
                if hasattr(engine, '_on_enemy_killed'):
                    engine._on_enemy_killed(target)
                if target in engine.entities:
                    engine.entities.remove(target)
        
        if spell.healing > 0 and caster and hasattr(caster, 'fighter') and caster.fighter:
            heal = min(spell.get_effective_healing(), caster.fighter.max_hp - caster.fighter.hp)
            caster.fighter.hp += heal
            engine.messages.append(f"{caster.name} heals for {heal} HP!")


# =============================================================================
# WAND / STAFF SYSTEM
# =============================================================================

class Wand:
    """Reusable magic item with limited charges."""
    
    def __init__(self, spell: Spell, charges: int = 5, max_charges: int = 5):
        self.spell = spell
        self.charges = charges
        self.max_charges = max_charges
        self.identified = False
        self.cursed = False
        self.entity = None
    
    def zap(self, caster: Entity, target, engine: GameEngine) -> str:
        """Use the wand to cast its spell."""
        if self.charges <= 0:
            return f"The wand is out of charges!"
        
        if self.cursed and random.random() < 0.3:
            # Backfire
            caster.fighter.take_damage(5)
            self.charges -= 1
            return "The cursed wand backfires!"
        
        result = self.spell.cast(caster, target, engine)
        self.charges -= 1
        
        if not self.identified:
            self.identified = True
            result += f" (It was a Wand of {self.spell.name}!)"
        
        return result
    
    def recharge(self, amount: int = 1) -> int:
        """Recharge the wand. Returns actual amount recharged."""
        old = self.charges
        self.charges = min(self.max_charges, self.charges + amount)
        return self.charges - old


class Staff(Wand):
    """More powerful magic item, can hold multiple spells."""
    
    def __init__(self, name: str = "Staff"):
        super().__init__(None, charges=10, max_charges=10)
        self.name = name
        self.spells: list[Spell] = []
        self.active_spell_index = 0
        self.melee_damage_bonus = 2
    
    def add_spell(self, spell: Spell):
        self.spells.append(spell)
        if len(self.spells) == 1:
            self.spell = spell
    
    def set_active_spell(self, index: int) -> bool:
        if 0 <= index < len(self.spells):
            self.active_spell_index = index
            self.spell = self.spells[index]
            return True
        return False
    
    def zap(self, caster: Entity, target, engine: GameEngine) -> str:
        if not self.spells:
            return "The staff has no spells imbued."
        return super().zap(caster, target, engine)


# =============================================================================
# SPELL FACTORY - Pre-built spells
# =============================================================================

class SpellFactory:
    """Factory for creating common spells."""
    
    @staticmethod
    def fireball() -> EvocationSpell:
        return EvocationSpell(
            name="Fireball", mana_cost=5, damage=12, element="fire",
            range_val=6, aoe=2, cooldown=3,
            description="A ball of fire that explodes on impact."
        )
    
    @staticmethod
    def ice_bolt() -> EvocationSpell:
        return EvocationSpell(
            name="Ice Bolt", mana_cost=3, damage=8, element="ice",
            range_val=5, cooldown=1,
            description="A freezing bolt of ice."
        )
    
    @staticmethod
    def lightning_chain() -> EvocationSpell:
        spell = EvocationSpell(
            name="Chain Lightning", mana_cost=6, damage=10, element="lightning",
            range_val=5, cooldown=4,
            description="Lightning that arcs between enemies."
        )
        spell.chain_hits = 3
        spell.chain_range = 3
        return spell
    
    @staticmethod
    def magic_missile() -> EvocationSpell:
        return EvocationSpell(
            name="Magic Missile", mana_cost=2, damage=4, element="arcane",
            range_val=7, cooldown=0,
            description="Unerring bolts of magical force."
        )
    
    @staticmethod
    def heal() -> Spell:
        return Spell(
            name="Heal", school=SpellSchool.TRANSMUTATION, mana_cost=4,
            healing=15, range_val=4, cooldown=2,
            description="Restores health to a target."
        )
    
    @staticmethod
    def haste() -> ChronomancySpell:
        return ChronomancySpell(
            name="Haste", mana_cost=4, time_effect="haste",
            duration=5, range_val=5, cooldown=4
        )
    
    @staticmethod
    def slow() -> ChronomancySpell:
        return ChronomancySpell(
            name="Slow", mana_cost=3, time_effect="slow",
            duration=4, range_val=5, cooldown=3
        )
    
    @staticmethod
    def time_stop() -> ChronomancySpell:
        return ChronomancySpell(
            name="Time Stop", mana_cost=8, time_effect="stop",
            duration=2, range_val=6, cooldown=8
        )
    
    @staticmethod
    def mind_blast() -> MentomancySpell:
        return MentomancySpell(
            name="Mind Blast", mana_cost=4, mind_effect="psychic_blast",
            psychic_damage=10, range_val=5, cooldown=2
        )
    
    @staticmethod
    def fear() -> MentomancySpell:
        return MentomancySpell(
            name="Fear", mana_cost=3, mind_effect="fear",
            duration=3, range_val=4, cooldown=3
        )
    
    @staticmethod
    def charm() -> MentomancySpell:
        return MentomancySpell(
            name="Charm", mana_cost=5, mind_effect="charm",
            duration=4, range_val=4, cooldown=5
        )
    
    @staticmethod
    def summon_skeleton() -> ConjurationSpell:
        return ConjurationSpell(
            name="Summon Skeleton", mana_cost=4, summon_type="Skeleton",
            summon_count=1, duration=15, range_val=3, cooldown=5,
            summon_hp=15, summon_damage=4
        )
    
    @staticmethod
    def magic_armor() -> AbjurationSpell:
        return AbjurationSpell(
            name="Magic Armor", mana_cost=3, shield_type="magic_armor",
            potency=5, duration=10, range_val=0, cooldown=3
        )
    
    @staticmethod
    def dispel() -> AbjurationSpell:
        return AbjurationSpell(
            name="Dispel Magic", mana_cost=4, shield_type="dispel",
            range_val=5, cooldown=2
        )
    
    @staticmethod
    def life_drain() -> NecromancySpell:
        return NecromancySpell(
            name="Life Drain", mana_cost=4, necromancy_type="drain",
            damage=8, healing=0, range_val=4, cooldown=3
        )
    
    @staticmethod
    def raise_dead() -> NecromancySpell:
        return NecromancySpell(
            name="Raise Dead", mana_cost=6, necromancy_type="raise",
            range_val=3, cooldown=6
        )
    
    @staticmethod
    def reveal_map() -> DivinationSpell:
        return DivinationSpell(
            name="Reveal Map", mana_cost=5, divination_type="map",
            range_val=0
        )
    
    @staticmethod
    def invisibility() -> IllusionSpell:
        return IllusionSpell(
            name="Invisibility", mana_cost=4, illusion_type="invisibility",
            duration=8, range_val=0
        )
    
    @staticmethod
    def blink() -> TeleportSpell:
        return TeleportSpell(
            name="Blink", mana_cost=3, range_val=4,
            precision="blink", cooldown=3
        )
    
    @staticmethod
    def stone_to_mud() -> TransmutationSpell:
        return TransmutationSpell(
            name="Stone to Mud", mana_cost=3, target_type="wall",
            result_char="~", result_color=(139, 90, 43), result_name="mud",
            range_val=5
        )
    
    @staticmethod
    def all_spells() -> list[Spell]:
        """Get all factory spells."""
        return [
            SpellFactory.fireball(),
            SpellFactory.ice_bolt(),
            SpellFactory.lightning_chain(),
            SpellFactory.magic_missile(),
            SpellFactory.heal(),
            SpellFactory.haste(),
            SpellFactory.slow(),
            SpellFactory.time_stop(),
            SpellFactory.mind_blast(),
            SpellFactory.fear(),
            SpellFactory.charm(),
            SpellFactory.summon_skeleton(),
            SpellFactory.magic_armor(),
            SpellFactory.dispel(),
            SpellFactory.life_drain(),
            SpellFactory.raise_dead(),
            SpellFactory.reveal_map(),
            SpellFactory.invisibility(),
            SpellFactory.blink(),
            SpellFactory.stone_to_mud(),
        ]
