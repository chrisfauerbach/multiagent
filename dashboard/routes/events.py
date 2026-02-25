from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from shared.config_loader import load_pipeline_config
from shared.constants import ACTIVITY_CHANNEL

router = APIRouter()


async def _event_generator(request: Request):
    import redis

    config = load_pipeline_config()["redis"]
    client = redis.Redis(
        host=config["host"],
        port=config["port"],
        db=config["db"],
        decode_responses=True,
    )
    pubsub = client.pubsub()
    pubsub.subscribe(ACTIVITY_CHANNEL)

    try:
        # Send retry hint for browser reconnection
        yield "retry: 3000\n\n"

        heartbeat_interval = 15
        elapsed = 0.0
        poll_interval = 1.0

        while True:
            if await request.is_disconnected():
                break

            msg = await asyncio.to_thread(
                pubsub.get_message, ignore_subscribe_messages=True, timeout=poll_interval
            )

            if msg and msg["type"] == "message":
                data = msg["data"]
                # Validate it's JSON before sending
                try:
                    json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    data = json.dumps({"raw": str(data)})
                yield f"data: {data}\n\n"
                elapsed = 0.0
            else:
                elapsed += poll_interval
                if elapsed >= heartbeat_interval:
                    yield ": heartbeat\n\n"
                    elapsed = 0.0
    except Exception:
        # Redis error — client will reconnect via retry header
        pass
    finally:
        try:
            pubsub.unsubscribe()
            pubsub.close()
            client.close()
        except Exception:
            pass


@router.get("/api/events/stream")
async def event_stream(request: Request):
    return StreamingResponse(
        _event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
