import asyncio
import time
import os
import json
from aiogram import Router, Bot
from aiogram.types import Message, MessageEntity, InputMediaPhoto, InputMediaVideo, InputMediaAudio, InputMediaDocument, FSInputFile
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session_maker
from app.db.crud import get_channel, log_event, update_channel_status
from app.db.models import ChannelStatus
from app.services import media_buffer
from app.utils.retry import execute_post_with_rate_limit, execute_delete_with_retry
from app.services.queue_worker import schedule_post

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
    """
    try:
        # Sleep for debounce window
        await asyncio.sleep(1.5)
        
        # Fresh read from Redis to verify if we are the latest scheduled task
        last_arrival = await media_buffer.get_last_arrival(media_group_id)
        if last_arrival is None or last_arrival != timestamp:
            return
            
        logger.info(f"Debounce finished for media group {media_group_id} in channel {chat_id}. Processing album...")
        parts = await media_buffer.get_and_clear_buffer(media_group_id)
        if not parts:
            return
            
        async with async_session_maker() as session:
            channel = await get_channel(session, chat_id)
            if not channel or channel.status != ChannelStatus.ACTIVE:
                return

            # Sort parts by message_id
            parts.sort(key=lambda x: x["message_id"])
            original_message_ids = [part["message_id"] for part in parts]

            # Case A: Queue is Enabled
            if channel.queue_enabled:
                payload = {
                    "type": "album",
                    "parts": [
                        {
                            "media_type": p["media_type"],
                            "file_id": p["file_id"],
                            "caption": p["caption"],
                            "caption_entities": p["caption_entities"],
                            "document_conversion": p.get("document_conversion", False),
                            "mime_type": p.get("mime_type", ""),
                            "file_name": p.get("file_name", "")
                        }
                        for p in parts
                    ]
                }
                await schedule_post(session, channel, payload)
                
                # Delete original posts in parallel
                delete_tasks = [
                    execute_delete_with_retry(bot.delete_message, chat_id=chat_id, message_id=msg_id)
                    for msg_id in original_message_ids
                ]
                await asyncio.gather(*delete_tasks, return_exceptions=True)
                return

            # Case B: Instant Repost Flow
            footer = f"\n\n{channel.custom_footer}" if channel.custom_footer else ""

            # Helper to download/prepare media parts concurrently
            async def prepare_part(part):
                m_type = part["media_type"]
                file_id = part["file_id"]
                caption = part["caption"] or ""
                if caption:
                    caption += footer

                entities = None
                if part["caption_entities"]:
                    entities = [MessageEntity.model_validate(e) for e in part["caption_entities"]]

                doc_convert = part.get("document_conversion", False)
                if doc_convert and m_type == "document":
                    mime_type = part.get("mime_type", "")
                    file_name = part.get("file_name", "")
                    os.makedirs("temp_media", exist_ok=True)
                    local_path = f"temp_media/{file_id}_{file_name}"
                    
                    try:
                        file_info = await bot.get_file(file_id)
                        await bot.download_file(file_info.file_path, local_path)
                        
                        if mime_type.startswith("image/"):
                            return InputMediaPhoto(media=FSInputFile(local_path), caption=caption, caption_entities=entities)
                        elif mime_type.startswith("video/"):
                            return InputMediaVideo(media=FSInputFile(local_path), caption=caption, caption_entities=entities)
                    except Exception as e:
                        logger.error(f"Failed to convert document in album: {e}")
                        return InputMediaDocument(media=file_id, caption=caption, caption_entities=entities)
                else:
                    if m_type == "photo":
                        return InputMediaPhoto(media=file_id, caption=caption, caption_entities=entities)
                    elif m_type == "video":
                        return InputMediaVideo(media=file_id, caption=caption, caption_entities=entities)
                    elif m_type == "audio":
                        return InputMediaAudio(media=file_id, caption=caption, caption_entities=entities)
                    elif m_type == "document":
                        return InputMediaDocument(media=file_id, caption=caption, caption_entities=entities)
                return None

            # Prepare all parts in parallel
            prepare_tasks = [prepare_part(part) for part in parts]
            input_media = await asyncio.gather(*prepare_tasks, return_exceptions=True)
            input_media = [im for im in input_media if im is not None and not isinstance(im, Exception)]

            try:
                # Repost album
                res_list = await execute_post_with_rate_limit(
                    chat_id,
                    bot.send_media_group,
                    chat_id=chat_id,
                    media=input_media
                )
                
                # Concurrently delete original messages, log event, and auto-pin
                post_cleanup_tasks = [
                    log_event(session, chat_id, message_type="album", success=True)
                ]
                
                # Add delete tasks
                for msg_id in original_message_ids:
                    post_cleanup_tasks.append(
                        execute_delete_with_retry(bot.delete_message, chat_id=chat_id, message_id=msg_id)
                    )
                
                # Add auto-pin task
                if res_list and channel.auto_pin_enabled:
                    post_cleanup_tasks.append(
                        bot.pin_chat_message(chat_id=chat_id, message_id=res_list[0].message_id, disable_notification=True)
                    )

                # Execute all post-cleanup tasks concurrently
                await asyncio.gather(*post_cleanup_tasks, return_exceptions=True)

                # Clean up local media files
                for media_item in input_media:
                    if hasattr(media_item.media, "path") and os.path.exists(media_item.media.path):
                        try:
                            os.remove(media_item.media.path)
                        except Exception:
                            pass

                logger.info(f"Successfully reposted media group {media_group_id} in channel {chat_id}")

            except Exception as api_err:
                logger.warning(f"Failed to process media group {media_group_id} in channel {chat_id}: {api_err}")
                await update_channel_status(session, chat_id, ChannelStatus.PERMISSION_ERROR)
                await log_event(session, chat_id, message_type="album", success=False)

                # Clean up local media files in case of API failure
                for media_item in input_media:
                    if hasattr(media_item.media, "path") and os.path.exists(media_item.media.path):
                        try:
                            os.remove(media_item.media.path)
                        except Exception:
                            pass

    except Exception as e:
        logger.exception(f"Unhandled exception in media group {media_group_id} debounce: {e}")

@router.channel_post()
async def on_channel_post(message: Message, session: AsyncSession, bot: Bot):
    """
    Listens to channel posts. Detects forwards and processes them.
    """
    try:
        # Ignore non-forwarded posts
        if message.forward_origin is None:
            return

        channel_id = message.chat.id
        channel = await get_channel(session, channel_id)
        if not channel or channel.status != ChannelStatus.ACTIVE:
            return

        # Check for Document to Media Auto-Conversion criteria
        doc_convert = False
        mime_type = ""
        file_name = ""
        if message.document:
            mime_type = message.document.mime_type or ""
            file_name = message.document.file_name or ""
            if mime_type.startswith(("image/", "video/")) and not mime_type.endswith("svg+xml"):
                doc_convert = True

        # Case A: Media Group (Album) Flow
        if message.media_group_id is not None:
            media_info = get_media_info(message)
            if not media_info:
                return
            media_type, file_id = media_info
            
            serialized_entities = None
            if message.caption_entities:
                serialized_entities = [entity.model_dump() for entity in message.caption_entities]

            part_data = {
                "message_id": message.message_id,
                "media_type": media_type,
                "file_id": file_id,
                "caption": message.caption,
                "caption_entities": serialized_entities,
                "document_conversion": doc_convert,
                "mime_type": mime_type,
                "file_name": file_name
            }

            await media_buffer.add_media_group_part(message.media_group_id, part_data)
            timestamp = time.time()
            await media_buffer.set_last_arrival(message.media_group_id, timestamp)

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
        logger.info(f"Forwarded post detected in active channel {channel_id} (Msg: {message.message_id}, Type: {message.content_type})")

        # 1. Queue Enabled Flow
        if channel.queue_enabled:
            entities = [e.model_dump() for e in message.entities] if message.entities else None
            caption_entities = [e.model_dump() for e in message.caption_entities] if message.caption_entities else None
            
            payload = {
                "type": "single",
                "content_type": message.content_type,
                "original_message_id": message.message_id,
                "file_id": message.document.file_id if message.document else (get_media_info(message)[1] if get_media_info(message) else None),
                "text": message.text,
                "caption": message.caption,
                "entities": entities,
                "caption_entities": caption_entities,
                "document_conversion": doc_convert,
                "mime_type": mime_type,
                "file_name": file_name
            }
            
            await schedule_post(session, channel, payload)
            
            # Delete original instantly
            await execute_delete_with_retry(bot.delete_message, chat_id=channel_id, message_id=message.message_id)
            return

        # 2. Instant Repost Flow
        sent_msg_id = None
        footer = f"\n\n{channel.custom_footer}" if channel.custom_footer else ""

        try:
            # Document Auto-Conversion
            if doc_convert:
                os.makedirs("temp_media", exist_ok=True)
                local_path = f"temp_media/{message.document.file_id}_{file_name}"
                try:
                    file_info = await bot.get_file(message.document.file_id)
                    await bot.download_file(file_info.file_path, local_path)
                    
                    caption = (message.caption or "") + footer
                    entities = message.caption_entities
                    
                    if mime_type.startswith("image/"):
                        res = await execute_post_with_rate_limit(
                            channel_id,
                            bot.send_photo,
                            chat_id=channel_id,
                            photo=FSInputFile(local_path),
                            caption=caption,
                            caption_entities=entities
                        )
                    else:
                        res = await execute_post_with_rate_limit(
                            channel_id,
                            bot.send_video,
                            chat_id=channel_id,
                            video=FSInputFile(local_path),
                            caption=caption,
                            caption_entities=entities
                        )
                    sent_msg_id = res.message_id
                finally:
                    if os.path.exists(local_path):
                        os.remove(local_path)
            
            # Normal repost
            if sent_msg_id is None:
                if message.text:
                    res = await execute_post_with_rate_limit(
                        channel_id,
                        bot.send_message,
                        chat_id=channel_id,
                        text=message.text + footer,
                        entities=message.entities
                    )
                    sent_msg_id = res.message_id
                else:
                    res = await execute_post_with_rate_limit(
                        channel_id,
                        bot.copy_message,
                        chat_id=channel_id,
                        from_chat_id=channel_id,
                        message_id=message.message_id,
                        caption=(message.caption or "") + footer,
                        caption_entities=message.caption_entities
                    )
                    sent_msg_id = res.message_id

            # Concurrently delete original message, pin message, and log event
            post_cleanup_tasks = [
                execute_delete_with_retry(bot.delete_message, chat_id=channel_id, message_id=message.message_id),
                log_event(session, channel_id, message_type=message.content_type, success=True)
            ]
            
            if sent_msg_id and channel.auto_pin_enabled:
                post_cleanup_tasks.append(
                    bot.pin_chat_message(chat_id=channel_id, message_id=sent_msg_id, disable_notification=True)
                )
                
            await asyncio.gather(*post_cleanup_tasks, return_exceptions=True)
            logger.info(f"Successfully reposted forwarded post in channel {channel_id}")

        except Exception as api_err:
            logger.warning(f"Failed to process forwarded post in channel {channel_id}: {api_err}")
            await update_channel_status(session, channel_id, ChannelStatus.PERMISSION_ERROR)
            await log_event(session, channel_id, message_type=message.content_type, success=False)


    except Exception as e:
        logger.exception(f"Unhandled exception in channel_posts handler: {e}")
