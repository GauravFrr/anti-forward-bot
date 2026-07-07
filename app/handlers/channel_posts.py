import asyncio
import time
from aiogram import Router, Bot
from aiogram.types import Message
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session_maker
from app.db.crud import get_channel, log_event, update_channel_status
from app.db.models import ChannelStatus
from app.services import media_buffer

router = Router(name="channel_posts")

def get_media_info(message: Message) -> tuple[str, str] | None:
    """
    Helper function to extract content type and the file_id for standard media types.
    """
    if message.photo:
        return "photo", message.photo[-1].file_id
    elif message.video:
        return "video", message.video.file_id
    elif message.audio:
        return "audio", message.audio.file_id
    elif message.document:
        return "document", message.document.file_id
    return None

async def debounce_media_group(bot: Bot, chat_id: int, media_group_id: str, timestamp: float):
    """
    Debounce task that sleeps and reassembles media groups once all parts are received.
    Uses a fresh database session and checks Redis fresh at wake-up.
    """
    try:
        # Sleep for debounce window
        await asyncio.sleep(1.5)
        
        # Fresh read from Redis to verify if we are the latest scheduled task
        last_arrival = await media_buffer.get_last_arrival(media_group_id)
        if last_arrival is None or last_arrival != timestamp:
            # A newer part arrived and scheduled its own task; exit silently
            return
            
        logger.info(f"Debounce finished for media group {media_group_id} in channel {chat_id}. Processing album...")
        
        # Retrieve and clear the buffered parts
        parts = await media_buffer.get_and_clear_buffer(media_group_id)
        if not parts:
            return
            
        # Open a fresh database session for background DB work
        async with async_session_maker() as session:
            # Re-verify channel status is ACTIVE
            channel = await get_channel(session, chat_id)
            if not channel or channel.status != ChannelStatus.ACTIVE:
                logger.debug(f"Ignoring media group {media_group_id} because channel {chat_id} is not ACTIVE.")
                return

            # Sort parts by message_id to maintain correct album order
            parts.sort(key=lambda x: x["message_id"])

            from aiogram.types import InputMediaPhoto, InputMediaVideo, InputMediaAudio, InputMediaDocument, MessageEntity
            input_media = []
            original_message_ids = []

            for part in parts:
                m_type = part["media_type"]
                file_id = part["file_id"]
                caption = part["caption"]
                entities_data = part["caption_entities"]

                # Deserialize caption entities if any
                entities = None
                if entities_data:
                    entities = [MessageEntity.model_validate(e) for e in entities_data]

                original_message_ids.append(part["message_id"])

                # Instantiate corresponding InputMedia class
                if m_type == "photo":
                    input_media.append(InputMediaPhoto(media=file_id, caption=caption, caption_entities=entities))
                elif m_type == "video":
                    input_media.append(InputMediaVideo(media=file_id, caption=caption, caption_entities=entities))
                elif m_type == "audio":
                    input_media.append(InputMediaAudio(media=file_id, caption=caption, caption_entities=entities))
                elif m_type == "document":
                    input_media.append(InputMediaDocument(media=file_id, caption=caption, caption_entities=entities))

            try:
                from app.utils.retry import execute_post_with_rate_limit, execute_delete_with_retry

                # Repost album with per-channel rate limit and retry
                await execute_post_with_rate_limit(
                    chat_id,
                    bot.send_media_group,
                    chat_id=chat_id,
                    media=input_media
                )
                
                # Delete original posts with retry only (bypasses per-channel rate limiting)
                for msg_id in original_message_ids:
                    await execute_delete_with_retry(
                        bot.delete_message,
                        chat_id=chat_id,
                        message_id=msg_id
                    )

                # Log successful event
                await log_event(session, chat_id, message_type="album", success=True)
                logger.info(f"Successfully reposted and deleted media group {media_group_id} in channel {chat_id}")

            except Exception as api_err:
                logger.warning(f"Failed to process media group {media_group_id} in channel {chat_id}: {api_err}")
                
                # Update status to permission_error in case rights were revoked mid-operation
                await update_channel_status(session, chat_id, ChannelStatus.PERMISSION_ERROR)
                
                # Log failed event
                await log_event(session, chat_id, message_type="album", success=False)

    except Exception as e:
        logger.exception(f"Unhandled exception in media group {media_group_id} debounce task for channel {chat_id}: {e}")

@router.channel_post()
async def on_channel_post(message: Message, session: AsyncSession, bot: Bot):
    """
    Listens to channel posts.
    Detects forwarded posts and processes them based on single message vs media group (album) flows.
    """
    try:
        # 1. Ignore non-forwarded posts
        if message.forward_origin is None:
            return

        channel_id = message.chat.id
        
        # 2. Verify channel status is ACTIVE before buffering or processing
        channel = await get_channel(session, channel_id)
        if not channel or channel.status != ChannelStatus.ACTIVE:
            status_str = channel.status if channel else "not registered"
            logger.debug(f"Ignoring forwarded post in channel {channel_id} (status: {status_str})")
            return

        # Case A: Media Group (Album) Flow
        if message.media_group_id is not None:
            media_info = get_media_info(message)
            if not media_info:
                logger.warning(f"Unsupported media type in media group {message.media_group_id} for channel {channel_id}")
                return
                
            media_type, file_id = media_info
            
            # Serialize caption entities
            serialized_entities = None
            if message.caption_entities:
                serialized_entities = [entity.model_dump() for entity in message.caption_entities]

            part_data = {
                "message_id": message.message_id,
                "media_type": media_type,
                "file_id": file_id,
                "caption": message.caption,
                "caption_entities": serialized_entities
            }

            # Buffer part details in Redis
            await media_buffer.add_media_group_part(message.media_group_id, part_data)
            
            # Update last arrival timestamp
            timestamp = time.time()
            await media_buffer.set_last_arrival(message.media_group_id, timestamp)

            # Spawn background task to handle debounced processing
            asyncio.create_task(
                debounce_media_group(
                    bot=bot,
                    chat_id=channel_id,
                    media_group_id=message.media_group_id,
                    timestamp=timestamp
                )
            )
            return

        # Case B: Single Message Flow
        logger.info(f"Forwarded post detected in active channel {channel_id} (Message ID: {message.message_id}, Type: {message.content_type})")

        try:
            from app.utils.retry import execute_post_with_rate_limit, execute_delete_with_retry

            await execute_post_with_rate_limit(
                channel_id,
                bot.copy_message,
                chat_id=channel_id,
                from_chat_id=channel_id,
                message_id=message.message_id
            )
            await execute_delete_with_retry(
                bot.delete_message,
                chat_id=channel_id,
                message_id=message.message_id
            )
            
            # Log success
            await log_event(session, channel_id, message_type=message.content_type, success=True)
            logger.info(f"Successfully reposted and deleted forwarded post in channel {channel_id}")
            
        except Exception as api_err:
            logger.warning(f"Failed to process forwarded post in channel {channel_id}: {api_err}")
            
            # Update status to permission_error in case rights were revoked mid-operation
            await update_channel_status(session, channel_id, ChannelStatus.PERMISSION_ERROR)
            
            # Log failure
            await log_event(session, channel_id, message_type=message.content_type, success=False)
            
    except Exception as e:
        logger.exception(f"Unhandled exception in channel_posts handler for channel {message.chat.id}: {e}")
