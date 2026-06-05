#!/usr/bin/env python3
"""Check if websocket events are being published to Redis."""
import asyncio
import redis.asyncio as redis

async def main():
    r = redis.from_url("redis://localhost:6379/0", decode_responses=True)
    pubsub = r.pubsub()
    
    # Subscribe to the sharekhan:ticks channel
    await pubsub.subscribe("sharekhan:ticks")
    print("Listening for sharekhan:ticks events... (Ctrl+C to stop)")
    print()
    
    message_count = 0
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                message_count += 1
                print(f"[{message_count}] {message['data'][:100]}")
    except KeyboardInterrupt:
        print("\nStopped listening")
    finally:
        await pubsub.aclose()
        await r.aclose()

if __name__ == "__main__":
    asyncio.run(main())
