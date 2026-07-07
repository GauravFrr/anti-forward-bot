import asyncio
import json
import os
from datetime import datetime, timedelta
from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Bot
from aiogram.types import InputMediaPhoto, InputMediaVideo, InputMediaAudio, InputMediaDocument, MessageEntity, FSInputFile

from app.db.base import async_session_maker
from app.db.models import Channel, QueuePost, ChannelStatus, EventLog
from app.utils.retry import execute_post_with_rate_limit
from app.db.crud import get_pending_queue_posts

async def schedule_post(session: AsyncSession, channel: Channel, message_data: dict) -> QueuePost:
    """
    Calculates the next available slot for the channel queue (spacing out posts)
    and inserts it into the queue_posts table.
    """
    interval = timedelta(minutes=channel.queue_interval_minutes)
    
    # Get the latest scheduled pending post for this channel
    result = await session.execute(
        select(QueuePost)
        .where(QueuePost.channel_id == channel.id)
        .where(QueuePost.is_processed == False)
        .order_by(QueuePost.scheduled_for.desc())
        .limit(1)
    )
    latest_post = result.scalar_one_or_none()
    
    if latest_post:
        scheduled_for = latest_post.scheduled_for + interval
    else:
        scheduled_for = datetime.now() + interval
        
    post = QueuePost(
        channel_id=channel.id,
        message_data=json.dumps(message_data),
        scheduled_for=scheduled_for
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)
    
    logger.info(f"Scheduled post ID {post.id} for channel {channel.channel_id} at {scheduled_for}")
    return post

