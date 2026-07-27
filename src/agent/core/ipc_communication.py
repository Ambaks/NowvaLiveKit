"""
IPC Communication Module
UNIX domain socket communication between voice agent and pose estimation.

Uses 4-byte length-prefix framing to ensure complete message delivery:
  [4-byte big-endian length][JSON payload bytes]
This prevents message corruption when multiple messages arrive in one recv() call
or when a single message spans multiple recv() calls.
"""

from __future__ import annotations

import socket
import struct
import json
import os
import logging
import threading
from collections import deque
from typing import Callable, Optional, Dict, Any

logger = logging.getLogger(__name__)

# 4-byte unsigned big-endian header for message length
HEADER_FORMAT = ">I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_MESSAGE_SIZE = 1024 * 1024  # 1MB safety limit

# Bounded outbound queue so a slow peer never stalls the caller
SEND_QUEUE_MAX_SIZE = 256
FRAME_DATA_MESSAGE_TYPE = "frame_data"
SENDER_JOIN_TIMEOUT_S = 2.0


def _send_framed(sock: socket.socket, message: Dict[str, Any]) -> None:
    """Send a length-prefixed JSON message over a socket."""
    data = json.dumps(message).encode('utf-8')
    header = struct.pack(HEADER_FORMAT, len(data))
    sock.sendall(header + data)


def _send_framed_raw(sock: socket.socket, data: bytes) -> None:
    """Send pre-serialized bytes with length-prefix framing.

    Skips JSON encoding -- use when forwarding an already-serialized message.
    """
    header = struct.pack(HEADER_FORMAT, len(data))
    sock.sendall(header + data)


def _recv_exactly(sock: socket.socket, num_bytes: int) -> bytes:
    """Receive exactly num_bytes from a socket, handling partial reads."""
    chunks = []
    remaining = num_bytes
    while remaining > 0:
        chunk = sock.recv(min(remaining, 65536))
        if not chunk:
            raise ConnectionError("Socket closed while reading")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def _recv_framed(sock: socket.socket) -> Optional[Dict[str, Any]]:
    """Receive a single length-prefixed JSON message from a socket.

    Returns:
        Parsed message dict, or None if connection closed cleanly
    """
    try:
        header = _recv_exactly(sock, HEADER_SIZE)
    except ConnectionError:
        return None

    msg_len = struct.unpack(HEADER_FORMAT, header)[0]
    if msg_len > MAX_MESSAGE_SIZE:
        raise ValueError(f"Message too large: {msg_len} bytes (max {MAX_MESSAGE_SIZE})")

    data = _recv_exactly(sock, msg_len)
    return json.loads(data.decode('utf-8'))


def _recv_framed_with_raw(
    sock: socket.socket,
) -> tuple[bytes, dict[str, Any]] | tuple[bytes, None]:
    """Receive a length-prefixed message, returning both raw bytes and parsed dict.

    The raw bytes are the JSON payload *before* decoding, suitable for
    forwarding via ``_send_framed_raw`` without re-serialization.

    Returns (b'', None) if connection closed cleanly.
    """
    try:
        header = _recv_exactly(sock, HEADER_SIZE)
    except ConnectionError:
        return b'', None

    msg_len = struct.unpack(HEADER_FORMAT, header)[0]
    if msg_len > MAX_MESSAGE_SIZE:
        raise ValueError(f"Message too large: {msg_len} bytes (max {MAX_MESSAGE_SIZE})")

    data = _recv_exactly(sock, msg_len)
    return data, json.loads(data.decode('utf-8'))


def _remove_socket_file(socket_path: str) -> None:
    try:
        os.unlink(socket_path)
    except FileNotFoundError:
        pass


def _is_frame_data(item: dict[str, Any] | bytes) -> bool:
    """Check whether a queued item is a frame_data message.

    Raw bytes items (pre-serialized frame_data) are always treated as
    frame_data for queue-management purposes.
    """
    if isinstance(item, bytes):
        return True
    return item.get("type") == FRAME_DATA_MESSAGE_TYPE


