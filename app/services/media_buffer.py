import json
from typing import List, Dict, Any
from redis.asyncio import Redis
from app.config import settings

# Initialize async Redis client
redis_client: Redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)

async def add_media_group_part(media_group_id: str, part_data: Dict[str, Any]) -> None:
    """
    Appends a media group part (serialized) to the Redis list for this media_group_id.
    Sets a 60-second expiration to prevent memory leaks.
    """
    key = f"media_group:parts:{media_group_id}"
    await redis_client.rpush(key, json.dumps(part_data))
    await redis_client.expire(key, 60)

async def set_last_arrival(media_group_id: str, timestamp: float) -> None:
    """
    Updates the latest arrival timestamp in Redis for this media_group_id.
    Sets a 60-second expiration.
    """
    key = f"media_group:last_time:{media_group_id}"
    await redis_client.set(key, str(timestamp), ex=60)

async def get_last_arrival(media_group_id: str) -> float | None:
    """
    Retrieves the latest arrival timestamp from Redis.
    """
    key = f"media_group:last_time:{media_group_id}"
    val = await redis_client.get(key)
    return float(val) if val else None

async def get_and_clear_buffer(media_group_id: str) -> List[Dict[str, Any]]:
    """
    Retrieves all buffered parts for this media_group_id and deletes the Redis keys.
    """
    parts_key = f"media_group:parts:{media_group_id}"
    time_key = f"media_group:last_time:{media_group_id}"
    
    parts_json = await redis_client.lrange(parts_key, 0, -1)
    parts = [json.loads(p) for p in parts_json]
    
    # Clean up keys
    await redis_client.delete(parts_key, time_key)
    
    return parts
