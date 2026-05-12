# Standard library imports
import asyncio
import json
import struct
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple, Any
from enum import Enum, auto
from collections import defaultdict, deque
import logging

# Third-party imports
# (none)

# Local imports
# (none)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class MessageType:
    """Message type constants for the multiplayer protocol."""
    JOIN = "join"
    LEAVE = "leave"
    STATE = "state"
    PLAYER_LIST = "player_list"
    ACTION = "action"
    CHAT = "chat"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"
    HEARTBEAT = "heartbeat"
    SERVER_INFO = "server_info"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    COMBAT = "combat"
    INVENTORY = "inventory"
    LEVEL_UP = "level_up"


class NetworkError(Exception):
    """Custom exception for network-related errors."""
    pass


class ProtocolError(NetworkError):
    """Raised when protocol violations are detected."""
    pass


def encode_message(msg_type: str, data: dict, msg_id: Optional[str] = None) -> bytes:
    """
    Encode a message into the wire format.
    
    Format: [4-byte length][JSON payload]
    
    Args:
        msg_type: Type of message being sent.
        data: Message payload dictionary.
        msg_id: Optional unique message identifier for request/response tracking.
    
    Returns:
        Bytes ready for socket transmission.
    """
    payload = {
        "type": msg_type,
        "data": data,
        "timestamp": time.time(),
    }
    if msg_id:
        payload["msg_id"] = msg_id
    
    json_str = json.dumps(payload, separators=(',', ':'))
    json_bytes = json_str.encode("utf-8")
    length = struct.pack("!I", len(json_bytes))
    return length + json_bytes


def decode_message(raw: bytes) -> Optional[Tuple[str, dict, Optional[str], float]]:
    """
    Decode a message from raw bytes.
    
    Args:
        raw: Raw bytes received from socket.
    
    Returns:
        Tuple of (msg_type, data, msg_id, timestamp) or None if invalid.
    """
    try:
        msg = json.loads(raw.decode("utf-8"))
        return (
            msg.get("type"),
            msg.get("data", {}),
            msg.get("msg_id"),
            msg.get("timestamp", 0.0)
        )
    except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
        return None


@dataclass
class PlayerSnapshot:
    """Snapshot of player state for network transmission."""
    player_id: int
    name: str
    x: int = 0
    y: int = 0
    hp: int = 100
    max_hp: int = 100
    level: int = 1
    xp: int = 0
    dungeon_level: int = 1
    alive: bool = True
    inventory_size: int = 0
    status_effects: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'PlayerSnapshot':
        return cls(**data)


@dataclass
class EntitySnapshot:
    """Snapshot of an entity (monster, item, etc.) for network transmission."""
    entity_id: str
    entity_type: str
    x: int
    y: int
    hp: int = 0
    max_hp: int = 0
    char: str = "?"
    color: str = "#FFFFFF"
    name: str = "Unknown"
    alive: bool = True
    hostile: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'EntitySnapshot':
        return cls(**data)


@dataclass
class GameState:
    """
    Complete game state snapshot for synchronization.
    
    Optimized for network transmission with delta compression support.
    """
    dungeon_level: int
    players: List[dict]
    entities: List[dict]
    map_data: List[List[dict]]
    messages: List[str]
    turn_count: int = 0
    game_time: float = 0.0
    seed: int = 0
    
    # For delta compression
    sequence_number: int = 0
    previous_sequence: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'GameState':
        return cls(**data)

    def compute_delta(self, previous: 'GameState') -> dict:
        """
        Compute a delta update from a previous state.
        Only includes fields that have changed.
        
        Args:
            previous: The previous game state to compare against.
        
        Returns:
            Dictionary with only changed fields.
        """
        delta = {
            "sequence_number": self.sequence_number,
            "previous_sequence": previous.sequence_number,
        }
        
        if self.dungeon_level != previous.dungeon_level:
            delta["dungeon_level"] = self.dungeon_level
        if self.turn_count != previous.turn_count:
            delta["turn_count"] = self.turn_count
        if self.messages != previous.messages:
            # Only send new messages
            delta["messages"] = self.messages[len(previous.messages):]
        if self.players != previous.players:
            delta["players"] = self.players
        if self.entities != previous.entities:
            delta["entities"] = self.entities
        
        return delta