class _SendQueue:
    """Bounded outbound message queue drained by a dedicated sender thread.

    Items may be ``dict`` (JSON-serialized on send) or ``bytes``
    (pre-serialized, forwarded with framing only — no re-encoding).

    When full: new 'frame_data' messages are dropped (debug log); other
    message types evict the oldest queued 'frame_data' if one exists,
    otherwise the new message is dropped with a warning.
    """

    def __init__(self, name: str, get_socket_fn: Callable[[], Optional[socket.socket]]):
        self._name = name
        self._get_socket_fn = get_socket_fn
        self._condition = threading.Condition()
        self._messages: deque[dict[str, Any] | bytes] = deque()
        self._stopped = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        with self._condition:
            self._stopped = False
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._drain, name=f"{self._name}-sender", daemon=True
            )
            self._thread.start()

    def put(self, message: Dict[str, Any]) -> None:
        with self._condition:
            if self._stopped:
                return
            if len(self._messages) >= SEND_QUEUE_MAX_SIZE:
                if message.get("type") == FRAME_DATA_MESSAGE_TYPE:
                    logger.debug(f"{self._name}: send queue full — dropping frame_data")
                    return
                if not self._evict_oldest_frame_data():
                    logger.warning(
                        f"{self._name}: send queue full — dropping message "
                        f"type={message.get('type')}"
                    )
                    return
            self._messages.append(message)
            self._condition.notify()

    def put_raw(self, data: bytes) -> None:
        """Enqueue pre-serialized bytes (treated as frame_data for eviction)."""
        with self._condition:
            if self._stopped:
                return
            if len(self._messages) >= SEND_QUEUE_MAX_SIZE:
                logger.debug(f"{self._name}: send queue full — dropping raw frame_data")
                return
            self._messages.append(data)
            self._condition.notify()

    def stop(self) -> None:
        with self._condition:
            self._stopped = True
            # Keep control messages for a synchronous flush below — final
            # sends like 'error' or 'pipeline_status: stopped' are enqueued
            # right before disconnect()/stop() and must not be lost.
            # Raw bytes items are always frame_data, so always dropped.
            pending = [m for m in self._messages if not _is_frame_data(m)]
            self._messages.clear()
            self._condition.notify_all()
        thread = self._thread
        sender_finished = True
        if thread is not None and thread.is_alive():
            thread.join(timeout=SENDER_JOIN_TIMEOUT_S)
            sender_finished = not thread.is_alive()
        if not sender_finished:
            # Sender is wedged mid-sendall — flushing now would interleave
            # bytes on the same socket and corrupt framing
            if pending:
                logger.warning(
                    f"{self._name}: sender thread stuck at stop — "
                    f"dropping {len(pending)} pending message(s)"
                )
            return
        for message in pending:
            sock = self._get_socket_fn()
            if sock is None:
                break
            try:
                _send_framed(sock, message)
            except Exception as e:
                logger.error(f"{self._name}: error flushing message at stop: {e}")
                break

    def _evict_oldest_frame_data(self) -> bool:
        for index, queued in enumerate(self._messages):
            if _is_frame_data(queued):
                del self._messages[index]
                logger.debug(f"{self._name}: send queue full — evicted oldest frame_data")
                return True
        return False

    def _drain(self) -> None:
        while True:
            with self._condition:
                while not self._messages and not self._stopped:
                    self._condition.wait()
                if self._stopped:
                    return
                item = self._messages.popleft()
            sock = self._get_socket_fn()
            if sock is None:
                if _is_frame_data(item):
                    logger.debug(
                        f"{self._name}: no peer connected — dropping frame_data"
                    )
                    continue
                # Hold non-ephemeral messages until a client connects
                with self._condition:
                    if self._stopped:
                        return
                    self._messages.appendleft(item)
                    self._condition.wait(timeout=0.1)
                continue
            try:
                if isinstance(item, bytes):
                    _send_framed_raw(sock, item)
                else:
                    _send_framed(sock, item)
            except Exception as e:
                logger.error(f"{self._name}: error sending message: {e}")


