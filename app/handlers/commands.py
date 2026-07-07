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
async def cmd_start(message: Message, session: AsyncSession):
    """
    Welcoming introduction and setup instructions.
    Tracks the user in the database.
    """
    from app.db.crud import create_or_update_user
    await create_or_update_user(
        session,
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )

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
async def cmd_help(message: Message, session: AsyncSession):
    """
    Re-prints setup instructions.
    """
    await cmd_start(message, session)

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

@router.message(Command("owner"))
async def cmd_owner(message: Message):
    """
    Shows help menu for the bot owner.
    """
    if message.from_user.id != settings.OWNER_ID:
        return  # Silently ignore for non-owners

    text = (
        "👑 <b>Owner Administrative Control</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Available Administrative Commands:\n\n"
        "📊 /adminstats — Full system telemetry dashboard\n"
        "📈 /activechannels — Top active channels by volume\n"
        "🔍 /findchannel &lt;channel_id&gt; — Detailed status & logs\n"
        "👤 /finduser &lt;username/id&gt; — Lookup user & channels\n"
        "⏸️ /pausechannel &lt;channel_id&gt; — Emergency pause override\n"
        "▶️ /resumechannel &lt;channel_id&gt; — Emergency resume override\n"
        "📤 /broadcast &lt;message&gt; — Send bulk message to all users\n"
        "💾 /exportdata — Export database to CSV files"
    )
    await message.reply(text)

@router.message(Command("stats"))
@router.message(Command("adminstats"))
async def cmd_stats(message: Message, session: AsyncSession):
    """
    Prints global stats. Only accessible by the bot owner.
    """
    if message.from_user.id != settings.OWNER_ID:
        if message.text.startswith("/stats"):
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
        "👥 <b>Userbase Stats:</b>\n"
        f"├─ <b>Total Bot Users:</b> <code>{stats.get('total_users', 0)}</code>\n"
        f"├─ <b>Total Channels:</b> <code>{stats['total_channels']}</code>\n"
        f"└─ <b>Active Protection:</b> <code>{stats['active_channels']}</code>\n\n"
        "✉️ <b>Message Processing:</b>\n"
        f"├─ <b>Total Processed:</b> <code>{stats['total_messages']}</code>\n"
        f"├─ 🟢 <b>Successful Reposts:</b> <code>{success_count}</code>\n"
        f"└─ 🔴 <b>Failed Reposts:</b> <code>{fail_count}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👨‍💻 <b>Developer:</b> @MikeyyFrr"
    )
    await message.reply(text)

