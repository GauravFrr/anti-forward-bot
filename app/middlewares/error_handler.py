from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from loguru import logger

class ErrorHandlerMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            event_type = type(event).__name__
            logger.exception(f"Unhandled exception caught in global ErrorHandlerMiddleware during {event_type} processing: {e}")
            # Return None to suppress the exception and prevent the dispatcher from crashing/failing
            return None
