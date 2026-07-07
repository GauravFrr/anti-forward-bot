from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Channel, ChannelStatus, EventLog, User, QueuePost

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

    # Count users
    users_count_result = await session.execute(select(func.count(User.id)))
    total_users = users_count_result.scalar() or 0

    return {
        "total_channels": total_channels,
        "active_channels": active_channels,
        "total_messages": total_messages,
        "successful_messages": successful_messages,
        "total_users": total_users
    }

async def get_user(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(
        select(User).where(User.user_id == user_id)
    )
    return result.scalar_one_or_none()

async def create_or_update_user(
    session: AsyncSession,
    user_id: int,
    username: str | None,
    first_name: str | None
) -> User:
    user = await get_user(session, user_id)
    if user:
        user.username = username
        user.first_name = first_name
        user.last_seen_at = func.now()
    else:
        user = User(
            user_id=user_id,
            username=username,
            first_name=first_name
        )
        session.add(user)
    await session.commit()
    await session.refresh(user)
    return user

async def get_total_users_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(User.id)))
    return result.scalar() or 0

async def get_active_channels_sorted(session: AsyncSession, limit: int = 20) -> list[tuple[Channel, int]]:
    result = await session.execute(
        select(Channel, func.count(EventLog.id))
        .outerjoin(EventLog, Channel.id == EventLog.channel_id)
        .group_by(Channel.id)
        .order_by(func.count(EventLog.id).desc())
        .limit(limit)
    )
    return [(row[0], row[1]) for row in result.all()]

async def find_user_by_query(session: AsyncSession, query_str: str) -> User | None:
    try:
        uid = int(query_str)
        result = await session.execute(select(User).where(User.user_id == uid))
        return result.scalar_one_or_none()
    except ValueError:
        clean_username = query_str.lstrip('@')
        result = await session.execute(
            select(User).where(User.username.ilike(clean_username))
        )
        return result.scalar_one_or_none()

async def get_all_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User))
    return list(result.scalars().all())

async def get_all_channels(session: AsyncSession) -> list[Channel]:
    result = await session.execute(select(Channel))
    return list(result.scalars().all())

async def add_to_queue(
    session: AsyncSession,
    channel_id: int,
    message_data: str,
    scheduled_for: datetime
) -> QueuePost:
    post = QueuePost(
        channel_id=channel_id,
        message_data=message_data,
        scheduled_for=scheduled_for
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post

async def get_pending_queue_posts(session: AsyncSession) -> list[QueuePost]:
    result = await session.execute(
        select(QueuePost)
        .where(QueuePost.is_processed == False)
        .where(QueuePost.scheduled_for <= func.now())
        .order_by(QueuePost.scheduled_for.asc())
    )
    return list(result.scalars().all())

