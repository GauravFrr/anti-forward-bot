from aiogram.utils.web_app import check_webapp_signature, parse_webapp_init_data
from app.config import settings
from loguru import logger

def verify_telegram_webapp_data(init_data: str) -> dict | None:
    """
    Verifies the integrity and authenticity of the data received from the Telegram Web App
    using aiogram's official verification utilities.
    Returns the parsed user dict if valid, otherwise None.
    """
    try:
        token = settings.BOT_TOKEN.get_secret_value()
        
        # Verify using official aiogram utility
        if not check_webapp_signature(token, init_data):
            logger.warning("TWA HMAC signature verification failed.")
            return None
            
        # Parse verified data
        web_app_data = parse_webapp_init_data(init_data)
        
        if web_app_data.user:
            return {
                "id": web_app_data.user.id,
                "first_name": web_app_data.user.first_name,
                "last_name": web_app_data.user.last_name or "",
                "username": web_app_data.user.username or "",
                "language_code": web_app_data.user.language_code or "en"
            }
        return {}
    except Exception as e:
        logger.exception(f"Exception during TWA verification: {e}")
        return None
