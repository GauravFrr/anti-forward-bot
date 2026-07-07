import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime

from aiogram import Bot
from aiogram.types import Chat, Message, MessageOriginUser, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session_maker
from app.db.models import ChannelStatus
from app.db.crud import get_channel, create_or_update_channel, log_event
from app.handlers.channel_posts import on_channel_post

async def test_forward_detection():
    print("Starting forward detection handler integration tests...")
    
    bot = AsyncMock(spec=Bot)
    channel_id = -1008888888888
    owner_id = 987654321
    title = "Test Forwarding Channel"
    
    chat = Chat(id=channel_id, type="channel", title=title)
    sender = User(id=owner_id, is_bot=False, first_name="Owner")
    
    # 1. Test case: Non-forwarded message (should do nothing)
    print("\n--- Test Case 1: Non-forwarded message ---")
    msg_normal = Message(
        message_id=1,
        date=datetime.now(),
        chat=chat,
        text="This is a regular post",
        from_user=sender
    )
    
    async with async_session_maker() as session:
        # Reset mocks
        bot.copy_message.reset_mock()
        bot.delete_message.reset_mock()
        
        await on_channel_post(msg_normal, session, bot)
        
        bot.copy_message.assert_not_called()
        bot.delete_message.assert_not_called()
        print("Verified: Non-forwarded message was ignored.")

    # 2. Test case: Forwarded but is part of media group (should do nothing - skipped for Step 5)
    print("\n--- Test Case 2: Forwarded album part (media group) ---")
    msg_album = Message(
        message_id=2,
        date=datetime.now(),
        chat=chat,
        text="Part of an album",
        from_user=sender,
        forward_origin=MessageOriginUser(date=datetime.now(), sender_user=sender),
        media_group_id="12345"
    )
    
    async with async_session_maker() as session:
        bot.copy_message.reset_mock()
        bot.delete_message.reset_mock()
        
        await on_channel_post(msg_album, session, bot)
        
        bot.copy_message.assert_not_called()
        bot.delete_message.assert_not_called()
        print("Verified: Forwarded album part was ignored.")

    # 3. Test case: Forwarded single message in an ACTIVE channel
    print("\n--- Test Case 3: Forwarded single message in ACTIVE channel ---")
    msg_forwarded = Message(
        message_id=3,
        date=datetime.now(),
        chat=chat,
        text="A forwarded post",
        from_user=sender,
        forward_origin=MessageOriginUser(date=datetime.now(), sender_user=sender)
    )
    
    async with async_session_maker() as session:
        # Delete existing test channel if any to ensure clean run
        existing = await get_channel(session, channel_id)
        if existing:
            await session.delete(existing)
            await session.commit()
            
        # Create channel with ACTIVE status
        await create_or_update_channel(session, channel_id, owner_id, title, ChannelStatus.ACTIVE)
        
        bot.copy_message.reset_mock()
        bot.delete_message.reset_mock()
        
        await on_channel_post(msg_forwarded, session, bot)
        
        # Verify copy and delete were called
        bot.copy_message.assert_called_once_with(
            chat_id=channel_id,
            from_chat_id=channel_id,
            message_id=3
        )
        bot.delete_message.assert_called_once_with(
            chat_id=channel_id,
            message_id=3
        )
        
        # Verify stats/log in database
        from sqlalchemy import select
        from app.db.models import EventLog
        channel = await get_channel(session, channel_id)
        result = await session.execute(
            select(EventLog).where(EventLog.channel_id == channel.id)
        )
        logs = result.scalars().all()
        assert len(logs) == 1, "Failed to log event in DB"
        assert logs[0].success == True, "Logged event success should be True"
        print("Verified: Forwarded single message was copied, deleted, and successfully logged.")

    # 4. Test case: Forwarded single message where delete fails (e.g. rights revoked)
    print("\n--- Test Case 4: Delete operation fails ---")
    msg_fail = Message(
        message_id=4,
        date=datetime.now(),
        chat=chat,
        text="Forwarded post with revoked permissions",
        from_user=sender,
        forward_origin=MessageOriginUser(date=datetime.now(), sender_user=sender)
    )
    
    async with async_session_maker() as session:
        bot.copy_message.reset_mock()
        bot.delete_message.reset_mock()
        # Mock delete_message to raise exception
        bot.delete_message.side_effect = Exception("Forbidden: bot can't delete message")
        
        # Ensure status is ACTIVE first
        await create_or_update_channel(session, channel_id, owner_id, title, ChannelStatus.ACTIVE)
        
        await on_channel_post(msg_fail, session, bot)
        
        # Check that DB status got updated to PERMISSION_ERROR
        channel = await get_channel(session, channel_id)
        assert channel.status == ChannelStatus.PERMISSION_ERROR, f"Expected PERMISSION_ERROR status, got {channel.status}"
        
        # Check that a failed event log was written
        from sqlalchemy import select
        from app.db.models import EventLog
        result = await session.execute(
            select(EventLog).where(EventLog.channel_id == channel.id, EventLog.success == False)
        )
        failed_logs = result.scalars().all()
        assert len(failed_logs) == 1, "Expected failed event log to be written"
        print("Verified: Channel status updated to PERMISSION_ERROR and failed event logged when delete fails.")

    # 5. Test case: Forwarded single message in PAUSED channel (should do nothing)
    print("\n--- Test Case 5: Forwarded message in PAUSED channel ---")
    async with async_session_maker() as session:
        bot.copy_message.reset_mock()
        bot.delete_message.reset_mock()
        bot.delete_message.side_effect = None
        
        # Update channel to PAUSED
        await create_or_update_channel(session, channel_id, owner_id, title, ChannelStatus.PAUSED)
        
        await on_channel_post(msg_forwarded, session, bot)
        
        bot.copy_message.assert_not_called()
        bot.delete_message.assert_not_called()
        print("Verified: Message in PAUSED channel was ignored.")

    # 6. Test case: Forwarded message in REMOVED channel (should do nothing)
    print("\n--- Test Case 6: Forwarded message in REMOVED channel ---")
    async with async_session_maker() as session:
        bot.copy_message.reset_mock()
        bot.delete_message.reset_mock()
        
        # Update channel to REMOVED
        await create_or_update_channel(session, channel_id, owner_id, title, ChannelStatus.REMOVED)
        
        await on_channel_post(msg_forwarded, session, bot)
        
        bot.copy_message.assert_not_called()
        bot.delete_message.assert_not_called()
        print("Verified: Message in REMOVED channel was ignored.")
        
        # Clean up database
        channel = await get_channel(session, channel_id)
        await session.delete(channel)
        await session.commit()
        print("Cleanup completed.")

    print("\nAll forward-detection tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_forward_detection())
