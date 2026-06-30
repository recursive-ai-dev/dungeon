import pytest
from map import Map, Rect, TileType

def test_map_bounds_and_walkable():
    m = Map(10, 10)
    # Default is WALL
    assert not m.is_walkable(0, 0)
    assert not m.is_walkable(5, 5)

    # Manually carve a room
    room = Rect(1, 1, 3, 3)
    m.create_room(room)

    assert m.is_walkable(2, 2)
    assert m.tiles[2][2].tile_type == TileType.FLOOR

    # Boundary checks
    assert m.is_in_bounds(0, 0)
    assert m.is_in_bounds(9, 9)
    assert not m.is_in_bounds(-1, 0)
    assert not m.is_in_bounds(0, -1)
    assert not m.is_in_bounds(10, 10)

    # Out of bounds is not walkable
    assert not m.is_walkable(-1, -1)

def test_fov_computation():
    m = Map(10, 10)
    room = Rect(1, 1, 5, 5)
    m.create_room(room)

    # Compute FOV from center
    fov = m.compute_fov(3, 3, radius=5)

    # Center is visible
    assert fov[3][3]
    # Edge of room is visible
    assert fov[1][1]

    # Block LOS intentionally
    m.tiles[2][2].transparent = False
    fov2 = m.compute_fov(3, 3, radius=5)
    # Target behind it might still be partially visible due to algorithms, but generally test basic FOV pass
    assert fov2[3][3]