async def process_queued_post(bot: Bot, session: AsyncSession, post: QueuePost):
    """
    Executes a single queued post (single message or album).
    """
    try:
        channel = post.channel
        if not channel or channel.status != ChannelStatus.ACTIVE:
            logger.warning(f"Skipping queue post {post.id} because channel is not active.")
            post.is_processed = True
            await session.commit()
            return
            
        data = json.loads(post.message_data)
        post_type = data.get("type", "single")
        
        # Determine Custom Footer
        footer = f"\n\n{channel.custom_footer}" if channel.custom_footer else ""
        
        sent_msg_id = None
        
        # 1. Single Post Execution
        if post_type == "single":
            content_type = data.get("content_type")
            file_id = data.get("file_id")
            text = data.get("text", "")
            caption = data.get("caption", "")
            
            # Reconstruct entities
            entities = [MessageEntity.model_validate(e) for e in data.get("entities") or []]
            caption_entities = [MessageEntity.model_validate(e) for e in data.get("caption_entities") or []]
            
            # Apply Custom Footer
            if text:
                text += footer
            if caption:
                caption += footer
                
            # Document to Media Auto-Conversion (Feature C)
            doc_convert = data.get("document_conversion", False)
            if doc_convert and content_type == "document":
                # Check mime type from data
                mime_type = data.get("mime_type", "")
                file_name = data.get("file_name", "file")
                
                os.makedirs("temp_media", exist_ok=True)
                local_path = f"temp_media/{file_id}_{file_name}"
                
                try:
                    # Download document
                    file_info = await bot.get_file(file_id)
                    await bot.download_file(file_info.file_path, local_path)
                    
                    # Upload as standard photo/video
                    if mime_type.startswith("image/"):
                        res = await execute_post_with_rate_limit(
                            channel.channel_id,
                            bot.send_photo,
                            chat_id=channel.channel_id,
                            photo=FSInputFile(local_path),
                            caption=caption,
                            caption_entities=caption_entities
                        )
                        sent_msg_id = res.message_id
                    elif mime_type.startswith("video/"):
                        res = await execute_post_with_rate_limit(
                            channel.channel_id,
                            bot.send_video,
                            chat_id=channel.channel_id,
                            video=FSInputFile(local_path),
                            caption=caption,
                            caption_entities=caption_entities
                        )
                        sent_msg_id = res.message_id
                finally:
                    if os.path.exists(local_path):
                        os.remove(local_path)
            
            # Standard single post copy or send
            if sent_msg_id is None:
                if content_type == "text":
                    res = await execute_post_with_rate_limit(
                        channel.channel_id,
                        bot.send_message,
                        chat_id=channel.channel_id,
                        text=text,
                        entities=entities
                    )
                    sent_msg_id = res.message_id
                else:
                    res = await execute_post_with_rate_limit(
                        channel.channel_id,
                        bot.copy_message,
                        chat_id=channel.channel_id,
                        from_chat_id=channel.channel_id, # Target copies from itself internally
                        message_id=data.get("original_message_id"),
                        caption=caption,
                        caption_entities=caption_entities
                    )
                    sent_msg_id = res.message_id
                    
        # 2. Album Post Execution
        elif post_type == "album":
            parts = data.get("parts", [])
            
            async def prepare_part(part):
                m_type = part["media_type"]
                file_id = part["file_id"]
                caption = part["caption"] or ""
                
                # Append footer only to the first part containing caption (standard album style)
                if caption:
                    caption += footer
                    
                entities = [MessageEntity.model_validate(e) for e in part.get("caption_entities") or []]
                
                # Check for Document to Media Auto-Conversion inside albums
                doc_convert = part.get("document_conversion", False)
                if doc_convert and m_type == "document":
                    mime_type = part.get("mime_type", "")
                    file_name = part.get("file_name", "file")
                    
                    os.makedirs("temp_media", exist_ok=True)
                    local_path = f"temp_media/{file_id}_{file_name}"
                    
                    try:
                        file_info = await bot.get_file(file_id)
                        await bot.download_file(file_info.file_path, local_path)
                        
                        # We use FSInputFile for the media
                        if mime_type.startswith("image/"):
                            return InputMediaPhoto(media=FSInputFile(local_path), caption=caption, caption_entities=entities)
                        elif mime_type.startswith("video/"):
                            return InputMediaVideo(media=FSInputFile(local_path), caption=caption, caption_entities=entities)
                    except Exception as e:
                        logger.error(f"Failed to convert document in album: {e}")
                        # Fallback to standard doc file
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

            # Prepare all parts concurrently in the background queue
            prepare_tasks = [prepare_part(part) for part in parts]
            input_media = await asyncio.gather(*prepare_tasks, return_exceptions=True)
            input_media = [im for im in input_media if im is not None and not isinstance(im, Exception)]
            
            # Send media group
            res_list = await execute_post_with_rate_limit(
                channel.channel_id,
                bot.send_media_group,
                chat_id=channel.channel_id,
                media=input_media
            )
            if res_list:
                sent_msg_id = res_list[0].message_id
                
            # Clean up any local temporary files used for conversion
            for media_item in input_media:
                if hasattr(media_item.media, "path") and os.path.exists(media_item.media.path):
                    try:
                        os.remove(media_item.media.path)
                    except Exception:
                        pass

        # Auto-Pin Syncing (Feature B)
        if sent_msg_id and (channel.auto_pin_enabled or data.get("should_pin", False)):
            try:
                await bot.pin_chat_message(chat_id=channel.channel_id, message_id=sent_msg_id, disable_notification=True)
                logger.info(f"Auto-pinned clean repost {sent_msg_id} in channel {channel.channel_id}")
            except Exception as pin_err:
                logger.warning(f"Failed to auto-pin message {sent_msg_id} in channel {channel.channel_id}: {pin_err}")

        # Mark post as processed
        post.is_processed = True
        await session.commit()
        
        # Log successful event in DB
        event = EventLog(channel_id=channel.id, message_type=post_type, success=True)
        session.add(event)
        await session.commit()
        
        logger.info(f"Queue post {post.id} successfully processed and sent to channel {channel.channel_id}")

    except Exception as err:
        logger.exception(f"Failed to process queue post {post.id}: {err}")
        # Log failed event in DB and mark as processed to prevent infinite loop
        try:
            event = EventLog(channel_id=post.channel_id, message_type="queue_fail", success=False)
            session.add(event)
            post.is_processed = True
            await session.commit()
        except Exception:
            pass

async def queue_processor_loop(bot: Bot):
    """
    Background worker loop polling queue_posts table for release times.
    """
    logger.info("Starting background Queue Processor loop...")
    while True:
        try:
            await asyncio.sleep(10)  # Check queue every 10 seconds
            async with async_session_maker() as session:
                posts = await get_pending_queue_posts(session)
                for post in posts:
                    # Re-fetch with channel relationship joined
                    result = await session.execute(
                        select(QueuePost).where(QueuePost.id == post.id)
                    )
                    full_post = result.scalar_one_or_none()
                    if full_post:
                        # Load channel eagerly
                        await session.refresh(full_post, ["channel"])
                        await process_queued_post(bot, session, full_post)
        except Exception as e:
            logger.error(f"Error inside queue processor loop: {e}")
