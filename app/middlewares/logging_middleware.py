import time
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from loguru import logger

class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        t0 = time.time()
        
        # Determine the class/type of the incoming update
        event_type = type(event).__name__
        chat_id = None
        user_id = None
        
        # Try to safely extract chat/user ID details
        if hasattr(event, "chat"):
            chat_id = getattr(event.chat, "id", None)
        if hasattr(event, "from_user"):
            user_id = getattr(event.from_user, "id", None)
            
        logger.info(f"Incoming Update: {event_type} | Chat ID: {chat_id} | User ID: {user_id}")
        
        try:
            res = await handler(event, data)
            elapsed = time.time() - t0
            logger.info(f"Finished processing Update: {event_type} in {elapsed:.4f}s")
            return res
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"Failed processing Update: {event_type} in {elapsed:.4f}s with error: {e}")
            raise
