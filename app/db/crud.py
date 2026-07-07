from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Channel, ChannelStatus, EventLog

async def get_channel(session: AsyncSession, channel_id: int) -> Channel | None:
    result = await session.execute(
        select(Channel).where(Channel.channel_id == channel_id)
    )
    return result.scalar_one_or_none()

async def get_channels_by_owner(session: AsyncSession, owner_user_id: int) -> list[Channel]:
    result = await session.execute(
        select(Channel).where(Channel.owner_user_id == owner_user_id)
    )
    return list(result.scalars().all())

async def create_or_update_channel(
    session: AsyncSession,
    channel_id: int,
    owner_user_id: int,
    title: str | None,
    status: ChannelStatus = ChannelStatus.ACTIVE
) -> Channel:
    channel = await get_channel(session, channel_id)
    if channel:
        channel.owner_user_id = owner_user_id
        channel.title = title
        channel.status = status
    else:
        channel = Channel(
            channel_id=channel_id,
            owner_user_id=owner_user_id,
            title=title,
            status=status
        )
        session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return channel

async def update_channel_status(
    session: AsyncSession,
    channel_id: int,
    status: ChannelStatus
) -> bool:
    channel = await get_channel(session, channel_id)
    if channel:
        channel.status = status
        await session.commit()
        return True
    return False

async def log_event(
    session: AsyncSession,
    channel_id: int,
    message_type: str,
    success: bool
) -> EventLog | None:
    channel = await get_channel(session, channel_id)
    if not channel:
        return None
    
    event = EventLog(
        channel_id=channel.id,
        message_type=message_type,
        success=success
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event

async def get_global_stats(session: AsyncSession) -> dict:
    # Count channels
    channels_count_result = await session.execute(select(func.count(Channel.id)))
    total_channels = channels_count_result.scalar() or 0

    # Count active channels
    active_count_result = await session.execute(
        select(func.count(Channel.id)).where(Channel.status == ChannelStatus.ACTIVE)
    )
    active_channels = active_count_result.scalar() or 0

    # Count total events log
    total_events_result = await session.execute(select(func.count(EventLog.id)))
    total_messages = total_events_result.scalar() or 0

    # Count successful events log
    success_events_result = await session.execute(
        select(func.count(EventLog.id)).where(EventLog.success == True)
    )
    successful_messages = success_events_result.scalar() or 0

    return {
        "total_channels": total_channels,
        "active_channels": active_channels,
        "total_messages": total_messages,
        "successful_messages": successful_messages
    }
