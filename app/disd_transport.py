"""
DISD Transport Layer

Abstract transport layer for DISD protocol messages.
Supports multiple transport mechanisms (HTTP, WebSocket, gRPC).

STATUS: PRODUCTION IMPLEMENTATION
UPDATED: 2026-01-08
PURPOSE: DISD protocol transport abstraction
"""

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import logging

from .disd_message import DISDMessage, DISDMessageType

logger = logging.getLogger(__name__)


class TransportResult:
    """Result of transport operation"""
    
    def __init__(self, success: bool, message: str = "", data: Any = None):
        self.success = success
        self.message = message
        self.data = data
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp.isoformat()
        }


class DISDTransport(ABC):
    """Abstract base class for DISD transport mechanisms"""
    
    def __init__(self, transport_id: str):
        self.transport_id = transport_id
        self.is_connected = False
        self.message_handlers: Dict[DISDMessageType, List[Callable]] = {}
        self.global_handlers: List[Callable] = []
        
    @abstractmethod
    async def connect(self) -> TransportResult:
        """Connect to transport"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> TransportResult:
        """Disconnect from transport"""
        pass
    
    @abstractmethod
    async def send_message(self, message: DISDMessage, target: str) -> TransportResult:
        """Send message to target"""
        pass
    
    @abstractmethod
    async def broadcast_message(self, message: DISDMessage) -> TransportResult:
        """Broadcast message to all targets"""
        pass
    
    @abstractmethod
    async def receive_message(self) -> Optional[DISDMessage]:
        """Receive message"""
        pass
    
    def register_handler(self, message_type: DISDMessageType, handler: Callable) -> bool:
        """Register message handler"""
        if message_type not in self.message_handlers:
            self.message_handlers[message_type] = []
        self.message_handlers[message_type].append(handler)
        return True
    
    def register_global_handler(self, handler: Callable) -> bool:
        """Register global message handler"""
        self.global_handlers.append(handler)
        return True
    
    async def handle_message(self, message: DISDMessage) -> None:
        """Handle received message"""
        try:
            # Call global handlers
            for handler in self.global_handlers:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error(f"Global handler error: {e}")
            
            # Call type-specific handlers
            handlers = self.message_handlers.get(message.message_type, [])
            for handler in handlers:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error(f"Handler error for {message.message_type}: {e}")
                    
        except Exception as e:
            logger.error(f"Message handling error: {e}")


class HTTPTransport(DISDTransport):
    """HTTP-based transport for DISD messages"""
    
    def __init__(self, base_url: str, timeout_ms: int = 5000):
        super().__init__("http")
        self.base_url = base_url.rstrip('/')
        self.timeout_ms = timeout_ms
        self.session = None
        
    async def connect(self) -> TransportResult:
        """Connect to HTTP transport"""
        try:
            import httpx
            
            self.session = httpx.AsyncClient(timeout=self.timeout_ms / 1000)
            
            # Test connection
            response = await self.session.get(f"{self.base_url}/health")
            if response.status_code == 200:
                self.is_connected = True
                return TransportResult(True, "HTTP transport connected")
            else:
                return TransportResult(False, f"HTTP health check failed: {response.status_code}")
                
        except Exception as e:
            return TransportResult(False, f"HTTP connection failed: {str(e)}")
    
    async def disconnect(self) -> TransportResult:
        """Disconnect from HTTP transport"""
        try:
            if self.session:
                await self.session.aclose()
                self.session = None
            
            self.is_connected = False
            return TransportResult(True, "HTTP transport disconnected")
            
        except Exception as e:
            return TransportResult(False, f"HTTP disconnect failed: {str(e)}")
    
    async def send_message(self, message: DISDMessage, target: str) -> TransportResult:
        """Send message to target via HTTP"""
        try:
            if not self.is_connected or not self.session:
                return TransportResult(False, "HTTP transport not connected")
            
            url = f"{self.base_url}/agents/{target}/disd/message"
            data = message.to_json()
            
            response = await self.session.post(url, content=data)
            
            if response.status_code == 200:
                return TransportResult(True, "Message sent via HTTP", response.json())
            else:
                return TransportResult(False, f"HTTP send failed: {response.status_code}")
                
        except Exception as e:
            return TransportResult(False, f"HTTP send error: {str(e)}")
    
    async def broadcast_message(self, message: DISDMessage) -> TransportResult:
        """Broadcast message via HTTP"""
        try:
            if not self.is_connected or not self.session:
                return TransportResult(False, "HTTP transport not connected")
            
            url = f"{self.base_url}/disd/broadcast"
            data = message.to_json()
            
            response = await self.session.post(url, content=data)
            
            if response.status_code == 200:
                return TransportResult(True, "Message broadcast via HTTP", response.json())
            else:
                return TransportResult(False, f"HTTP broadcast failed: {response.status_code}")
                
        except Exception as e:
            return TransportResult(False, f"HTTP broadcast error: {str(e)}")
    
    async def receive_message(self) -> Optional[DISDMessage]:
        """Receive message via HTTP (polling)"""
        try:
            if not self.is_connected or not self.session:
                return None
            
            url = f"{self.base_url}/disd/receive"
            response = await self.session.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if data:
                    from .disd_message import DISDMessage
                    return DISDMessage.from_dict(data)
            
            return None
            
        except Exception as e:
            logger.error(f"HTTP receive error: {e}")
            return None


class WebSocketTransport(DISDTransport):
    """WebSocket-based transport for DISD messages"""
    
    def __init__(self, websocket_url: str, timeout_ms: int = 5000):
        super().__init__("websocket")
        self.websocket_url = websocket_url
        self.timeout_ms = timeout_ms
        self.websocket = None
        self.receive_queue = asyncio.Queue()
        
    async def connect(self) -> TransportResult:
        """Connect to WebSocket transport"""
        try:
            import websockets
            
            self.websocket = await websockets.connect(
                self.websocket_url,
                ping_interval=self.timeout_ms / 2000,
                ping_timeout=self.timeout_ms / 1000
            )
            
            self.is_connected = True
            
            # Start receive loop
            asyncio.create_task(self._receive_loop())
            
            return TransportResult(True, "WebSocket transport connected")
            
        except Exception as e:
            return TransportResult(False, f"WebSocket connection failed: {str(e)}")
    
    async def disconnect(self) -> TransportResult:
        """Disconnect from WebSocket transport"""
        try:
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
            
            self.is_connected = False
            return TransportResult(True, "WebSocket transport disconnected")
            
        except Exception as e:
            return TransportResult(False, f"WebSocket disconnect failed: {str(e)}")
    
    async def send_message(self, message: DISDMessage, target: str) -> TransportResult:
        """Send message to target via WebSocket"""
        try:
            if not self.is_connected or not self.websocket:
                return TransportResult(False, "WebSocket transport not connected")
            
            # Add target to message
            message_with_target = message.to_dict()
            message_with_target["target"] = target
            
            await self.websocket.send(json.dumps(message_with_target))
            return TransportResult(True, "Message sent via WebSocket")
            
        except Exception as e:
            return TransportResult(False, f"WebSocket send error: {str(e)}")
    
    async def broadcast_message(self, message: DISDMessage) -> TransportResult:
        """Broadcast message via WebSocket"""
        try:
            if not self.is_connected or not self.websocket:
                return TransportResult(False, "WebSocket transport not connected")
            
            # Mark as broadcast
            message_with_broadcast = message.to_dict()
            message_with_broadcast["broadcast"] = True
            
            await self.websocket.send(json.dumps(message_with_broadcast))
            return TransportResult(True, "Message broadcast via WebSocket")
            
        except Exception as e:
            return TransportResult(False, f"WebSocket broadcast error: {str(e)}")
    
    async def receive_message(self) -> Optional[DISDMessage]:
        """Receive message from WebSocket"""
        try:
            if not self.receive_queue.empty():
                data = await self.receive_queue.get()
                from .disd_message import DISDMessage
                return DISDMessage.from_dict(data)
            
            return None
            
        except Exception as e:
            logger.error(f"WebSocket receive error: {e}")
            return None
    
    async def _receive_loop(self):
        """Background receive loop"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    await self.receive_queue.put(data)
                    
                    # Handle message
                    from .disd_message import DISDMessage
                    disd_message = DISDMessage.from_dict(data)
                    await self.handle_message(disd_message)
                    
                except Exception as e:
                    logger.error(f"WebSocket message processing error: {e}")
                    
        except Exception as e:
            logger.error(f"WebSocket receive loop error: {e}")
            self.is_connected = False


