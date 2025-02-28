# websockets_manager.py

import asyncio
import threading
import json
from typing import Dict, Set, Tuple

import redis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# ---------------------------
# 1) Redis Setup
# ---------------------------
# Adjust host, port, and DB as needed. In production, read from env vars/configs.
redis_client = redis.Redis(host="localhost", port=6379, db=0)

# For production with high concurrency or async, consider `aioredis`.
# For demonstration, we'll do simple sync usage + threads.

# ---------------------------
# 2) Data Structures
# ---------------------------
# We'll keep two separate dictionaries:
#  - connected_tasks:   Key = (username, taskId)  -> set of websockets
#  - connected_notifs:  Key = username            -> set of websockets

connected_tasks: Dict[Tuple[str, str], Set[WebSocket]] = {}
connected_notifs: Dict[str, Set[WebSocket]] = {}

# ---------------------------
# 3) Redis Pub/Sub Thread
# ---------------------------
def redis_listener():
    pubsub = redis_client.pubsub()
    pubsub.subscribe("task_updates")  # We'll handle all messages in one channel

    for msg in pubsub.listen():
        print(msg)
        if msg["type"] != "message":
            continue
        if not msg["data"]:
            continue
        data_str = msg["data"].decode("utf-8")
        asyncio.run(broadcast_message(data_str))

async def broadcast_message(data_str: str):
    """
    data_str is JSON, for example:
    {
      "type": "taskUpdate",
      "username": "123",
      "taskId": "abc",
      "message": "Done"
    }
    OR
    {
      "type": "notification",
      "username": "123",
      "message": "Task xyz completed!"
    }
    We'll parse and decide whether to send to (username, taskId) or username only.
    """
    try:
        payload = json.loads(data_str)
        username = payload["username"]
    except (ValueError, KeyError):
        print("Invalid message format:", data_str)
        return

    if "module_id" in payload and payload["module_id"]!="":
        task_id = payload["module_id"]
    else:
        task_id = payload.get("project_id", "")
        
    message = payload.get("state", "")
    key = (username, task_id)

    # Send to all websockets subscribed to (username, taskId)
    if key in connected_tasks:
        ws = connected_tasks[key]
        try:
            await ws.send_text(message)
        except Exception:
            connected_tasks[key].remove(ws)
    # Optionally remove empty sets to keep memory clean
    if key in connected_tasks and not connected_tasks[key]:
        del connected_tasks[key]

    # Send to all websockets subscribed to username notifications
    if username in connected_notifs:
        ws = connected_notifs[username]
        try:
            await ws.send_json(payload)
        except Exception:
            connected_notifs[username].remove(ws)
    
        
# ---------------------------
# 4) Task-Specific WebSocket
# ---------------------------
@router.websocket("/ws/tasks/{username}/{task_id}")
async def tasks_websocket(websocket: WebSocket, username: str, task_id: str):
    """
    WebSocket for a user to receive updates for a single task.
    E.g.: ws://.../ws/tasks/123/abc
    """
    await websocket.accept()
    key = (username, task_id)
    if key not in connected_tasks:
        connected_tasks[key] = websocket
    print(f"Connected: {key}")
    print("Connected tasks:", connected_tasks)
    try:
        while True:
            # We don't expect any messages from client side in this scenario,
            # but we need to read to keep the connection alive (ping/pong).
            await websocket.receive_text()
    except WebSocketDisconnect:
        if key in connected_tasks:
            del connected_tasks[key]

# ---------------------------
# 5) Notification WebSocket
# ---------------------------
@router.websocket("/ws/notifications/{username}")
async def notifications_websocket(websocket: WebSocket, username: str):
    """
    WebSocket for global notifications for a single user.
    E.g.: ws://.../ws/notifications/123
    """
    await websocket.accept()

    connected_notifs[username] = websocket
    print(f"Connected to notifications: {username}")
    print("Connected notifs:", connected_notifs)    
    

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if username in connected_notifs:
            del connected_notifs[username]

# ---------------------------
# 6) Startup Hook
# ---------------------------
# Typically, we'd start the Redis listener in your main app on startup
def start_redis_listener():
    t = threading.Thread(target=redis_listener, daemon=True)
    t.start()
