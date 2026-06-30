from datetime import datetime
from database import get_user


async def check_subscription(user_id: int) -> bool:
    """Возвращает True если подписка активна"""
    user = await get_user(user_id)
    if not user or not user["subscription_end"]:
        return False

    try:
        end_date = datetime.fromisoformat(user["subscription_end"])
        return end_date > datetime.now()
    except:
        return False


async def get_subscription_days_left(user_id: int) -> int:
    """Возвращает количество дней до конца подписки"""
    user = await get_user(user_id)
    if not user or not user["subscription_end"]:
        return 0

    try:
        end_date = datetime.fromisoformat(user["subscription_end"])
        now = datetime.now()
        if end_date > now:
            return (end_date - now).days
        return 0
    except:
        return 0