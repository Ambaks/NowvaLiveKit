"""
IPC Communication Module
UNIX domain socket communication between voice agent and pose estimation
"""

import socket
import json
import os
import threading
from typing import Callable, Optional, Dict, Any


class IPCServer:
    """IPC Server using UNIX domain sockets"""

    def __init__(self, socket_path: str = "/tmp/nowva_ipc.sock"):
        """
        Initialize IPC server

        Args:
            socket_path: Path to UNIX domain socket
        """
        self.socket_path = socket_path
        self.server_socket = None
        self.client_socket = None
        self.running = False
        self.message_callback: Optional[Callable[[Dict], None]] = None

    def start(self, message_callback: Optional[Callable[[Dict], None]] = None):
        """
        Start IPC server

        Args:
            message_callback: Function to call when message is received
        """
        # Remove existing socket file
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

        # Create socket
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.socket_path)
        self.server_socket.listen(1)

        self.running = True
        self.message_callback = message_callback

        print(f"IPC Server started on {self.socket_path}")

        # Accept connection (blocking)
        print("Waiting for client connection...")
        self.client_socket, _ = self.server_socket.accept()
        print("Client connected!")

    def listen(self):
        """Listen for incoming messages in a loop"""
        if not self.client_socket:
            print("No client connected")
            return

        while self.running:
            try:
                data = self.client_socket.recv(4096)
                if not data:
                    break

                message = json.loads(data.decode('utf-8'))
                print(f"IPC Server received: {message}")

                if self.message_callback:
                    self.message_callback(message)

            except json.JSONDecodeError as e:
                print(f"Error decoding message: {e}")
            except Exception as e:
                print(f"Error in IPC server: {e}")
                break

    def send_message(self, message: Dict[str, Any]):
        """Send message to connected client"""
        if not self.client_socket:
            print("No client connected")
            return

        try:
            data = json.dumps(message).encode('utf-8')
            self.client_socket.sendall(data)
            print(f"IPC Server sent: {message}")
        except Exception as e:
            print(f"Error sending message: {e}")

    def stop(self):
        """Stop IPC server"""
        self.running = False
        if self.client_socket:
            self.client_socket.close()
        if self.server_socket:
            self.server_socket.close()
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        print("IPC Server stopped")


class IPCClient:
    """IPC Client using UNIX domain sockets"""

    def __init__(self, socket_path: str = "/tmp/nowva_ipc.sock"):
        """
        Initialize IPC client

        Args:
            socket_path: Path to UNIX domain socket
        """
        self.socket_path = socket_path
        self.client_socket = None
        self.running = False
        self.message_callback: Optional[Callable[[Dict], None]] = None

    def connect(self, timeout: int = 10):
        """
        Connect to IPC server

        Args:
            timeout: Connection timeout in seconds
        """
        import time
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                self.client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.client_socket.connect(self.socket_path)
                self.running = True
                print(f"IPC Client connected to {self.socket_path}")
                return True
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.5)

        print(f"Failed to connect to IPC server after {timeout}s")
        return False

    def listen(self, message_callback: Optional[Callable[[Dict], None]] = None):
        """
        Listen for incoming messages

        Args:
            message_callback: Function to call when message is received
        """
        if not self.client_socket:
            print("Not connected to server")
            return

        self.message_callback = message_callback

        while self.running:
            try:
                data = self.client_socket.recv(4096)
                if not data:
                    break

                message = json.loads(data.decode('utf-8'))
                print(f"IPC Client received: {message}")

                if self.message_callback:
                    self.message_callback(message)

            except json.JSONDecodeError as e:
                print(f"Error decoding message: {e}")
            except Exception as e:
                print(f"Error in IPC client: {e}")
                break

    def send_message(self, message: Dict[str, Any]):
        """Send message to server"""
        if not self.client_socket:
            print("Not connected to server")
            return

        try:
            data = json.dumps(message).encode('utf-8')
            self.client_socket.sendall(data)
            print(f"IPC Client sent: {message}")
        except Exception as e:
            print(f"Error sending message: {e}")

    def disconnect(self):
        """Disconnect from server"""
        self.running = False
        if self.client_socket:
            self.client_socket.close()
        print("IPC Client disconnected")