class IPCServer:
    """IPC Server using UNIX domain sockets with length-prefix framing.

    Thread-safe: socket mutation is guarded by a lock and send_message()
    only enqueues onto a bounded queue (SEND_QUEUE_MAX_SIZE) drained by a
    background sender thread, so a slow peer never blocks the caller.
    When the queue is full, 'frame_data' messages are dropped (debug log);
    other message types evict the oldest queued 'frame_data' if possible,
    otherwise the new message is dropped with a warning.

    listen() re-accepts a new client after a disconnect, so a restarted
    peer can reconnect without restarting the server.
    """

    def __init__(self, socket_path: str = "/tmp/nowva_ipc.sock"):
        self.socket_path = socket_path
        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None
        self.message_callback: Optional[Callable[[Dict], None]] = None
        self.raw_message_callback: Optional[Callable[[Dict, bytes], None]] = None
        self._lock = threading.Lock()
        self._running = threading.Event()
        self._sender = _SendQueue("IPCServer", self._get_client_socket)

    @property
    def running(self) -> bool:
        return self._running.is_set()

    def _get_client_socket(self) -> Optional[socket.socket]:
        with self._lock:
            return self.client_socket

    def bind(
        self,
        message_callback: Optional[Callable[[Dict], None]] = None,
        raw_message_callback: Optional[Callable[[Dict, bytes], None]] = None,
    ):
        """Create and bind the server socket. Connectable immediately after return.

        If *raw_message_callback* is provided it takes precedence over
        *message_callback* and receives ``(parsed_dict, raw_bytes)`` so
        the caller can forward the pre-serialized payload without
        re-encoding.
        """
        _remove_socket_file(self.socket_path)

        server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_socket.bind(self.socket_path)
        server_socket.listen(1)

        with self._lock:
            self.server_socket = server_socket
        self._running.set()
        self.message_callback = message_callback
        self.raw_message_callback = raw_message_callback
        self._sender.start()

        logger.info(f"IPC Server bound on {self.socket_path}")

    def accept_client(self):
        """Block until a client connects. Call after bind()."""
        with self._lock:
            server_socket = self.server_socket
        if server_socket is None:
            raise OSError("Server socket is not bound")

        logger.info("Waiting for client connection...")
        client_socket, _ = server_socket.accept()
        with self._lock:
            self.client_socket = client_socket
        logger.info("Client connected!")

    def start(
        self,
        message_callback: Optional[Callable[[Dict], None]] = None,
        raw_message_callback: Optional[Callable[[Dict, bytes], None]] = None,
    ):
        """Bind and wait for a client connection (convenience wrapper)."""
        self.bind(message_callback, raw_message_callback=raw_message_callback)
        self.accept_client()

    def listen(self):
        """Receive framed messages in a loop, re-accepting a new client on disconnect.

        If a ``raw_message_callback`` is set, it receives ``(message, raw_bytes)``
        instead of the default ``message_callback(message)``.  This allows
        callers to forward the pre-serialized payload without re-encoding.
        """
        while self._running.is_set():
            with self._lock:
                client_socket = self.client_socket
            if client_socket is None:
                if not self._accept_for_listen():
                    return
                continue

            try:
                raw_data, message = _recv_framed_with_raw(client_socket)
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding message: {e}")
                continue
            except (ConnectionError, ValueError) as e:
                logger.error(f"Error in IPC server: {e}")
                raw_data, message = b'', None
            except Exception as e:
                if not self._running.is_set():
                    return
                logger.error(f"Unexpected error in IPC server: {e}")
                raw_data, message = b'', None

            if message is None:
                logger.info("Client disconnected")
                self._close_client_socket()
                continue

            if self.raw_message_callback:
                try:
                    self.raw_message_callback(message, raw_data)
                except Exception as e:
                    logger.error(f"Error in raw message callback: {e}")
            elif self.message_callback:
                try:
                    self.message_callback(message)
                except Exception as e:
                    logger.error(f"Error in message callback: {e}")

    def send_message(self, message: Dict[str, Any]):
        """Enqueue a framed message for the connected client (never blocks)."""
        self._sender.put(message)

    def send_raw_message(self, data: bytes) -> None:
        """Enqueue pre-serialized bytes for the connected client (never blocks).

        Skips JSON encoding -- use when forwarding an already-serialized
        message received from another IPC hop.
        """
        self._sender.put_raw(data)

    def stop(self):
        """Stop IPC server and clean up socket file."""
        self._running.clear()
        self._sender.stop()
        with self._lock:
            client_socket = self.client_socket
            server_socket = self.server_socket
            self.client_socket = None
            self.server_socket = None
        if client_socket is not None:
            client_socket.close()
        if server_socket is not None:
            server_socket.close()
        _remove_socket_file(self.socket_path)
        logger.info("IPC Server stopped")

    def _accept_for_listen(self) -> bool:
        try:
            self.accept_client()
            return True
        except OSError as e:
            if self._running.is_set():
                logger.error(f"Accept failed while waiting for client: {e}")
            return False

    def _close_client_socket(self) -> None:
        with self._lock:
            client_socket = self.client_socket
            self.client_socket = None
        if client_socket is not None:
            client_socket.close()


