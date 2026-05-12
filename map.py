# Standard library imports
import random
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Tuple, Optional, Set, Dict, Iterator
from collections import deque

# Third-party imports
# (none)

# Local imports
# (none)


class TileType(Enum):
    """Enumeration of all possible tile types in the dungeon."""
    WALL = auto()
    FLOOR = auto()
    DOOR = auto()
    STAIRS_UP = auto()
    STAIRS_DOWN = auto()
    TRAP = auto()
    WATER = auto()
    LAVA = auto()
    GRASS = auto()
    BRIDGE = auto()


@dataclass
class Tile:
    """
    Represents a single tile on the dungeon map.
    
    Attributes:
        tile_type: The type of terrain this tile represents.
        walkable: Whether entities can walk on this tile.
        transparent: Whether light/vision passes through this tile.
        char: ASCII character used to render this tile.
        color: Hex color string for rendering.
        visible: Whether the player can currently see this tile.
        explored: Whether the player has ever seen this tile.
        blocked: Whether the tile blocks movement (dynamic, e.g., closed door).
        block_sight: Whether the tile blocks sight (dynamic).
        trap_damage: Damage dealt by trap tiles (0 if not a trap).
        description: Flavor text for the tile.
    """
    tile_type: TileType
    walkable: bool
    transparent: bool
    char: str
    color: str
    visible: bool = False
    explored: bool = False
    blocked: bool = False
    block_sight: bool = False
    trap_damage: int = 0
    description: str = ""

    def __post_init__(self):
        """Ensure blocked state is consistent with tile properties."""
        if not self.walkable:
            self.blocked = True
        if not self.transparent:
            self.block_sight = True


