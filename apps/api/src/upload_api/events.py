from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict

from fastapi import WebSocket


class JobEventBus:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, job_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[job_id].add(websocket)

    async def disconnect(self, job_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(job_id)
            if not conns:
                return
            conns.discard(websocket)
            if not conns:
                self._connections.pop(job_id, None)

    async def publish(self, job_id: uuid.UUID, payload: dict) -> None:
        async with self._lock:
            conns = list(self._connections.get(job_id, set()))
        if not conns:
            return
        text = json.dumps(payload, default=str)
        stale: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(text)
            except Exception:
                stale.append(ws)
        if stale:
            async with self._lock:
                active = self._connections.get(job_id)
                if not active:
                    return
                for ws in stale:
                    active.discard(ws)
                if not active:
                    self._connections.pop(job_id, None)
