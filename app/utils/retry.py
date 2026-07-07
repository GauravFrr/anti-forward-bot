import tenacity
from aiogram.exceptions import TelegramRetryAfter
from loguru import logger
from app.services.rate_limiter import acquire_rate_limit

def wait_retry_after(retry_state: tenacity.RetryCallState) -> float:
    """
    Custom tenacity wait strategy that reads the TelegramRetryAfter exception's
    retry_after value and sleeps for exactly that duration. Falls back to 1.0s.
    """
    if retry_state.outcome and retry_state.outcome.failed:
        exc = retry_state.outcome.exception()
        if isinstance(exc, TelegramRetryAfter):
            logger.warning(f"Telegram rate limit hit (429)! Waiting {exc.retry_after} seconds before retrying...")
            return float(exc.retry_after)
    return 1.0

# Post wrapper: decorated to retry, calls acquire_rate_limit before execution
@tenacity.retry(
    retry=tenacity.retry_if_exception_type(TelegramRetryAfter),
    wait=wait_retry_after,
    stop=tenacity.stop_after_attempt(5),
    reraise=True
)
async def _post_retry_wrapper(channel_id: int, func, *args, **kwargs):
    await acquire_rate_limit(channel_id)
    return await func(*args, **kwargs)

async def execute_post_with_rate_limit(channel_id: int, func, *args, **kwargs):
    """
    Executes a posting function, ensuring the per-channel 3s rate-limit is acquired
    on every attempt, and retries up to 5 times if a TelegramRetryAfter error occurs.
    """
    return await _post_retry_wrapper(channel_id, func, *args, **kwargs)

# Delete wrapper: decorated to retry, bypasses rate limiting
@tenacity.retry(
    retry=tenacity.retry_if_exception_type(TelegramRetryAfter),
    wait=wait_retry_after,
    stop=tenacity.stop_after_attempt(5),
    reraise=True
)
async def _delete_retry_wrapper(func, *args, **kwargs):
    return await func(*args, **kwargs)

async def execute_delete_with_retry(func, *args, **kwargs):
    """
    Executes a delete/cleanup function immediately, and retries up to 5 times
    if a TelegramRetryAfter error occurs. Bypasses the rate-limiting spacing.
    """
    return await _delete_retry_wrapper(func, *args, **kwargs)
