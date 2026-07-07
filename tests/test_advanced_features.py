import asyncio
import json
import urllib.parse
from unittest.mock import AsyncMock
from datetime import datetime

from app.config import settings
from app.db.base import async_session_maker
from app.db.models import User, Channel, QueuePost, ChannelStatus
from app.db.crud import create_or_update_user, get_total_users_count, add_to_queue
from app.utils.twa_auth import verify_telegram_webapp_data
from app.handlers.commands import cmd_owner, cmd_stats

async def test_database_models():
    print("\n--- Test Case 1: Advanced DB Models ---")
    async with async_session_maker() as session:
        # 1. Test User creation & retrieval
        test_uid = 555444333
        await create_or_update_user(
            session,
            user_id=test_uid,
            username="test_adv_user",
            first_name="Advanced User"
        )
        
        # Verify count
        count = await get_total_users_count(session)
        assert count > 0
        print(f"Verified: User table populated. Count: {count}")
        
        # 2. Test Channel overrides (footer, queue, pin)
        ch_id = -1009999999
        ch = Channel(
            channel_id=ch_id,
            owner_user_id=test_uid,
            title="Advanced Test Channel",
            status=ChannelStatus.ACTIVE,
            custom_footer="Clean Posts Footer",
            auto_pin_enabled=True,
            queue_enabled=True,
            queue_interval_minutes=30
        )
        session.add(ch)
        await session.commit()
        await session.refresh(ch)
        
        assert ch.custom_footer == "Clean Posts Footer"
        assert ch.auto_pin_enabled is True
        assert ch.queue_enabled is True
        assert ch.queue_interval_minutes == 30
        print("Verified: Channel config overrides successfully written.")
        
        # 3. Test QueuePost creation
        post = await add_to_queue(
            session,
            channel_id=ch.id,
            message_data=json.dumps({"type": "single", "content_type": "text", "text": "Hello Queue"}),
            scheduled_for=datetime.now()
        )
        assert post.id is not None
        assert post.is_processed is False
        print("Verified: QueuePost record successfully written.")
        
        # Cleanup
        await session.delete(post)
        await session.delete(ch)
        
        # Delete user
        result = await session.execute(
            sa_select := select_user() if 'select_user' in globals() else select_user_fallback(test_uid)
        )
        user = result.scalar_one_or_none()
        if user:
            await session.delete(user)
        await session.commit()
        print("Cleaned up database test records.")

def select_user_fallback(user_id):
    from sqlalchemy import select
    return select(User).where(User.user_id == user_id)

async def test_twa_security():
    print("\n--- Test Case 2: TWA Signature Authentication ---")
    # A valid authentication sequence mock hash generated using the standard Telegram secret formula
    import hmac
    import hashlib
    
    token = settings.BOT_TOKEN.get_secret_value()
    init_data_dict = {
        "auth_date": "1710000000",
        "query_id": "AAHpdxwAAAAAAOl3HA",
        "user": json.dumps({"id": 6447766151, "first_name": "Mike", "username": "MikeyyFrr"})
    }
    
    # Sort and join
    data_check_string = "\n".join(f"{k}={init_data_dict[k]}" for k in sorted(init_data_dict.keys()))
    
    # Secret Key
    secret_key = hmac.new(
        b"WebAppsData",
        token.encode("utf-8"),
        hashlib.sha256
    ).digest()
    
    # Target Hash
    tg_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    # Assemble complete mock initData query string
    init_data_dict["hash"] = tg_hash
    query_string = urllib.parse.urlencode(init_data_dict)
    
    # Call authentication verification
    user_info = verify_telegram_webapp_data(query_string)
    assert user_info is not None
    assert user_info["id"] == 6447766151
    print("Verified: HMAC signature validation passed successfully.")

async def test_admin_commands():
    print("\n--- Test Case 3: Admin CLI Commands ---")
    owner_id = settings.OWNER_ID
    
    msg_owner = AsyncMock()
    msg_owner.from_user.id = owner_id
    msg_owner.text = "/owner"
    
    await cmd_owner(msg_owner)
    msg_owner.reply.assert_called_once()
    assert "Owner Administrative Control" in msg_owner.reply.call_args[0][0]
    print("Verified: /owner replies successfully to bot owner.")
    
    msg_non_owner = AsyncMock()
    msg_non_owner.from_user.id = 123456
    msg_non_owner.text = "/owner"
    
    await cmd_owner(msg_non_owner)
    msg_non_owner.reply.assert_not_called()
    print("Verified: /owner silently ignores non-owner messages.")

async def main():
    print("Running advanced features unit tests...")
    await test_twa_security()
    await test_admin_commands()
    await test_database_models()
    print("\nAll advanced features tests completed successfully! 🎉")

if __name__ == "__main__":
    asyncio.run(main())
