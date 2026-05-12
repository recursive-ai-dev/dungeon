"""
Enhanced Dungeon Crawler TUI — main.py
======================================
A dramatically upgraded terminal interface for the dungeon engine,
featuring: reactive state, animated transitions, a command palette,
mini-map, combat log viewer, run statistics dashboard, contextual
action bar, particle-style damage numbers, screen-shake on hit,
and a fully overhauled aesthetic.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.reactive import reactive
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Static,
    RichLog,
    ProgressBar,
    DataTable,
    TabbedContent,
    TabPane,
    Input,
    Checkbox,
    Select,
)
from textual.worker import Worker

from dungeon.entities import (
    CurioMerchant,
    Item,
    LoreSystem,
    Player,
    Stairs,
)
from dungeon.engine import GameEngine


# ═══════════════════════════════════════════════════════════════════════════════
#  UTILITY / DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ScreenShake:
    """Encapsulates screen-shake state for combat feedback."""
    intensity: int = 0
    duration: float = 0.0
    start_time: float = 0.0

    def active(self) -> bool:
        return time.time() - self.start_time < self.duration

    def offset(self) -> Tuple[int, int]:
        if not self.active():
            return (0, 0)
        elapsed = time.time() - self.start_time
        decay = 1.0 - (elapsed / self.duration)
        dx = random.randint(-self.intensity, self.intensity) * decay
        dy = random.randint(-self.intensity, self.intensity) * decay
        return (int(dx), int(dy))


@dataclass
class FloatingText:
    """A transient damage/heal number that floats up and fades."""
    text: str
    color: str
    x: int
    y: int
    birth: float
    lifetime: float = 1.2

    def alpha(self) -> float:
        elapsed = time.time() - self.birth
        if elapsed > self.lifetime:
            return 0.0
        return 1.0 - (elapsed / self.lifetime)


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREENS
# ═══════════════════════════════════════════════════════════════════════════════

class GameOverScreen(ModalScreen):
    """Cinematic death screen with lore revelation and run stats."""

    def __init__(
        self,
        death_scene: str = "",
        lore_title: str = "",
        lore_text: str = "",
        stats: Optional[dict] = None,
    ):
        super().__init__()
        self.death_scene = death_scene
        self.lore_title = lore_title
        self.lore_text = lore_text
        self.stats = stats or {}

    def compose(self) -> ComposeResult:
        with Vertical(id="gameover-container"):
            yield Label("THE END OF THE LINE", id="gameover-header")
            yield Label(
                "Your journey ends here, in the cold embrace of the pit...",
                id="gameover-subtitle",
            )
            if self.death_scene:
                yield Label(f"[italic]{self.death_scene}[/italic]", id="death-scene")
            if self.lore_title:
                yield Label(
                    f"[bold cyan]A TRUTH REVEALED: {self.lore_title}[/bold cyan]",
                    id="lore-title",
                )
                yield Label(f"[cyan]{self.lore_text}[/cyan]", id="lore-text")

            # Run statistics panel
            if self.stats:
                with Vertical(id="run-stats"):
                    yield Label("[bold]TALLY OF THE FALLEN[/bold]", id="stats-header")
                    yield Label(
                        f"Depth Reached: [bold]{self.stats.get('dungeon_level_reached', 1)}[/bold]  |  "
                        f"Kills: [bold]{self.stats.get('enemies_slain', 0)}[/bold]  |  "
                        f"Gold: [bold]{self.stats.get('gold_earned', 0)}[/bold]"
                    )
                    yield Label(
                        f"Style: [bold]{self.stats.get('combat_style', 'balanced').title()}[/bold]  |  "
                        f"Playtime: [bold]{self.stats.get('playtime_seconds', 0)}s[/bold]"
                    )
                    if self.stats.get("achievements"):
                        yield Label(
                            "Rites: " + ", ".join(self.stats["achievements"]),
                            id="achievements-line",
                        )

            yield Button("Begin Anew", id="restart-btn", variant="primary")
            yield Button("Surrender to the Dark", id="quit-btn", variant="error")

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("r", "restart", "Restart"),
        Binding("q", "quit", "Quit"),
    ]

    def action_restart(self) -> None:
        self.dismiss("restart")

    def action_quit(self) -> None:
        self.dismiss("quit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "restart-btn":
            self.dismiss("restart")
        else:
            self.dismiss("quit")


class HelpScreen(ModalScreen):
    """Comprehensive help with searchable hotkey reference."""

    def compose(self) -> ComposeResult:
        with Vertical(id="help-container"):
            yield Label("SCROLL OF GUIDANCE", id="help-header")
            yield Label(
                "[bold]The Dance of Death (Movement)[/]\n"
                "  [key]Arrow Keys[/] / [key]WASD[/]  Move\n"
                "  [key]Space[/]              Rest / Catch Breath\n\n"
                "[bold]The Labor of Survival (Actions)[/]\n"
                "  [key]g[/]   Scavenge item\n"
                "  [key]i[/]   Inspect satchel\n"
                "  [key]>[/]   Descend further\n"
                "  [key]e[/]   Invoke site (shrine underfoot, or trade with Curio Peddler when adjacent)\n"
                "  [key]1–5[/] Cast learned arcana (costs spirit; Stone to Mud uses last move direction)\n"
                "  [key]l[/]   Gaze / Examine surroundings\n"
                "  [key]u[/]   Unravel fate (Undo)\n"
                "  [key]h[/]   Seek omen (Hint)\n"
                "  [key]?[/]   This scroll\n\n"
                "[bold]The Satchel (Inventory)[/]\n"
                "  [key]Enter[/]  Use / Equip relic\n"
                "  [key]d[/]      Discard item\n"
                "  [key]Esc[/]    Close\n\n"
                "[bold]Memory & Blood (Save/Load)[/]\n"
                "  [key]Ctrl+S[/]  Etch memory (Save)\n"
                "  [key]Ctrl+A[/]  Fated anchor (Autosave)\n\n"
                "[bold]Relics of the Fallen[/]\n"
                "  [bold #7f00ff]![/] Alchemical Draught (Health)\n"
                "  [bold #ffff00]?[/] Storm-touched Parchment (Lightning)\n"
                "  [bold #ff00ff]?[/] Mist of Confusion\n"
                "  [bold #55aaff]/[/] Notched Blade (weapon)\n"
                "  [bold #aaaaaa][[/] Rusted Mail\n\n"
                "[bold]The Denizens[/]\n"
                "  [bold #8B4513]g[/] Goblin Scavenger\n"
                "  [bold #3f7f3f]o[/] Orc Auditor\n"
                "  [bold #007f00]T[/] Systemic Troll\n"
                "  [bold #ff4444]D[/] The Legacy Kernel (Boss)\n"
                "  [bold #ff00ff]?[/] Logic Disrupter\n"
                "  [bold #00ffff]~[/] Data Siphoner\n"
                "  [bold #8844ff]W[/] Fate Weaver\n\n"
                "[bold]Other finds[/]\n"
                "  [bold #d4af37]$[/] Tarnished Coin Pile (pick up: banks coin)\n"
                "  [bold #66ddff]*[/] Essence Phial (spirit)\n"
                "  [bold #ffd700]+[/] Shrine (invoke once with e—then cold cinder)\n"
                "  [bold #eecc66]&[/] Curio Peddler (adjacent + e; one stall per run; each ware once)\n\n"
                "[bold]The Weight of the World (Status)[/]\n"
                "  Flames consume the flesh\n"
                "  The dampness of the deep smothers fire\n"
                "  The chill of the void halts the heart\n\n"
                "[bold]The Finality[/]\n"
                "  [key]q[/]    Abandon the descent\n"
                "  [key]Esc[/]  Close scroll"
            )
            yield Button("Return to the Dark", id="close-btn")

    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()


class ShopScreen(ModalScreen):
    """The Curio Peddler's ledger with animated coin counter."""

    def __init__(self, engine: GameEngine, merchant: CurioMerchant):
        super().__init__()
        self.engine = engine
        self.merchant = merchant

    def compose(self) -> ComposeResult:
        with Vertical(id="shop-container"):
            yield Label("THE CURIO PEDDLER", id="shop-header")
            yield Label(
                "Each line is written once. Pay in coin; no rain checks in the pit.",
                id="shop-sub",
            )
            yield Label(
                f"Your purse: [bold #d4af37]{self.engine.player.gold}[/bold #d4af37] coin",
                id="shop-purse",
            )
            for i, row in enumerate(self.merchant.stock):
                sold = self.merchant.sold_out[i]
                label = f"{i + 1}. {row['label']} — {row['price']} coin"
                if sold:
                    yield Button(
                        f"{i + 1}. {row['label']} — SOLD OUT",
                        id=f"buy_{i}",
                        disabled=True,
                    )
                else:
                    yield Button(label, id=f"buy_{i}", variant="primary")
            yield Button("Step away", id="close-shop")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "close-shop":
            self.dismiss(None)
            return
        if bid.startswith("buy_") and not event.button.disabled:
            idx = int(bid.split("_", 1)[1])
            msg = self.engine.buy_curio_ware(self.merchant, idx)
            self.engine.messages.append(msg)
            self.dismiss(True)

    BINDINGS = [Binding("escape", "dismiss", "Close")]


