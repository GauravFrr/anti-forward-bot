from aiogram import Router, Bot
from aiogram.types import ChatMemberUpdated
from aiogram.enums import ChatMemberStatus
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud import create_or_update_channel, update_channel_status
from app.db.models import ChannelStatus

router = Router(name="chat_member")

@router.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated, session: AsyncSession, bot: Bot):
    """
    Handles updates to the bot's own chat member status in channels.
    Auto-registers channels when added as admin, checks permissions, and marks them as removed when kicked/demoted.
    """
    try:
        chat = event.chat
        if chat.type != "channel":
            # We only support channels in this bot
            logger.debug(f"Ignoring my_chat_member update for non-channel chat {chat.id} ({chat.type})")
            return

        old_status = event.old_chat_member.status
        new_status = event.new_chat_member.status
        
        logger.info(f"Bot status change in channel {chat.id} ({chat.title or 'No Title'}): {old_status} -> {new_status}")

        # Case 1: Added or promoted to administrator
        if new_status == ChatMemberStatus.ADMINISTRATOR:
            owner_user_id = event.from_user.id
            title = chat.title
            
            # Check permissions with proper type narrowing
            from aiogram.types import ChatMemberAdministrator
            if isinstance(event.new_chat_member, ChatMemberAdministrator):
                can_delete = event.new_chat_member.can_delete_messages
                can_post = event.new_chat_member.can_post_messages
            else:
                can_delete = False
                can_post = False
            
            logger.info(f"Permission check for channel {chat.id}: can_delete_messages={can_delete}, can_post_messages={can_post}")
            
            if can_delete and can_post:
                status = ChannelStatus.ACTIVE
                logger.info(f"Bot has sufficient permissions in channel {chat.id}. Setting status to ACTIVE.")
            else:
                status = ChannelStatus.PERMISSION_ERROR
                logger.warning(f"Bot is missing permissions in channel {chat.id}. Setting status to PERMISSION_ERROR.")

            # Auto-register/upsert the channel in DB
            channel = await create_or_update_channel(
                session=session,
                channel_id=chat.id,
                owner_user_id=owner_user_id,
                title=title,
                status=status
            )
            logger.info(f"Channel {chat.id} registered successfully in DB. ID={channel.id}, Status={channel.status}")

            # Notify owner if there is a permission error
            if status == ChannelStatus.PERMISSION_ERROR:
                warning_text = (
                    f"⚠️ <b>Action Required: Missing Permissions</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"You added me as an administrator to the channel <b>{title or 'your channel'}</b>, "
                    f"but I am missing required permissions.\n\n"
                    f"Please ensure the following rights are enabled in the channel administrator settings:\n"
                    f"1️⃣ <b>Post messages</b> (Post Messages)\n"
                    f"2️⃣ <b>Delete messages</b> (Delete Messages)\n\n"
                    f"🔄 <i>I will automatically activate the moment these permissions are granted!</i>\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👨‍💻 <b>Developer:</b> @MikeyyFrr | DM for suggestions or custom bots!"
                )
                try:
                    await bot.send_message(chat_id=owner_user_id, text=warning_text)
                    logger.info(f"Notified owner {owner_user_id} about permission error in channel {chat.id}")
                except Exception as dm_err:
                    logger.warning(
                        f"Could not notify owner {owner_user_id} about permission error in channel {chat.id} "
                        f"(they may not have started the bot in DMs): {dm_err}"
                    )

        # Case 2: Demoted or removed from administrator
        elif old_status == ChatMemberStatus.ADMINISTRATOR and new_status != ChatMemberStatus.ADMINISTRATOR:
            logger.info(f"Bot was demoted/removed from channel {chat.id}. Marking as REMOVED.")
            # Set status to REMOVED, maintaining original owner record
            updated = await update_channel_status(
                session=session,
                channel_id=chat.id,
                status=ChannelStatus.REMOVED
            )
            if updated:
                logger.info(f"Successfully marked channel {chat.id} as REMOVED in the database.")
            else:
                logger.warning(f"Bot was removed from channel {chat.id}, but it was not registered in the database.")

    except Exception as e:
        logger.exception(f"Error handling my_chat_member update in channel {event.chat.id}: {e}")
