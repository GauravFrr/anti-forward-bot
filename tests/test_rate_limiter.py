import asyncio
import time
from unittest.mock import AsyncMock, patch
from aiogram.exceptions import TelegramRetryAfter
from app.utils.retry import execute_post_with_rate_limit, execute_delete_with_retry
from app.services.media_buffer import redis_client

async def test_rate_limiter_and_retry():
    print("Starting rate limiter and retry backoff tests...")
    
    channel_id = 999111
    
    # Clean up Redis keys before testing
    await redis_client.delete(f"rate_limit:lock:{channel_id}")
    await redis_client.delete(f"rate_limit:last_sent:{channel_id}")

    # 1. Test Rate Limiting on Posts
    print("\n--- Test Case 1: Post Rate Limiting (Spacing spacing of ~3s) ---")
    
    mock_post_func = AsyncMock(return_value="post_success")
    
    async def worker(worker_id):
        t0 = time.time()
        res = await execute_post_with_rate_limit(channel_id, mock_post_func, worker_id)
        elapsed = time.time() - t0
        print(f"Worker {worker_id} finished in {elapsed:.2f}s with: {res}")
        return elapsed

    t_start = time.time()
    # Spawn 3 workers concurrently
    results = await asyncio.gather(
        worker(1),
        worker(2),
        worker(3)
    )
    total_elapsed = time.time() - t_start
    print(f"Total time elapsed for 3 posts: {total_elapsed:.2f}s")
    
    # Assertions:
    # Worker 1 runs immediately (~0s)
    # Worker 2 runs after 3s (~3s)
    # Worker 3 runs after 6s (~6s)
    # Total time should be at least 6.0s
    assert total_elapsed >= 6.0, f"Expected total elapsed time >= 6.0s, got {total_elapsed:.2f}s"
    assert mock_post_func.call_count == 3
    print("Verified: Posts are properly serialized and spaced out by 3.0s per channel.")

    # 2. Test No Rate Limiting on Deletes
    print("\n--- Test Case 2: Delete operations (No artificial rate limit) ---")
    mock_delete_func = AsyncMock(return_value="delete_success")
    
    async def delete_worker(worker_id):
        t0 = time.time()
        res = await execute_delete_with_retry(mock_delete_func, worker_id)
        elapsed = time.time() - t0
        print(f"Delete Worker {worker_id} finished in {elapsed:.4f}s")
        return elapsed

    t_start_delete = time.time()
    # Spawn 5 delete workers concurrently
    delete_results = await asyncio.gather(
        delete_worker(1),
        delete_worker(2),
        delete_worker(3),
        delete_worker(4),
        delete_worker(5)
    )
    total_elapsed_delete = time.time() - t_start_delete
    print(f"Total time elapsed for 5 deletes: {total_elapsed_delete:.4f}s")
    
    # Assertions:
    # All deletes should run concurrently and finish instantly (well under 1 second total)
    assert total_elapsed_delete < 1.0, f"Expected deletes to bypass rate limiting, got {total_elapsed_delete:.2f}s"
    assert mock_delete_func.call_count == 5
    print("Verified: Deletes bypass the rate-limiter and execute immediately.")

    # 3. Test Tenacity Retry on TelegramRetryAfter
    print("\n--- Test Case 3: Tenacity retry with TelegramRetryAfter (429) ---")
    
    mock_fail_then_succeed = AsyncMock()
    # Mock behavior: raise TelegramRetryAfter on 1st call, succeed on 2nd call
    # TelegramRetryAfter expects method, message, and retry_after
    error_429 = TelegramRetryAfter(
        method=AsyncMock(),
        message="Flood control",
        retry_after=2  # Wait 2 seconds
    )
    mock_fail_then_succeed.side_effect = [error_429, "retry_success"]
    
    # Clean Redis key to run immediately first
    await redis_client.delete(f"rate_limit:last_sent:{channel_id}")
    
    t_start_retry = time.time()
    res = await execute_post_with_rate_limit(channel_id, mock_fail_then_succeed)
    total_elapsed_retry = time.time() - t_start_retry
    print(f"Total time elapsed for retry: {total_elapsed_retry:.2f}s, result: {res}")
    
    # Assertions:
    # Call 1: Runs, hits 429, sleeps for 2 seconds.
    # Call 2: Runs, succeeds.
    # Total time should be around 2.0s (+ minor overhead, but < 3.0s because rate-limiter allows first attempt)
    assert total_elapsed_retry >= 2.0, f"Expected elapsed time >= 2.0s, got {total_elapsed_retry:.2f}s"
    assert mock_fail_then_succeed.call_count == 2
    print("Verified: Tenacity retries after waiting the exact retry_after duration.")

    # Cleanup Redis
    await redis_client.delete(f"rate_limit:lock:{channel_id}")
    await redis_client.delete(f"rate_limit:last_sent:{channel_id}")
    print("\nAll rate-limiter and retry tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_rate_limiter_and_retry())