class InProcessTransport(DISDTransport):
    """In-process transport for DISD messages (for testing/local development)"""
    
    def __init__(self):
        super().__init__("inprocess")
        self.message_queue = asyncio.Queue()
        self.connected_peers: Dict[str, 'InProcessTransport'] = {}
        
    async def connect(self) -> TransportResult:
        """Connect to in-process transport"""
        self.is_connected = True
        return TransportResult(True, "In-process transport connected")
    
    async def disconnect(self) -> TransportResult:
        """Disconnect from in-process transport"""
        self.is_connected = False
        self.connected_peers.clear()
        return TransportResult(True, "In-process transport disconnected")
    
    async def send_message(self, message: DISDMessage, target: str) -> TransportResult:
        """Send message to target peer"""
        try:
            if not self.is_connected:
                return TransportResult(False, "In-process transport not connected")
            
            peer = self.connected_peers.get(target)
            if peer:
                await peer.message_queue.put(message.to_dict())
                return TransportResult(True, "Message sent in-process")
            else:
                return TransportResult(False, f"Target {target} not found")
                
        except Exception as e:
            return TransportResult(False, f"In-process send error: {str(e)}")
    
    async def broadcast_message(self, message: DISDMessage) -> TransportResult:
        """Broadcast message to all peers"""
        try:
            if not self.is_connected:
                return TransportResult(False, "In-process transport not connected")
            
            sent_count = 0
            for peer in self.connected_peers.values():
                await peer.message_queue.put(message.to_dict())
                sent_count += 1
            
            return TransportResult(True, f"Message broadcast to {sent_count} peers")
            
        except Exception as e:
            return TransportResult(False, f"In-process broadcast error: {str(e)}")
    
    async def receive_message(self) -> Optional[DISDMessage]:
        """Receive message from queue"""
        try:
            if not self.message_queue.empty():
                data = await self.message_queue.get()
                from .disd_message import DISDMessage
                return DISDMessage.from_dict(data)
            
            return None
            
        except Exception as e:
            logger.error(f"In-process receive error: {e}")
            return None
    
    def connect_peer(self, peer_id: str, peer: 'InProcessTransport') -> bool:
        """Connect to peer"""
        self.connected_peers[peer_id] = peer
        peer.connected_peers[self.transport_id] = self
        return True
    
    def disconnect_peer(self, peer_id: str) -> bool:
        """Disconnect from peer"""
        if peer_id in self.connected_peers:
            peer = self.connected_peers[peer_id]
            peer.connected_peers.pop(self.transport_id, None)
            del self.connected_peers[peer_id]
            return True
        return False


