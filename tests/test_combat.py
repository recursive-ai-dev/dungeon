import pytest
from entities.components import Fighter
from entities import Entity
import random
from entities.ai import HostileAI
from unittest.mock import MagicMock

def test_fighter_defense_power():
    entity = Entity(x=0, y=0, char='@', color='#FFF', name='Test')
    fighter = Fighter(hp=10, defense=5, power=5, xp=0)
    fighter.entity = entity

    # Test base stats
    assert fighter.defense == 5
    assert fighter.power == 5

    # Test ascension tier bonuses
    fighter.ascension_tier = 5
    assert fighter.power == 6  # Tier 5 gives +1 power
    assert fighter.defense == 5

    fighter.ascension_tier = 10
    assert fighter.power == 6
    assert fighter.defense == 7  # Tier 10 gives +2 defense

def test_fighter_hp_bounds():
    entity = Entity(x=0, y=0, char='@', color='#FFF', name='Test')
    fighter = Fighter(hp=10, defense=5, power=5, xp=0)
    fighter.entity = entity

    assert fighter.hp == 10

    # Test taking damage
    fighter.hp -= 5
    assert fighter.hp == 5

    # Test over-healing
    fighter.hp += 10
    assert fighter.hp == 10  # Max HP is 10

    # Test dying
    fighter.hp -= 15
    assert fighter.hp == 0  # Min HP is 0


def test_hostile_ai_attack():
    attacker = Entity(x=0, y=0, char='O', color='#FFF', name='Orc')
    attacker.fighter = Fighter(hp=10, defense=0, power=5, xp=0)
    attacker.fighter.entity = attacker
    attacker.ai = HostileAI()
    attacker.ai.entity = attacker

    target = Entity(x=1, y=0, char='@', color='#FFF', name='Player')
    target.fighter = Fighter(hp=10, defense=2, power=2, xp=0)
    target.fighter.entity = target

    # We mock GameEngine as it crashes on small sizes during initialization
    engine = MagicMock()
    engine.messages = []

    # Simulate attack (power 5 - defense 2 = 3 damage)
    attacker.ai._attack(target, engine)

    assert target.fighter.hp == 7

def test_hostile_ai_zero_damage():
    attacker = Entity(x=0, y=0, char='g', color='#FFF', name='Goblin')
    attacker.fighter = Fighter(hp=10, defense=0, power=2, xp=0)
    attacker.fighter.entity = attacker
    attacker.ai = HostileAI()
    attacker.ai.entity = attacker

    target = Entity(x=1, y=0, char='@', color='#FFF', name='Player')
    target.fighter = Fighter(hp=10, defense=5, power=2, xp=0)
    target.fighter.entity = target

    # We mock GameEngine
    engine = MagicMock()
    engine.messages = []

    # Simulate attack (power 2 - defense 5 <= 0 damage)
    attacker.ai._attack(target, engine)

    assert target.fighter.hp == 10
