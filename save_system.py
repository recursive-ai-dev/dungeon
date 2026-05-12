# Standard library imports
import gzip
import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Protocol, TypeVar, Callable
from pathlib import Path
import time

# Third-party imports
# (none)

# Local imports
if TYPE_CHECKING:
    from dungeon.engine import GameEngine


class SaveError(Exception):
    """Base exception for save system errors."""
    pass


class LoadError(SaveError):
    """Raised when loading a save file fails."""
    pass


class CorruptSaveError(LoadError):
    """Raised when a save file is corrupted or has invalid checksum."""
    pass


class VersionMismatchError(LoadError):
    """Raised when save file version is incompatible."""
    pass


class SaveVersion(Enum):
    """Enumeration of save file versions for migration."""
    V1_0 = "1.0"
    V2_0 = "2.0"  # Current version with enhanced features
    CURRENT = V2_0



SAVE_DIR = "saves"
MAX_SLOTS = 5


@dataclass
class PersistentContext:
    """Persistent game state that survives across all runs."""
    total_runs: int = 0
    highest_floor: int = 0
    total_kills: int = 0
    total_gold: int = 0
    ng_plus_level: int = 0
    unlocked_classes: List[str] = field(default_factory=lambda: ["warrior"])
    achievements: List[str] = field(default_factory=list)
    delayed_branching_stats: Dict[str, int] = field(default_factory=lambda: {"brutality": 0, "finesse": 0})
    alibi_narratives: List[str] = field(default_factory=list)
    
    # New: Storylet persistence
    triggered_storylets: List[str] = field(default_factory=list)
    storylet_cooldowns: Dict[str, float] = field(default_factory=dict)
    
    # New: Statistics tracking
    total_playtime_seconds: float = 0.0
    total_damage_dealt: int = 0
    total_damage_taken: int = 0
    favorite_combat_style: str = "balanced"
    
    # New: Timestamps
    first_played: Optional[str] = None
    last_played: Optional[str] = None
    
    def __post_init__(self):
        if not self.first_played:
            self.first_played = datetime.now().isoformat()
        self.last_played = datetime.now().isoformat()

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


@dataclass
class SaveSlot:
    """Metadata for a save slot."""
    slot_id: int
    player_name: str
    dungeon_level: int
    player_hp: int
    player_max_hp: int
    timestamp: str
    is_ng_plus: bool = False
    playtime_seconds: int = 0
    notes: str = ""
    
    # New: Enhanced metadata
    version: str = SaveVersion.CURRENT.value
    checksum: str = ""
    compressed: bool = True
    size_bytes: int = 0
    
    # New: Quick-save marker
    is_quicksave: bool = False
    
    # New: Engine statistics snapshot
    combat_style: str = "balanced"
    enemies_slain: int = 0
    gold_earned: int = 0


