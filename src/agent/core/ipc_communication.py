"""
IPC Communication Module
UNIX domain socket communication between voice agent and pose estimation.

Uses 4-byte length-prefix framing to ensure complete message delivery:
  [4-byte big-endian length][JSON payload bytes]
This prevents message corruption when multiple messages arrive in one recv() call
or when a single message spans multiple recv() calls.
"""

import socket
import struct
import json
import os
import logging
from typing import Callable, Optional, Dict, Any

logger = logging.getLogger(__name__)

# 4-byte unsigned big-endian header for message length
HEADER_FORMAT = ">I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_MESSAGE_SIZE = 1024 * 1024  # 1MB safety limit


def _send_framed(sock: socket.socket, message: Dict[str, Any]) -> None:
    """Send a length-prefixed JSON message over a socket."""
    data = json.dumps(message).encode('utf-8')
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


class IPCServer:
    """IPC Server using UNIX domain sockets with length-prefix framing"""

    def __init__(self, socket_path: str = "/tmp/nowva_ipc.sock"):
        self.socket_path = socket_path
        self.server_socket = None
        self.client_socket = None
        self.running = False
        self.message_callback: Optional[Callable[[Dict], None]] = None

    def bind(self, message_callback: Optional[Callable[[Dict], None]] = None):
        """Create and bind the server socket. Connectable immediately after return."""
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.socket_path)
        self.server_socket.listen(1)

        self.running = True
        self.message_callback = message_callback

        logger.info(f"IPC Server bound on {self.socket_path}")

    def accept_client(self):
        """Block until a client connects. Call after bind()."""
        logger.info("Waiting for client connection...")
        self.client_socket, _ = self.server_socket.accept()
        logger.info("Client connected!")

    def start(self, message_callback: Optional[Callable[[Dict], None]] = None):
        """Bind and wait for a client connection (convenience wrapper)."""
        self.bind(message_callback)
        self.accept_client()

    def listen(self):
        """Listen for incoming framed messages in a loop."""
        if not self.client_socket:
            logger.warning("No client connected")
            return

        while self.running:
            try:
                message = _recv_framed(self.client_socket)
                if message is None:
                    logger.info("Client disconnected")
                    break

                if self.message_callback:
                    self.message_callback(message)

            except json.JSONDecodeError as e:
                logger.error(f"Error decoding message: {e}")
            except (ConnectionError, ValueError) as e:
                logger.error(f"Error in IPC server: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in IPC server: {e}")
                break

    def send_message(self, message: Dict[str, Any]):
        """Send a framed message to the connected client."""
        if not self.client_socket:
            logger.warning("No client connected")
            return

        try:
            _send_framed(self.client_socket, message)
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    def stop(self):
        """Stop IPC server and clean up socket file."""
        self.running = False
        if self.client_socket:
            self.client_socket.close()
        if self.server_socket:
            self.server_socket.close()
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        logger.info("IPC Server stopped")


class IPCClient:
    """IPC Client using UNIX domain sockets with length-prefix framing"""

    def __init__(self, socket_path: str = "/tmp/nowva_ipc.sock"):
        self.socket_path = socket_path
        self.client_socket = None
        self.running = False
        self.message_callback: Optional[Callable[[Dict], None]] = None

    def connect(self, timeout: int = 10):
        """Connect to IPC server with retry."""
        import time
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                self.client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.client_socket.connect(self.socket_path)
                self.running = True
                logger.info(f"IPC Client connected to {self.socket_path}")
                return True
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.5)

        logger.error(f"Failed to connect to IPC server after {timeout}s")
        return False

    def listen(self, message_callback: Optional[Callable[[Dict], None]] = None):
        """Listen for incoming framed messages."""
        if not self.client_socket:
            logger.warning("Not connected to server")
            return

        self.message_callback = message_callback

        while self.running:
            try:
                message = _recv_framed(self.client_socket)
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
                if not self.running:
                    break
                logger.error("Unexpected OS error in IPC client")
                break
            except Exception as e:
                logger.error(f"Unexpected error in IPC client: {e}")
                break

    def send_message(self, message: Dict[str, Any]):
        """Send a framed message to the server."""
        if not self.client_socket:
            logger.warning("Not connected to server")
            return

        try:
            _send_framed(self.client_socket, message)
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    def disconnect(self):
        """Disconnect from server."""
        self.running = False
        if self.client_socket:
            try:
                # Shut down the socket first to unblock any recv() calls
                # in the listener thread, preventing "Bad file descriptor".
                self.client_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.client_socket.close()
        logger.info("IPC Client disconnected")