class ConnectionStats:
    """Track network connection statistics."""
    
    def __init__(self):
        self.bytes_sent = 0
        self.bytes_received = 0
        self.messages_sent = 0
        self.messages_received = 0
        self.last_ping_time = 0.0
        self.latency_ms = 0.0
        self.connect_time = time.time()
        self.packets_lost = 0
        self.ping_history: deque = deque(maxlen=10)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.connect_time

    @property
    def average_latency(self) -> float:
        if not self.ping_history:
            return 0.0
        return sum(self.ping_history) / len(self.ping_history)

    def record_ping(self, latency: float):
        self.ping_history.append(latency)
        self.latency_ms = latency


class MultiplayerClient:
    """
    Enhanced multiplayer client with auto-reconnection, ping tracking,
    message queuing, and state delta compression.
    """

    def __init__(
        self,
        host: str,
        port: int,
        player_name: str = "Player",
        auto_reconnect: bool = True,
        reconnect_delay: float = 3.0,
        max_reconnect_attempts: int = 5
    ):
        self.host = host
        self.port = port
        self.player_name = player_name
        self.auto_reconnect = auto_reconnect
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.player_id: Optional[int] = None
        self.running = False
        self.connected = False
        
        # Callbacks
        self.on_state: Optional[Callable[[GameState], None]] = None
        self.on_players: Optional[Callable[[List[dict]], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_chat: Optional[Callable[[str, str], None]] = None
        self.on_connect: Optional[Callable[[], None]] = None
        self.on_disconnect: Optional[Callable[[], None]] = None
        self.on_player_joined: Optional[Callable[[dict], None]] = None
        self.on_player_left: Optional[Callable[[dict], None]] = None
        self.on_combat: Optional[Callable[[dict], None]] = None
        
        # State management
        self.stats = ConnectionStats()
        self._pending_messages: deque = deque()
        self._last_state: Optional[GameState] = None
        self._reconnect_attempts = 0
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._send_queue: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        """
        Connect to the multiplayer server.
        
        Returns:
            True if connection was successful.
        """
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0
            )
            
            # Send join message
            join_msg = encode_message(
                MessageType.JOIN,
                {
                    "name": self.player_name,
                    "version": "2.0",
                    "client_id": str(uuid.uuid4())
                }
            )
            self.writer.write(join_msg)
            await self.writer.drain()
            self.stats.bytes_sent += len(join_msg)
            self.stats.messages_sent += 1
            
            self.running = True
            self.connected = True
            self._reconnect_attempts = 0
            self.stats.connect_time = time.time()
            
            # Start background tasks
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._ping_task = asyncio.create_task(self._ping_loop())
            asyncio.create_task(self._send_loop())
            asyncio.create_task(self._receive_loop())
            
            if self.on_connect:
                try:
                    self.on_connect()
                except Exception as e:
                    logger.error(f"Connect callback error: {e}")
            
            logger.info(f"Connected to {self.host}:{self.port} as {self.player_name}")
            return True
            
        except Exception as e:
            error_msg = f"Connection failed: {e}"
            logger.error(error_msg)
            if self.on_error:
                self.on_error(error_msg)
            
            if self.auto_reconnect:
                asyncio.create_task(self._attempt_reconnect())
            return False

    async def _attempt_reconnect(self):
        """Attempt to reconnect with exponential backoff."""
        while (self.auto_reconnect and
               self._reconnect_attempts < self.max_reconnect_attempts and
               not self.connected):
            self._reconnect_attempts += 1
            delay = self.reconnect_delay * (1.5 ** (self._reconnect_attempts - 1))
            delay = min(delay, 60.0)  # Cap at 60 seconds
            
            logger.info(f"Reconnection attempt {self._reconnect_attempts}/{self.max_reconnect_attempts} in {delay:.1f}s")
            await asyncio.sleep(delay)
            
            if await self.connect():
                break
        
        if not self.connected and self._reconnect_attempts >= self.max_reconnect_attempts:
            error_msg = "Max reconnection attempts reached. Giving up."
            logger.error(error_msg)
            if self.on_error:
                self.on_error(error_msg)

    async def _send_loop(self):
        """Background task to send queued messages."""
        while self.running:
            try:
                msg = await asyncio.wait_for(self._send_queue.get(), timeout=1.0)
                if self.writer and self.connected:
                    self.writer.write(msg)
                    await self.writer.drain()
                    self.stats.bytes_sent += len(msg)
                    self.stats.messages_sent += 1
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Send loop error: {e}")
                break

    async def _receive_loop(self):
        """Main receive loop with message framing."""
        buffer = b""
        
        while self.running:
            try:
                data = await self.reader.read(4096)
                if not data:
                    break
                
                buffer += data
                self.stats.bytes_received += len(data)
                
                # Process complete messages
                while len(buffer) >= 4:
                    length = struct.unpack("!I", buffer[:4])[0]
                    if len(buffer) < 4 + length:
                        break
                    
                    msg_data = buffer[4:4 + length]
                    buffer = buffer[4 + length:]
                    
                    decoded = decode_message(msg_data)
                    if decoded:
                        self.stats.messages_received += 1
                        msg_type, data, msg_id, timestamp = decoded
                        await self._handle_message(msg_type, data, msg_id, timestamp)
                    else:
                        logger.warning("Failed to decode message")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.running:
                    logger.error(f"Receive error: {e}")
                    if self.on_error:
                        self.on_error(f"Connection error: {e}")
                break
        
        # Connection lost
        await self._handle_disconnect()

    async def _handle_message(
        self,
        msg_type: str,
        data: dict,
        msg_id: Optional[str],
        timestamp: float
    ):
        """Route incoming messages to appropriate handlers."""
        if msg_type == MessageType.JOIN:
            self.player_id = data.get("player_id")
            logger.info(f"Assigned player ID: {self.player_id}")
            
        elif msg_type == MessageType.STATE:
            state = GameState.from_dict(data)
            self._last_state = state
            if self.on_state:
                try:
                    self.on_state(state)
                except Exception as e:
                    logger.error(f"State callback error: {e}")
                    
        elif msg_type == MessageType.PLAYER_LIST:
            if self.on_players:
                try:
                    self.on_players(data.get("players", []))
                except Exception as e:
                    logger.error(f"Player list callback error: {e}")
                    
        elif msg_type == MessageType.PLAYER_JOINED:
            if self.on_player_joined:
                try:
                    self.on_player_joined(data)
                except Exception as e:
                    logger.error(f"Player joined callback error: {e}")
            logger.info(f"Player joined: {data.get('name', 'Unknown')}")
            
        elif msg_type == MessageType.PLAYER_LEFT:
            if self.on_player_left:
                try:
                    self.on_player_left(data)
                except Exception as e:
                    logger.error(f"Player left callback error: {e}")
            logger.info(f"Player left: {data.get('name', 'Unknown')}")
            
        elif msg_type == MessageType.CHAT:
            sender = data.get("sender", "Unknown")
            message = data.get("message", "")
            if self.on_chat:
                try:
                    self.on_chat(sender, message)
                except Exception as e:
                    logger.error(f"Chat callback error: {e}")
                    
        elif msg_type == MessageType.COMBAT:
            if self.on_combat:
                try:
                    self.on_combat(data)
                except Exception as e:
                    logger.error(f"Combat callback error: {e}")
                    
        elif msg_type == MessageType.PONG:
            latency = (time.time() - timestamp) * 1000
            self.stats.record_ping(latency)
            
        elif msg_type == MessageType.ERROR:
            error_msg = data.get("message", "Unknown error")
            logger.error(f"Server error: {error_msg}")
            if self.on_error:
                self.on_error(error_msg)
                
        elif msg_type == MessageType.SERVER_INFO:
            logger.info(f"Server info: {data}")

    async def _heartbeat_loop(self):
        """Send periodic heartbeat to keep connection alive."""
        while self.running and self.connected:
            await asyncio.sleep(30.0)
            if self.connected:
                await self._queue_message(MessageType.HEARTBEAT, {})

    async def _ping_loop(self):
        """Send periodic ping requests to measure latency."""
        while self.running and self.connected:
            await asyncio.sleep(5.0)
            if self.connected:
                await self._queue_message(
                    MessageType.PING,
                    {"time": time.time()},
                    msg_id=str(uuid.uuid4())
                )

    async def _queue_message(
        self,
        msg_type: str,
        data: dict,
        msg_id: Optional[str] = None
    ):
        """Queue a message for sending."""
        msg = encode_message(msg_type, data, msg_id)
        try:
            await asyncio.wait_for(self._send_queue.put(msg), timeout=1.0)
        except asyncio.TimeoutError:
            logger.warning("Send queue full, message dropped")

    async def send_action(self, action: str, data: dict):
        """
        Send a game action to the server.
        
        Args:
            action: Action type (move, wait, pickup, etc.).
            data: Action-specific data.
        """
        if not self.connected:
            logger.warning("Cannot send action: not connected")
            return
            
        payload = {"action": action, **data}
        await self._queue_message(MessageType.ACTION, payload)

    async def send_chat(self, message: str):
        """Send a chat message to all players."""
        if not self.connected:
            return
        await self._queue_message(MessageType.CHAT, {
            "sender": self.player_name,
            "message": message,
            "player_id": self.player_id
        })

    async def _handle_disconnect(self):
        """Handle unexpected disconnection."""
        if not self.running:
            return
            
        self.connected = False
        logger.warning("Disconnected from server")
        
        if self.on_disconnect:
            try:
                self.on_disconnect()
            except Exception as e:
                logger.error(f"Disconnect callback error: {e}")
        
        # Cancel background tasks
        for task in [self._heartbeat_task, self._ping_task]:
            if task and not task.done():
                task.cancel()
        
        if self.auto_reconnect and self._reconnect_attempts < self.max_reconnect_attempts:
            asyncio.create_task(self._attempt_reconnect())

    async def close(self):
        """Gracefully disconnect from the server."""
        self.running = False
        self.auto_reconnect = False  # Prevent reconnection on intentional close
        
        if self.writer:
            try:
                leave_msg = encode_message(MessageType.LEAVE, {
                    "player_id": self.player_id,
                    "reason": "client_disconnect"
                })
                self.writer.write(leave_msg)
                await self.writer.drain()
                await asyncio.sleep(0.1)  # Give server time to process
            except Exception:
                pass
            finally:
                self.writer.close()
                try:
                    await self.writer.wait_closed()
                except Exception:
                    pass
        
        self.connected = False
        logger.info("Client disconnected")

    @property
    def latency(self) -> float:
        """Current connection latency in milliseconds."""
        return self.stats.latency_ms

    @property
    def uptime(self) -> float:
        """Connection uptime in seconds."""
        return self.stats.uptime_seconds

    def __repr__(self):
        status = "connected" if self.connected else "disconnected"
        return f"MultiplayerClient({self.player_name}, {status}, latency={self.latency:.1f}ms)"


class ClientConnection:
    """Represents a single client connection on the server."""
    
    def __init__(self, client_id: int, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.client_id = client_id
        self.reader = reader
        self.writer = writer
        self.name = f"Player{client_id}"
        self.player_id: Optional[int] = None
        self.addr = writer.get_extra_info('peername')
        self.stats = ConnectionStats()
        self.join_time = time.time()
        self.last_activity = time.time()
        self.buffer = b""
        self.send_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.alive = True

    async def send(self, msg_type: str, data: dict, msg_id: Optional[str] = None) -> bool:
        """Send a message to this client."""
        try:
            msg = encode_message(msg_type, data, msg_id)
            await asyncio.wait_for(self.send_queue.put(msg), timeout=0.5)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Client {self.client_id} send queue full")
            return False

    async def drain_queue(self):
        """Send all queued messages."""
        while not self.send_queue.empty() and self.alive:
            try:
                msg = self.send_queue.get_nowait()
                self.writer.write(msg)
                await self.writer.drain()
                self.stats.bytes_sent += len(msg)
                self.stats.messages_sent += 1
            except Exception as e:
                logger.error(f"Error sending to client {self.client_id}: {e}")
                self.alive = False
                break

    def update_activity(self):
        """Update the last activity timestamp."""
        self.last_activity = time.time()

    @property
    def idle_time(self) -> float:
        """Seconds since last activity."""
        return time.time() - self.last_activity

    def __repr__(self):
        return f"ClientConnection({self.client_id}, {self.name}, {self.addr})"


class MultiplayerServer:
    """
    Enhanced multiplayer server with proper client management,
    rate limiting, message batching, and graceful shutdown.
    """

    def __init__(
        self,
        port: int = 7777,
        max_clients: int = 16,
        tick_rate: float = 20.0,
        idle_timeout: float = 300.0,
        broadcast_rate_limit: float = 0.05
    ):
        self.port = port
        self.max_clients = max_clients
        self.tick_rate = tick_rate
        self.idle_timeout = idle_timeout
        self.broadcast_rate_limit = broadcast_rate_limit
        
        self.clients: Dict[int, ClientConnection] = {}
        self.running = False
        self.server: Optional[asyncio.Server] = None
        self.game_engine = None
        self.local_player_id = 1
        self._next_client_id = 2
        
        # Rate limiting
        self._last_broadcast_time = 0.0
        self._pending_broadcast = False
        self._pending_state: Optional[GameState] = None
        
        # Statistics
        self.total_connections = 0
        self.peak_clients = 0
        self.start_time = 0.0
        
        # Background tasks
        self._broadcast_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def set_engine(self, engine):
        """Set the game engine that handles game logic."""
        self.game_engine = engine

    async def start(self):
        """Start the multiplayer server."""
        self.server = await asyncio.start_server(
            self._handle_client, "0.0.0.0", self.port
        )
        self.running = True
        self.start_time = time.time()
        
        addr = self.server.sockets[0].getsockname()
        logger.info(f"Server started on {addr[0]}:{addr[1]}")
        logger.info(f"Max clients: {self.max_clients}")
        logger.info(f"Share this address with other players on your LAN")
        
        # Start background tasks
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a new client connection."""
        addr = writer.get_extra_info('peername')
        
        # Check max clients
        if len(self.clients) >= self.max_clients:
            logger.warning(f"Connection from {addr} rejected: server full")
            try:
                error_msg = encode_message(MessageType.ERROR, {
                    "message": "Server is full. Please try again later."
                })
                writer.write(error_msg)
                await writer.drain()
            except Exception:
                pass
            writer.close()
            await writer.wait_closed()
            return
        
        async with self._lock:
            client_id = self._next_client_id
            self._next_client_id += 1
        
        client = ClientConnection(client_id, reader, writer)
        self.total_connections += 1
        
        try:
            # Wait for join message
            initial_data = await asyncio.wait_for(reader.read(4096), timeout=10.0)
            if not initial_data:
                writer.close()
                return
            
            msg_type, data, msg_id, timestamp = decode_message(initial_data) or (None, {}, None, 0)
            
            if msg_type == MessageType.JOIN:
                player_name = data.get("name", f"Player{client_id}")
                client.name = player_name
                client.player_id = client_id
                
                async with self._lock:
                    self.clients[client_id] = client
                    self.peak_clients = max(self.peak_clients, len(self.clients))
                
                logger.info(f"Player '{player_name}' joined (ID: {client_id}) from {addr}")
                
                # Send welcome
                await client.send(MessageType.JOIN, {
                    "player_id": client_id,
                    "server_time": time.time(),
                    "client_count": len(self.clients)
                })
                
                # Notify other players
                await self._broadcast(
                    MessageType.PLAYER_JOINED,
                    {"id": client_id, "name": player_name},
                    exclude=client_id
                )
                
                await self._broadcast_player_list()
                await self._broadcast_state()
                
                # Send server info
                await client.send(MessageType.SERVER_INFO, {
                    "max_clients": self.max_clients,
                    "current_clients": len(self.clients),
                    "uptime": time.time() - self.start_time,
                    "version": "2.0"
                })
                
                # Start message loops
                receive_task = asyncio.create_task(self._client_receive_loop(client))
                send_task = asyncio.create_task(self._client_send_loop(client))
                
                # Wait for either task to finish
                done, pending = await asyncio.wait(
                    [receive_task, send_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                for task in pending:
                    task.cancel()
                    
            else:
                logger.warning(f"Expected join message from {addr}, got {msg_type}")
                await client.send(MessageType.ERROR, {
                    "message": "Expected join message as first packet"
                })
                
        except asyncio.TimeoutError:
            logger.warning(f"Client {addr} timed out during handshake")
        except Exception as e:
            logger.error(f"Client {client_id} error: {e}")
        finally:
            await self._disconnect_client(client_id)

    async def _client_receive_loop(self, client: ClientConnection):
        """Handle incoming messages from a client."""
        buffer = b""
        
        while self.running and client.alive:
            try:
                data = await asyncio.wait_for(client.reader.read(4096), timeout=1.0)
                if not data:
                    break
                
                client.stats.bytes_received += len(data)
                buffer += data
                client.update_activity()
                
                # Process complete messages
                while len(buffer) >= 4:
                    length = struct.unpack("!I", buffer[:4])[0]
                    if len(buffer) < 4 + length:
                        break
                    
                    msg_data = buffer[4:4 + length]
                    buffer = buffer[4 + length:]
                    
                    decoded = decode_message(msg_data)
                    if decoded:
                        client.stats.messages_received += 1
                        msg_type, action_data, msg_id, timestamp = decoded
                        await self._handle_client_message(client, msg_type, action_data)
                    else:
                        logger.warning(f"Invalid message from client {client.client_id}")
                        
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if client.alive:
                    logger.error(f"Receive error for client {client.client_id}: {e}")
                break
        
        client.alive = False

    async def _client_send_loop(self, client: ClientConnection):
        """Handle outgoing messages to a client."""
        while self.running and client.alive:
            try:
                await client.drain_queue()
                await asyncio.sleep(0.01)  # Small delay to batch messages
            except Exception as e:
                logger.error(f"Send error for client {client.client_id}: {e}")
                break
        
        client.alive = False

    async def _handle_client_message(
        self,
        client: ClientConnection,
        msg_type: str,
        data: dict
    ):
        """Process a message from a client."""
        if msg_type == MessageType.ACTION:
            await self._handle_action(client.client_id, data)
            
        elif msg_type == MessageType.CHAT:
            # Broadcast chat to all clients
            chat_data = {
                "sender": client.name,
                "message": data.get("message", ""),
                "player_id": client.client_id,
                "timestamp": time.time()
            }
            await self._broadcast(MessageType.CHAT, chat_data)
            logger.info(f"Chat from {client.name}: {data.get('message', '')}")
            
        elif msg_type == MessageType.PING:
            await client.send(MessageType.PONG, {
                "client_time": data.get("time"),
                "server_time": time.time()
            })
            
        elif msg_type == MessageType.HEARTBEAT:
            # Just update activity (already done)
            pass
            
        elif msg_type == MessageType.LEAVE:
            logger.info(f"Client {client.client_id} requested disconnect")
            client.alive = False

    async def _handle_action(self, client_id: int, action_data: dict):
        """Process a game action from a client."""
        if not self.game_engine:
            return
        
        action = action_data.get("action")
        player = self.game_engine.get_player(client_id)
        
        if not player or player.fighter.hp <= 0:
            client = self.clients.get(client_id)
            if client:
                await client.send(MessageType.ERROR, {
                    "message": "You cannot act while dead."
                })
            return
        
        handled = False
        action_handlers = {
            "move": lambda: self.game_engine.handle_move_player(
                player,
                action_data.get("dx", 0),
                action_data.get("dy", 0)
            ),
            "wait": lambda: self.game_engine.handle_wait(),
            "pickup": lambda: self.game_engine.handle_pickup_player(player),
            "take_stairs": lambda: self.game_engine.handle_stairs_player(player),
            "use_item": lambda: self.game_engine.handle_use_item(
                player,
                action_data.get("item_index", 0)
            ),
            "drop_item": lambda: self.game_engine.handle_drop_item(
                player,
                action_data.get("item_index", 0)
            ),
            "attack": lambda: self.game_engine.handle_attack(
                player,
                action_data.get("target_id")
            ),
            "interact": lambda: self.game_engine.handle_interact(player),
        }
        
        handler = action_handlers.get(action)
        if handler:
            try:
                handled = handler()
            except Exception as e:
                logger.error(f"Action handler error for '{action}': {e}")
                handled = False
        else:
            logger.warning(f"Unknown action: {action}")
        
        if handled:
            await self._schedule_broadcast()

    async def _schedule_broadcast(self):
        """Schedule a state broadcast, respecting rate limits."""
        async with self._lock:
            self._pending_broadcast = True
            if self.game_engine:
                self._pending_state = self.game_engine.get_state()

    async def _broadcast_loop(self):
        """Background loop that broadcasts state at the tick rate."""
        while self.running:
            await asyncio.sleep(1.0 / self.tick_rate)
            
            if not self._pending_broadcast or not self.game_engine:
                continue
            
            current_time = time.time()
            if current_time - self._last_broadcast_time < self.broadcast_rate_limit:
                continue
            
            async with self._lock:
                self._pending_broadcast = False
                self._last_broadcast_time = current_time
                state = self._pending_state
            
            if state:
                await self._broadcast(MessageType.STATE, state.to_dict())

    async def _cleanup_loop(self):
        """Periodically clean up idle or disconnected clients."""
        while self.running:
            await asyncio.sleep(60.0)  # Check every minute
            
            stale_clients = []
            for client_id, client in list(self.clients.items()):
                if client.idle_time > self.idle_timeout:
                    logger.info(f"Client {client_id} idle for {client.idle_time:.0f}s, disconnecting")
                    stale_clients.append(client_id)
                elif not client.alive:
                    stale_clients.append(client_id)
            
            for client_id in stale_clients:
                await self._disconnect_client(client_id)

    async def _disconnect_client(self, client_id: int):
        """Gracefully disconnect a client and clean up."""
        client = self.clients.get(client_id)
        if not client:
            return
        
        logger.info(f"Disconnecting client {client_id} ({client.name})")
        
        # Remove from clients dict
        async with self._lock:
            if client_id in self.clients:
                del self.clients[client_id]
        
        # Mark as not alive
        client.alive = False
        
        # Close writer
        try:
            client.writer.close()
            await client.writer.wait_closed()
        except Exception:
            pass
        
        # Notify other players
        await self._broadcast(
            MessageType.PLAYER_LEFT,
            {"id": client_id, "name": client.name}
        )
        await self._broadcast_player_list()
        
        # Update game engine if needed
        if self.game_engine:
            try:
                self.game_engine.remove_player(client_id)
                await self._schedule_broadcast()
            except Exception as e:
                logger.error(f"Error removing player from engine: {e}")

    async def _broadcast(
        self,
        msg_type: str,
        data: dict,
        exclude: Optional[int] = None,
        msg_id: Optional[str] = None
    ):
        """Broadcast a message to all connected clients."""
        dead_clients = []
        
        for client_id, client in list(self.clients.items()):
            if client_id == exclude:
                continue
            if not client.alive:
                dead_clients.append(client_id)
                continue
                
            success = await client.send(msg_type, data, msg_id)
            if not success:
                dead_clients.append(client_id)
        
        # Clean up dead clients
        for client_id in dead_clients:
            asyncio.create_task(self._disconnect_client(client_id))

    async def _broadcast_state(self):
        """Immediately broadcast current game state."""
        if not self.game_engine:
            return
        state = self.game_engine.get_state()
        await self._broadcast(MessageType.STATE, state.to_dict())

    async def _broadcast_player_list(self):
        """Broadcast the current player list to all clients."""
        players = [
            {
                "id": cid,
                "name": client.name,
                "latency": client.stats.average_latency,
                "idle_time": client.idle_time
            }
            for cid, client in self.clients.items()
            if client.alive
        ]
        players.append({
            "id": self.local_player_id,
            "name": "Host (You)",
            "is_host": True
        })
        
        await self._broadcast(MessageType.PLAYER_LIST, {"players": players})

    async def send_to_client(self, client_id: int, msg_type: str, data: dict) -> bool:
        """Send a message to a specific client."""
        client = self.clients.get(client_id)
        if client and client.alive:
            return await client.send(msg_type, data)
        return False

    def get_stats(self) -> dict:
        """Get server statistics."""
        return {
            "running": self.running,
            "port": self.port,
            "connected_clients": len(self.clients),
            "max_clients": self.max_clients,
            "total_connections": self.total_connections,
            "peak_clients": self.peak_clients,
            "uptime": time.time() - self.start_time if self.start_time else 0,
            "clients": [
                {
                    "id": c.client_id,
                    "name": c.name,
                    "addr": c.addr,
                    "latency": c.stats.average_latency,
                    "messages_sent": c.stats.messages_sent,
                    "messages_received": c.stats.messages_received,
                    "uptime": c.stats.uptime_seconds
                }
                for c in self.clients.values()
            ]
        }

    async def stop(self):
        """Gracefully stop the server."""
        logger.info("Shutting down server...")
        self.running = False
        
        # Notify all clients
        await self._broadcast(MessageType.ERROR, {
            "message": "Server is shutting down."
        })
        
        # Disconnect all clients
        for client_id in list(self.clients.keys()):
            await self._disconnect_client(client_id)
        
        # Cancel background tasks
        for task in [self._broadcast_task, self._cleanup_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Close server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        
        logger.info("Server stopped")

    def __repr__(self):
        status = "running" if self.running else "stopped"
        return f"MultiplayerServer(port={self.port}, {status}, clients={len(self.clients)}/{self.max_clients})"