class IPCClient:
    """IPC Client using UNIX domain sockets with length-prefix framing.

    Thread-safe: socket mutation is guarded by a lock and send_message()
    only enqueues onto a bounded queue (SEND_QUEUE_MAX_SIZE) drained by a
    background sender thread, so a slow peer never blocks the caller.
    When the queue is full, 'frame_data' messages are dropped (debug log);
    other message types evict the oldest queued 'frame_data' if possible,
    otherwise the new message is dropped with a warning.
    """

    def __init__(self, socket_path: str = "/tmp/nowva_ipc.sock"):
        self.socket_path = socket_path
        self.client_socket: Optional[socket.socket] = None
        self.message_callback: Optional[Callable[[Dict], None]] = None
        self._lock = threading.Lock()
        self._running = threading.Event()
        self._sender = _SendQueue("IPCClient", self._get_client_socket)

    @property
    def running(self) -> bool:
        return self._running.is_set()

    def _get_client_socket(self) -> Optional[socket.socket]:
        with self._lock:
            return self.client_socket

    def connect(self, timeout: int = 10):
        """Connect to IPC server with retry."""
        import time
        start_time = time.time()

        while time.time() - start_time < timeout:
            client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                client_socket.connect(self.socket_path)
            except (FileNotFoundError, ConnectionRefusedError):
                client_socket.close()
                time.sleep(0.5)
                continue

            with self._lock:
                self.client_socket = client_socket
            self._running.set()
            self._sender.start()
            logger.info(f"IPC Client connected to {self.socket_path}")
            return True

        logger.error(f"Failed to connect to IPC server after {timeout}s")
        return False

    def listen(self, message_callback: Optional[Callable[[Dict], None]] = None):
        """Listen for incoming framed messages."""
        with self._lock:
            client_socket = self.client_socket
        if client_socket is None:
            logger.warning("Not connected to server")
            return

        self.message_callback = message_callback

        while self._running.is_set():
            try:
                message = _recv_framed(client_socket)
                if message is None:
                    logger.info("Server disconnected")
                    break

                if self.message_callback:
                    self.message_callback(message)

            except json.JSONDecodeError as e:
                logger.error(f"Error decoding message: {e}")
            except (ConnectionError, ValueError) as e:
                logger.error(f"Error in IPC client: {e}")
                break
            except OSError:
                # Expected during shutdown — socket was closed via disconnect()
                if not self._running.is_set():
                    break
                logger.error("Unexpected OS error in IPC client")
                break
            except Exception as e:
                logger.error(f"Unexpected error in IPC client: {e}")
                break

    def send_message(self, message: Dict[str, Any]):
        """Enqueue a framed message for the server (never blocks)."""
        self._sender.put(message)

    def disconnect(self):
        """Disconnect from server."""
        self._running.clear()
        self._sender.stop()
        with self._lock:
            client_socket = self.client_socket
            self.client_socket = None
        if client_socket is not None:
            try:
                # Shut down the socket first to unblock any recv() calls
                # in the listener thread, preventing "Bad file descriptor".
                client_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client_socket.close()
        logger.info("IPC Client disconnected")
