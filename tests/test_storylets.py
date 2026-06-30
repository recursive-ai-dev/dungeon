import pytest
from storylets import Storylet, StoryletEffect, StoryletEffectType, StoryletSystem
from entities.components import Fighter
from entities import Entity
from unittest.mock import MagicMock
import time

def test_storylet_availability_and_cooldown():
    engine = MagicMock()
    engine.dungeon_level = 1
    engine.player = MagicMock()
    engine.player.fighter = MagicMock()
    engine.player.fighter.hp = 100
    engine.player.fighter.status_effects = MagicMock()
    engine.player.fighter.status_effects.delayed_branching_stats = {}
    engine.player.inventory = MagicMock()
    engine.player.inventory.items = []

    s = Storylet(
        title="Test Storylet",
        text="A test.",
        cooldown_seconds=10.0,
        max_triggers=2,
        once_only=False
    )

    s.last_triggered = -20.0
    assert s.is_available(engine, current_time=0.0)

    # Trigger it, which sets last_triggered to time.time()
    s.trigger(engine)

    now = time.time()

    # It should not be available 5 seconds after now
    assert not s.is_available(engine, current_time=now + 5.0)

    # It should be available 15 seconds after now
    assert s.is_available(engine, current_time=now + 15.0)

    # Set to a fake high time to force the second trigger
    s.last_triggered = now - 20.0
    s.trigger(engine)

    # Should be out of charges (max_triggers = 2)
    assert not s.is_available(engine, current_time=now + 50.0)

def test_storylet_triggers_after_dependency():
    engine = MagicMock()
    engine.dungeon_level = 1
    engine.player = MagicMock()
    engine.player.fighter = MagicMock()
    engine.player.fighter.hp = 100
    engine.player.fighter.status_effects = MagicMock()
    engine.player.fighter.status_effects.delayed_branching_stats = {}
    engine.player.inventory = MagicMock()
    engine.player.inventory.items = []

    system = StoryletSystem(save_system=MagicMock())

    import storylets
    old_system = storylets.storylet_system
    storylets.storylet_system = system

    pre = Storylet(title="Pre", text="Pre", storylet_id="pre", once_only=False)
    pre.last_triggered = -100
    system.add_storylet(pre)

    dep = Storylet(title="Dep", text="Dep", storylet_id="dep", triggers_after="pre", once_only=False)
    dep.last_triggered = -100
    system.add_storylet(dep)

    assert not dep.is_available(engine, current_time=time.time())

    system.trigger_storylet("pre", engine)

    assert dep.is_available(engine, current_time=time.time())

    storylets.storylet_system = old_system

def test_trigger_storylet_effect():
    engine = MagicMock()
    engine.dungeon_level = 1
    engine.player = MagicMock()
    engine.player.fighter = MagicMock()
    engine.player.fighter.hp = 100
    engine.player.fighter.status_effects = MagicMock()
    engine.player.fighter.status_effects.delayed_branching_stats = {}
    engine.player.inventory = MagicMock()
    engine.player.inventory.items = []

    system = StoryletSystem(save_system=MagicMock())

    import storylets
    old_system = storylets.storylet_system
    storylets.storylet_system = system

    target = Storylet(title="Target", text="Target", storylet_id="target", once_only=False)
    target.last_triggered = 1000000000.0 # High cooldown so it can't trigger naturally
    system.add_storylet(target)

    origin = Storylet(
        title="Origin",
        text="Origin",
        effects=[StoryletEffect(effect_type=StoryletEffectType.TRIGGER_STORYLET, target_storylet_id="target")],
        once_only=False
    )
    origin.last_triggered = -100
    system.add_storylet(origin)

    # triggering origin should apply TRIGGER_STORYLET which calls _queue_chain_trigger, which sets target.last_triggered = 0
    system.trigger_storylet("origin", engine)

    assert target.last_triggered == 0

    storylets.storylet_system = old_system
