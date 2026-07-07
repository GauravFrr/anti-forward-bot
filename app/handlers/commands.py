from aiogram import Router, Bot, F
from aiogram.types import Message
from aiogram.filters import Command
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Channel, ChannelStatus, EventLog
from app.db.crud import get_channels_by_owner, update_channel_status, get_global_stats

router = Router(name="commands")

# Filter this entire router to only handle private (DM) messages
router.message.filter(F.chat.type == "private")

async def find_channel(session: AsyncSession, owner_id: int, arg: str) -> Channel | None:
    """
    Helper to search for an owned channel by Database primary key index,
    full Telegram channel ID, or Telegram channel ID without the -100 prefix.
    """
    # 1. Search by Database primary key index (channel.id)
    if arg.isdigit():
        db_id = int(arg)
        result = await session.execute(
            select(Channel).where(Channel.id == db_id, Channel.owner_user_id == owner_id)
        )
        channel = result.scalar_one_or_none()
        if channel:
            return channel

    # 2. Search by full Telegram channel_id
    try:
        tg_id = int(arg)
        result = await session.execute(
            select(Channel).where(Channel.channel_id == tg_id, Channel.owner_user_id == owner_id)
        )
        channel = result.scalar_one_or_none()
        if channel:
            return channel
    except ValueError:
        pass

    # 3. Search by Telegram channel_id missing the -100 prefix
    if not arg.startswith("-"):
        try:
            tg_id = int(f"-100{arg}")
            result = await session.execute(
                select(Channel).where(Channel.channel_id == tg_id, Channel.owner_user_id == owner_id)
            )
            channel = result.scalar_one_or_none()
            if channel:
                return channel
        except ValueError:
            pass

    return None

@router.message(Command("start"))
async def cmd_start(message: Message):
    """
    Welcoming introduction and setup instructions.
    """
    text = (
        "✨ <b>Anti-Forward-Tag Bot</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Automatically strip the annoying <i>\"Forwarded from...\"</i> headers from your Telegram channels instantly! 🚀\n\n"
        "🛡️ <b>Quick Setup Guide:</b>\n"
        "1️⃣ Add me to your Channel as an <b>Administrator</b>.\n"
        "2️⃣ Grant me the following permissions:\n"
        "   • <b>Post messages</b> (to publish clean reposts)\n"
        "   • <b>Delete messages</b> (to clean up the originals)\n"
        "3️⃣ Once added, the bot will auto-onboard and start protecting your channel!\n\n"
        "⚡ <b>Available Commands (DM Only):</b>\n"
        "📂 /mychannels — View your registered channels & status\n"
        "⏸️ /pause &lt;id&gt; — Pause protection for a channel\n"
        "▶️ /resume &lt;id&gt; — Resume protection & recheck permissions\n"
        "ℹ️ /help — Show this instruction manual\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👨‍💻 <b>Developer:</b> @MikeyyFrr\n"
        "💡 <i>Need custom Telegram bots, suggestions, or queries? Feel free to DM me!</i>"
    )
    await message.reply(text)

@router.message(Command("help"))
async def cmd_help(message: Message):
    """
    Re-prints setup instructions.
    """
    await cmd_start(message)

