#!/usr/bin/env python3
"""
Browser Interpreter Runner
Simple WebSocket server that serves HTML and relays commands to browser.
NO interpretation logic - just a relay.
"""

import asyncio
import json
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connected clients
clients = set()



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint - just relay messages to all clients."""
    await websocket.accept()
    clients.add(websocket)
    print(f"Client connected. Total clients: {len(clients)}")
    
    try:
        while True:
            # Receive from any client (realtime_listen.py or browser)
            print("Waiting for message...")
            data = await websocket.receive_json()
            print(f"Received message: {data}")
            
            # Broadcast to all other clients
            await broadcast(data, exclude=websocket)
    
    except WebSocketDisconnect:
        clients.remove(websocket)
        print(f"Client disconnected. Total clients: {len(clients)}")


async def broadcast(message, exclude=None):
    """Broadcast message to all connected clients except the sender."""
    print(f"Broadcasting message: {message}")
    disconnected = set()
    for client in clients:
        if client == exclude:
            continue
        try:
            await client.send_json(message)
        except:
            disconnected.add(client)
    
    # Remove disconnected clients
    for client in disconnected:
        clients.discard(client)


if __name__ == "__main__":
    print("="*60)
    print("BROWSER INTERPRETER SERVER")
    print("="*60)
    print("Starting server at http://localhost:8000")
    print("\nFor OBS:")
    print("  1. Add 'Browser' source")
    print("  2. URL: http://127.0.0.1:8000")
    print("  3. Width: 1920, Height: 1080")
    print("\nThe server relays commands from realtime_listen.py to browser.")
    print("Browser executes commands via eval().")
    print("="*60)
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