class Rect:
    """Axis-aligned rectangle representing a room or region on the map."""
    
    def __init__(self, x: int, y: int, w: int, h: int):
        self.x1 = x
        self.y1 = y
        self.x2 = x + w
        self.y2 = y + h
        self.width = w
        self.height = h

    @property
    def center(self) -> Tuple[int, int]:
        """Return the center coordinates of the rectangle."""
        center_x = int((self.x1 + self.x2) / 2)
        center_y = int((self.y1 + self.y2) / 2)
        return center_x, center_y

    @property
    def area(self) -> int:
        """Return the area of the rectangle in tiles."""
        return self.width * self.height

    @property
    def inner(self) -> Iterator[Tuple[int, int]]:
        """Yield all coordinates inside the rectangle (excluding walls)."""
        for y in range(self.y1 + 1, self.y2):
            for x in range(self.x1 + 1, self.x2):
                yield x, y

    @property
    def perimeter(self) -> Iterator[Tuple[int, int]]:
        """Yield all coordinates on the perimeter of the rectangle."""
        for x in range(self.x1, self.x2 + 1):
            yield x, self.y1
            yield x, self.y2
        for y in range(self.y1 + 1, self.y2):
            yield self.x1, y
            yield self.x2, y

    @property
    def corners(self) -> List[Tuple[int, int]]:
        """Return the four corner coordinates."""
        return [
            (self.x1, self.y1),
            (self.x2, self.y1),
            (self.x1, self.y2),
            (self.x2, self.y2)
        ]

    def intersect(self, other: 'Rect', padding: int = 0) -> bool:
        """
        Check if this rectangle intersects with another.
        
        Args:
            other: The other rectangle to check against.
            padding: Extra space to require between rectangles.
        
        Returns:
            True if the rectangles overlap (considering padding).
        """
        return (self.x1 - padding <= other.x2 and
                self.x2 + padding >= other.x1 and
                self.y1 - padding <= other.y2 and
                self.y2 + padding >= other.y1)

    def contains(self, x: int, y: int) -> bool:
        """Check if a point is inside this rectangle."""
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def distance_to(self, other: 'Rect') -> float:
        """Calculate the minimum distance between two rectangle centers."""
        cx1, cy1 = self.center
        cx2, cy2 = other.center
        return math.sqrt((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2)

    def __repr__(self):
        return f"Rect({self.x1},{self.y1} -> {self.x2},{self.y2}, {self.width}x{self.height})"


class RoomFeature(Enum):
    """Special features that can be added to rooms."""
    NONE = auto()
    PILLARS = auto()
    ALTAR = auto()
    FOUNTAIN = auto()
    PIT = auto()
    TREASURE = auto()
    TRAP = auto()
    WATER_POOL = auto()


@dataclass
class Room:
    """A room in the dungeon with additional metadata."""
    rect: Rect
    feature: RoomFeature = RoomFeature.NONE
    connections: List[Tuple[int, int]] = field(default_factory=list)
    is_special: bool = False
    difficulty: int = 1


class Map:
    """
    A complete dungeon map with procedural generation, pathfinding,
    field of view, and various terrain features.
    """

    # Tile factory presets
    TILE_PRESETS: Dict[TileType, dict] = {
        TileType.WALL: {
            "walkable": False, "transparent": False,
            "char": "█", "color": "#444444",
            "description": "A solid stone wall."
        },
        TileType.FLOOR: {
            "walkable": True, "transparent": True,
            "char": "·", "color": "#888888",
            "description": "A dusty stone floor."
        },
        TileType.DOOR: {
            "walkable": True, "transparent": False,
            "char": "+", "color": "#8B4513",
            "description": "A wooden door."
        },
        TileType.STAIRS_UP: {
            "walkable": True, "transparent": True,
            "char": "<", "color": "#FFFFFF",
            "description": "Stairs leading up."
        },
        TileType.STAIRS_DOWN: {
            "walkable": True, "transparent": True,
            "char": ">", "color": "#FFFFFF",
            "description": "Stairs leading deeper into the dungeon."
        },
        TileType.TRAP: {
            "walkable": True, "transparent": True,
            "char": "·", "color": "#888888",
            "trap_damage": 10,
            "description": "A hidden trap!"
        },
        TileType.WATER: {
            "walkable": False, "transparent": True,
            "char": "~", "color": "#0066CC",
            "description": "Deep water."
        },
        TileType.LAVA: {
            "walkable": False, "transparent": True,
            "char": "~", "color": "#FF4500",
            "description": "Molten lava!"
        },
        TileType.GRASS: {
            "walkable": True, "transparent": True,
            "char": "\"", "color": "#228B22",
            "description": "Overgrown moss and grass."
        },
        TileType.BRIDGE: {
            "walkable": True, "transparent": True,
            "char": "=", "color": "#8B6914",
            "description": "A rickety wooden bridge."
        },
    }

    def __init__(self, width: int, height: int, dungeon_level: int = 1):
        """
        Initialize a new dungeon map.
        
        Args:
            width: Map width in tiles.
            height: Map height in tiles.
            dungeon_level: Current dungeon depth (affects difficulty).
        """
        self.width = width
        self.height = height
        self.dungeon_level = dungeon_level
        self.tiles: List[List[Tile]] = [
            [self._create_tile(TileType.WALL) for _ in range(width)]
            for _ in range(height)
        ]
        self.rooms: List[Room] = []
        self.stairs_up: Optional[Tuple[int, int]] = None
        self.stairs_down: Optional[Tuple[int, int]] = None
        self._fov_map: Optional[List[List[bool]]] = None
        self._pathfinding_cache: Dict[Tuple[int, int], Dict[Tuple[int, int], int]] = {}

    def _create_tile(self, tile_type: TileType, **overrides) -> Tile:
        """Create a tile from a preset with optional overrides."""
        preset = self.TILE_PRESETS.get(tile_type, self.TILE_PRESETS[TileType.WALL]).copy()
        preset.update(overrides)
        return Tile(tile_type=tile_type, **preset)

    def _wall_tile(self) -> Tile:
        """Create a standard wall tile."""
        return self._create_tile(TileType.WALL)

    def _floor_tile(self) -> Tile:
        """Create a standard floor tile."""
        return self._create_tile(TileType.FLOOR)

    def is_in_bounds(self, x: int, y: int) -> bool:
        """Check if coordinates are within map boundaries."""
        return 0 <= x < self.width and 0 <= y < self.height

    def is_walkable(self, x: int, y: int) -> bool:
        """Check if a tile can be walked on."""
        if not self.is_in_bounds(x, y):
            return False
        tile = self.tiles[y][x]
        return tile.walkable and not tile.blocked

    def is_transparent(self, x: int, y: int) -> bool:
        """Check if a tile allows vision through it."""
        if not self.is_in_bounds(x, y):
            return False
        return self.tiles[y][x].transparent and not self.tiles[y][x].block_sight

    def get_tile(self, x: int, y: int) -> Optional[Tile]:
        """Get the tile at coordinates, or None if out of bounds."""
        if not self.is_in_bounds(x, y):
            return None
        return self.tiles[y][x]

    def set_tile(self, x: int, y: int, tile_type: TileType, **overrides) -> bool:
        """
        Set a tile at specific coordinates.
        
        Args:
            x, y: Coordinates.
            tile_type: Type of tile to place.
            **overrides: Additional tile attributes to override.
        
        Returns:
            True if successful, False if out of bounds.
        """
        if not self.is_in_bounds(x, y):
            return False
        self.tiles[y][x] = self._create_tile(tile_type, **overrides)
        self._invalidate_cache()
        return True

    def _invalidate_cache(self):
        """Invalidate cached pathfinding and FOV data."""
        self._fov_map = None
        self._pathfinding_cache.clear()

    def create_room(self, room: Rect):
        """Carve out a rectangular room, setting all interior tiles to floor."""
        for y in range(room.y1 + 1, room.y2):
            for x in range(room.x1 + 1, room.x2):
                if self.is_in_bounds(x, y):
                    self.tiles[y][x] = self._floor_tile()
        self._invalidate_cache()

    def create_h_tunnel(self, x1: int, x2: int, y: int, tile_type: TileType = TileType.FLOOR):
        """Create a horizontal tunnel between two x coordinates."""
        for x in range(min(x1, x2), max(x1, x2) + 1):
            if self.is_in_bounds(x, y):
                self.tiles[y][x] = self._create_tile(tile_type)
        self._invalidate_cache()

    def create_v_tunnel(self, y1: int, y2: int, x: int, tile_type: TileType = TileType.FLOOR):
        """Create a vertical tunnel between two y coordinates."""
        for y in range(min(y1, y2), max(y1, y2) + 1):
            if self.is_in_bounds(x, y):
                self.tiles[y][x] = self._create_tile(tile_type)
        self._invalidate_cache()

    def place_door(self, x: int, y: int, locked: bool = False) -> bool:
        """
        Place a door at the specified coordinates.
        
        Args:
            x, y: Door position.
            locked: Whether the door is initially locked.
        
        Returns:
            True if placed successfully.
        """
        if not self.is_in_bounds(x, y):
            return False
        self.tiles[y][x] = self._create_tile(
            TileType.DOOR,
            blocked=locked,
            block_sight=not locked,
            char="+" if locked else "/",
            color="#8B4513" if locked else "#D2691E"
        )
        self._invalidate_cache()
        return True

    def open_door(self, x: int, y: int) -> bool:
        """Open a door at the specified coordinates."""
        tile = self.get_tile(x, y)
        if tile and tile.tile_type == TileType.DOOR and tile.blocked:
            tile.blocked = False
            tile.block_sight = False
            tile.char = "/"
            tile.color = "#D2691E"
            self._invalidate_cache()
            return True
        return False

    def close_door(self, x: int, y: int) -> bool:
        """Close a door at the specified coordinates."""
        tile = self.get_tile(x, y)
        if tile and tile.tile_type == TileType.DOOR and not tile.blocked:
            # Check if something is blocking the door
            tile.blocked = True
            tile.block_sight = True
            tile.char = "+"
            tile.color = "#8B4513"
            self._invalidate_cache()
            return True
        return False

    def place_stairs(self, x: int, y: int, going_up: bool = False) -> bool:
        """Place stairs at the specified coordinates."""
        tile_type = TileType.STAIRS_UP if going_up else TileType.STAIRS_DOWN
        if self.set_tile(x, y, tile_type):
            if going_up:
                self.stairs_up = (x, y)
            else:
                self.stairs_down = (x, y)
            return True
        return False

    def place_feature(self, room: Room) -> bool:
        """
        Add a special feature to a room based on its assigned feature type.
        
        Args:
            room: The room to modify.
        
        Returns:
            True if a feature was placed.
        """
        rect = room.rect
        cx, cy = rect.center

        if room.feature == RoomFeature.PILLARS:
            # Place pillars in corners
            for px, py in [
                (rect.x1 + 2, rect.y1 + 2),
                (rect.x2 - 2, rect.y1 + 2),
                (rect.x1 + 2, rect.y2 - 2),
                (rect.x2 - 2, rect.y2 - 2)
            ]:
                if self.is_in_bounds(px, py):
                    self.tiles[py][px] = self._create_tile(
                        TileType.WALL,
                        char="O", color="#666666",
                        description="A stone pillar."
                    )

        elif room.feature == RoomFeature.ALTAR:
            if self.is_in_bounds(cx, cy):
                self.tiles[cy][cx] = self._create_tile(
                    TileType.FLOOR,
                    char="A", color="#FFD700",
                    description="A mysterious altar."
                )

        elif room.feature == RoomFeature.FOUNTAIN:
            if self.is_in_bounds(cx, cy):
                self.tiles[cy][cx] = self._create_tile(
                    TileType.WATER,
                    walkable=True, char="¶", color="#00CED1",
                    description="A healing fountain."
                )

        elif room.feature == RoomFeature.WATER_POOL:
            # Create a small pool
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    px, py = cx + dx, cy + dy
                    if self.is_in_bounds(px, py) and random.random() > 0.3:
                        self.tiles[py][px] = self._create_tile(TileType.WATER)

        elif room.feature == RoomFeature.TRAP:
            # Place hidden traps
            for _ in range(random.randint(1, 3)):
                tx = random.randint(rect.x1 + 1, rect.x2 - 1)
                ty = random.randint(rect.y1 + 1, rect.y2 - 1)
                if self.is_in_bounds(tx, ty):
                    self.tiles[ty][tx] = self._create_tile(
                        TileType.TRAP,
                        trap_damage=random.randint(5, 15) + self.dungeon_level * 2
                    )

        elif room.feature == RoomFeature.TREASURE:
            # Mark room as having treasure (game engine handles items)
            room.is_special = True

        return True

    def compute_fov(
        self,
        origin_x: int,
        origin_y: int,
        radius: int,
        light_walls: bool = True,
        algorithm: str = "shadow_casting"
    ) -> List[List[bool]]:
        """
        Compute field of view from an origin point.
        
        Args:
            origin_x, origin_y: Viewpoint origin.
            radius: Maximum view distance.
            light_walls: Whether to reveal wall tiles at the edge of vision.
            algorithm: FOV algorithm to use ("shadow_casting" or "ray_casting").
        
        Returns:
            2D boolean grid where True means the tile is visible.
        """
        if algorithm == "shadow_casting":
            return self._compute_fov_shadow_casting(origin_x, origin_y, radius, light_walls)
        else:
            return self._compute_fov_ray_casting(origin_x, origin_y, radius, light_walls)

    def _compute_fov_shadow_casting(
        self,
        ox: int, oy: int,
        radius: int,
        light_walls: bool
    ) -> List[List[bool]]:
        """Shadow casting FOV algorithm - efficient and accurate."""
        visible = [[False for _ in range(self.width)] for _ in range(self.height)]
        
        if not self.is_in_bounds(ox, oy):
            return visible

        # Mark origin as visible
        visible[oy][ox] = True
        self.tiles[oy][ox].explored = True

        # Cast shadows in all 8 octants
        for octant in range(8):
            self._cast_octant(visible, ox, oy, radius, octant, light_walls)

        self._fov_map = visible
        return visible

    def _cast_octant(
        self,
        visible: List[List[bool]],
        ox: int, oy: int,
        radius: int,
        octant: int,
        light_walls: bool
    ):
        """Cast light in a single octant using recursive shadow casting."""
        # Transform coordinates based on octant
        transforms = [
            (1, 0, 0, 1),   # 0: East-North
            (0, 1, 1, 0),   # 1: North-East
            (0, -1, 1, 0),  # 2: North-West
            (-1, 0, 0, 1),  # 3: West-North
            (-1, 0, 0, -1), # 4: West-South
            (0, -1, -1, 0), # 5: South-West
            (0, 1, -1, 0),  # 6: South-East
            (1, 0, 0, -1),  # 7: East-South
        ]
        xx, xy, yx, yy = transforms[octant]

        def transform(dx: int, dy: int) -> Tuple[int, int]:
            return (ox + dx * xx + dy * xy, oy + dx * yx + dy * yy)

        # Recursive shadow casting
        def scan(row: int, start_slope: float, end_slope: float):
            if start_slope >= end_slope or row > radius:
                return

            # Find the first non-transparent tile in this row
            dx = row
            dy = int(row * start_slope)
            
            while dy <= int(row * end_slope):
                x, y = transform(dx, dy)
                
                if not self.is_in_bounds(x, y):
                    dy += 1
                    continue

                # Check if tile is within radius
                distance = math.sqrt(dx * dx + dy * dy)
                if distance > radius:
                    dy += 1
                    continue

                visible[y][x] = True
                self.tiles[y][x].explored = True

                # Check if this tile blocks sight
                blocks = not self.is_transparent(x, y)
                
                if blocks:
                    # If previous tile was transparent, start a new scan
                    if dy > int(row * start_slope):
                        scan(row + 1, start_slope, (dy - 0.5) / (dx + 0.5))
                    start_slope = (dy + 0.5) / (dx - 0.5)
                
                dy += 1

            # Continue scanning if we haven't hit a wall
            if start_slope < end_slope:
                scan(row + 1, start_slope, end_slope)

        scan(1, 0.0, 1.0)

    def _compute_fov_ray_casting(
        self,
        ox: int, oy: int,
        radius: int,
        light_walls: bool
    ) -> List[List[bool]]:
        """Simple ray casting FOV - casts rays to every point on the perimeter."""
        visible = [[False for _ in range(self.width)] for _ in range(self.height)]
        
        if not self.is_in_bounds(ox, oy):
            return visible

        visible[oy][ox] = True
        self.tiles[oy][ox].explored = True

        # Cast rays in a circle
        num_rays = max(8, radius * 8)
        for i in range(num_rays):
            angle = 2 * math.pi * i / num_rays
            dx = math.cos(angle)
            dy = math.sin(angle)
            
            x, y = float(ox), float(oy)
            for _ in range(radius):
                x += dx
                y += dy
                ix, iy = int(round(x)), int(round(y))
                
                if not self.is_in_bounds(ix, iy):
                    break
                
                visible[iy][ix] = True
                self.tiles[iy][ix].explored = True
                
                if not self.is_transparent(ix, iy):
                    if light_walls:
                        visible[iy][ix] = True
                    break

        self._fov_map = visible
        return visible

    def find_path(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        allow_diagonal: bool = False
    ) -> Optional[List[Tuple[int, int]]]:
        """
        Find a path from start to goal using A* pathfinding.
        
        Args:
            start: (x, y) starting position.
            goal: (x, y) target position.
            allow_diagonal: Whether diagonal movement is allowed.
        
        Returns:
            List of coordinates forming the path, or None if no path exists.
        """
        if not self.is_walkable(goal[0], goal[1]):
            return None

        # Check cache
        cache_key = (start, goal, allow_diagonal)
        if cache_key in self._pathfinding_cache:
            return self._pathfinding_cache[cache_key]

        # A* implementation
        open_set: deque = deque([start])
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], float] = {start: 0}
        f_score: Dict[Tuple[int, int], float] = {start: self._heuristic(start, goal)}

        directions = [
            (0, 1), (0, -1), (1, 0), (-1, 0),
            (1, 1), (1, -1), (-1, 1), (-1, -1)
        ] if allow_diagonal else [(0, 1), (0, -1), (1, 0), (-1, 0)]

        while open_set:
            # Find node with lowest f_score
            current = min(open_set, key=lambda p: f_score.get(p, float('inf')))
            open_set.remove(current)

            if current == goal:
                # Reconstruct path
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                self._pathfinding_cache[cache_key] = path
                return path

            for dx, dy in directions:
                neighbor = (current[0] + dx, current[1] + dy)
                
                if not self.is_walkable(neighbor[0], neighbor[1]):
                    continue

                # Diagonal movement requires both adjacent tiles to be walkable
                if allow_diagonal and dx != 0 and dy != 0:
                    if not (self.is_walkable(current[0] + dx, current[1]) and
                            self.is_walkable(current[0], current[1] + dy)):
                        continue

                tentative_g = g_score[current] + (1.414 if dx != 0 and dy != 0 else 1)

                if tentative_g < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + self._heuristic(neighbor, goal)
                    if neighbor not in open_set:
                        open_set.append(neighbor)

        self._pathfinding_cache[cache_key] = None
        return None

    def _heuristic(self, a: Tuple[int, int], b: Tuple[int, int]) -> float:
        """Calculate heuristic distance for A* (diagonal distance)."""
        dx = abs(a[0] - b[0])
        dy = abs(a[1] - b[1])
        return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)

    def get_neighbors(
        self,
        x: int, y: int,
        walkable_only: bool = True,
        include_diagonal: bool = False
    ) -> List[Tuple[int, int]]:
        """
        Get all neighboring coordinates.
        
        Args:
            x, y: Center coordinates.
            walkable_only: Only return walkable neighbors.
            include_diagonal: Include diagonal neighbors.
        
        Returns:
            List of (x, y) neighbor coordinates.
        """
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        if include_diagonal:
            directions.extend([(1, 1), (1, -1), (-1, 1), (-1, -1)])

        neighbors = []
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if self.is_in_bounds(nx, ny):
                if not walkable_only or self.is_walkable(nx, ny):
                    neighbors.append((nx, ny))
        return neighbors

    def get_random_walkable_tile(
        self,
        room: Optional[Rect] = None,
        exclude: Optional[Set[Tuple[int, int]]] = None
    ) -> Optional[Tuple[int, int]]:
        """
        Get a random walkable tile, optionally constrained to a room.
        
        Args:
            room: If provided, only search within this rectangle.
            exclude: Set of coordinates to exclude.
        
        Returns:
            A random (x, y) coordinate, or None if no valid tile found.
        """
        candidates = []
        search_area = room.inner if room else (
            (x, y) for y in range(self.height) for x in range(self.width)
        )
        
        for x, y in search_area:
            if self.is_walkable(x, y):
                if exclude is None or (x, y) not in exclude:
                    candidates.append((x, y))

        return random.choice(candidates) if candidates else None

    def generate_dungeon(
        self,
        max_rooms: int = 30,
        room_min_size: int = 6,
        room_max_size: int = 10,
        room_padding: int = 1,
        feature_chance: float = 0.3,
        trap_chance: float = 0.15
    ) -> Tuple[int, int]:
        """
        Procedurally generate a complete dungeon level.
        
        Args:
            max_rooms: Maximum number of rooms to attempt.
            room_min_size: Minimum room dimension.
            room_max_size: Maximum room dimension.
            room_padding: Extra space between rooms.
            feature_chance: Chance for a room to have a special feature.
            trap_chance: Chance for a room to contain traps.
        
        Returns:
            (x, y) coordinates of the center of the first room (player start).
        """
        self.rooms.clear()
        center_of_first_room = (0, 0)
        
        # Reset map to all walls
        self.tiles = [
            [self._wall_tile() for _ in range(self.width)]
            for _ in range(self.height)
        ]

        for r in range(max_rooms):
            w = random.randint(room_min_size, room_max_size)
            h = random.randint(room_min_size, room_max_size)
            x = random.randint(1, self.width - w - 2)
            y = random.randint(1, self.height - h - 2)

            new_room = Rect(x, y, w, h)
            
            # Check for intersection with padding
            if any(new_room.intersect(other.rect, room_padding) for other in self.rooms):
                continue

            self.create_room(new_room)
            (new_x, new_y) = new_room.center

            # Assign room features
            feature = RoomFeature.NONE
            if random.random() < feature_chance:
                feature = random.choice([
                    RoomFeature.PILLARS, RoomFeature.ALTAR,
                    RoomFeature.FOUNTAIN, RoomFeature.WATER_POOL,
                    RoomFeature.TREASURE
                ])
            elif random.random() < trap_chance:
                feature = RoomFeature.TRAP

            room = Room(rect=new_room, feature=feature, difficulty=self.dungeon_level)
            self.rooms.append(room)
            self.place_feature(room)

            if not self.rooms[:-1]:  # First room
                center_of_first_room = (new_x, new_y)
            else:
                # Connect to previous room with corridor
                (prev_x, prev_y) = self.rooms[-2].rect.center
                if random.random() > 0.5:
                    self.create_h_tunnel(prev_x, new_x, prev_y)
                    self.create_v_tunnel(prev_y, new_y, new_x)
                else:
                    self.create_v_tunnel(prev_y, new_y, prev_x)
                    self.create_h_tunnel(prev_x, new_x, new_y)

                # Sometimes place a door at corridor entrance
                if random.random() > 0.7:
                    door_x = new_x if random.random() > 0.5 else prev_x
                    door_y = new_y if door_x == new_x else prev_y
                    if self.is_in_bounds(door_x, door_y):
                        self.place_door(door_x, door_y, locked=random.random() > 0.8)

        # Place stairs
        if len(self.rooms) >= 2:
            # Stairs down in the last room
            last_room = self.rooms[-1].rect
            sx = random.randint(last_room.x1 + 1, last_room.x2 - 1)
            sy = random.randint(last_room.y1 + 1, last_room.y2 - 1)
            self.place_stairs(sx, sy, going_up=False)

            # Stairs up in the first room
            first_room = self.rooms[0].rect
            sx = random.randint(first_room.x1 + 1, first_room.x2 - 1)
            sy = random.randint(first_room.y1 + 1, first_room.y2 - 1)
            self.place_stairs(sx, sy, going_up=True)

        self._invalidate_cache()
        return center_of_first_room

    def generate_cave(
        self,
        fill_prob: float = 0.45,
        smoothing_iterations: int = 5,
        birth_limit: int = 4,
        death_limit: int = 3
    ) -> Tuple[int, int]:
        """
        Generate a cave-like dungeon using cellular automata.
        
        Args:
            fill_prob: Initial probability of a wall tile.
            smoothing_iterations: Number of smoothing passes.
            birth_limit: Neighbors needed to create a wall.
            death_limit: Neighbors needed to destroy a wall.
        
        Returns:
            (x, y) coordinates of a valid starting position.
        """
        # Initialize random grid
        for y in range(self.height):
            for x in range(self.width):
                if random.random() < fill_prob:
                    self.tiles[y][x] = self._wall_tile()
                else:
                    self.tiles[y][x] = self._floor_tile()

        # Cellular automata smoothing
        for _ in range(smoothing_iterations):
            new_tiles = [row[:] for row in self.tiles]
            for y in range(1, self.height - 1):
                for x in range(1, self.width - 1):
                    neighbors = self._count_wall_neighbors(x, y)
                    if self.tiles[y][x].tile_type == TileType.WALL:
                        if neighbors < death_limit:
                            new_tiles[y][x] = self._floor_tile()
                    else:
                        if neighbors > birth_limit:
                            new_tiles[y][x] = self._wall_tile()
            self.tiles = new_tiles

        # Find largest connected floor region for player start
        start = self._find_largest_floor_region()
        
        # Place stairs
        if start:
            self.place_stairs(start[0], start[1], going_up=True)
            # Find farthest point for stairs down
            far_point = self._find_farthest_point(start)
            if far_point:
                self.place_stairs(far_point[0], far_point[1], going_up=False)

        self._invalidate_cache()
        return start or (self.width // 2, self.height // 2)

    def _count_wall_neighbors(self, x: int, y: int) -> int:
        """Count wall neighbors including diagonals."""
        count = 0
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if not self.is_in_bounds(nx, ny):
                    count += 1
                elif self.tiles[ny][nx].tile_type == TileType.WALL:
                    count += 1
        return count

    def _find_largest_floor_region(self) -> Optional[Tuple[int, int]]:
        """Find the largest connected floor region and return a point in it."""
        visited = [[False for _ in range(self.width)] for _ in range(self.height)]
        largest_region = []
        
        for y in range(self.height):
            for x in range(self.width):
                if (self.tiles[y][x].tile_type == TileType.FLOOR and
                    not visited[y][x]):
                    region = self._flood_fill(x, y, visited)
                    if len(region) > len(largest_region):
                        largest_region = region
        
        return random.choice(largest_region) if largest_region else None

    def _flood_fill(
        self,
        x: int, y: int,
        visited: List[List[bool]]
    ) -> List[Tuple[int, int]]:
        """Flood fill to find all connected floor tiles."""
        region = []
        queue = deque([(x, y)])
        visited[y][x] = True
        
        while queue:
            cx, cy = queue.popleft()
            region.append((cx, cy))
            
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = cx + dx, cy + dy
                if (self.is_in_bounds(nx, ny) and
                    not visited[ny][nx] and
                    self.tiles[ny][nx].tile_type == TileType.FLOOR):
                    visited[ny][nx] = True
                    queue.append((nx, ny))
        
        return region

    def _find_farthest_point(self, start: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Find the walkable tile farthest from the start point using BFS."""
        distances = self._compute_distance_map(start)
        max_dist = -1
        farthest = None
        
        for y in range(self.height):
            for x in range(self.width):
                if distances[y][x] > max_dist:
                    max_dist = distances[y][x]
                    farthest = (x, y)
        
        return farthest

    def _compute_distance_map(
        self,
        origin: Tuple[int, int]
    ) -> List[List[int]]:
        """Compute distance from origin to all walkable tiles using BFS."""
        distances = [[-1 for _ in range(self.width)] for _ in range(self.height)]
        queue = deque([origin])
        distances[origin[1]][origin[0]] = 0
        
        while queue:
            x, y = queue.popleft()
            for nx, ny in self.get_neighbors(x, y, walkable_only=True):
                if distances[ny][nx] == -1:
                    distances[ny][nx] = distances[y][x] + 1
                    queue.append((nx, ny))
        
        return distances

    def to_dict(self) -> dict:
        """Serialize the map to a dictionary for network transmission."""
        return {
            "width": self.width,
            "height": self.height,
            "dungeon_level": self.dungeon_level,
            "tiles": [
                [
                    {
                        "type": tile.tile_type.name,
                        "char": tile.char,
                        "color": tile.color,
                        "walkable": tile.walkable,
                        "transparent": tile.transparent,
                        "blocked": tile.blocked,
                        "explored": tile.explored,
                    }
                    for tile in row
                ]
                for row in self.tiles
            ],
            "stairs_up": self.stairs_up,
            "stairs_down": self.stairs_down,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Map':
        """Deserialize a map from a dictionary."""
        map_obj = cls(data["width"], data["height"], data.get("dungeon_level", 1))
        
        type_map = {t.name: t for t in TileType}
        for y, row in enumerate(data["tiles"]):
            for x, tile_data in enumerate(row):
                tile_type = type_map.get(tile_data["type"], TileType.WALL)
                map_obj.tiles[y][x] = map_obj._create_tile(
                    tile_type,
                    char=tile_data.get("char", "█"),
                    color=tile_data.get("color", "#444"),
                    walkable=tile_data.get("walkable", False),
                    transparent=tile_data.get("transparent", False),
                    blocked=tile_data.get("blocked", False),
                    explored=tile_data.get("explored", False),
                )
        
        map_obj.stairs_up = data.get("stairs_up")
        map_obj.stairs_down = data.get("stairs_down")
        return map_obj

    def __repr__(self):
        return f"Map({self.width}x{self.height}, level={self.dungeon_level}, rooms={len(self.rooms)})"