@router.message(Command("activechannels"))
async def cmd_active_channels(message: Message, session: AsyncSession):
    """
    Lists top channels by processing volume. Owner only.
    """
    if message.from_user.id != settings.OWNER_ID:
        return

    from app.db.crud import get_active_channels_sorted
    channels = await get_active_channels_sorted(session, limit=20)
    
    if not channels:
        await message.reply("No active channels found.")
        return

    lines = [
        "📈 <b>Top Channels by Volume</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
    ]
    for idx, (ch, count) in enumerate(channels, 1):
        lines.append(
            f"<b>{idx}. {ch.title or 'No Title'}</b>\n"
            f"├─ <b>Telegram ID:</b> <code>{ch.channel_id}</code>\n"
            f"├─ <b>Owner ID:</b> <code>{ch.owner_user_id}</code>\n"
            f"└─ <b>Cleaned Posts:</b> <code>{count}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
    await message.reply("\n".join(lines))

@router.message(Command("findchannel"))
async def cmd_find_channel(message: Message, session: AsyncSession):
    """
    Searches a channel and prints its details and recent event logs. Owner only.
    """
    if message.from_user.id != settings.OWNER_ID:
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: <code>/findchannel &lt;channel_id&gt;</code>")
        return

    from app.db.crud import get_channel
    ch = None
    
    # Try searching by Telegram channel_id first
    try:
        tg_id = int(args[1])
        ch = await get_channel(session, tg_id)
    except ValueError:
        pass

    # Fallback to search by database index (primary key)
    if not ch and args[1].isdigit():
        db_id = int(args[1])
        result = await session.execute(
            select(Channel).where(Channel.id == db_id)
        )
        ch = result.scalar_one_or_none()

    if not ch:
        await message.reply("❌ Channel not found in database.")
        return

    # Fetch last 10 logs
    logs_result = await session.execute(
        select(EventLog)
        .where(EventLog.channel_id == ch.id)
        .order_by(EventLog.created_at.desc())
        .limit(10)
    )
    logs = list(logs_result.scalars().all())

    lines = [
        f"🔍 <b>Channel: {ch.title or 'No Title'}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>DB Index:</b> <code>{ch.id}</code>\n"
        f"• <b>Telegram ID:</b> <code>{ch.channel_id}</code>\n"
        f"• <b>Owner ID:</b> <code>{ch.owner_user_id}</code>\n"
        f"• <b>Status:</b> <code>{ch.status.value.upper()}</code>\n"
        f"• <b>Auto-Pin:</b> <code>{ch.auto_pin_enabled}</code>\n"
        f"• <b>Queue:</b> <code>{ch.queue_enabled} ({ch.queue_interval_minutes}m)</code>\n"
        f"• <b>Created At:</b> <code>{ch.created_at.strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
        "📋 <b>Recent Events (Last 10):</b>\n"
    ]

    if not logs:
        lines.append("No event logs recorded.")
    for log in logs:
        emoji = "🟢" if log.success else "🔴"
        lines.append(f"{emoji} <code>{log.created_at.strftime('%H:%M:%S')}</code> | <b>{log.message_type}</b>")

    await message.reply("\n".join(lines))

@router.message(Command("finduser"))
async def cmd_find_user(message: Message, session: AsyncSession):
    """
    Finds a user by ID or Username and shows their registered channels. Owner only.
    """
    if message.from_user.id != settings.OWNER_ID:
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: <code>/finduser &lt;username/user_id&gt;</code>")
        return

    from app.db.crud import find_user_by_query
    user = await find_user_by_query(session, args[1])
    if not user:
        await message.reply("❌ User not found in database.")
        return

    # Fetch user's channels
    ch_result = await session.execute(
        select(Channel).where(Channel.owner_user_id == user.user_id)
    )
    channels = list(ch_result.scalars().all())

    lines = [
        f"👤 <b>User: {user.first_name or 'No Name'}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>User ID:</b> <code>{user.user_id}</code>\n"
        f"• <b>Username:</b> @{user.username or 'None'}\n"
        f"• <b>First Seen:</b> <code>{user.first_seen_at.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
        f"• <b>Last Seen:</b> <code>{user.last_seen_at.strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
        "📋 <b>Registered Channels:</b>\n"
    ]
    if not channels:
        lines.append("No channels registered.")
    for ch in channels:
        lines.append(f"• [{ch.id}] <b>{ch.title}</b> (<code>{ch.status.value.upper()}</code>)")

    await message.reply("\n".join(lines))

@router.message(Command("pausechannel"))
async def cmd_pause_channel(message: Message, session: AsyncSession):
    """
    Force pauses a channel. Owner override.
    """
    if message.from_user.id != settings.OWNER_ID:
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: <code>/pausechannel &lt;channel_id&gt;</code>")
        return

    try:
        ch_id = int(args[1])
        result = await session.execute(select(Channel).where(Channel.channel_id == ch_id))
        ch = result.scalar_one_or_none()
        if not ch:
            await message.reply("❌ Channel not found.")
            return
        ch.status = ChannelStatus.PAUSED
        await session.commit()
        await message.reply(f"⏸️ Manually paused channel: <b>{ch.title}</b> (<code>{ch.channel_id}</code>)")
    except ValueError:
        await message.reply("Invalid ID format.")

@router.message(Command("resumechannel"))
async def cmd_resume_channel(message: Message, session: AsyncSession):
    """
    Force resumes a channel. Owner override.
    """
    if message.from_user.id != settings.OWNER_ID:
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: <code>/resumechannel &lt;channel_id&gt;</code>")
        return

    try:
        ch_id = int(args[1])
        result = await session.execute(select(Channel).where(Channel.channel_id == ch_id))
        ch = result.scalar_one_or_none()
        if not ch:
            await message.reply("❌ Channel not found.")
            return
        ch.status = ChannelStatus.ACTIVE
        await session.commit()
        await message.reply(f"▶️ Manually activated channel: <b>{ch.title}</b> (<code>{ch.channel_id}</code>)")
    except ValueError:
        await message.reply("Invalid ID format.")

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, session: AsyncSession, bot: Bot):
    """
    Sends a formatted message to all registered users with safe rate-limiting. Owner only.
    """
    if message.from_user.id != settings.OWNER_ID:
        return

    broadcast_text = message.text.replace("/broadcast", "", 1).strip()
    if not broadcast_text:
        await message.reply(
            "⚠️ Please specify the text to broadcast.\n"
            "Usage: <code>/broadcast &lt;message&gt;</code>"
        )
        return

    from app.db.crud import get_all_users
    users = await get_all_users(session)
    if not users:
        await message.reply("No registered users found to broadcast to.")
        return

    status_msg = await message.reply(f"📢 Initiating broadcast to {len(users)} users...")
    success, fail = 0, 0

    import asyncio
    for idx, user in enumerate(users):
        try:
            await bot.send_message(chat_id=user.user_id, text=broadcast_text, parse_mode="HTML")
            success += 1
        except Exception as e:
            logger.warning(f"Broadcast failed to user {user.user_id}: {e}")
            fail += 1
        
        # Space out requests to avoid Telegram flood blocks (max 30 msgs/sec)
        await asyncio.sleep(0.05)

        # Update stats every 50 users
        if idx > 0 and idx % 50 == 0:
            try:
                await status_msg.edit_text(
                    f"📢 Broadcasting announcements...\n"
                    f"Progress: <code>{idx}/{len(users)}</code>\n"
                    f"🟢 Delivered: <code>{success}</code>\n"
                    f"🔴 Failed: <code>{fail}</code>"
                )
            except Exception:
                pass

    await status_msg.edit_text(
        f"✅ <b>Broadcast Completed!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Total Targets:</b> <code>{len(users)}</code>\n"
        f"• 🟢 <b>Successful:</b> <code>{success}</code>\n"
        f"• 🔴 <b>Failed:</b> <code>{fail}</code>"
    )