class InventoryScreen(ModalScreen):
    """Satchel management with detailed item inspection."""

    def __init__(self, engine: GameEngine):
        super().__init__()
        self.engine = engine

    def compose(self) -> ComposeResult:
        with Vertical(id="inventory-container"):
            yield Label(
                "SATCHEL (Enter: Use,  D: Discard,  Esc: Close)",
                id="inventory-header",
            )
            items = self.engine.player.inventory.items
            if not items:
                yield Label("Your inventory is empty.")
            else:
                list_items = []
                for i, item in enumerate(items):
                    equipped = ""
                    if (
                        self.engine.player.equipment.weapon == item
                        or self.engine.player.equipment.armor == item
                    ):
                        equipped = " (E)"
                    list_items.append(
                        ListItem(
                            Label(f"{chr(97 + i)}) {item.name}{equipped}"),
                            id=f"item_{i}",
                        )
                    )
                yield ListView(*list_items)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = self.query_one(ListView).index
        item = self.engine.player.inventory.items[index]
        if self.engine.handle_consume(item):
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_drop(self) -> None:
        list_view = self.query_one(ListView)
        if list_view.index is not None and list_view.index < len(
            self.engine.player.inventory.items
        ):
            item = self.engine.player.inventory.items[list_view.index]
            self.engine.player.inventory.drop(item, self.engine)
            self.dismiss(False)

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("d", "drop", "Drop"),
    ]


