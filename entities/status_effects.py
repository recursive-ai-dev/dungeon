# Standard library imports
from __future__ import annotations

from typing import TYPE_CHECKING

# Third-party imports
# (none)

# Local imports
if TYPE_CHECKING:
    from dungeon.engine import GameEngine


class StatusEffect:
    def __init__(self, name: str, duration: int, power: int):
        self.name = name
        self.duration = duration
        self.power = power
    
    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"{target.entity.name} is now {self.name}."
    
    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        self.duration -= 1
        return ""
    
    def on_remove(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"{target.entity.name} is no longer {self.name}."
    
    def to_dict(self):
        return {"name": self.name, "duration": self.duration, "power": self.power}
    
    @classmethod
    def from_dict(cls, data):
        name = data.get("name", "")
        duration = data.get("duration", 0)
        power = data.get("power", 0)
        if name == "burning":
            return BurnEffect(duration, power)
        elif name == "poisoned":
            return PoisonEffect(duration, power)
        elif name == "frozen":
            return FreezeEffect(duration, power)
        elif name == "wet":
            return WetEffect(duration, power)
        elif name == "stunned":
            return StunEffect(duration, power)
        elif name == "regeneration":
            return RegenEffect(duration, power)
        elif name == "hasted":
            return HasteEffect(duration, power)
        elif name == "slowed":
            return SlowEffect(duration, power)
        elif name == "decaying":
            return DecayEffect(duration, power)
        elif name == "fearful":
            return FearEffect(duration, power)
        elif name == "charmed":
            return CharmEffect(duration, power)
        elif name == "confused":
            return ConfusionEffect(duration, power)
        elif name == "barriered":
            return BarrierEffect(duration, power)
        elif name == "reflecting":
            return ReflectEffect(duration, power)
        elif name == "absorbing":
            return AbsorbEffect(duration, power)
        elif name == "magic_armored":
            return MagicArmorEffect(duration, power)
        elif name == "cursed":
            return CurseEffect(duration, power)
        return cls(name, duration, power)


class BurnEffect(StatusEffect):
    def __init__(self, duration: int = 3, power: int = 5):
        super().__init__("burning", duration, power)
    
    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"🔥 {target.entity.name} bursts into flames! ({self.power} dmg/turn)"
    
    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        target.hp -= self.power
        return f"🔥 {target.entity.name} takes {self.power} fire damage."


class PoisonEffect(StatusEffect):
    def __init__(self, duration: int = 4, power: int = 3):
        super().__init__("poisoned", duration, power)
    
    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"☠ {target.entity.name} is poisoned! ({self.power} dmg/turn)"
    
    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        target.hp -= self.power
        return f"☠ {target.entity.name} takes {self.power} poison damage."


class FreezeEffect(StatusEffect):
    def __init__(self, duration: int = 2, power: int = 0):
        super().__init__("frozen", duration, power)
    
    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"❄ {target.entity.name} is frozen solid! Can't act."
    
    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        return f"❄ {target.entity.name} is frozen and cannot move."


class WetEffect(StatusEffect):
    def __init__(self, duration: int = 3, power: int = 0):
        super().__init__("wet", duration, power)
    
    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"💧 {target.entity.name} is soaked! Vulnerable to lightning."
    
    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        return ""


class StunEffect(StatusEffect):
    def __init__(self, duration: int = 1, power: int = 0):
        super().__init__("stunned", duration, power)
    
    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"⚡ {target.entity.name} is stunned! Can't act."
    
    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        return f"⚡ {target.entity.name} is stunned and cannot act."


class RegenEffect(StatusEffect):
    def __init__(self, duration: int = 3, power: int = 5):
        super().__init__("regeneration", duration, power)

    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"✨ {target.entity.name} begins regenerating! (+{self.power} HP/turn)"

    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        heal = min(self.power, target.max_hp - target.hp)
        target.hp += heal
        if heal > 0:
            return f"✨ {target.entity.name} regenerates {heal} HP."
        return ""


class HasteEffect(StatusEffect):
    def __init__(self, duration: int = 3, power: int = 1):
        super().__init__("hasted", duration, power)

    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"⚡ {target.entity.name} moves with supernatural speed!"

    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        return f"⚡ {target.entity.name} acts at double speed!"


class SlowEffect(StatusEffect):
    def __init__(self, duration: int = 3, power: int = 1):
        super().__init__("slowed", duration, power)

    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"🐌 {target.entity.name} moves sluggishly!"

    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        return f"🐌 {target.entity.name} struggles to act!"


class DecayEffect(StatusEffect):
    def __init__(self, duration: int = 3, power: int = 3):
        super().__init__("decaying", duration, power)

    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"💀 {target.entity.name} withers away! ({self.power} dmg/turn)"

    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        target.hp -= self.power
        return f"💀 {target.entity.name} takes {self.power} decay damage."


class FearEffect(StatusEffect):
    def __init__(self, duration: int = 3, power: int = 2):
        super().__init__("fearful", duration, power)

    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"😱 {target.entity.name} is overcome with terror!"

    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        return f"😱 {target.entity.name} cowers in fear!"


class CharmEffect(StatusEffect):
    def __init__(self, duration: int = 3, power: int = 0, charmer=None):
        super().__init__("charmed", duration, power)
        self.charmer = charmer

    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"💖 {target.entity.name} looks at you with adoration!"

    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        return f"💖 {target.entity.name} is entranced!"


class ConfusionEffect(StatusEffect):
    def __init__(self, duration: int = 3, power: int = 1):
        super().__init__("confused", duration, power)

    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"🌀 {target.entity.name}'s mind is clouded!"

    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        return f"🌀 {target.entity.name} acts erratically!"


class BarrierEffect(StatusEffect):
    def __init__(self, duration: int = 3, power: int = 10):
        super().__init__("barriered", duration, power)
        self.absorbed = 0

    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"🛡️ A shimmering barrier surrounds {target.entity.name}!"

    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        return f"🛡️ The barrier holds strong!"


class ReflectEffect(StatusEffect):
    def __init__(self, duration: int = 3, power: int = 5):
        super().__init__("reflecting", duration, power)

    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"🪞 {target.entity.name} is surrounded by reflective energy!"

    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        return f"🪞 {target.entity.name}'s shield glimmers!"


class AbsorbEffect(StatusEffect):
    def __init__(self, duration: int = 3, power: int = 10):
        super().__init__("absorbing", duration, power)
        self.absorbed = 0

    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"🔮 {target.entity.name} is wrapped in absorbing energies!"

    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        return f"🔮 {target.entity.name} pulses with absorbed power!"


class MagicArmorEffect(StatusEffect):
    def __init__(self, duration: int = 3, power: int = 5):
        super().__init__("magic_armored", duration, power)

    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"✨ Arcane armor materializes around {target.entity.name}!"

    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        return f"✨ The magical armor hums with power!"


class CurseEffect(StatusEffect):
    def __init__(self, duration: int = 5, power: int = 3):
        super().__init__("cursed", duration, power)

    def on_apply(self, target: "Fighter", engine: "GameEngine") -> str:
        return f"👁️ {target.entity.name} is cursed!"

    def on_turn_end(self, target: "Fighter", engine: "GameEngine") -> str:
        super().on_turn_end(target, engine)
        target.hp -= self.power
        return f"👁️ {target.entity.name} takes {self.power} curse damage."



class StatusEffectManager:
    def __init__(self):
        self.effects: list[StatusEffect] = []
        self.delayed_branching_stats = {"brutality": 0, "finesse": 0}
    
    def add_effect(self, effect: StatusEffect, target: "Fighter", engine: "GameEngine") -> str:
        # Check for elemental synergies (Linear Logic / Defeasible Logic)
        for existing in self.effects:
            if existing.name == "burning" and effect.name == "wet":
                self.effects.remove(existing)
                return "The fire is hissed out by the dampness, leaving only thick steam."
            if existing.name == "wet" and effect.name == "burning":
                self.effects.remove(existing)
                return "Your flames are smothered by the moisture before they can catch."
            if existing.name == "wet" and effect.name == "frozen":
                effect.duration += 2  # Frozen lasts longer if wet
                break
            if existing.name == "burning" and effect.name == "frozen":
                self.effects.remove(existing)
                return "The ice melts instantly against your heat."

        for existing in self.effects:
            if existing.name == effect.name:
                existing.duration = max(existing.duration, effect.duration)
                existing.power = max(existing.power, effect.power)
                return f"The {effect.name} is renewed."
        
        self.effects.append(effect)
        return effect.on_apply(target, engine)
    
    def remove_expired(self, target: "Fighter", engine: "GameEngine") -> list[str]:
        expired = []
        remaining = []
        for effect in self.effects:
            if effect.duration <= 0:
                expired.append(effect.on_remove(target, engine))
            else:
                remaining.append(effect)
        self.effects = remaining
        return expired
    
    def process_turn_end(self, target: "Fighter", engine: "GameEngine") -> list[str]:
        messages = []
        for effect in self.effects:
            msg = effect.on_turn_end(target, engine)
            if msg:
                messages.append(msg)
        return messages
    
    def can_act(self) -> bool:
        for effect in self.effects:
            if isinstance(effect, (FreezeEffect, StunEffect)):
                return False
        return True
    
    def is_vulnerable_to(self, effect_type: str) -> bool:
        for effect in self.effects:
            if effect_type == "fire" and isinstance(effect, WetEffect):
                return False
        return True
    
    def can_apply_effect(self, effect_type: str) -> tuple[bool, str]:
        """
        Defeasible logic for effect application.
        Returns (can_apply, reason). Precedence: RF > RL > RD
        """
        if effect_type == "burn":
            for effect in self.effects:
                if isinstance(effect, WetEffect):
                    return False, "The wetness prevents the burn from taking hold!"
            return True, ""
        elif effect_type == "freeze":
            for effect in self.effects:
                if isinstance(effect, RegenEffect):
                    return False, "The regenerative energy prevents freezing!"
            return True, ""
        elif effect_type == "poison":
            if any(isinstance(e, PoisonEffect) for e in self.effects):
                return False, "Already poisoned!"
            return True, ""
        return True, ""
    
    def apply_effect(self, effect: StatusEffect, engine: "GameEngine") -> str:
        """Apply effect with defeasible logic checks."""
        effect_name = effect.name
        target = self.entity.fighter
        
        if effect_name == "burning":
            can_apply, reason = self.can_apply_effect("burn")
            if not can_apply:
                return reason
            return self.add_effect(effect, target, engine)
        
        elif effect_name == "frozen":
            can_apply, reason = self.can_apply_effect("freeze")
            if not can_apply:
                return reason
            return self.add_effect(effect, target, engine)
        
        elif effect_name == "poisoned":
            can_apply, reason = self.can_apply_effect("poison")
            if not can_apply:
                return reason
            return self.add_effect(effect, target, engine)
        
        else:
            return self.add_effect(effect, target, engine)
    
    def to_dict(self):
        return {
            "effects": [e.to_dict() for e in self.effects],
            "delayed_branching": self.delayed_branching_stats
        }
    
    @classmethod
    def from_dict(cls, data):
        manager = cls()
        if data:
            manager.delayed_branching_stats = data.get("delayed_branching", {"brutality": 0, "finesse": 0})
            for e_data in data.get("effects", []):
                manager.effects.append(StatusEffect.from_dict(e_data))
        return manager