class TransportManager:
    """Manages multiple transport mechanisms"""
    
    def __init__(self):
        self.transports: Dict[str, DISDTransport] = {}
        self.default_transport: Optional[str] = None
        self.message_handlers: Dict[DISDMessageType, List[Callable]] = {}
        self.global_handlers: List[Callable] = []
        
    def add_transport(self, transport_id: str, transport: DISDTransport, is_default: bool = False) -> bool:
        """Add transport"""
        self.transports[transport_id] = transport
        
        if is_default or self.default_transport is None:
            self.default_transport = transport_id
        
        # Register handlers with transport
        for message_type, handlers in self.message_handlers.items():
            for handler in handlers:
                transport.register_handler(message_type, handler)
        
        for handler in self.global_handlers:
            transport.register_global_handler(handler)
        
        logger.info(f"Added transport: {transport_id}")
        return True
    
    def remove_transport(self, transport_id: str) -> bool:
        """Remove transport"""
        if transport_id in self.transports:
            del self.transports[transport_id]
            
            if self.default_transport == transport_id:
                self.default_transport = next(iter(self.transports.keys()), None)
            
            logger.info(f"Removed transport: {transport_id}")
            return True
        
        return False
    
    async def connect_all(self) -> Dict[str, TransportResult]:
        """Connect all transports"""
        results = {}
        
        for transport_id, transport in self.transports.items():
            result = await transport.connect()
            results[transport_id] = result
        
        return results
    
    async def disconnect_all(self) -> Dict[str, TransportResult]:
        """Disconnect all transports"""
        results = {}
        
        for transport_id, transport in self.transports.items():
            result = await transport.disconnect()
            results[transport_id] = result
        
        return results
    
    async def send_message(self, message: DISDMessage, target: str, transport_id: Optional[str] = None) -> TransportResult:
        """Send message using specified or default transport"""
        transport_id = transport_id or self.default_transport
        
        if not transport_id or transport_id not in self.transports:
            return TransportResult(False, f"Transport {transport_id} not found")
        
        transport = self.transports[transport_id]
        return await transport.send_message(message, target)
    
    async def broadcast_message(self, message: DISDMessage, transport_id: Optional[str] = None) -> TransportResult:
        """Broadcast message using specified or default transport"""
        transport_id = transport_id or self.default_transport
        
        if not transport_id or transport_id not in self.transports:
            return TransportResult(False, f"Transport {transport_id} not found")
        
        transport = self.transports[transport_id]
        return await transport.broadcast_message(message)
    
    async def receive_messages(self) -> Dict[str, Optional[DISDMessage]]:
        """Receive messages from all transports"""
        messages = {}
        
        for transport_id, transport in self.transports.items():
            message = await transport.receive_message()
            messages[transport_id] = message
        
        return messages
    
    def register_handler(self, message_type: DISDMessageType, handler: Callable) -> bool:
        """Register message handler with all transports"""
        if message_type not in self.message_handlers:
            self.message_handlers[message_type] = []
        
        self.message_handlers[message_type].append(handler)
        
        # Register with all existing transports
        for transport in self.transports.values():
            transport.register_handler(message_type, handler)
        
        return True
    
    def register_global_handler(self, handler: Callable) -> bool:
        """Register global handler with all transports"""
        self.global_handlers.append(handler)
        
        # Register with all existing transports
        for transport in self.transports.values():
            transport.register_global_handler(handler)
        
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """Get transport manager status"""
        return {
            "total_transports": len(self.transports),
            "default_transport": self.default_transport,
            "transport_ids": list(self.transports.keys()),
            "connected_transports": [
                tid for tid, transport in self.transports.items() if transport.is_connected
            ],
            "message_handlers": {
                msg_type.value: len(handlers) for msg_type, handlers in self.message_handlers.items()
            },
            "global_handlers": len(self.global_handlers)
        }


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

transport_manager: TransportManager = None


def get_transport_manager() -> Optional[TransportManager]:
    """Get the global transport manager instance"""
    return transport_manager


def initialize_transport_manager() -> TransportManager:
    """Initialize the global transport manager"""
    global transport_manager
    transport_manager = TransportManager()
    return transport_manager
