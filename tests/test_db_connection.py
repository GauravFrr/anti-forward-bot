import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import engine, async_session_maker
from app.db.models import Base, ChannelStatus
from app.db.crud import create_or_update_channel, get_channel, log_event, get_global_stats

async def test_db():
    print("Testing database connection and CRUD operations...")
    
    # 1. Open a session
    async with async_session_maker() as session:
        # 2. Insert/upsert a channel
        channel_id = -1001234567890
        owner_id = 987654321
        title = "Test Channel"
        
        print(f"Upserting channel {channel_id}...")
        channel = await create_or_update_channel(
            session=session,
            channel_id=channel_id,
            owner_user_id=owner_id,
            title=title,
            status=ChannelStatus.ACTIVE
        )
        print(f"Channel upserted successfully: ID={channel.id}, Title={channel.title}, Status={channel.status}")
        
        # 3. Retrieve the channel
        print("Retrieving channel...")
        fetched = await get_channel(session, channel_id)
        assert fetched is not None, "Failed to retrieve channel"
        print(f"Fetched channel: {fetched.title} ({fetched.status})")
        
        # 4. Log an event
        print("Logging a test event...")
        event = await log_event(
            session=session,
            channel_id=channel_id,
            message_type="text",
            success=True
        )
        assert event is not None, "Failed to log event"
        print(f"Logged event successfully: ID={event.id}, Type={event.message_type}, Success={event.success}")
        
        # 5. Retrieve global stats
        print("Retrieving global stats...")
        stats = await get_global_stats(session)
        print(f"Stats: {stats}")
        
        # 6. Cleanup (delete the test channel and its cascaded logs)
        print("Cleaning up test data...")
        await session.delete(fetched)
        await session.commit()
        print("Cleanup completed successfully.")
        
    print("Database verification completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_db())
