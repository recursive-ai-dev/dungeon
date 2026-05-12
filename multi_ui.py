# Standard library imports
import asyncio

# Third-party imports
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.events import Key
from textual.screen import Screen, ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, Static

# Local imports
from .entities import Player
from .engine import GameEngine
from .network import GameState, MultiplayerClient, MultiplayerServer


class ConnectionScreen(Screen):
    def compose(self) -> ComposeResult:
        with Vertical(id="conn-container"):
            yield Label("LAN MULTIPLAYER", id="conn-header")
            yield Label("Choose an option:", id="conn-sub")
            yield Button("Host Game (Server)", id="host-btn", variant="primary")
            yield Button("Join Game", id="join-btn", variant="success")
            yield Label("", id="spacer")
            yield Button("Back", id="back-btn", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "host-btn":
            self.app.push_screen(HostSetupScreen())
        elif event.button.id == "join-btn":
            self.app.push_screen(JoinSetupScreen())
        elif event.button.id == "back-btn":
            self.app.pop_screen()


class HostSetupScreen(Screen):
    def compose(self) -> ComposeResult:
        with Vertical(id="host-container"):
            yield Label("HOST A GAME", id="host-header")
            yield Label("Enter your name:")
            yield Input(placeholder="Player name", id="name-input")
            yield Label("")
            yield Button("Start Server", id="start-host-btn", variant="primary")
            yield Button("Back", id="back-btn", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-host-btn":
            name = self.query_one("#name-input", Input).value or "Player"
            self.app.start_host(name)
        elif event.button.id == "back-btn":
            self.app.pop_screen()


class JoinSetupScreen(Screen):
    def compose(self) -> ComposeResult:
        with Vertical(id="join-container"):
            yield Label("JOIN A GAME", id="join-header")
            yield Label("Enter your name:")
            yield Input(placeholder="Player name", id="name-input")
            yield Label("")
            yield Label("Server address (e.g., 192.168.1.100:7777):")
            yield Input(placeholder="IP:Port", id="address-input")
            yield Label("")
            yield Button("Connect", id="connect-btn", variant="primary")
            yield Button("Back", id="back-btn", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "connect-btn":
            name = self.query_one("#name-input", Input).value or "Player"
            address = self.query_one("#address-input", Input).value
            if ":" in address:
                host, port = address.split(":")
                try:
                    port = int(port)
                    self.app.connect_to_server(host, port, name)
                except:
                    self.app.notify("Invalid port number")
            else:
                self.app.notify("Invalid address format")


class MultiplayerMapWidget(Static):
    def __init__(self, game_state: GameState, local_player_id: int, **kwargs):
        super().__init__(**kwargs)
        self.game_state = game_state
        self.local_player_id = local_player_id

    def update_state(self, game_state: GameState, local_player_id: int):
        self.game_state = game_state
        self.local_player_id = local_player_id
        self.refresh()

    def render(self) -> str:
        if not self.game_state:
            return "Waiting for game state..."
        
        lines = []
        player_map = {p["player_id"]: p for p in self.game_state.players}
        
        for y in range(len(self.game_state.map_data)):
            line = []
            for x in range(len(self.game_state.map_data[y])):
                tile = self.game_state.map_data[y][x]
                
                for p in self.game_state.players:
                    if p["x"] == x and p["y"] == y:
                        if p["player_id"] == self.local_player_id:
                            line.append("[yellow]@[/]")
                            break
                        else:
                            line.append(f"[{Player.player_colors[(p['player_id']-1) % len(Player.player_colors)]}]@[/]")
                            break
                else:
                    for e in self.game_state.entities:
                        if e["x"] == x and e["y"] == y and tile.get("visible"):
                            line.append(f"[{e['color']}]{e['char']}[/]")
                            break
                    else:
                        if tile.get("visible"):
                            line.append(f"[{tile['color']}]{tile['char']}[/]")
                        elif tile.get("explored"):
                            line.append(f"[#333]{tile['char']}[/]")
                        else:
                            line.append(" ")
            lines.append("".join(line))
        
        return "\n".join(lines)


class MultiplayerStatsWidget(Static):
    def __init__(self, game_state: GameState, local_player_id: int, **kwargs):
        super().__init__(**kwargs)
        self.game_state = game_state
        self.local_player_id = local_player_id

    def update_state(self, game_state: GameState, local_player_id: int):
        self.game_state = game_state
        self.local_player_id = local_player_id
        self.refresh()

    def render(self) -> str:
        if not self.game_state:
            return "Waiting..."
        
        player = None
        for p in self.game_state.players:
            if p["player_id"] == self.local_player_id:
                player = p
                break
        
        if not player:
            return "You are dead!"
        
        hp_color = "#00ff00" if player["hp"] > (player["max_hp"] / 2) else "#ff0000"
        
        return (
            f"Floor: {self.game_state.dungeon_level}\n"
            f"HP: [{hp_color}]{player['hp']}/{player['max_hp']}[/]\n"
            f"Level: {player['level']}\n"
            f"Gold: {player['gold']}\n"
            f"Power: {player['power']}\n"
            f"Defense: {player['defense']}\n"
            f"Weapon: {player.get('weapon') or 'None'}\n"
            f"Armor: {player.get('armor') or 'None'}"
        )


class MultiplayerLogWidget(Static):
    def __init__(self, messages: list, **kwargs):
        super().__init__(**kwargs)
        self.messages = messages

    def update_messages(self, messages: list):
        self.messages = messages
        self.refresh()

    def render(self) -> str:
        return "\n".join(self.messages[-5:])


class MultiplayerPlayersWidget(Static):
    def __init__(self, players: list, local_player_id: int, **kwargs):
        super().__init__(**kwargs)
        self.players = players
        self.local_player_id = local_player_id

    def update_players(self, players: list, local_player_id: int):
        self.players = players
        self.local_player_id = local_player_id
        self.refresh()

    def render(self) -> str:
        lines = ["[bold]Players[/]"]
        for p in self.players:
            is_you = "[yellow](You)[/]" if p["id"] == self.local_player_id else ""
            lines.append(f"  @{p['id']}: {p['name']} {is_you}")
        return "\n".join(lines)


class MultiplayerGameScreen(Screen):
    def __init__(self, engine: GameEngine, is_host: bool, server: MultiplayerServer = None, client: MultiplayerClient = None):
        super().__init__()
        self.engine = engine
        self.is_host = is_host
        self.server = server
        self.client = client
        self.local_player_id = 1 if is_host else None
        self.game_state = None
        self.players = [{"id": 1, "name": "Host"}] if is_host else []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            with Vertical():
                yield MultiplayerMapWidget(self.game_state, self.local_player_id, id="map-widget")
                yield MultiplayerLogWidget([], id="log-widget")
            with Vertical(id="sidebar"):
                yield Label("PLAYER INFO", id="sidebar-label")
                yield MultiplayerStatsWidget(self.game_state, self.local_player_id, id="stats-widget")
                yield Label("", id="players-label")
                yield MultiplayerPlayersWidget(self.players, self.local_player_id, id="players-widget")

    async def on_mount(self) -> None:
        if self.is_host:
            self.server.set_engine(self.engine)
            await self.server.start()
            asyncio.create_task(self._host_update_loop())
        else:
            self.client.on_state = self._on_state_received
            self.client.on_players = self._on_players_received
            self.client.on_error = self._on_error
            asyncio.create_task(self._client_receive_loop())

    async def _host_update_loop(self):
        while self.server.running:
            await asyncio.sleep(0.5)

    async def _client_receive_loop(self):
        while self.client.running:
            await asyncio.sleep(0.1)

    def _on_state_received(self, state: GameState):
        self.game_state = state
        self.local_player_id = self.client.player_id
        self.app.call_later(self._update_ui)

    def _on_players_received(self, players: list):
        self.players = players
        self.app.call_later(self._update_players)

    def _on_error(self, error: str):
        self.app.notify(error)

    def _update_ui(self):
        if self.game_state:
            self.query_one("#map-widget", MultiplayerMapWidget).update_state(self.game_state, self.local_player_id)
            self.query_one("#stats-widget", MultiplayerStatsWidget).update_state(self.game_state, self.local_player_id)
            self.query_one("#log-widget", MultiplayerLogWidget).update_messages(self.game_state.messages)

    def _update_players(self):
        self.query_one("#players-widget", MultiplayerPlayersWidget).update_players(self.players, self.local_player_id)

    def action_move(self, dx: int, dy: int) -> None:
        if self.is_host:
            self.engine.handle_move_player(self.engine.player, dx, dy)
            self._broadcast_state()
        else:
            asyncio.create_task(self.client.send_action("move", {"dx": dx, "dy": dy}))

    def action_wait(self) -> None:
        if self.is_host:
            self.engine.handle_wait()
            self._broadcast_state()
        else:
            asyncio.create_task(self.client.send_action("wait", {}))

    def action_pickup(self) -> None:
        if self.is_host:
            self.engine.handle_pickup_player(self.engine.player)
            self._broadcast_state()
        else:
            asyncio.create_task(self.client.send_action("pickup", {}))

    def action_take_stairs(self) -> None:
        if self.is_host:
            self.engine.handle_stairs_player(self.engine.player)
            self._broadcast_state()
        else:
            asyncio.create_task(self.client.send_action("take_stairs", {}))

    def _broadcast_state(self):
        if self.is_host:
            asyncio.create_task(self.server._broadcast_state())


class MultiplayerApp(App):
    CSS = """
    Screen { background: #1a1a1a; }
    #main-container { height: 1fr; width: 1fr; }
    #sidebar { width: 28; background: #262626; border-left: solid #444; padding: 1; }
    MultiplayerMapWidget { height: 1fr; width: 1fr; border: heavy #444; content-align: center middle; font-family: monospace; color: #ddd; }
    MultiplayerLogWidget { height: 10; border-top: solid #444; padding: 1; background: #121212; color: #aaa; }
    MultiplayerStatsWidget { height: auto; color: #00ff00; }
    #sidebar-label { text-style: bold; color: #fff; margin-bottom: 1; }
    #players-widget { height: auto; margin-top: 1; color: #aaa; }
    #conn-container, #host-container, #join-container { width: 40; height: auto; align: center middle; background: #262626; border: thick #444; padding: 2; }
    #conn-header, #host-header, #join-header { text-style: bold; color: #fff; text-align: center; margin-bottom: 1; }
    Button { margin: 1 0; }
    #conn-sub { margin-bottom: 1; }
    #spacer { margin: 1; }
    Input { margin-bottom: 1; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("space", "wait", "Wait"),
        ("up,w", "move(0, -1)", "Up"),
        ("down,s", "move(0, 1)", "Down"),
        ("left,a", "move(-1, 0)", "Left"),
        ("right,d", "move(1, 0)", "Right"),
        ("g", "pickup", "Get"),
        (">", "take_stairs", "Stairs"),
    ]

    SCREENS = {
        "connection": ConnectionScreen,
        "host": HostSetupScreen,
        "join": JoinSetupScreen,
    }

    def __init__(self):
        super().__init__()
        self.server = None
        self.client = None
        self.game_screen = None

    def get_engine(self, is_host: bool, player_id: int = 1):
        return GameEngine(40, 20, is_host=is_host, local_player_id=player_id)

    def start_host(self, player_name: str):
        self.server = MultiplayerServer(7777)
        engine = GameEngine(40, 20, is_host=True, local_player_id=1)
        engine.player.name = player_name
        self.game_screen = MultiplayerGameScreen(engine, True, server=self.server)
        self.push_screen(self.game_screen)

    def connect_to_server(self, host: str, port: int, player_name: str):
        self.client = MultiplayerClient(host, port, player_name)
        
        async def do_connect():
            if await self.client.connect():
                engine = self.get_engine(False, 0)
                engine.player.name = player_name
                self.game_screen = MultiplayerGameScreen(engine, False, client=self.client)
                self.push_screen(self.game_screen)
            else:
                self.notify("Failed to connect")

        asyncio.create_task(do_connect())

    def on_mount(self) -> None:
        self.push_screen(ConnectionScreen())


def run_multiplayer():
    app = MultiplayerApp()
    app.run()