#!/usr/bin/env python3
"""
Test IPC Communication
Simple test to verify UNIX socket communication works
"""

import time
import threading
from core.ipc_communication import IPCServer, IPCClient


def test_ipc():
    """Test IPC server and client communication"""
    print("="*50)
    print("Testing IPC Communication")
    print("="*50)

    received_messages = []

    # Define message handlers
    def server_handler(message):
        print(f"[Server] Received: {message}")
        received_messages.append(('server', message))

    def client_handler(message):
        print(f"[Client] Received: {message}")
        received_messages.append(('client', message))

    # Start server in thread
    server = IPCServer()

    def run_server():
        server.start(message_callback=server_handler)
        server.listen()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    print("\n[Test] Server started")

    # Give server time to start
    time.sleep(1)

    # Start client
    client = IPCClient()
    print("[Test] Client connecting...")

    if not client.connect(timeout=5):
        print("[Test] FAILED: Client could not connect")
        server.stop()
        return False

    print("[Test] Client connected successfully")

    # Start client listener in thread
    def run_client():
        client.listen(message_callback=client_handler)

    client_thread = threading.Thread(target=run_client, daemon=True)
    client_thread.start()

    # Give client listener time to start
    time.sleep(0.5)

    # Test 1: Client sends to server
    print("\n[Test] Client sending messages to server...")
    client.send_message({"type": "rep_count", "value": 1})
    time.sleep(0.2)
    client.send_message({"type": "feedback", "value": "knees caving"})
    time.sleep(0.2)
    client.send_message({"type": "status", "value": "initialized"})
    time.sleep(0.5)

    # Test 2: Server sends to client
    print("\n[Test] Server sending messages to client...")
    server.send_message({"type": "command", "value": "start"})
    time.sleep(0.2)
    server.send_message({"type": "command", "value": "stop"})
    time.sleep(0.5)

    # Verify messages received
    print("\n" + "="*50)
    print("Test Results")
    print("="*50)

    server_received = [msg for sender, msg in received_messages if sender == 'server']
    client_received = [msg for sender, msg in received_messages if sender == 'client']

    print(f"\nServer received {len(server_received)} messages:")
    for msg in server_received:
        print(f"  - {msg}")

    print(f"\nClient received {len(client_received)} messages:")
    for msg in client_received:
        print(f"  - {msg}")

    # Cleanup
    client.disconnect()
    server.stop()

    # Check if test passed
    if len(server_received) >= 3 and len(client_received) >= 2:
        print("\n✓ Test PASSED: IPC communication working correctly")
        return True
    else:
        print("\n✗ Test FAILED: Not all messages were received")
        return False


if __name__ == "__main__":
    success = test_ipc()
    exit(0 if success else 1)
