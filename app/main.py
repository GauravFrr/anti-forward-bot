import sys
import asyncio
from loguru import logger
import uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from app.config import settings
from app.bot_instance import bot, dp
from app.api import app

# Middlewares
from app.middlewares.logging_middleware import LoggingMiddleware
from app.middlewares.error_handler import ErrorHandlerMiddleware
from app.middlewares.db_session import DbSessionMiddleware

# Handlers
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

# Serve the static Telegram Web App index at root
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        return f.read()

# Mount static files (style.css, app.js)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

routers_registered = False
polling_task = None
queue_task = None

@app.on_event("startup")
async def on_startup():
    global polling_task, queue_task, routers_registered
    if routers_registered:
        logger.info("Routers already registered. Skipping startup hooks.")
        return
        
    logger.info("Initializing bot and registering handlers...")
    
    # Register global middlewares in correct outer-to-inner order
    dp.update.outer_middleware(LoggingMiddleware())
    dp.update.outer_middleware(ErrorHandlerMiddleware())
    dp.update.outer_middleware(DbSessionMiddleware())
    
    # Register handlers
    dp.include_router(chat_member_router)
    dp.include_router(channel_posts_router)
    dp.include_router(commands_router)
    
    # Run the aiogram bot polling dispatcher loop as an asynchronous background task
    async def bot_polling():
        logger.info("Starting Anti-Forward Telegram Bot polling loop...")
        try:
            await dp.start_polling(bot)
        except Exception as e:
            logger.exception("Bot polling loop encountered an error")
        finally:
            await bot.session.close()
            logger.info("Bot session closed.")

    polling_task = asyncio.create_task(bot_polling())

    # Start the background queue processor loop
    from app.services.queue_worker import queue_processor_loop
    queue_task = asyncio.create_task(queue_processor_loop(bot))
    
    routers_registered = True

@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Shutting down services...")
    if polling_task:
        polling_task.cancel()
    if queue_task:
        queue_task.cancel()
        
    try:
        if polling_task:
            await polling_task
    except asyncio.CancelledError:
        pass
    try:
        if queue_task:
            await queue_task
    except asyncio.CancelledError:
        pass
    logger.info("FastAPI, Bot polling, and Queue processor stopped.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