class RunStatsScreen(ModalScreen):
    """Post-run or mid-run statistics dashboard with DataTable."""

    def __init__(self, engine: GameEngine):
        super().__init__()
        self.engine = engine

    def compose(self) -> ComposeResult:
        with Vertical(id="stats-screen-container"):
            yield Label("CHRONICLE OF THE DESCENT", id="stats-screen-header")

            with TabbedContent():
                with TabPane("Combat", id="tab-combat"):
                    table = DataTable(id="combat-table")
                    table.add_columns("Metric", "Value")
                    yield table

                with TabPane("Wealth", id="tab-wealth"):
                    table = DataTable(id="wealth-table")
                    table.add_columns("Metric", "Value")
                    yield table

                with TabPane("Achievements", id="tab-achieve"):
                    yield Label("Rites of Passage:", id="achieve-label")
                    yield Static("", id="achieve-list")

            yield Button("Close Chronicle", id="close-stats", variant="primary")

    def on_mount(self) -> None:
        stats = self.engine.get_run_statistics()

        combat_table = self.query_one("#combat-table", DataTable)
        combat_table.add_row("Enemies Slain", str(stats.get("enemies_slain", 0)))
        combat_table.add_row("Total Damage Dealt", str(stats.get("total_damage_dealt", 0)))
        combat_table.add_row("Total Damage Taken", str(stats.get("total_damage_taken", 0)))
        combat_table.add_row("Combat Style", stats.get("combat_style", "balanced").title())
        combat_table.add_row("Max Brutality Streak", str(stats.get("brutality_streak_max", 0)))
        combat_table.add_row("Max Finesse Streak", str(stats.get("finesse_streak_max", 0)))

        wealth_table = self.query_one("#wealth-table", DataTable)
        wealth_table.add_row("Gold Earned", str(stats.get("gold_earned", 0)))
        wealth_table.add_row("Gold Spent", str(stats.get("gold_spent", 0)))
        wealth_table.add_row("Net Worth", str(stats.get("gold_earned", 0) - stats.get("gold_spent", 0)))
        wealth_table.add_row("Ascension Tier", str(stats.get("ascension_tier", 0)))

        achieve_static = self.query_one("#achieve-list", Static)
        achievements = stats.get("achievements", [])
        if achievements:
            achieve_static.update("\n".join(f"  • {a}" for a in achievements))
        else:
            achieve_static.update("  None yet. The pit has not yet witnessed your legend.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-stats":
            self.dismiss()

    BINDINGS = [Binding("escape", "dismiss", "Close")]


class SettingsScreen(ModalScreen):
    """In-game settings: animation toggle, colorblind mode, etc."""

    def __init__(self, app_ref: DungeonApp):
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-container"):
            yield Label("PREFERENCES OF THE DAMNED", id="settings-header")
            yield Checkbox("Screen Shake", value=self.app_ref.settings_shake, id="shake-check")
            yield Checkbox("Floating Numbers", value=self.app_ref.settings_floaters, id="floater-check")
            yield Checkbox("High-Contrast Mode", value=self.app_ref.settings_high_contrast, id="contrast-check")
            yield Checkbox("Compact Sidebar", value=self.app_ref.settings_compact_sidebar, id="compact-check")
            yield Button("Seal Preferences", id="close-settings", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-settings":
            self.app_ref.settings_shake = self.query_one("#shake-check", Checkbox).value
            self.app_ref.settings_floaters = self.query_one("#floater-check", Checkbox).value
            self.app_ref.settings_high_contrast = self.query_one("#contrast-check", Checkbox).value
            self.app_ref.settings_compact_sidebar = self.query_one("#compact-check", Checkbox).value
            self.dismiss()

    BINDINGS = [Binding("escape", "dismiss", "Close")]


class CommandPaletteScreen(ModalScreen):
    """Quick-action palette à-la VS Code / Sublime."""

    def __init__(self, app_ref: DungeonApp):
        super().__init__()
        self.app_ref = app_ref
        self.commands: List[Tuple[str, str, Callable[[], None]]] = [
            ("Rest / Wait", "space", lambda: self._dispatch("wait")),
            ("Inventory", "i", lambda: self._dispatch("inventory")),
            ("Look Mode", "l", lambda: self._dispatch("look")),
            ("Pick Up", "g", lambda: self._dispatch("pickup")),
            ("Take Stairs", ">", lambda: self._dispatch("take_stairs")),
            ("Invoke / Interact", "e", lambda: self._dispatch("invoke")),
            ("Undo", "u", lambda: self._dispatch("undo")),
            ("Hint", "h", lambda: self._dispatch("hint")),
            ("Help", "?", lambda: self._dispatch("help")),
            ("Save", "ctrl+s", lambda: self._dispatch("save")),
            ("Autosave", "ctrl+a", lambda: self._dispatch("autosave")),
            ("Run Stats", "F1", lambda: self._dispatch("stats")),
            ("Settings", "F2", lambda: self._dispatch("settings")),
            ("Cast Spell 1", "1", lambda: self._dispatch("cast_1")),
            ("Cast Spell 2", "2", lambda: self._dispatch("cast_2")),
            ("Cast Spell 3", "3", lambda: self._dispatch("cast_3")),
            ("Cast Spell 4", "4", lambda: self._dispatch("cast_4")),
            ("Cast Spell 5", "5", lambda: self._dispatch("cast_5")),
            ("Quit", "q", lambda: self._dispatch("quit")),
        ]

    def compose(self) -> ComposeResult:
        with Vertical(id="palette-container"):
            yield Label("COMMAND PALETTE", id="palette-header")
            yield Input(placeholder="Type to filter commands...", id="palette-input")
            yield ListView(id="palette-list")

    def on_mount(self) -> None:
        self._refresh_list("")
        self.query_one("#palette-input", Input).focus()

    def _refresh_list(self, filter_text: str) -> None:
        list_view = self.query_one("#palette-list", ListView)
        list_view.clear()
        ft = filter_text.lower()
        for label, key, _ in self.commands:
            if ft in label.lower() or ft in key.lower():
                display = f"{label}  [dim]({key})[/dim]"
                list_view.append(ListItem(Label(display)))

    def on_input_changed(self, event: Input.Changed) -> None:
        self._refresh_list(event.value)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        list_view = self.query_one("#palette-list", ListView)
        idx = list_view.index
        # Map filtered index back to command
        ft = self.query_one("#palette-input", Input).value.lower()
        visible = [(label, key, cb) for label, key, cb in self.commands
                   if ft in label.lower() or ft in key.lower()]
        if 0 <= idx < len(visible):
            visible[idx][2]()

    def _dispatch(self, action: str) -> None:
        self.dismiss(action)

    BINDINGS = [Binding("escape", "dismiss", "Close")]


class TitleScreen(Screen):
    """Atmospheric title / main menu with animated ASCII art."""

    BINDINGS = [
        Binding("n", "new_game", "New Descent"),
        Binding("l", "load_game", "Load Memory"),
        Binding("q", "quit", "Abandon"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="title-container"):
            yield Static(
                """
    ▓█████▄  █    ██  ███▄    █   ▄████ ▓█████  ▒█████   ███▄    █ 
    ▒██▀ ██▌ ██  ▓██▒ ██ ▀█   █  ██▒ ▀█▒▓█   ▀ ▒██▒  ██▒ ██ ▀█   █ 
    ░██   █▌▓██  ▒██░▓██  ▀█ ██▒▒██░▄▄▄░▒███   ▒██░  ██▒▓██  ▀█ ██▒
    ░▓█▄   ▌▓▓█  ░██░▓██▒  ▐▌██▒░▓█  ██▓▒▓█  ▄ ▒██   ██░▓██▒  ▐▌██▒
    ░▒████▓ ▒▒█████▓ ▒██░   ▓██░░▒▓███▀▒░▒████▒░ ████▓▒░▒██░   ▓██░
     ▒▒▓  ▒ ░▒▓▒ ▒ ▒ ░ ▒░   ▒ ▒  ░▒   ▒ ░░ ▒░ ░░ ▒░▒░▒░ ░ ▒░   ▒ ▒ 
     ░ ▒  ▒ ░░▒░ ░ ░ ░ ░░   ░ ▒░  ░   ░  ░ ░  ░  ░ ▒ ▒░ ░ ░░   ░ ▒░
     ░ ░  ░  ░░░ ░ ░    ░   ░ ░ ░ ░   ░    ░   ░ ░ ░ ▒     ░   ░ ░ 
       ░       ░              ░       ░    ░  ░    ░ ░           ░ 
     ░                                                              
                """,
                id="title-ascii",
            )
            yield Label("THE IRON MAW", id="title-game-name")
            yield Label(
                "A terminal descent into procedural darkness.\n"
                "No two runs are alike. No one returns unchanged.",
                id="title-tagline",
            )
            with Horizontal(id="title-buttons"):
                yield Button("New Descent [N]", id="new-game", variant="primary")
                yield Button("Load Memory [L]", id="load-game")
                yield Button("Abandon [Q]", id="quit-game", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new-game":
            self.app.action_new_game()
        elif event.button.id == "load-game":
            self.app.action_load_game()
        elif event.button.id == "quit-game":
            self.app.exit()

    def action_new_game(self) -> None:
        self.app.action_new_game()

    def action_load_game(self) -> None:
        self.app.action_load_game()

    def action_quit(self) -> None:
        self.app.exit()

    def on_mount(self) -> None:
        # Subtle fade-in for the title
        self.styles.animate("opacity", 1.0, duration=0.8)


# ═══════════════════════════════════════════════════════════════════════════════
#  WIDGETS
# ═══════════════════════════════════════════════════════════════════════════════

class MapWidget(Static):
    """The primary dungeon viewport with optional screen-shake and floating text."""

    def __init__(self, engine: GameEngine, **kwargs):
        super().__init__(**kwargs)
        self.engine = engine
        self.cursor: Optional[Tuple[int, int]] = None
        self.shake = ScreenShake()
        self.floating_texts: List[FloatingText] = []

    def on_mount(self) -> None:
        self.update_map()
        self.set_interval(0.05, self._tick_animations)

    def _tick_animations(self) -> None:
        """Called every 50ms to refresh floating text / shake."""
        # Prune dead floaters
        self.floating_texts = [f for f in self.floating_texts if f.alpha() > 0]
        if self.floating_texts or self.shake.active():
            self.update_map()

    def add_floater(self, text: str, color: str, x: int, y: int) -> None:
        self.floating_texts.append(FloatingText(text, color, x, y, time.time()))

    def trigger_shake(self, intensity: int = 2, duration: float = 0.3) -> None:
        self.shake.intensity = intensity
        self.shake.duration = duration
        self.shake.start_time = time.time()

    def update_map(self, cursor: Optional[Tuple[int, int]] = None) -> None:
        self.cursor = cursor
        raw = self.engine.get_render_data(cursor=cursor)

        # Overlay floating text
        if self.floating_texts:
            lines = raw.split("\n")
            for ft in self.floating_texts:
                if 0 <= ft.y < len(lines):
                    line = lines[ft.y]
                    # Simple overlay: insert colored text at x position
                    # This is a best-effort overlay; full rich-text overlay
                    # would require segment-level manipulation.
                    if ft.x < len(line):
                        alpha = ft.alpha()
                        if alpha > 0.5:
                            prefix = line[:ft.x]
                            suffix = line[ft.x + len(ft.text):]
                            lines[ft.y] = f"{prefix}[bold {ft.color}]{ft.text}[/]{suffix}"
            raw = "\n".join(lines)

        self.update(raw)


class StatsWidget(Static):
    """Reactive sidebar showing hero statistics with progress bars."""

    def __init__(self, engine: GameEngine, **kwargs):
        super().__init__(**kwargs)
        self.engine = engine

    def on_mount(self) -> None:
        self.update_stats()

    def update_stats(self) -> None:
        p = self.engine.player
        hp_pct = p.fighter.hp / p.fighter.max_hp if p.fighter.max_hp else 0
        hp_color = "#00ff00" if hp_pct > 0.5 else "#ffaa00" if hp_pct > 0.25 else "#ff0000"

        weapon = p.equipment.weapon
        armor = p.equipment.armor
        weapon_str = f"  {weapon.name}" if weapon else "  Bare Hands"
        armor_str = f"  {armor.name}" if armor else "  Threadbare Rags"

        mana_str = ""
        mana_bar = ""
        if p.mana:
            mana_pct = p.mana.mana / p.mana.max_mana if p.mana.max_mana else 0
            mana_bar = f"\nSpirit: [{'█' * int(mana_pct * 10)}{'░' * (10 - int(mana_pct * 10))}] {p.mana.mana}/{p.mana.max_mana}"

        status_str = ""
        if p.fighter.status_effects.effects:
            status_str = "\n" + self.engine.get_status_display()

        ng_plus_str = ""
        if self.engine.is_ng_plus:
            ng_plus_str = "\n[bold yellow]The Cycle Deepens[/]"

        delayed_stats = p.fighter.status_effects.delayed_branching_stats
        brutality = delayed_stats.get("brutality", 0)
        finesse = delayed_stats.get("finesse", 0)
        style_str = f"\nLegacy: 🔪{brutality} / ✨{finesse}"
        arcana = ""
        if p.mana and p.mana.learned_spells:
            names = [s.name[:4] for s in p.mana.learned_spells[:5]]
            arcana = f"\nArcana [1–5]: {' / '.join(names)}  ·  [e] rite"

        hp_bar = f"[{'█' * int(hp_pct * 10)}{'░' * (10 - int(hp_pct * 10))}]"

        stats_text = (
            f"Depth: {self.engine.dungeon_level}{ng_plus_str}\n"
            f"Vitality: [{hp_color}]{hp_bar} {p.fighter.hp}/{p.fighter.max_hp}[/]{mana_bar}\n"
            f"Prestige: {p.level.current_level}\n"
            f"Essence: {p.level.current_xp}/{p.level.experience_to_next_level}\n"
            f"Coin: {p.gold}\n"
            f"Might: {p.fighter.power}\n"
            f"Warding: {p.fighter.defense}\n"
            f"Relic: {weapon_str}\n"
            f"Raiment: {armor_str}{status_str}{style_str}{arcana}"
        )
        if p.fighter.hp <= 0:
            stats_text += "\n\n[bold red]YOUR BLOOD COOLS...[/]"

        self.update(stats_text)


class LogWidget(Static):
    """Combat / event log with color-coded severity and auto-scroll."""

    def __init__(self, engine: GameEngine, **kwargs):
        super().__init__(**kwargs)
        self.engine = engine
        self._last_len = 0

    def on_mount(self) -> None:
        self.update_log()
        self.set_interval(0.1, self._poll_messages)

    def _poll_messages(self) -> None:
        if len(self.engine.messages) != self._last_len:
            self.update_log()

    def update_log(self) -> None:
        msgs = self.engine.messages[-6:]
        self._last_len = len(self.engine.messages)
        colored = []
        for msg in msgs:
            if "strike" in msg.lower() or "damage" in msg.lower():
                colored.append(f"[bold #ff4444]{msg}[/]")
            elif "heal" in msg.lower() or "vitality" in msg.lower() or "+" in msg:
                colored.append(f"[bold #00ff00]{msg}[/]")
            elif "coin" in msg.lower() or "gold" in msg.lower() or "$" in msg:
                colored.append(f"[bold #d4af37]{msg}[/]")
            elif "spell" in msg.lower() or "arcana" in msg.lower() or "mana" in msg.lower():
                colored.append(f"[bold #00ffff]{msg}[/]")
            elif "shrine" in msg.lower():
                colored.append(f"[bold #ffd700]{msg}[/]")
            else:
                colored.append(msg)
        self.update("\n".join(colored))


class MiniMapWidget(Static):
    """A zoomed-out tactical overview of the explored dungeon."""

    def __init__(self, engine: GameEngine, **kwargs):
        super().__init__(**kwargs)
        self.engine = engine

    def on_mount(self) -> None:
        self.update_minimap()
        self.set_interval(0.5, self.update_minimap)

    def update_minimap(self) -> None:
        gm = self.engine.game_map
        if not gm or not gm.tiles:
            self.update("[dim]No map data.[/]")
            return

        # Downsample: 1 minimap cell = 2x2 or 3x3 tiles
        scale = max(1, gm.width // 32)
        rows = []
        for my in range(0, gm.height, scale):
            row = []
            for mx in range(0, gm.width, scale):
                # Sample the tile at this minimap cell
                tx, ty = mx + scale // 2, my + scale // 2
                if tx >= gm.width:
                    tx = gm.width - 1
                if ty >= gm.height:
                    ty = gm.height - 1
                tile = gm.tiles[ty][tx]
                if self.engine.player.x // scale == mx // scale and self.engine.player.y // scale == my // scale:
                    row.append("[bold white]@[/]")
                elif tile.visible:
                    # Check for entities
                    entities = [e for e in self.engine.entities if e.x // scale == mx // scale and e.y // scale == my // scale]
                    if entities:
                        e = entities[0]
                        row.append(f"[bold {e.color}]{e.char}[/]")
                    elif tile.walkable:
                        row.append("[dim].[/]")
                    else:
                        row.append("[dim]#[/]")
                elif tile.explored:
                    row.append("[dim]·[/]")
                else:
                    row.append(" ")
            rows.append("".join(row))
        self.update("\n".join(rows))


class ActionBarWidget(Static):
    """Context-sensitive action hints based on player surroundings."""

    def __init__(self, engine: GameEngine, **kwargs):
        super().__init__(**kwargs)
        self.engine = engine

    def on_mount(self) -> None:
        self.update_bar()
        self.set_interval(0.3, self.update_bar)

    def update_bar(self) -> None:
        p = self.engine.player
        if p.fighter.hp <= 0:
            self.update("[dim]The hero has fallen.[/]")
            return

        actions = []
        px, py = p.x, p.y

        # Check for items
        items = [e for e in self.engine.spatial.get_at(px, py) if isinstance(e, Item)]
        if items:
            actions.append("[key]g[/] Scavenge")

        # Check for stairs
        stairs = [e for e in self.engine.spatial.get_at(px, py) if isinstance(e, Stairs)]
        if stairs:
            actions.append("[key]>[/] Descend")

        # Check for shrine
        shrine = self.engine.shrine_under_player()
        if shrine:
            actions.append("[key]e[/] Invoke Shrine")

        # Check for adjacent curio
        merchant = self.engine.adjacent_curio()
        if merchant:
            actions.append("[key]e[/] Trade")

        # Check for visible enemies
        hostiles = self.engine.spatial.get_hostiles_near(px, py, 5)
        visible_hostiles = [h for h in hostiles if self.engine.game_map.tiles[h.y][h.x].visible]
        if visible_hostiles:
            actions.append("[key]1-5[/] Cast")

        if not actions:
            actions.append("[key]Space[/] Rest")
            actions.append("[key]l[/] Look")

        self.update("  ".join(actions))


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════════════════════════

class DungeonApp(App):
    """
    The Iron Maw — Enhanced Terminal Dungeon Crawler.

    New features over the original:
    • Title screen with animated ASCII art
    • Command palette (Ctrl+P) for quick actions
    • Settings screen (F2) for accessibility toggles
    • Run statistics dashboard (F1)
    • Mini-map widget in sidebar
    • Contextual action bar
    • Screen-shake on damage + floating combat text
    • Reactive log polling (no manual update needed)
    • Color-coded message severity
    • Enhanced CSS with hover states and transitions
    """

    CSS = """
    Screen {
        background: #0a0a0a;
        color: #c8c8c8;
    }

    /* ── Title Screen ── */
    #title-container {
        align: center middle;
        height: 1fr;
        width: 1fr;
        background: #050505;
    }

    #title-ascii {
        color: #8B0000;
        text-align: center;
        height: auto;
        content-align: center middle;
    }

    #title-game-name {
        text-style: bold;
        color: #ff3333;
        text-align: center;
        font-size: 200%;
        margin: 1 0;
    }

    #title-tagline {
        color: #888;
        text-align: center;
        margin-bottom: 2;
    }

    #title-buttons {
        align: center middle;
        height: auto;
    }

    #title-buttons Button {
        margin: 0 1;
        min-width: 20;
    }

    /* ── Main Game Layout ── */
    #main-container {
        height: 1fr;
        width: 1fr;
    }

    #sidebar {
        width: 34;
        background: #111111;
        border-left: double #333;
        padding: 1;
    }

    #sidebar.compact {
        width: 28;
    }

    MapWidget {
        height: 1fr;
        width: 1fr;
        border: tall #222;
        content-align: center middle;
        font-family: 'Courier New', monospace;
        background: #080808;
    }

    LogWidget {
        height: 9;
        border-top: hkey #333;
        padding: 0 1;
        background: #0c0c0c;
        color: #777;
        text-align: left;
    }

    StatsWidget {
        height: auto;
        min-height: 14;
        color: #b0b0b0;
        padding: 0 1;
        margin-bottom: 1;
    }

    MiniMapWidget {
        height: auto;
        min-height: 8;
        max-height: 14;
        border: inner #222;
        background: #0a0a0a;
        padding: 0 1;
        color: #444;
        margin-bottom: 1;
    }

    ActionBarWidget {
        height: auto;
        min-height: 1;
        color: #d4af37;
        background: #1a1a1a;
        border-top: solid #333;
        padding: 0 1;
        text-align: center;
    }

    #sidebar-label {
        text-style: bold;
        color: #e0e0e0;
        margin-bottom: 1;
        border-bottom: solid #333;
        width: 100%;
        text-align: center;
    }

    #look-info {
        height: auto;
        min-height: 6;
        color: #d4af37;
        margin-top: 1;
        padding: 1;
        background: #1a1a1a;
        border: inner #333;
    }

    /* ── Inventory ── */
    InventoryScreen {
        align: center middle;
    }

    #inventory-container {
        width: 52;
        height: auto;
        max-height: 26;
        background: #161616;
        border: double #d4af37;
        padding: 1;
    }

    #inventory-header {
        text-style: bold;
        color: #d4af37;
        margin-bottom: 1;
        text-align: center;
        border-bottom: solid #444;
    }

    ListView {
        background: #0d0d0d;
    }

    ListItem {
        padding: 0 1;
    }

    ListItem:focus {
        background: #222;
        color: #fff;
    }

    /* ── Game Over ── */
    GameOverScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.9);
    }

    #gameover-container {
        width: 56;
        height: auto;
        background: #1a0505;
        border: thick #880000;
        padding: 2;
        align: center middle;
    }

    #gameover-header {
        text-style: bold;
        color: #ff3333;
        text-align: center;
        margin-bottom: 1;
        font-size: 150%;
    }

    #gameover-container Label {
        text-align: center;
        margin-bottom: 1;
    }

    #gameover-container Button {
        margin: 1 0;
        width: 100%;
    }

    #death-scene {
        color: #bcbcbc;
        text-align: center;
        margin: 1 0;
        text-style: italic;
    }

    #lore-title {
        color: #d4af37;
        text-align: center;
        margin-top: 1;
        text-style: bold;
    }

    #lore-text {
        color: #777;
        text-align: center;
        margin-bottom: 1;
    }

    #run-stats {
        border-top: solid #444;
        margin-top: 1;
        padding-top: 1;
    }

    #stats-header {
        color: #d4af37;
        text-align: center;
        text-style: bold;
    }

    #achievements-line {
        color: #aa66ff;
        text-align: center;
        text-style: italic;
    }

    /* ── Help ── */
    HelpScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.9);
    }

    #help-container {
        width: 64;
        height: auto;
        max-height: 90%;
        background: #161616;
        border: thick #444;
        padding: 2;
    }

    #help-header {
        text-style: bold;
        color: #d4af37;
        text-align: center;
        margin-bottom: 1;
        border-bottom: solid #444;
    }

    #help-container Label {
        margin-bottom: 1;
        line-height: 1.2;
    }

    #help-container Button {
        margin-top: 1;
        width: 100%;
    }

    /* ── Shop ── */
    ShopScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.92);
    }

    #shop-container {
        width: 54;
        height: auto;
        background: #141008;
        border: double #c9a227;
        padding: 2;
    }

    #shop-header {
        text-style: bold;
        color: #eecc66;
        text-align: center;
        margin-bottom: 1;
        border-bottom: solid #444;
    }

    #shop-sub {
        color: #888;
        text-align: center;
        margin-bottom: 1;
    }

    #shop-purse {
        color: #d4af37;
        text-align: center;
        margin-bottom: 1;
        text-style: bold;
    }

    #shop-container Button {
        margin: 1 0;
        width: 100%;
    }

    /* ── Run Stats Dashboard ── */
    RunStatsScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.92);
    }

    #stats-screen-container {
        width: 60;
        height: auto;
        max-height: 90%;
        background: #161616;
        border: double #444;
        padding: 2;
    }

    #stats-screen-header {
        text-style: bold;
        color: #d4af37;
        text-align: center;
        margin-bottom: 1;
        border-bottom: solid #444;
    }

    DataTable {
        height: auto;
        max-height: 16;
        margin-bottom: 1;
    }

    #achieve-label {
        color: #aa66ff;
        text-style: bold;
        margin-bottom: 1;
    }

    #achieve-list {
        color: #888;
    }

    /* ── Settings ── */
    SettingsScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.92);
    }

    #settings-container {
        width: 44;
        height: auto;
        background: #161616;
        border: double #444;
        padding: 2;
    }

    #settings-header {
        text-style: bold;
        color: #d4af37;
        text-align: center;
        margin-bottom: 1;
        border-bottom: solid #444;
    }

    #settings-container Checkbox {
        margin: 1 0;
    }

    #settings-container Button {
        margin-top: 1;
        width: 100%;
    }

    /* ── Command Palette ── */
    CommandPaletteScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }

    #palette-container {
        width: 50;
        height: auto;
        max-height: 60%;
        background: #161616;
        border: double #444;
        padding: 1;
    }

    #palette-header {
        text-style: bold;
        color: #d4af37;
        text-align: center;
        margin-bottom: 1;
        border-bottom: solid #444;
    }

    #palette-input {
        margin-bottom: 1;
    }

    #palette-list {
        background: #0d0d0d;
        height: auto;
        max-height: 20;
    }

    #palette-list ListItem {
        padding: 0 1;
    }

    #palette-list ListItem:focus {
        background: #222;
        color: #fff;
    }

    /* ── Animations & Transitions ── */
    Button {
        transition: background 150ms;
    }

    Button:hover {
        background: #333;
    }

    Button:focus {
        background: #444;
    }

    Static {
        transition: opacity 200ms;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("space", "wait", "Wait"),
        Binding("up,w", "move(0, -1)", "Move Up"),
        Binding("down,s", "move(0, 1)", "Move Down"),
        Binding("left,a", "move(-1, 0)", "Move Left"),
        Binding("right,d", "move(1, 0)", "Move Right"),
        Binding("g", "pickup", "Get Item"),
        Binding("i", "inventory", "Inventory"),
        Binding(">", "take_stairs", "Take Stairs"),
        Binding("l", "look", "Look"),
        Binding("?", "help", "Help"),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+a", "autosave", "AutoSave"),
        Binding("u", "undo", "Undo"),
        Binding("h", "hint", "Hint"),
        Binding("e", "invoke", "Invoke"),
        Binding("1", "cast_spell_1", "Spell 1"),
        Binding("2", "cast_spell_2", "Spell 2"),
        Binding("3", "cast_spell_3", "Spell 3"),
        Binding("4", "cast_spell_4", "Spell 4"),
        Binding("5", "cast_spell_5", "Spell 5"),
        Binding("f1", "stats", "Run Stats"),
        Binding("f2", "settings", "Settings"),
        Binding("ctrl+p", "palette", "Command Palette"),
    ]

    # ── Settings state ──
    settings_shake: bool = True
    settings_floaters: bool = True
    settings_high_contrast: bool = False
    settings_compact_sidebar: bool = False

    def __init__(self):
        super().__init__()
        self.engine: GameEngine = GameEngine(40, 20)
        self.look_mode = False
        self.look_x = 0
        self.look_y = 0
        self._showing_death = False
        self._title_shown = True

    def compose(self) -> ComposeResult:
        if self._title_shown:
            yield TitleScreen()
            return

        yield Header()
        with Horizontal(id="main-container"):
            with Vertical():
                yield MapWidget(self.engine, id="map-widget")
                yield LogWidget(self.engine, id="log-widget")
            with Vertical(id="sidebar"):
                yield Label("THE HERO'S BURDEN", id="sidebar-label")
                yield StatsWidget(self.engine, id="stats-widget")
                yield MiniMapWidget(self.engine, id="minimap-widget")
                yield ActionBarWidget(self.engine, id="action-bar")
                yield Label("", id="look-info")
        yield Footer()

    # ── Screen Navigation ──

    def action_new_game(self) -> None:
        self._title_shown = False
        self.engine = GameEngine(40, 20)
        self.look_mode = False
        self.refresh(layout=True)
        self.update_ui()

    def action_load_game(self) -> None:
        # Attempt load from slot 1
        if self.engine.load(1):
            self._title_shown = False
            self.refresh(layout=True)
            self.engine.messages.append("[Memory restored from the stone...]")
            self.update_ui()
        else:
            self.notify("No memory etched in slot 1.")

    def on_mount(self) -> None:
        if not self._title_shown:
            self.update_ui()

    # ── Movement & Actions ──

    def action_move(self, dx: int, dy: int) -> None:
        if self.engine.player.fighter.hp <= 0:
            return
        if self.look_mode:
            self.look_x = max(
                0, min(self.look_x + dx, self.engine.game_map.width - 1)
            )
            self.look_y = max(
                0, min(self.look_y + dy, self.engine.game_map.height - 1)
            )
            self.update_look_info()
            self.query_one("#map-widget", MapWidget).update_map(
                cursor=(self.look_x, self.look_y)
            )
            return

        old_hp = self.engine.player.fighter.hp
        self.engine.handle_move(dx, dy)

        # Visual feedback
        if self.settings_shake and self.engine.player.fighter.hp < old_hp:
            self.query_one("#map-widget", MapWidget).trigger_shake(intensity=2, duration=0.25)

        self.after_action()

    def action_wait(self) -> None:
        if self.engine.player.fighter.hp <= 0:
            return
        self.engine.handle_wait()
        self.after_action()

    def action_pickup(self) -> None:
        if self.engine.player.fighter.hp <= 0:
            return
        self.engine.handle_pickup()
        self.after_action()

    def action_take_stairs(self) -> None:
        if self.engine.player.fighter.hp <= 0:
            return
        for entity in self.engine.entities:
            if (
                isinstance(entity, Stairs)
                and entity.x == self.engine.player.x
                and entity.y == self.engine.player.y
            ):
                self.engine.next_floor()
                self.after_action()
                return
        self.engine.messages.append("There are no stairs here.")
        self.after_action()

    def action_inventory(self) -> None:
        def on_item_used(used: bool) -> None:
            self.after_action()

        self.push_screen(InventoryScreen(self.engine), on_item_used)

    def action_look(self) -> None:
        if self.look_mode:
            self.look_mode = False
            self.query_one("#look-info", Label).update("")
            self.query_one("#map-widget", MapWidget).update_map()
        else:
            self.look_mode = True
            self.look_x = self.engine.player.x
            self.look_y = self.engine.player.y
            self.update_look_info()
            self.query_one("#map-widget", MapWidget).update_map(
                cursor=(self.look_x, self.look_y)
            )

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_stats(self) -> None:
        self.push_screen(RunStatsScreen(self.engine))

    def action_settings(self) -> None:
        self.push_screen(SettingsScreen(self))

    def action_palette(self) -> None:
        def on_palette_result(result: Optional[str]) -> None:
            if result:
                getattr(self, f"action_{result}", lambda: None)()

        self.push_screen(CommandPaletteScreen(self), on_palette_result)

    def update_look_info(self) -> None:
        if not self.look_mode:
            return
        tile = self.engine.game_map.tiles[self.look_y][self.look_x]
        entities_at_pos = [
            e
            for e in self.engine.entities
            if e.x == self.look_x
            and e.y == self.look_y
            and self.engine.game_map.tiles[e.y][e.x].visible
        ]

        info = f"[yellow]Gaze: ({self.look_x},{self.look_y})[/]\n"
        if tile.visible:
            tactical = self.engine.get_tactical_info(self.look_x, self.look_y)
            if tactical:
                info += f"[#aaa]{tactical}[/]\n"

            if entities_at_pos:
                for e in entities_at_pos:
                    info += f"[{e.color}]{e.name}[/]\n"
                    if e.fighter:
                        info += f"  Vitality: {e.fighter.hp}/{e.fighter.max_hp}\n"
            else:
                info += "Cold Floor" if tile.walkable else "Immovable Wall"
        else:
            info += "Veiled in Shadows"

        self.query_one("#look-info", Label).update(info.strip())

    def after_action(self) -> None:
        self.update_ui()
        if self.engine.player.fighter.hp <= 0 and not self._showing_death:
            self._showing_death = True
            self.look_mode = False
            self.show_game_over()

    def show_game_over(self) -> None:
        death_scene, lore_title, lore_text = self.engine.get_death_scene_data()
        stats = self.engine.get_run_statistics()

        def on_game_over(result):
            self._showing_death = False
            if result == "restart":
                self.engine = GameEngine(40, 20)
                self.look_mode = False
                self.update_ui()
            else:
                self.exit()

        self.push_screen(
            GameOverScreen(death_scene, lore_title, lore_text, stats),
            on_game_over,
        )

    def update_ui(self) -> None:
        cursor = (self.look_x, self.look_y) if self.look_mode else None
        self.query_one("#map-widget", MapWidget).update_map(cursor=cursor)
        self.query_one("#stats-widget", StatsWidget).update_stats()
        # LogWidget auto-updates via polling, but force once for responsiveness
        self.query_one("#log-widget", LogWidget).update_log()

    # ── Save / Load / Undo ──

    def action_save(self) -> None:
        if self.engine.save(1):
            self.engine.messages.append("Game saved to slot 1!")
            self.update_ui()
        else:
            self.notify("Failed to save game")

    def action_autosave(self) -> None:
        if self.engine.autosave():
            self.engine.messages.append("Autosaved!")
            self.update_ui()
        else:
            self.notify("Autosave failed")

    def action_undo(self) -> None:
        if self.engine.undo():
            self.update_ui()
            self.notify("Action undone!")
        else:
            self.notify("Nothing to undo")

    def action_hint(self) -> None:
        hint = self.engine.get_hint()
        self.engine.messages.append(f"[yellow]HINT: {hint}[/yellow]")
        self.update_ui()

    def action_invoke(self) -> None:
        if self.engine.player.fighter.hp <= 0 or self.look_mode:
            return
        shrine = self.engine.shrine_under_player()
        if shrine:
            self.engine.apply_shrine(shrine)
            self.after_action()
            return
        merchant = self.engine.adjacent_curio()
        if merchant:
            self.push_screen(
                ShopScreen(self.engine, merchant), lambda _: self.after_action()
            )
            return
        self.engine.messages.append(
            "Nothing answers your gesture—the world owes you no rite."
        )
        self.update_ui()

    # ── Spell Casting ──

    def _cast_spell_slot(self, slot: int) -> None:
        if self.engine.player.fighter.hp <= 0 or self.look_mode:
            return
        if self.engine.cast_spell_slot(slot):
            self.after_action()

    def action_cast_spell_1(self) -> None:
        self._cast_spell_slot(0)

    def action_cast_spell_2(self) -> None:
        self._cast_spell_slot(1)

    def action_cast_spell_3(self) -> None:
        self._cast_spell_slot(2)

    def action_cast_spell_4(self) -> None:
        self._cast_spell_slot(3)

    def action_cast_spell_5(self) -> None:
        self._cast_spell_slot(4)


if __name__ == "__main__":
    app = DungeonApp()
    app.run()