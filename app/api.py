from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import asyncio
from datetime import datetime
from loguru import logger

from app.config import settings
from app.db.base import async_session_maker
from app.db.models import Channel, EventLog, ChannelStatus
from app.db.crud import get_global_stats
from app.utils.twa_auth import verify_telegram_webapp_data
from app.bot_instance import bot

app = FastAPI(title="Anti-Forward Bot API")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_db():
    async with async_session_maker() as session:
        yield session

async def get_current_user(x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data")) -> dict:
    user = verify_telegram_webapp_data(x_telegram_init_data)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid Telegram WebApp session")
    return user

class ChannelSettingsUpdate(BaseModel):
    custom_footer: str | None
    auto_pin_enabled: bool
    queue_enabled: bool
    queue_interval_minutes: int

class BroadcastRequest(BaseModel):
    message: str

@app.get("/api/me")
async def get_me(user: dict = Depends(get_current_user)):
    user_id = user.get("id")
    is_owner = (user_id == settings.OWNER_ID)
    return {
        "id": user_id,
        "first_name": user.get("first_name"),
        "username": user.get("username"),
        "is_owner": is_owner
    }

@app.get("/api/stats")
async def get_stats(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.get("id") != settings.OWNER_ID:
        raise HTTPException(status_code=403, detail="Restricted to bot owner")
    
    stats = await get_global_stats(db)
    
    # Query logs
    success_result = await db.execute(select(func.count(EventLog.id)).where(EventLog.success == True))
    success_count = success_result.scalar() or 0
    fail_result = await db.execute(select(func.count(EventLog.id)).where(EventLog.success == False))
    fail_count = fail_result.scalar() or 0

    stats["successful_messages"] = success_count
    stats["failed_messages"] = fail_count
    return stats

@app.get("/api/channels")
async def get_channels(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user_id = user.get("id")
    is_owner = (user_id == settings.OWNER_ID)
    
    if is_owner:
        result = await db.execute(select(Channel).order_by(Channel.created_at.desc()))
    else:
        result = await db.execute(select(Channel).where(Channel.owner_user_id == user_id).order_by(Channel.created_at.desc()))
        
    channels = result.scalars().all()
    return [
        {
            "id": ch.id,
            "channel_id": ch.channel_id,
            "owner_user_id": ch.owner_user_id,
            "title": ch.title,
            "status": ch.status.value,
            "custom_footer": ch.custom_footer,
            "auto_pin_enabled": ch.auto_pin_enabled,
            "queue_enabled": ch.queue_enabled,
            "queue_interval_minutes": ch.queue_interval_minutes,
            "created_at": ch.created_at
        }
        for ch in channels
    ]

@app.post("/api/channels/{ch_id}/settings")
async def update_settings(
    ch_id: int,
    payload: ChannelSettingsUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user_id = user.get("id")
    is_owner = (user_id == settings.OWNER_ID)
    
    # Find channel by DB primary key ID
    result = await db.execute(select(Channel).where(Channel.id == ch_id))
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    # Security check
    if not is_owner and ch.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this channel")
        
    ch.custom_footer = payload.custom_footer
    ch.auto_pin_enabled = payload.auto_pin_enabled
    ch.queue_enabled = payload.queue_enabled
    ch.queue_interval_minutes = payload.queue_interval_minutes
    
    await db.commit()
    return {"success": True}

@app.post("/api/broadcast")
async def trigger_broadcast(
    payload: BroadcastRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if user.get("id") != settings.OWNER_ID:
        raise HTTPException(status_code=403, detail="Restricted to bot owner")
        
    from app.db.crud import get_all_users
    users = await get_all_users(db)
    if not users:
        return {"total": 0, "success": 0, "fail": 0}
        
    # Run broadcast in background
    async def run_bg_broadcast(msg: str):
        success, fail = 0, 0
        for u in users:
            try:
                await bot.send_message(chat_id=u.user_id, text=msg, parse_mode="HTML")
                success += 1
            except Exception as e:
                logger.warning(f"TWA Broadcast failed to user {u.user_id}: {e}")
                fail += 1
            await asyncio.sleep(0.05)
        logger.info(f"TWA Broadcast finished: total={len(users)}, success={success}, fail={fail}")
        
    asyncio.create_task(run_bg_broadcast(payload.message))
    return {"started": True, "total_users": len(users)}

# We will mount static files index.html at root later
