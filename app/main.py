import sys
import asyncio
from loguru import logger
from app.config import settings
from app.bot_instance import bot, dp
from app.middlewares.logging_middleware import LoggingMiddleware
from app.middlewares.error_handler import ErrorHandlerMiddleware
from app.middlewares.db_session import DbSessionMiddleware
from app.handlers.chat_member import router as chat_member_router
from app.handlers.channel_posts import router as channel_posts_router
from app.handlers.commands import router as commands_router

# Configure loguru logger
logger.remove()  # Remove default handler
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=settings.LOG_LEVEL
)
logger.add(
    "logs/bot.log",
    rotation="1 day",
    retention="14 days",
    level=settings.LOG_LEVEL,
    compression="zip"
)

async def main():
    logger.info("Starting Anti-Forward Telegram Bot...")
    try:
        # Register global middlewares in correct outer-to-inner order
        dp.update.outer_middleware(LoggingMiddleware())
        dp.update.outer_middleware(ErrorHandlerMiddleware())
        dp.update.outer_middleware(DbSessionMiddleware())
        
        # Register handlers
        dp.include_router(chat_member_router)
        dp.include_router(channel_posts_router)
        dp.include_router(commands_router)
        
        # Resolve any dependency healthcheck here later
        await dp.start_polling(bot)
    except Exception as e:
        logger.exception("Failed to start or run bot polling dispatcher")
    finally:
        await bot.session.close()
        logger.info("Bot stopped and session closed.")

if __name__ == "__main__":
    asyncio.run(main())


