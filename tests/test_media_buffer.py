import asyncio
from unittest.mock import AsyncMock
from datetime import datetime

from aiogram import Bot
from aiogram.types import (
    Chat, Message, MessageOriginUser, User, PhotoSize,
    InputMediaPhoto, MessageEntity
)
from sqlalchemy import select

from app.db.base import async_session_maker
from app.db.models import ChannelStatus, EventLog
from app.db.crud import get_channel, create_or_update_channel
from app.handlers.channel_posts import on_channel_post
from app.services.media_buffer import redis_client

async def test_media_buffering():
    print("Starting media group buffering integration tests...")
    
    # 1. Clean up Redis before starting
    await redis_client.delete("media_group:parts:test_album_1", "media_group:last_time:test_album_1")
    await redis_client.delete("media_group:parts:test_album_2", "media_group:last_time:test_album_2")
    
    bot = AsyncMock(spec=Bot)
    channel_id = -1007777777777
    owner_id = 987654321
    title = "Test Buffering Channel"
    
    chat = Chat(id=channel_id, type="channel", title=title)
    sender = User(id=owner_id, is_bot=False, first_name="Owner")
    
    # Mock photo size objects for aiogram validation
    mock_photo = [PhotoSize(file_id="photo_file_id", file_unique_id="unique_1", width=100, height=100)]
    
    # Create the test channel in DB
    async with async_session_maker() as session:
        existing = await get_channel(session, channel_id)
        if existing:
            await session.delete(existing)
            await session.commit()
            
        await create_or_update_channel(session, channel_id, owner_id, title, ChannelStatus.ACTIVE)
    
    print("\n--- Test Case 1: Multiple album parts with debounce ---")
    
    entity = MessageEntity(type="bold", offset=0, length=4)
    
    msg_part1 = Message(
        message_id=10,
        date=datetime.now(),
        chat=chat,
        photo=mock_photo,
        caption="Bold caption here",
        caption_entities=[entity],
        from_user=sender,
        forward_origin=MessageOriginUser(date=datetime.now(), sender_user=sender),
        media_group_id="test_album_1"
    )
    msg_part2 = Message(
        message_id=11,
        date=datetime.now(),
        chat=chat,
        photo=mock_photo,
        from_user=sender,
        forward_origin=MessageOriginUser(date=datetime.now(), sender_user=sender),
        media_group_id="test_album_1"
    )
    msg_part3 = Message(
        message_id=12,
        date=datetime.now(),
        chat=chat,
        photo=mock_photo,
        from_user=sender,
        forward_origin=MessageOriginUser(date=datetime.now(), sender_user=sender),
        media_group_id="test_album_1"
    )
    
    # Process sequentially with small delays (simulating Telegram updates)
    async with async_session_maker() as session:
        bot.send_media_group.reset_mock()
        bot.delete_message.reset_mock()
        
        await on_channel_post(msg_part1, session, bot)
        await asyncio.sleep(0.1)
        await on_channel_post(msg_part2, session, bot)
        await asyncio.sleep(0.1)
        await on_channel_post(msg_part3, session, bot)
        
        # Debounce is 1.5s. We shouldn't trigger immediately.
        bot.send_media_group.assert_not_called()
        print("Verified: send_media_group not called prematurely during buffering.")
        
        # Wait for the debounce timer to complete (1.5s sleep + margin)
        await asyncio.sleep(2.0)
        
        # Verify send_media_group was called exactly once
        bot.send_media_group.assert_called_once()
        print("Verified: send_media_group called exactly once after debounce window.")
        
        # Verify sorted media order and caption mapping
        call_args = bot.send_media_group.call_args[1]
        media_list = call_args["media"]
        assert len(media_list) == 3, f"Expected 3 media items, got {len(media_list)}"
        
        # Item 1 should have the caption and caption entities
        assert media_list[0].caption == "Bold caption here"
        assert len(media_list[0].caption_entities) == 1
        assert media_list[0].caption_entities[0].type == "bold"
        
        # Items 2 and 3 should have no caption
        assert media_list[1].caption is None
        assert media_list[2].caption is None
        print("Verified: Album parts sorted and caption/entities correctly preserved on the original item.")
        
        # Verify delete_message was called for all 3 original parts
        assert bot.delete_message.call_count == 3
        bot.delete_message.assert_any_call(chat_id=channel_id, message_id=10)
        bot.delete_message.assert_any_call(chat_id=channel_id, message_id=11)
        bot.delete_message.assert_any_call(chat_id=channel_id, message_id=12)
        print("Verified: delete_message was called for all original parts.")

        # Verify DB logs
        channel = await get_channel(session, channel_id)
        result = await session.execute(
            select(EventLog).where(EventLog.channel_id == channel.id)
        )
        logs = result.scalars().all()
        assert len(logs) == 1
        assert logs[0].message_type == "album"
        assert logs[0].success == True
        print("Verified: Album processing logged as success in the DB.")
        
        # Verify Redis keys cleared
        parts_exists = await redis_client.exists("media_group:parts:test_album_1")
        time_exists = await redis_client.exists("media_group:last_time:test_album_1")
        assert not parts_exists
        assert not time_exists
        print("Verified: Redis keys successfully deleted/cleaned up.")

    print("\n--- Test Case 2: Album processing fails ---")
    async with async_session_maker() as session:
        # Reset mock calls and throw exception
        bot.send_media_group.reset_mock()
        bot.send_media_group.side_effect = Exception("Forbidden: bot cannot post in this channel")
        
        # Make sure status is ACTIVE again
        await create_or_update_channel(session, channel_id, owner_id, title, ChannelStatus.ACTIVE)
        
        # Send one part for the new album
        msg_fail = Message(
            message_id=20,
            date=datetime.now(),
            chat=chat,
            photo=mock_photo,
            from_user=sender,
            forward_origin=MessageOriginUser(date=datetime.now(), sender_user=sender),
            media_group_id="test_album_2"
        )
        
        await on_channel_post(msg_fail, session, bot)
        
        # Wait for debounce
        await asyncio.sleep(2.0)
        
        # Check DB status is now PERMISSION_ERROR
        channel = await get_channel(session, channel_id)
        assert channel.status == ChannelStatus.PERMISSION_ERROR
        
        # Check failed log written
        result = await session.execute(
            select(EventLog).where(EventLog.channel_id == channel.id, EventLog.success == False)
        )
        failed_logs = result.scalars().all()
        assert len(failed_logs) == 1
        print("Verified: API exceptions trigger PERMISSION_ERROR status change and failed log entry.")
        
        # Cleanup
        await session.delete(channel)
        await session.commit()
        print("Cleanup completed.")

    print("\nAll media group buffering tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_media_buffering())
