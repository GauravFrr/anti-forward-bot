import asyncio
import time
from loguru import logger
from app.services.media_buffer import redis_client

async def acquire_rate_limit(channel_id: int) -> None:
    """
    Acquires a per-channel lock and ensures at least 3.0 seconds have passed
    since the last message was sent in this channel. If not, it sleeps to delay the send.
    """
    lock_key = f"rate_limit:lock:{channel_id}"
    last_sent_key = f"rate_limit:last_sent:{channel_id}"
    
    # Acquire a Redis lock (timeout=10 to prevent deadlock if process crashes)
    lock = redis_client.lock(lock_key, timeout=10)
    async with lock:
        last_sent_str = await redis_client.get(last_sent_key)
        now = time.time()
        
        if last_sent_str:
            last_sent = float(last_sent_str)
            time_passed = now - last_sent
            if time_passed < 3.0:
                wait_time = 3.0 - time_passed
                logger.info(f"Rate limiting channel {channel_id}: waiting {wait_time:.2f}s before sending...")
                await asyncio.sleep(wait_time)
                now = time.time()  # Update current timestamp after waiting
                
        # Save the timestamp of this send
        await redis_client.set(last_sent_key, str(now), ex=60)
