import pytest
from entities.components import Fighter, Level
from entities import Entity
from entities.ai import BaseAI
from entities.ai import ActionResult
from unittest.mock import MagicMock

def test_level_xp_math():
    level = Level(level_up_base=200, level_up_factor=150, xp_given=0)

    # Base level 1 requires 200 + (1*150) = 350 xp
    assert level.experience_to_next_level == 350
    assert not level.requires_level_up

    # Adding some XP shouldn't level up immediately
    assert not level.add_xp(100)
    assert level.current_xp == 100
    assert not level.requires_level_up

    # Adding XP to cross the threshold
    assert level.add_xp(300) # Total 400
    assert level.requires_level_up

    # Process level up
    level.increase_level()
    assert level.current_level == 2
    assert level.current_xp == 50 # 400 - 350

    # Level 2 requires 200 + (2*150) = 500 xp
    assert level.experience_to_next_level == 500


def test_base_ai_not_implemented():
    class DummyAI(BaseAI):
        pass

    ai = DummyAI()
    engine = MagicMock()
    with pytest.raises(NotImplementedError):
        ai.perform(engine)