@router.message(Command("mychannels"))
async def cmd_mychannels(message: Message, session: AsyncSession):
    """
    Lists all registered channels owned by the user.
    """
    channels = await get_channels_by_owner(session, message.from_user.id)
    if not channels:
        await message.reply(
            "📋 <b>Your Channels</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "You haven't registered any channels with me yet.\n\n"
            "💡 <b>To get started:</b> Add me to your channel as an administrator with post and delete rights!\n\n"
            "👨‍💻 <b>Developer:</b> @MikeyyFrr"
        )
        return

    lines = [
        "📋 <b>Your Channels</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Here are the channels you currently manage:\n"
    ]
    
    status_emojis = {
        "active": "🟢",
        "paused": "⏸️",
        "permission_error": "⚠️",
        "removed": "❌"
    }

    for ch in channels:
        status_val = ch.status.value.lower()
        emoji = status_emojis.get(status_val, "❓")
        lines.append(
            f"📌 <b>{ch.title or 'No Title'}</b>\n"
            f"├─ <b>Index ID:</b> <code>{ch.id}</code>\n"
            f"├─ <b>Telegram ID:</b> <code>{ch.channel_id}</code>\n"
            f"└─ <b>Status:</b> {emoji} <code>{ch.status.value.upper()}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        
    lines.append(
        "\n👨‍💻 <b>Developer:</b> @MikeyyFrr\n"
        "💡 <i>Suggestions/Custom Bots? DM: @MikeyyFrr</i>"
    )
    await message.reply("\n".join(lines))

@router.message(Command("pause"))
async def cmd_pause(message: Message, session: AsyncSession):
    """
    Pauses reposting for a specific channel.
    """
    args = message.text.split()
    if len(args) < 2:
        await message.reply(
            "⚠️ Please specify the channel index ID or Telegram ID to pause.\n"
            "Usage: <code>/pause &lt;id&gt;</code>"
        )
        return

    channel = await find_channel(session, message.from_user.id, args[1])
    if not channel:
        await message.reply(
            "❌ Channel not found. Make sure you own this channel and check the ID in /mychannels."
        )
        return

    await update_channel_status(session, channel.channel_id, ChannelStatus.PAUSED)
    await message.reply(
        f"⏸️ <b>Protection Paused</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Reposting has been suspended for channel: <b>{channel.title}</b>.\n"
        f"Status is now: <code>PAUSED</code>.\n\n"
        f"💡 <i>To reactivate, run <code>/resume {channel.id}</code>.</i>"
    )

@router.message(Command("resume"))
async def cmd_resume(message: Message, session: AsyncSession, bot: Bot):
    """
    Resumes reposting for a specific channel after checking admin permissions.
    """
    args = message.text.split()
    if len(args) < 2:
        await message.reply(
            "⚠️ Please specify the channel index ID or Telegram ID to resume.\n"
            "Usage: <code>/resume &lt;id&gt;</code>"
        )
        return

    channel = await find_channel(session, message.from_user.id, args[1])
    if not channel:
        await message.reply(
            "❌ Channel not found. Make sure you own this channel and check the ID in /mychannels."
        )
        return

    # Re-run permission self-check
    try:
        chat_member = await bot.get_chat_member(chat_id=channel.channel_id, user_id=bot.id)
        from aiogram.types import ChatMemberAdministrator
        
        can_delete = getattr(chat_member, "can_delete_messages", False)
        can_post = getattr(chat_member, "can_post_messages", False)
        
        if isinstance(chat_member, ChatMemberAdministrator) and can_delete and can_post:
            await update_channel_status(session, channel.channel_id, ChannelStatus.ACTIVE)
            await message.reply(
                f"▶️ <b>Protection Resumed</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"Reposting has been successfully activated for channel: <b>{channel.title}</b>.\n"
                f"Status is now: 🟢 <code>ACTIVE</code>."
            )
        else:
            await update_channel_status(session, channel.channel_id, ChannelStatus.PERMISSION_ERROR)
            await message.reply(
                f"⚠️ <b>Action Required: Missing Permissions</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"I cannot resume protection for channel: <b>{channel.title}</b> because I am missing required administrator permissions in your channel settings.\n\n"
                f"Please ensure I have <b>Post messages</b> and <b>Delete messages</b> rights in your channel settings."
            )
    except Exception as e:
        logger.warning(f"Error checking bot permissions in channel {channel.channel_id} during resume: {e}")
        await update_channel_status(session, channel.channel_id, ChannelStatus.PERMISSION_ERROR)
        await message.reply(
            f"❌ <b>Failed to verify permissions</b> in channel <b>{channel.title}</b>. "
            f"I have marked it as <code>PERMISSION_ERROR</code>.\n\n"
            f"Error details: <code>{e}</code>"
        )

@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession):
    """
    Prints global stats. Only accessible by the bot owner.
    """
    if message.from_user.id != settings.OWNER_ID:
        await message.reply("❌ This command is restricted to the bot owner.")
        return

    stats = await get_global_stats(session)
    
    # Query success/failure metrics from EventLog
    from sqlalchemy import func
    success_result = await session.execute(
        select(func.count(EventLog.id)).where(EventLog.success == True)
    )
    success_count = success_result.scalar() or 0

    fail_result = await session.execute(
        select(func.count(EventLog.id)).where(EventLog.success == False)
    )
    fail_count = fail_result.scalar() or 0

    text = (
        "📊 <b>Bot Global Statistics</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Here is the system-wide status of the bot:\n\n"
        "👥 <b>Channels:</b>\n"
        f"├─ <b>Total Registered:</b> <code>{stats['total_channels']}</code>\n"
        f"└─ <b>Active Protection:</b> <code>{stats['active_channels']}</code>\n\n"
        "✉️ <b>Message Processing:</b>\n"
        f"├─ <b>Total Processed:</b> <code>{stats['total_messages']}</code>\n"
        f"├─ 🟢 <b>Successful Reposts:</b> <code>{success_count}</code>\n"
        f"└─ 🔴 <b>Failed Reposts:</b> <code>{fail_count}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👨‍💻 <b>Developer:</b> @MikeyyFrr"
    )
    await message.reply(text)
