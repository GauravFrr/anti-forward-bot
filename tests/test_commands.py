import asyncio
from unittest.mock import AsyncMock
from datetime import datetime

from aiogram import Bot
from aiogram.types import Chat, User, ChatMemberAdministrator
from sqlalchemy import select

from app.config import settings
from app.db.base import async_session_maker
from app.db.models import ChannelStatus, Channel, EventLog
from app.db.crud import get_channel, create_or_update_channel
from app.handlers.commands import (
    cmd_start, cmd_mychannels, cmd_pause, cmd_resume, cmd_stats
)

async def test_commands():
    print("Starting command handler integration tests...")
    
    bot = AsyncMock(spec=Bot)
    channel_id = -1006666666666
    owner_id = 999888777  # Sandbox owner ID to avoid conflicting with real channels in the database
    non_owner_id = 111222333
    title = "Test Commands Channel"
    
    chat_private = Chat(id=owner_id, type="private")
    sender_owner = User(id=owner_id, is_bot=False, first_name="Owner")
    sender_non_owner = User(id=non_owner_id, is_bot=False, first_name="Non-Owner")
    
    # 1. Test /start command
    print("\n--- Test Case 1: /start command ---")
    msg_start = AsyncMock()
    msg_start.text = "/start"
    msg_start.chat = chat_private
    msg_start.from_user = sender_owner
    
    await cmd_start(msg_start)
    msg_start.reply.assert_called_once()
    assert "Anti-Forward-Tag Bot" in msg_start.reply.call_args[0][0]
    print("Verified: /start reply successfully sent.")

    # 2. Test /mychannels command (empty & populated states)
    print("\n--- Test Case 2: /mychannels command ---")
    async with async_session_maker() as session:
        # Delete any existing test channel first
        existing = await get_channel(session, channel_id)
        if existing:
            await session.delete(existing)
            await session.commit()
            
        # Empty state
        msg_mychannels = AsyncMock()
        msg_mychannels.text = "/mychannels"
        msg_mychannels.chat = chat_private
        msg_mychannels.from_user = sender_owner
        
        await cmd_mychannels(msg_mychannels, session)
        msg_mychannels.reply.assert_called_once()
        assert "You haven't registered any channels" in msg_mychannels.reply.call_args[0][0]
        
        # Populated state
        channel = await create_or_update_channel(session, channel_id, owner_id, title, ChannelStatus.ACTIVE)
        
        msg_mychannels.reply.reset_mock()
        await cmd_mychannels(msg_mychannels, session)
        msg_mychannels.reply.assert_called_once()
        assert title in msg_mychannels.reply.call_args[0][0]
        assert str(channel.id) in msg_mychannels.reply.call_args[0][0]
        print("Verified: /mychannels accurately lists channels and status.")

    # 3. Test /pause command (validation, ownership, success)
    print("\n--- Test Case 3: /pause command ---")
    async with async_session_maker() as session:
        # No args
        msg_pause_empty = AsyncMock()
        msg_pause_empty.text = "/pause"
        msg_pause_empty.chat = chat_private
        msg_pause_empty.from_user = sender_owner
        
        await cmd_pause(msg_pause_empty, session)
        assert "Please specify" in msg_pause_empty.reply.call_args[0][0]

        # Non-existent/unowned channel ID
        msg_pause_fake = AsyncMock()
        msg_pause_fake.text = "/pause 999999"
        msg_pause_fake.chat = chat_private
        msg_pause_fake.from_user = sender_owner
        
        await cmd_pause(msg_pause_fake, session)
        assert "Channel not found" in msg_pause_fake.reply.call_args[0][0]

        # Unowned channel ID (unowned because user is non-owner)
        msg_pause_unowned = AsyncMock()
        msg_pause_unowned.text = f"/pause {channel.id}"
        msg_pause_unowned.chat = chat_private
        msg_pause_unowned.from_user = sender_non_owner
        
        await cmd_pause(msg_pause_unowned, session)
        assert "Channel not found" in msg_pause_unowned.reply.call_args[0][0]

        # Owned channel ID success (using database primary key index)
        msg_pause_success = AsyncMock()
        msg_pause_success.text = f"/pause {channel.id}"
        msg_pause_success.chat = chat_private
        msg_pause_success.from_user = sender_owner
        
        await cmd_pause(msg_pause_success, session)
        assert "PAUSED" in msg_pause_success.reply.call_args[0][0]
        
        # Verify in DB
        db_chan = await get_channel(session, channel_id)
        assert db_chan.status == ChannelStatus.PAUSED
        print("Verified: /pause updates DB status and enforces ownership.")

    # 4. Test /resume command (success with permissions, failure on missing permissions)
    print("\n--- Test Case 4: /resume command ---")
    async with async_session_maker() as session:
        # Owned channel success (with mock get_chat_member returning correct permissions)
        msg_resume_success = AsyncMock()
        msg_resume_success.text = f"/resume {channel_id}"
        msg_resume_success.chat = chat_private
        msg_resume_success.from_user = sender_owner
        
        bot.get_chat_member.return_value = ChatMemberAdministrator(
            status="administrator",
            user=sender_owner,
            can_be_edited=True,
            can_manage_chat=True,
            can_change_info=True,
            can_post_messages=True,
            can_edit_messages=True,
            can_delete_messages=True,
            can_invite_users=True,
            can_restrict_members=True,
            can_pin_messages=True,
            can_promote_members=True,
            can_manage_video_chats=True,
            can_post_stories=True,
            can_edit_stories=True,
            can_delete_stories=True,
            is_anonymous=False
        )
        
        await cmd_resume(msg_resume_success, session, bot)
        assert "ACTIVE" in msg_resume_success.reply.call_args[0][0]
        
        db_chan = await get_channel(session, channel_id)
        assert db_chan.status == ChannelStatus.ACTIVE
        print("Verified: /resume successfully activates channel with sufficient permissions.")

        # Owned channel with missing permissions
        msg_resume_missing = AsyncMock()
        msg_resume_missing.text = f"/resume {channel_id}"
        msg_resume_missing.chat = chat_private
        msg_resume_missing.from_user = sender_owner
        
        bot.get_chat_member.return_value = ChatMemberAdministrator(
            status="administrator",
            user=sender_owner,
            can_be_edited=True,
            can_manage_chat=True,
            can_change_info=True,
            can_post_messages=False, # Missing
            can_edit_messages=True,
            can_delete_messages=True,
            can_invite_users=True,
            can_restrict_members=True,
            can_pin_messages=True,
            can_promote_members=True,
            can_manage_video_chats=True,
            can_post_stories=True,
            can_edit_stories=True,
            can_delete_stories=True,
            is_anonymous=False
        )
        
        await cmd_resume(msg_resume_missing, session, bot)
        assert "missing required administrator permissions" in msg_resume_missing.reply.call_args[0][0]
        
        db_chan = await get_channel(session, channel_id)
        assert db_chan.status == ChannelStatus.PERMISSION_ERROR
        print("Verified: /resume sets status to PERMISSION_ERROR if permissions are missing.")

    # 5. Test /stats command (restricted, success)
    print("\n--- Test Case 5: /stats command ---")
    async with async_session_maker() as session:
        # Non-owner fails
        msg_stats_non_owner = AsyncMock()
        msg_stats_non_owner.text = "/stats"
        msg_stats_non_owner.chat = chat_private
        msg_stats_non_owner.from_user = sender_non_owner
        
        await cmd_stats(msg_stats_non_owner, session)
        assert "restricted to the bot owner" in msg_stats_non_owner.reply.call_args[0][0]
        
        # Owner success
        msg_stats_success = AsyncMock()
        msg_stats_success.text = "/stats"
        msg_stats_success.chat = chat_private
        msg_stats_success.from_user = User(id=settings.OWNER_ID, is_bot=False, first_name="Real Owner")
        
        await cmd_stats(msg_stats_success, session)
        assert "Bot Global Statistics" in msg_stats_success.reply.call_args[0][0]
        print("Verified: /stats is restricted to owner and displays metrics successfully.")
        
        # Cleanup
        db_chan = await get_channel(session, channel_id)
        await session.delete(db_chan)
        await session.commit()
        print("Cleanup completed.")

    print("\nAll bot command tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_commands())