class SaveSystem:
    def __init__(self, save_dir: str = SAVE_DIR):
        self.save_dir = save_dir
        self.persistent_context = PersistentContext()
        self._ensure_save_dir()
        self._migrations = {
            SaveVersion.V1_0.value: self._migrate_v1_to_v2,
        }
        self._autosave_rotation = 3  # Keep last 3 autosaves

    def _ensure_save_dir(self):
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
        persistent_file = os.path.join(self.save_dir, "persistent.json")
        if os.path.exists(persistent_file):
            try:
                with open(persistent_file, 'r') as f:
                    data = json.load(f)
                    self.persistent_context = PersistentContext.from_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Failed to load persistent context: {e}")
                self.persistent_context = PersistentContext()

    def save_persistent_context(self):
        self.persistent_context.last_played = datetime.now().isoformat()
        persistent_file = os.path.join(self.save_dir, "persistent.json")
        with open(persistent_file, 'w') as f:
            json.dump(self.persistent_context.to_dict(), f, indent=2)
    
    def _compute_checksum(self, data: bytes) -> str:
        """Compute SHA256 checksum for data integrity."""
        return hashlib.sha256(data).hexdigest()
    
    def _compress_data(self, data: str) -> bytes:
        """Compress JSON data using gzip."""
        return gzip.compress(data.encode('utf-8'))
    
    def _decompress_data(self, data: bytes) -> str:
        """Decompress gzip data."""
        return gzip.decompress(data).decode('utf-8')
    
    def _migrate_v1_to_v2(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate save data from version 1.0 to 2.0."""
        # Add new fields with defaults
        if "persistent_state" in data:
            persistent = data["persistent_state"]
            persistent.setdefault("triggered_storylets", [])
            persistent.setdefault("storylet_cooldowns", {})
            persistent.setdefault("total_playtime_seconds", 0.0)
            persistent.setdefault("total_damage_dealt", 0)
            persistent.setdefault("total_damage_taken", 0)
            persistent.setdefault("favorite_combat_style", "balanced")
            persistent.setdefault("first_played", datetime.now().isoformat())
            persistent.setdefault("last_played", datetime.now().isoformat())
        return data

    def get_slot_info(self, slot_id: int) -> Optional[SaveSlot]:
        slot_file = os.path.join(self.save_dir, f"slot_{slot_id}.json")
        if not os.path.exists(slot_file):
            return None
        try:
            with open(slot_file, 'rb') as f:
                raw_data = f.read()
            
            # Try to detect and decompress
            try:
                data_str = self._decompress_data(raw_data)
                data = json.loads(data_str)
                compressed = True
            except:
                data = json.loads(raw_data.decode('utf-8'))
                compressed = False
            
            return SaveSlot(
                slot_id=data.get("slot_id", slot_id),
                player_name=data.get("player_name", "Unknown"),
                dungeon_level=data.get("dungeon_level", 1),
                player_hp=data.get("player_hp", 0),
                player_max_hp=data.get("player_max_hp", 0),
                timestamp=data.get("timestamp", ""),
                is_ng_plus=data.get("is_ng_plus", False),
                playtime_seconds=data.get("playtime_seconds", 0),
                notes=data.get("notes", ""),
                version=data.get("version", SaveVersion.V1_0.value),
                checksum=data.get("checksum", ""),
                compressed=compressed,
                size_bytes=len(raw_data),
                is_quicksave=data.get("is_quicksave", False),
                combat_style=data.get("combat_style", "balanced"),
                enemies_slain=data.get("enemies_slain", 0),
                gold_earned=data.get("gold_earned", 0)
            )
        except Exception as e:
            raise LoadError(f"Failed to load slot {slot_id}: {e}")

    def list_slots(self) -> List[SaveSlot]:
        slots = []
        for i in range(1, MAX_SLOTS + 1):
            slot = self.get_slot_info(i)
            if slot:
                slots.append(slot)
        return slots

    def save_game(self, slot_id: int, game_state: Dict[str, Any], player_name: str = "Player", 
                 is_quicksave: bool = False, notes: str = "") -> bool:
        slot_file = os.path.join(self.save_dir, f"slot_{slot_id}.json")

        save_data = {
            "slot_id": slot_id,
            "player_name": player_name,
            "timestamp": datetime.now().isoformat(),
            "ephemeral_state": game_state.get("ephemeral", {}),
            "persistent_state": game_state.get("persistent", {}),
            "dungeon_level": game_state.get("dungeon_level", 1),
            "player_hp": game_state.get("player_hp", 0),
            "player_max_hp": game_state.get("player_max_hp", 0),
            "is_ng_plus": game_state.get("is_ng_plus", False),
            "playtime_seconds": game_state.get("playtime_seconds", 0),
            "version": SaveVersion.CURRENT.value,
            "is_quicksave": is_quicksave,
            "notes": notes,
            # New: Engine statistics
            "combat_style": game_state.get("combat_style", "balanced"),
            "enemies_slain": game_state.get("enemies_slain", 0),
            "gold_earned": game_state.get("gold_earned", 0),
        }

        # Merge persistent context
        save_data["persistent_state"].update(self.persistent_context.to_dict())

        try:
            json_str = json.dumps(save_data, indent=2)
            compressed_data = self._compress_data(json_str)
            checksum = self._compute_checksum(compressed_data)
            
            save_data["checksum"] = checksum
            save_data["compressed"] = True
            
            final_json = json.dumps(save_data, indent=2)
            final_data = self._compress_data(final_json)
            
            with open(slot_file, 'wb') as f:
                f.write(final_data)
            return True
        except Exception as e:
            raise SaveError(f"Save failed: {e}")

    def load_game(self, slot_id: int) -> Optional[Dict[str, Any]]:
        slot_file = os.path.join(self.save_dir, f"slot_{slot_id}.json")
        if not os.path.exists(slot_file):
            return None

        try:
            with open(slot_file, 'rb') as f:
                raw_data = f.read()
            
            # Try decompression
            try:
                data_str = self._decompress_data(raw_data)
                data = json.loads(data_str)
            except:
                data = json.loads(raw_data.decode('utf-8'))
            
            # Verify checksum
            if "checksum" in data and data["compressed"]:
                recomputed = self._compute_checksum(raw_data)
                if recomputed != data["checksum"]:
                    raise CorruptSaveError("Checksum mismatch - save file may be corrupted")
            
            # Version migration
            version = data.get("version", SaveVersion.V1_0.value)
            if version != SaveVersion.CURRENT.value:
                if version in self._migrations:
                    data = self._migrations[version](data)
                else:
                    raise VersionMismatchError(f"Cannot migrate from version {version}")
            
            # Update persistent context with loaded data
            if "persistent_state" in data:
                for key, value in data["persistent_state"].items():
                    if hasattr(self.persistent_context, key):
                        setattr(self.persistent_context, key, value)
            
            return {
                "ephemeral": data.get("ephemeral_state", {}),
                "persistent": data.get("persistent_state", {}),
                "dungeon_level": data.get("dungeon_level", 1),
                "player_hp": data.get("player_hp", 0),
                "player_max_hp": data.get("player_max_hp", 0),
                "is_ng_plus": data.get("is_ng_plus", False),
                "playtime_seconds": data.get("playtime_seconds", 0),
                "player_name": data.get("player_name", "Player"),
                "combat_style": data.get("combat_style", "balanced"),
                "enemies_slain": data.get("enemies_slain", 0),
                "gold_earned": data.get("gold_earned", 0),
            }
        except CorruptSaveError:
            raise
        except VersionMismatchError:
            raise
        except Exception as e:
            raise LoadError(f"Load failed: {e}")

    def delete_slot(self, slot_id: int) -> bool:
        slot_file = os.path.join(self.save_dir, f"slot_{slot_id}.json")
        if os.path.exists(slot_file):
            os.remove(slot_file)
            return True
        return False

    def autosave(self, game_state: Dict[str, Any]) -> bool:
        """Perform autosave with rotation."""
        # Rotate autosaves
        for i in range(self._autosave_rotation - 1, 0, -1):
            old_file = os.path.join(self.save_dir, f"autosave_{i}.json")
            new_file = os.path.join(self.save_dir, f"autosave_{i + 1}.json")
            if os.path.exists(old_file):
                if os.path.exists(new_file):
                    os.remove(new_file)
                os.rename(old_file, new_file)
        
        return self.save_game(0, game_state, "Autosave", is_quicksave=True)

    def load_autosave(self) -> Optional[Dict[str, Any]]:
        """Load most recent autosave."""
        return self.load_game(0)
    
    def quicksave(self, game_state: Dict[str, Any], notes: str = "") -> bool:
        """Quick save to a dedicated quicksave slot."""
        quicksave_file = os.path.join(self.save_dir, "quicksave.json")
        
        save_data = {
            "slot_id": -1,  # Special slot for quicksave
            "player_name": game_state.get("player_name", "Player"),
            "timestamp": datetime.now().isoformat(),
            "ephemeral_state": game_state.get("ephemeral", {}),
            "persistent_state": game_state.get("persistent", {}),
            "dungeon_level": game_state.get("dungeon_level", 1),
            "player_hp": game_state.get("player_hp", 0),
            "player_max_hp": game_state.get("player_max_hp", 0),
            "is_ng_plus": game_state.get("is_ng_plus", False),
            "playtime_seconds": game_state.get("playtime_seconds", 0),
            "version": SaveVersion.CURRENT.value,
            "is_quicksave": True,
            "notes": notes,
            "combat_style": game_state.get("combat_style", "balanced"),
            "enemies_slain": game_state.get("enemies_slain", 0),
            "gold_earned": game_state.get("gold_earned", 0),
        }
        
        save_data["persistent_state"].update(self.persistent_context.to_dict())
        
        try:
            json_str = json.dumps(save_data, indent=2)
            compressed_data = self._compress_data(json_str)
            checksum = self._compute_checksum(compressed_data)
            
            save_data["checksum"] = checksum
            save_data["compressed"] = True
            
            final_json = json.dumps(save_data, indent=2)
            final_data = self._compress_data(final_json)
            
            with open(quicksave_file, 'wb') as f:
                f.write(final_data)
            return True
        except Exception as e:
            raise SaveError(f"Quicksave failed: {e}")
    
    def load_quicksave(self) -> Optional[Dict[str, Any]]:
        """Load quicksave."""
        quicksave_file = os.path.join(self.save_dir, "quicksave.json")
        if not os.path.exists(quicksave_file):
            return None
        
        try:
            with open(quicksave_file, 'rb') as f:
                raw_data = f.read()
            
            try:
                data_str = self._decompress_data(raw_data)
                data = json.loads(data_str)
            except:
                data = json.loads(raw_data.decode('utf-8'))
            
            if "checksum" in data and data["compressed"]:
                recomputed = self._compute_checksum(raw_data)
                if recomputed != data["checksum"]:
                    raise CorruptSaveError("Quicksave checksum mismatch")
            
            version = data.get("version", SaveVersion.V1_0.value)
            if version != SaveVersion.CURRENT.value:
                if version in self._migrations:
                    data = self._migrations[version](data)
            
            if "persistent_state" in data:
                for key, value in data["persistent_state"].items():
                    if hasattr(self.persistent_context, key):
                        setattr(self.persistent_context, key, value)
            
            return {
                "ephemeral": data.get("ephemeral_state", {}),
                "persistent": data.get("persistent_state", {}),
                "dungeon_level": data.get("dungeon_level", 1),
                "player_hp": data.get("player_hp", 0),
                "player_max_hp": data.get("player_max_hp", 0),
                "is_ng_plus": data.get("is_ng_plus", False),
                "playtime_seconds": data.get("playtime_seconds", 0),
                "player_name": data.get("player_name", "Player"),
                "combat_style": data.get("combat_style", "balanced"),
                "enemies_slain": data.get("enemies_slain", 0),
                "gold_earned": data.get("gold_earned", 0),
            }
        except Exception as e:
            raise LoadError(f"Quicksave load failed: {e}")
    
    def export_save(self, slot_id: int, export_path: str) -> bool:
        """Export a save file to an external location."""
        slot_file = os.path.join(self.save_dir, f"slot_{slot_id}.json")
        if not os.path.exists(slot_file):
            return False
        
        try:
            shutil.copy2(slot_file, export_path)
            return True
        except Exception as e:
            raise SaveError(f"Export failed: {e}")
    
    def import_save(self, import_path: str, target_slot: int) -> bool:
        """Import a save file from an external location."""
        if not os.path.exists(import_path):
            return False
        
        target_file = os.path.join(self.save_dir, f"slot_{target_slot}.json")
        
        try:
            # Verify the imported file is valid
            with open(import_path, 'rb') as f:
                raw_data = f.read()
            
            try:
                data_str = self._decompress_data(raw_data)
                data = json.loads(data_str)
            except:
                data = json.loads(raw_data.decode('utf-8'))
            
            if "checksum" in data and data["compressed"]:
                recomputed = self._compute_checksum(raw_data)
                if recomputed != data["checksum"]:
                    raise CorruptSaveError("Imported file checksum mismatch")
            
            shutil.copy2(import_path, target_file)
            return True
        except Exception as e:
            raise SaveError(f"Import failed: {e}")

    def update_persistent_on_death(self, floor_reached: int, kills: int, gold: int, 
                                combat_stats: Optional[Dict[str, Any]] = None):
        self.persistent_context.total_runs += 1
        if floor_reached > self.persistent_context.highest_floor:
            self.persistent_context.highest_floor = floor_reached
        self.persistent_context.total_kills += kills
        self.persistent_context.total_gold += gold
        
        if combat_stats:
            self.persistent_context.total_damage_dealt += combat_stats.get("total_damage_dealt", 0)
            self.persistent_context.total_damage_taken += combat_stats.get("total_damage_taken", 0)
            self.persistent_context.favorite_combat_style = combat_stats.get("combat_style", "balanced")

    def update_persistent_on_victory(self, floor_reached: int, playtime: float = 0.0,
                                 combat_stats: Optional[Dict[str, Any]] = None):
        self.persistent_context.total_runs += 1
        if floor_reached > self.persistent_context.highest_floor:
            self.persistent_context.highest_floor = floor_reached
        self.persistent_context.delayed_branching_stats["brutality"] += floor_reached
        self.persistent_context.total_playtime_seconds += playtime
        
        if combat_stats:
            self.persistent_context.total_damage_dealt += combat_stats.get("total_damage_dealt", 0)
            self.persistent_context.total_damage_taken += combat_stats.get("total_damage_taken", 0)
            self.persistent_context.favorite_combat_style = combat_stats.get("combat_style", "balanced")

    def generate_alibi(self, ng_plus_level: int) -> str:
        alibi_options = [
            f"You awake with fragmented memories of previous lives...",
            f"Visions of {self.persistent_context.highest_floor} floors burned into your mind.",
            f"The spirits of your past incarnations whisper their wisdom.",
            f"You carry the weight of {self.persistent_context.total_runs} previous attempts.",
            f"Ancient knowledge stirs within you from your {ng_plus_level}th journey.",
        ]
        alibi = alibi_options[ng_plus_level % len(alibi_options)]
        self.persistent_context.alibi_narratives.append(alibi)
        return alibi

    def start_ng_plus(self, current_stats: Dict[str, Any]) -> Dict[str, Any]:
        """Start a new NG+ run with bonuses."""
        self.persistent_context.ng_plus_level += 1
        alibi = self.generate_alibi(self.persistent_context.ng_plus_level)
        
        # Calculate bonuses based on NG+ level
        bonus_hp = self.persistent_context.ng_plus_level * 10
        bonus_mana = self.persistent_context.ng_plus_level * 5
        bonus_gold = self.persistent_context.ng_plus_level * 50
        
        # Unlock new classes at certain NG+ levels
        if self.persistent_context.ng_plus_level >= 2 and "mage" not in self.persistent_context.unlocked_classes:
            self.persistent_context.unlocked_classes.append("mage")
        if self.persistent_context.ng_plus_level >= 3 and "rogue" not in self.persistent_context.unlocked_classes:
            self.persistent_context.unlocked_classes.append("rogue")
        if self.persistent_context.ng_plus_level >= 5 and "cleric" not in self.persistent_context.unlocked_classes:
            self.persistent_context.unlocked_classes.append("cleric")
        
        return {
            "hp_bonus": bonus_hp,
            "mana_bonus": bonus_mana,
            "gold_bonus": bonus_gold,
            "alibi": alibi,
            "unlocked_classes": self.persistent_context.unlocked_classes.copy(),
            "ng_plus_level": self.persistent_context.ng_plus_level
        }

    def get_achievements(self) -> List[str]:
        """Get all unlocked achievements based on persistent context."""
        achievements = []
        
        # Run-based achievements
        if self.persistent_context.total_runs >= 10:
            achievements.append("Dedicated Explorer")
        if self.persistent_context.total_runs >= 50:
            achievements.append("Veteran Delver")
        if self.persistent_context.total_runs >= 100:
            achievements.append("Legendary Explorer")
        
        # Depth-based achievements
        if self.persistent_context.highest_floor >= 5:
            achievements.append("Surface Dweller")
        if self.persistent_context.highest_floor >= 10:
            achievements.append("Deep Delver")
        if self.persistent_context.highest_floor >= 20:
            achievements.append("Abyss Walker")
        if self.persistent_context.highest_floor >= 30:
            achievements.append("Void Treader")
        
        # NG+ achievements
        if self.persistent_context.ng_plus_level >= 1:
            achievements.append("Cycle Breaker")
        if self.persistent_context.ng_plus_level >= 5:
            achievements.append("Reincarnate")
        if self.persistent_context.ng_plus_level >= 10:
            achievements.append("Timeless")
        
        # Combat achievements
        if self.persistent_context.total_kills >= 100:
            achievements.append("Monster Slayer")
        if self.persistent_context.total_kills >= 500:
            achievements.append("Butcher")
        if self.persistent_context.total_kills >= 1000:
            achievements.append("Apex Predator")
        
        # Gold achievements
        if self.persistent_context.total_gold >= 1000:
            achievements.append("Wealthy")
        if self.persistent_context.total_gold >= 5000:
            achievements.append("Rich")
        if self.persistent_context.total_gold >= 10000:
            achievements.append("Tycoon")
        
        # Combat style achievements
        if self.persistent_context.favorite_combat_style == "aggressive":
            achievements.append("Berserker")
        if self.persistent_context.favorite_combat_style == "defensive":
            achievements.append("Guardian")
        if self.persistent_context.favorite_combat_style == "tactical":
            achievements.append("Strategist")
        
        # Storylet achievements
        if len(self.persistent_context.triggered_storylets) >= 5:
            achievements.append("Story Seeker")
        if len(self.persistent_context.triggered_storylets) >= 10:
            achievements.append("Lore Master")
        
        return achievements
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics from persistent context."""
        return {
            "total_runs": self.persistent_context.total_runs,
            "highest_floor": self.persistent_context.highest_floor,
            "total_kills": self.persistent_context.total_kills,
            "total_gold": self.persistent_context.total_gold,
            "total_playtime_hours": self.persistent_context.total_playtime_seconds / 3600,
            "total_damage_dealt": self.persistent_context.total_damage_dealt,
            "total_damage_taken": self.persistent_context.total_damage_taken,
            "favorite_combat_style": self.persistent_context.favorite_combat_style,
            "ng_plus_level": self.persistent_context.ng_plus_level,
            "unlocked_classes": self.persistent_context.unlocked_classes,
            "achievements_count": len(self.get_achievements()),
            "triggered_storylets_count": len(self.persistent_context.triggered_storylets),
            "first_played": self.persistent_context.first_played,
            "last_played": self.persistent_context.last_played,
        }


save_system = SaveSystem()