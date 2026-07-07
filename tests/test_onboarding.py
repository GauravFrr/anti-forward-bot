import asyncio
from unittest.mock import AsyncMock
from datetime import datetime

from aiogram import Bot
from aiogram.types import Chat, User, ChatMemberAdministrator, ChatMemberLeft, ChatMemberUpdated
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session_maker
from app.db.models import ChannelStatus
from app.db.crud import get_channel, create_or_update_channel
from app.handlers.chat_member import on_my_chat_member

async def test_onboarding():
    print("Starting onboarding handler integration tests...")
    
    # Setup mock bot
    bot = AsyncMock(spec=Bot)
    
    channel_id = -1009999999999
    owner_id = 987654321
    title = "Test Onboarding Channel"
    
    chat = Chat(id=channel_id, type="channel", title=title)
    owner = User(id=owner_id, is_bot=False, first_name="Test Owner")
    
    # 1. Test case: Added as Admin with full permissions
    print("\n--- Test Case 1: Added as Admin with Full Permissions ---")
    event_full = ChatMemberUpdated(
        chat=chat,
        from_user=owner,
        date=datetime.now(),
        old_chat_member=ChatMemberLeft(status="left", user=owner),
        new_chat_member=ChatMemberAdministrator(
            status="administrator",
            user=owner,
            can_be_edited=True,
            can_manage_chat=True,
            can_change_info=True,
            can_post_messages=True,      # Required
            can_edit_messages=True,
            can_delete_messages=True,    # Required
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
    )
    
    async with async_session_maker() as session:
        # Delete existing test channel if any to ensure clean run
        existing = await get_channel(session, channel_id)
        if existing:
            await session.delete(existing)
            await session.commit()
            
        await on_my_chat_member(event_full, session, bot)
        
        # Verify status in database
        channel = await get_channel(session, channel_id)
        assert channel is not None, "Channel was not saved to DB"
        assert channel.status == ChannelStatus.ACTIVE, f"Expected ACTIVE status, got {channel.status}"
        assert channel.owner_user_id == owner_id, f"Expected owner {owner_id}, got {channel.owner_user_id}"
        print(f"Verified: Channel is ACTIVE in DB. Owner ID is {channel.owner_user_id}")
        
    # 2. Test case: Added as Admin with missing permissions
    print("\n--- Test Case 2: Added as Admin with Missing Permissions ---")
    event_missing = ChatMemberUpdated(
        chat=chat,
        from_user=owner,
        date=datetime.now(),
        old_chat_member=ChatMemberLeft(status="left", user=owner),
        new_chat_member=ChatMemberAdministrator(
            status="administrator",
            user=owner,
            can_be_edited=True,
            can_manage_chat=True,
            can_change_info=True,
            can_post_messages=False,     # Missing
            can_edit_messages=True,
            can_delete_messages=True,    # Present
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
    )
    
    async with async_session_maker() as session:
        # Reset mock call history
        bot.send_message.reset_mock()
        
        await on_my_chat_member(event_missing, session, bot)
        
        # Verify status in database
        channel = await get_channel(session, channel_id)
        assert channel is not None
        assert channel.status == ChannelStatus.PERMISSION_ERROR, f"Expected PERMISSION_ERROR, got {channel.status}"
        print(f"Verified: Channel is PERMISSION_ERROR in DB.")
        
        # Verify DM was attempted
        bot.send_message.assert_called_once()
        print("Verified: send_message was called to notify the owner.")

    # 3. Test case: Added as Admin with missing permissions, but DM is blocked (should not fail/block registration)
    print("\n--- Test Case 3: Blocked DM notification ---")
    async with async_session_maker() as session:
        # Setup mock to throw exception
        bot.send_message.reset_mock()
        bot.send_message.side_effect = Exception("Forbidden: bot can't initiate conversation")
        
        # We manually change status to active first to verify it changes to PERMISSION_ERROR
        channel.status = ChannelStatus.ACTIVE
        await session.commit()
        
        await on_my_chat_member(event_missing, session, bot)
        
        # Verify status in database
        channel = await get_channel(session, channel_id)
        assert channel is not None
        assert channel.status == ChannelStatus.PERMISSION_ERROR, f"Expected PERMISSION_ERROR, got {channel.status}"
        print("Verified: Channel status updated to PERMISSION_ERROR despite DM call failing.")

    # 4. Test case: Demoted/Removed (should set status to REMOVED, keeping original owner)
    print("\n--- Test Case 4: Bot Demoted/Removed ---")
    event_removed = ChatMemberUpdated(
        chat=chat,
        from_user=User(id=777777777, is_bot=False, first_name="Kicker Admin"), # Different user kicks the bot
        date=datetime.now(),
        old_chat_member=ChatMemberAdministrator(
            status="administrator",
            user=owner,
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
        ),
        new_chat_member=ChatMemberLeft(status="left", user=owner)
    )
    
    async with async_session_maker() as session:
        # Set database owner as owner_id
        await create_or_update_channel(session, channel_id, owner_id, title, ChannelStatus.ACTIVE)
        
        await on_my_chat_member(event_removed, session, bot)
        
        # Verify status and owner in database
        channel = await get_channel(session, channel_id)
        assert channel is not None
        assert channel.status == ChannelStatus.REMOVED, f"Expected REMOVED status, got {channel.status}"
        assert channel.owner_user_id == owner_id, f"Expected original owner {owner_id} to be retained, got {channel.owner_user_id}"
        print(f"Verified: Channel is REMOVED in DB. Original Owner ID {channel.owner_user_id} was successfully retained.")
        
        # Cleanup
        await session.delete(channel)
        await session.commit()
        print("Cleanup completed.")

    print("\nAll onboarding tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_onboarding())
