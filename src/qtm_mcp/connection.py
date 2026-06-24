import asyncio
import logging
from enum import Enum
from typing import Optional

import httpx

from qtm_mcp.config import get_settings, Settings
from qtm_mcp.utils import CircuitBreakerClient

logger = logging.getLogger("Universal_QTM_Server.connection")

try:
    import qtm_rt
    QTM_RT_AVAILABLE = True
except ImportError:
    QTM_RT_AVAILABLE = False


class QTMState(Enum):
    UNKNOWN = "unknown"
    DISCONNECTED = "disconnected"
    IDLE = "idle"
    PREVIEW = "preview"
    RECORDING = "recording"
    PLAYING = "playing"


class QTMConnectionManager:
    """Manages the persistent QTM RT connection and Scripting API HTTP clients.
    
    This acts as a singleton providing thread-safe, non-blocking access to QTM streams
    and REST endpoints.
    """
    
    def __init__(self, settings: Settings):
        self._settings = settings
        
        # RT state. _rt_conn / rt_connected / qtm_state are mutated from two
        # contexts:
        #   (a) get_rt() / _ensure_rt_connected() on the event loop, and
        #   (b) the qtm_rt on_disconnect callback, which fires from a
        #       background thread inside the qtm_rt library.
        # To keep those two contexts coordinated, the disconnect callback
        # re-enters the loop via loop.call_soon_threadsafe and the resulting
        # mutation is gated by _reconnect_lock (same lock get_rt uses).
        self._rt_conn: Optional['qtm_rt.QRTConnection'] = None
        self.rt_connected: bool = False
        self.qtm_state: QTMState = QTMState.UNKNOWN
        self._reconnect_lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Scripting HTTP state
        self._scripting_client: Optional[httpx.AsyncClient] = None
        self._scripting_circuit_breaker: Optional[CircuitBreakerClient] = None
        
        # General REST state
        self._rest_client: Optional[httpx.AsyncClient] = None
        self._rest_circuit_breaker: Optional[CircuitBreakerClient] = None

    async def startup(self):
        """Initialise HTTP clients. RT connection is lazily initialised."""
        logger.info("Initialising HTTP clients in ConnectionManager.")
        # Remember the loop we were started on so the on_disconnect callback
        # (which runs in a qtm_rt-owned thread) can schedule its mutation
        # back onto the same loop.
        self._loop = asyncio.get_running_loop()
        
        # Scripting Client (Port 7979)
        self._scripting_client = httpx.AsyncClient(
            base_url=self._settings.qtm_scripting_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        self._scripting_circuit_breaker = CircuitBreakerClient(
            self._scripting_client, max_failures=5, reset_timeout=30.0
        )
        
        # General REST Client (Port 22222 by default)
        self._rest_client = httpx.AsyncClient(
            base_url=self._settings.qtm_rest_url,
            timeout=httpx.Timeout(5.0, connect=2.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        self._rest_circuit_breaker = CircuitBreakerClient(
            self._rest_client, max_failures=3, reset_timeout=60.0
        )

    async def shutdown(self):
        """Cleanly drain HTTP clients and RT connection."""
        logger.info("Shutting down ConnectionManager.")
        if self._scripting_client:
            await self._scripting_client.aclose()
        if self._rest_client:
            await self._rest_client.aclose()
            
        if self._rt_conn and self.rt_connected:
            try:
                self._rt_conn.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting RT: {e}")
            self.rt_connected = False

    # --- HTTP Clients ---
    
    def get_scripting_client(self) -> CircuitBreakerClient:
        if not self._scripting_circuit_breaker:
            raise RuntimeError("Scripting client not initialised.")
        return self._scripting_circuit_breaker

    def get_rest_client(self) -> CircuitBreakerClient:
        if not self._rest_circuit_breaker:
            raise RuntimeError("REST client not initialised.")
        return self._rest_circuit_breaker

    # --- RT Connection & Streaming ---
    
    def _on_rt_disconnect(self, reason: str):
        """Invoked by qtm_rt from its I/O thread when the RT connection drops.

        We must NOT mutate shared state here directly -- get_rt() reads the
        same fields on the event loop, so we'd race. Instead, hop back onto
        the event loop and apply the mutation under _reconnect_lock.
        """
        logger.warning("RT disconnected: %s", reason)
        loop = self._loop
        if loop is None or loop.is_closed():
            # No loop available (we're being torn down). Best-effort mutation;
            # the lock can't help us here.
            self.rt_connected = False
            self.qtm_state = QTMState.DISCONNECTED
            self._rt_conn = None
            return
        loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(self._apply_disconnect(), loop=loop)
        )

    async def _apply_disconnect(self) -> None:
        async with self._reconnect_lock:
            self.rt_connected = False
            self.qtm_state = QTMState.DISCONNECTED
            self._rt_conn = None

    async def _ensure_rt_connected(self) -> 'qtm_rt.QRTConnection':
        """Internal method to establish RT connection. MUST be called with _reconnect_lock held."""
        if not QTM_RT_AVAILABLE:
            raise RuntimeError("qtm-rt is not installed.")
            
        if self._rt_conn and self.rt_connected:
            return self._rt_conn
        try:
            self._rt_conn = await asyncio.wait_for(
                qtm_rt.connect(
                    self._settings.qtm_rt_host,
                    port=self._settings.qtm_rt_port,
                    on_disconnect=self._on_rt_disconnect,
                ),
                timeout=5.0,
            )
            if self._rt_conn is None:
                raise ConnectionError("qtm_rt.connect returned None")
            self.rt_connected = True
            self.qtm_state = QTMState.IDLE
            logger.info("RT connection established.")
            return self._rt_conn
        except Exception as exc:
            self.rt_connected = False
            self.qtm_state = QTMState.DISCONNECTED
            raise ConnectionError(f"RT connect failed: {exc}") from exc

    async def get_rt(self) -> 'qtm_rt.QRTConnection':
        """Gets or re-establishes the RT connection."""
        if self._rt_conn and self.rt_connected:
            return self._rt_conn
        
        MAX_RECONNECT_ATTEMPTS = 3
        RECONNECT_BACKOFF_BASE = 1.0  # seconds

        async with self._reconnect_lock:
            if self._rt_conn and self.rt_connected:
                return self._rt_conn
            
            for attempt in range(MAX_RECONNECT_ATTEMPTS):
                try:
                    return await self._ensure_rt_connected()
                except ConnectionError:
                    if attempt < MAX_RECONNECT_ATTEMPTS - 1:
                        delay = RECONNECT_BACKOFF_BASE * (2 ** attempt)
                        logger.warning("RT reconnect attempt %d failed, retrying in %.1fs", attempt + 1, delay)
                        await asyncio.sleep(delay)
            
            raise ConnectionError("All RT reconnection attempts exhausted")

    async def get_rt_frame(self, components: list[str], timeout: float = 2.0) -> Optional[dict]:
        """Concurrent-safe frame fetcher.
        
        Hooks into the stream, grabs the latest frame of the requested components,
        and unhooks without breaking the connection for other requests.
        """
        conn = await self.get_rt()
        
        frame_dict = {}
        done_event = asyncio.Event()

        def on_packet(packet):
            frame_dict["frame_number"] = packet.framenumber
            
            if "3d" in components:
                try:
                    _, markers = packet.get_3d_markers()
                    frame_dict["3d"] = [{"x": m.x, "y": m.y, "z": m.z} for m in markers] if markers else []
                except Exception:
                    frame_dict["3d"] = []

            if "6d" in components:
                try:
                    _, bodies = packet.get_6d()
                    if bodies:
                        frame_dict["6d"] = [
                            {
                                "name": name,
                                "position": list(pos) if pos is not None else [],
                                "rotation": [list(row) for row in rot] if rot is not None else []
                            }
                            for name, pos, rot in bodies
                        ]
                    else:
                        frame_dict["6d"] = []
                except Exception:
                    frame_dict["6d"] = []

            if "analog" in components:
                try:
                    _, analog = packet.get_analog()
                    frame_dict["analog"] = analog if analog is not None else []
                except Exception:
                    frame_dict["analog"] = []

            if "force" in components:
                try:
                    _, force = packet.get_force()
                    frame_dict["force"] = force if force is not None else []
                except Exception:
                    frame_dict["force"] = []
                    
            if "skeleton" in components:
                try:
                    _, skeletons = packet.get_skeleton()
                    # Skeleton format can vary, just extract the dict
                    frame_dict["skeleton"] = skeletons if skeletons is not None else []
                except Exception as e:
                    # Capture graceful fallback error if skeleton fails
                    frame_dict["skeleton_error"] = str(e)
                    frame_dict["skeleton"] = []

            done_event.set()

        try:
            # We start the stream. If multiple tools call this, qtm_rt handles multiple streams
            # or overrides components. We just grab one packet.
            await conn.stream_frames(components=components, on_packet=on_packet)
            try:
                await asyncio.wait_for(done_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout waiting for RT frame with components {components}")
                return None
        finally:
            try:
                await conn.stream_frames_stop()
            except Exception as e:
                logger.error(f"Error stopping stream: {e}")

        return frame_dict

# Singleton instance
_manager: Optional[QTMConnectionManager] = None

def get_connection_manager() -> QTMConnectionManager:
    if _manager is None:
        raise RuntimeError("Connection manager not initialised.")
    return _manager

def set_connection_manager(manager: Optional[QTMConnectionManager]):
    global _manager
    _manager = manager