@router.message(Command("exportdata"))
async def cmd_export_data(message: Message, session: AsyncSession):
    """
    Generates and exports users and channels tables as CSV documents. Owner only.
    """
    if message.from_user.id != settings.OWNER_ID:
        return

    from app.db.crud import get_all_users, get_all_channels
    users = await get_all_users(session)
    channels = await get_all_channels(session)

    import csv
    import io
    from aiogram.types import BufferedInputFile

    # 1. Users CSV
    out_users = io.StringIO()
    writer_users = csv.writer(out_users)
    writer_users.writerow(["id", "user_id", "username", "first_name", "first_seen_at"])
    for u in users:
        writer_users.writerow([u.id, u.user_id, u.username, u.first_name, u.first_seen_at])
    
    users_file = BufferedInputFile(
        out_users.getvalue().encode("utf-8"),
        filename="users_export.csv"
    )

    # 2. Channels CSV
    out_channels = io.StringIO()
    writer_channels = csv.writer(out_channels)
    writer_channels.writerow([
        "id", "channel_id", "owner_user_id", "title", "status",
        "custom_footer", "auto_pin_enabled", "queue_enabled", "queue_interval"
    ])
    for c in channels:
        writer_channels.writerow([
            c.id, c.channel_id, c.owner_user_id, c.title, c.status.value,
            c.custom_footer, c.auto_pin_enabled, c.queue_enabled, c.queue_interval_minutes
        ])

    channels_file = BufferedInputFile(
        out_channels.getvalue().encode("utf-8"),
        filename="channels_export.csv"
    )

    await message.reply_document(users_file, caption="👥 Users database export")
    await message.reply_document(channels_file, caption="📌 Channels database export")

